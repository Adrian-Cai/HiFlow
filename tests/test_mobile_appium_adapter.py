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
from mobile_automation.errors import AutomationError, UserActionRequired
from mobile_automation.models import Job


class AppiumCardParsingTests(unittest.TestCase):
    def test_locator_results_do_not_query_dynamic_element_attributes(self) -> None:
        class Element:
            def is_displayed(self) -> bool:
                raise AssertionError("dynamic list reads must not issue a separate displayed request")

            def is_enabled(self) -> bool:
                raise AssertionError("dynamic list reads must not issue a separate enabled request")

        element = Element()

        self.assertEqual(AppiumBossAdapter._visible([element]), [element])

    def test_blocker_detection_uses_uiautomator_queries_without_reading_page_source(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        adapter = AppiumBossAdapter(config)
        queries: list[tuple[str, str]] = []

        class Driver:
            @property
            def page_source(self) -> str:
                raise AssertionError("拦截检查不应读取整页 XML")

            def find_elements(self, by: str, value: str) -> list[object]:
                queries.append((by, value))
                return []

        adapter.driver = Driver()
        adapter._by = SimpleNamespace(ANDROID_UIAUTOMATOR="uiautomator")

        adapter._assert_no_blocker()

        self.assertEqual(len(queries), 1)
        self.assertTrue(all(by == "uiautomator" for by, _value in queries))
        self.assertIn("textMatches", queries[0][1])

    def test_blocker_detection_is_throttled_between_page_transition_polls(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        adapter = AppiumBossAdapter(config)
        queries: list[str] = []

        class Driver:
            def find_elements(self, _by: str, value: str) -> list[object]:
                queries.append(value)
                return []

        adapter.driver = Driver()
        adapter._by = SimpleNamespace(ANDROID_UIAUTOMATOR="uiautomator")

        with patch("mobile_automation.appium_adapter.time.monotonic", side_effect=[10.0, 10.5, 12.1]):
            adapter._assert_no_blocker()
            adapter._assert_no_blocker()
            adapter._assert_no_blocker()

        self.assertEqual(len(queries), 2)

    def test_blocker_detection_still_pauses_when_security_text_is_visible(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        adapter = AppiumBossAdapter(config)

        class Element:
            text = "安全验证"

            def is_displayed(self) -> bool:
                return True

            def is_enabled(self) -> bool:
                return True

            def get_attribute(self, _name: str) -> str:
                return ""

        class Driver:
            def find_elements(self, _by: str, value: str) -> list[Element]:
                return [Element()] if "textMatches" in value else []

        adapter.driver = Driver()
        adapter._by = SimpleNamespace(ANDROID_UIAUTOMATOR="uiautomator")

        with self.assertRaises(UserActionRequired) as raised:
            adapter._assert_no_blocker()

        self.assertEqual(raised.exception.code, "SECURITY_VERIFICATION")
    def test_disables_toast_listener_that_breaks_page_source_on_vendor_android(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        adapter = AppiumBossAdapter(config)
        applied: list[dict[str, object]] = []

        class Driver:
            def update_settings(self, settings: dict[str, object]) -> None:
                applied.append(settings)

        adapter.driver = Driver()

        adapter._configure_driver_settings()

        self.assertEqual(
            applied,
            [
                {
                    "elementResponseAttributes": "text",
                    "enableNotificationListener": False,
                    "shouldUseCompactResponses": False,
                    "trackScrollEvents": False,
                    "waitForIdleTimeout": 0,
                    "waitForSelectorTimeout": 500,
                }
            ],
        )

    def test_bulk_id_text_read_uses_find_response_without_per_element_text_requests(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        adapter = AppiumBossAdapter(config)

        class Executor:
            def execute(self, command: str, params: dict[str, object]) -> dict[str, object]:
                self.command = command
                self.params = params
                return {"value": [{"text": "岗位一"}, {"text": "岗位二"}]}

        executor = Executor()
        adapter.driver = SimpleNamespace(command_executor=executor, session_id="session-1")
        adapter._by = SimpleNamespace(ID="id")

        texts = adapter._texts_by_id(config.element_ids["cardTitle"])

        self.assertEqual(texts, ["岗位一", "岗位二"])
        self.assertEqual(executor.command, "findElements")

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
            current_activity = ".module.main.activity.MainActivity"

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

    def test_detail_related_jobs_list_is_not_mistaken_for_the_main_job_list(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        adapter = AppiumBossAdapter(config)

        class Element:
            def is_displayed(self) -> bool:
                return True

            def is_enabled(self) -> bool:
                return True

        class Driver:
            current_activity = ".geekjd.activity.BossJobPagerActivity"

            def find_elements(self, _by: str, value: str) -> list[Element]:
                if value == config.element_ids["jobList"]:
                    return [Element()]
                return []

        adapter.driver = Driver()
        adapter._by = SimpleNamespace(ID="id")

        self.assertFalse(adapter._job_list_visible())

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

    def test_unknown_detail_activity_is_allowed_only_for_read_only_verification(self) -> None:
        fields = {
            "title": "测试平台工程师",
            "company": "质量云",
            "salary": "25-35K",
            "location": "上海·徐汇",
            "activity_text": "",
            "description": "负责自动化测试平台建设、测试执行、质量分析和持续改进。" * 2,
        }

        with self.assertRaises(AutomationError) as raised:
            build_job_from_fields(**fields)
        self.assertEqual(raised.exception.code, "JOB_ACTIVITY_UNKNOWN")

        job = build_job_from_fields(**fields, allow_unknown_activity=True)
        self.assertEqual(job.activity_level, ActivityLevel.UNKNOWN)

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
        card = object()
        adapter._return_to_job_list = lambda: returned.append(True)
        adapter._open_job_list = lambda: self.fail("返回详情页后不应重新点击岗位页签")
        adapter._assert_no_blocker = lambda: None
        adapter._find_job_cards = lambda: [card]
        adapter._read_card_summary = lambda element: second if element is card else None
        adapter._open_bound_card_and_read_detail = (
            lambda element, job, *, keep_open=False: opened.append(job.title) or job
        )

        result = adapter.next_job()

        self.assertEqual(result, second)
        self.assertEqual(returned, [True])
        self.assertEqual(opened, [second.title])

    def test_streaming_opens_the_bound_visible_card_without_relocating_by_title(self) -> None:
        config = AppiumConfig(
            version=1,
            app_package="com.hpbr.bosszhipin",
            app_activity="",
            max_scrolls=0,
            job_card_locators=(),
            communicate_texts=(),
            continue_texts=(),
            blocker_texts=(),
        )
        adapter = AppiumBossAdapter(config, allow_contact=True)
        summary = Job(
            title="游戏测试开发工程师",
            company="几近非凡",
            salary="15-30K",
            location="上海 浦东",
            activity_level=ActivityLevel.TODAY,
            activity_text="今日活跃",
            jd_text="游戏测试开发工程师 几近非凡 15-30K 上海 浦东 今日活跃",
        )
        card = object()
        opened: list[object] = []
        adapter.driver = object()
        adapter._by = object()
        adapter._open_job_list = lambda: None
        adapter._assert_no_blocker = lambda: None
        adapter._find_job_cards = lambda: [card]
        adapter._read_card_summary = lambda element: summary if element is card else None
        adapter._read_visible_card_summaries = lambda: self.fail("顺序投递不应批量读取后按标题重定位")
        adapter._find_job_title = lambda _job: self.fail("顺序投递不应按标题重新查找岗位")
        adapter._open_bound_card_and_read_detail = (
            lambda element, job, *, keep_open=False: opened.append(element) or job
        )

        result = adapter.next_job()

        self.assertEqual(result, summary)
        self.assertEqual(opened, [card])

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
                    return ".module.main.activity.MainActivity"
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

    def test_list_scrolling_uses_native_gesture_bound_to_job_list(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        statuses: list[tuple[str, str]] = []
        adapter = AppiumBossAdapter(config, status_reporter=lambda category, message: statuses.append((category, message)))

        class Element:
            id = "job-list-element-id"

            def is_displayed(self) -> bool:
                return True

            def is_enabled(self) -> bool:
                return True

        class Driver:
            current_activity = ".module.main.activity.MainActivity"

            def __init__(self) -> None:
                self.scripts: list[tuple[str, dict[str, object]]] = []

            def find_elements(self, _by: str, value: str) -> list[Element]:
                return [Element()] if value == config.element_ids["jobList"] else []

            def execute_script(self, script: str, arguments: dict[str, object]) -> bool:
                self.scripts.append((script, arguments))
                return False

        driver = Driver()
        adapter.driver = driver
        adapter._by = SimpleNamespace(ID="id")

        self.assertFalse(adapter._scroll_down())

        self.assertEqual(
            driver.scripts,
            [
                (
                    "mobile: scrollGesture",
                    {
                        "elementId": "job-list-element-id",
                        "direction": "down",
                        "percent": 0.7,
                    },
                )
            ],
        )
        self.assertEqual(adapter.verification_metrics().scrolls, 1)
        self.assertEqual(statuses, [("列表", "正在向下滚动查找新岗位")])

    def test_verification_preconditions_require_current_filtered_main_job_list(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        adapter = AppiumBossAdapter(config)

        class Element:
            def __init__(self, text: str = "") -> None:
                self.text = text

            def is_displayed(self) -> bool:
                return True

            def is_enabled(self) -> bool:
                return True

        class Driver:
            current_activity = ".module.main.activity.MainActivity"

            def find_elements(self, _by: str, value: str) -> list[Element]:
                if value == config.element_ids["jobList"]:
                    return [Element()]
                if value == config.element_ids["filterLabel"]:
                    return [Element("上海"), Element("薪资"), Element("筛选·1")]
                return []

        adapter.driver = Driver()
        adapter._by = SimpleNamespace(ID="id")
        adapter._assert_no_blocker = lambda: None

        self.assertEqual(
            adapter.verify_preconditions(),
            {"city": "上海", "filterText": "筛选·1"},
        )

    def test_verification_preconditions_do_not_navigate_to_job_list(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        adapter = AppiumBossAdapter(config)
        adapter.driver = SimpleNamespace(current_activity=".geekjd.activity.BossJobPagerActivity")
        adapter._by = SimpleNamespace(ID="id")
        adapter._open_job_list = lambda: self.fail("验证前置检查不得自动导航")
        adapter._job_list_visible = lambda: False

        with self.assertRaises(AutomationError) as raised:
            adapter.verify_preconditions()

        self.assertEqual(raised.exception.code, "VERIFICATION_JOB_LIST_REQUIRED")

    def test_read_only_adapter_rejects_every_contact_entrypoint(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        adapter = AppiumBossAdapter(config)
        job = Job(
            title="测试开发工程师",
            company="示例科技",
            salary="20-30K",
            location="上海",
            activity_level=ActivityLevel.TODAY,
            activity_text="今日活跃",
            jd_text="负责接口自动化、UI 自动化、性能测试与质量平台建设。" * 2,
        )

        with self.assertRaises(AutomationError) as contact_error:
            adapter.contact(job)
        with self.assertRaises(AutomationError) as current_error:
            adapter.contact_current()

        self.assertEqual(contact_error.exception.code, "CONTACT_DISABLED")
        self.assertEqual(current_error.exception.code, "CONTACT_DISABLED")
        self.assertEqual(adapter.verification_metrics().contact_attempts, 2)

    def test_finish_current_job_returns_to_original_list_before_counting(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        adapter = AppiumBossAdapter(config)
        adapter.driver = object()
        adapter._by = object()
        adapter._current_job = object()  # type: ignore[assignment]
        returned: list[bool] = []
        adapter._return_to_job_list = lambda: returned.append(True)

        adapter.finish_current_job()

        self.assertEqual(returned, [True])
        self.assertIsNone(adapter._current_job)

    def test_finish_current_job_wraps_driver_timeout_as_page_read_failure(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        adapter = AppiumBossAdapter(config)
        adapter.driver = object()
        adapter._by = object()
        adapter._current_job = object()  # type: ignore[assignment]
        adapter._return_to_job_list = lambda: (_ for _ in ()).throw(
            RuntimeError("timeout of 15000ms exceeded")
        )

        with self.assertRaises(AutomationError) as raised:
            adapter.finish_current_job()

        self.assertEqual(raised.exception.code, "APPIUM_PAGE_READ_FAILED")

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

    def test_streaming_reads_visible_cards_with_root_queries_instead_of_nested_card_queries(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        adapter = AppiumBossAdapter(config)
        calls: list[str] = []

        class Element:
            def __init__(self, text: str) -> None:
                self.text = text

            def find_elements(self, _by: str, _value: str) -> list[object]:
                raise AssertionError("列表卡片不应再执行容易卡死的嵌套查询")

        values = {
            config.element_ids["cardTitle"]: ["测试开发工程师", "测试平台工程师"],
            config.element_ids["cardCompany"]: ["示例科技", "质量云"],
            config.element_ids["cardSalary"]: ["20-30K", "25-35K"],
            config.element_ids["cardLocation"]: ["上海·浦东", "上海·徐汇"],
            config.element_ids["cardActivity"]: ["今日活跃", "3日内活跃"],
        }

        class Driver:
            def find_elements(self, _by: str, value: str) -> list[Element]:
                calls.append(value)
                return [Element(text) for text in values[value]]

        adapter.driver = Driver()
        adapter._by = SimpleNamespace(ID="id")

        jobs = adapter._read_visible_card_summaries()

        self.assertEqual([job.title for job in jobs], ["测试开发工程师", "测试平台工程师"])
        self.assertEqual(len(calls), 5)

    def test_read_only_verification_keeps_cards_without_list_activity_for_detail_validation(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        adapter = AppiumBossAdapter(config, allow_contact=False)

        class Element:
            def __init__(self, text: str) -> None:
                self.text = text

        values = {
            config.element_ids["cardTitle"]: ["测试开发工程师", "测试平台工程师"],
            config.element_ids["cardCompany"]: ["示例科技", "质量云"],
            config.element_ids["cardSalary"]: ["20-30K", "25-35K"],
            config.element_ids["cardLocation"]: ["上海·浦东", "上海·徐汇"],
            config.element_ids["cardActivity"]: ["今日活跃"],
        }

        class Driver:
            def find_elements(self, _by: str, value: str) -> list[Element]:
                return [Element(text) for text in values[value]]

        adapter.driver = Driver()
        adapter._by = SimpleNamespace(ID="id")

        jobs = adapter._read_visible_card_summaries()

        self.assertEqual([job.title for job in jobs], ["测试开发工程师", "测试平台工程师"])
        self.assertEqual(jobs[1].activity_level, ActivityLevel.UNKNOWN)

    def test_read_only_verification_opens_unknown_list_activity_for_detail_validation(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        adapter = AppiumBossAdapter(config, allow_contact=False)
        summary = Job(
            title="测试平台工程师",
            company="质量云",
            salary="25-35K",
            location="上海·徐汇",
            activity_level=ActivityLevel.UNKNOWN,
            activity_text="",
            jd_text="测试平台工程师 质量云 25-35K 上海·徐汇",
        )
        opened: list[Job] = []
        adapter.driver = object()
        adapter._by = object()
        card = object()
        adapter._open_job_list = lambda: None
        adapter._assert_no_blocker = lambda: None
        adapter._find_job_cards = lambda: [card]
        adapter._read_card_summary = lambda element: summary if element is card else None
        adapter._open_bound_card_and_read_detail = (
            lambda element, job, *, keep_open=False: opened.append(job) or job
        )

        self.assertEqual(adapter.next_job(), summary)
        self.assertEqual(opened, [summary])

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
        adapter = AppiumBossAdapter(
            config,
            allow_contact=True,
            status_reporter=lambda category, message: statuses.append((category, message)),
        )
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
        self.assertEqual(capabilities["uiautomator2ServerReadTimeout"], 60000)

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

    def test_detail_reader_does_not_expand_more_when_visible_text_is_already_sufficient(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        adapter = AppiumBossAdapter(config)
        summary = Job(
            title="测试工具开发工程师",
            company="示例科技",
            salary="20-30K",
            location="上海",
            activity_level=ActivityLevel.TODAY,
            activity_text="今日活跃",
            jd_text="测试工具开发工程师 示例科技 20-30K 上海 今日活跃",
        )
        clicked: list[bool] = []
        events: list[str] = []

        class Target:
            def click(self) -> None:
                clicked.append(True)
                events.append("click")

        class Description:
            text = "负责 Python 自动化测试工具、接口测试平台、日志分析和持续集成建设。" * 2 + " 查看更多"

            def click(self) -> None:
                raise AssertionError("可见详情已足够时不应点击展开控件")

        detail_values = {
            "detailTitle": summary.title,
            "detailSalary": summary.salary,
            "detailLocation": summary.location,
            "detailActivity": summary.activity_text,
            "detailBossTitle": summary.company + " · 招聘经理",
        }
        adapter.driver = object()
        adapter._find_job_title = lambda _summary: Target()
        adapter._wait_for_job_detail_description = lambda *, timeout: events.append("read") or Description()
        adapter._assert_no_blocker = lambda: None
        adapter._text_by_id = lambda key: detail_values[key]

        with patch("mobile_automation.appium_adapter.time.sleep", side_effect=lambda _seconds: events.append("settle")):
            job = adapter._open_and_read_detail(summary, keep_open=True)

        self.assertEqual(clicked, [True])
        self.assertEqual(events[:3], ["click", "settle", "read"])
        self.assertIn("Python 自动化测试工具", job.jd_text)

    def test_detail_wait_reads_description_before_running_blocker_query(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        adapter = AppiumBossAdapter(config)
        events: list[str] = []

        class Description:
            pass

        description = Description()

        class Driver:
            current_activity = ".geekjd.activity.BossJobPagerActivity"

            def find_elements(self, _by: str, value: str) -> list[Description]:
                events.append(value)
                return [description]

        adapter.driver = Driver()
        adapter._by = SimpleNamespace(ID="id")
        adapter._assert_no_blocker = lambda: events.append("blocker")

        result = adapter._wait_for_job_detail_description(timeout=1)

        self.assertIs(result, description)
        self.assertEqual(events, [config.element_ids["detailDescription"]])

    def test_only_known_boss_subpages_allow_single_back_navigation(self) -> None:
        self.assertTrue(is_known_subpage_activity(".geekjd.activity.BossJobPagerActivity"))
        self.assertTrue(is_known_subpage_activity(".chat.single.activity.ChatRoomActivity"))
        self.assertTrue(is_known_subpage_activity(".module.webview.WebViewActivity"))
        self.assertFalse(is_known_subpage_activity(".module.login.activity.LoginActivity"))

    def test_uiautomator_literal_escapes_dynamic_job_titles(self) -> None:
        self.assertEqual(uiautomator_literal('测试 "AI" \\ 开发'), '测试 \\"AI\\" \\\\ 开发')

    def test_duplicate_visible_titles_are_disambiguated_by_their_job_card_fields(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        adapter = AppiumBossAdapter(config)

        class Field:
            def __init__(self, text: str, element_id: str) -> None:
                self.text = text
                self.id = element_id

            def is_displayed(self) -> bool:
                return True

        class Card:
            def __init__(self, prefix: str, company: str, location: str = "上海") -> None:
                self.id = f"card-{prefix}"
                self.fields = {
                    config.element_ids["cardTitle"]: Field("测试开发工程师", f"title-{prefix}"),
                    config.element_ids["cardCompany"]: Field(company, f"company-{prefix}"),
                    config.element_ids["cardSalary"]: Field("20-30K", f"salary-{prefix}"),
                    config.element_ids["cardLocation"]: Field(location, f"location-{prefix}"),
                    config.element_ids["cardActivity"]: Field("今日活跃", f"activity-{prefix}"),
                }

            def is_displayed(self) -> bool:
                return True

            def find_elements(self, _by: str, value: str) -> list[Field]:
                field = self.fields.get(value)
                return [field] if field is not None else []

        wrong_card = Card("wrong", "其他科技")
        target_card = Card("target", "目标科技", "上海  浦东")

        class Driver:
            def find_elements(self, by: str, value: str) -> list[object]:
                if by == "uiautomator":
                    return [
                        wrong_card.fields[config.element_ids["cardTitle"]],
                        target_card.fields[config.element_ids["cardTitle"]],
                    ]
                if by == "id" and value == config.element_ids["jobCard"]:
                    return [wrong_card, target_card]
                return []

        adapter.driver = Driver()
        adapter._by = SimpleNamespace(
            ID="id",
            XPATH="xpath",
            ACCESSIBILITY_ID="accessibility_id",
            ANDROID_UIAUTOMATOR="uiautomator",
        )
        job = Job(
            title="测试开发工程师",
            company="目标科技",
            salary="20-30K",
            location="上海 浦东",
            activity_level=ActivityLevel.TODAY,
            activity_text="今日活跃",
            jd_text="负责接口自动化、UI 自动化、性能测试与质量平台建设。" * 2,
        )

        target = adapter._find_job_title(job)

        self.assertIs(target, target_card.fields[config.element_ids["cardTitle"]])

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
            allow_contact=True,
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
        adapter = AppiumBossAdapter(config, allow_contact=True)
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
        adapter = AppiumBossAdapter(config, allow_contact=True)
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
            max_scrolls=1,
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
        duplicate_card = Job(
            title=job.title,
            company=job.company,
            salary="20-30K·14薪",
            location="上海·浦东新区",
            activity_level=job.activity_level,
            activity_text=job.activity_text,
            jd_text=job.jd_text,
            source_ref=job.source_ref,
        )
        opened: list[bool] = []
        open_list_calls: list[bool] = []
        exhausted_refreshes: list[bool] = []
        adapter._open_job_list = lambda: open_list_calls.append(True)
        adapter._return_to_job_list = lambda: open_list_calls.append(True)
        adapter._refresh_job_list = lambda: exhausted_refreshes.append(True)
        adapter._assert_no_blocker = lambda: None
        cards = [object() for _ in range(4)]
        pages = iter(([cards[0]], [cards[1]], [cards[2]], [cards[3]]))
        summaries = {
            cards[0]: job,
            cards[1]: duplicate_card,
            cards[2]: duplicate_card,
            cards[3]: duplicate_card,
        }
        adapter._find_job_cards = lambda: next(pages)
        adapter._read_card_summary = lambda card: summaries[card]
        adapter._open_bound_card_and_read_detail = (
            lambda card, _job, *, keep_open=False: opened.append(keep_open) or job
        )
        adapter._scroll_down = lambda: False

        self.assertEqual(adapter.next_job(), job)
        self.assertEqual(adapter.next_job(), None)
        self.assertEqual(opened, [True])
        self.assertEqual(len(open_list_calls), 2)
        self.assertEqual(exhausted_refreshes, [True])

    def test_streaming_never_exceeds_configured_scroll_limit(self) -> None:
        config = AppiumConfig(
            version=1,
            app_package="com.hpbr.bosszhipin",
            app_activity="",
            max_scrolls=3,
            job_card_locators=(),
            communicate_texts=(),
            continue_texts=(),
            blocker_texts=(),
        )
        adapter = AppiumBossAdapter(config)
        adapter.driver = object()
        adapter._by = object()
        scrolls: list[bool] = []
        page = 0

        def inactive_job() -> list[Job]:
            nonlocal page
            page += 1
            return [
                Job(
                    title=f"硬件测试工程师{page}",
                    company=f"示例公司{page}",
                    salary="20-30K",
                    location="上海",
                    activity_level=ActivityLevel.STALE,
                    activity_text="一个月前活跃",
                    jd_text="硬件测试岗位，不进入详情，仅用于验证滚动次数。" * 3,
                )
            ]

        adapter._open_job_list = lambda: None
        adapter._assert_no_blocker = lambda: None
        adapter._read_visible_card_summaries = inactive_job
        adapter._refresh_exhausted_list_once = lambda: False
        adapter._scroll_down = lambda: scrolls.append(True) or True

        self.assertIsNone(adapter.next_job())
        self.assertEqual(len(scrolls), 3)

    def test_false_scroll_result_waits_for_lazy_load_before_refresh(self) -> None:
        config = AppiumConfig(
            version=1,
            app_package="com.hpbr.bosszhipin",
            app_activity="",
            max_scrolls=2,
            job_card_locators=(),
            communicate_texts=(),
            continue_texts=(),
            blocker_texts=(),
        )
        adapter = AppiumBossAdapter(config, allow_contact=True)
        adapter.driver = object()
        adapter._by = object()
        stale = Job(
            title="旧岗位",
            company="示例公司",
            salary="20-30K",
            location="上海",
            activity_level=ActivityLevel.STALE,
            activity_text="本月活跃",
            jd_text="旧岗位描述" * 20,
        )
        loaded = Job(
            title="懒加载岗位",
            company="质量云",
            salary="25-35K",
            location="上海",
            activity_level=ActivityLevel.TODAY,
            activity_text="今日活跃",
            jd_text="懒加载岗位描述" * 20,
        )
        stale_card = object()
        loaded_card = object()
        pages = iter(([stale_card], [loaded_card]))
        refreshes: list[bool] = []
        adapter._open_job_list = lambda: None
        adapter._assert_no_blocker = lambda: None
        adapter._find_job_cards = lambda: next(pages)
        adapter._read_card_summary = lambda card: stale if card is stale_card else loaded
        adapter._scroll_down = lambda: False
        adapter._refresh_job_list = lambda: refreshes.append(True)
        adapter._open_bound_card_and_read_detail = lambda card, job, *, keep_open=False: job

        with patch("mobile_automation.appium_adapter.time.sleep"):
            self.assertEqual(adapter.next_job(), loaded)

        self.assertEqual(refreshes, [])

    def test_unchanged_pages_use_scroll_budget_before_single_refresh(self) -> None:
        config = AppiumConfig(
            version=1,
            app_package="com.hpbr.bosszhipin",
            app_activity="",
            max_scrolls=3,
            job_card_locators=(),
            communicate_texts=(),
            continue_texts=(),
            blocker_texts=(),
        )
        adapter = AppiumBossAdapter(config, allow_contact=True)
        adapter.driver = object()
        adapter._by = object()
        stale = Job(
            title="重复旧岗位",
            company="示例公司",
            salary="20-30K",
            location="上海",
            activity_level=ActivityLevel.STALE,
            activity_text="本月活跃",
            jd_text="重复旧岗位描述" * 20,
        )
        events: list[str] = []
        adapter._open_job_list = lambda: None
        adapter._assert_no_blocker = lambda: None
        adapter._read_visible_card_summaries = lambda: [stale]
        adapter._scroll_down = lambda: events.append("scroll") or False
        adapter._refresh_job_list = lambda: events.append("refresh")

        with patch("mobile_automation.appium_adapter.time.sleep"):
            self.assertIsNone(adapter.next_job())

        self.assertEqual(events, ["scroll", "scroll", "scroll", "refresh"])

    def test_streaming_skips_a_promotional_webview_and_continues_with_next_pending_job(self) -> None:
        config = AppiumConfig.load(Path("mobile_automation/selectors.v1.json"))
        adapter = AppiumBossAdapter(config)
        promotional = build_job_from_fields(
            title="测试开发工程师一",
            company="示例科技一",
            salary="20-30K",
            location="上海",
            activity_text="今日活跃",
            description="负责接口自动化、UI自动化、性能测试与质量平台建设。" * 2,
        )
        suitable = build_job_from_fields(
            title="测试开发工程师二",
            company="示例科技二",
            salary="20-30K",
            location="上海",
            activity_text="今日活跃",
            description="负责接口自动化、UI自动化、性能测试与质量平台建设。" * 2,
        )
        adapter.driver = object()
        adapter._by = object()
        adapter._stream_started = True
        promotional_card = object()
        suitable_card = object()
        adapter._assert_no_blocker = lambda: None
        adapter._find_job_cards = lambda: [promotional_card, suitable_card]
        adapter._read_card_summary = (
            lambda card: promotional if card is promotional_card else suitable
        )

        def open_detail(card: object, job: Job, *, keep_open: bool = False) -> Job:
            if job is promotional:
                raise AutomationError("NON_JOB_PAGE_OPENED", "点击岗位后进入了非岗位推广页")
            return job

        adapter._open_bound_card_and_read_detail = open_detail

        self.assertEqual(adapter.next_job(), suitable)


if __name__ == "__main__":
    unittest.main()
