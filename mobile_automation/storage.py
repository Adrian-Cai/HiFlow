from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .models import Batch, CandidateStatus, Job, MatchResult


CHINA_TIMEZONE = timezone(timedelta(hours=8))


class BatchStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def save(self, batch: Batch) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / f"{batch.id}.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(batch.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
        return target

    def load(self, batch_id: str) -> Batch:
        if not batch_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in batch_id):
            raise ValueError("batch_id 格式无效")
        target = self.root / f"{batch_id}.json"
        if not target.is_file():
            raise FileNotFoundError(f"批次不存在：{batch_id}")
        return Batch.from_dict(json.loads(target.read_text(encoding="utf-8")))

    def list(self) -> list[Batch]:
        if not self.root.exists():
            return []
        batches = [Batch.from_dict(json.loads(path.read_text(encoding="utf-8"))) for path in self.root.glob("batch-*.json")]
        return sorted(batches, key=lambda batch: batch.created_at, reverse=True)

    def contacted_fingerprints(self) -> set[str]:
        return {
            candidate.job.fingerprint
            for batch in self.list()
            for candidate in batch.candidates
            if candidate.status == CandidateStatus.CONTACTED
        }


class ApplicationStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.ledger_path = root / "applications.jsonl"

    def record_success(
        self,
        resume_id: str,
        job: Job,
        match: MatchResult,
        *,
        at: datetime | None = None,
    ) -> None:
        contacted_at = at or datetime.now(CHINA_TIMEZONE)
        if contacted_at.tzinfo is None:
            contacted_at = contacted_at.replace(tzinfo=CHINA_TIMEZONE)
        contacted_at = contacted_at.astimezone(CHINA_TIMEZONE)
        entry = {
            "at": contacted_at.isoformat(),
            "localDate": contacted_at.date().isoformat(),
            "resumeId": resume_id,
            "jobFingerprint": job.fingerprint,
            "job": job.to_dict(),
            "match": match.to_dict(),
        }
        self.root.mkdir(parents=True, exist_ok=True)
        with self.ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            handle.flush()

    def successful_count_on(self, local_date: date) -> int:
        target = local_date.isoformat()
        return sum(1 for entry in self._entries() if entry.get("localDate") == target)

    def contacted_fingerprints(self) -> set[str]:
        recorded = {
            str(entry.get("jobFingerprint") or "")
            for entry in self._entries()
            if entry.get("jobFingerprint")
        }
        return recorded | BatchStore(self.root).contacted_fingerprints()

    def _entries(self) -> list[dict[str, object]]:
        if not self.ledger_path.is_file():
            return []
        entries: list[dict[str, object]] = []
        for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                entries.append(entry)
        return entries
