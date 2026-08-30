"""
Unit tests for backend/tools/scholar_search.py

Tests cover:
- SerpAPI path: successful call returns mapped Paper objects
- SerpAPI path: year extracted from summary string via regex
- SerpAPI path: missing fields fall back to safe defaults
- scholarly path: successful iteration returns mapped Paper objects
- scholarly path: exception returns empty list and logs WARNING
- Cache HIT path: no backend call made
- Cache MISS path: result stored after fetch
- Empty results are not written to cache
- Exception in outer function returns empty list and logs WARNING
- Correct source field ("google_scholar") on all results
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.paper import Paper
from tools.scholar_search import search_google_scholar


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _serpapi_result(
    title: str = "Test Paper",
    snippet: str = "An abstract.",
    link: str = "https://scholar.google.com/test",
    summary: str = "Nature, 2021",
    authors: list[str] | None = None,
) -> dict:
    """Return a fake SerpAPI organic result dict."""
    if authors is None:
        authors = ["Alice Smith", "Bob Jones"]
    return {
        "title": title,
        "snippet": snippet,
        "link": link,
        "publication_info": {
            "summary": summary,
            "authors": [{"name": a} for a in authors],
        },
    }


def _scholarly_pub(
    title: str = "Scholarly Paper",
    authors: list[str] | None = None,
    pub_year: str = "2020",
    venue: str = "ICML",
    abstract: str = "A scholarly abstract.",
    pub_url: str = "https://scholar.google.com/scholarly",
) -> dict:
    """Return a fake scholarly publication dict."""
    if authors is None:
        authors = ["Carol White"]
    return {
        "bib": {
            "title": title,
            "author": authors,
            "pub_year": pub_year,
            "venue": venue,
            "abstract": abstract,
        },
        "pub_url": pub_url,
    }


# ---------------------------------------------------------------------------
# SerpAPI backend tests
# ---------------------------------------------------------------------------


class TestSerpAPIPath:
    @pytest.mark.asyncio
    async def test_returns_papers_on_success(self):
        result = _serpapi_result()
        mock_response = MagicMock()
        mock_response.json.return_value = {"organic_results": [result]}
        mock_response.raise_for_status = MagicMock()

        with patch("tools.scholar_search.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            papers = await search_google_scholar(
                "transformers", max_results=5, serpapi_key="test-key"
            )

        assert len(papers) == 1
        assert isinstance(papers[0], Paper)
        assert papers[0].title == "Test Paper"
        assert papers[0].source == "google_scholar"

    @pytest.mark.asyncio
    async def test_year_extracted_from_summary(self):
        result = _serpapi_result(summary="Journal of AI, 2019, vol 3")
        mock_response = MagicMock()
        mock_response.json.return_value = {"organic_results": [result]}
        mock_response.raise_for_status = MagicMock()

        with patch("tools.scholar_search.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            papers = await search_google_scholar("deep learning", serpapi_key="key")

        assert papers[0].year == 2019

    @pytest.mark.asyncio
    async def test_year_defaults_to_zero_when_no_year_in_summary(self):
        result = _serpapi_result(summary="No year here")
        mock_response = MagicMock()
        mock_response.json.return_value = {"organic_results": [result]}
        mock_response.raise_for_status = MagicMock()

        with patch("tools.scholar_search.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            papers = await search_google_scholar("nlp", serpapi_key="key")

        assert papers[0].year == 0

    @pytest.mark.asyncio
    async def test_missing_fields_fall_back_to_defaults(self):
        """A result with all optional fields absent should not raise."""
        sparse_result: dict = {}  # completely empty
        mock_response = MagicMock()
        mock_response.json.return_value = {"organic_results": [sparse_result]}
        mock_response.raise_for_status = MagicMock()

        with patch("tools.scholar_search.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            papers = await search_google_scholar("robots", serpapi_key="key")

        assert len(papers) == 1
        p = papers[0]
        assert p.title == ""
        assert p.authors == []
        assert p.year == 0
        assert p.journal == "Google Scholar"
        assert p.abstract == ""
        assert p.url == ""
        assert p.doi is None

    @pytest.mark.asyncio
    async def test_num_param_capped_at_20(self):
        """max_results > 20 must be capped at 20 in the API call."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"organic_results": []}
        mock_response.raise_for_status = MagicMock()

        captured_params: list[dict] = []

        async def _fake_get(url: str, params: dict):
            captured_params.append(params)
            return mock_response

        with patch("tools.scholar_search.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = _fake_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await search_google_scholar("ml", max_results=50, serpapi_key="key")

        assert captured_params[0]["num"] == 20

    @pytest.mark.asyncio
    async def test_no_organic_results_key_returns_empty_list(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {}  # no organic_results key
        mock_response.raise_for_status = MagicMock()

        with patch("tools.scholar_search.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            papers = await search_google_scholar("unknown", serpapi_key="key")

        assert papers == []

    @pytest.mark.asyncio
    async def test_authors_field_mapped_correctly(self):
        result = _serpapi_result(authors=["Dr. A", "Prof. B", "C"])
        mock_response = MagicMock()
        mock_response.json.return_value = {"organic_results": [result]}
        mock_response.raise_for_status = MagicMock()

        with patch("tools.scholar_search.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            papers = await search_google_scholar("vision", serpapi_key="key")

        assert papers[0].authors == ["Dr. A", "Prof. B", "C"]


# ---------------------------------------------------------------------------
# scholarly fallback backend tests
# ---------------------------------------------------------------------------


class TestScholarlyPath:
    @pytest.mark.asyncio
    async def test_returns_papers_on_success(self):
        pub = _scholarly_pub()

        def _fake_iter():
            return iter([pub])

        mock_scholarly_module = MagicMock()
        mock_scholarly_module.scholarly.search_pubs.return_value = _fake_iter()

        with patch.dict("sys.modules", {"scholarly": mock_scholarly_module}):
            with patch("tools.scholar_search.asyncio.get_event_loop") as mock_loop_fn:
                loop = MagicMock()
                mock_loop_fn.return_value = loop

                call_count = 0

                async def _fake_run_in_executor(executor, func, *args):
                    nonlocal call_count
                    call_count += 1
                    if call_count == 1:
                        # First call: scholarly.search_pubs → returns an iterator
                        return _fake_iter()
                    # Subsequent calls: next(iterator)
                    return func(*args)

                loop.run_in_executor = _fake_run_in_executor

                with patch("tools.scholar_search.asyncio.sleep", new_callable=AsyncMock):
                    papers = await search_google_scholar("attention", max_results=1)

        assert len(papers) == 1
        assert papers[0].title == "Scholarly Paper"
        assert papers[0].source == "google_scholar"
        assert papers[0].year == 2020

    @pytest.mark.asyncio
    async def test_author_as_single_string_is_wrapped_in_list(self):
        pub = _scholarly_pub()
        pub["bib"]["author"] = "Single Author"  # string, not list

        def _fake_iter():
            return iter([pub])

        mock_scholarly_module = MagicMock()

        with patch.dict("sys.modules", {"scholarly": mock_scholarly_module}):
            with patch("tools.scholar_search.asyncio.get_event_loop") as mock_loop_fn:
                loop = MagicMock()
                mock_loop_fn.return_value = loop

                call_count = 0

                async def _fake_run_in_executor(executor, func, *args):
                    nonlocal call_count
                    call_count += 1
                    if call_count == 1:
                        return _fake_iter()
                    return func(*args)

                loop.run_in_executor = _fake_run_in_executor

                with patch("tools.scholar_search.asyncio.sleep", new_callable=AsyncMock):
                    papers = await search_google_scholar("robotics", max_results=1)

        assert papers[0].authors == ["Single Author"]

    @pytest.mark.asyncio
    async def test_missing_pub_year_defaults_to_zero(self):
        pub = _scholarly_pub(pub_year="")
        pub["bib"]["pub_year"] = None

        def _fake_iter():
            return iter([pub])

        mock_scholarly_module = MagicMock()

        with patch.dict("sys.modules", {"scholarly": mock_scholarly_module}):
            with patch("tools.scholar_search.asyncio.get_event_loop") as mock_loop_fn:
                loop = MagicMock()
                mock_loop_fn.return_value = loop
                call_count = 0

                async def _fake_run_in_executor(executor, func, *args):
                    nonlocal call_count
                    call_count += 1
                    if call_count == 1:
                        return _fake_iter()
                    return func(*args)

                loop.run_in_executor = _fake_run_in_executor

                with patch("tools.scholar_search.asyncio.sleep", new_callable=AsyncMock):
                    papers = await search_google_scholar("bert", max_results=1)

        assert papers[0].year == 0

    @pytest.mark.asyncio
    async def test_scholarly_exception_returns_empty_list(self, caplog):
        import logging

        mock_scholarly_module = MagicMock()

        with patch.dict("sys.modules", {"scholarly": mock_scholarly_module}):
            with patch("tools.scholar_search.asyncio.get_event_loop") as mock_loop_fn:
                loop = MagicMock()
                mock_loop_fn.return_value = loop

                async def _raise(_executor, _func, *_args):
                    raise RuntimeError("scholarly exploded")

                loop.run_in_executor = _raise

                with caplog.at_level(logging.WARNING, logger="tools.scholar_search"):
                    papers = await search_google_scholar("nlp")

        assert papers == []
        assert any("WARNING" in r.levelname for r in caplog.records)


# ---------------------------------------------------------------------------
# Cache behaviour tests
# ---------------------------------------------------------------------------


class TestCacheBehaviour:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_backend(self):
        cached_papers = [
            Paper(
                paper_id="cached-id",
                title="Cached Paper",
                authors=["Dave"],
                year=2021,
                journal="Google Scholar",
                abstract="Cached.",
                url="https://scholar.google.com/cached",
                source="google_scholar",
            )
        ]
        cache = _FakeCache(initial={"scholar:nlp:10": cached_papers})

        # Neither httpx nor scholarly should be called on a cache hit.
        with patch(
            "tools.scholar_search.httpx.AsyncClient", side_effect=AssertionError("httpx called on cache hit")
        ):
            papers = await search_google_scholar(
                "nlp", max_results=10, cache=cache, serpapi_key="key"
            )

        assert papers == cached_papers

    @pytest.mark.asyncio
    async def test_cache_miss_stores_result_with_correct_key_and_ttl(self):
        result = _serpapi_result()
        mock_response = MagicMock()
        mock_response.json.return_value = {"organic_results": [result]}
        mock_response.raise_for_status = MagicMock()
        cache = _FakeCache()

        with patch("tools.scholar_search.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            papers = await search_google_scholar(
                "deep learning", max_results=5, cache=cache, serpapi_key="key"
            )

        assert len(cache.set_calls) == 1
        key, stored, ttl = cache.set_calls[0]
        assert key == "scholar:deep learning:5"
        assert stored == papers
        assert ttl == 86400

    @pytest.mark.asyncio
    async def test_empty_results_not_written_to_cache(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"organic_results": []}
        mock_response.raise_for_status = MagicMock()
        cache = _FakeCache()

        with patch("tools.scholar_search.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            papers = await search_google_scholar(
                "obscure xyz", cache=cache, serpapi_key="key"
            )

        assert papers == []
        assert cache.set_calls == []

    @pytest.mark.asyncio
    async def test_no_cache_provided_works(self):
        result = _serpapi_result()
        mock_response = MagicMock()
        mock_response.json.return_value = {"organic_results": [result]}
        mock_response.raise_for_status = MagicMock()

        with patch("tools.scholar_search.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            papers = await search_google_scholar("ai safety", serpapi_key="key")

        assert len(papers) == 1


# ---------------------------------------------------------------------------
# Logging tests
# ---------------------------------------------------------------------------


class TestLogging:
    @pytest.mark.asyncio
    async def test_info_log_serpapi_path(self, caplog):
        import logging

        mock_response = MagicMock()
        mock_response.json.return_value = {"organic_results": []}
        mock_response.raise_for_status = MagicMock()

        with patch("tools.scholar_search.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with caplog.at_level(logging.INFO, logger="tools.scholar_search"):
                await search_google_scholar("ml", serpapi_key="key")

        messages = " ".join(r.message for r in caplog.records)
        assert "SerpAPI" in messages

    @pytest.mark.asyncio
    async def test_info_log_scholarly_path(self, caplog):
        import logging

        mock_scholarly_module = MagicMock()

        with patch.dict("sys.modules", {"scholarly": mock_scholarly_module}):
            with patch("tools.scholar_search.asyncio.get_event_loop") as mock_loop_fn:
                loop = MagicMock()
                mock_loop_fn.return_value = loop

                async def _raise(_executor, _func, *_args):
                    raise StopIteration

                loop.run_in_executor = _raise

                with caplog.at_level(logging.INFO, logger="tools.scholar_search"):
                    await search_google_scholar("transformers")

        messages = " ".join(r.message for r in caplog.records)
        assert "scholarly" in messages

    @pytest.mark.asyncio
    async def test_warning_on_exception(self, caplog):
        import logging

        with patch("tools.scholar_search.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=RuntimeError("network error"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with caplog.at_level(logging.WARNING, logger="tools.scholar_search"):
                papers = await search_google_scholar("rl", serpapi_key="bad-key")

        assert papers == []
        assert any("WARNING" in r.levelname for r in caplog.records)
