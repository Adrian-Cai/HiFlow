import tempfile
import unittest
from pathlib import Path

from mobile_automation.activity import ActivityLevel
from mobile_automation.errors import UserActionRequired, WorkflowError
from mobile_automation.models import BatchStatus, CandidateStatus, Job, MatchResult
from mobile_automation.storage import BatchStore
from mobile_automation.workflow import apply_batch, scan_and_create_batch


def make_job(index: int, activity: ActivityLevel = ActivityLevel.TODAY) -> Job:
    return Job(
        title=f"测试开发工程师{index}",
        company=f"公司{index}",
        salary="20-30K",
        location="上海",
        activity_level=activity,
        activity_text="今日活跃" if activity == ActivityLevel.TODAY else "未知",
        jd_text="负责自动化测试、接口测试、性能压测和持续集成质量保障。" * 2,
    )


class FakeScanner:
    def __init__(self, jobs: list[Job]) -> None:
        self.jobs = jobs

    def scan_jobs(self, limit: int) -> list[Job]:
        return self.jobs[:limit]


class FakeMatcher:
    def __init__(self) -> None:
        self.matched: list[str] = []

    def match(self, resume_id: str, job: Job) -> MatchResult:
        self.matched.append(job.fingerprint)
        return MatchResult(score=95, decision="RECOMMEND")


class PausingApplicator:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.pause_once = True

    def contact(self, job: Job) -> None:
        self.calls.append(job.fingerprint)
        if len(self.calls) == 2 and self.pause_once:
            self.pause_once = False
            raise UserActionRequired("SECURITY_VERIFICATION", "检测到安全验证")


class WorkflowTests(unittest.TestCase):
    def test_scan_matches_only_active_jobs_and_creates_review_batch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = BatchStore(Path(directory))
            active = make_job(1)
            unknown = make_job(2, ActivityLevel.UNKNOWN)
            matcher = FakeMatcher()

            batch = scan_and_create_batch(
                FakeScanner([active, unknown]), matcher, store, resume_id="resume_001", scan_limit=10
            )

            self.assertEqual(batch.status, BatchStatus.REVIEW)
            self.assertEqual([item.job.fingerprint for item in batch.candidates], [active.fingerprint])
            self.assertEqual(matcher.matched, [active.fingerprint])

    def test_apply_requires_confirmation_and_pauses_for_manual_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = BatchStore(Path(directory))
            batch = scan_and_create_batch(
                FakeScanner([make_job(1), make_job(2)]),
                FakeMatcher(),
                store,
                resume_id="resume_001",
                scan_limit=10,
            )
            applicator = PausingApplicator()

            with self.assertRaises(WorkflowError) as raised:
                apply_batch(batch, applicator, store)
            self.assertEqual(raised.exception.code, "BATCH_NOT_CONFIRMED")

            batch.confirm()
            store.save(batch)
            paused = apply_batch(batch, applicator, store)

            self.assertEqual(paused.status, BatchStatus.PAUSED)
            self.assertEqual(paused.candidates[0].status, CandidateStatus.CONTACTED)
            self.assertEqual(paused.candidates[1].status, CandidateStatus.NEEDS_USER_ACTION)

            completed = apply_batch(paused, applicator, store, resume=True)
            self.assertEqual(completed.status, BatchStatus.COMPLETED)
            self.assertTrue(all(item.status == CandidateStatus.CONTACTED for item in completed.candidates))


if __name__ == "__main__":
    unittest.main()
