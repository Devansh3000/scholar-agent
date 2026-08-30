"""
Google Scholar search tool for the Literature Review Web Application.

Provides an async interface to Google Scholar using one of two backends:

* **SerpAPI** (preferred) – when a non-empty ``serpapi_key`` is supplied the
  function calls ``https://serpapi.com/search`` via :mod:`httpx` with a 30-second
  timeout.  Up to 20 results are returned per request (SerpAPI limit).

* **scholarly** (fallback) – when no API key is provided the open-source
  :mod:`scholarly` library scrapes Google Scholar directly.  Each result fetch
  is interleaved with a 2-second sleep to avoid triggering anti-bot measures.
  This path is inherently fragile and may fail silently; errors are caught and
  logged as WARNING.

Both paths:

- Cache results under the key ``scholar:<query>:<max_results>`` with a 24-hour
  TTL when a :class:`~services.cache_service.CacheService` is provided.
- Return ``[]`` on any exception rather than propagating.
- Emit INFO-level log messages indicating the active path and result count.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING
from uuid import uuid4

import httpx

from models.paper import Paper

if TYPE_CHECKING:
    from services.cache_service import CacheService

logger = logging.getLogger(__name__)

_CACHE_TTL: int = 86400  # 24 hours in seconds
_SERPAPI_URL: str = "https://serpapi.com/search"
_SERPAPI_TIMEOUT: float = 30.0
_SCHOLARLY_DELAY: float = 2.0


async def search_google_scholar(
    query: str,
    max_results: int = 20,
    cache: "CacheService | None" = None,
    serpapi_key: str = "",
) -> list[Paper]:
    """Search Google Scholar and return a list of :class:`~models.paper.Paper` objects.

    Parameters
    ----------
    query:
        Free-text search string forwarded to Google Scholar.
    max_results:
        Maximum number of results to retrieve (default 20).
    cache:
        Optional :class:`~services.cache_service.CacheService` instance.
        When provided, results are read from and written to the cache using
        the key ``scholar:<query>:<max_results>`` with a 24-hour TTL.
    serpapi_key:
        SerpAPI API key.  When non-empty the SerpAPI backend is used;
        otherwise the :mod:`scholarly` library is used as a fallback.

    Returns
    -------
    list[Paper]
        Papers matching the query, or an empty list on any error.
    """
    cache_key = f"scholar:{query}:{max_results}"

    try:
        # --- cache read ---
        if cache is not None:
            cached = await cache.get(cache_key)
            if cached is not None:
                logger.info(
                    "search_google_scholar: cache HIT for query=%r max_results=%d",
                    query,
                    max_results,
                )
                return cached

        if serpapi_key:
            papers = await _search_via_serpapi(query, max_results, serpapi_key)
        else:
            papers = await _search_via_scholarly(query, max_results)

        logger.info(
            "search_google_scholar: retrieved %d result(s) for query=%r",
            len(papers),
            query,
        )

        # --- cache write ---
        if cache is not None and papers:
            await cache.set(cache_key, papers, ttl_seconds=_CACHE_TTL)

        return papers

    except Exception as exc:  # noqa: BLE001
        logger.warning("Google Scholar search failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# SerpAPI backend
# ---------------------------------------------------------------------------


async def _search_via_serpapi(
    query: str,
    max_results: int,
    serpapi_key: str,
) -> list[Paper]:
    """Fetch results from the SerpAPI Google Scholar engine.

    Parameters
    ----------
    query:
        Search query string.
    max_results:
        Desired upper bound on results; capped at 20 per SerpAPI limits.
    serpapi_key:
        Valid SerpAPI API key.

    Returns
    -------
    list[Paper]
        Parsed results mapped to :class:`~models.paper.Paper` objects.
    """
    logger.info("search_google_scholar: using SerpAPI backend for query=%r", query)

    params: dict = {
        "engine": "google_scholar",
        "q": query,
        "num": min(max_results, 20),
        "api_key": serpapi_key,
    }

    async with httpx.AsyncClient(timeout=_SERPAPI_TIMEOUT) as client:
        response = await client.get(_SERPAPI_URL, params=params)
        response.raise_for_status()
        data = response.json()

    organic: list[dict] = data.get("organic_results", [])
    papers: list[Paper] = []

    for r in organic:
        pub_info: dict = r.get("publication_info", {})
        summary: str = pub_info.get("summary", "")

        # Extract the first 4-digit year found in the summary string.
        year_match = re.search(r"\b(\d{4})\b", summary)
        year: int = int(year_match.group(1)) if year_match else 0

        authors_raw: list[dict] = pub_info.get("authors", [])
        authors: list[str] = [a.get("name", "") for a in authors_raw]

        papers.append(
            Paper(
                paper_id=str(uuid4()),
                title=r.get("title", ""),
                authors=authors,
                year=year,
                journal=summary or "Google Scholar",
                abstract=r.get("snippet", ""),
                url=r.get("link", ""),
                source="google_scholar",
                doi=None,
            )
        )

    return papers


# ---------------------------------------------------------------------------
# scholarly fallback backend
# ---------------------------------------------------------------------------


async def _search_via_scholarly(query: str, max_results: int) -> list[Paper]:
    """Fetch results using the :mod:`scholarly` library with a strict timeout."""
    logger.info("search_google_scholar: using scholarly fallback for query=%r", query)

    try:
        import scholarly  # type: ignore[import-untyped]

        # 15s timeout for the scholarly search
        papers = await asyncio.wait_for(
            asyncio.to_thread(_do_scholarly_search, query, max_results),
            timeout=15.0
        )
        return papers

    except asyncio.TimeoutError:
        logger.warning("scholarly search timed out for query=%r — skipping", query)
        return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("Google Scholar search failed: %s", exc)
        return []


def _do_scholarly_search(query: str, max_results: int) -> list[Paper]:
    """Run scholarly search synchronously (called via asyncio.to_thread)."""
    try:
        import scholarly  # type: ignore[import-untyped]
        results = []
        search_iter = scholarly.scholarly.search_pubs(query)
        for _ in range(min(max_results, 3)):  # cap at 3 to limit blocking time
            try:
                pub = next(search_iter)
                bib = pub.get("bib", {})
                raw_authors = bib.get("author", [])
                authors = raw_authors if isinstance(raw_authors, list) else ([raw_authors] if raw_authors else [])
                raw_year = bib.get("pub_year")
                year = int(raw_year) if raw_year else 0
                results.append(Paper(
                    paper_id=str(uuid4()),
                    title=bib.get("title", ""),
                    authors=authors,
                    year=year,
                    journal=bib.get("venue", "") or bib.get("journal", "") or "Google Scholar",
                    abstract=bib.get("abstract", ""),
                    url=pub.get("pub_url", ""),
                    source="google_scholar",
                    doi=None,
                ))
            except StopIteration:
                break
        return results
    except Exception as e:
        logger.warning("scholarly inner error: %s", e)
        return []

__all__ = ["search_google_scholar"]
