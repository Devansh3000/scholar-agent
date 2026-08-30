"""Job state models for the literature review pipeline.

This module defines the ``Stage`` enum, the ordered ``STAGE_ORDER`` list,
and the mutable ``Job`` dataclass that tracks a single review pipeline
execution from creation through completion (or failure/cancellation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.api import ReviewConfig
    from models.paper import LiteratureReview


# ---------------------------------------------------------------------------
# Stage enum
# ---------------------------------------------------------------------------


class Stage(str, Enum):
    """All possible pipeline stages for a literature review job.

    The enum inherits from ``str`` so values serialise directly to JSON-safe
    strings (e.g. ``Stage.PENDING == "pending"`` is ``True``).
    """

    PENDING = "pending"
    TOPIC_UNDERSTOOD = "topic_understood"
    PAPERS_FETCHED = "papers_fetched"
    PDFS_RETRIEVED = "pdfs_retrieved"
    SUMMARIES_DONE = "summaries_done"
    THEMES_IDENTIFIED = "themes_identified"
    ANALYSIS_COMPLETE = "analysis_complete"
    GAPS_IDENTIFIED = "gaps_identified"
    REVIEW_WRITTEN = "review_written"
    CITATIONS_FORMATTED = "citations_formatted"
    OUTPUT_GENERATED = "output_generated"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Ordered processing stages (used for progress calculation)
# ---------------------------------------------------------------------------

#: The 10 stages that represent actual pipeline work, in execution order.
#: Each stage accounts for 10 % of the overall ``progress_pct``.
STAGE_ORDER: list[Stage] = [
    Stage.TOPIC_UNDERSTOOD,
    Stage.PAPERS_FETCHED,
    Stage.PDFS_RETRIEVED,
    Stage.SUMMARIES_DONE,
    Stage.THEMES_IDENTIFIED,
    Stage.ANALYSIS_COMPLETE,
    Stage.GAPS_IDENTIFIED,
    Stage.REVIEW_WRITTEN,
    Stage.CITATIONS_FORMATTED,
    Stage.OUTPUT_GENERATED,
]


# ---------------------------------------------------------------------------
# Progress helper
# ---------------------------------------------------------------------------


def compute_progress(completed_stages: list[Stage]) -> float:
    """Return the progress percentage for a set of completed pipeline stages.

    The percentage is calculated as::

        (number_of_completed_stages / 10) * 100

    where 10 is the total number of processing stages in ``STAGE_ORDER``.

    Args:
        completed_stages: A list of :class:`Stage` values that have already
            been completed.  Duplicate entries are counted multiple times, so
            callers should pass a de-duplicated list when that matters.

    Returns:
        A ``float`` in the range ``[0.0, 100.0]``.

    Examples:
        >>> compute_progress([])
        0.0
        >>> compute_progress(STAGE_ORDER[:5])
        50.0
        >>> compute_progress(STAGE_ORDER)
        100.0
    """
    return (len(completed_stages) / 10) * 100


# ---------------------------------------------------------------------------
# Job dataclass
# ---------------------------------------------------------------------------


@dataclass
class Job:
    """Mutable state container for a single literature review pipeline run.

    Instances are created by :class:`~services.job_manager.JobManager` and
    mutated in place as the pipeline progresses through each :class:`Stage`.

    Attributes:
        job_id: Unique identifier for this job (UUID v4 string).
        topic: The research topic submitted by the user.
        config: The :class:`~models.api.ReviewConfig` supplied at creation
            time (max_papers, search_depth, citation_style, include_pdfs).
        status: Current :class:`Stage` of the pipeline.
        created_at: UTC timestamp when the job was created.
        updated_at: UTC timestamp of the most recent status update.
        progress_pct: Percentage of the pipeline complete (0.0–100.0).
        message: Human-readable status message surfaced to the frontend.
        result: The completed :class:`~models.paper.LiteratureReview`, or
            ``None`` while the job is still running.
        error: Error message string when ``status`` is
            :attr:`Stage.FAILED`, otherwise ``None``.
    """

    job_id: str
    topic: str
    config: ReviewConfig
    status: Stage
    created_at: datetime
    updated_at: datetime
    progress_pct: float = field(default=0.0)
    message: str = field(default="")
    result: LiteratureReview | None = field(default=None)
    error: str | None = field(default=None)
