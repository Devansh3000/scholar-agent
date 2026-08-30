"""
Comparative Analysis Agent (Agent 6) for the Literature Review Web Application.

Uses an LLM (via OpenRouter with model fallback) to generate a per-theme
comparative analysis of research papers, identifying cross-theme methodological
patterns, contradictions, common trends, and a comparison matrix summary.

On any failure a WARNING is logged and an empty string is returned so the
pipeline can continue without this section.
"""

from __future__ import annotations

import logging

from models.paper import Paper, Theme
from services.llm_client import llm_complete

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
You are an expert academic researcher performing a comparative analysis.

Analyze the following thematic groups of research papers and produce:
1. A comparison of methodologies across themes
2. Identification of contradictions or conflicting findings
3. Common patterns and trends
4. A comparison matrix summary

Themes and papers:
{themes_context}

Write 3-5 paragraphs of comparative analysis in academic style.\
"""


def _build_themes_context(papers: list[Paper], themes: list[Theme]) -> str:
    paper_map: dict[str, Paper] = {p.paper_id: p for p in papers}

    lines: list[str] = []
    for theme in themes:
        lines.append(f"Theme {theme.theme_id}: {theme.label}")
        if theme.description:
            lines.append(f"  Description: {theme.description}")

        for paper_id in sorted(theme.paper_ids):
            paper = paper_map.get(paper_id)
            if paper is None:
                continue
            lines.append(f"  - {paper.title} ({paper.year})")
            if paper.methodology:
                lines.append(f"      Methodology: {paper.methodology}")
            if paper.findings:
                lines.append(f"      Findings: {paper.findings}")

        lines.append("")

    return "\n".join(lines).strip()


async def run_comparative_analysis(
    papers: list[Paper],
    themes: list[Theme],
    api_key: str,
) -> str:
    """Generate a comparative analysis across thematic groups.

    Parameters
    ----------
    papers:
        All papers processed by the pipeline.
    themes:
        Thematic clusters produced by the clustering agent.
    api_key:
        OpenRouter API key.

    Returns
    -------
    str
        3–5 paragraphs of comparative analysis, or empty string on failure.
    """
    logger.info(
        "Comparative analysis agent starting — %d papers across %d themes.",
        len(papers),
        len(themes),
    )

    themes_context = _build_themes_context(papers, themes)
    prompt = _PROMPT_TEMPLATE.format(themes_context=themes_context)

    try:
        analysis = await llm_complete(prompt=prompt, api_key=api_key)
        logger.info("Comparative analysis complete (%d characters).", len(analysis))
        return analysis
    except Exception as exc:  # noqa: BLE001
        logger.warning("Comparative analysis failed: %s", exc)
        return ""
