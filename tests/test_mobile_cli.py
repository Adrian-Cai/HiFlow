import unittest
from contextlib import redirect_stdout
from io import BytesIO, StringIO, TextIOWrapper
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from mobile_automation.activity import ActivityLevel
from mobile_automation.cli import (
    _configure_console_errors,
    build_parser,
    doctor_result,
    format_device_status,
    format_failure,
    format_progress_event,
    run,
)
from mobile_automation.errors import AutomationError
from mobile_automation.models import Job
from mobile_automation.workflow import ProgressEvent, StreamingRunResult


class CliContractTests(unittest.TestCase):
    def test_console_output_escapes_characters_missing_from_gbk(self) -> None:
        raw = BytesIO()
        stream = TextIOWrapper(raw, encoding="gbk", errors="strict")
        _configure_console_errors(stream, stream)
        print("岗位\u2f45", file=stream)
        stream.flush()

        self.assertEqual(stream.errors, "backslashreplace")
        self.assertIn("\\u2f45", raw.getvalue().decode("gbk"))

    def test_formats_device_status_as_a_short_chinese_progress_line(self) -> None:
        self.assertEqual(
            format_device_status("列表", "正在向下滚动查找新岗位"),
            "[列表] 正在向下滚动查找新岗位",
        )

    def test_formats_failures_as_readable_chinese_instead_of_raw_json(self) -> None:
        message = format_failure("APPIUM_SESSION_FAILED", "无法建立 Appium 真机会话")

        self.assertIn("[失败]", message)
        self.assertIn("无法建立 Appium 真机会话", message)
        self.assertIn("APPIUM_SESSION_FAILED", message)

    def test_security_verification_failure_explains_that_progress_is_preserved(self) -> None:
        message = format_failure("SECURITY_VERIFICATION", "检测到需要人工处理的页面：安全验证")

        self.assertIn("任务已暂停", message)
        self.assertIn("进度已经保留", message)

    def test_formats_progress_events_as_short_chinese_explanations(self) -> None:
        job = Job(
            title="测试开发工程师",
            company="示例科技",
            salary="20-30K",
            location="上海",
            activity_level=ActivityLevel.TODAY,
            activity_text="今日活跃",
            jd_text="负责接口自动化、UI自动化和质量平台建设。" * 3,
        )

        self.assertIn("正在检查岗位", format_progress_event(ProgressEvent("JOB_READ", job=job)))
        self.assertIn(
            "薪资低于设定下限",
            format_progress_event(ProgressEvent("JOB_SKIPPED", job=job, reason="SALARY_BELOW_MINIMUM")),
        )
        self.assertIn(
            "匹配度 95%",
            format_progress_event(ProgressEvent("JOB_MATCHED", job=job, score=95)),
        )
        self.assertIn(
            "今日累计 3/150",
            format_progress_event(ProgressEvent("JOB_CONTACTED", job=job, daily_total=3, daily_limit=150)),
        )
        self.assertIn(
            "暂停 120 秒",
            format_progress_event(ProgressEvent("COOLDOWN_STARTED", seconds=120)),
        )
        self.assertIn(
            "继续查找下一个岗位",
            format_progress_event(ProgressEvent("NEXT_JOB_REQUESTED")),
        )
        self.assertIn(
            "今日历史已沟通 1/150，剩余 149",
            format_progress_event(ProgressEvent("RUN_STARTED", daily_total=1, daily_limit=150)),
        )

    def test_auto_contract_uses_confirmed_streaming_defaults(self) -> None:
        args = build_parser().parse_args(["auto", "--resume-id", "resume_001"])

        self.assertEqual(args.command, "auto")
        self.assertEqual(args.minimum_salary_k, 15)
        self.assertEqual(args.threshold, 90)
        self.assertEqual(args.batch_size, 5)
        self.assertEqual(args.cooldown_seconds, 120)
        self.assertEqual(args.daily_limit, 150)

    def test_verify_contract_defaults_to_fifty_jobs_and_thirty_scrolls(self) -> None:
        args = build_parser().parse_args(["verify"])

        self.assertEqual(args.command, "verify")
        self.assertEqual(args.job_limit, 50)
        self.assertEqual(args.max_scrolls, 30)

    def test_verify_is_read_only_and_never_constructs_match_client(self) -> None:
        class AdapterContext:
            def __enter__(self) -> object:
                return object()

            def __exit__(self, *_args: object) -> None:
                return None

        with TemporaryDirectory() as root:
            args = build_parser().parse_args(["--data-dir", root, "verify", "--job-limit", "5"])
            report = SimpleNamespace(
                status="PASS",
                unique_jobs=5,
                target_jobs=5,
                to_dict=lambda: {"status": "PASS"},
            )
            identity = SimpleNamespace(gate_id="gate")
            with (
                patch("mobile_automation.cli._adapter", return_value=AdapterContext()) as adapter_factory,
                patch("mobile_automation.cli.collect_verification_identity", return_value=identity),
                patch("mobile_automation.cli.run_stability_verification", return_value=report) as verify_run,
                patch("mobile_automation.cli.MatchClient") as matcher,
            ):
                exit_code = run(args)

        self.assertEqual(exit_code, 0)
        adapter_factory.assert_called_once_with(args, allow_contact=False)
        matcher.assert_not_called()
        self.assertEqual(verify_run.call_args.kwargs["target_jobs"], 5)

    def test_auto_reconnects_after_a_transient_page_read_failure(self) -> None:
        class AdapterContext:
            def __enter__(self) -> object:
                return object()

            def __exit__(self, *_args: object) -> None:
                return None

        with TemporaryDirectory() as root:
            args = build_parser().parse_args(
                ["--data-dir", root, "auto", "--resume-id", "resume_001", "--daily-limit", "1"]
            )
            output = StringIO()
            with (
                patch("mobile_automation.cli._adapter", side_effect=[AdapterContext(), AdapterContext()]),
                patch(
                    "mobile_automation.cli.run_streaming_applications",
                    side_effect=[
                        AutomationError("APPIUM_PAGE_READ_FAILED", "页面服务短暂失去响应"),
                        StreamingRunResult(1, 0, 1, "DAILY_LIMIT_REACHED"),
                    ],
                ) as streaming,
                patch("mobile_automation.cli.time.sleep"),
                redirect_stdout(output),
            ):
                exit_code = run(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(streaming.call_count, 2)
        self.assertIn("正在重新连接手机", output.getvalue())

    def test_auto_starts_without_reading_a_fifty_job_gate(self) -> None:
        class AdapterContext:
            def __enter__(self) -> object:
                return object()

            def __exit__(self, *_args: object) -> None:
                return None

        with TemporaryDirectory() as root:
            args = build_parser().parse_args(
                ["--data-dir", root, "auto", "--resume-id", "resume_001", "--daily-limit", "1"]
            )
            with (
                patch("mobile_automation.cli.collect_verification_identity") as collect_identity,
                patch("mobile_automation.cli.VerificationReportStore.require_valid_gate") as require_gate,
                patch("mobile_automation.cli._adapter", return_value=AdapterContext()) as adapter_factory,
                patch(
                    "mobile_automation.cli.run_streaming_applications",
                    return_value=StreamingRunResult(1, 0, 1, "DAILY_LIMIT_REACHED"),
                ),
            ):
                exit_code = run(args)

        self.assertEqual(exit_code, 0)
        adapter_factory.assert_called_once_with(args, allow_contact=True)
        collect_identity.assert_not_called()
        require_gate.assert_not_called()

    def test_scan_contract(self) -> None:
        args = build_parser().parse_args(["scan", "--resume-id", "resume_001"])
        self.assertEqual(args.command, "scan")
        self.assertEqual(args.resume_id, "resume_001")
        self.assertEqual(args.threshold, 80)
        self.assertEqual(args.candidate_limit, 5)

    def test_batch_commands_require_batch_id(self) -> None:
        for command in ("apply", "resume", "status"):
            with self.subTest(command=command):
                args = build_parser().parse_args([command, "--batch-id", "batch-123"])
                self.assertEqual(args.batch_id, "batch-123")

    def test_doctor_requires_authorized_device_and_python_client(self) -> None:
        pending = doctor_result(["SERIAL authorizing product:phone"], client_installed=False)
        ready = doctor_result(["SERIAL device product:phone"], client_installed=True)

        self.assertFalse(pending["ok"])
        self.assertEqual(pending["deviceState"], "authorizing")
        self.assertTrue(ready["ok"])
        self.assertEqual(ready["deviceState"], "device")


if __name__ == "__main__":
    unittest.main()
