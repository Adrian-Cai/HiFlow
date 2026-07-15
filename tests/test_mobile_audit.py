import json
import tempfile
import unittest
from pathlib import Path

from mobile_automation.audit import AuditLogger


class AuditLoggerTests(unittest.TestCase):
    def test_writes_structured_events_without_arbitrary_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            logger = AuditLogger(Path(directory))
            logger.write("BATCH_CREATED", batch_id="batch-1", job_fingerprint="abc", status="REVIEW")

            entry = json.loads(next(Path(directory).glob("events-*.jsonl")).read_text(encoding="utf-8"))
            self.assertEqual(entry["event"], "BATCH_CREATED")
            self.assertEqual(entry["batchId"], "batch-1")
            self.assertNotIn("pageSource", entry)


if __name__ == "__main__":
    unittest.main()
