from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


class AuditLogger:
    """Writes a deliberately small event schema; raw UI and personal data are not accepted."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def write(
        self,
        event: str,
        *,
        batch_id: str = "",
        job_fingerprint: str = "",
        status: str = "",
        code: str = "",
        count: int | None = None,
    ) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        now = datetime.now(UTC)
        entry: dict[str, object] = {
            "at": now.isoformat(),
            "event": event,
        }
        if batch_id:
            entry["batchId"] = batch_id
        if job_fingerprint:
            entry["jobFingerprint"] = job_fingerprint
        if status:
            entry["status"] = status
        if code:
            entry["code"] = code
        if count is not None:
            entry["count"] = count
        target = self.root / f"events-{now.strftime('%Y%m%d')}.jsonl"
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
