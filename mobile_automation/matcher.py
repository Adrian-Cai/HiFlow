from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .errors import HiFlowMobileError
from .models import Job, MatchResult


class MatchServiceError(HiFlowMobileError):
    pass


class MatchClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8787", timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def match(self, resume_id: str, job: Job) -> MatchResult:
        payload = {
            "resume_id": resume_id,
            "jd_text": job.jd_text,
            "source": "boss-android",
            "job_meta": {
                "title": job.title,
                "company": job.company,
                "salary": job.salary,
                "location": job.location,
                "link": job.source_ref,
            },
        }
        request = Request(
            f"{self.base_url}/match",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise MatchServiceError("MATCH_SERVICE_ERROR", f"本地匹配服务返回 HTTP {error.code}") from error
        except (URLError, TimeoutError) as error:
            raise MatchServiceError("MATCH_SERVICE_UNAVAILABLE", "无法连接本地匹配服务") from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise MatchServiceError("MATCH_RESPONSE_INVALID", "本地匹配服务返回了无效 JSON") from error

        if not isinstance(data, dict) or "score" not in data or "decision" not in data:
            raise MatchServiceError("MATCH_RESPONSE_INVALID", "本地匹配服务响应缺少 score 或 decision")
        try:
            result = MatchResult.from_dict(data)
        except (TypeError, ValueError) as error:
            raise MatchServiceError("MATCH_RESPONSE_INVALID", "本地匹配服务响应字段格式无效") from error
        if not 0 <= result.score <= 100 or result.decision not in {"RECOMMEND", "PASS"}:
            raise MatchServiceError("MATCH_RESPONSE_INVALID", "本地匹配服务响应取值无效")
        return result
