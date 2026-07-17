from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Protocol

from .errors import AutomationError, WorkflowError
from .models import Job
from .storage import CHINA_TIMEZONE, ApplicationStore


@dataclass(frozen=True, slots=True)
class VerificationIdentity:
    device_serial: str
    boss_version: str
    selector_hash: str
    code_hash: str

    @property
    def gate_id(self) -> str:
        raw = "|".join(
            (self.device_serial, self.boss_version, self.selector_hash, self.code_hash)
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class VerificationSessionMetrics:
    scrolls: int = 0
    refreshes: int = 0
    contact_attempts: int = 0


@dataclass(frozen=True, slots=True)
class VerificationReport:
    status: str
    started_at: str
    finished_at: str
    gate_id: str
    device_serial: str
    boss_version: str
    selector_hash: str
    code_hash: str
    city: str
    filter_text: str
    target_jobs: int
    unique_jobs: int
    detail_round_trips: int
    scrolls: int
    refreshes: int
    reconnects: int
    ui_timeouts: int
    contact_attempts: int
    duration_seconds: float
    ledger_before: dict[str, object]
    ledger_after: dict[str, object]
    error_code: str = ""
    error_message: str = ""

    def to_dict(self) -> dict[str, object]:
        values = asdict(self)
        return {
            "status": values["status"],
            "startedAt": values["started_at"],
            "finishedAt": values["finished_at"],
            "gateId": values["gate_id"],
            "deviceSerial": values["device_serial"],
            "bossVersion": values["boss_version"],
            "selectorHash": values["selector_hash"],
            "codeHash": values["code_hash"],
            "city": values["city"],
            "filterText": values["filter_text"],
            "targetJobs": values["target_jobs"],
            "uniqueJobs": values["unique_jobs"],
            "detailRoundTrips": values["detail_round_trips"],
            "scrolls": values["scrolls"],
            "refreshes": values["refreshes"],
            "reconnects": values["reconnects"],
            "uiTimeouts": values["ui_timeouts"],
            "contactAttempts": values["contact_attempts"],
            "durationSeconds": values["duration_seconds"],
            "ledgerBefore": values["ledger_before"],
            "ledgerAfter": values["ledger_after"],
            "errorCode": values["error_code"],
            "errorMessage": values["error_message"],
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "VerificationReport":
        return cls(
            status=str(data.get("status") or "FAIL"),
            started_at=str(data.get("startedAt") or ""),
            finished_at=str(data.get("finishedAt") or ""),
            gate_id=str(data.get("gateId") or ""),
            device_serial=str(data.get("deviceSerial") or ""),
            boss_version=str(data.get("bossVersion") or ""),
            selector_hash=str(data.get("selectorHash") or ""),
            code_hash=str(data.get("codeHash") or ""),
            city=str(data.get("city") or ""),
            filter_text=str(data.get("filterText") or ""),
            target_jobs=int(data.get("targetJobs") or 0),
            unique_jobs=int(data.get("uniqueJobs") or 0),
            detail_round_trips=int(data.get("detailRoundTrips") or 0),
            scrolls=int(data.get("scrolls") or 0),
            refreshes=int(data.get("refreshes") or 0),
            reconnects=int(data.get("reconnects") or 0),
            ui_timeouts=int(data.get("uiTimeouts") or 0),
            contact_attempts=int(data.get("contactAttempts") or 0),
            duration_seconds=float(data.get("durationSeconds") or 0),
            ledger_before=dict(data.get("ledgerBefore") or {}),
            ledger_after=dict(data.get("ledgerAfter") or {}),
            error_code=str(data.get("errorCode") or ""),
            error_message=str(data.get("errorMessage") or ""),
        )


class ReadOnlyVerificationSession(Protocol):
    def verify_preconditions(self) -> dict[str, str]: ...

    def next_job(self) -> Job | None: ...

    def finish_current_job(self) -> None: ...

    def verification_metrics(self) -> VerificationSessionMetrics: ...


class VerificationReportStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def save(self, report: VerificationReport) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        stamp = report.started_at.replace(":", "").replace("+", "-")
        target = self.root / f"verification-{stamp}.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(target)
        return target

    def list(self) -> list[VerificationReport]:
        if not self.root.exists():
            return []
        reports: list[VerificationReport] = []
        for path in sorted(self.root.glob("verification-*.json"), reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                reports.append(VerificationReport.from_dict(data))
        return reports

    def require_valid_gate(
        self,
        identity: VerificationIdentity,
        *,
        minimum_jobs: int = 50,
    ) -> VerificationReport:
        for report in self.list():
            if (
                report.status == "PASS"
                and report.gate_id == identity.gate_id
                and report.target_jobs >= minimum_jobs
                and report.unique_jobs >= minimum_jobs
                and report.detail_round_trips == report.unique_jobs
                and report.reconnects == 0
                and report.ui_timeouts == 0
                and report.contact_attempts == 0
                and report.ledger_before == report.ledger_after
            ):
                return report
        raise WorkflowError(
            "VERIFICATION_REQUIRED",
            "没有找到与当前设备、BOSS 版本和代码一致的 50 岗位零异常验证报告",
        )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _critical_code_paths() -> tuple[Path, ...]:
    package = Path(__file__).resolve().parent
    project = package.parent
    return (
        package / "activity.py",
        package / "appium_adapter.py",
        package / "cli.py",
        package / "matcher.py",
        package / "models.py",
        package / "policy.py",
        package / "storage.py",
        package / "verification.py",
        package / "workflow.py",
        package / "start.ps1",
        project / "local_service" / "server.py",
    )


def _sha256_paths(paths: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for path in sorted((item.resolve() for item in paths), key=lambda item: str(item).lower()):
        if not path.is_file():
            raise WorkflowError("VERIFICATION_CODE_MISSING", f"门禁关键文件不存在：{path}")
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def collect_verification_identity(
    selector_path: Path,
    *,
    critical_paths: tuple[Path, ...] | None = None,
) -> VerificationIdentity:
    try:
        serial_result = subprocess.run(
            ["adb", "get-serialno"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as error:
        raise WorkflowError("DEVICE_IDENTITY_FAILED", "无法读取已授权手机的设备序列号") from error
    serial = serial_result.stdout.strip()
    if not serial or serial.lower() in {"unknown", "error"}:
        raise WorkflowError("DEVICE_IDENTITY_FAILED", "没有识别到唯一的已授权手机")

    try:
        package_result = subprocess.run(
            ["adb", "-s", serial, "shell", "dumpsys", "package", "com.hpbr.bosszhipin"],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as error:
        raise WorkflowError("BOSS_VERSION_FAILED", "无法读取手机上的 BOSS 直聘版本") from error
    version_name = re.search(r"\bversionName=([^\s]+)", package_result.stdout)
    version_code = re.search(r"\bversionCode=(\d+)", package_result.stdout)
    if version_name is None or version_code is None:
        raise WorkflowError("BOSS_VERSION_FAILED", "手机上未识别到 BOSS 直聘的完整版本信息")

    if not selector_path.is_file():
        raise WorkflowError("CONFIG_NOT_FOUND", f"选择器配置不存在：{selector_path}")
    paths = critical_paths if critical_paths is not None else _critical_code_paths()
    return VerificationIdentity(
        device_serial=serial,
        boss_version=f"{version_name.group(1)} ({version_code.group(1)})",
        selector_hash=_sha256_file(selector_path),
        code_hash=_sha256_paths(paths),
    )


def application_snapshot(store: ApplicationStore, at: datetime) -> dict[str, object]:
    path = store.ledger_path
    content = path.read_bytes() if path.is_file() else b""
    return {
        "sha256": hashlib.sha256(content).hexdigest(),
        "dailyCount": store.successful_count_on(at.astimezone(CHINA_TIMEZONE).date()),
    }


def run_stability_verification(
    session: ReadOnlyVerificationSession,
    application_store: ApplicationStore,
    report_store: VerificationReportStore,
    *,
    identity: VerificationIdentity,
    target_jobs: int = 50,
    now_provider: Callable[[], datetime] = lambda: datetime.now(CHINA_TIMEZONE),
    on_progress: Callable[[int, int, Job], None] | None = None,
) -> VerificationReport:
    if target_jobs < 1:
        raise ValueError("target_jobs 必须大于 0")

    started = now_provider().astimezone(CHINA_TIMEZONE)
    ledger_before = application_snapshot(application_store, started)
    preconditions: dict[str, str] = {}
    unique_fingerprints: set[str] = set()
    detail_round_trips = 0
    status = "INCOMPLETE"
    error_code = ""
    error_message = ""
    ui_timeouts = 0

    try:
        preconditions = session.verify_preconditions()
        while len(unique_fingerprints) < target_jobs:
            job = session.next_job()
            if job is None:
                break
            session.finish_current_job()
            detail_round_trips += 1
            if job.fingerprint not in unique_fingerprints:
                unique_fingerprints.add(job.fingerprint)
            if on_progress is not None:
                on_progress(len(unique_fingerprints), target_jobs, job)
        if len(unique_fingerprints) >= target_jobs:
            if detail_round_trips == len(unique_fingerprints):
                status = "PASS"
            else:
                status = "FAIL"
                error_code = "VERIFICATION_DUPLICATE_DETAIL"
                error_message = "验证期间重复进入了已检查岗位详情"
    except AutomationError as error:
        status = "FAIL"
        error_code = error.code
        error_message = error.message
        if error.code == "APPIUM_PAGE_READ_FAILED" or "TIMEOUT" in error.code:
            ui_timeouts = 1
    except Exception as error:  # report unexpected read-only failures instead of losing diagnostics
        status = "FAIL"
        error_code = "VERIFICATION_UNEXPECTED_ERROR"
        error_message = str(error)

    finished = now_provider().astimezone(CHINA_TIMEZONE)
    ledger_after = application_snapshot(application_store, finished)
    metrics = session.verification_metrics()
    if metrics.contact_attempts:
        status = "FAIL"
        error_code = error_code or "VERIFICATION_CONTACT_ATTEMPTED"
    if ledger_before != ledger_after:
        status = "FAIL"
        error_code = error_code or "VERIFICATION_LEDGER_CHANGED"
    if metrics.refreshes > 1:
        status = "FAIL"
        error_code = error_code or "VERIFICATION_REFRESH_LIMIT_EXCEEDED"

    report = VerificationReport(
        status=status,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        gate_id=identity.gate_id,
        device_serial=identity.device_serial,
        boss_version=identity.boss_version,
        selector_hash=identity.selector_hash,
        code_hash=identity.code_hash,
        city=str(preconditions.get("city") or ""),
        filter_text=str(preconditions.get("filterText") or ""),
        target_jobs=target_jobs,
        unique_jobs=len(unique_fingerprints),
        detail_round_trips=detail_round_trips,
        scrolls=metrics.scrolls,
        refreshes=metrics.refreshes,
        reconnects=0,
        ui_timeouts=ui_timeouts,
        contact_attempts=metrics.contact_attempts,
        duration_seconds=max(0.0, (finished - started).total_seconds()),
        ledger_before=ledger_before,
        ledger_after=ledger_after,
        error_code=error_code,
        error_message=error_message,
    )
    report_store.save(report)
    return report
