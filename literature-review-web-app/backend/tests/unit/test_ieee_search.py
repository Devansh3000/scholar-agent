"""
Unit tests for backend/tools/ieee_search.py

Tests cover:
- Empty api_key logs WARNING and returns [] immediately (no HTTP call)
- Cache HIT returns cached result without making an HTTP request
- Cache MISS triggers HTTP call and stores result with correct TTL (86400 s)
- Cache key format: "ieee:<query>:<max_results>"
- Correct field mapping from IEEE article dict to Paper
- paper_id falls back to uuid4() when article_number is absent
- year defaults to 0 when publication_year is absent/None
- url resolution: html_url preferred over pdf_url; empty string if both absent
- doi is None when not in article dict
- HTTP error (non-2xx) → logs WARNING and returns []
- Exception during HTTP call → logs WARNING and returns []
- Empty results are not written to cache
- max_records is capped at 200
- source field is always "ieee"
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from models.paper import Paper
from tools.ieee_search import search_ieee, _map_article_to_paper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_article(**kwargs: Any) -> dict[str, Any]:
    """Return a well-formed IEEE Xplore article dict with optional overrides."""
    base: dict[str, Any] = {
        "article_number": "9999999",
        "title": "A Survey on Deep Learning",
        "authors": {
            "authors": [
                {"full_name": "Alice Smith"},
                {"full_name": "Bob Jones"},
            ]
        },
        "publication_year": "2022",
        "publication_title": "IEEE Transactions on Neural Networks",
        "abstract": "An interesting abstract.",
        "html_url": "https://ieeexplore.ieee.org/document/9999999",
        "pdf_url": "",
        "doi": "10.1109/TNNLS.2022.999",
    }
    base.update(kwargs)
    return base


class _FakeCache:
    """Minimal async cache double."""

    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self._store: dict[str, Any] = dict(initial or {})
        self.set_calls: list[tuple[str, Any, int]] = []

    async def get(self, key: str) -> Any | None:
        return self._store.get(key)

    async def set(self, key: str, value: Any, ttl_seconds: int = 86400) -> None:
        self._store[key] = value
        self.set_calls.append((key, value, ttl_seconds))


def _mock_response(articles: list[dict[str, Any]], status_code: int = 200) -> MagicMock:
    """Build a mock httpx.Response that returns the given article list."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = {"articles": articles}
    # raise_for_status: no-op for 2xx, raises HTTPStatusError otherwise
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=resp,
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# _map_article_to_paper unit tests
# ---------------------------------------------------------------------------


class TestMapArticleToPaper:
    def test_basic_mapping(self):
        article = _make_article()
        paper = _map_article_to_paper(article)

        assert isinstance(paper, Paper)
        assert paper.paper_id == "9999999"
        assert paper.title == "A Survey on Deep Learning"
        assert paper.authors == ["Alice Smith", "Bob Jones"]
        assert paper.year == 2022
        assert paper.journal == "IEEE Transactions on Neural Networks"
        assert paper.abstract == "An interesting abstract."
        assert paper.url == "https://ieeexplore.ieee.org/document/9999999"
        assert paper.source == "ieee"
        assert paper.doi == "10.1109/TNNLS.2022.999"

    def test_missing_article_number_generates_uuid(self):
        article = _make_article(article_number="")
        paper = _map_article_to_paper(article)
        assert len(paper.paper_id) == 36  # uuid4 canonical form

    def test_absent_article_number_key_generates_uuid(self):
        article = _make_article()
        del article["article_number"]
        paper = _map_article_to_paper(article)
        assert len(paper.paper_id) == 36

    def test_year_defaults_to_zero_when_absent(self):
        article = _make_article()
        del article["publication_year"]
        paper = _map_article_to_paper(article)
        assert paper.year == 0

    def test_year_defaults_to_zero_when_none(self):
        article = _make_article(publication_year=None)
        paper = _map_article_to_paper(article)
        assert paper.year == 0

    def test_html_url_preferred_over_pdf_url(self):
        article = _make_article(
            html_url="https://example.com/html",
            pdf_url="https://example.com/pdf",
        )
        paper = _map_article_to_paper(article)
        assert paper.url == "https://example.com/html"

    def test_pdf_url_used_when_html_url_empty(self):
        article = _make_article(html_url="", pdf_url="https://example.com/pdf")
        paper = _map_article_to_paper(article)
        assert paper.url == "https://example.com/pdf"

    def test_url_empty_when_both_absent(self):
        article = _make_article(html_url="", pdf_url="")
        paper = _map_article_to_paper(article)
        assert paper.url == ""

    def test_doi_none_when_absent(self):
        article = _make_article()
        del article["doi"]
        paper = _map_article_to_paper(article)
        assert paper.doi is None

    def test_journal_defaults_to_ieee(self):
        article = _make_article()
        del article["publication_title"]
        paper = _map_article_to_paper(article)
        assert paper.journal == "IEEE"

    def test_empty_authors_list(self):
        article = _make_article(authors={"authors": []})
        paper = _map_article_to_paper(article)
        assert paper.authors == []

    def test_missing_authors_key(self):
        article = _make_article(authors={})
        paper = _map_article_to_paper(article)
        assert paper.authors == []

    def test_source_is_ieee(self):
        paper = _map_article_to_paper(_make_article())
        assert paper.source == "ieee"


# ---------------------------------------------------------------------------
# search_ieee async tests
# ---------------------------------------------------------------------------


