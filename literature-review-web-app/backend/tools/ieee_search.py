"""
IEEE Xplore search tool for the Literature Review Web Application.

Provides an async function to query the IEEE Xplore REST API and map the
results to the canonical ``Paper`` domain model.  Responses are cached for
24 hours to avoid redundant API calls and to respect rate limits.

API reference: https://developer.ieee.org/docs/read/IEEE_Xplore_API_Reference
"""

from __future__ import annotations

import asyncio  # noqa: F401 – kept for consistency with other search tools
import logging
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import httpx

from models.paper import Paper

if TYPE_CHECKING:
    from services.cache_service import CacheService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_IEEE_BASE_URL = "https://ieeexploreapi.ieee.org/api/v1/search/articles"
_TIMEOUT_SECONDS = 30.0
_CACHE_TTL = 86400  # 24 hours in seconds
_MAX_RECORDS_LIMIT = 200


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


def _map_article_to_paper(article: dict[str, Any]) -> Paper:
    """Map a single IEEE Xplore article dict to a :class:`~models.paper.Paper` instance."""
    raw_authors: list[dict[str, Any]] = article.get("authors", {}).get("authors", [])
    authors = [a.get("full_name", "") for a in raw_authors]

    raw_year = article.get("publication_year")
    year: int = int(raw_year) if raw_year else 0

    url = article.get("html_url", "") or article.get("pdf_url", "")

    raw_id = article.get("article_number", "")
    paper_id = str(raw_id) if raw_id else str(uuid4())

    return Paper(
        paper_id=paper_id,
        title=article.get("title", ""),
        authors=authors,
        year=year,
        journal=article.get("publication_title", "IEEE"),
        abstract=article.get("abstract", ""),
        url=url,
        source="ieee",
        doi=article.get("doi"),
    )


# ---------------------------------------------------------------------------
# Public search function
# ---------------------------------------------------------------------------


async def search_ieee(
    query: str,
    max_results: int = 20,
    cache: "CacheService | None" = None,
    api_key: str = "",
) -> list[Paper]:
    """Search the IEEE Xplore API and return a list of :class:`~models.paper.Paper` objects.

    Parameters
    ----------
    query:
        Free-text search query forwarded to the ``querytext`` parameter.
    max_results:
        Maximum number of records to retrieve (capped at 200 per the API limit).
        Defaults to 20.
    cache:
        Optional :class:`~services.cache_service.CacheService` instance.
        When provided, results are read from and written to the cache using
        the key ``ieee:<query>:<max_results>`` with a 24-hour TTL.
    api_key:
        IEEE Xplore API key.  If empty, logs a WARNING and returns ``[]``
        immediately — the API requires a valid key.

    Returns
    -------
    list[Paper]
        Parsed papers, or an empty list on any error or missing API key.
    """
    if not api_key:
        logger.warning("IEEE_API_KEY not configured – skipping IEEE search")
        return []

    cache_key = f"ieee:{query}:{max_results}"

    # ------------------------------------------------------------------ #
    # Cache read
    # ------------------------------------------------------------------ #
    if cache is not None:
        cached = await cache.get(cache_key)
        if cached is not None:
            logger.debug("IEEE cache hit for key: %s", cache_key)
            return cached

    # ------------------------------------------------------------------ #
    # HTTP request
    # ------------------------------------------------------------------ #
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(
                _IEEE_BASE_URL,
                params={
                    "querytext": query,
                    "max_records": min(max_results, _MAX_RECORDS_LIMIT),
                    "apikey": api_key,
                },
            )
            response.raise_for_status()

            data = response.json()
            articles: list[dict[str, Any]] = data.get("articles", [])
            papers = [_map_article_to_paper(article) for article in articles]

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "IEEE Xplore search failed for query %r: %s",
            query,
            exc,
        )
        return []

    # ------------------------------------------------------------------ #
    # Cache write
    # ------------------------------------------------------------------ #
    if cache is not None and papers:
        await cache.set(cache_key, papers, ttl_seconds=_CACHE_TTL)

    return papers


__all__ = ["search_ieee"]
