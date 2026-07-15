import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from mobile_automation.activity import ActivityLevel
from mobile_automation.models import Batch, BatchStatus, Candidate, CandidateStatus, Job, MatchResult
from mobile_automation.storage import CHINA_TIMEZONE, ApplicationStore, BatchStore


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


class ApplicationStoreTests(unittest.TestCase):
    def test_daily_count_includes_contacted_candidates_from_legacy_batches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch = sample_batch()
            batch.candidates[0].status = CandidateStatus.CONTACTED
            batch.candidates[0].updated_at = "2026-07-15T04:02:38+00:00"
            BatchStore(root).save(batch)

            count = ApplicationStore(root).successful_count_on(date(2026, 7, 15))

            self.assertEqual(count, 1)

    def test_daily_count_deduplicates_the_same_job_across_legacy_and_streaming_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch = sample_batch()
            candidate = batch.candidates[0]
            candidate.status = CandidateStatus.CONTACTED
            candidate.updated_at = "2026-07-15T04:02:38+00:00"
            BatchStore(root).save(batch)

            store = ApplicationStore(root)
            store.record_success(
                "resume_001",
                candidate.job,
                candidate.match,
                at=datetime(2026, 7, 15, 13, 0, tzinfo=CHINA_TIMEZONE),
            )

            self.assertEqual(store.successful_count_on(date(2026, 7, 15)), 1)


if __name__ == "__main__":
    unittest.main()
