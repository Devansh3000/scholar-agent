"""
Thematic Clustering Agent (Agent 5) for the Literature Review Web Application.

Generates embeddings for papers via OpenRouter's embeddings endpoint (with a
local sentence-transformers fallback), then clusters them into thematic groups
using k-means via the clustering tool.

Concurrency for embedding requests is bounded by a semaphore.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging

from models.paper import Paper, Theme
from services.llm_client import llm_embed
from tools.clustering import cluster_papers

logger = logging.getLogger(__name__)

_MAX_ABSTRACT_CHARS = 500
_MAX_CONCURRENT_EMBEDDINGS = 10


async def run_thematic_clustering(
    papers: list[Paper],
    api_key: str,
    n_clusters: int = 5,
) -> tuple[list[Paper], list[Theme]]:
    """Generate embeddings for *papers* and cluster them into thematic groups.

    Parameters
    ----------
    papers:
        The list of :class:`~models.paper.Paper` objects to embed and cluster.
    api_key:
        OpenRouter API key (used for embeddings; falls back to local
        sentence-transformers if the API call fails).
    n_clusters:
        Desired number of thematic clusters (default 5).  Clamped to the
        number of papers with valid embeddings.

    Returns
    -------
    tuple[list[Paper], list[Theme]]
        * Updated papers with ``embedding`` and ``theme_id`` set.
        * List of :class:`~models.paper.Theme` objects.
    """
    if not papers:
        return papers, []

    # Build the text corpus — one string per paper
    texts = [
        f"{p.title} {(p.abstract or '')[:_MAX_ABSTRACT_CHARS]}"
        for p in papers
    ]

    # Fetch all embeddings in one batched call (with local fallback inside llm_embed)
    logger.info("Thematic clustering: generating embeddings for %d papers.", len(papers))
    try:
        embeddings = await llm_embed(texts=texts, api_key=api_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Embedding generation failed entirely (%s) — skipping embeddings.", exc
        )
        embeddings = [None] * len(papers)  # type: ignore[list-item]

    # Attach embeddings to paper copies
    papers_with_embeddings: list[Paper] = []
    for paper, emb in zip(papers, embeddings):
        if emb is not None:
            papers_with_embeddings.append(dataclasses.replace(paper, embedding=emb))
        else:
            papers_with_embeddings.append(paper)

    papers_embedded_count = sum(
        1 for p in papers_with_embeddings if p.embedding is not None
    )
    logger.info(
        "Embeddings ready: %d/%d papers embedded.", papers_embedded_count, len(papers)
    )

    # Cluster
    try:
        themes: list[Theme] = cluster_papers(
            papers_with_embeddings, n_clusters=n_clusters
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Clustering failed (%s) — returning single fallback theme.", exc)
        themes = [
            Theme(
                theme_id=0,
                label="General",
                description="All papers",
                paper_ids=frozenset(p.paper_id for p in papers),
            )
        ]

    paper_to_theme: dict[str, int] = {
        paper_id: theme.theme_id
        for theme in themes
        for paper_id in theme.paper_ids
    }

    final_papers: list[Paper] = [
        dataclasses.replace(p, theme_id=paper_to_theme.get(p.paper_id, 0))
        for p in papers_with_embeddings
    ]

    logger.info(
        "Thematic clustering complete: total=%d embedded=%d themes=%d",
        len(papers),
        papers_embedded_count,
        len(themes),
    )

    return final_papers, themes
