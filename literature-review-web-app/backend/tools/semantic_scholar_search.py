"""
Semantic Scholar search tool for the Literature Review Web Application.

Provides an async interface to the Semantic Scholar API via the ``semanticscholar``
Python library.  Because the library is synchronous, the blocking call is offloaded
to a thread-pool executor so the event loop is never stalled.

Key behaviours
--------------
- Results are cached with a 24-hour TTL (key: ``s2:<query>:<max_results>``).
- Unauthenticated callers are rate-limited by a 1-second sleep *before* the
  fetch to stay within the free-tier limits.
- All field mappings fall back to safe defaults so missing API fields never raise.
- On any exception the function logs a WARNING and returns an empty list.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
from uuid import uuid4

from semanticscholar import SemanticScholar

from models.paper import Paper

if TYPE_CHECKING:
    from services.cache_service import CacheService

logger = logging.getLogger(__name__)

# Fields requested from the Semantic Scholar API.
_S2_FIELDS: list[str] = [
    "paperId",
    "title",
    "authors",
    "year",
    "venue",
    "journal",
    "abstract",
    "externalIds",
]

_CACHE_TTL: int = 86400  # 24 hours in seconds


async def search_semantic_scholar(
    query: str,
    max_results: int = 20,
    cache: "CacheService | None" = None,
    api_key: str = "",
) -> list[Paper]:
    """Search Semantic Scholar and return a list of :class:`~models.paper.Paper` objects.

    Parameters
    ----------
    query:
        The search string forwarded to the Semantic Scholar paper-search endpoint.
    max_results:
        Maximum number of results to request (default 20).
    cache:
        Optional :class:`~services.cache_service.CacheService` instance.
        When provided, results are read from and written to the cache using
        the key ``s2:<query>:<max_results>`` with a 24-hour TTL.
    api_key:
        Semantic Scholar API key.  When empty the unauthenticated free tier is
        used and a 1-second rate-limit delay is applied *before* the fetch.

    Returns
    -------
    list[Paper]
        Papers matching the query, or an empty list on any error.
    """
    cache_key = f"s2:{query}:{max_results}"

    try:
        # --- cache read ---
        if cache is not None:
            cached = await cache.get(cache_key)
            if cached is not None:
                logger.info(
                    "search_semantic_scholar: cache HIT for query=%r max_results=%d",
                    query,
                    max_results,
                )
                return cached

        logger.info(
            "search_semantic_scholar: cache MISS – querying Semantic Scholar for "
            "query=%r max_results=%d",
            query,
            max_results,
        )

        # --- rate-limit for unauthenticated tier (applied before the fetch) ---
        if not api_key:
            await asyncio.sleep(1.0)

        # --- blocking API call in thread with 15s timeout ---
        def _blocking_search() -> list:
            ss = SemanticScholar(api_key=api_key or None)
            return ss.search_paper(query, limit=max_results, fields=_S2_FIELDS)

        try:
            raw_results: list = await asyncio.wait_for(
                asyncio.to_thread(_blocking_search),
                timeout=15.0
            )
        except asyncio.TimeoutError:
            logger.warning("search_semantic_scholar: timed out for query=%r — skipping", query)
            return []

        # --- map to Paper domain objects ---
        papers: list[Paper] = []
        for paper in raw_results:
            paper_id: str = paper.paperId or str(uuid4())

            # Authors: handle both list[dict] ({"name": ...}) and list of objects.
            authors: list[str] = []
            for a in (paper.authors or []):
                if isinstance(a, dict):
                    authors.append(a.get("name", ""))
                else:
                    authors.append(getattr(a, "name", "") or "")

            # Resolve journal: prefer venue, then journal dict/object, then default.
            journal_name: str = getattr(paper, "venue", "") or ""
            if not journal_name and hasattr(paper, "journal") and paper.journal:
                if isinstance(paper.journal, dict):
                    journal_name = paper.journal.get("name", "")
                else:
                    journal_name = getattr(paper.journal, "name", "") or ""
            journal_name = journal_name or "Semantic Scholar"

            url: str = (
                f"https://semanticscholar.org/paper/{paper.paperId}"
                if paper.paperId
                else ""
            )

            doi: str | None = (paper.externalIds or {}).get("DOI")

            papers.append(
                Paper(
                    paper_id=paper_id,
                    title=paper.title or "",
                    authors=authors,
                    year=paper.year or 0,
                    journal=journal_name,
                    abstract=paper.abstract or "",
                    url=url,
                    source="semantic_scholar",
                    doi=doi,
                )
            )

        logger.info(
            "search_semantic_scholar: retrieved %d result(s) for query=%r",
            len(papers),
            query,
        )

        # --- cache write ---
        if cache is not None and papers:
            await cache.set(cache_key, papers, ttl_seconds=_CACHE_TTL)

        return papers

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "search_semantic_scholar: failed for query=%r – %s",
            query,
            exc,
        )
        return []


__all__ = ["search_semantic_scholar"]
