import unittest
from pathlib import Path

from mobile_automation.activity import ActivityLevel
from mobile_automation.appium_adapter import (
    AppiumBossAdapter,
    AppiumConfig,
    build_job_from_fields,
    is_known_subpage_activity,
    parse_job_card_text,
    uiautomator_literal,
)
from mobile_automation.errors import AutomationError
from mobile_automation.models import Job


class AppiumCardParsingTests(unittest.TestCase):
    def test_parses_visible_boss_job_card_text(self) -> None:
        job = parse_job_card_text(
            "测试开发工程师\n20-30K·14薪\n上海·浦东新区\n5-10年 本科\n示例科技\nPython 自动化测试 接口测试\n招聘者 今日活跃"
        )

        self.assertIsNotNone(job)
        self.assertEqual(job.title, "测试开发工程师")
        self.assertEqual(job.company, "示例科技")
        self.assertEqual(job.salary, "20-30K·14薪")
        self.assertEqual(job.location, "上海·浦东新区")
        self.assertEqual(job.activity_level, ActivityLevel.TODAY)

    def test_rejects_card_without_activity_or_enough_matching_text(self) -> None:
        self.assertIsNone(parse_job_card_text("测试开发\n20-30K\n示例公司"))

    def test_unexpected_driver_error_is_converted_to_safe_automation_error(self) -> None:
        config = AppiumConfig(
            version=1,
            app_package="com.hpbr.bosszhipin",
            app_activity="",
            max_scrolls=0,
            job_card_locators=(),
            communicate_texts=("立即沟通",),
            continue_texts=("继续沟通",),
            blocker_texts=(),
        )
        adapter = AppiumBossAdapter(config)
        adapter._contact = lambda job: (_ for _ in ()).throw(RuntimeError("driver disconnected"))
        job = Job(
            title="测试开发工程师",
            company="示例科技",
            salary="20-30K",
            location="上海",
            activity_level=ActivityLevel.TODAY,
            activity_text="今日活跃",
            jd_text="测试开发工程师 示例科技 20-30K 上海 招聘者今日活跃 Python 自动化测试",
        )

        with self.assertRaises(AutomationError) as raised:
            adapter.contact(job)

        self.assertEqual(raised.exception.code, "APPIUM_OPERATION_FAILED")

    def test_vendor_locked_device_capabilities_preserve_app_data(self) -> None:
        config = AppiumConfig(
            version=1,
            app_package="com.hpbr.bosszhipin",
            app_activity=".module.launcher.WelcomeActivity",
            max_scrolls=0,
            job_card_locators=(),
            communicate_texts=(),
            continue_texts=(),
            blocker_texts=(),
        )

        capabilities = AppiumBossAdapter(config)._capabilities()

        self.assertTrue(capabilities["noReset"])
        self.assertTrue(capabilities["forceAppLaunch"])
        self.assertFalse(capabilities["shouldTerminateApp"])
        self.assertTrue(capabilities["ignoreHiddenApiPolicyError"])
        self.assertFalse(capabilities["autoGrantPermissions"])

    def test_real_boss_selectors_and_detail_fields_build_matchable_job(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        job = build_job_from_fields(
            title="测试开发-上海",
            company="澳发软件",
            salary="1.1-1.5万元",
            location="上海·五角场",
            activity_text="3分钟前回复",
            description=(
                "职位描述：负责接口自动化、性能测试和 Python 测试平台建设，"
                "参与需求评审、测试计划、缺陷跟踪、持续集成和质量效率改进。"
            ),
        )

        self.assertEqual(config.element_ids["jobCard"], "com.hpbr.bosszhipin:id/boss_job_card_view")
        self.assertEqual(job.activity_level, ActivityLevel.TODAY)
        self.assertEqual(job.salary, "1.1-1.5万元")
        self.assertIn("接口自动化", job.jd_text)

    def test_only_known_detail_and_chat_activities_allow_single_back_navigation(self) -> None:
        self.assertTrue(is_known_subpage_activity(".geekjd.activity.BossJobPagerActivity"))
        self.assertTrue(is_known_subpage_activity(".chat.single.activity.ChatRoomActivity"))
        self.assertFalse(is_known_subpage_activity(".module.login.activity.LoginActivity"))

    def test_uiautomator_literal_escapes_dynamic_job_titles(self) -> None:
        self.assertEqual(uiautomator_literal('测试 "AI" \\ 开发'), '测试 \\"AI\\" \\\\ 开发')

    def test_streaming_contact_clicks_current_detail_without_relocating_job(self) -> None:
        config = AppiumConfig(
            version=1,
            app_package="com.hpbr.bosszhipin",
            app_activity="",
            max_scrolls=0,
            job_card_locators=(),
            communicate_texts=("立即沟通",),
            continue_texts=("继续沟通",),
            blocker_texts=(),
        )
        adapter = AppiumBossAdapter(config)
        adapter._current_job = Job(
            title="测试开发工程师",
            company="示例科技",
            salary="20-30K",
            location="上海",
            activity_level=ActivityLevel.TODAY,
            activity_text="今日活跃",
            jd_text="负责接口自动化、UI自动化、性能测试与质量平台建设。" * 2,
        )
        clicked: list[bool] = []

        class Button:
            def click(self) -> None:
                clicked.append(True)

        adapter._require_driver = lambda: None
        adapter._assert_no_blocker = lambda: None
        adapter._open_job_list = lambda: self.fail("当前详情页沟通不应返回岗位列表")
        adapter._find_job_title = lambda _job: self.fail("当前详情页沟通不应重新查找岗位")
        adapter._find_unique_text_element = (
            lambda texts: None if texts == config.continue_texts else Button()
        )

        self.assertTrue(adapter.contact_current())
        self.assertEqual(clicked, [True])

    def test_streaming_contact_does_not_count_already_contacted_job(self) -> None:
        config = AppiumConfig(
            version=1,
            app_package="com.hpbr.bosszhipin",
            app_activity="",
            max_scrolls=0,
            job_card_locators=(),
            communicate_texts=("立即沟通",),
            continue_texts=("继续沟通",),
            blocker_texts=(),
        )
        adapter = AppiumBossAdapter(config)
        adapter._current_job = Job(
            title="测试开发工程师",
            company="示例科技",
            salary="20-30K",
            location="上海",
            activity_level=ActivityLevel.TODAY,
            activity_text="今日活跃",
            jd_text="负责接口自动化、UI自动化、性能测试与质量平台建设。" * 2,
        )
        adapter._require_driver = lambda: None
        adapter._assert_no_blocker = lambda: None
        adapter._find_unique_text_element = (
            lambda texts: object() if texts == config.continue_texts else None
        )

        self.assertFalse(adapter.contact_current())

    def test_next_job_keeps_detail_open_and_does_not_revisit_seen_card(self) -> None:
        config = AppiumConfig(
            version=1,
            app_package="com.hpbr.bosszhipin",
            app_activity="",
            max_scrolls=0,
            job_card_locators=(),
            communicate_texts=("立即沟通",),
            continue_texts=("继续沟通",),
            blocker_texts=(),
        )
        adapter = AppiumBossAdapter(config)
        adapter.driver = object()
        adapter._by = object()
        job = Job(
            title="测试开发工程师",
            company="示例科技",
            salary="20-30K",
            location="上海",
            activity_level=ActivityLevel.TODAY,
            activity_text="今日活跃",
            jd_text="负责接口自动化、UI自动化、性能测试与质量平台建设。" * 2,
        )
        opened: list[bool] = []
        open_list_calls: list[bool] = []
        adapter._open_job_list = lambda: open_list_calls.append(True)
        adapter._assert_no_blocker = lambda: None
        adapter._find_job_cards = lambda: [object()]
        adapter._read_card_summary = lambda _element: job
        adapter._open_and_read_detail = lambda _job, *, keep_open=False: opened.append(keep_open) or job
        adapter._scroll_down = lambda: False

        self.assertEqual(adapter.next_job(), job)
        self.assertEqual(adapter.next_job(), None)
        self.assertEqual(opened, [True])
        self.assertEqual(len(open_list_calls), 2)


if __name__ == "__main__":
    unittest.main()
