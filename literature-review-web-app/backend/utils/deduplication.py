"""
Deduplication utilities for academic papers.

Provides functions to normalize paper titles and remove duplicate papers
from multi-source search results, either by simple first-occurrence
deduplication or by source-priority-aware merging.
"""

import re
from models.paper import Paper

# Source priority order for merge_paper_sources (highest to lowest).
_SOURCE_PRIORITY: dict[str, int] = {
    "semantic_scholar": 0,
    "arxiv": 1,
    "ieee": 2,
    "google_scholar": 3,
}


def normalize_title(title: str) -> str:
    """Return a canonical form of *title* for duplicate detection.

    Transformation steps:
    1. Lowercase the string.
    2. Remove all non-word, non-whitespace characters (punctuation).
    3. Collapse consecutive whitespace characters into a single space.
    4. Strip leading/trailing whitespace.

    Args:
        title: The raw paper title.

    Returns:
        The normalized title string.

    Examples:
        >>> normalize_title("Deep Learning: A Review!")
        'deep learning a review'
        >>> normalize_title("  Attention  Is  All  You  Need  ")
        'attention is all you need'
    """
    lowered = title.lower()
    no_punct = re.sub(r"[^\w\s]", "", lowered)
    collapsed = re.sub(r"\s+", " ", no_punct)
    return collapsed.strip()


def deduplicate_papers(papers: list[Paper]) -> list[Paper]:
    """Remove duplicate papers, preserving original ordering.

    Deduplication is performed in two sequential passes:

    1. **DOI pass** – for papers that carry a non-null DOI, only the first
       occurrence of each DOI is kept.
    2. **Title pass** – papers whose normalized title has already appeared in
       the output are dropped.

    The original list is never mutated; a new list is returned.

    Args:
        papers: Input collection of papers (may contain duplicates).

    Returns:
        A new list with duplicates removed, in the same relative order as the
        input.
    """
    seen_dois: set[str] = set()
    seen_titles: set[str] = set()
    result: list[Paper] = []

    for paper in papers:
        # --- Pass 1: DOI deduplication ---
        if paper.doi is not None:
            if paper.doi in seen_dois:
                continue
            seen_dois.add(paper.doi)

        # --- Pass 2: normalized-title deduplication ---
        norm = normalize_title(paper.title)
        if norm in seen_titles:
            continue
        seen_titles.add(norm)

        result.append(paper)

    return result


def merge_paper_sources(papers: list[Paper]) -> list[Paper]:
    """Deduplicate papers by choosing the best representative from each group.

    Papers are grouped into duplicate groups using the same criteria as
    :func:`deduplicate_papers` (shared non-null DOI *or* identical normalized
    title).  Within each group the paper selected is:

    * The paper with the **highest score**; or,
    * When scores are equal, the paper whose ``source`` appears earliest in the
      priority order: ``semantic_scholar`` > ``arxiv`` > ``ieee`` >
      ``google_scholar``.

    The returned list preserves the order in which each group's *winning*
    paper first appeared in *papers*.

    The original list is never mutated; a new list is returned.

    Args:
        papers: Input collection of papers (may contain duplicates from
            different academic sources).

    Returns:
        A new deduplicated list where each logical paper is represented by the
        highest-quality variant found across sources.
    """
    # Map from a canonical group key to the current best Paper for that group.
    # We also keep an insertion-order list of keys to reproduce stable output.
    group_best: dict[str, Paper] = {}
    group_order: list[str] = []

    def _group_key(paper: Paper) -> str:
        """Return a stable, unique key representing this paper's duplicate group."""
        # Prefer DOI as the canonical key because it is authoritative.
        if paper.doi is not None:
            return f"doi:{paper.doi}"
        return f"title:{normalize_title(paper.title)}"

    def _is_better(challenger: Paper, current_best: Paper) -> bool:
        """Return True if *challenger* should replace *current_best*."""
        if challenger.score > current_best.score:
            return True
        if challenger.score == current_best.score:
            challenger_priority = _SOURCE_PRIORITY.get(challenger.source, 99)
            current_priority = _SOURCE_PRIORITY.get(current_best.source, 99)
            return challenger_priority < current_priority
        return False

    for paper in papers:
        key = _group_key(paper)

        if key not in group_best:
            group_best[key] = paper
            group_order.append(key)
        else:
            if _is_better(paper, group_best[key]):
                group_best[key] = paper

    return [group_best[key] for key in group_order]
