import unittest

from mobile_automation.activity import ActivityLevel
from mobile_automation.cli import (
    build_parser,
    doctor_result,
    format_device_status,
    format_failure,
    format_progress_event,
)
from mobile_automation.models import Job
from mobile_automation.workflow import ProgressEvent


class CliContractTests(unittest.TestCase):
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
