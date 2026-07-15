import tempfile
import unittest
from pathlib import Path

from mobile_automation.activity import ActivityLevel
from mobile_automation.models import Batch, BatchStatus, Candidate, CandidateStatus, Job, MatchResult
from mobile_automation.storage import BatchStore


def sample_batch() -> Batch:
    job = Job(
        title="测试开发工程师",
        company="示例公司",
        salary="20-30K",
        location="上海",
        activity_level=ActivityLevel.TODAY,
        activity_text="今日活跃",
        jd_text="负责自动化测试、接口测试和质量平台建设。" * 3,
    )
    return Batch.create("resume_001", [Candidate(job=job, match=MatchResult(score=95, decision="RECOMMEND"))])


class BatchStoreTests(unittest.TestCase):
    def test_batch_round_trips_and_requires_explicit_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = BatchStore(Path(directory))
            batch = sample_batch()
            store.save(batch)

            loaded = store.load(batch.id)
            self.assertEqual(loaded.status, BatchStatus.REVIEW)
            self.assertFalse(loaded.is_confirmed)

            loaded.confirm()
            store.save(loaded)
            confirmed = store.load(batch.id)
            self.assertEqual(confirmed.status, BatchStatus.CONFIRMED)
            self.assertTrue(confirmed.is_confirmed)

    def test_contacted_fingerprints_include_only_successful_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = BatchStore(Path(directory))
            contacted = sample_batch()
            contacted.candidates[0].status = CandidateStatus.CONTACTED
            store.save(contacted)

            failed = sample_batch()
            failed.candidates[0].status = CandidateStatus.FAILED
            store.save(failed)

            self.assertEqual(store.contacted_fingerprints(), {contacted.candidates[0].job.fingerprint})


if __name__ == "__main__":
    unittest.main()
