from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from .activity import ActivityLevel


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _fingerprint_part(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def make_job_fingerprint(title: str, company: str, salary: str, location: str) -> str:
    raw = "|".join(_fingerprint_part(part) for part in (title, company, salary, location))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


class CandidateStatus(StrEnum):
    REVIEW = "REVIEW"
    CONFIRMED = "CONFIRMED"
    APPLYING = "APPLYING"
    CONTACTED = "CONTACTED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"
    NEEDS_USER_ACTION = "NEEDS_USER_ACTION"


class BatchStatus(StrEnum):
    REVIEW = "REVIEW"
    CONFIRMED = "CONFIRMED"
    APPLYING = "APPLYING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(slots=True)
class Job:
    title: str
    company: str
    salary: str
    location: str
    activity_level: ActivityLevel
    activity_text: str
    jd_text: str
    source_ref: str = ""
    collected_at: str = field(default_factory=utc_now)

    @property
    def fingerprint(self) -> str:
        return make_job_fingerprint(self.title, self.company, self.salary, self.location)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "company": self.company,
            "salary": self.salary,
            "location": self.location,
            "activityLevel": self.activity_level.value,
            "activityText": self.activity_text,
            "jdText": self.jd_text,
            "sourceRef": self.source_ref,
            "jobFingerprint": self.fingerprint,
            "collectedAt": self.collected_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Job":
        return cls(
            title=str(data.get("title") or ""),
            company=str(data.get("company") or ""),
            salary=str(data.get("salary") or ""),
            location=str(data.get("location") or ""),
            activity_level=ActivityLevel(str(data.get("activityLevel") or ActivityLevel.UNKNOWN)),
            activity_text=str(data.get("activityText") or ""),
            jd_text=str(data.get("jdText") or ""),
            source_ref=str(data.get("sourceRef") or ""),
            collected_at=str(data.get("collectedAt") or utc_now()),
        )


@dataclass(slots=True)
class MatchResult:
    score: int
    decision: str
    matched_points: list[str] = field(default_factory=list)
    missing_points: list[str] = field(default_factory=list)
    risk_points: list[str] = field(default_factory=list)
    suggested_first_message: str = ""

    @property
    def hits_exclusion(self) -> bool:
        return any("排除词" in point for point in self.risk_points)

    def to_dict(self) -> dict[str, Any]:
        return {
            "matchScore": self.score,
            "decision": self.decision,
            "matchedPoints": self.matched_points,
            "missingPoints": self.missing_points,
            "riskPoints": self.risk_points,
            "suggestedFirstMessage": self.suggested_first_message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MatchResult":
        return cls(
            score=int(data.get("matchScore", data.get("score", 0)) or 0),
            decision=str(data.get("decision") or "PASS").upper(),
            matched_points=list(data.get("matchedPoints", data.get("matched_points", [])) or []),
            missing_points=list(data.get("missingPoints", data.get("missing_points", [])) or []),
            risk_points=list(data.get("riskPoints", data.get("risk_points", [])) or []),
            suggested_first_message=str(
                data.get("suggestedFirstMessage", data.get("suggested_first_message", "")) or ""
            ),
        )


@dataclass(slots=True)
class Candidate:
    job: Job
    match: MatchResult
    status: CandidateStatus = CandidateStatus.REVIEW
    failure_reason: str = ""
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job": self.job.to_dict(),
            **self.match.to_dict(),
            "status": self.status.value,
            "failureReason": self.failure_reason,
            "updatedAt": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Candidate":
        return cls(
            job=Job.from_dict(dict(data.get("job") or {})),
            match=MatchResult.from_dict(data),
            status=CandidateStatus(str(data.get("status") or CandidateStatus.REVIEW)),
            failure_reason=str(data.get("failureReason") or ""),
            updated_at=str(data.get("updatedAt") or utc_now()),
        )


@dataclass(slots=True)
class Batch:
    id: str
    resume_id: str
    candidates: list[Candidate]
    status: BatchStatus = BatchStatus.REVIEW
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    @classmethod
    def create(cls, resume_id: str, candidates: list[Candidate]) -> "Batch":
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        return cls(id=f"batch-{timestamp}-{uuid.uuid4().hex[:8]}", resume_id=resume_id, candidates=candidates)

    @property
    def is_confirmed(self) -> bool:
        return self.status in {BatchStatus.CONFIRMED, BatchStatus.APPLYING, BatchStatus.PAUSED, BatchStatus.COMPLETED}

    def confirm(self) -> None:
        if self.status != BatchStatus.REVIEW:
            raise ValueError("只有待审核批次可以确认")
        self.status = BatchStatus.CONFIRMED
        for candidate in self.candidates:
            if candidate.status == CandidateStatus.REVIEW:
                candidate.status = CandidateStatus.CONFIRMED
                candidate.updated_at = utc_now()
        self.updated_at = utc_now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "batchId": self.id,
            "resumeId": self.resume_id,
            "status": self.status.value,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Batch":
        return cls(
            id=str(data.get("batchId") or ""),
            resume_id=str(data.get("resumeId") or ""),
            status=BatchStatus(str(data.get("status") or BatchStatus.REVIEW)),
            candidates=[Candidate.from_dict(item) for item in list(data.get("candidates") or [])],
            created_at=str(data.get("createdAt") or utc_now()),
            updated_at=str(data.get("updatedAt") or utc_now()),
        )
