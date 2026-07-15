import unittest

from mobile_automation.activity import ActivityLevel
from mobile_automation.models import Job, MatchResult, make_job_fingerprint
from mobile_automation.workflow import select_candidates


def make_job(index: int, activity: ActivityLevel = ActivityLevel.TODAY) -> Job:
    return Job(
        title=f"测试开发工程师{index}",
        company=f"公司{index}",
        salary="20-30K",
        location="上海",
        activity_level=activity,
        activity_text="今日活跃",
        jd_text="负责自动化测试、接口测试、性能测试与持续集成质量保障。" * 2,
    )


class JobDomainTests(unittest.TestCase):
    def test_fingerprint_is_stable_across_whitespace_and_case(self) -> None:
        left = make_job_fingerprint(" 测试开发 ", "ACME", "20-30K", "上海")
        right = make_job_fingerprint("测试开发", " acme ", "20-30k", "上海")
        self.assertEqual(left, right)

    def test_selection_requires_activity_recommendation_threshold_and_no_excludes(self) -> None:
        accepted = make_job(1)
        stale = make_job(2, ActivityLevel.STALE)
        low_score = make_job(3)
        excluded = make_job(4)
        matches = {
            accepted.fingerprint: MatchResult(score=94, decision="RECOMMEND"),
            stale.fingerprint: MatchResult(score=98, decision="RECOMMEND"),
            low_score.fingerprint: MatchResult(score=89, decision="RECOMMEND"),
            excluded.fingerprint: MatchResult(score=97, decision="RECOMMEND", risk_points=["命中排除词：外包驻场"]),
        }

        selected = select_candidates([accepted, stale, low_score, excluded], matches, threshold=90)

        self.assertEqual([item.job.fingerprint for item in selected], [accepted.fingerprint])

    def test_selection_caps_batch_and_removes_previously_contacted_jobs(self) -> None:
        jobs = [make_job(index) for index in range(7)]
        matches = {job.fingerprint: MatchResult(score=95, decision="RECOMMEND") for job in jobs}

        selected = select_candidates(
            jobs,
            matches,
            threshold=90,
            excluded_fingerprints={jobs[0].fingerprint},
            limit=5,
        )

        self.assertEqual(len(selected), 5)
        self.assertNotIn(jobs[0].fingerprint, {item.job.fingerprint for item in selected})


if __name__ == "__main__":
    unittest.main()
