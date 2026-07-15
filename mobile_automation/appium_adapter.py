from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .activity import ActivityLevel, normalize_activity
from .errors import AutomationError, UserActionRequired
from .models import Job


@dataclass(frozen=True, slots=True)
class Locator:
    by: str
    value: str


@dataclass(frozen=True, slots=True)
class AppiumConfig:
    version: int
    app_package: str
    app_activity: str
    max_scrolls: int
    job_card_locators: tuple[Locator, ...]
    communicate_texts: tuple[str, ...]
    continue_texts: tuple[str, ...]
    blocker_texts: tuple[str, ...]
    element_ids: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "AppiumConfig":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise AutomationError("CONFIG_NOT_FOUND", f"选择器配置不存在：{path}") from error
        except json.JSONDecodeError as error:
            raise AutomationError("CONFIG_INVALID", "选择器配置不是有效 JSON") from error

        locators = tuple(
            Locator(by=str(item.get("by") or ""), value=str(item.get("value") or ""))
            for item in list(data.get("jobCardLocators") or [])
        )
        if int(data.get("version", 0)) != 1:
            raise AutomationError("CONFIG_VERSION_UNSUPPORTED", "仅支持 version=1 的选择器配置")
        if not str(data.get("appPackage") or "").strip():
            raise AutomationError("CONFIG_INVALID", "appPackage 不能为空")
        if not locators or any(locator.by not in {"id", "xpath", "accessibility_id"} or not locator.value for locator in locators):
            raise AutomationError("CONFIG_INVALID", "jobCardLocators 配置无效")
        element_ids = {str(key): str(value) for key, value in dict(data.get("elementIds") or {}).items()}
        required_ids = {
            "jobTab",
            "jobList",
            "jobCard",
            "cardTitle",
            "cardCompany",
            "cardSalary",
            "cardLocation",
            "cardActivity",
            "detailTitle",
            "detailSalary",
            "detailLocation",
            "detailBossTitle",
            "detailActivity",
            "detailDescription",
            "communicateButton",
        }
        if required_ids - element_ids.keys() or any(not element_ids[key].strip() for key in required_ids):
            raise AutomationError("CONFIG_INVALID", "elementIds 缺少真机 PoC 已确认的必要控件")

        return cls(
            version=1,
            app_package=str(data["appPackage"]),
            app_activity=str(data.get("appActivity") or ""),
            max_scrolls=max(0, min(10, int(data.get("maxScrolls", 5)))),
            job_card_locators=locators,
            communicate_texts=tuple(data.get("communicateTexts") or ("立即沟通", "打招呼", "感兴趣")),
            continue_texts=tuple(data.get("continueTexts") or ("继续沟通",)),
            blocker_texts=tuple(data.get("blockerTexts") or ()),
            element_ids=element_ids,
        )


_SALARY = re.compile(r"\d+(?:\.\d+)?\s*[-–—~至]\s*\d+(?:\.\d+)?\s*[Kk]|\d+\s*[Kk](?:以上)?")
_CITIES = re.compile(r"北京|上海|广州|深圳|杭州|成都|武汉|南京|苏州|重庆|西安|郑州|长沙|天津|合肥|厦门|东莞|佛山|青岛|济南|周口")


def parse_job_card_text(value: str) -> Job | None:
    lines = [line.strip() for line in str(value or "").splitlines() if line.strip()]
    if not lines:
        return None
    activity_text = next((line for line in lines if normalize_activity(line) != ActivityLevel.UNKNOWN), "")
    activity_level = normalize_activity(activity_text)
    if activity_level == ActivityLevel.UNKNOWN:
        return None

    salary = next((line for line in lines if _SALARY.search(line)), "")
    location = next((line for line in lines if _CITIES.search(line)), "")
    title = next(
        (
            line
            for line in lines
            if line not in {activity_text, salary, location}
            and not re.search(r"经验|本科|大专|硕士|博士|招聘者", line)
        ),
        "",
    )
    company = next(
        (
            line
            for line in lines
            if line not in {title, activity_text, salary, location}
            and re.search(r"公司|科技|集团|网络|信息|软件|电子|智能", line)
        ),
        "",
    )
    jd_text = " ".join(lines)
    if not title or not company or not salary or len(jd_text) < 40:
        return None
    return Job(
        title=title,
        company=company,
        salary=salary,
        location=location,
        activity_level=activity_level,
        activity_text=activity_text,
        jd_text=jd_text,
        source_ref=f"{title}|{company}",
    )


