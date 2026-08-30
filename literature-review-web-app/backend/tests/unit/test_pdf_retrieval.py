"""
Unit tests for backend/agents/pdf_retrieval.py

Tests cover:
- include_pdfs=False: papers returned unchanged immediately
- Successful PDF extraction: full_text populated via dataclasses.replace
- Failed extraction (returns None): paper kept with full_text=None
- Exception during extraction: paper kept with full_text=None
- Mixed results: some retrieved, some abstract-only
- Concurrency: all papers processed when count > semaphore limit
- Logging: INFO summary and DEBUG per-URL messages are emitted
- Return type is always list[Paper]
"""

from __future__ import annotations

import dataclasses
import logging
from unittest.mock import AsyncMock, patch

import pytest

from models.paper import Paper


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_paper(
    paper_id: str = "p1",
    url: str = "https://example.com/paper.pdf",
    full_text: str | None = None,
) -> Paper:
    return Paper(
        paper_id=paper_id,
        title=f"Paper {paper_id}",
        authors=["Author A"],
        year=2024,
        journal="Test Journal",
        abstract="Abstract text.",
        url=url,
        source="arxiv",
        full_text=full_text,
    )


# ---------------------------------------------------------------------------
# include_pdfs=False
# ---------------------------------------------------------------------------


class TestIncludePdfsFalse:
    @pytest.mark.asyncio
    async def test_returns_papers_unchanged(self):
        papers = [_make_paper("p1"), _make_paper("p2")]

        with patch("agents.pdf_retrieval.extract_pdf_text") as mock_extract:
            from agents.pdf_retrieval import run_pdf_retrieval

            result = await run_pdf_retrieval(papers, include_pdfs=False)

        mock_extract.assert_not_called()
        assert result is papers  # exact same object returned

    @pytest.mark.asyncio
    async def test_returns_papers_unchanged_empty_list(self):
        with patch("agents.pdf_retrieval.extract_pdf_text") as mock_extract:
            from agents.pdf_retrieval import run_pdf_retrieval

            result = await run_pdf_retrieval([], include_pdfs=False)

        mock_extract.assert_not_called()
        assert result == []


# ---------------------------------------------------------------------------
# Successful extraction
# ---------------------------------------------------------------------------


class TestSuccessfulExtraction:
    @pytest.mark.asyncio
    async def test_full_text_populated(self):
        paper = _make_paper("p1", url="https://example.com/p1.pdf")

        with patch(
            "agents.pdf_retrieval.extract_pdf_text",
            new=AsyncMock(return_value="extracted text"),
        ):
            from agents.pdf_retrieval import run_pdf_retrieval

            result = await run_pdf_retrieval([paper])

        assert len(result) == 1
        assert result[0].full_text == "extracted text"
        # Frozen dataclass — must be a new object
        assert result[0] is not paper

    @pytest.mark.asyncio
    async def test_other_fields_preserved_after_replace(self):
        paper = _make_paper("p42", url="https://example.com/p42.pdf")

        with patch(
            "agents.pdf_retrieval.extract_pdf_text",
            new=AsyncMock(return_value="some text"),
        ):
            from agents.pdf_retrieval import run_pdf_retrieval

            result = await run_pdf_retrieval([paper])

        updated = result[0]
        assert updated.paper_id == "p42"
        assert updated.title == "Paper p42"
        assert updated.full_text == "some text"


# ---------------------------------------------------------------------------
# Failed extraction
# ---------------------------------------------------------------------------


class TestFailedExtraction:
    @pytest.mark.asyncio
    async def test_none_result_keeps_original_paper(self):
        paper = _make_paper("p1")

        with patch(
            "agents.pdf_retrieval.extract_pdf_text",
            new=AsyncMock(return_value=None),
        ):
            from agents.pdf_retrieval import run_pdf_retrieval

            result = await run_pdf_retrieval([paper])

        assert len(result) == 1
        assert result[0].full_text is None
        assert result[0] is paper  # original object returned unchanged

    @pytest.mark.asyncio
    async def test_exception_keeps_original_paper(self):
        paper = _make_paper("p1")

        with patch(
            "agents.pdf_retrieval.extract_pdf_text",
            new=AsyncMock(side_effect=RuntimeError("network error")),
        ):
            from agents.pdf_retrieval import run_pdf_retrieval

            result = await run_pdf_retrieval([paper])

        assert len(result) == 1
        assert result[0].full_text is None
        assert result[0] is paper


