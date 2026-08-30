"""
Summarization Agent (Agent 4).

Uses an LLM (via OpenRouter with model fallback) to generate structured
summaries for a list of academic papers concurrently.  Each paper receives:

    - micro_summary  : a ~20-word headline summary
    - long_summary   : a ~150-word comprehensive summary
    - methodology    : research methodology used
    - findings       : key findings and results
    - contributions  : main contributions to the field
    - limitations    : acknowledged limitations
    - relevance_notes: relevance to academic research

Up to 5 LLM calls are made concurrently (governed by an asyncio.Semaphore).
If summarisation fails for any individual paper, a WARNING is logged and the
original Paper object is returned unchanged so the pipeline can continue.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import re

from models.paper import Paper
from services.llm_client import llm_complete

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """\
Analyze this academic paper and return a JSON object with:
- "micro_summary": exactly 20 words summarizing the paper
- "long_summary": 150-word comprehensive summary
- "methodology": the research methodology used
- "findings": key findings and results
- "contributions": main contributions to the field
- "limitations": acknowledged limitations
- "relevance_notes": relevance to academic research

Paper title: {title}
Authors: {authors}
Abstract: {abstract}

Return only valid JSON, no markdown.\
"""

_EXPECTED_FIELDS: tuple[str, ...] = (
    "micro_summary",
    "long_summary",
    "methodology",
    "findings",
    "contributions",
    "limitations",
    "relevance_notes",
)

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _strip_code_fences(text: str) -> str:
    match = _CODE_FENCE_RE.search(text)
    return match.group(1) if match else text.strip()


def _build_prompt(paper: Paper) -> str:
    authors_str = ", ".join(paper.authors[:5]) if paper.authors else "Unknown"
    abstract_str = (paper.abstract or "")[:2000]
    return _PROMPT_TEMPLATE.format(
        title=paper.title,
        authors=authors_str,
        abstract=abstract_str,
    )


async def run_summarization(papers: list[Paper], api_key: str) -> list[Paper]:
    """Summarise *papers* concurrently using OpenRouter LLM with fallback.

    Args:
        papers:  List of :class:`~models.paper.Paper` objects to summarise.
        api_key: OpenRouter API key.

    Returns:
        A new list of :class:`~models.paper.Paper` objects.  Papers that were
        summarised successfully contain populated summary fields; papers that
        failed are returned unchanged.
    """
    logger.info("Summarization agent starting — %d papers to process.", len(papers))

    semaphore = asyncio.Semaphore(5)

    async def _summarise_one(paper: Paper) -> Paper:
        async with semaphore:
            try:
                prompt = _build_prompt(paper)
                raw_text = await llm_complete(prompt=prompt, api_key=api_key)
                raw_text = _strip_code_fences(raw_text)
                data: dict = json.loads(raw_text)
                updates: dict[str, str | None] = {
                    f: str(data[f]) if f in data else None
                    for f in _EXPECTED_FIELDS
                }
                updated_paper = dataclasses.replace(paper, **updates)
                logger.debug("Summarised paper: %s", paper.title)
                return updated_paper
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to summarise paper '%s' (%s): %s",
                    paper.title,
                    paper.paper_id,
                    exc,
                )
                return paper

    tasks = [_summarise_one(paper) for paper in papers]
    results: list[Paper | BaseException] = await asyncio.gather(
        *tasks, return_exceptions=True
    )

    summarised: list[Paper] = []
    succeeded = 0
    skipped = 0

    for original, result in zip(papers, results):
        if isinstance(result, BaseException):
            logger.warning(
                "Unexpected exception gathering summary for '%s': %s",
                original.title,
                result,
            )
            summarised.append(original)
            skipped += 1
        else:
            summarised.append(result)
            if result.micro_summary is not None and result is not original:
                succeeded += 1
            else:
                skipped += 1

    logger.info(
        "Summarization complete — total: %d, summarised: %d, skipped: %d.",
        len(papers),
        succeeded,
        skipped,
    )

    return summarised
