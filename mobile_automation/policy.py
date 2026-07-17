from __future__ import annotations

import re
from dataclasses import dataclass

from .activity import ActivityLevel
from .models import Job, MatchResult


ELIGIBLE_ACTIVITY = {ActivityLevel.TODAY, ActivityLevel.WITHIN_3_DAYS}

_K_RANGE = re.compile(r"(?P<low>\d+(?:\.\d+)?)\s*[-–—~至]\s*\d+(?:\.\d+)?\s*[Kk]")
_K_SINGLE = re.compile(r"(?P<low>\d+(?:\.\d+)?)\s*[Kk](?:以上)?")
_WAN_RANGE = re.compile(r"(?P<low>\d+(?:\.\d+)?)\s*[-–—~至]\s*\d+(?:\.\d+)?\s*万\s*元")
_YUAN_MONTH_RANGE = re.compile(
    r"(?P<low>\d+(?:\.\d+)?)\s*[-–—~至]\s*\d+(?:\.\d+)?\s*元\s*/\s*(?:月|个月)"
)

_EXCLUDED_DOMAIN_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"硬件测试|硬件加速|智能硬件|嵌入式|固件|单片机|示波器|烧录|射频|芯片测试",
        r"(?<![A-Za-z0-9])(?:MCU|PCB|FPGA|EMC|RTOS|BMC|BIOS)(?![A-Za-z0-9])",
        r"物联网|(?<![A-Za-z0-9])IoT(?![A-Za-z0-9])|Zigbee|LoRa|智能家居",
        r"车载测试|车载软件|车载底层|车载.*测试|车联网|汽车电子|智能座舱|自动驾驶|"
        r"(?<![A-Za-z0-9])(?:ADAS|AUTOSAR)(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])(?:ECU|UDS|HIL|SIL)(?![A-Za-z0-9])|"
        r"T-?Box|(?<![A-Za-z0-9])SOME/IP(?![A-Za-z0-9])",
        r"工控测试|工业控制|产线测试|仪器仪表测试",
    )
)


def parse_salary_lower_k(value: str) -> float | None:
    text = re.sub(r"\s+", "", str(value or ""))
    if not text or "面议" in text or re.search(r"/(?:天|日|时|小时)", text):
        return None

    for pattern, multiplier in (
        (_K_RANGE, 1.0),
        (_K_SINGLE, 1.0),
        (_WAN_RANGE, 10.0),
        (_YUAN_MONTH_RANGE, 0.001),
    ):
        match = pattern.search(text)
        if match:
            return float(match.group("low")) * multiplier
    return None


def hits_excluded_domain(job: Job) -> bool:
    text = "\n".join((job.title, job.company, job.jd_text))
    return any(pattern.search(text) for pattern in _EXCLUDED_DOMAIN_PATTERNS)


@dataclass(frozen=True, slots=True)
class JobPolicy:
    minimum_salary_k: float = 15
    match_threshold: int = 90

    def precheck(self, job: Job) -> list[str]:
        reasons: list[str] = []
        salary_lower_k = parse_salary_lower_k(job.salary)
        if salary_lower_k is None:
            reasons.append("SALARY_UNPARSABLE")
        elif salary_lower_k < self.minimum_salary_k:
            reasons.append("SALARY_BELOW_MINIMUM")
        if job.activity_level not in ELIGIBLE_ACTIVITY:
            reasons.append("RECRUITER_INACTIVE")
        if hits_excluded_domain(job):
            reasons.append("EXCLUDED_DOMAIN")
        return reasons

    def accepts_match(self, match: MatchResult) -> bool:
        return (
            match.score >= self.match_threshold
            and match.decision.upper() == "RECOMMEND"
            and not match.hits_exclusion
        )
