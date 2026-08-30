"""
Citation Formatter Agent (Agent 9).

Formats a bibliography for a collection of academic papers using the
synchronous :func:`~tools.citation_formatter.format_bibliography` tool.

Two public entry points are provided:

* :func:`run_citation_formatter` — core function that calls the tool and
  returns a formatted bibliography string, logging a WARNING and returning a
  descriptive placeholder on failure.
* :func:`run_citation_formatter_with_fallback` — thin wrapper around the
  above with an additional outer safety net that returns a generic
  ``"[Bibliography unavailable]"`` string if anything unexpected escapes the
  inner function.
"""

from __future__ import annotations

import logging
from typing import Literal

from models.paper import Paper
from tools.citation_formatter import format_bibliography

logger = logging.getLogger(__name__)


async def run_citation_formatter(
    papers: list[Paper],
    style: Literal["APA", "Harvard", "IEEE"] = "APA",
) -> str:
    """Format a bibliography for *papers* in the requested citation *style*.

    The underlying :func:`~tools.citation_formatter.format_bibliography` call
    is synchronous and fast, so it is invoked directly on the event-loop
    thread without delegating to an executor.

    Args:
        papers: List of :class:`~models.paper.Paper` objects to include in
                the bibliography.
        style:  Citation style — one of ``"APA"``, ``"Harvard"``, or
                ``"IEEE"``.  Defaults to ``"APA"``.

    Returns:
        A formatted bibliography string with individual citations separated
        by blank lines.  Returns a descriptive placeholder string if
        formatting fails for any reason.
    """
    try:
        bibliography = format_bibliography(papers, style=style)
        logger.debug(
            "Citation formatter produced bibliography (%d papers, style=%s).",
            len(papers),
            style,
        )
        return bibliography
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Citation formatting failed for %d papers (style=%s): %s",
            len(papers),
            style,
            exc,
        )
        return f"[{len(papers)} references — citation formatting failed]"


async def run_citation_formatter_with_fallback(
    papers: list[Paper],
    style: Literal["APA", "Harvard", "IEEE"] = "APA",
) -> str:
    """Format a bibliography, returning a safe fallback string on any failure.

    Wraps :func:`run_citation_formatter` with an additional outer
    ``try/except`` so that even unexpected errors (e.g. those raised inside
    the inner error handler) are caught gracefully.

    Args:
        papers: List of :class:`~models.paper.Paper` objects to include in
                the bibliography.
        style:  Citation style — one of ``"APA"``, ``"Harvard"``, or
                ``"IEEE"``.  Defaults to ``"APA"``.

    Returns:
        A formatted bibliography string, or ``"[Bibliography unavailable]"``
        if any exception escapes :func:`run_citation_formatter`.
    """
    try:
        return await run_citation_formatter(papers, style=style)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Citation formatter with fallback caught unexpected error: %s", exc
        )
        return "[Bibliography unavailable]"
