import unittest

from mobile_automation.activity import ActivityLevel
from mobile_automation.models import Job, MatchResult
from mobile_automation.policy import JobPolicy, parse_salary_lower_k


def make_job(
    *,
    salary: str = "15-20K",
    activity: ActivityLevel = ActivityLevel.TODAY,
    title: str = "测试开发工程师",
    description: str = "负责互联网平台接口自动化、UI 自动化、性能测试和质量平台建设。",
) -> Job:
    return Job(
        title=title,
        company="示例科技",
        salary=salary,
        location="上海",
        activity_level=activity,
        activity_text="今日活跃",
        jd_text=f"{title}\n{description}" * 2,
    )


class SalaryPolicyTests(unittest.TestCase):
    def test_parses_monthly_salary_lower_bound_in_k(self) -> None:
        cases = {
            "15-20K": 15,
            "15-20K·14薪": 15,
            "15K以上": 15,
            "1.5-2万元": 15,
            "15000-20000元/月": 15,
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(parse_salary_lower_k(value), expected)

    def test_unknown_or_non_monthly_salary_is_not_guessed(self) -> None:
        for value in ("面议", "300-500元/天", ""):
            with self.subTest(value=value):
                self.assertIsNone(parse_salary_lower_k(value))


class JobPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = JobPolicy(minimum_salary_k=15, match_threshold=90)

    def test_accepts_salary_when_lower_bound_meets_fifteen_k(self) -> None:
        self.assertEqual(self.policy.precheck(make_job(salary="15-20K")), [])

    def test_rejects_salary_when_lower_bound_is_below_fifteen_k(self) -> None:
        self.assertIn("SALARY_BELOW_MINIMUM", self.policy.precheck(make_job(salary="14-25K")))

    def test_rejects_stale_or_unknown_recruiter_activity(self) -> None:
        self.assertIn("RECRUITER_INACTIVE", self.policy.precheck(make_job(activity=ActivityLevel.STALE)))
        self.assertIn("RECRUITER_INACTIVE", self.policy.precheck(make_job(activity=ActivityLevel.UNKNOWN)))

    def test_rejects_hardware_iot_and_automotive_domains_before_scoring(self) -> None:
        descriptions = (
            "负责 MCU、PCB 和硬件测试，使用示波器定位问题",
            "负责物联网网关、传感器和 Zigbee 协议测试",
            "负责车载测试、CAN 总线、ECU 和智能座舱质量保障",
        )
        for description in descriptions:
            with self.subTest(description=description):
                self.assertIn("EXCLUDED_DOMAIN", self.policy.precheck(make_job(description=description)))

    def test_does_not_misclassify_software_voice_robot_or_mobile_app_testing(self) -> None:
        job = make_job(description="负责 RAG 语音机器人软件平台及 Android、iOS App 自动化测试")
        self.assertEqual(self.policy.precheck(job), [])

    def test_requires_ninety_score_and_recommend_decision_without_exclusion(self) -> None:
        self.assertFalse(self.policy.accepts_match(MatchResult(score=89, decision="RECOMMEND")))
        self.assertFalse(self.policy.accepts_match(MatchResult(score=95, decision="PASS")))
        self.assertFalse(
            self.policy.accepts_match(
                MatchResult(score=95, decision="RECOMMEND", risk_points=["命中排除词：外包驻场"])
            )
        )
        self.assertTrue(self.policy.accepts_match(MatchResult(score=90, decision="RECOMMEND")))


if __name__ == "__main__":
    unittest.main()
