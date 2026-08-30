"""
Unit tests for backend/tools/pdf_extractor.py

Tests cover:
- Successful PDF download and text extraction
- Cache HIT path (no HTTP call made)
- Cache MISS path (HTTP called, result stored with TTL=3600)
- Content-type guard: non-PDF content-type without .pdf extension → None + INFO log
- Content-type guard: .pdf URL suffix bypasses content-type check
- Empty extracted text returns None and is not cached
- Exception during HTTP download logs WARNING and returns None
- Exception during PDF parsing logs WARNING and returns None
- Text is normalised (whitespace collapsed) and truncated to 50 000 chars
"""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeCache:
    """Minimal async cache double."""

    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self._store: dict[str, Any] = dict(initial or {})
        self.set_calls: list[tuple] = []

    async def get(self, key: str) -> Any | None:
        return self._store.get(key)

    async def set(self, key: str, value: Any, ttl_seconds: int = 86400) -> None:
        self._store[key] = value
        self.set_calls.append((key, value, ttl_seconds))


def _make_response(
    content: bytes = b"",
    content_type: str = "application/pdf",
    status_code: int = 200,
) -> MagicMock:
    """Return a mock httpx.Response."""
    resp = MagicMock()
    resp.content = content
    resp.headers = {"content-type": content_type}
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


def _make_pdf_reader(pages_text: list[str]) -> MagicMock:
    """Return a mock PdfReader whose .pages yield text via extract_text()."""
    pages = []
    for text in pages_text:
        page = MagicMock()
        page.extract_text.return_value = text
        pages.append(page)
    reader = MagicMock()
    reader.pages = pages
    return reader


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExtractPdfTextSuccess:
    @pytest.mark.asyncio
    async def test_returns_extracted_text(self):
        reader = _make_pdf_reader(["Hello world ", "  page two  "])
        resp = _make_response(content=b"%PDF-fake", content_type="application/pdf")

        async_cm = AsyncMock()
        async_cm.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=resp)))
        async_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("tools.pdf_extractor.httpx.AsyncClient", return_value=async_cm), \
             patch("tools.pdf_extractor.PdfReader", return_value=reader, create=True):
            from tools.pdf_extractor import extract_pdf_text
            result = await extract_pdf_text("https://example.com/paper.pdf")

        assert result == "Hello world page two"

    @pytest.mark.asyncio
    async def test_text_truncated_to_50000_chars(self):
        long_text = "A" * 60_000
        reader = _make_pdf_reader([long_text])
        resp = _make_response(content=b"%PDF-fake", content_type="application/pdf")

        async_cm = AsyncMock()
        async_cm.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=resp)))
        async_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("tools.pdf_extractor.httpx.AsyncClient", return_value=async_cm), \
             patch("tools.pdf_extractor.PdfReader", return_value=reader, create=True):
            from tools.pdf_extractor import extract_pdf_text
            result = await extract_pdf_text("https://example.com/big.pdf")

        assert result is not None
        assert len(result) == 50_000

    @pytest.mark.asyncio
    async def test_whitespace_normalised(self):
        reader = _make_pdf_reader(["  lots   of\t\twhitespace\n\nhere  "])
        resp = _make_response(content=b"%PDF-fake", content_type="application/pdf")

        async_cm = AsyncMock()
        async_cm.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=resp)))
        async_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("tools.pdf_extractor.httpx.AsyncClient", return_value=async_cm), \
             patch("tools.pdf_extractor.PdfReader", return_value=reader, create=True):
            from tools.pdf_extractor import extract_pdf_text
            result = await extract_pdf_text("https://example.com/paper.pdf")

        assert result == "lots of whitespace here"

    @pytest.mark.asyncio
    async def test_page_none_extract_text_handled(self):
        """Pages where extract_text() returns None should be treated as empty."""
        reader = _make_pdf_reader([None, "real text"])  # type: ignore[list-item]
        # Override extract_text to return None for first page
        reader.pages[0].extract_text.return_value = None

        resp = _make_response(content=b"%PDF-fake", content_type="application/pdf")

        async_cm = AsyncMock()
        async_cm.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=resp)))
        async_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("tools.pdf_extractor.httpx.AsyncClient", return_value=async_cm), \
             patch("tools.pdf_extractor.PdfReader", return_value=reader, create=True):
            from tools.pdf_extractor import extract_pdf_text
            result = await extract_pdf_text("https://example.com/paper.pdf")

        assert result == "real text"


