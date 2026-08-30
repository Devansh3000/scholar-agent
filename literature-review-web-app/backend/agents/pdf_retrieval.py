"""
PDF Retrieval Agent for the Literature Review Web Application.

Agent 3 in the pipeline: attempts to retrieve full PDF text for each paper
concurrently.  Papers whose PDF cannot be fetched are returned unchanged with
``full_text=None`` (abstract-only mode).
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from typing import TYPE_CHECKING

from models.paper import Paper
from tools.pdf_extractor import extract_pdf_text

if TYPE_CHECKING:
    from services.cache_service import CacheService

logger = logging.getLogger(__name__)

_CONCURRENCY_LIMIT = 10


async def run_pdf_retrieval(
    papers: list[Paper],
    cache: "CacheService | None" = None,
    include_pdfs: bool = True,
) -> list[Paper]:
    """Attempt to retrieve full PDF text for each paper concurrently.

    Parameters
    ----------
    papers:
        List of :class:`~models.paper.Paper` objects to enrich with full text.
    cache:
        Optional :class:`~services.cache_service.CacheService` instance passed
        through to :func:`~tools.pdf_extractor.extract_pdf_text` for result
        caching.
    include_pdfs:
        When ``False``, skip all PDF retrieval and return *papers* unchanged.
        Useful for lightweight / abstract-only runs.

    Returns
    -------
    list[Paper]
        A new list of :class:`~models.paper.Paper` objects.  Papers whose PDF
        was fetched successfully have their ``full_text`` field populated;
        all others retain ``full_text=None``.
    """
    if not include_pdfs:
        logger.info(
            "pdf_retrieval: include_pdfs=False — skipping retrieval for %d paper(s)",
            len(papers),
        )
        return papers

    semaphore = asyncio.Semaphore(_CONCURRENCY_LIMIT)

    async def _fetch_one(paper: Paper) -> Paper:
        """Fetch PDF text for a single paper, honouring the concurrency limit."""
        logger.debug("pdf_retrieval: attempting url=%r", paper.url)
        async with semaphore:
            try:
                text = await extract_pdf_text(paper.url, cache=cache)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "pdf_retrieval: unhandled exception for url=%r: %s",
                    paper.url,
                    exc,
                )
                text = None

        if text is not None:
            return dataclasses.replace(paper, full_text=text)
        return paper  # full_text stays None (abstract-only)

    results = await asyncio.gather(
        *(_fetch_one(p) for p in papers),
        return_exceptions=True,
    )

    updated: list[Paper] = []
    for original, result in zip(papers, results):
        if isinstance(result, BaseException):
            logger.warning(
                "pdf_retrieval: gather exception for paper_id=%r: %s",
                original.paper_id,
                result,
            )
            updated.append(original)
        else:
            updated.append(result)  # type: ignore[arg-type]

    retrieved = sum(1 for p in updated if p.full_text is not None)
    abstract_only = len(updated) - retrieved

    logger.info(
        "pdf_retrieval: total=%d  pdfs_retrieved=%d  abstract_only=%d",
        len(updated),
        retrieved,
        abstract_only,
    )

    return updated


__all__ = ["run_pdf_retrieval"]
