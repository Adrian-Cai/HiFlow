import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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
    def test_disables_toast_listener_that_breaks_page_source_on_vendor_android(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        adapter = AppiumBossAdapter(config)
        applied: list[dict[str, object]] = []

        class Driver:
            def update_settings(self, settings: dict[str, object]) -> None:
                applied.append(settings)

        adapter.driver = Driver()

        adapter._configure_driver_settings()

        self.assertEqual(applied, [{"enableNotificationListener": False}])

    def test_streaming_wraps_unexpected_page_source_failure_as_chinese_error(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        adapter = AppiumBossAdapter(config)
        adapter.driver = object()
        adapter._by = object()
        adapter._open_job_list = lambda: (_ for _ in ()).throw(
            RuntimeError("Cannot set AccessibilityNodeInfo's field 'mSealed' to 'true'")
        )

        with self.assertRaises(AutomationError) as raised:
            adapter.next_job()

        self.assertEqual(raised.exception.code, "APPIUM_PAGE_READ_FAILED")
        self.assertIn("读取岗位列表", str(raised.exception))

    def test_opening_an_already_visible_job_list_does_not_click_tab_or_refresh(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        adapter = AppiumBossAdapter(config)
        tab_clicks: list[bool] = []

        class Element:
            id = "element"

            def __init__(self, *, tab: bool = False) -> None:
                self.tab = tab

            def is_displayed(self) -> bool:
                return True

            def is_enabled(self) -> bool:
                return True

            def click(self) -> None:
                if self.tab:
                    tab_clicks.append(True)

        class Driver:
            page_source = ""

            def find_elements(self, _by: str, value: str) -> list[Element]:
                if value == config.element_ids["jobList"]:
                    return [Element()]
                if value == config.element_ids["jobTab"]:
                    return [Element(tab=True)]
                return []

        adapter.driver = Driver()
        adapter._by = SimpleNamespace(ID="id")
        adapter._assert_no_blocker = lambda: None

        adapter._open_job_list()

        self.assertEqual(tab_clicks, [])

    def test_exhausted_list_refresh_clicks_job_tab_exactly_once(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        statuses: list[tuple[str, str]] = []
        adapter = AppiumBossAdapter(config, status_reporter=lambda category, message: statuses.append((category, message)))
        tab_clicks: list[bool] = []

        class Tab:
            def click(self) -> None:
                tab_clicks.append(True)

        adapter.driver = object()
        adapter._by = object()
        adapter._job_list_visible = lambda: True
        adapter._assert_no_blocker = lambda: None
        adapter._wait_unique_id = lambda _resource_id, *, timeout: Tab()

        with patch("mobile_automation.appium_adapter.time.sleep"):
            adapter._refresh_job_list()

        self.assertEqual(tab_clicks, [True])
        self.assertEqual(statuses, [("刷新", "当前列表已检查完，正在刷新一次查找新岗位")])

    def test_streaming_returns_to_same_list_and_opens_pending_next_job(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        adapter = AppiumBossAdapter(config)
        first = build_job_from_fields(
            title="测试开发工程师一",
            company="示例科技一",
            salary="20-30K",
            location="上海",
            activity_text="今日活跃",
            description="负责接口自动化、UI自动化、性能测试与质量平台建设。" * 2,
        )
        second = build_job_from_fields(
            title="测试开发工程师二",
            company="示例科技二",
            salary="20-30K",
            location="上海",
            activity_text="今日活跃",
            description="负责接口自动化、UI自动化、性能测试与质量平台建设。" * 2,
        )
        returned: list[bool] = []
        opened: list[str] = []
        adapter.driver = object()
        adapter._by = object()
        adapter._stream_started = True
        adapter._current_job = first
        adapter._stream_pending = [second]
        adapter._return_to_job_list = lambda: returned.append(True)
        adapter._open_job_list = lambda: self.fail("返回详情页后不应重新点击岗位页签")
        adapter._open_and_read_detail = (
            lambda job, *, keep_open=False: opened.append(job.title) or job
        )

        result = adapter.next_job()

        self.assertEqual(result, second)
        self.assertEqual(returned, [True])
        self.assertEqual(opened, [second.title])

    def test_return_to_job_list_uses_back_once_and_preserves_list_page(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        statuses: list[tuple[str, str]] = []
        adapter = AppiumBossAdapter(config, status_reporter=lambda category, message: statuses.append((category, message)))

        class Element:
            def is_displayed(self) -> bool:
                return True

            def is_enabled(self) -> bool:
                return True

        class Driver:
            page_source = ""

            def __init__(self) -> None:
                self.on_list = False
                self.back_calls = 0

            @property
            def current_activity(self) -> str:
                if self.on_list:
                    return ".main.activity.MainActivity"
                return ".geekjd.activity.BossJobPagerActivity"

            def find_elements(self, _by: str, value: str) -> list[Element]:
                if value == config.element_ids["jobList"] and self.on_list:
                    return [Element()]
                if value == config.element_ids["detailDescription"] and not self.on_list:
                    return [Element()]
                return []

            def back(self) -> None:
                self.back_calls += 1
                self.on_list = True

        driver = Driver()
        adapter.driver = driver
        adapter._by = SimpleNamespace(ID="id")
        adapter._assert_no_blocker = lambda: None

        with patch("mobile_automation.appium_adapter.time.sleep"):
            adapter._return_to_job_list()

        self.assertTrue(driver.on_list)
        self.assertEqual(driver.back_calls, 1)
        self.assertEqual(statuses, [("列表", "正在返回原岗位列表")])

    def test_list_scrolling_uses_bounded_adb_swipe_without_appium_scroll_wait(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        statuses: list[tuple[str, str]] = []
        adapter = AppiumBossAdapter(config, status_reporter=lambda category, message: statuses.append((category, message)))

        class Driver:
            def get_window_size(self) -> dict[str, int]:
                return {"width": 1080, "height": 2400}

        adapter.driver = Driver()

        with patch("mobile_automation.appium_adapter.subprocess.run") as run_command:
            self.assertTrue(adapter._scroll_down())

        command = run_command.call_args.args[0]
        self.assertEqual(command[:4], ["adb", "shell", "input", "swipe"])
        self.assertGreater(int(command[5]), int(command[7]))
        self.assertEqual(run_command.call_args.kwargs["timeout"], 5)
        self.assertEqual(statuses, [("列表", "正在向下滚动查找新岗位")])

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
        statuses: list[tuple[str, str]] = []
        adapter = AppiumBossAdapter(config, status_reporter=lambda category, message: statuses.append((category, message)))
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

    def test_device_capabilities_preserve_the_running_filtered_job_list(self) -> None:
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
        self.assertFalse(capabilities["forceAppLaunch"])
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
        statuses: list[tuple[str, str]] = []
        adapter = AppiumBossAdapter(
            config,
            status_reporter=lambda category, message: statuses.append((category, message)),
        )
        adapter.driver = SimpleNamespace(current_activity=".geekjd.activity.BossJobPagerActivity")
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
        contact_confirmed = False

        class Button:
            def click(self) -> None:
                nonlocal contact_confirmed
                clicked.append(True)
                contact_confirmed = True

        adapter._require_driver = lambda: None
        adapter._assert_no_blocker = lambda: None
        adapter._open_job_list = lambda: self.fail("当前详情页沟通不应返回岗位列表")
        adapter._find_job_title = lambda _job: self.fail("当前详情页沟通不应重新查找岗位")
        adapter._find_unique_text_element = lambda texts: (
            object() if texts == config.continue_texts and contact_confirmed
            else None if texts == config.continue_texts
            else Button()
        )

        self.assertTrue(adapter.contact_current())
        self.assertEqual(clicked, [True])
        self.assertEqual(
            statuses,
            [
                ("沟通", "已点击打招呼，正在等待平台确认"),
                ("沟通", "平台已确认沟通成功"),
            ],
        )

    def test_streaming_contact_is_not_successful_until_platform_state_is_confirmed(self) -> None:
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
        adapter._find_unique_text_element = (
            lambda texts: None if texts == config.continue_texts else Button()
        )
        adapter._wait_for_contact_confirmation = lambda timeout=10: False

        with self.assertRaises(AutomationError) as raised:
            adapter.contact_current()

        self.assertEqual(raised.exception.code, "CONTACT_NOT_CONFIRMED")
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
        exhausted_refreshes: list[bool] = []
        adapter._open_job_list = lambda: open_list_calls.append(True)
        adapter._return_to_job_list = lambda: open_list_calls.append(True)
        adapter._refresh_job_list = lambda: exhausted_refreshes.append(True)
        adapter._assert_no_blocker = lambda: None
        adapter._find_job_cards = lambda: [object()]
        adapter._read_card_summary = lambda _element: job
        adapter._open_and_read_detail = lambda _job, *, keep_open=False: opened.append(keep_open) or job
        adapter._scroll_down = lambda: False

        self.assertEqual(adapter.next_job(), job)
        self.assertEqual(adapter.next_job(), None)
        self.assertEqual(opened, [True])
        self.assertEqual(len(open_list_calls), 2)
        self.assertEqual(exhausted_refreshes, [True])


if __name__ == "__main__":
    unittest.main()
