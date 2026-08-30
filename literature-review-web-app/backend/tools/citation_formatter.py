"""
Citation formatter tool for the Literature Review Web Application.

Provides functions to format academic paper citations in APA, Harvard, and
IEEE styles, as well as a bibliography formatter that sorts and formats a
collection of papers.
"""

from __future__ import annotations

from typing import Literal

from models.paper import Paper


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_author(full_name: str) -> tuple[str, str]:
    """Parse an author's full name into (last_name, initials).

    Parameters
    ----------
    full_name:
        The author's name, e.g. ``"Jane A. Smith"`` or ``"Smith"``.

    Returns
    -------
    tuple[str, str]
        A ``(last_name, initials)`` pair.  *initials* is a dot-separated
        string such as ``"J. A."``.  When only a single token is present the
        whole token is treated as the last name and initials is an empty
        string.

    Examples
    --------
    >>> _parse_author("Jane Smith")
    ('Smith', 'J.')
    >>> _parse_author("Jane Ann Smith")
    ('Smith', 'J. A.')
    >>> _parse_author("Smith")
    ('Smith', '')
    """
    parts = full_name.strip().split()
    if len(parts) == 1:
        return (parts[0], "")
    last = parts[-1]
    initials = " ".join(f"{p[0]}." for p in parts[:-1] if p)
    return (last, initials)


# ---------------------------------------------------------------------------
# APA helpers
# ---------------------------------------------------------------------------


def _apa_author(full_name: str) -> str:
    """Format a single author name in APA style: ``"Last, F."``."""
    last, initials = _parse_author(full_name)
    if not initials:
        return last
    return f"{last}, {initials}"


def _authors_apa(authors: list[str]) -> str:
    """Format an author list for APA style.

    * 1 author  → ``"Last, F."``
    * 2 authors → ``"Last, F., & Last, F."``
    * 3-6       → ``"Last, F., Last, F., & Last, F."``
    * >6        → first 6 + ``, … et al.``
    """
    formatted = [_apa_author(a) for a in authors]
    n = len(formatted)
    if n == 0:
        return ""
    if n == 1:
        return formatted[0]
    if n == 2:
        return f"{formatted[0]}, & {formatted[1]}"
    if n <= 6:
        return ", ".join(formatted[:-1]) + f", & {formatted[-1]}"
    # > 6 authors: first 6 then et al.
    return ", ".join(formatted[:6]) + ", … et al."


# ---------------------------------------------------------------------------
# Harvard helpers
# ---------------------------------------------------------------------------


def _harvard_author(full_name: str) -> str:
    """Format a single author name in Harvard style: ``"Last, F."``."""
    # Harvard uses the same per-author format as APA
    return _apa_author(full_name)


def _authors_harvard(authors: list[str]) -> str:
    """Format an author list for Harvard style.

    The last two authors are joined with *and*; all earlier entries are
    separated by commas.

    * 1 author  → ``"Last, F."``
    * 2 authors → ``"Last, F. and Last, F."``
    * 3+        → ``"Last, F., Last, F. and Last, F."``
    """
    formatted = [_harvard_author(a) for a in authors]
    n = len(formatted)
    if n == 0:
        return ""
    if n == 1:
        return formatted[0]
    if n == 2:
        return f"{formatted[0]} and {formatted[1]}"
    return ", ".join(formatted[:-1]) + f" and {formatted[-1]}"


# ---------------------------------------------------------------------------
# IEEE helpers
# ---------------------------------------------------------------------------


def _ieee_author(full_name: str) -> str:
    """Format a single author name in IEEE style: ``"F. Last"``."""
    last, initials = _parse_author(full_name)
    if not initials:
        return last
    return f"{initials} {last}"


def _authors_ieee(authors: list[str]) -> str:
    """Format an author list for IEEE style.

    If there are more than three authors only the first author is included
    followed by *et al.*
    """
    if not authors:
        return ""
    formatted = [_ieee_author(a) for a in authors]
    if len(formatted) > 3:
        return f"{formatted[0]} et al."
    return ", ".join(formatted)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def format_citation(
    paper: Paper,
    style: Literal["APA", "Harvard", "IEEE"] = "APA",
) -> str:
    """Return a formatted citation string for *paper* in the requested *style*.

    Parameters
    ----------
    paper:
        The :class:`~models.paper.Paper` to cite.
    style:
        One of ``"APA"``, ``"Harvard"``, or ``"IEEE"`` (default ``"APA"``).

    Returns
    -------
    str
        A single-line citation string ready for inclusion in a bibliography.

    Examples
    --------
    >>> from models.paper import Paper
    >>> p = Paper(
    ...     paper_id="1", title="Deep Learning", authors=["Yann LeCun", "Geoffrey Hinton"],
    ...     year=2015, journal="Nature", abstract="", url="", source="arxiv",
    ...     doi="10.1038/nature14539",
    ... )
    >>> format_citation(p, "APA")
    'LeCun, Y., & Hinton, G. (2015). Deep Learning. Nature. https://doi.org/10.1038/nature14539'
    """
    doi_part = f" https://doi.org/{paper.doi}" if paper.doi else ""

    if style == "APA":
        authors_str = _authors_apa(paper.authors)
        return f"{authors_str}. ({paper.year}). {paper.title}. {paper.journal}.{doi_part}"

    if style == "Harvard":
        authors_str = _authors_harvard(paper.authors)
        return f"{authors_str} ({paper.year}) '{paper.title}', {paper.journal}.{doi_part}"

    if style == "IEEE":
        authors_str = _authors_ieee(paper.authors)
        return f'{authors_str}, "{paper.title}," {paper.journal}, {paper.year}.{doi_part}'

    raise ValueError(f"Unknown citation style: {style!r}")


def format_bibliography(
    papers: list[Paper],
    style: Literal["APA", "Harvard", "IEEE"] = "APA",
) -> str:
    """Return a full bibliography string for a collection of papers.

    Papers are sorted alphabetically by the last name of the first author
    before formatting.  Individual citations are separated by a blank line.

    Parameters
    ----------
    papers:
        The papers to include in the bibliography.
    style:
        Citation style to apply to every entry (default ``"APA"``).

    Returns
    -------
    str
        Formatted bibliography with entries separated by ``"\\n\\n"``.
        Returns an empty string when *papers* is empty.
    """
    if not papers:
        return ""

    def _sort_key(paper: Paper) -> str:
        if not paper.authors:
            return ""
        last, _ = _parse_author(paper.authors[0])
        return last.lower()

    sorted_papers = sorted(papers, key=_sort_key)
    citations = [format_citation(p, style) for p in sorted_papers]
    return "\n\n".join(citations)


__all__ = ["format_citation", "format_bibliography", "_parse_author"]
