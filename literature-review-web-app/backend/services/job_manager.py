"""Job lifecycle management service for the literature review pipeline.

This module provides :class:`JobManager`, the single authoritative store for
all in-flight and completed review jobs.  Jobs are held in an in-memory
dictionary (so state is lost on process restart) protected by an
:class:`asyncio.Lock` for safe concurrent access from async request handlers
and background pipeline tasks.

Typical usage::

    manager = JobManager()
    job_id = await manager.create_job(topic="quantum computing", config=config)
    await manager.update_status(job_id, Stage.PAPERS_FETCHED, 20.0, "Papers fetched")
    await manager.complete_job(job_id, review)
    result = await manager.get_result(job_id)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from models.api import (
    JobResultResponse,
    JobStatusResponse,
    LiteratureReviewDTO,
    PaperDTO,
    ResearchGapDTO,
    ThemeDTO,
)
from models.job import Job, Stage, STAGE_ORDER

if TYPE_CHECKING:
    from models.api import ReviewConfig
    from models.paper import LiteratureReview

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stage → simplified status string mapping
# ---------------------------------------------------------------------------

#: Terminal / non-running stages have specific status strings; all pipeline
#: stages that represent active work map to ``"running"``.
_STAGE_TO_STATUS: dict[Stage, str] = {
    Stage.COMPLETED: "completed",
    Stage.FAILED: "failed",
    Stage.CANCELLED: "cancelled",
    Stage.PENDING: "pending",
}


def _stage_to_status(stage: Stage) -> str:
    """Map a :class:`Stage` value to a simplified API status string.

    Args:
        stage: The current pipeline stage.

    Returns:
        One of ``"pending"``, ``"running"``, ``"completed"``, ``"failed"``,
        or ``"cancelled"``.
    """
    return _STAGE_TO_STATUS.get(stage, "running")


# ---------------------------------------------------------------------------
# Active stages set (used for counting active jobs)
# ---------------------------------------------------------------------------

#: Stages that count as "active" (i.e. job is in progress or waiting to run).
_ACTIVE_STAGES: frozenset[Stage] = frozenset(
    [Stage.PENDING] + STAGE_ORDER
)


class JobManager:
    """Async-safe in-memory store and lifecycle manager for review jobs.

    All public methods are ``async`` and acquire :attr:`_lock` before
    reading or mutating :attr:`_jobs`, ensuring correctness under concurrent
    FastAPI request handlers and background pipeline tasks.

    Attributes:
        _jobs: Dictionary mapping ``job_id`` strings to :class:`~models.job.Job`
            instances.
        _lock: :class:`asyncio.Lock` guarding all mutations to ``_jobs``.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Job creation
    # ------------------------------------------------------------------

    async def create_job(self, topic: str, config: ReviewConfig) -> str:
        """Create a new review job and return its unique identifier.

        A UUID v4 is generated for the job.  The job starts in
        :attr:`Stage.PENDING` with ``progress_pct`` of ``0.0``.

        Args:
            topic: The research topic string submitted by the user.
            config: :class:`~models.api.ReviewConfig` supplied by the client.

        Returns:
            The ``job_id`` string (UUID v4).
        """
        job_id = str(uuid.uuid4())
        now = datetime.now(tz=timezone.utc)
        job = Job(
            job_id=job_id,
            topic=topic,
            config=config,
            status=Stage.PENDING,
            created_at=now,
            updated_at=now,
        )
        async with self._lock:
            self._jobs[job_id] = job
        logger.info("JobManager: created job %s for topic=%r", job_id, topic)
        return job_id

    # ------------------------------------------------------------------
    # Status queries
    # ------------------------------------------------------------------

    async def get_status(self, job_id: str) -> JobStatusResponse | None:
        """Return a :class:`~models.api.JobStatusResponse` for the given job.

        Elapsed seconds are computed from ``job.created_at`` to the current
        UTC time.  ``estimated_remaining_seconds`` is provided only while the
        job is in ``"running"`` or ``"pending"`` state; it is ``None`` once
        the job has reached a terminal state.

        Args:
            job_id: UUID string identifying the job.

        Returns:
            A :class:`~models.api.JobStatusResponse` if the job exists,
            otherwise ``None``.
        """
        async with self._lock:
            job = self._jobs.get(job_id)

        if job is None:
            return None

        now = datetime.now(tz=timezone.utc)
        elapsed = (now - job.created_at).total_seconds()
        status_str = _stage_to_status(job.status)

        estimated_remaining: float | None = None
        if status_str in ("running", "pending"):
            estimated_remaining = max(0.0, 120.0 - elapsed)

        return JobStatusResponse(
            job_id=job.job_id,
            status=status_str,
            stage=job.status.value,
            progress_pct=job.progress_pct,
            message=job.message,
            elapsed_seconds=elapsed,
            estimated_remaining_seconds=estimated_remaining,
        )

    async def get_result(self, job_id: str) -> JobResultResponse | None:
        """Return the completed review result for a job.

        Only returns a value when the job status is :attr:`Stage.COMPLETED`
        and ``job.result`` is not ``None``.

        Args:
            job_id: UUID string identifying the job.

        Returns:
            A :class:`~models.api.JobResultResponse` if the job is complete
            with a result, otherwise ``None``.
        """
        async with self._lock:
            job = self._jobs.get(job_id)

        if job is None:
            return None
        if job.status != Stage.COMPLETED or job.result is None:
            return None

        review_dto = self._review_to_dto(job.result)
        return JobResultResponse(
            job_id=job.job_id,
            review=review_dto,
            completed_at=job.updated_at,
        )

    # ------------------------------------------------------------------
    # Status mutations
    # ------------------------------------------------------------------

    async def update_status(
        self,
        job_id: str,
        stage: Stage,
        progress_pct: float,
        message: str,
    ) -> None:
        """Update the stage, progress, and message of an existing job.

        Args:
            job_id: UUID string identifying the job.
            stage: New :class:`Stage` value.
            progress_pct: New progress percentage (0.0–100.0).
            message: Human-readable status message.
        """
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                logger.warning(
                    "JobManager.update_status: unknown job_id=%s", job_id
                )
                return
            job.status = stage
            job.progress_pct = progress_pct
            job.message = message
            job.updated_at = datetime.now(tz=timezone.utc)

        logger.debug(
            "JobManager: job %s → stage=%s progress=%.1f%%",
            job_id,
            stage.value,
            progress_pct,
        )

    async def complete_job(self, job_id: str, result: LiteratureReview) -> None:
        """Mark a job as completed and store its result.

        Args:
            job_id: UUID string identifying the job.
            result: The finished :class:`~models.paper.LiteratureReview`.
        """
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                logger.warning(
                    "JobManager.complete_job: unknown job_id=%s", job_id
                )
                return
            job.status = Stage.COMPLETED
            job.result = result
            job.progress_pct = 100.0
            job.updated_at = datetime.now(tz=timezone.utc)

        logger.info("JobManager: job %s completed", job_id)

    async def fail_job(self, job_id: str, error: str) -> None:
        """Mark a job as failed and record the error message.

        Args:
            job_id: UUID string identifying the job.
            error: Human-readable description of the failure.
        """
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                logger.warning(
                    "JobManager.fail_job: unknown job_id=%s", job_id
                )
                return
            job.status = Stage.FAILED
            job.error = error
            job.updated_at = datetime.now(tz=timezone.utc)

        logger.error("JobManager: job %s failed — %s", job_id, error)

    async def cancel_job(self, job_id: str) -> None:
        """Mark a job as cancelled.

        Args:
            job_id: UUID string identifying the job.
        """
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                logger.warning(
                    "JobManager.cancel_job: unknown job_id=%s", job_id
                )
                return
            job.status = Stage.CANCELLED
            job.updated_at = datetime.now(tz=timezone.utc)

        logger.info("JobManager: job %s cancelled", job_id)

    # ------------------------------------------------------------------
    # Aggregate queries
    # ------------------------------------------------------------------

    async def get_active_job_count(self) -> int:
        """Return the number of jobs that are currently active.

        A job is considered active if its status is :attr:`Stage.PENDING` or
        any of the 10 processing stages in :data:`~models.job.STAGE_ORDER`.

        Returns:
            Integer count of active jobs.
        """
        async with self._lock:
            return sum(
                1 for job in self._jobs.values() if job.status in _ACTIVE_STAGES
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _review_to_dto(self, review: LiteratureReview) -> LiteratureReviewDTO:
        """Convert a domain :class:`~models.paper.LiteratureReview` to a DTO.

        All nested domain objects (:class:`~models.paper.Paper`,
        :class:`~models.paper.Theme`, :class:`~models.paper.ResearchGap`) are
        mapped to their respective DTO representations.

        Args:
            review: The completed :class:`~models.paper.LiteratureReview`.

        Returns:
            A :class:`~models.api.LiteratureReviewDTO` ready for API
            serialisation.
        """
        papers = [
            PaperDTO(
                paper_id=p.paper_id,
                title=p.title,
                authors=list(p.authors),
                year=p.year,
                journal=p.journal,
                url=p.url,
                source=p.source,
                doi=p.doi,
                micro_summary=p.micro_summary,
                theme_id=p.theme_id,
            )
            for p in review.papers
        ]

        themes = [
            ThemeDTO(
                theme_id=t.theme_id,
                label=t.label,
                description=t.description,
                paper_ids=list(t.paper_ids),
                narrative_summary=t.narrative_summary,
            )
            for t in review.themes
        ]

        research_gaps = [
            ResearchGapDTO(
                gap_type=g.gap_type,
                description=g.description,
                evidence=list(g.evidence),
                suggested_questions=list(g.suggested_questions),
            )
            for g in review.research_gaps
        ]

        return LiteratureReviewDTO(
            review_id=review.review_id,
            topic=review.topic,
            generated_at=review.generated_at,
            papers=papers,
            themes=themes,
            research_gaps=research_gaps,
            introduction=review.introduction,
            executive_summary=review.executive_summary,
            thematic_analysis=review.thematic_analysis,
            comparative_analysis=review.comparative_analysis,
            gaps_section=review.gaps_section,
            conclusion=review.conclusion,
            bibliography=review.bibliography,
            citation_style=review.citation_style,
            paper_count=review.paper_count,
            quality_metrics=dict(review.quality_metrics),
        )
