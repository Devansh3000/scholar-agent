"""
Agent 1: Topic Understanding

Analyzes a research topic using an LLM (via OpenRouter with model fallback)
and extracts structured information required by downstream agents: an expanded
topic description, core keywords, relevant academic subdomains, and optimized
search queries.

Usage::

    from agents.topic_understanding import run_topic_understanding

    result = await run_topic_understanding(
        topic="transformer architectures in NLP",
        api_key="sk-or-...",
    )
    # result.keywords, result.search_queries, etc.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from services.llm_client import llm_complete

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class TopicUnderstandingResult:
    """Structured output produced by the Topic Understanding agent.

    Attributes
    ----------
    expanded_topic:
        A 2–3 sentence expansion of the original research topic.
    keywords:
        10–15 core academic keywords for the topic.
    subdomains:
        3–5 relevant academic subdomains.
    search_queries:
        15–20 optimized academic search queries ready for use by the
        Paper Search agent.
    """

    expanded_topic: str
    keywords: list[str] = field(default_factory=list)
    subdomains: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """\
You are an expert academic researcher. Analyze the following research topic and return a JSON object with:
- "expanded_topic": a 2-3 sentence expansion of the topic
- "keywords": list of 10-15 core keywords
- "subdomains": list of 3-5 relevant academic subdomains
- "search_queries": list of 15-20 optimized academic search queries

Topic: {topic}

Return only valid JSON, no markdown.\
"""

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


# ---------------------------------------------------------------------------
# Safe defaults helper
# ---------------------------------------------------------------------------


def _safe_defaults(topic: str) -> TopicUnderstandingResult:
    """Return a minimal result when JSON parsing fails."""
    return TopicUnderstandingResult(
        expanded_topic=topic,
        keywords=[topic],
        subdomains=[topic],
        search_queries=[topic],
    )


# ---------------------------------------------------------------------------
# Public async entry point
# ---------------------------------------------------------------------------


async def run_topic_understanding(
    topic: str,
    api_key: str,
) -> TopicUnderstandingResult:
    """Analyze *topic* with an LLM and return a :class:`TopicUnderstandingResult`.

    Parameters
    ----------
    topic:
        The research topic or question supplied by the user.
    api_key:
        OpenRouter API key (``sk-or-...``).

    Returns
    -------
    TopicUnderstandingResult
        Structured information extracted from the topic.  If the model returns
        unparseable JSON, safe defaults derived from the original topic are
        returned and a WARNING is logged.

    Raises
    ------
    RuntimeError
        Raised when all fallback models fail.  Topic Understanding is Agent 1
        and a failure here is unrecoverable — the orchestrator aborts the job.
    """
    logger.info("Topic Understanding agent starting. topic=%r", topic)

    prompt = _PROMPT_TEMPLATE.format(topic=topic)

    try:
        raw_text = await llm_complete(prompt=prompt, api_key=api_key)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Topic understanding failed: {exc}") from exc

    # Strip markdown code fences if present
    fence_match = _CODE_FENCE_RE.search(raw_text)
    if fence_match:
        raw_text = fence_match.group(1)
    raw_text = raw_text.strip()

    try:
        data: dict = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.warning(
            "Topic Understanding: JSON parse error for topic=%r — using safe defaults. "
            "Error: %s. Raw response (first 500 chars): %.500s",
            topic,
            exc,
            raw_text,
        )
        return _safe_defaults(topic)

    result = TopicUnderstandingResult(
        expanded_topic=data.get("expanded_topic", topic),
        keywords=data.get("keywords", []),
        subdomains=data.get("subdomains", []),
        search_queries=data.get("search_queries", []),
    )

    logger.info(
        "Topic Understanding agent completed. topic=%r — "
        "%d keywords, %d subdomains, %d search queries",
        topic,
        len(result.keywords),
        len(result.subdomains),
        len(result.search_queries),
    )

    return result


__all__ = ["TopicUnderstandingResult", "run_topic_understanding"]
