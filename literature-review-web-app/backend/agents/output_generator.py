"""
Output Generator Agent for the Literature Review Web Application.

Assembles the final :class:`~models.paper.LiteratureReview` dataclass from
all upstream agent outputs and, optionally, renders it to a PDF document via
:func:`~tools.pdf_generator.generate_pdf`.

If PDF generation fails for any reason (missing dependency, filesystem error,
etc.) the agent logs a warning and returns the review with ``pdf_path=None``
so the caller can fall back to Markdown-only output.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from models.paper import LiteratureReview, Paper, ResearchGap, Theme
from tools.pdf_generator import generate_pdf

if TYPE_CHECKING:
    from agents.review_writer import ReviewSections

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public agent entry-point
# ---------------------------------------------------------------------------


async def run_output_generator(
    topic: str,
    papers: list[Paper],
    themes: list[Theme],
    research_gaps: list[ResearchGap],
    review_sections: "ReviewSections",
    bibliography: str,
    citation_style: Literal["APA", "Harvard", "IEEE"],
    output_dir: str = "/tmp/reviews",
) -> LiteratureReview:
    """Assemble a :class:`~models.paper.LiteratureReview` and generate a PDF.

    Parameters
    ----------
    topic:
        The research topic of the literature review.
    papers:
        All papers collected and processed by earlier pipeline agents.
    themes:
        Thematic clusters produced by the clustering agent.
    research_gaps:
        Research gaps identified by the gap-identification agent.
    review_sections:
        Structured narrative sections produced by the review-writer agent.
    bibliography:
        Formatted bibliography string (may contain multiple entries separated
        by ``\\n\\n``).
    citation_style:
        One of ``"APA"``, ``"Harvard"``, or ``"IEEE"``.
    output_dir:
        Directory where the generated PDF will be stored.  Defaults to
        ``/tmp/reviews``.

    Returns
    -------
    LiteratureReview
        The assembled review, with ``pdf_path`` set if PDF generation
        succeeded, or ``None`` if it failed.
    """
    # ------------------------------------------------------------------
    # 1. Build quality metrics
    # ------------------------------------------------------------------
    unique_sources: list[str] = list({paper.source for paper in papers})
    quality_metrics: dict = {
        "paper_count": len(papers),
        "theme_count": len(themes),
        "gap_count": len(research_gaps),
        "sources": unique_sources,
    }

    # ------------------------------------------------------------------
    # 2. Assemble the LiteratureReview dataclass
    # ------------------------------------------------------------------
    review = LiteratureReview(
        review_id=str(uuid4()),
        topic=topic,
        generated_at=datetime.utcnow(),
        papers=tuple(papers),
        themes=tuple(themes),
        research_gaps=tuple(research_gaps),
        introduction=review_sections.introduction,
        thematic_analysis=review_sections.thematic_analysis,
        comparative_analysis=review_sections.comparative_analysis,
        gaps_section=review_sections.gaps_section,
        conclusion=review_sections.conclusion,
        executive_summary=review_sections.executive_summary,
        bibliography=bibliography,
        citation_style=citation_style,
        paper_count=len(papers),
        quality_metrics=quality_metrics,
    )

    # ------------------------------------------------------------------
    # 3. Attempt PDF generation (non-fatal on failure)
    # ------------------------------------------------------------------
    output_path = f"{output_dir}/{review.review_id}.pdf"
    try:
        pdf_path: str = await asyncio.get_event_loop().run_in_executor(
            None, generate_pdf, review, output_path
        )
        review = dataclasses.replace(review, pdf_path=pdf_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "PDF generation failed for review %s — returning Markdown-only output. "
            "Reason: %s",
            review.review_id,
            exc,
        )

    # ------------------------------------------------------------------
    # 4. Structured log for observability
    # ------------------------------------------------------------------
    logger.info(
        "Output generator complete: review_id=%s paper_count=%d theme_count=%d",
        review.review_id,
        len(papers),
        len(themes),
    )

    return review


__all__ = ["run_output_generator"]
