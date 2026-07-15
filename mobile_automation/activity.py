from __future__ import annotations

import re
from enum import StrEnum


class ActivityLevel(StrEnum):
    TODAY = "TODAY"
    WITHIN_3_DAYS = "WITHIN_3_DAYS"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


_TODAY_PATTERNS = (
    r"在线",
    r"刚刚活跃",
    r"今日活跃",
    r"今天活跃",
    r"\d+\s*分钟(?:前)?活跃",
    r"\d+\s*小时(?:前)?活跃",
    r"\d+\s*分钟(?:前)?回复",
    r"\d+\s*小时(?:前)?回复",
    r"今日回复(?:\d+\+?次)?",
)
_RECENT_PATTERNS = (
    r"近\s*3\s*日活跃",
    r"3\s*日内活跃",
    r"近\s*三\s*日活跃",
    r"三\s*日内活跃",
)


def normalize_activity(value: str | None) -> ActivityLevel:
    text = re.sub(r"\s+", "", str(value or ""))
    if not text:
        return ActivityLevel.UNKNOWN
    if any(re.search(pattern, text) for pattern in _TODAY_PATTERNS):
        return ActivityLevel.TODAY
    if any(re.search(pattern, text) for pattern in _RECENT_PATTERNS):
        return ActivityLevel.WITHIN_3_DAYS

    days = re.search(r"(\d+)天前活跃", text)
    if days:
        return ActivityLevel.WITHIN_3_DAYS if int(days.group(1)) <= 3 else ActivityLevel.STALE
    if re.search(r"本周活跃|本月活跃|\d+周前活跃|\d+月前活跃|很久未活跃", text):
        return ActivityLevel.STALE
    return ActivityLevel.UNKNOWN
