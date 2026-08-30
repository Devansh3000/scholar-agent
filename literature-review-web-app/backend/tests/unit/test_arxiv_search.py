"""
Unit tests for backend/tools/arxiv_search.py

Tests cover:
- Successful search returning mapped Paper objects
- Cache HIT path (no API call made)
- Cache MISS path (API called, result stored)
- Exception handling returns empty list and logs a WARNING
- Correct field mapping from arxiv.Result to Paper
- Empty results are not written to cache
- Cache set uses ttl_seconds=86400
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.arxiv_search import search_arxiv, _result_to_paper
from models.paper import Paper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_arxiv_result(
    entry_id: str = "https://arxiv.org/abs/2301.00001v1",
    title: str = "  Test Paper Title  ",
    authors: list[str] | None = None,
    year: int = 2023,
    journal_ref: str | None = None,
    summary: str = "An abstract.",
    doi: str | None = "10.1234/test",
) -> MagicMock:
    """Return a MagicMock that behaves like an ``arxiv.Result``."""
    result = MagicMock()
    result.entry_id = entry_id
    result.title = title
    if authors is None:
        authors = ["Alice Smith", "Bob Jones"]
    author_mocks = []
    for a in authors:
        m = MagicMock()
        m.name = a
        author_mocks.append(m)
    result.authors = author_mocks
    published = MagicMock()
    published.year = year
    result.published = published
    result.journal_ref = journal_ref
    result.summary = summary
    result.doi = doi
    return result


class _FakeCache:
    """Simple in-memory async cache double."""

    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self._store: dict[str, Any] = dict(initial or {})
        self.set_calls: list[tuple] = []

    async def get(self, key: str) -> Any | None:
        return self._store.get(key)

    async def set(self, key: str, value: Any, ttl_seconds: int = 86400) -> None:
        self._store[key] = value
        self.set_calls.append((key, value, ttl_seconds))


# ---------------------------------------------------------------------------
# _result_to_paper unit tests
# ---------------------------------------------------------------------------


class TestResultToPaper:
    def test_basic_mapping(self):
        raw = _make_arxiv_result()
        paper = _result_to_paper(raw)

        assert isinstance(paper, Paper)
        assert paper.title == "Test Paper Title"  # stripped
        assert paper.paper_id == "https://arxiv.org/abs/2301.00001v1"
        assert paper.authors == ["Alice Smith", "Bob Jones"]
        assert paper.year == 2023
        assert paper.journal == "arXiv preprint"  # no journal_ref → default
        assert paper.abstract == "An abstract."
        assert paper.url == "https://arxiv.org/abs/2301.00001v1"
        assert paper.source == "arxiv"
        assert paper.doi == "10.1234/test"

    def test_journal_ref_used_when_present(self):
        raw = _make_arxiv_result(journal_ref="Nature, 2023")
        paper = _result_to_paper(raw)
        assert paper.journal == "Nature, 2023"

    def test_missing_entry_id_generates_uuid(self):
        raw = _make_arxiv_result(entry_id="")
        raw.entry_id = ""  # ensure falsy
        paper = _result_to_paper(raw)
        # Should fall back to a UUID string
        assert len(paper.paper_id) == 36  # UUID format

    def test_missing_published_year_defaults_to_zero(self):
        raw = _make_arxiv_result()
        raw.published = None
        paper = _result_to_paper(raw)
        assert paper.year == 0

    def test_missing_title_defaults_to_empty_string(self):
        raw = _make_arxiv_result(title="")
        raw.title = None
        paper = _result_to_paper(raw)
        assert paper.title == ""

    def test_missing_summary_defaults_to_empty_string(self):
        raw = _make_arxiv_result(summary="")
        raw.summary = None
        paper = _result_to_paper(raw)
        assert paper.abstract == ""

    def test_empty_authors_list(self):
        raw = _make_arxiv_result(authors=[])
        paper = _result_to_paper(raw)
        assert paper.authors == []

    def test_doi_can_be_none(self):
        raw = _make_arxiv_result(doi=None)
        raw.doi = None
        paper = _result_to_paper(raw)
        assert paper.doi is None


# ---------------------------------------------------------------------------
# search_arxiv async tests
# ---------------------------------------------------------------------------


class TestSearchArxiv:
    @pytest.mark.asyncio
    async def test_returns_list_of_papers_on_success(self):
        raw = _make_arxiv_result()

        with patch(
            "tools.arxiv_search.asyncio.get_event_loop"
        ) as mock_loop:
            future: asyncio.Future = asyncio.get_event_loop().create_future()
            future.set_result([raw])
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=[raw])

            papers = await search_arxiv("transformers", max_results=5)

        assert len(papers) == 1
        assert isinstance(papers[0], Paper)
        assert papers[0].title == "Test Paper Title"

    @pytest.mark.asyncio
    async def test_cache_hit_skips_api(self):
        cached_papers = [
            Paper(
                paper_id="cached-id",
                title="Cached Paper",
                authors=["Eve"],
                year=2022,
                journal="arXiv preprint",
                abstract="Cached abstract.",
                url="https://arxiv.org/abs/cached",
                source="arxiv",
            )
        ]
        cache = _FakeCache(initial={"arxiv:neural networks:10": cached_papers})

        with patch(
            "tools.arxiv_search.asyncio.get_event_loop"
        ) as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(side_effect=AssertionError("should not call API on cache hit"))
            papers = await search_arxiv("neural networks", max_results=10, cache=cache)

        assert papers == cached_papers

    @pytest.mark.asyncio
    async def test_cache_miss_stores_result(self):
        raw = _make_arxiv_result()
        cache = _FakeCache()

        with patch(
            "tools.arxiv_search.asyncio.get_event_loop"
        ) as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=[raw])
            papers = await search_arxiv("deep learning", max_results=5, cache=cache)

        assert len(papers) == 1
        # Cache should have been written
        assert len(cache.set_calls) == 1
        key, stored_papers, ttl = cache.set_calls[0]
        assert key == "arxiv:deep learning:5"
        assert stored_papers == papers
        assert ttl == 86400

    @pytest.mark.asyncio
    async def test_exception_returns_empty_list_and_logs_warning(self, caplog):
        import logging

        with patch(
            "tools.arxiv_search.asyncio.get_event_loop"
        ) as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(
                side_effect=RuntimeError("network error")
            )

            with caplog.at_level(logging.WARNING, logger="tools.arxiv_search"):
                papers = await search_arxiv("quantum computing")

        assert papers == []
        assert any("WARNING" in r.levelname for r in caplog.records)

    @pytest.mark.asyncio
    async def test_empty_results_not_written_to_cache(self):
        cache = _FakeCache()

        with patch(
            "tools.arxiv_search.asyncio.get_event_loop"
        ) as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=[])
            papers = await search_arxiv("obscure topic xyz", cache=cache)

        assert papers == []
        assert cache.set_calls == []  # nothing should be cached

    @pytest.mark.asyncio
    async def test_no_cache_provided_works(self):
        raw = _make_arxiv_result()

        with patch(
            "tools.arxiv_search.asyncio.get_event_loop"
        ) as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=[raw])
            papers = await search_arxiv("machine learning")

        assert len(papers) == 1

    @pytest.mark.asyncio
    async def test_info_log_searching(self, caplog):
        import logging

        with patch(
            "tools.arxiv_search.asyncio.get_event_loop"
        ) as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=[])

            with caplog.at_level(logging.INFO, logger="tools.arxiv_search"):
                await search_arxiv("attention mechanism")

        messages = [r.message for r in caplog.records]
        assert any("Searching arXiv for: attention mechanism" in m for m in messages)

    @pytest.mark.asyncio
    async def test_info_log_result_count(self, caplog):
        import logging

        raw = _make_arxiv_result()

        with patch(
            "tools.arxiv_search.asyncio.get_event_loop"
        ) as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=[raw])

            with caplog.at_level(logging.INFO, logger="tools.arxiv_search"):
                await search_arxiv("BERT")

        messages = [r.message for r in caplog.records]
        assert any("arXiv returned 1 results" in m for m in messages)