def build_job_from_fields(
    *,
    title: str,
    company: str,
    salary: str,
    location: str,
    activity_text: str,
    description: str,
) -> Job:
    values = {
        "title": str(title or "").strip(),
        "company": str(company or "").strip(),
        "salary": str(salary or "").strip(),
        "location": str(location or "").strip(),
        "activity_text": str(activity_text or "").strip(),
        "description": str(description or "").strip(),
    }
    activity_level = normalize_activity(values["activity_text"])
    if not values["title"] or not values["company"] or not values["salary"]:
        raise AutomationError("JOB_FIELDS_INCOMPLETE", "岗位详情缺少标题、公司或薪资")
    if activity_level == ActivityLevel.UNKNOWN:
        raise AutomationError("JOB_ACTIVITY_UNKNOWN", "岗位活跃度无法可靠识别")
    if len(values["description"]) < 40:
        raise AutomationError("JOB_DESCRIPTION_INCOMPLETE", "岗位详情描述过短，已停止匹配")
    jd_text = "\n".join(
        value
        for value in (
            values["title"],
            values["company"],
            values["salary"],
            values["location"],
            values["activity_text"],
            values["description"],
        )
        if value
    )
    return Job(
        title=values["title"],
        company=values["company"],
        salary=values["salary"],
        location=values["location"],
        activity_level=activity_level,
        activity_text=values["activity_text"],
        jd_text=jd_text,
        source_ref=f"{values['title']}|{values['company']}",
    )


def _xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    return "concat(" + ", \"'\", ".join(f"'{part}'" for part in parts) + ")"


def is_known_subpage_activity(activity: str) -> bool:
    value = str(activity or "")
    return value.endswith(".geekjd.activity.BossJobPagerActivity") or value.endswith(
        ".chat.single.activity.ChatRoomActivity"
    )


