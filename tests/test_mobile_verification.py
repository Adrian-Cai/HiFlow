import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mobile_automation.activity import ActivityLevel
from mobile_automation.errors import AutomationError, WorkflowError
from mobile_automation.models import Job
from mobile_automation.storage import ApplicationStore, CHINA_TIMEZONE
from mobile_automation.verification import (
    VerificationIdentity,
    VerificationReportStore,
    VerificationSessionMetrics,
    collect_verification_identity,
    run_stability_verification,
)


def verification_job(index: int) -> Job:
    return Job(
        title=f"测试开发工程师{index}",
        company=f"示例公司{index}",
        salary="20-30K",
        location="上海",
        activity_level=ActivityLevel.TODAY,
        activity_text="今日活跃",
        jd_text="负责接口自动化、测试平台、持续集成和质量工程建设。" * 3,
    )


class FakeVerificationSession:
    def __init__(self, jobs: list[Job], *, failure: AutomationError | None = None) -> None:
        self.jobs = list(jobs)
        self.failure = failure
        self.finished: list[str] = []

    def verify_preconditions(self) -> dict[str, str]:
        return {"city": "上海", "filterText": "筛选·1"}

    def next_job(self) -> Job | None:
        if self.failure is not None:
            failure, self.failure = self.failure, None
            raise failure
        return self.jobs.pop(0) if self.jobs else None

    def finish_current_job(self) -> None:
        self.finished.append("returned")

    def verification_metrics(self) -> VerificationSessionMetrics:
        return VerificationSessionMetrics(scrolls=12, refreshes=0, contact_attempts=0)


class VerificationWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = VerificationIdentity(
            device_serial="DEVICE-001",
            boss_version="13.120",
            selector_hash="selector-hash",
            code_hash="code-hash",
        )
        self.now = datetime(2026, 7, 15, 12, 0, tzinfo=CHINA_TIMEZONE)

    def test_fifty_read_only_round_trips_create_a_pass_report_without_changing_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            application_store = ApplicationStore(root)
            report_store = VerificationReportStore(root / "verifications")
            session = FakeVerificationSession([verification_job(index) for index in range(50)])
            progress: list[tuple[int, int, str]] = []

            report = run_stability_verification(
                session,
                application_store,
                report_store,
                identity=self.identity,
                target_jobs=50,
                now_provider=lambda: self.now,
                on_progress=lambda completed, target, job: progress.append(
                    (completed, target, job.title)
                ),
            )

            self.assertEqual(report.status, "PASS")
            self.assertEqual(report.unique_jobs, 50)
            self.assertEqual(report.detail_round_trips, 50)
            self.assertEqual(len(session.finished), 50)
            self.assertEqual(progress[0], (1, 50, "测试开发工程师0"))
            self.assertEqual(progress[-1], (50, 50, "测试开发工程师49"))
            self.assertEqual(report.contact_attempts, 0)
            self.assertEqual(report.duration_seconds, 0)
            self.assertEqual(report.ledger_before, report.ledger_after)
            self.assertFalse(application_store.ledger_path.exists())
            self.assertEqual(len(list((root / "verifications").glob("verification-*.json"))), 1)

    def test_exhausting_the_list_before_target_is_incomplete_and_does_not_open_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_store = VerificationReportStore(root / "verifications")
            report = run_stability_verification(
                FakeVerificationSession([verification_job(index) for index in range(30)]),
                ApplicationStore(root),
                report_store,
                identity=self.identity,
                target_jobs=50,
                now_provider=lambda: self.now,
            )

            self.assertEqual(report.status, "INCOMPLETE")
            self.assertEqual(report.unique_jobs, 30)
            with self.assertRaises(WorkflowError) as raised:
                report_store.require_valid_gate(self.identity, minimum_jobs=50)
            self.assertEqual(raised.exception.code, "VERIFICATION_REQUIRED")

    def test_any_appium_page_timeout_fails_immediately_without_reconnect(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = run_stability_verification(
                FakeVerificationSession(
                    [verification_job(1)],
                    failure=AutomationError("APPIUM_PAGE_READ_FAILED", "页面服务失去响应"),
                ),
                ApplicationStore(root),
                VerificationReportStore(root / "verifications"),
                identity=self.identity,
                target_jobs=50,
                now_provider=lambda: self.now,
            )

            self.assertEqual(report.status, "FAIL")
            self.assertEqual(report.ui_timeouts, 1)
            self.assertEqual(report.reconnects, 0)
            self.assertEqual(report.error_code, "APPIUM_PAGE_READ_FAILED")

    def test_duplicate_detail_round_trip_cannot_produce_a_pass_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jobs = [verification_job(0)] + [verification_job(index) for index in range(50)]
            report = run_stability_verification(
                FakeVerificationSession(jobs),
                ApplicationStore(root),
                VerificationReportStore(root / "verifications"),
                identity=self.identity,
                target_jobs=50,
                now_provider=lambda: self.now,
            )

        self.assertEqual(report.status, "FAIL")
        self.assertEqual(report.unique_jobs, 50)
        self.assertEqual(report.detail_round_trips, 51)
        self.assertEqual(report.error_code, "VERIFICATION_DUPLICATE_DETAIL")

    def test_gate_is_invalidated_when_device_boss_selector_or_code_identity_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_store = VerificationReportStore(root / "verifications")
            run_stability_verification(
                FakeVerificationSession([verification_job(index) for index in range(50)]),
                ApplicationStore(root),
                report_store,
                identity=self.identity,
                target_jobs=50,
                now_provider=lambda: self.now,
            )

            self.assertEqual(
                report_store.require_valid_gate(self.identity, minimum_jobs=50).status,
                "PASS",
            )
            changed = VerificationIdentity(
                device_serial=self.identity.device_serial,
                boss_version=self.identity.boss_version,
                selector_hash=self.identity.selector_hash,
                code_hash="changed-code-hash",
            )
            with self.assertRaises(WorkflowError):
                report_store.require_valid_gate(changed, minimum_jobs=50)

    def test_identity_uses_device_boss_selector_and_critical_code_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selector = root / "selectors.v1.json"
            selector.write_text('{"version": 1}', encoding="utf-8")
            code = root / "workflow.py"
            code.write_text("VERSION = 1\n", encoding="utf-8")
            responses = [
                SimpleNamespace(stdout="DEVICE-001\n"),
                SimpleNamespace(stdout="versionCode=123\nversionName=13.140\n"),
            ]
            with patch("mobile_automation.verification.subprocess.run", side_effect=responses):
                identity = collect_verification_identity(
                    selector,
                    critical_paths=(code,),
                )

        self.assertEqual(identity.device_serial, "DEVICE-001")
        self.assertEqual(identity.boss_version, "13.140 (123)")
        self.assertEqual(len(identity.selector_hash), 64)
        self.assertEqual(len(identity.code_hash), 64)


if __name__ == "__main__":
    unittest.main()
