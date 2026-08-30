"""
Gap Identification Agent (Agent 7) for the Literature Review Web Application.

Uses an LLM (via OpenRouter with model fallback) to analyse a collection of
research papers and their thematic clusters, then surfaces 4-8 research gaps
across four categories:
  - methodological
  - empirical
  - theoretical
  - geographical

On any failure the agent logs a WARNING and returns an empty list so the
downstream pipeline can continue without interruption.
"""

from __future__ import annotations

import json
import logging
import re

from models.paper import Paper, ResearchGap, Theme
from services.llm_client import llm_complete

logger = logging.getLogger(__name__)

_MODEL_NAME = "openrouter-fallback"  # symbolic; actual model chosen by llm_client

_PROMPT_TEMPLATE = """\
You are an expert academic researcher. Based on these research papers on "{topic}", identify research gaps.

Return a JSON array of gap objects, each with:
- "gap_type": one of "methodological", "empirical", "theoretical", "geographical"
- "description": clear description of the gap
- "evidence": list of 1-3 paper titles that reveal this gap
- "suggested_questions": list of 1-3 research questions to address this gap

Papers summary:
{papers_context}

Identify 4-8 gaps total. Return only valid JSON array, no markdown.\
"""

_VALID_GAP_TYPES = frozenset({"methodological", "empirical", "theoretical", "geographical"})


def _build_papers_context(papers: list[Paper]) -> str:
    lines: list[str] = []
    for paper in papers:
        summary = paper.micro_summary or (paper.abstract or "")[:300]
        lines.append(f"- {paper.title}: {summary}")
    return "\n".join(lines)


def _strip_code_fences(text: str) -> str:
    stripped = re.sub(r"^```[a-zA-Z]*\n?", "", text.strip())
    stripped = re.sub(r"\n?```$", "", stripped.strip())
    return stripped.strip()


def _parse_gaps(raw: str) -> list[ResearchGap]:
    cleaned = _strip_code_fences(raw)
    data = json.loads(cleaned)

    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array, got {type(data).__name__}")

    gaps: list[ResearchGap] = []
    for item in data:
        gap_type = item.get("gap_type", "")
        if gap_type not in _VALID_GAP_TYPES:
            logger.warning("Skipping gap with unknown gap_type %r", gap_type)
            continue

        gaps.append(
            ResearchGap(
                gap_type=gap_type,  # type: ignore[arg-type]
                description=item.get("description", ""),
                evidence=tuple(item.get("evidence", [])),
                suggested_questions=tuple(item.get("suggested_questions", [])),
            )
        )

    return gaps


async def run_gap_identification(
    papers: list[Paper],
    themes: list[Theme],
    topic: str,
    api_key: str,
) -> list[ResearchGap]:
    """Identify research gaps across the provided papers.

    Parameters
    ----------
    papers:
        The list of :class:`~models.paper.Paper` objects to analyse.
    themes:
        Thematic clusters (used as context).
    topic:
        The original research topic supplied by the user.
    api_key:
        OpenRouter API key.

    Returns
    -------
    list[ResearchGap]
        Between 4 and 8 :class:`~models.paper.ResearchGap` instances.
        Returns an empty list on any error so the pipeline continues.
    """
    if not papers:
        logger.warning("run_gap_identification called with no papers; returning empty list.")
        return []

    papers_context = _build_papers_context(papers)
    prompt = _PROMPT_TEMPLATE.format(topic=topic, papers_context=papers_context)

    try:
        raw_text = await llm_complete(prompt=prompt, api_key=api_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM request failed in gap identification: %s", exc)
        return []

    try:
        gaps = _parse_gaps(raw_text)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to parse gap identification response: %s\nRaw (first 500): %.500s",
            exc,
            raw_text,
        )
        return []

    logger.info(
        "Gap identification complete: topic=%r, papers=%d, gaps_found=%d",
        topic,
        len(papers),
        len(gaps),
    )

    return gaps
