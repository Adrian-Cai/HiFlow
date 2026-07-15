from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from .appium_adapter import AppiumBossAdapter, AppiumConfig
from .audit import AuditLogger
from .errors import HiFlowMobileError, WorkflowError
from .matcher import MatchClient
from .models import Batch, BatchStatus
from .policy import JobPolicy
from .storage import ApplicationStore, BatchStore
from .workflow import ProgressEvent, apply_batch, run_streaming_applications, scan_and_create_batch


PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = PACKAGE_DIR / "data"
DEFAULT_CONFIG = PACKAGE_DIR / "selectors.v1.json"


_SKIP_REASON_TEXT = {
    "SALARY_UNPARSABLE": "薪资格式无法可靠识别",
    "SALARY_BELOW_MINIMUM": "薪资低于设定下限",
    "RECRUITER_INACTIVE": "招聘者超过3天未活跃或活跃度未知",
    "EXCLUDED_DOMAIN": "命中硬件、物联网、车载等禁投方向",
    "ALREADY_CONTACTED": "本地记录显示已经沟通过",
    "ALREADY_CONTACTED_ON_PLATFORM": "岗位页面显示继续沟通，未重复打招呼",
    "MATCH_REJECTED": "匹配度或推荐条件未达到自动沟通线",
}

_FAILURE_HINT_TEXT = {
    "APPIUM_SESSION_FAILED": "请确认手机已解锁并允许 USB 调试；建议改用一键启动脚本自动检查依赖服务。",
    "MATCH_SERVICE_UNAVAILABLE": "本地匹配服务不可用；建议改用一键启动脚本自动启动服务。",
    "SECURITY_VERIFICATION": "任务已暂停，进度已经保留；请在手机上完成验证后重新启动。",
}


def format_failure(code: str, message: str) -> str:
    hint = _FAILURE_HINT_TEXT.get(code)
    suffix = f"；处理建议：{hint}" if hint else ""
    return f"[失败] {message}（错误码：{code}）{suffix}"


def format_device_status(category: str, message: str) -> str:
    return f"[{category}] {message}"


def format_progress_event(event: ProgressEvent) -> str:
    job_name = event.job.title if event.job else "当前岗位"
    if event.code == "RUN_STARTED":
        daily_total = int(event.daily_total or 0)
        daily_limit = int(event.daily_limit or 0)
        return (
            f"[进度] 今日历史已沟通 {daily_total}/{daily_limit}，"
            f"剩余 {max(0, daily_limit - daily_total)}"
        )
    if event.code == "JOB_READ" and event.job:
        return f"[岗位] 正在检查岗位：{job_name}｜{event.job.company}｜{event.job.salary}｜{event.job.activity_text}"
    if event.code == "JOB_SKIPPED":
        reason = _SKIP_REASON_TEXT.get(event.reason, event.reason or "未满足筛选条件")
        return f"[跳过] {job_name}｜原因：{reason}"
    if event.code == "JOB_MATCHED":
        return f"[匹配] {job_name}｜匹配度 {event.score}%"
    if event.code == "JOB_CONTACTED":
        return f"[沟通] 已成功打招呼：{job_name}｜今日累计 {event.daily_total}/{event.daily_limit}"
    if event.code == "COOLDOWN_STARTED":
        seconds = int(event.seconds or 0)
        return f"[等待] 已完成一组沟通，暂停 {seconds} 秒后继续"
    if event.code == "NEXT_JOB_REQUESTED":
        return "[列表] 正在返回原岗位列表，继续查找下一个岗位"
    if event.code == "RUN_STOPPED":
        if event.reason == "DAILY_LIMIT_REACHED":
            return f"[完成] 今日沟通已达到 {event.daily_total}/{event.daily_limit}，任务停止"
        if event.reason == "NO_MORE_JOBS":
            return f"[完成] 当前列表没有更多新岗位，今日累计 {event.daily_total}/{event.daily_limit}"
        return f"[完成] 任务结束：{event.reason}"
    return f"[状态] {event.code}"


def _print_progress(event: ProgressEvent) -> None:
    print(f"{time.strftime('%H:%M:%S')} {format_progress_event(event)}", flush=True)


