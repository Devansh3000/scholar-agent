"""
Orchestrator for the Literature Review Web Application.

This module implements the master coordinator that runs all 10 pipeline agents
in sequence, updating job progress after each stage and applying the
per-agent error-handling strategy defined in the design document.

Pipeline order
--------------
1.  Topic Understanding    → abort on failure
2.  Paper Search           → abort if zero papers; continue if ≥1 paper
3.  PDF Retrieval          → skip on failure (abstract-only is fine)
4.  Summarization          → skip on failure (use unsummarized papers)
5.  Thematic Clustering    → fallback to single theme on failure
6.  Comparative Analysis   → omit section on failure, continue
7.  Gap Identification     → omit section on failure, continue
8.  Review Writer          → abort on failure
9.  Citation Formatter     → use placeholder on failure
10. Output Generator       → log error, return partial review without PDF

Usage::

    from agents.orchestrator import run_pipeline
    review = await run_pipeline(job_id, topic, config, settings, cache, job_manager)
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from config.settings import Settings
from models.api import ReviewConfig
from models.job import Stage, compute_progress
from models.paper import LiteratureReview, Paper, ResearchGap, Theme

if TYPE_CHECKING:
    from services.cache_service import CacheService
    from services.job_manager import JobManager

# Agent imports
from agents.topic_understanding import run_topic_understanding
from agents.paper_search import run_paper_search
from agents.pdf_retrieval import run_pdf_retrieval
from agents.summarization import run_summarization
from agents.thematic_clustering import run_thematic_clustering
from agents.comparative_analysis import run_comparative_analysis
from agents.gap_identification import run_gap_identification
from agents.review_writer import run_review_writer, ReviewSections
from agents.citation_formatter import run_citation_formatter_with_fallback
from agents.output_generator import run_output_generator

logger = logging.getLogger(__name__)


async def run_pipeline(
    job_id: str,
    topic: str,
    config: ReviewConfig,
    settings: Settings,
    cache: "CacheService | None",
    job_manager: "JobManager",
) -> LiteratureReview:
    """Run all 10 pipeline agents in sequence and return the completed review.

    Each agent is called in order (1 → 10). After every agent completes
    (or is skipped due to a non-fatal failure), the job status is updated
    via ``job_manager.update_status`` using the appropriate :class:`Stage`
    value and a progress percentage computed from the set of completed stages.

    Parameters
    ----------
    job_id:
        UUID string identifying the current job in the :class:`JobManager`.
    topic:
        The research topic submitted by the user.
    config:
        :class:`~models.api.ReviewConfig` carrying max_papers, citation_style,
        include_pdfs, and search_depth.
    settings:
        Application :class:`~config.settings.Settings` instance supplying
        API keys and service URLs.
    cache:
        Optional :class:`~services.cache_service.CacheService` for read-through
        caching within the search and embedding agents.  ``None`` disables
        caching.
    job_manager:
        :class:`~services.job_manager.JobManager` instance used to persist
        and broadcast stage progress to polling clients.

    Returns
    -------
    LiteratureReview
        The fully assembled review.  On non-fatal agent failures some fields
        may be empty strings or ``pdf_path`` may be ``None``.

    Raises
    ------
    RuntimeError
        Raised when a *critical* agent fails and the pipeline cannot produce
        meaningful output:

        * Agent 1 (topic_understanding) — no search queries to proceed with.
        * Agent 2 (paper_search) — zero papers returned across all sources.
        * Agent 8 (review_writer) — no review text to include in the output.
    """
    logger.info(
        "Orchestrator starting pipeline. job_id=%s topic=%r max_papers=%d",
        job_id,
        topic,
        config.max_papers,
    )

    # Tracks which stages have been completed; used by compute_progress().
    completed_stages: list[Stage] = []

    # Resolve the LLM API key: prefer OpenRouter, fall back to Google key
    llm_api_key: str = settings.OPENROUTER_API_KEY or settings.GOOGLE_API_KEY

    # -----------------------------------------------------------------------
    # Agent 1 — Topic Understanding
    # -----------------------------------------------------------------------
    logger.info("Agent 1: Topic Understanding — job_id=%s", job_id)
    try:
        topic_result = await run_topic_understanding(
            topic=topic,
            api_key=llm_api_key,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Agent 1 (topic_understanding) failed — aborting pipeline. "
            "job_id=%s error=%s",
            job_id,
            exc,
        )
        raise RuntimeError(
            f"Pipeline aborted: topic understanding failed — {exc}"
        ) from exc

    completed_stages.append(Stage.TOPIC_UNDERSTOOD)
    await job_manager.update_status(
        job_id,
        Stage.TOPIC_UNDERSTOOD,
        compute_progress(completed_stages),
        f"Topic analyzed: {len(topic_result.search_queries)} search queries generated.",
    )
    logger.info(
        "Agent 1 complete. job_id=%s queries=%d",
        job_id,
        len(topic_result.search_queries),
    )

    # -----------------------------------------------------------------------
    # Agent 2 — Paper Search
    # -----------------------------------------------------------------------
    logger.info("Agent 2: Paper Search — job_id=%s", job_id)
    papers: list[Paper]
    try:
        papers = await asyncio.wait_for(
            run_paper_search(
                search_queries=topic_result.search_queries,
                max_papers=config.max_papers,
                cache=cache,
                settings=settings,
            ),
            timeout=90.0,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Agent 2 (paper_search) timed out after 90s — aborting. job_id=%s",
            job_id,
        )
        raise RuntimeError(
            "Pipeline aborted: paper search timed out. "
            "External academic APIs are not responding. Please try again."
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Agent 2 (paper_search) raised an unexpected error — aborting. "
            "job_id=%s error=%s",
            job_id,
            exc,
        )
        raise RuntimeError(
            f"Pipeline aborted: paper search failed — {exc}"
        ) from exc

    if not papers:
        logger.error(
            "Agent 2 (paper_search) returned zero papers — aborting. job_id=%s",
            job_id,
        )
        raise RuntimeError(
            "Pipeline aborted: paper search returned zero results. "
            "Try broadening the topic or adjusting the search depth."
        )

    completed_stages.append(Stage.PAPERS_FETCHED)
    await job_manager.update_status(
        job_id,
        Stage.PAPERS_FETCHED,
        compute_progress(completed_stages),
        f"Found {len(papers)} papers across academic sources.",
    )
    logger.info("Agent 2 complete. job_id=%s papers=%d", job_id, len(papers))

    # -----------------------------------------------------------------------
    # Agent 3 — PDF Retrieval  (non-fatal: skip on failure)
    # -----------------------------------------------------------------------
    logger.info("Agent 3: PDF Retrieval — job_id=%s", job_id)
    try:
        papers = await run_pdf_retrieval(
            papers=papers,
            cache=cache,
            include_pdfs=config.include_pdfs,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Agent 3 (pdf_retrieval) failed — continuing with abstract-only papers. "
            "job_id=%s error=%s",
            job_id,
            exc,
        )

    pdfs_retrieved = sum(1 for p in papers if p.full_text is not None)
    completed_stages.append(Stage.PDFS_RETRIEVED)
    await job_manager.update_status(
        job_id,
        Stage.PDFS_RETRIEVED,
        compute_progress(completed_stages),
        f"Retrieved {pdfs_retrieved} full-text PDFs "
        f"({len(papers) - pdfs_retrieved} abstract-only).",
    )
    logger.info(
        "Agent 3 complete. job_id=%s pdfs=%d abstract_only=%d",
        job_id,
        pdfs_retrieved,
        len(papers) - pdfs_retrieved,
    )

    # -----------------------------------------------------------------------
    # Agent 4 — Summarization  (non-fatal: skip on failure)
    # -----------------------------------------------------------------------
    logger.info("Agent 4: Summarization — job_id=%s", job_id)
    try:
        papers = await run_summarization(
            papers=papers,
            api_key=llm_api_key,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Agent 4 (summarization) failed — continuing with unsummarized papers. "
            "job_id=%s error=%s",
            job_id,
            exc,
        )

    summarized = sum(1 for p in papers if p.micro_summary is not None)
    completed_stages.append(Stage.SUMMARIES_DONE)
    await job_manager.update_status(
        job_id,
        Stage.SUMMARIES_DONE,
        compute_progress(completed_stages),
        f"Summarized {summarized} of {len(papers)} papers.",
    )
    logger.info(
        "Agent 4 complete. job_id=%s summarized=%d", job_id, summarized
    )

    # -----------------------------------------------------------------------
    # Agent 5 — Thematic Clustering  (non-fatal: fallback to single theme)
    # -----------------------------------------------------------------------
    logger.info("Agent 5: Thematic Clustering — job_id=%s", job_id)
    themes: list[Theme]
    try:
        papers, themes = await run_thematic_clustering(
            papers=papers,
            api_key=llm_api_key,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Agent 5 (thematic_clustering) failed — falling back to single theme. "
            "job_id=%s error=%s",
            job_id,
            exc,
        )
        themes = [
            Theme(
                theme_id=0,
                label="General",
                description="All papers (clustering unavailable)",
                paper_ids=frozenset(p.paper_id for p in papers),
            )
        ]

    completed_stages.append(Stage.THEMES_IDENTIFIED)
    await job_manager.update_status(
        job_id,
        Stage.THEMES_IDENTIFIED,
        compute_progress(completed_stages),
        f"Identified {len(themes)} thematic cluster(s).",
    )
    logger.info(
        "Agent 5 complete. job_id=%s themes=%d", job_id, len(themes)
    )

    # -----------------------------------------------------------------------
    # Agent 6 — Comparative Analysis  (non-fatal: omit section on failure)
    # -----------------------------------------------------------------------
    logger.info("Agent 6: Comparative Analysis — job_id=%s", job_id)
    comparative_text: str = ""
    try:
        comparative_text = await run_comparative_analysis(
            papers=papers,
            themes=themes,
            api_key=llm_api_key,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Agent 6 (comparative_analysis) failed — omitting section. "
            "job_id=%s error=%s",
            job_id,
            exc,
        )

    completed_stages.append(Stage.ANALYSIS_COMPLETE)
    await job_manager.update_status(
        job_id,
        Stage.ANALYSIS_COMPLETE,
        compute_progress(completed_stages),
        "Comparative analysis complete."
        if comparative_text
        else "Comparative analysis skipped (agent failure).",
    )
    logger.info(
        "Agent 6 complete. job_id=%s chars=%d", job_id, len(comparative_text)
    )

    # -----------------------------------------------------------------------
    # Agent 7 — Gap Identification  (non-fatal: omit section on failure)
    # -----------------------------------------------------------------------
    logger.info("Agent 7: Gap Identification — job_id=%s", job_id)
    gaps: list[ResearchGap] = []
    try:
        gaps = await run_gap_identification(
            papers=papers,
            themes=themes,
            topic=topic,
            api_key=llm_api_key,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Agent 7 (gap_identification) failed — omitting gaps section. "
            "job_id=%s error=%s",
            job_id,
            exc,
        )

    completed_stages.append(Stage.GAPS_IDENTIFIED)
    await job_manager.update_status(
        job_id,
        Stage.GAPS_IDENTIFIED,
        compute_progress(completed_stages),
        f"Identified {len(gaps)} research gap(s)."
        if gaps
        else "Gap identification skipped or returned no results.",
    )
    logger.info(
        "Agent 7 complete. job_id=%s gaps=%d", job_id, len(gaps)
    )

    # -----------------------------------------------------------------------
    # Agent 8 — Review Writer  (critical: abort on failure)
    # -----------------------------------------------------------------------
    logger.info("Agent 8: Review Writer — job_id=%s", job_id)
    sections: ReviewSections
    try:
        sections = await run_review_writer(
            topic=topic,
            papers=papers,
            themes=themes,
            research_gaps=gaps,
            comparative_analysis_text=comparative_text,
            api_key=llm_api_key,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Agent 8 (review_writer) failed — aborting pipeline. "
            "job_id=%s error=%s",
            job_id,
            exc,
        )
        raise RuntimeError(
            f"Pipeline aborted: review writing failed — {exc}"
        ) from exc

    completed_stages.append(Stage.REVIEW_WRITTEN)
    await job_manager.update_status(
        job_id,
        Stage.REVIEW_WRITTEN,
        compute_progress(completed_stages),
        "Literature review sections written.",
    )
    logger.info("Agent 8 complete. job_id=%s", job_id)

    # -----------------------------------------------------------------------
    # Agent 9 — Citation Formatter  (non-fatal: use placeholder on failure)
    # -----------------------------------------------------------------------
    logger.info("Agent 9: Citation Formatter — job_id=%s", job_id)
    bibliography: str
    try:
        bibliography = await run_citation_formatter_with_fallback(
            papers=papers,
            style=config.citation_style,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Agent 9 (citation_formatter) failed — using placeholder bibliography. "
            "job_id=%s error=%s",
            job_id,
            exc,
        )
        bibliography = f"[{len(papers)} references — citation formatting unavailable]"

    completed_stages.append(Stage.CITATIONS_FORMATTED)
    await job_manager.update_status(
        job_id,
        Stage.CITATIONS_FORMATTED,
        compute_progress(completed_stages),
        f"Formatted {len(papers)} citation(s) in {config.citation_style} style.",
    )
    logger.info("Agent 9 complete. job_id=%s style=%s", job_id, config.citation_style)

    # -----------------------------------------------------------------------
    # Agent 10 — Output Generator  (non-fatal: log error, return partial review)
    # -----------------------------------------------------------------------
    logger.info("Agent 10: Output Generator — job_id=%s", job_id)
    review: LiteratureReview
    try:
        review = await run_output_generator(
            topic=topic,
            papers=papers,
            themes=themes,
            research_gaps=gaps,
            review_sections=sections,
            bibliography=bibliography,
            citation_style=config.citation_style,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Agent 10 (output_generator) failed — returning partial review without PDF. "
            "job_id=%s error=%s",
            job_id,
            exc,
        )
        # Build a minimal LiteratureReview from what we have so the job can
        # still complete rather than leaving the client with no output at all.
        from datetime import datetime
        from uuid import uuid4

        review = LiteratureReview(
            review_id=str(uuid4()),
            topic=topic,
            generated_at=datetime.utcnow(),
            papers=tuple(papers),
            themes=tuple(themes),
            research_gaps=tuple(gaps),
            introduction=sections.introduction,
            thematic_analysis=sections.thematic_analysis,
            comparative_analysis=sections.comparative_analysis,
            gaps_section=sections.gaps_section,
            conclusion=sections.conclusion,
            executive_summary=sections.executive_summary,
            bibliography=bibliography,
            citation_style=config.citation_style,
            paper_count=len(papers),
            quality_metrics={
                "paper_count": len(papers),
                "theme_count": len(themes),
                "gap_count": len(gaps),
                "sources": list({p.source for p in papers}),
            },
            pdf_path=None,
        )

    completed_stages.append(Stage.OUTPUT_GENERATED)
    await job_manager.update_status(
        job_id,
        Stage.OUTPUT_GENERATED,
        compute_progress(completed_stages),
        "Literature review generated successfully."
        if review.pdf_path is not None
        else "Literature review generated (PDF unavailable).",
    )
    logger.info(
        "Agent 10 complete. job_id=%s review_id=%s pdf=%s",
        job_id,
        review.review_id,
        review.pdf_path,
    )

    logger.info(
        "Orchestrator pipeline complete. job_id=%s review_id=%s papers=%d themes=%d gaps=%d",
        job_id,
        review.review_id,
        len(papers),
        len(themes),
        len(gaps),
    )

    return review


__all__ = ["run_pipeline"]