# ---------------------------------------------------------------------------
# Mixed results
# ---------------------------------------------------------------------------


class TestMixedResults:
    @pytest.mark.asyncio
    async def test_mix_of_success_and_failure(self):
        papers = [
            _make_paper("p1", url="https://example.com/p1.pdf"),
            _make_paper("p2", url="https://example.com/p2.pdf"),
            _make_paper("p3", url="https://example.com/p3.pdf"),
        ]

        async def _fake_extract(url: str, cache=None) -> str | None:
            if "p2" in url:
                return None  # failure
            return f"text for {url}"

        with patch("agents.pdf_retrieval.extract_pdf_text", side_effect=_fake_extract):
            from agents.pdf_retrieval import run_pdf_retrieval

            result = await run_pdf_retrieval(papers)

        assert len(result) == 3
        assert result[0].full_text == "text for https://example.com/p1.pdf"
        assert result[1].full_text is None
        assert result[2].full_text == "text for https://example.com/p3.pdf"

    @pytest.mark.asyncio
    async def test_empty_paper_list_returns_empty(self):
        with patch("agents.pdf_retrieval.extract_pdf_text", new=AsyncMock()) as mock_e:
            from agents.pdf_retrieval import run_pdf_retrieval

            result = await run_pdf_retrieval([])

        mock_e.assert_not_called()
        assert result == []


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


class TestConcurrency:
    @pytest.mark.asyncio
    async def test_processes_more_papers_than_semaphore_limit(self):
        """More than 10 papers should all be processed (semaphore throttles, not limits)."""
        papers = [_make_paper(str(i), url=f"https://example.com/p{i}.pdf") for i in range(25)]

        with patch(
            "agents.pdf_retrieval.extract_pdf_text",
            new=AsyncMock(return_value="text"),
        ):
            from agents.pdf_retrieval import run_pdf_retrieval

            result = await run_pdf_retrieval(papers)

        assert len(result) == 25
        assert all(p.full_text == "text" for p in result)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


class TestLogging:
    @pytest.mark.asyncio
    async def test_info_log_contains_counts(self, caplog):
        papers = [
            _make_paper("p1", url="https://example.com/p1.pdf"),
            _make_paper("p2", url="https://example.com/p2.pdf"),
        ]

        async def _fake_extract(url: str, cache=None) -> str | None:
            return "text" if "p1" in url else None

        with patch("agents.pdf_retrieval.extract_pdf_text", side_effect=_fake_extract):
            from agents.pdf_retrieval import run_pdf_retrieval

            with caplog.at_level(logging.INFO, logger="agents.pdf_retrieval"):
                await run_pdf_retrieval(papers)

        # One INFO record must mention totals
        info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
        assert any("total=2" in m and "pdfs_retrieved=1" in m and "abstract_only=1" in m for m in info_messages)

    @pytest.mark.asyncio
    async def test_debug_log_per_url(self, caplog):
        papers = [_make_paper("p1", url="https://example.com/p1.pdf")]

        with patch(
            "agents.pdf_retrieval.extract_pdf_text",
            new=AsyncMock(return_value="text"),
        ):
            from agents.pdf_retrieval import run_pdf_retrieval

            with caplog.at_level(logging.DEBUG, logger="agents.pdf_retrieval"):
                await run_pdf_retrieval(papers)

        debug_messages = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("https://example.com/p1.pdf" in m for m in debug_messages)

    @pytest.mark.asyncio
    async def test_info_log_when_include_pdfs_false(self, caplog):
        papers = [_make_paper("p1")]

        with patch("agents.pdf_retrieval.extract_pdf_text", new=AsyncMock()):
            from agents.pdf_retrieval import run_pdf_retrieval

            with caplog.at_level(logging.INFO, logger="agents.pdf_retrieval"):
                await run_pdf_retrieval(papers, include_pdfs=False)

        info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
        assert any("include_pdfs=False" in m for m in info_messages)


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


class TestReturnType:
    @pytest.mark.asyncio
    async def test_always_returns_list(self):
        papers = [_make_paper("p1")]

        with patch(
            "agents.pdf_retrieval.extract_pdf_text",
            new=AsyncMock(return_value="text"),
        ):
            from agents.pdf_retrieval import run_pdf_retrieval

            result = await run_pdf_retrieval(papers)

        assert isinstance(result, list)
        assert all(isinstance(p, Paper) for p in result)