def _print_device_status(category: str, message: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {format_device_status(category, message)}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hiflow-mobile", description="HiFlow Android Appium 岗位筛选与批次沟通")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    subparsers = parser.add_subparsers(dest="command", required=True)

    auto = subparsers.add_parser("auto", help="逐岗位筛选并在当前详情页即时沟通")
    auto.add_argument("--resume-id", required=True)
    auto.add_argument("--minimum-salary-k", type=float, default=15)
    auto.add_argument("--threshold", type=int, default=90)
    auto.add_argument("--batch-size", type=int, default=5)
    auto.add_argument("--cooldown-seconds", type=float, default=120)
    auto.add_argument("--daily-limit", type=int, default=150)
    auto.add_argument("--service-url", default="http://127.0.0.1:8787")
    _add_appium_options(auto)

    scan = subparsers.add_parser("scan", help="扫描活跃岗位并生成待确认批次")
    scan.add_argument("--resume-id", required=True)
    scan.add_argument("--threshold", type=int, default=80)
    scan.add_argument("--scan-limit", type=int, default=20)
    scan.add_argument("--candidate-limit", type=int, default=5)
    scan.add_argument("--service-url", default="http://127.0.0.1:8787")
    _add_appium_options(scan)

    apply = subparsers.add_parser("apply", help="确认并执行候选批次")
    apply.add_argument("--batch-id", required=True)
    _add_appium_options(apply)

    resume = subparsers.add_parser("resume", help="人工完成验证后恢复批次")
    resume.add_argument("--batch-id", required=True)
    _add_appium_options(resume)

    status = subparsers.add_parser("status", help="查看批次状态")
    status.add_argument("--batch-id", required=True)

    subparsers.add_parser("doctor", help="只读检查 ADB 与 Python Appium 客户端")
    return parser


def _add_appium_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--appium-url", default="http://127.0.0.1:4723")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)


def _print_batch(batch: Batch) -> None:
    print(f"批次: {batch.id}")
    print(f"状态: {batch.status.value}")
    print(f"简历: {batch.resume_id}")
    if not batch.candidates:
        print("候选: 0")
        return
    print(f"候选: {len(batch.candidates)}")
    for index, candidate in enumerate(batch.candidates, 1):
        job = candidate.job
        print(
            f"{index}. [{candidate.status.value}] {job.title} | {job.company} | "
            f"{job.salary} | {job.location or '-'} | {job.activity_text} | {candidate.match.score}%"
        )
        if candidate.failure_reason:
            print(f"   原因: {candidate.failure_reason}")


def _confirm(prompt: str, expected: str) -> None:
    entered = input(f"{prompt}\n请输入 {expected}：").strip()
    if entered != expected:
        raise WorkflowError("CONFIRMATION_REJECTED", "确认文本不匹配，未执行任何沟通动作")


def _adapter(args: argparse.Namespace) -> AppiumBossAdapter:
    return AppiumBossAdapter(
        AppiumConfig.load(args.config),
        args.appium_url,
        status_reporter=_print_device_status,
    )


def run(args: argparse.Namespace) -> int:
    if args.command == "auto":
        application_store = ApplicationStore(args.data_dir)
        policy = JobPolicy(
            minimum_salary_k=args.minimum_salary_k,
            match_threshold=args.threshold,
        )
        print(f"{time.strftime('%H:%M:%S')} [启动] 正在连接手机自动化服务……", flush=True)
        with _adapter(args) as adapter:
            print(f"{time.strftime('%H:%M:%S')} [启动] 手机连接成功，开始逐个检查岗位", flush=True)
            result = run_streaming_applications(
                adapter,
                MatchClient(args.service_url),
                application_store,
                resume_id=args.resume_id,
                policy=policy,
                daily_limit=args.daily_limit,
                batch_size=args.batch_size,
                cooldown_seconds=args.cooldown_seconds,
                on_progress=_print_progress,
            )
        print(
            f"{time.strftime('%H:%M:%S')} [汇总] 本次成功 {result.contacted} 个，"
            f"跳过 {result.skipped} 个，今日累计 {result.daily_total} 个",
            flush=True,
        )
        return 0

    store = BatchStore(args.data_dir)
    if args.command == "doctor":
        return _doctor()
    if args.command == "status":
        _print_batch(store.load(args.batch_id))
        return 0
    if args.command == "scan":
        with _adapter(args) as adapter:
            batch = scan_and_create_batch(
                adapter,
                MatchClient(args.service_url),
                store,
                resume_id=args.resume_id,
                threshold=args.threshold,
                scan_limit=args.scan_limit,
                candidate_limit=args.candidate_limit,
            )
        _print_batch(batch)
        print(f"确认后执行：python -m mobile_automation apply --batch-id {batch.id}")
        return 0

    batch = store.load(args.batch_id)
    _print_batch(batch)
    if args.command == "apply":
        if batch.status != BatchStatus.REVIEW:
            raise WorkflowError("BATCH_NOT_REVIEW", "apply 仅接受待审核批次")
        _confirm("确认后将逐个点击以上岗位的沟通按钮。", f"APPLY {batch.id}")
        batch.confirm()
        store.save(batch)
        with _adapter(args) as adapter:
            result = apply_batch(batch, adapter, store)
    elif args.command == "resume":
        _confirm("请先在手机上完成人工验证。", f"RESUME {batch.id}")
        with _adapter(args) as adapter:
            result = apply_batch(batch, adapter, store, resume=True)
    else:
        raise WorkflowError("COMMAND_UNSUPPORTED", "不支持的命令")

    _print_batch(result)
    if result.status == BatchStatus.PAUSED:
        print(f"人工处理完成后恢复：python -m mobile_automation resume --batch-id {result.id}")
        return 3
    return 0 if result.status == BatchStatus.COMPLETED else 2


def _doctor() -> int:
    try:
        completed = subprocess.run(["adb", "devices", "-l"], capture_output=True, text=True, timeout=10, check=True)
    except (FileNotFoundError, subprocess.SubprocessError):
        print(json.dumps({"ok": False, "code": "ADB_UNAVAILABLE", "message": "未找到可用的 adb"}, ensure_ascii=False))
        return 2
    devices = [line.strip() for line in completed.stdout.splitlines()[1:] if line.strip()]
    try:
        import appium  # noqa: F401
        client_installed = True
    except ImportError:
        client_installed = False
    result = doctor_result(devices, client_installed)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


def doctor_result(devices: list[str], client_installed: bool) -> dict[str, object]:
    states = [line.split()[1] for line in devices if len(line.split()) >= 2]
    if "device" in states:
        device_state = "device"
    elif "authorizing" in states:
        device_state = "authorizing"
    elif "unauthorized" in states:
        device_state = "unauthorized"
    elif states:
        device_state = states[0]
    else:
        device_state = "missing"
    return {
        "ok": device_state == "device" and client_installed,
        "deviceState": device_state,
        "adbDevices": devices,
        "appiumPythonClient": "installed" if client_installed else "missing",
    }


def main(argv: list[str] | None = None) -> int:
    args: argparse.Namespace | None = None
    logger: AuditLogger | None = None
    try:
        args = build_parser().parse_args(argv)
        logger = AuditLogger(args.data_dir / "logs")
        logger.write("COMMAND_STARTED", batch_id=getattr(args, "batch_id", ""), status=args.command)
        exit_code = run(args)
        logger.write(
            "COMMAND_FINISHED",
            batch_id=getattr(args, "batch_id", ""),
            status=args.command,
            code=str(exit_code),
        )
        return exit_code
    except (HiFlowMobileError, FileNotFoundError, ValueError) as error:
        code = getattr(error, "code", "COMMAND_FAILED")
        if logger is not None and args is not None:
            logger.write("COMMAND_FAILED", batch_id=getattr(args, "batch_id", ""), status=args.command, code=code)
        print(f"{time.strftime('%H:%M:%S')} {format_failure(code, str(error))}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print(f"{time.strftime('%H:%M:%S')} [结束] 操作已由用户中断", file=sys.stderr)
        return 130
