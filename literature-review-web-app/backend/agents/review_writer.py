"""
Review Writer Agent (Agent 8) for the Literature Review Web Application.

Uses an LLM (via OpenRouter with model fallback) to write all sections of a
literature review in a single API call.  The agent accepts structured inputs
(papers, themes, research gaps, and a pre-computed comparative analysis) and
returns a :class:`ReviewSections` dataclass containing every narrative section
of the final report.

If the LLM call or JSON parsing fails the agent raises a :exc:`RuntimeError`,
aborting the pipeline so the caller can handle the failure gracefully.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re

from models.paper import Paper, ResearchGap, Theme
from services.llm_client import llm_complete

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class ReviewSections:
    """All narrative sections produced by the review writer."""

    introduction: str
    thematic_analysis: str
    comparative_analysis: str
    gaps_section: str
    conclusion: str
    executive_summary: str


async def run_review_writer(
    topic: str,
    papers: list[Paper],
    themes: list[Theme],
    research_gaps: list[ResearchGap],
    comparative_analysis_text: str,
    api_key: str,
) -> ReviewSections:
    """Write all sections of a literature review using an LLM.

    Parameters
    ----------
    topic:
        The research topic of the literature review.
    papers:
        All :class:`~models.paper.Paper` objects available for the review.
    themes:
        Thematic clusters produced by the clustering agent.
    research_gaps:
        Research gaps identified by the gap-identification agent.
    comparative_analysis_text:
        Pre-computed comparative analysis summary (plain text).
    api_key:
        OpenRouter API key.

    Returns
    -------
    ReviewSections
        A dataclass containing each narrative section of the literature review.

    Raises
    ------
    RuntimeError
        If all fallback models fail or JSON parsing fails.  This aborts the pipeline.
    """
    paper_lookup: dict[str, Paper] = {p.paper_id: p for p in papers}

    theme_blocks: list[str] = []
    for theme in themes:
        paper_snippets: list[str] = []
        for pid in theme.paper_ids:
            paper = paper_lookup.get(pid)
            if paper is None:
                continue
            body = paper.long_summary or paper.abstract or ""
            paper_snippets.append(f"  - {paper.title}: {body[:300]}")
        block = (
            f"Theme: {theme.label}\n"
            f"Description: {theme.description}\n"
            + "\n".join(paper_snippets)
        )
        theme_blocks.append(block)

    themes_papers_context = "\n\n".join(theme_blocks) if theme_blocks else "(no themes)"

    gaps_lines: list[str] = [
        f"- [{gap.gap_type}] {gap.description}" for gap in research_gaps
    ]
    gaps_context = "\n".join(gaps_lines) if gaps_lines else "(no gaps identified)"

    prompt = (
        f'You are an expert academic writer. Write a comprehensive literature review on "{topic}".\n\n'
        f"Use these papers organized by theme:\n{themes_papers_context}\n\n"
        f"Research gaps identified:\n{gaps_context}\n\n"
        f"Comparative analysis summary:\n{comparative_analysis_text}\n\n"
        "Return a JSON object with these sections:\n"
        '- "executive_summary": 200-word executive summary\n'
        '- "introduction": 300-word introduction with background and scope\n'
        '- "thematic_analysis": 500-word analysis organized by themes\n'
        '- "gaps_section": 200-word section on research gaps\n'
        '- "conclusion": 200-word conclusion with future directions\n\n'
        "Write in formal academic style. Return only valid JSON, no markdown."
    )

    logger.info("Sending review-writing prompt via OpenRouter (with fallback).")

    try:
        raw_text = await llm_complete(prompt=prompt, api_key=api_key)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Review writing failed: {exc}") from exc

    cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())

    try:
        data: dict = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Review writing failed — JSON parse error: {exc}") from exc

    logger.info("Review sections successfully parsed from LLM response.")

    return ReviewSections(
        introduction=data.get("introduction", ""),
        thematic_analysis=data.get("thematic_analysis", ""),
        comparative_analysis=comparative_analysis_text,
        gaps_section=data.get("gaps_section", ""),
        conclusion=data.get("conclusion", ""),
        executive_summary=data.get("executive_summary", ""),
    )
