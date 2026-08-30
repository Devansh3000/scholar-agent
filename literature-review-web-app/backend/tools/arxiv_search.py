"""
arXiv search tool for the Literature Review Web Application.

Provides an async interface to the arXiv API via the ``arxiv`` Python library.
Results are mapped to the internal ``Paper`` domain model and optionally cached
with a 24-hour TTL.  The blocking arXiv client call is offloaded to a
thread-pool executor so the asyncio event loop is never stalled.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
from uuid import uuid4

import arxiv

from models.paper import Paper

if TYPE_CHECKING:
    from services.cache_service import CacheService

logger = logging.getLogger(__name__)

_CACHE_TTL = 86400  # 24 hours in seconds


async def search_arxiv(
    query: str,
    max_results: int = 20,
    cache: CacheService | None = None,
) -> list[Paper]:
    """Search arXiv for papers matching *query* and return them as ``Paper`` objects.

    Parameters
    ----------
    query:
        Free-text or structured arXiv query string.
    max_results:
        Maximum number of results to retrieve (default 20).
    cache:
        Optional :class:`~services.cache_service.CacheService` instance.
        When provided, results are stored and retrieved using a query-scoped
        key with a 24-hour TTL.

    Returns
    -------
    list[Paper]
        Papers matching the query, or an empty list on error or no results.
    """
    cache_key = f"arxiv:{query}:{max_results}"

    # --- Cache look-up ---
    if cache is not None:
        cached = await cache.get(cache_key)
        if cached is not None:
            logger.info("arXiv cache HIT for query=%r max_results=%d", query, max_results)
            return cached
        logger.info("arXiv cache MISS for query=%r max_results=%d", query, max_results)

    logger.info("Searching arXiv for: %s", query)

    try:
        # Offload blocking arXiv call to a thread with a hard 20s timeout.
        # asyncio.to_thread uses a fresh daemon thread and avoids polluting
        # the shared default executor pool.
        def _blocking_fetch() -> list[arxiv.Result]:
            client = arxiv.Client(num_retries=1, delay_seconds=0.5)
            search = arxiv.Search(query=query, max_results=max_results)
            return list(client.results(search))

        raw_results: list[arxiv.Result] = await asyncio.wait_for(
            asyncio.to_thread(_blocking_fetch),
            timeout=20.0,
        )
    except asyncio.TimeoutError:
        logger.warning("search_arxiv: timed out for query=%r — skipping", query)
        return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("search_arxiv: failed to fetch results for query=%r: %s", query, exc)
        return []

    papers = [_result_to_paper(r) for r in raw_results]

    logger.info("arXiv returned %d results", len(papers))

    # --- Cache store ---
    if cache is not None and papers:
        await cache.set(cache_key, papers, ttl_seconds=_CACHE_TTL)

    return papers


def _result_to_paper(result: arxiv.Result) -> Paper:
    """Convert a single :class:`arxiv.Result` to a :class:`Paper` domain object."""
    return Paper(
        paper_id=result.entry_id or str(uuid4()),
        title=result.title.strip() if result.title else "",
        authors=[a.name for a in (result.authors or [])],
        year=result.published.year if result.published else 0,
        journal=result.journal_ref or "arXiv preprint",
        abstract=result.summary or "",
        url=result.entry_id or "",
        source="arxiv",
        doi=result.doi,
    )


__all__ = ["search_arxiv"]