class TestExtractPdfTextCache:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_http(self):
        cached_text = "previously extracted text"
        cache = _FakeCache(initial={"pdf:https://example.com/paper.pdf": cached_text})

        async_cm = AsyncMock()
        async_cm.__aenter__ = AsyncMock(
            side_effect=AssertionError("should not call HTTP on cache hit")
        )

        with patch("tools.pdf_extractor.httpx.AsyncClient", return_value=async_cm):
            from tools.pdf_extractor import extract_pdf_text
            result = await extract_pdf_text("https://example.com/paper.pdf", cache=cache)

        assert result == cached_text

    @pytest.mark.asyncio
    async def test_cache_miss_stores_result_with_ttl_3600(self):
        reader = _make_pdf_reader(["stored text"])
        resp = _make_response(content=b"%PDF-fake", content_type="application/pdf")
        cache = _FakeCache()

        async_cm = AsyncMock()
        async_cm.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=resp)))
        async_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("tools.pdf_extractor.httpx.AsyncClient", return_value=async_cm), \
             patch("tools.pdf_extractor.PdfReader", return_value=reader, create=True):
            from tools.pdf_extractor import extract_pdf_text
            result = await extract_pdf_text("https://example.com/paper.pdf", cache=cache)

        assert result == "stored text"
        assert len(cache.set_calls) == 1
        key, stored, ttl = cache.set_calls[0]
        assert key == "pdf:https://example.com/paper.pdf"
        assert stored == "stored text"
        assert ttl == 3600

    @pytest.mark.asyncio
    async def test_empty_text_not_stored_in_cache(self):
        """Empty extraction result should not be written to cache."""
        reader = _make_pdf_reader([""])
        resp = _make_response(content=b"%PDF-fake", content_type="application/pdf")
        cache = _FakeCache()

        async_cm = AsyncMock()
        async_cm.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=resp)))
        async_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("tools.pdf_extractor.httpx.AsyncClient", return_value=async_cm), \
             patch("tools.pdf_extractor.PdfReader", return_value=reader, create=True):
            from tools.pdf_extractor import extract_pdf_text
            result = await extract_pdf_text("https://example.com/empty.pdf", cache=cache)

        assert result is None
        assert cache.set_calls == []


class TestExtractPdfTextContentTypeGuard:
    @pytest.mark.asyncio
    async def test_non_pdf_content_type_non_pdf_url_returns_none(self, caplog):
        import logging

        resp = _make_response(content=b"<html>...</html>", content_type="text/html")

        async_cm = AsyncMock()
        async_cm.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=resp)))
        async_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("tools.pdf_extractor.httpx.AsyncClient", return_value=async_cm):
            from tools.pdf_extractor import extract_pdf_text
            with caplog.at_level(logging.INFO, logger="tools.pdf_extractor"):
                result = await extract_pdf_text("https://example.com/paper")

        assert result is None
        assert any("skipping non-PDF" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_pdf_url_suffix_bypasses_content_type_check(self):
        """A URL ending in .pdf should be processed even with non-pdf content-type."""
        reader = _make_pdf_reader(["some pdf text"])
        resp = _make_response(
            content=b"%PDF-fake",
            content_type="application/octet-stream",  # non-pdf content-type
        )

        async_cm = AsyncMock()
        async_cm.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=resp)))
        async_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("tools.pdf_extractor.httpx.AsyncClient", return_value=async_cm), \
             patch("tools.pdf_extractor.PdfReader", return_value=reader, create=True):
            from tools.pdf_extractor import extract_pdf_text
            result = await extract_pdf_text("https://example.com/paper.pdf")

        assert result == "some pdf text"

    @pytest.mark.asyncio
    async def test_application_pdf_content_type_processed(self):
        """application/pdf content-type should always be processed regardless of URL."""
        reader = _make_pdf_reader(["pdf content here"])
        resp = _make_response(content=b"%PDF-fake", content_type="application/pdf")

        async_cm = AsyncMock()
        async_cm.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=resp)))
        async_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("tools.pdf_extractor.httpx.AsyncClient", return_value=async_cm), \
             patch("tools.pdf_extractor.PdfReader", return_value=reader, create=True):
            from tools.pdf_extractor import extract_pdf_text
            result = await extract_pdf_text("https://example.com/no-extension")

        assert result == "pdf content here"


class TestExtractPdfTextErrorHandling:
    @pytest.mark.asyncio
    async def test_http_exception_returns_none_and_logs_warning(self, caplog):
        import logging

        async_cm = AsyncMock()
        async_cm.__aenter__ = AsyncMock(
            side_effect=Exception("network error")
        )
        async_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("tools.pdf_extractor.httpx.AsyncClient", return_value=async_cm):
            from tools.pdf_extractor import extract_pdf_text
            with caplog.at_level(logging.WARNING, logger="tools.pdf_extractor"):
                result = await extract_pdf_text("https://example.com/paper.pdf")

        assert result is None
        assert any("WARNING" in r.levelname for r in caplog.records)

    @pytest.mark.asyncio
    async def test_pdf_parse_exception_returns_none_and_logs_warning(self, caplog):
        import logging

        resp = _make_response(content=b"not-valid-pdf", content_type="application/pdf")

        async_cm = AsyncMock()
        async_cm.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=resp)))
        async_cm.__aexit__ = AsyncMock(return_value=False)

        broken_reader = MagicMock(side_effect=Exception("PDF parse error"))

        with patch("tools.pdf_extractor.httpx.AsyncClient", return_value=async_cm), \
             patch("tools.pdf_extractor.PdfReader", broken_reader, create=True):
            from tools.pdf_extractor import extract_pdf_text
            with caplog.at_level(logging.WARNING, logger="tools.pdf_extractor"):
                result = await extract_pdf_text("https://example.com/bad.pdf")

        assert result is None
        assert any("WARNING" in r.levelname for r in caplog.records)

    @pytest.mark.asyncio
    async def test_no_cache_provided_still_works(self):
        reader = _make_pdf_reader(["text without cache"])
        resp = _make_response(content=b"%PDF-fake", content_type="application/pdf")

        async_cm = AsyncMock()
        async_cm.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=resp)))
        async_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("tools.pdf_extractor.httpx.AsyncClient", return_value=async_cm), \
             patch("tools.pdf_extractor.PdfReader", return_value=reader, create=True):
            from tools.pdf_extractor import extract_pdf_text
            result = await extract_pdf_text("https://example.com/paper.pdf")

        assert result == "text without cache"
