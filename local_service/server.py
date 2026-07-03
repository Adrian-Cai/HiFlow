from __future__ import annotations

import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


HOST = "127.0.0.1"
PORT = 8787
DATA_DIR = Path(__file__).resolve().parent / "data"
RESUMES_FILE = DATA_DIR / "resumes.json"
MATCH_LOG_FILE = DATA_DIR / "matches.jsonl"


DEFAULT_RESUME = {
    "id": "resume_001",
    "name": "AI测试/测试开发",
    "summary": "6年测试开发经验，覆盖自动化、接口测试、性能压测、CI/CD、质量平台和AI测试提效。",
    "target_titles": [
        "测试开发",
        "测试工程师",
        "自动化测试",
        "质量工程师",
        "AI测试",
        "测试平台",
    ],
    "skills": [
        "软件测试",
        "测试用例",
        "需求分析",
        "缺陷管理",
        "接口测试",
        "自动化测试",
        "UI自动化",
        "Playwright",
        "Selenium",
        "Cypress",
        "Postman",
        "JMeter",
        "k6",
        "pytest",
        "Python",
        "Java",
        "SQL",
        "Linux",
        "Git",
        "Jenkins",
        "CI/CD",
        "Allure",
        "测试平台",
        "质量工程",
        "AI测试",
        "大模型",
        "Prompt",
    ],
    "exclude_keywords": [
        "销售",
        "电话销售",
        "客服",
        "地推",
        "培训贷",
        "无薪",
        "保险",
        "直播",
        "主播",
        "外包驻场",
        "纯外包",
        "996",
        "单休",
    ],
}


def ensure_data_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not RESUMES_FILE.exists():
        RESUMES_FILE.write_text(json.dumps([DEFAULT_RESUME], ensure_ascii=False, indent=2), encoding="utf-8")


def read_resumes() -> list[dict[str, Any]]:
    ensure_data_files()
    try:
      data = json.loads(RESUMES_FILE.read_text(encoding="utf-8"))
      return data if isinstance(data, list) else [DEFAULT_RESUME]
    except (OSError, json.JSONDecodeError):
      return [DEFAULT_RESUME]


def write_resumes(resumes: list[dict[str, Any]]) -> None:
    ensure_data_files()
    RESUMES_FILE.write_text(json.dumps(resumes, ensure_ascii=False, indent=2), encoding="utf-8")


def append_match_log(entry: dict[str, Any]) -> None:
    ensure_data_files()
    with MATCH_LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def contains_any(text: str, terms: list[str]) -> list[str]:
    normalized = normalize_text(text)
    return [term for term in terms if normalize_text(term) in normalized]


def clamp_score(value: float) -> int:
    return max(0, min(100, round(value)))


def pick_resume(resume_id: str | None) -> dict[str, Any]:
    resumes = read_resumes()
    for resume in resumes:
        if resume.get("id") == resume_id:
            return resume
    return resumes[0] if resumes else DEFAULT_RESUME


def score_match(payload: dict[str, Any]) -> dict[str, Any]:
    jd_text = str(payload.get("jd_text") or "")
    if len(jd_text.strip()) < 40:
        raise ValueError("jd_text 过短，无法完成匹配")

    job_meta = payload.get("job_meta") if isinstance(payload.get("job_meta"), dict) else {}
    resume = pick_resume(payload.get("resume_id"))
    title_text = " ".join([
        str(job_meta.get("title") or ""),
        jd_text[:400],
    ])

    target_titles = list(resume.get("target_titles") or [])
    skills = list(resume.get("skills") or [])
    excludes = list(resume.get("exclude_keywords") or [])

    matched_titles = contains_any(title_text, target_titles)
    hit_excludes = contains_any(jd_text, excludes)
    jd_required_skills = contains_any(jd_text, skills)
    matched_skills = jd_required_skills
    missing_skills = infer_missing_skills(jd_text, skills)

    hard_score = 100
    if hit_excludes:
        hard_score = 20
    elif not matched_titles:
        hard_score = 72

    title_score = 100 if matched_titles else 62
    skill_score = 76 if not jd_required_skills else min(100, 58 + len(matched_skills) * 7)
    condition_score = 100 if not hit_excludes else 25
    llm_stub_score = 82 if matched_titles else 66

    score = clamp_score(
        hard_score * 0.28 +
        title_score * 0.22 +
        skill_score * 0.30 +
        condition_score * 0.12 +
        llm_stub_score * 0.08
    )

    decision = "RECOMMEND" if score >= 90 and not hit_excludes else "PASS"
    risk_points = build_risk_points(hit_excludes, matched_titles, missing_skills)
    matched_points = build_matched_points(matched_titles, matched_skills)

    result = {
        "score": score,
        "decision": decision,
        "title": job_meta.get("title") or "",
        "matched_points": matched_points,
        "missing_points": missing_skills[:8],
        "risk_points": risk_points,
        "suggested_first_message": build_first_message(job_meta, matched_skills),
        "suggested_second_message": build_second_message(resume, matched_skills),
        "detail": {
            "hardScore": hard_score,
            "titleScore": title_score,
            "skillScore": skill_score,
            "conditionScore": condition_score,
            "llmScore": llm_stub_score,
            "matchedTitles": matched_titles,
            "source": "local-rule-engine",
        },
    }

    append_match_log({
        "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "resume_id": resume.get("id"),
        "job_meta": job_meta,
        "score": score,
        "decision": decision,
    })
    return result


