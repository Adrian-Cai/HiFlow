import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mobile_automation.activity import ActivityLevel
from mobile_automation.matcher import MatchClient, MatchServiceError
from mobile_automation.models import Job


class _MatchHandler(BaseHTTPRequestHandler):
    response_status = 200
    response_body = {
        "score": 95,
        "decision": "RECOMMEND",
        "risk_points": [],
        "matched_points": ["技能覆盖：Python"],
    }
    received = None

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        type(self).received = json.loads(self.rfile.read(length).decode("utf-8"))
        body = json.dumps(type(self).response_body).encode("utf-8")
        self.send_response(type(self).response_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def sample_job() -> Job:
    return Job(
        title="测试开发工程师",
        company="示例公司",
        salary="20-30K",
        location="上海",
        activity_level=ActivityLevel.TODAY,
        activity_text="今日活跃",
        jd_text="负责自动化测试、接口测试、性能压测和持续集成质量保障。" * 2,
    )


class MatchClientTests(unittest.TestCase):
    def setUp(self) -> None:
        _MatchHandler.response_status = 200
        _MatchHandler.response_body = {"score": 95, "decision": "RECOMMEND", "risk_points": []}
        _MatchHandler.received = None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _MatchHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def test_match_sends_resume_and_job_metadata(self) -> None:
        client = MatchClient(f"http://127.0.0.1:{self.server.server_port}")
        result = client.match("resume_001", sample_job())

        self.assertEqual(result.score, 95)
        self.assertEqual(result.decision, "RECOMMEND")
        self.assertEqual(_MatchHandler.received["resume_id"], "resume_001")
        self.assertEqual(_MatchHandler.received["job_meta"]["company"], "示例公司")

    def test_match_rejects_invalid_service_response(self) -> None:
        _MatchHandler.response_body = {"decision": "RECOMMEND"}
        client = MatchClient(f"http://127.0.0.1:{self.server.server_port}")

        with self.assertRaises(MatchServiceError) as raised:
            client.match("resume_001", sample_job())

        self.assertEqual(raised.exception.code, "MATCH_RESPONSE_INVALID")

    def test_match_client_rejects_any_non_loopback_service(self) -> None:
        with self.assertRaises(MatchServiceError) as raised:
            MatchClient("https://matcher.example.com")

        self.assertEqual(raised.exception.code, "MATCH_SERVICE_NOT_LOCAL")


if __name__ == "__main__":
    unittest.main()
