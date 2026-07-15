from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .activity import ActivityLevel
from .errors import AutomationError, UserActionRequired, WorkflowError
from .models import Batch, BatchStatus, Candidate, CandidateStatus, Job, MatchResult, utc_now
from .policy import JobPolicy
from .storage import CHINA_TIMEZONE, ApplicationStore, BatchStore


ELIGIBLE_ACTIVITY = {ActivityLevel.TODAY, ActivityLevel.WITHIN_3_DAYS}


class JobScanner(Protocol):
    def scan_jobs(self, limit: int) -> list[Job]: ...


class JobMatcher(Protocol):
    def match(self, resume_id: str, job: Job) -> MatchResult: ...


class JobApplicator(Protocol):
    def contact(self, job: Job) -> None: ...


class StreamingJobSession(Protocol):
    def next_job(self) -> Job | None: ...

    def contact_current(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class StreamingRunResult:
    contacted: int
    skipped: int
    daily_total: int
    stop_reason: str


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    code: str
    job: Job | None = None
    reason: str = ""
    score: int | None = None
    daily_total: int | None = None
    daily_limit: int | None = None
    seconds: float | None = None


def run_streaming_applications(
    session: StreamingJobSession,
    matcher: JobMatcher,
    store: ApplicationStore,
    *,
    resume_id: str,
    policy: JobPolicy,
    daily_limit: int = 150,
    batch_size: int = 5,
    cooldown_seconds: float = 120,
    sleeper: Callable[[float], None] = time.sleep,
    now_provider: Callable[[], datetime] = lambda: datetime.now(CHINA_TIMEZONE),
    on_progress: Callable[[ProgressEvent], None] | None = None,
) -> StreamingRunResult:
    if not resume_id.strip():
        raise WorkflowError("RESUME_ID_REQUIRED", "resume_id 不能为空")
    if daily_limit < 1 or batch_size < 1 or cooldown_seconds < 0:
        raise ValueError("投递上限、分组大小和冷却时间配置无效")

    now = now_provider().astimezone(CHINA_TIMEZONE)
    daily_total = store.successful_count_on(now.date())
    contacted = 0
    skipped = 0
    contacted_fingerprints = store.contacted_fingerprints()
    emit = on_progress or (lambda _event: None)
    emit(ProgressEvent("RUN_STARTED", daily_total=daily_total, daily_limit=daily_limit))

    def finish(reason: str) -> StreamingRunResult:
        emit(ProgressEvent("RUN_STOPPED", reason=reason, daily_total=daily_total, daily_limit=daily_limit))
        return StreamingRunResult(contacted, skipped, daily_total, reason)

    if daily_total >= daily_limit:
        return finish("DAILY_LIMIT_REACHED")

    while daily_total < daily_limit:
        if contacted or skipped:
            emit(ProgressEvent("NEXT_JOB_REQUESTED", daily_total=daily_total, daily_limit=daily_limit))
        job = session.next_job()
        if job is None:
            return finish("NO_MORE_JOBS")
        emit(ProgressEvent("JOB_READ", job=job))
        if job.fingerprint in contacted_fingerprints:
            skipped += 1
            emit(ProgressEvent("JOB_SKIPPED", job=job, reason="ALREADY_CONTACTED"))
            continue

        precheck_reasons = policy.precheck(job)
        if precheck_reasons:
            skipped += 1
            emit(ProgressEvent("JOB_SKIPPED", job=job, reason=precheck_reasons[0]))
            continue
        match = matcher.match(resume_id, job)
        emit(ProgressEvent("JOB_MATCHED", job=job, score=match.score))
        if not policy.accepts_match(match):
            skipped += 1
            emit(ProgressEvent("JOB_SKIPPED", job=job, reason="MATCH_REJECTED", score=match.score))
            continue
        if not session.contact_current():
            skipped += 1
            emit(ProgressEvent("JOB_SKIPPED", job=job, reason="ALREADY_CONTACTED_ON_PLATFORM"))
            continue

        contacted_at = now_provider().astimezone(CHINA_TIMEZONE)
        store.record_success(resume_id, job, match, at=contacted_at)
        contacted_fingerprints.add(job.fingerprint)
        contacted += 1
        daily_total += 1
        emit(
            ProgressEvent(
                "JOB_CONTACTED",
                job=job,
                score=match.score,
                daily_total=daily_total,
                daily_limit=daily_limit,
            )
        )
        if daily_total >= daily_limit:
            return finish("DAILY_LIMIT_REACHED")
        if daily_total % batch_size == 0:
            emit(ProgressEvent("COOLDOWN_STARTED", seconds=cooldown_seconds, daily_total=daily_total))
            sleeper(cooldown_seconds)

    return finish("DAILY_LIMIT_REACHED")


def select_candidates(
    jobs: Iterable[Job],
    matches: Mapping[str, MatchResult],
    *,
    threshold: int = 80,
    excluded_fingerprints: set[str] | None = None,
    limit: int = 5,
) -> list[Candidate]:
    if not 0 <= threshold <= 100:
        raise ValueError("threshold 必须在 0 到 100 之间")
    if not 1 <= limit <= 5:
        raise ValueError("limit 必须在 1 到 5 之间")

    excluded = excluded_fingerprints or set()
    selected: list[Candidate] = []
    for job in jobs:
        match = matches.get(job.fingerprint)
        if job.fingerprint in excluded or job.activity_level not in ELIGIBLE_ACTIVITY or match is None:
            continue
        if match.score < threshold or match.decision.upper() != "RECOMMEND" or match.hits_exclusion:
            continue
        selected.append(Candidate(job=job, match=match))

    selected.sort(key=lambda candidate: candidate.match.score, reverse=True)
    return selected[:limit]


def scan_and_create_batch(
    scanner: JobScanner,
    matcher: JobMatcher,
    store: BatchStore,
    *,
    resume_id: str,
    threshold: int = 80,
    scan_limit: int = 20,
    candidate_limit: int = 5,
) -> Batch:
    if not resume_id.strip():
        raise WorkflowError("RESUME_ID_REQUIRED", "resume_id 不能为空")
    if not 1 <= scan_limit <= 50:
        raise WorkflowError("SCAN_LIMIT_INVALID", "scan_limit 必须在 1 到 50 之间")

    jobs = scanner.scan_jobs(scan_limit)
    contacted = store.contacted_fingerprints()
    unique_jobs: dict[str, Job] = {}
    matches: dict[str, MatchResult] = {}
    for job in jobs:
        if job.fingerprint in unique_jobs or job.fingerprint in contacted:
            continue
        unique_jobs[job.fingerprint] = job
        if job.activity_level in ELIGIBLE_ACTIVITY:
            matches[job.fingerprint] = matcher.match(resume_id, job)

    candidates = select_candidates(
        unique_jobs.values(),
        matches,
        threshold=threshold,
        excluded_fingerprints=contacted,
        limit=candidate_limit,
    )
    batch = Batch.create(resume_id, candidates)
    store.save(batch)
    return batch


def apply_batch(
    batch: Batch,
    applicator: JobApplicator,
    store: BatchStore,
    *,
    resume: bool = False,
) -> Batch:
    if resume:
        if batch.status != BatchStatus.PAUSED:
            raise WorkflowError("BATCH_NOT_PAUSED", "只有已暂停批次可以恢复")
    elif batch.status != BatchStatus.CONFIRMED:
        raise WorkflowError("BATCH_NOT_CONFIRMED", "批次必须先确认才能执行")

    batch.status = BatchStatus.APPLYING
    batch.updated_at = utc_now()
    store.save(batch)

    for candidate in batch.candidates:
        if candidate.status in {CandidateStatus.CONTACTED, CandidateStatus.SKIPPED}:
            continue
        if resume and candidate.status == CandidateStatus.NEEDS_USER_ACTION:
            candidate.status = CandidateStatus.CONFIRMED
            candidate.failure_reason = ""
        if candidate.status != CandidateStatus.CONFIRMED:
            continue

        candidate.status = CandidateStatus.APPLYING
        candidate.updated_at = utc_now()
        store.save(batch)
        try:
            applicator.contact(candidate.job)
        except UserActionRequired as error:
            candidate.status = CandidateStatus.NEEDS_USER_ACTION
            candidate.failure_reason = error.message
            candidate.updated_at = utc_now()
            batch.status = BatchStatus.PAUSED
            batch.updated_at = utc_now()
            store.save(batch)
            return batch
        except AutomationError as error:
            candidate.status = CandidateStatus.FAILED
            candidate.failure_reason = error.message
            candidate.updated_at = utc_now()
            batch.status = BatchStatus.FAILED
            batch.updated_at = utc_now()
            store.save(batch)
            return batch

        candidate.status = CandidateStatus.CONTACTED
        candidate.failure_reason = ""
        candidate.updated_at = utc_now()
        store.save(batch)

    batch.status = BatchStatus.COMPLETED
    batch.updated_at = utc_now()
    store.save(batch)
    return batch