def infer_missing_skills(jd_text: str, resume_skills: list[str]) -> list[str]:
    common_requirements = [
        "Appium",
        "Go",
        "TypeScript",
        "Kubernetes",
        "Docker",
        "安全测试",
        "数据测试",
        "测试管理",
    ]
    normalized_resume = {normalize_text(skill) for skill in resume_skills}
    return [
        requirement
        for requirement in common_requirements
        if normalize_text(requirement) in normalize_text(jd_text)
        and normalize_text(requirement) not in normalized_resume
    ]


def build_risk_points(hit_excludes: list[str], matched_titles: list[str], missing_skills: list[str]) -> list[str]:
    risks = []
    if hit_excludes:
        risks.append(f"命中排除词：{'、'.join(hit_excludes[:4])}")
    if not matched_titles:
        risks.append("岗位方向与目标方向匹配不明显")
    if len(missing_skills) >= 2:
        risks.append("存在多个简历未覆盖的显性技能")
    return risks


def build_matched_points(matched_titles: list[str], matched_skills: list[str]) -> list[str]:
    points = []
    if matched_titles:
        points.append(f"岗位方向命中：{'、'.join(matched_titles[:3])}")
    if matched_skills:
        points.append(f"技能覆盖：{'、'.join(matched_skills[:8])}")
    if not points:
        points.append("未命中强匹配项，建议人工复核")
    return points


def build_first_message(job_meta: dict[str, Any], matched_skills: list[str]) -> str:
    title = job_meta.get("title") or "这个岗位"
    skills = "、".join(matched_skills[:4]) if matched_skills else "测试开发、质量保障"
    return f"您好，我对{title}比较感兴趣，我的经历和岗位中的{skills}较匹配，方便进一步沟通吗？"


def build_second_message(resume: dict[str, Any], matched_skills: list[str]) -> str:
    skills = "、".join(matched_skills[:5]) if matched_skills else "自动化测试、接口测试、CI/CD"
    return f"您好，我补充一下背景：{resume.get('summary', '')} 其中和岗位最相关的是{skills}，期待进一步交流。"


class HiFlowHandler(BaseHTTPRequestHandler):
    server_version = "HiFlowLocal/0.1"

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_common_headers()
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self.send_json(200, {"status": "ok", "service": "hiflow-local", "version": "0.1.0"})
            return
        if path == "/resumes":
            self.send_json(200, {"resumes": read_resumes()})
            return
        self.send_error_json(404, "NOT_FOUND", "资源不存在")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/match":
            self.handle_match()
            return
        if path == "/resumes":
            self.handle_upsert_resume()
            return
        self.send_error_json(404, "NOT_FOUND", "资源不存在")

    def handle_match(self) -> None:
        try:
            payload = self.read_json_body(limit=512_000)
            result = score_match(payload)
            self.send_json(200, result)
        except ValueError as error:
            self.send_error_json(422, "VALIDATION_ERROR", str(error))
        except Exception:
            self.send_error_json(500, "INTERNAL_ERROR", "本地匹配服务内部错误")

    def handle_upsert_resume(self) -> None:
        try:
            payload = self.read_json_body(limit=128_000)
            resume_id = str(payload.get("id") or "").strip()
            if not resume_id:
                raise ValueError("id 不能为空")
            sanitized = sanitize_resume(payload)
            resumes = [resume for resume in read_resumes() if resume.get("id") != resume_id]
            resumes.append(sanitized)
            write_resumes(resumes)
            self.send_json(201, {"resume": sanitized})
        except ValueError as error:
            self.send_error_json(422, "VALIDATION_ERROR", str(error))
        except Exception:
            self.send_error_json(500, "INTERNAL_ERROR", "保存简历画像失败")

    def read_json_body(self, limit: int) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise ValueError("请求体不能为空")
        if length > limit:
            raise ValueError("请求体过大")
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError("请求体不是合法 JSON") from error
        if not isinstance(data, dict):
            raise ValueError("请求体必须是 JSON object")
        return data

    def send_json(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_common_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, status: int, code: str, message: str) -> None:
        self.send_json(status, {"error": {"code": code, "message": message}})

    def send_common_headers(self) -> None:
        origin = self.headers.get("Origin", "")
        if is_allowed_origin(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[HiFlow] {self.address_string()} - {format % args}")


def is_allowed_origin(origin: str) -> bool:
    if not origin:
        return False
    return (
        origin.startswith("chrome-extension://")
        or origin.startswith("edge-extension://")
        or origin in {"http://127.0.0.1:8787", "http://localhost:8787"}
    )


def sanitize_resume(payload: dict[str, Any]) -> dict[str, Any]:
    resume_id = str(payload.get("id") or "").strip()
    name = str(payload.get("name") or resume_id).strip()
    summary = str(payload.get("summary") or "").strip()

    if len(summary) > 20_000:
        raise ValueError("简历摘要过长，请控制在 20000 字以内")

    return {
        "id": resume_id,
        "name": name[:100],
        "summary": summary,
        "target_titles": normalize_list(payload.get("target_titles")),
        "skills": normalize_list(payload.get("skills")),
        "exclude_keywords": normalize_list(payload.get("exclude_keywords")),
    }


def normalize_list(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    else:
        items = re.split(r"[\n,，、]", str(value or ""))

    normalized = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in normalized:
            normalized.append(text[:80])

    return normalized[:200]


def main() -> None:
    ensure_data_files()
    server = ThreadingHTTPServer((HOST, PORT), HiFlowHandler)
    print(f"HiFlow local matcher listening on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
