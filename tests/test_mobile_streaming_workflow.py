import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mobile_automation.activity import ActivityLevel
from mobile_automation.models import Job, MatchResult
from mobile_automation.policy import JobPolicy
from mobile_automation.storage import ApplicationStore
from mobile_automation.workflow import run_streaming_applications


CHINA_TZ = timezone(timedelta(hours=8))


def make_job(index: int, *, salary: str = "20-30K", description: str = "接口自动化和质量平台") -> Job:
    return Job(
        title=f"测试开发工程师{index}",
        company=f"公司{index}",
        salary=salary,
        location="上海",
        activity_level=ActivityLevel.TODAY,
        activity_text="今日活跃",
        jd_text=(f"负责{description}，覆盖性能测试、持续集成和服务端质量保障。" * 2),
    )


class FakeJobSession:
    def __init__(self, jobs: list[Job]) -> None:
        self.jobs = jobs
        self.index = 0
        self.current: Job | None = None
        self.contacted: list[str] = []

    def next_job(self) -> Job | None:
        if self.index >= len(self.jobs):
            self.current = None
            return None
        self.current = self.jobs[self.index]
        self.index += 1
        return self.current

    def contact_current(self) -> bool:
        if self.current is None:
            raise AssertionError("没有当前岗位")
        self.contacted.append(self.current.fingerprint)
        return True


class FakeMatcher:
    def __init__(self, score: int = 95) -> None:
        self.score = score
        self.matched: list[str] = []

    def match(self, resume_id: str, job: Job) -> MatchResult:
        self.matched.append(job.fingerprint)
        return MatchResult(score=self.score, decision="RECOMMEND")


class StreamingWorkflowTests(unittest.TestCase):
    def test_filters_before_matching_and_contacts_eligible_job_on_current_detail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            low_salary = make_job(1, salary="14-25K")
            hardware = make_job(2, description="嵌入式 MCU 硬件测试")
            suitable = make_job(3)
            session = FakeJobSession([low_salary, hardware, suitable])
            matcher = FakeMatcher()
            store = ApplicationStore(Path(directory))

            result = run_streaming_applications(
                session,
                matcher,
                store,
                resume_id="resume_001",
                policy=JobPolicy(),
                sleeper=lambda _seconds: None,
            )

            self.assertEqual(matcher.matched, [suitable.fingerprint])
            self.assertEqual(session.contacted, [suitable.fingerprint])
            self.assertEqual(result.contacted, 1)
            self.assertEqual(result.skipped, 2)

    def test_waits_two_minutes_after_each_five_successes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            waits: list[float] = []
            session = FakeJobSession([make_job(index) for index in range(6)])

            result = run_streaming_applications(
                session,
                FakeMatcher(),
                ApplicationStore(Path(directory)),
                resume_id="resume_001",
                policy=JobPolicy(),
                batch_size=5,
                cooldown_seconds=120,
                sleeper=waits.append,
            )

            self.assertEqual(result.contacted, 6)
            self.assertEqual(waits, [120])

    def test_stops_at_persisted_daily_limit_without_final_wait(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ApplicationStore(Path(directory))
            now = datetime(2026, 7, 15, 9, 0, tzinfo=CHINA_TZ)
            for index in range(149):
                store.record_success("resume_001", make_job(index), MatchResult(95, "RECOMMEND"), at=now)
            waits: list[float] = []
            session = FakeJobSession([make_job(200), make_job(201)])

            result = run_streaming_applications(
                session,
                FakeMatcher(),
                store,
                resume_id="resume_001",
                policy=JobPolicy(),
                daily_limit=150,
                sleeper=waits.append,
                now_provider=lambda: now,
            )

            self.assertEqual(result.contacted, 1)
            self.assertEqual(result.daily_total, 150)
            self.assertEqual(result.stop_reason, "DAILY_LIMIT_REACHED")
            self.assertEqual(waits, [])
            self.assertEqual(len(session.contacted), 1)

    def test_skips_job_already_recorded_by_an_earlier_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ApplicationStore(Path(directory))
            job = make_job(1)
            store.record_success("resume_001", job, MatchResult(95, "RECOMMEND"))
            session = FakeJobSession([job])
            matcher = FakeMatcher()

            result = run_streaming_applications(
                session,
                matcher,
                store,
                resume_id="resume_001",
                policy=JobPolicy(),
                sleeper=lambda _seconds: None,
            )

            self.assertEqual(result.contacted, 0)
            self.assertEqual(matcher.matched, [])
            self.assertEqual(session.contacted, [])


if __name__ == "__main__":
    unittest.main()