def uiautomator_literal(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


class AppiumBossAdapter:
    def __init__(
        self,
        config: AppiumConfig,
        server_url: str = "http://127.0.0.1:4723",
        *,
        status_reporter: Callable[[str, str], None] | None = None,
    ) -> None:
        self.config = config
        self.server_url = server_url
        self._status_reporter = status_reporter or (lambda _category, _message: None)
        self.driver: Any | None = None
        self._by: Any | None = None
        self._current_job: Job | None = None
        self._stream_started = False
        self._stream_seen_cards: set[str] = set()
        self._stream_pending: list[Job] = []
        self._stream_unchanged_scrolls = 0
        self._stream_exhaustion_refreshed = False

    def __enter__(self) -> "AppiumBossAdapter":
        self.connect()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def connect(self) -> None:
        try:
            from appium import webdriver
            from appium.options.android import UiAutomator2Options
            from appium.webdriver.common.appiumby import AppiumBy
        except ImportError as error:
            raise AutomationError(
                "APPIUM_CLIENT_MISSING",
                "缺少 Appium-Python-Client，请先安装 mobile_automation/requirements.txt",
            ) from error

        capabilities = self._capabilities()
        try:
            self.driver = webdriver.Remote(
                self.server_url,
                options=UiAutomator2Options().load_capabilities(capabilities),
            )
        except Exception as error:
            raise AutomationError("APPIUM_SESSION_FAILED", "无法建立 Appium 真机会话") from error
        self._by = AppiumBy
        try:
            self._configure_driver_settings()
            self._assert_no_blocker()
        except (AutomationError, UserActionRequired):
            self.close()
            raise
        except Exception as error:
            self.close()
            raise AutomationError(
                "APPIUM_SESSION_CONFIG_FAILED",
                "无法配置 Appium 页面读取服务，请重新启动任务",
            ) from error

    def _configure_driver_settings(self) -> None:
        if self.driver is None:
            raise AutomationError("APPIUM_NOT_CONNECTED", "Appium 会话尚未建立")
        self.driver.update_settings({"enableNotificationListener": False})

    def _capabilities(self) -> dict[str, Any]:
        capabilities: dict[str, Any] = {
            "platformName": "Android",
            "automationName": "UiAutomator2",
            "deviceName": "Android",
            "appPackage": self.config.app_package,
            "noReset": True,
            "forceAppLaunch": False,
            "shouldTerminateApp": False,
            "autoGrantPermissions": False,
            "ignoreHiddenApiPolicyError": True,
            "newCommandTimeout": 180,
        }
        if self.config.app_activity:
            capabilities["appActivity"] = self.config.app_activity
        return capabilities

    def close(self) -> None:
        if self.driver is not None:
            try:
                self.driver.quit()
            finally:
                self.driver = None

    def scan_jobs(self, limit: int) -> list[Job]:
        self._require_driver()
        self._open_job_list()
        jobs: dict[str, Job] = {}
        seen_cards: set[str] = set()
        unchanged_scrolls = 0
        for _ in range(self.config.max_scrolls + 1):
            self._assert_no_blocker()
            discovered = 0
            summaries: list[Job] = []
            for element in self._find_job_cards():
                summary = self._read_card_summary(element)
                if summary is None:
                    continue
                card_key = "|".join((summary.title, summary.company, summary.salary, summary.location))
                if card_key in seen_cards:
                    continue
                seen_cards.add(card_key)
                discovered += 1
                if summary.activity_level not in {ActivityLevel.TODAY, ActivityLevel.WITHIN_3_DAYS}:
                    continue
                summaries.append(summary)
            for summary in summaries:
                job = self._open_and_read_detail(summary)
                jobs.setdefault(job.fingerprint, job)
                if len(jobs) >= limit:
                    return list(jobs.values())
            unchanged_scrolls = unchanged_scrolls + 1 if discovered == 0 else 0
            if unchanged_scrolls >= 2 or not self._scroll_down():
                break
            time.sleep(0.8)
        if not jobs:
            raise AutomationError("JOB_CARDS_NOT_FOUND", "没有识别到包含招聘者活跃度的岗位卡片")
        return list(jobs.values())

    def next_job(self) -> Job | None:
        try:
            return self._next_job()
        except (AutomationError, UserActionRequired):
            raise
        except Exception as error:
            raise AutomationError(
                "APPIUM_PAGE_READ_FAILED",
                "读取岗位列表时 Appium 页面服务异常，任务已安全停止",
            ) from error

    def _next_job(self) -> Job | None:
        self._require_driver()
        if not self._stream_started:
            self._stream_started = True
            self._stream_seen_cards.clear()
            self._stream_pending.clear()
            self._stream_unchanged_scrolls = 0
            self._stream_exhaustion_refreshed = False
            self._open_job_list()
        elif self._current_job is not None:
            self._return_to_job_list()
            self._current_job = None

        while True:
            if self._stream_pending:
                summary = self._stream_pending.pop(0)
                job = self._open_and_read_detail(summary, keep_open=True)
                self._current_job = job
                return job

            self._assert_no_blocker()
            discovered = 0
            for element in self._find_job_cards():
                summary = self._read_card_summary(element)
                if summary is None:
                    continue
                card_key = "|".join((summary.title, summary.company, summary.salary, summary.location))
                if card_key in self._stream_seen_cards:
                    continue
                self._stream_seen_cards.add(card_key)
                discovered += 1
                if summary.activity_level in {ActivityLevel.TODAY, ActivityLevel.WITHIN_3_DAYS}:
                    self._stream_pending.append(summary)

            if self._stream_pending:
                continue
            self._stream_unchanged_scrolls = self._stream_unchanged_scrolls + 1 if discovered == 0 else 0
            if self._stream_unchanged_scrolls >= 2:
                if self._refresh_exhausted_list_once():
                    continue
                return None
            if not self._scroll_down():
                if self._refresh_exhausted_list_once():
                    continue
                return None
            time.sleep(0.8)

    def contact(self, job: Job) -> None:
        try:
            self._contact(job)
        except (AutomationError, UserActionRequired):
            raise
        except Exception as error:
            raise AutomationError(
                "APPIUM_OPERATION_FAILED",
                "Appium 设备操作异常，已停止当前批次",
            ) from error

    def contact_current(self) -> bool:
        try:
            return self._contact_current()
        except (AutomationError, UserActionRequired):
            raise
        except Exception as error:
            raise AutomationError(
                "APPIUM_OPERATION_FAILED",
                "Appium 设备操作异常，已停止逐岗位沟通",
            ) from error

    def _contact_current(self) -> bool:
        self._require_driver()
        if self._current_job is None:
            raise AutomationError("CURRENT_JOB_MISSING", "当前不在可沟通的岗位详情页")
        self._assert_no_blocker()

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self._find_unique_text_element(self.config.continue_texts) is not None:
                return False
            communicate = self._find_unique_text_element(self.config.communicate_texts)
            if communicate is not None:
                communicate.click()
                self._status_reporter("沟通", "已点击打招呼，正在等待平台确认")
                if self._wait_for_contact_confirmation(timeout=10):
                    self._status_reporter("沟通", "平台已确认沟通成功")
                    return True
                raise AutomationError(
                    "CONTACT_NOT_CONFIRMED",
                    "已点击打招呼，但平台未确认沟通成功，本次未计入成功数量",
                )
            time.sleep(0.5)
            self._assert_no_blocker()
        raise AutomationError("COMMUNICATE_BUTTON_NOT_FOUND", "岗位详情页没有找到唯一的沟通按钮")

    def _contact(self, job: Job) -> None:
        self._require_driver()
        self._assert_no_blocker()
        self._open_job_list()
        target = self._find_job_title(job)
        if target is None:
            raise AutomationError("JOB_NOT_FOUND", "未能在当前岗位列表中重新定位候选岗位")
        target.click()

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            time.sleep(0.5)
            self._assert_no_blocker()
            if self._find_unique_text_element(self.config.continue_texts) is not None:
                return
            communicate = self._find_unique_text_element(self.config.communicate_texts)
            if communicate is not None:
                communicate.click()
                self._status_reporter("沟通", "已点击打招呼，正在等待平台确认")
                if self._wait_for_contact_confirmation(timeout=10):
                    self._status_reporter("沟通", "平台已确认沟通成功")
                    return
                raise AutomationError(
                    "CONTACT_NOT_CONFIRMED",
                    "已点击打招呼，但平台未确认沟通成功，本次未计入成功数量",
                )
        raise AutomationError("COMMUNICATE_BUTTON_NOT_FOUND", "岗位详情页没有找到唯一的沟通按钮")

    def _wait_for_contact_confirmation(self, *, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._assert_no_blocker()
            if self._find_unique_text_element(self.config.continue_texts) is not None:
                return True
            if self._chat_page_visible():
                return True
            time.sleep(0.5)
        return False

    def _chat_page_visible(self) -> bool:
        activity = str(self.driver.current_activity or "")
        if activity.endswith(".chat.single.activity.ChatRoomActivity"):
            return True
        return bool(
            self.driver.find_elements(
                self._by.ID,
                "com.hpbr.bosszhipin:id/editText_with_scrollbar",
            )
        )

    def _open_job_list(self) -> None:
        if self._job_list_visible():
            self._assert_no_blocker()
            return
        if self._known_subpage_visible():
            self._return_to_job_list()
            return
        tab = self._wait_unique_id(self.config.element_ids["jobTab"], timeout=10)
        tab.click()
        self._wait_unique_id(self.config.element_ids["jobList"], timeout=12)
        time.sleep(1)

    def _return_to_job_list(self) -> None:
        for _ in range(3):
            if self._job_list_visible():
                self._assert_no_blocker()
                time.sleep(0.4)
                return
            if not self._known_subpage_visible():
                raise AutomationError(
                    "UNSAFE_BACK_NAVIGATION",
                    "当前页面不是已知的岗位详情或沟通页面，未执行返回操作",
                )
            self._status_reporter("列表", "正在返回原岗位列表")
            self.driver.back()
            time.sleep(0.8)
        if not self._job_list_visible():
            raise AutomationError("JOB_LIST_NOT_RESTORED", "返回后没有恢复到原岗位列表")

    def _refresh_exhausted_list_once(self) -> bool:
        if self._stream_exhaustion_refreshed:
            return False
        self._refresh_job_list()
        self._stream_exhaustion_refreshed = True
        self._stream_unchanged_scrolls = 0
        return True

    def _refresh_job_list(self) -> None:
        if not self._job_list_visible():
            raise AutomationError("JOB_LIST_NOT_VISIBLE", "刷新前没有识别到岗位列表")
        self._assert_no_blocker()
        self._status_reporter("刷新", "当前列表已检查完，正在刷新一次查找新岗位")
        tab = self._wait_unique_id(self.config.element_ids["jobTab"], timeout=10)
        tab.click()
        self._wait_unique_id(self.config.element_ids["jobList"], timeout=12)
        time.sleep(2)

    def _job_list_visible(self) -> bool:
        matches = self._visible(
            self.driver.find_elements(self._by.ID, self.config.element_ids["jobList"])
        )
        if len(matches) > 1:
            raise AutomationError("LOCATOR_AMBIGUOUS", "岗位列表控件不唯一")
        return len(matches) == 1

    def _known_subpage_visible(self) -> bool:
        return is_known_subpage_activity(self.driver.current_activity) or bool(
            self.driver.find_elements(self._by.ID, self.config.element_ids["detailDescription"])
        ) or bool(
            self.driver.find_elements(self._by.ID, "com.hpbr.bosszhipin:id/editText_with_scrollbar")
        )

    def _read_card_summary(self, element: Any) -> Job | None:
        title = self._child_text(element, "cardTitle")
        company = self._child_text(element, "cardCompany")
        salary = self._child_text(element, "cardSalary")
        location = self._child_text(element, "cardLocation")
        activity_text = self._child_text(element, "cardActivity")
        activity_level = normalize_activity(activity_text)
        if not title or not company or not salary or activity_level == ActivityLevel.UNKNOWN:
            return None
        return Job(
            title=title,
            company=company,
            salary=salary,
            location=location,
            activity_level=activity_level,
            activity_text=activity_text,
            jd_text="\n".join(filter(None, (title, company, salary, location, activity_text))),
            source_ref=f"{title}|{company}",
        )

    def _open_and_read_detail(self, summary: Job, *, keep_open: bool = False) -> Job:
        target = self._find_job_title(summary)
        if target is None:
            raise AutomationError("JOB_NOT_FOUND", "扫描详情前无法重新定位岗位卡片")
        target.click()
        description_element = self._wait_unique_id(self.config.element_ids["detailDescription"], timeout=12)
        self._assert_no_blocker()

        description = str(description_element.text or "").strip()
        if "查看更多" in description:
            description_element.click()
            time.sleep(0.6)
            description_element = self._wait_unique_id(self.config.element_ids["detailDescription"], timeout=5)
            description = str(description_element.text or "").strip()

        title = self._text_by_id("detailTitle") or summary.title
        salary = self._text_by_id("detailSalary") or summary.salary
        location = self._text_by_id("detailLocation") or summary.location
        activity_text = self._text_by_id("detailActivity") or summary.activity_text
        boss_title = self._text_by_id("detailBossTitle")
        company = re.split(r"\s*[•·]\s*", boss_title, maxsplit=1)[0].strip() or summary.company
        job = build_job_from_fields(
            title=title,
            company=company,
            salary=salary,
            location=location,
            activity_text=activity_text,
            description=description,
        )
        if not keep_open:
            self.driver.back()
            self._wait_unique_id(self.config.element_ids["jobList"], timeout=12)
            time.sleep(0.8)
        return job

    def _child_text(self, element: Any, key: str) -> str:
        matches = self._visible(element.find_elements(self._by.ID, self.config.element_ids[key]))
        if len(matches) > 1:
            raise AutomationError("LOCATOR_AMBIGUOUS", f"岗位卡片字段 {key} 不唯一")
        return str(matches[0].text or "").strip() if matches else ""

    def _text_by_id(self, key: str) -> str:
        matches = self._visible(self.driver.find_elements(self._by.ID, self.config.element_ids[key]))
        if len(matches) > 1:
            raise AutomationError("LOCATOR_AMBIGUOUS", f"岗位详情字段 {key} 不唯一")
        return str(matches[0].text or "").strip() if matches else ""

    def _wait_unique_id(self, resource_id: str, *, timeout: float) -> Any:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._assert_no_blocker()
            matches = self._visible(self.driver.find_elements(self._by.ID, resource_id))
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise AutomationError("LOCATOR_AMBIGUOUS", f"资源控件不唯一：{resource_id}")
            time.sleep(0.5)
        raise AutomationError("LOCATOR_NOT_FOUND", f"等待资源控件超时：{resource_id}")

    def _require_driver(self) -> None:
        if self.driver is None or self._by is None:
            raise AutomationError("APPIUM_NOT_CONNECTED", "Appium 会话尚未建立")

    def _assert_no_blocker(self) -> None:
        self._require_driver()
        source = str(self.driver.page_source or "")
        blocker = next((text for text in self.config.blocker_texts if text and text in source), None)
        if blocker:
            raise UserActionRequired("SECURITY_VERIFICATION", f"检测到需要人工处理的页面：{blocker}")

    def _find_job_cards(self) -> list[Any]:
        cards: list[Any] = []
        seen: set[str] = set()
        for locator in self.config.job_card_locators:
            by = self._resolve_by(locator.by)
            for element in self.driver.find_elements(by, locator.value):
                element_id = str(getattr(element, "id", id(element)))
                if element_id not in seen and element.is_displayed():
                    seen.add(element_id)
                    cards.append(element)
        return cards

    def _find_job_title(self, job: Job) -> Any | None:
        title_elements = self._visible(
            self.driver.find_elements(self._by.ID, self.config.element_ids["cardTitle"])
        )
        exact_matches = [
            element
            for element in title_elements
            if str(element.text or element.get_attribute("content-desc") or "").strip() == job.title
        ]
        if len(exact_matches) == 1:
            return exact_matches[0]
        if len(exact_matches) > 1:
            raise AutomationError("LOCATOR_AMBIGUOUS", "候选岗位定位不唯一，已停止以避免误投")

        list_id = uiautomator_literal(self.config.element_ids["jobList"])
        title_id = uiautomator_literal(self.config.element_ids["cardTitle"])
        title = uiautomator_literal(job.title)
        selector = (
            f'new UiScrollable(new UiSelector().resourceId("{list_id}"))'
            f'.setMaxSearchSwipes({self.config.max_scrolls})'
            f'.scrollIntoView(new UiSelector().resourceId("{title_id}").text("{title}"))'
        )
        matches = self._visible(self.driver.find_elements(self._by.ANDROID_UIAUTOMATOR, selector))
        if len(matches) > 1:
            raise AutomationError("LOCATOR_AMBIGUOUS", "候选岗位定位不唯一，已停止以避免误投")
        return matches[0] if matches else None

    def _find_unique_text_element(self, texts: tuple[str, ...]) -> Any | None:
        matches: list[Any] = []
        seen: set[str] = set()
        for text in texts:
            literal = _xpath_literal(text)
            xpath = f"//*[@text={literal} or @content-desc={literal}]"
            for element in self._visible(self.driver.find_elements(self._by.XPATH, xpath)):
                element_id = str(getattr(element, "id", id(element)))
                if element_id not in seen:
                    seen.add(element_id)
                    matches.append(element)
        if len(matches) > 1:
            raise AutomationError("LOCATOR_AMBIGUOUS", "页面存在多个沟通按钮，已停止以避免误操作")
        return matches[0] if matches else None

    def _resolve_by(self, value: str) -> str:
        return {
            "id": self._by.ID,
            "xpath": self._by.XPATH,
            "accessibility_id": self._by.ACCESSIBILITY_ID,
        }[value]

    @staticmethod
    def _visible(elements: list[Any]) -> list[Any]:
        return [element for element in elements if element.is_displayed() and element.is_enabled()]

    def _scroll_down(self) -> bool:
        try:
            size = self.driver.get_window_size()
            self._status_reporter("列表", "正在向下滚动查找新岗位")
            center_x = int(size["width"] * 0.50)
            start_y = int(size["height"] * 0.75)
            end_y = int(size["height"] * 0.30)
            subprocess.run(
                [
                    "adb",
                    "shell",
                    "input",
                    "swipe",
                    str(center_x),
                    str(start_y),
                    str(center_x),
                    str(end_y),
                    "500",
                ],
                capture_output=True,
                check=True,
                timeout=5,
            )
            return True
        except Exception as error:
            raise AutomationError("SCROLL_FAILED", "岗位列表滚动失败") from error