class TestSearchIeeeNoApiKey:
    @pytest.mark.asyncio
    async def test_empty_api_key_returns_empty_list(self):
        result = await search_ieee("deep learning", api_key="")
        assert result == []

    @pytest.mark.asyncio
    async def test_empty_api_key_logs_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="tools.ieee_search"):
            await search_ieee("deep learning", api_key="")

        messages = " ".join(r.message for r in caplog.records)
        assert "IEEE_API_KEY not configured" in messages

    @pytest.mark.asyncio
    async def test_empty_api_key_no_http_call(self):
        with patch("httpx.AsyncClient") as mock_client_cls:
            await search_ieee("deep learning", api_key="")
        mock_client_cls.assert_not_called()


class TestSearchIeeeCaching:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_papers(self):
        cached = [
            Paper(
                paper_id="1234",
                title="Cached IEEE Paper",
                authors=["Eve"],
                year=2021,
                journal="IEEE",
                abstract="abs",
                url="https://ieeexplore.ieee.org/document/1234",
                source="ieee",
            )
        ]
        cache = _FakeCache(initial={"ieee:deep learning:10": cached})

        with patch("httpx.AsyncClient") as mock_client_cls:
            result = await search_ieee("deep learning", max_results=10, cache=cache, api_key="key")

        mock_client_cls.assert_not_called()
        assert result == cached

    @pytest.mark.asyncio
    async def test_cache_miss_stores_result_with_correct_ttl(self):
        article = _make_article()
        resp = _mock_response([article])
        cache = _FakeCache()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            papers = await search_ieee("neural networks", max_results=5, cache=cache, api_key="key")

        assert len(papers) == 1
        assert len(cache.set_calls) == 1
        key, stored, ttl = cache.set_calls[0]
        assert key == "ieee:neural networks:5"
        assert stored == papers
        assert ttl == 86400

    @pytest.mark.asyncio
    async def test_cache_key_format(self):
        article = _make_article()
        resp = _mock_response([article])
        cache = _FakeCache()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await search_ieee("my query", max_results=7, cache=cache, api_key="k")

        assert cache.set_calls[0][0] == "ieee:my query:7"

    @pytest.mark.asyncio
    async def test_empty_results_not_written_to_cache(self):
        resp = _mock_response([])
        cache = _FakeCache()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await search_ieee("obscure", cache=cache, api_key="key")

        assert result == []
        assert cache.set_calls == []


class TestSearchIeeeHttpRequest:
    @pytest.mark.asyncio
    async def test_max_records_capped_at_200(self):
        resp = _mock_response([])

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await search_ieee("test", max_results=500, api_key="key")

        call_kwargs = mock_client.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs.args[1] if len(call_kwargs.args) > 1 else {}
        # Extract params from positional or keyword args
        if "params" in call_kwargs.kwargs:
            params = call_kwargs.kwargs["params"]
        else:
            params = call_kwargs.kwargs.get("params", {})
        assert params["max_records"] == 200

    @pytest.mark.asyncio
    async def test_max_records_uses_requested_value_when_under_200(self):
        resp = _mock_response([])

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await search_ieee("test", max_results=50, api_key="key")

        call_kwargs = mock_client.get.call_args
        params = call_kwargs.kwargs["params"]
        assert params["max_records"] == 50

    @pytest.mark.asyncio
    async def test_correct_base_url_called(self):
        resp = _mock_response([])

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await search_ieee("transformers", api_key="key")

        url_called = mock_client.get.call_args.args[0]
        assert url_called == "https://ieeexploreapi.ieee.org/api/v1/search/articles"

    @pytest.mark.asyncio
    async def test_api_key_in_params(self):
        resp = _mock_response([])

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await search_ieee("transformers", api_key="my-secret-key")

        params = mock_client.get.call_args.kwargs["params"]
        assert params["apikey"] == "my-secret-key"

    @pytest.mark.asyncio
    async def test_returns_mapped_papers_on_success(self):
        articles = [_make_article(), _make_article(article_number="8888888", title="Second Paper")]
        resp = _mock_response(articles)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            papers = await search_ieee("neural networks", api_key="key")

        assert len(papers) == 2
        assert papers[0].paper_id == "9999999"
        assert papers[1].paper_id == "8888888"
        assert papers[1].title == "Second Paper"


class TestSearchIeeeErrorHandling:
    @pytest.mark.asyncio
    async def test_http_error_returns_empty_list(self):
        resp = _mock_response([], status_code=429)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await search_ieee("test", api_key="key")

        assert result == []

    @pytest.mark.asyncio
    async def test_http_error_logs_warning(self, caplog):
        resp = _mock_response([], status_code=500)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=resp)

        with patch("httpx.AsyncClient", return_value=mock_client), \
             caplog.at_level(logging.WARNING, logger="tools.ieee_search"):
            await search_ieee("test", api_key="key")

        assert any(r.levelno >= logging.WARNING for r in caplog.records)

    @pytest.mark.asyncio
    async def test_network_exception_returns_empty_list(self):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("unreachable"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await search_ieee("test", api_key="key")

        assert result == []

    @pytest.mark.asyncio
    async def test_network_exception_logs_warning(self, caplog):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with patch("httpx.AsyncClient", return_value=mock_client), \
             caplog.at_level(logging.WARNING, logger="tools.ieee_search"):
            await search_ieee("test", api_key="key")

        assert any(r.levelno >= logging.WARNING for r in caplog.records)

    @pytest.mark.asyncio
    async def test_no_api_call_when_cache_hit(self):
        """Confirm no HTTP client is instantiated on a cache hit."""
        cached = [
            Paper(
                paper_id="x1",
                title="Hit",
                authors=[],
                year=2020,
                journal="IEEE",
                abstract="",
                url="",
                source="ieee",
            )
        ]
        cache = _FakeCache(initial={"ieee:query:20": cached})

        with patch("httpx.AsyncClient") as mock_cls:
            result = await search_ieee("query", cache=cache, api_key="k")

        mock_cls.assert_not_called()
        assert result == cached
