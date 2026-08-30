"""
API request/response Pydantic models for the Literature Review Web Application.

These models are the serialization boundary between the FastAPI layer and the
outside world.  All domain objects (frozen dataclasses from ``paper.py`` and
``job.py``) are converted to the DTO types defined here before being sent to
clients, so internal implementation details never leak through the API surface.

Model hierarchy
---------------
Requests
    CreateReviewRequest  →  carries ReviewConfig
Responses (success)
    CreateReviewResponse
    JobStatusResponse
    JobResultResponse    →  carries LiteratureReviewDTO
                                which carries PaperDTO / ThemeDTO / ResearchGapDTO
Responses (error)
    ErrorResponse
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class ReviewConfig(BaseModel):
    """User-supplied configuration for a single literature review run."""

    max_papers: int = Field(
        default=20,
        ge=5,
        le=50,
        description="Maximum number of papers to retrieve and analyse (5–50).",
    )
    search_depth: Literal["shallow", "medium", "deep"] = Field(
        default="medium",
        description=(
            "Controls how many academic sources are queried and how many "
            "result pages are fetched per source."
        ),
    )
    citation_style: Literal["APA", "Harvard", "IEEE"] = Field(
        default="APA",
        description="Bibliographic citation style used in the generated review.",
    )
    include_pdfs: bool = Field(
        default=True,
        description="When True, the pipeline attempts to retrieve full-text PDFs.",
    )


class CreateReviewRequest(BaseModel):
    """Payload for ``POST /api/literature-review``."""

    topic: str = Field(
        min_length=5,
        max_length=500,
        description="Research topic or question to review (5–500 characters).",
    )
    config: ReviewConfig = Field(
        default_factory=ReviewConfig,
        description="Optional review configuration; defaults applied when omitted.",
    )


# ---------------------------------------------------------------------------
# Response models — job lifecycle
# ---------------------------------------------------------------------------


class CreateReviewResponse(BaseModel):
    """Returned by ``POST /api/literature-review`` (HTTP 202 Accepted)."""

    job_id: str = Field(description="UUID that uniquely identifies this review job.")
    estimated_seconds: int = Field(
        default=600,
        description="Server-side estimate of how long the pipeline will take.",
    )


class JobStatusResponse(BaseModel):
    """Returned by ``GET /api/literature-review/{job_id}/status``."""

    job_id: str = Field(description="UUID of the review job.")
    status: str = Field(
        description=(
            "High-level lifecycle state: "
            "``pending`` | ``running`` | ``completed`` | ``failed`` | ``cancelled``."
        ),
    )
    stage: str = Field(
        description=(
            "Current pipeline stage name, e.g. ``papers_fetched``. "
            "Maps to ``Stage`` enum values in ``job.py``."
        ),
    )
    progress_pct: float = Field(
        description="Completion percentage in the range [0.0, 100.0].",
    )
    message: str = Field(description="Human-readable status message.")
    elapsed_seconds: float = Field(
        description="Seconds elapsed since the job was created.",
    )
    estimated_remaining_seconds: float | None = Field(
        default=None,
        description=(
            "Seconds until estimated completion, or ``null`` when unknown "
            "(e.g. job not yet started or already finished)."
        ),
    )


# ---------------------------------------------------------------------------
# DTO models — serializable versions of domain objects
# ---------------------------------------------------------------------------


class ThemeDTO(BaseModel):
    """Serializable representation of ``paper.Theme`` for API responses."""

    theme_id: int = Field(description="Numeric cluster identifier.")
    label: str = Field(description="Short human-readable label for the theme.")
    description: str = Field(description="Paragraph describing the theme.")
    paper_ids: list[str] = Field(
        description="IDs of all papers assigned to this theme.",
    )
    narrative_summary: str | None = Field(
        default=None,
        description="Agent-generated narrative summarising this theme, if available.",
    )


class ResearchGapDTO(BaseModel):
    """Serializable representation of ``paper.ResearchGap`` for API responses."""

    gap_type: str = Field(
        description=(
            "Category of the gap: "
            "``methodological`` | ``empirical`` | ``theoretical`` | ``geographical``."
        ),
    )
    description: str = Field(description="Explanation of the identified gap.")
    evidence: list[str] = Field(
        description="Quotes or paper references that support the existence of this gap.",
    )
    suggested_questions: list[str] = Field(
        description="Research questions that would address this gap.",
    )


class PaperDTO(BaseModel):
    """Lightweight paper summary included in API responses.

    Omits heavy fields (``abstract``, ``full_text``, ``embedding``, etc.) that
    are only needed internally by the pipeline agents.
    """

    paper_id: str = Field(description="Unique identifier (UUID or source-provided).")
    title: str = Field(description="Full paper title.")
    authors: list[str] = Field(description="Ordered list of author names.")
    year: int = Field(description="Publication year.")
    journal: str = Field(description="Journal, conference, or repository name.")
    url: str = Field(description="Canonical URL or DOI link for the paper.")
    source: str = Field(
        description=(
            "Academic source that provided the paper: "
            "``arxiv`` | ``semantic_scholar`` | ``ieee`` | ``google_scholar``."
        ),
    )
    doi: str | None = Field(
        default=None,
        description="Digital Object Identifier for the paper, if available.",
    )
    micro_summary: str | None = Field(
        default=None,
        description="One-sentence summary produced by the summarisation agent.",
    )
    theme_id: int | None = Field(
        default=None,
        description="ID of the theme cluster this paper belongs to, if assigned.",
    )


class LiteratureReviewDTO(BaseModel):
    """Serializable representation of a completed ``paper.LiteratureReview``.

    This is the primary result payload returned to the client.  All nested
    domain objects are replaced with their DTO equivalents.
    """

    review_id: str = Field(description="UUID identifying this review.")
    topic: str = Field(description="Research topic submitted by the user.")
    generated_at: datetime = Field(
        description="UTC timestamp when the review was finalised.",
    )

    papers: list[PaperDTO] = Field(
        description="All papers included in this review.",
    )
    themes: list[ThemeDTO] = Field(
        description="Thematic clusters identified across the paper set.",
    )
    research_gaps: list[ResearchGapDTO] = Field(
        description="Gaps in the literature identified by the pipeline.",
    )

    # Review text sections (Markdown)
    introduction: str = Field(description="Introduction section of the review.")
    executive_summary: str = Field(
        description="High-level executive summary of the entire review.",
    )
    thematic_analysis: str = Field(
        description="Per-theme analysis section.",
    )
    comparative_analysis: str = Field(
        description="Cross-paper comparative analysis section.",
    )
    gaps_section: str = Field(
        description="Narrative section describing identified research gaps.",
    )
    conclusion: str = Field(description="Conclusion section of the review.")
    bibliography: str = Field(
        description="Formatted bibliography in the requested citation style.",
    )

    citation_style: str = Field(
        description="Citation style used throughout the review (APA / Harvard / IEEE).",
    )
    paper_count: int = Field(
        description="Number of papers included in the review.",
    )
    quality_metrics: dict[str, Any] = Field(
        description=(
            "Computed quality indicators (e.g. source diversity, coverage score). "
            "Keys and value types are pipeline-defined."
        ),
    )


# ---------------------------------------------------------------------------
# Response models — result and error
# ---------------------------------------------------------------------------


class JobResultResponse(BaseModel):
    """Returned by ``GET /api/literature-review/{job_id}/result`` (HTTP 200)."""

    job_id: str = Field(description="UUID of the completed review job.")
    review: LiteratureReviewDTO = Field(
        description="The completed literature review.",
    )
    completed_at: datetime = Field(
        description="UTC timestamp when the job reached ``completed`` status.",
    )


class ErrorResponse(BaseModel):
    """Standard error envelope returned for all non-2xx responses."""

    error: str = Field(description="Human-readable error message.")
    correlation_id: str = Field(
        description=(
            "UUID that links this error to a specific request in the server logs. "
            "Include this in any bug report."
        ),
    )
    status_code: int = Field(description="HTTP status code for this error.")
