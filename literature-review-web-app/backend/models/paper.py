"""
Domain models for the Literature Review Web Application.

All models are frozen dataclasses (immutable) to enforce agent isolation —
agents receive data and return new data without mutating shared objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass(frozen=True)
class Paper:
    """Represents a single academic paper retrieved from an external source."""

    paper_id: str
    """Unique identifier — UUID or source-provided ID."""

    title: str
    authors: list[str]
    year: int
    journal: str
    abstract: str
    url: str
    source: Literal["arxiv", "semantic_scholar", "ieee", "google_scholar"]

    doi: str | None = None
    score: float = 0.0
    full_text: str | None = None
    sections: dict[str, str] = field(default_factory=dict)
    micro_summary: str | None = None
    long_summary: str | None = None
    methodology: str | None = None
    findings: str | None = None
    contributions: str | None = None
    limitations: str | None = None
    relevance_notes: str | None = None
    embedding: list[float] | None = None
    theme_id: int | None = None


@dataclass(frozen=True)
class Theme:
    """A thematic cluster of related papers identified by the clustering agent."""

    theme_id: int
    label: str
    description: str
    paper_ids: frozenset[str]

    comparison_matrix: dict | None = None
    narrative_summary: str | None = None
    common_limitations: tuple[str, ...] = ()
    best_practices: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResearchGap:
    """A gap in the literature identified by the gap-identification agent."""

    gap_type: Literal["methodological", "empirical", "theoretical", "geographical"]
    description: str
    evidence: tuple[str, ...]
    suggested_questions: tuple[str, ...]


@dataclass(frozen=True)
class LiteratureReview:
    """The complete output of a literature review pipeline run."""

    review_id: str
    topic: str
    generated_at: datetime

    papers: tuple[Paper, ...]
    themes: tuple[Theme, ...]
    research_gaps: tuple[ResearchGap, ...]

    introduction: str
    thematic_analysis: str
    comparative_analysis: str
    gaps_section: str
    conclusion: str
    executive_summary: str
    bibliography: str

    citation_style: Literal["APA", "Harvard", "IEEE"]
    paper_count: int
    quality_metrics: dict[str, Any]

    pdf_path: str | None = None
