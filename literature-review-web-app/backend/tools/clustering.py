"""
Thematic clustering tool for the Literature Review Web Application.

Groups a list of ``Paper`` objects into thematic ``Theme`` clusters using
k-means on paper embedding vectors.  Papers that lack embeddings are assigned
to the largest cluster so that the partition property is preserved: every input
paper appears in exactly one output theme.
"""

from __future__ import annotations

import logging
from collections import defaultdict

import numpy as np
from sklearn.cluster import KMeans

from models.paper import Paper, Theme

logger = logging.getLogger(__name__)


def cluster_papers(papers: list[Paper], n_clusters: int = 5) -> list[Theme]:
    """Cluster *papers* into thematic groups using k-means on embedding vectors.

    Papers that carry no embedding (``paper.embedding is None``) are placed in
    the largest cluster so the partition property is maintained.

    Parameters
    ----------
    papers:
        The full list of papers to cluster.
    n_clusters:
        Desired number of themes.  Automatically clamped to
        ``len(papers_with_embeddings)`` when that is smaller.

    Returns
    -------
    list[Theme]
        One :class:`~models.paper.Theme` per cluster.  The union of all
        ``theme.paper_ids`` equals ``{p.paper_id for p in papers}``, and no
        paper ID appears in more than one theme.
    """
    # --- Partition into papers with and without embeddings ---
    papers_with_embeddings: list[Paper] = [p for p in papers if p.embedding is not None]
    papers_without_embeddings: list[Paper] = [p for p in papers if p.embedding is None]

    logger.info(
        "cluster_papers: n_clusters=%d, total=%d, without_embeddings=%d",
        n_clusters,
        len(papers),
        len(papers_without_embeddings),
    )

    # --- Fallback: not enough papers to cluster ---
    if len(papers_with_embeddings) < 2:
        return [
            Theme(
                theme_id=0,
                label="Theme 1",
                description=f"All {len(papers)} papers",
                paper_ids=frozenset(p.paper_id for p in papers),
            )
        ]

    # --- Clamp n_clusters ---
    n_clusters = min(n_clusters, len(papers_with_embeddings))

    # --- Build feature matrix ---
    X = np.array([p.embedding for p in papers_with_embeddings])

    # --- K-means clustering ---
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(X)

    # --- Build cluster groups from embedded papers ---
    cluster_groups: dict[int, list[str]] = defaultdict(list)
    for paper, label in zip(papers_with_embeddings, labels):
        cluster_groups[int(label)].append(paper.paper_id)

    # --- Assign papers without embeddings to the largest cluster ---
    if papers_without_embeddings:
        largest_cluster = max(cluster_groups, key=lambda k: len(cluster_groups[k]))
        for paper in papers_without_embeddings:
            cluster_groups[largest_cluster].append(paper.paper_id)

    # --- Build Theme objects ---
    themes: list[Theme] = []
    for i in range(n_clusters):
        paper_ids = frozenset(cluster_groups[i])
        themes.append(
            Theme(
                theme_id=i,
                label=f"Theme {i + 1}",
                description=f"Cluster {i + 1} containing {len(paper_ids)} papers",
                paper_ids=paper_ids,
            )
        )

    # --- Verify partition property ---
    all_assigned: set[str] = set()
    for theme in themes:
        all_assigned.update(theme.paper_ids)
    input_ids = {p.paper_id for p in papers}
    assert all_assigned == input_ids, (
        f"Partition violated: assigned={all_assigned!r} != input={input_ids!r}"
    )

    return themes


def assign_papers_to_themes(papers: list[Paper], themes: list[Theme]) -> dict[str, int]:
    """Build a ``{paper_id: theme_id}`` mapping for every paper.

    Parameters
    ----------
    papers:
        All papers that were clustered.
    themes:
        The themes returned by :func:`cluster_papers`.

    Returns
    -------
    dict[str, int]
        A mapping from each paper's ``paper_id`` to its assigned ``theme_id``.
        Papers not present in any theme are omitted from the result.
    """
    mapping: dict[str, int] = {}
    for theme in themes:
        for paper_id in theme.paper_ids:
            mapping[paper_id] = theme.theme_id
    return mapping


__all__ = ["cluster_papers", "assign_papers_to_themes"]
