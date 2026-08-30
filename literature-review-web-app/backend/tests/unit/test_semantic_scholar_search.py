"""
Unit tests for backend/tools/semantic_scholar_search.py

Tests cover:
- Cache HIT returns cached result without calling API
- Cache MISS triggers API call and stores result
- Rate-limit sleep (1 s) applied when api_key is empty
- No sleep when api_key is provided
- Paper field mapping: paperId, title, authors (dict and object), year,
  venue/journal resolution, abstract, url, doi
- Missing / None fields fall back to safe defaults
- Fallback paper_id (uuid4) when paperId is absent
- Exception in API call → logs WARNING and returns []
- CacheService.set receives correct TTL (86400 s)
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.paper import Paper
from tools.semantic_scholar_search import search_semantic_scholar


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_raw_paper(**kwargs) -> SimpleNamespace:
    """Build a minimal fake Semantic Scholar paper result object."""
    defaults = {
        "paperId": "abc123",
        "title": "A Great Paper",
        "authors": [{"name": "Alice"}, {"name": "Bob"}],
        "year": 2023,
        "venue": "NeurIPS",
        "journal": None,
        "abstract": "An interesting abstract.",
        "externalIds": {"DOI": "10.1000/xyz"},
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


async def _noop_sleep(_):
    """Replacement for asyncio.sleep that does nothing."""


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------


class TestCacheInteraction:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_papers(self):
        """When cache returns data, the API must not be called."""
        cached_papers = [
            Paper(
                paper_id="p1",
                title="Cached",
                authors=["Alice"],
                year=2022,
                journal="NeurIPS",
                abstract="abs",
                url="https://semanticscholar.org/paper/p1",
                source="semantic_scholar",
            )
        ]
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=cached_papers)

        with patch("tools.semantic_scholar_search.SemanticScholar") as mock_ss_cls:
            result = await search_semantic_scholar(
                "transformers", max_results=5, cache=mock_cache
            )

        mock_ss_cls.assert_not_called()
        assert result == cached_papers

    @pytest.mark.asyncio
    async def test_cache_miss_calls_api_and_stores(self):
        """On cache MISS, results are fetched and stored with correct TTL."""
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        raw = [_make_raw_paper()]

        def _fake_ss(*_, **__):
            inst = MagicMock()
            inst.search_paper.return_value = raw
            return inst

        with patch("tools.semantic_scholar_search.SemanticScholar", side_effect=_fake_ss), \
             patch("asyncio.sleep", side_effect=_noop_sleep):
            result = await search_semantic_scholar(
                "neural networks", max_results=10, cache=mock_cache, api_key="key"
            )

        assert len(result) == 1
        # cache.set must have been called with the correct key and TTL
        mock_cache.set.assert_awaited_once()
        call_kwargs = mock_cache.set.call_args
        assert call_kwargs.kwargs.get("ttl_seconds") == 86400 or \
               (len(call_kwargs.args) >= 3 and call_kwargs.args[2] == 86400) or \
               call_kwargs.kwargs.get("ttl_seconds") == 86400

    @pytest.mark.asyncio
    async def test_cache_key_format(self):
        """Cache key must be 's2:<query>:<max_results>'."""
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        raw = [_make_raw_paper()]

        def _fake_ss(*_, **__):
            inst = MagicMock()
            inst.search_paper.return_value = raw
            return inst

        with patch("tools.semantic_scholar_search.SemanticScholar", side_effect=_fake_ss), \
             patch("asyncio.sleep", side_effect=_noop_sleep):
            await search_semantic_scholar("my query", max_results=7, cache=mock_cache, api_key="k")

        get_call_key = mock_cache.get.call_args.args[0]
        assert get_call_key == "s2:my query:7"


# ---------------------------------------------------------------------------
# Rate-limit sleep
# ---------------------------------------------------------------------------


class TestRateLimiting:
    @pytest.mark.asyncio
    async def test_sleep_applied_when_no_api_key(self):
        """A 1.0 s sleep is injected when api_key is empty."""
        raw = [_make_raw_paper()]

        def _fake_ss(*_, **__):
            inst = MagicMock()
            inst.search_paper.return_value = raw
            return inst

        sleep_calls: list[float] = []

        async def recording_sleep(delay: float):
            sleep_calls.append(delay)

        with patch("tools.semantic_scholar_search.SemanticScholar", side_effect=_fake_ss), \
             patch("asyncio.sleep", side_effect=recording_sleep):
            await search_semantic_scholar("query", api_key="")

        assert sleep_calls == [1.0]

    @pytest.mark.asyncio
    async def test_no_sleep_when_api_key_provided(self):
        """No rate-limit sleep when a non-empty api_key is given."""
        raw = [_make_raw_paper()]

        def _fake_ss(*_, **__):
            inst = MagicMock()
            inst.search_paper.return_value = raw
            return inst

        sleep_calls: list[float] = []

        async def recording_sleep(delay: float):
            sleep_calls.append(delay)

        with patch("tools.semantic_scholar_search.SemanticScholar", side_effect=_fake_ss), \
             patch("asyncio.sleep", side_effect=recording_sleep):
            await search_semantic_scholar("query", api_key="my-key")

        assert sleep_calls == []


# ---------------------------------------------------------------------------
# Paper field mapping
# ---------------------------------------------------------------------------


class TestPaperMapping:
    @pytest.mark.asyncio
    async def test_basic_field_mapping(self):
        """Core fields are mapped correctly from a well-formed API result."""
        raw = _make_raw_paper(
            paperId="s2id1",
            title="Deep Learning",
            authors=[{"name": "LeCun"}, {"name": "Bengio"}],
            year=2015,
            venue="Nature",
            journal=None,
            abstract="A seminal paper.",
            externalIds={"DOI": "10.1038/nature14539"},
        )

        def _fake_ss(*_, **__):
            inst = MagicMock()
            inst.search_paper.return_value = [raw]
            return inst

        with patch("tools.semantic_scholar_search.SemanticScholar", side_effect=_fake_ss), \
             patch("asyncio.sleep", side_effect=_noop_sleep):
            papers = await search_semantic_scholar("deep learning", api_key="k")

        assert len(papers) == 1
        p = papers[0]
        assert p.paper_id == "s2id1"
        assert p.title == "Deep Learning"
        assert p.authors == ["LeCun", "Bengio"]
        assert p.year == 2015
        assert p.journal == "Nature"
        assert p.abstract == "A seminal paper."
        assert p.url == "https://semanticscholar.org/paper/s2id1"
        assert p.source == "semantic_scholar"
        assert p.doi == "10.1038/nature14539"

    @pytest.mark.asyncio
    async def test_authors_as_objects(self):
        """Authors that are objects with a .name attribute are also handled."""
        author_obj = SimpleNamespace(name="Turing")
        raw = _make_raw_paper(authors=[author_obj])

        def _fake_ss(*_, **__):
            inst = MagicMock()
            inst.search_paper.return_value = [raw]
            return inst

        with patch("tools.semantic_scholar_search.SemanticScholar", side_effect=_fake_ss), \
             patch("asyncio.sleep", side_effect=_noop_sleep):
            papers = await search_semantic_scholar("turing", api_key="k")

        assert papers[0].authors == ["Turing"]

    @pytest.mark.asyncio
    async def test_journal_fallback_to_journal_dict(self):
        """When venue is empty, fall back to journal dict 'name' key."""
        raw = _make_raw_paper(
            venue="",
            journal={"name": "JMLR", "volume": "12"},
        )

        def _fake_ss(*_, **__):
            inst = MagicMock()
            inst.search_paper.return_value = [raw]
            return inst

        with patch("tools.semantic_scholar_search.SemanticScholar", side_effect=_fake_ss), \
             patch("asyncio.sleep", side_effect=_noop_sleep):
            papers = await search_semantic_scholar("jmlr", api_key="k")

        assert papers[0].journal == "JMLR"

    @pytest.mark.asyncio
    async def test_journal_fallback_to_journal_object(self):
        """When venue is empty and journal is an object, use .name attribute."""
        raw = _make_raw_paper(
            venue="",
            journal=SimpleNamespace(name="ICML"),
        )

        def _fake_ss(*_, **__):
            inst = MagicMock()
            inst.search_paper.return_value = [raw]
            return inst

        with patch("tools.semantic_scholar_search.SemanticScholar", side_effect=_fake_ss), \
             patch("asyncio.sleep", side_effect=_noop_sleep):
            papers = await search_semantic_scholar("icml", api_key="k")

        assert papers[0].journal == "ICML"

    @pytest.mark.asyncio
    async def test_journal_final_fallback_to_semantic_scholar(self):
        """When both venue and journal are absent, default to 'Semantic Scholar'."""
        raw = _make_raw_paper(venue=None, journal=None)

        def _fake_ss(*_, **__):
            inst = MagicMock()
            inst.search_paper.return_value = [raw]
            return inst

        with patch("tools.semantic_scholar_search.SemanticScholar", side_effect=_fake_ss), \
             patch("asyncio.sleep", side_effect=_noop_sleep):
            papers = await search_semantic_scholar("q", api_key="k")

        assert papers[0].journal == "Semantic Scholar"

    @pytest.mark.asyncio
    async def test_missing_paper_id_generates_uuid(self):
        """When paperId is None/empty a UUID is generated and URL is empty."""
        raw = _make_raw_paper(paperId=None)

        def _fake_ss(*_, **__):
            inst = MagicMock()
            inst.search_paper.return_value = [raw]
            return inst

        with patch("tools.semantic_scholar_search.SemanticScholar", side_effect=_fake_ss), \
             patch("asyncio.sleep", side_effect=_noop_sleep):
            papers = await search_semantic_scholar("q", api_key="k")

        p = papers[0]
        # paper_id must be a non-empty string (a UUID)
        assert isinstance(p.paper_id, str)
        assert len(p.paper_id) == 36  # uuid4 canonical form
        assert p.url == ""

    @pytest.mark.asyncio
    async def test_missing_doi_is_none(self):
        """No DOI in externalIds → doi field is None."""
        raw = _make_raw_paper(externalIds={})

        def _fake_ss(*_, **__):
            inst = MagicMock()
            inst.search_paper.return_value = [raw]
            return inst

        with patch("tools.semantic_scholar_search.SemanticScholar", side_effect=_fake_ss), \
             patch("asyncio.sleep", side_effect=_noop_sleep):
            papers = await search_semantic_scholar("q", api_key="k")

        assert papers[0].doi is None

    @pytest.mark.asyncio
    async def test_none_external_ids_is_handled(self):
        """externalIds=None → doi is None, no exception."""
        raw = _make_raw_paper(externalIds=None)

        def _fake_ss(*_, **__):
            inst = MagicMock()
            inst.search_paper.return_value = [raw]
            return inst

        with patch("tools.semantic_scholar_search.SemanticScholar", side_effect=_fake_ss), \
             patch("asyncio.sleep", side_effect=_noop_sleep):
            papers = await search_semantic_scholar("q", api_key="k")

        assert papers[0].doi is None

    @pytest.mark.asyncio
    async def test_none_title_defaults_to_empty_string(self):
        raw = _make_raw_paper(title=None)

        def _fake_ss(*_, **__):
            inst = MagicMock()
            inst.search_paper.return_value = [raw]
            return inst

        with patch("tools.semantic_scholar_search.SemanticScholar", side_effect=_fake_ss), \
             patch("asyncio.sleep", side_effect=_noop_sleep):
            papers = await search_semantic_scholar("q", api_key="k")

        assert papers[0].title == ""

    @pytest.mark.asyncio
    async def test_none_year_defaults_to_zero(self):
        raw = _make_raw_paper(year=None)

        def _fake_ss(*_, **__):
            inst = MagicMock()
            inst.search_paper.return_value = [raw]
            return inst

        with patch("tools.semantic_scholar_search.SemanticScholar", side_effect=_fake_ss), \
             patch("asyncio.sleep", side_effect=_noop_sleep):
            papers = await search_semantic_scholar("q", api_key="k")

        assert papers[0].year == 0

    @pytest.mark.asyncio
    async def test_source_is_semantic_scholar(self):
        raw = _make_raw_paper()

        def _fake_ss(*_, **__):
            inst = MagicMock()
            inst.search_paper.return_value = [raw]
            return inst

        with patch("tools.semantic_scholar_search.SemanticScholar", side_effect=_fake_ss), \
             patch("asyncio.sleep", side_effect=_noop_sleep):
            papers = await search_semantic_scholar("q", api_key="k")

        assert papers[0].source == "semantic_scholar"

    @pytest.mark.asyncio
    async def test_multiple_results_mapped(self):
        raw = [_make_raw_paper(paperId=f"id{i}", title=f"Paper {i}") for i in range(5)]

        def _fake_ss(*_, **__):
            inst = MagicMock()
            inst.search_paper.return_value = raw
            return inst

        with patch("tools.semantic_scholar_search.SemanticScholar", side_effect=_fake_ss), \
             patch("asyncio.sleep", side_effect=_noop_sleep):
            papers = await search_semantic_scholar("q", max_results=5, api_key="k")

        assert len(papers) == 5
        assert [p.title for p in papers] == [f"Paper {i}" for i in range(5)]


# ---------------------------------------------------------------------------
# Exception handling
# ---------------------------------------------------------------------------


class TestExceptionHandling:
    @pytest.mark.asyncio
    async def test_api_exception_returns_empty_list(self):
        """Any exception during the API call must be caught and return []."""

        def _fake_ss(*_, **__):
            raise RuntimeError("network error")

        with patch("tools.semantic_scholar_search.SemanticScholar", side_effect=_fake_ss), \
             patch("asyncio.sleep", side_effect=_noop_sleep):
            result = await search_semantic_scholar("q", api_key="k")

        assert result == []

    @pytest.mark.asyncio
    async def test_api_exception_logs_warning(self):
        """The WARNING is logged when an exception occurs."""

        def _fake_ss(*_, **__):
            raise ConnectionError("timeout")

        with patch("tools.semantic_scholar_search.SemanticScholar", side_effect=_fake_ss), \
             patch("asyncio.sleep", side_effect=_noop_sleep), \
             patch("tools.semantic_scholar_search.logger") as mock_logger:
            await search_semantic_scholar("q", api_key="k")

        mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_results_returns_empty_list(self):
        """Zero results from the API returns an empty list (no exception)."""

        def _fake_ss(*_, **__):
            inst = MagicMock()
            inst.search_paper.return_value = []
            return inst

        with patch("tools.semantic_scholar_search.SemanticScholar", side_effect=_fake_ss), \
             patch("asyncio.sleep", side_effect=_noop_sleep):
            result = await search_semantic_scholar("q", api_key="k")

        assert result == []
