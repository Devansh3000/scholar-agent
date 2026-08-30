"""
Unit tests for backend/agents/topic_understanding.py

Tests cover:
- Successful Gemini response with well-formed JSON
- JSON wrapped in markdown code fences (```json ... ```)
- JSON parse failure → safe defaults returned (no exception)
- Gemini call exception → RuntimeError raised
- Result dataclass field population
- Prompt construction uses the provided topic
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from agents.topic_understanding import (
    TopicUnderstandingResult,
    _safe_defaults,
    run_topic_understanding,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(text: str) -> MagicMock:
    """Create a mock Gemini response with the given ``text`` attribute."""
    response = MagicMock()
    response.text = text
    return response


_VALID_JSON_DATA = {
    "expanded_topic": "Transformer architectures have revolutionised NLP.",
    "keywords": [
        "transformer",
        "attention mechanism",
        "BERT",
        "GPT",
        "self-attention",
        "NLP",
        "language model",
        "pre-training",
        "fine-tuning",
        "encoder",
        "decoder",
        "multi-head attention",
    ],
    "subdomains": [
        "natural language processing",
        "deep learning",
        "computational linguistics",
    ],
    "search_queries": [
        "transformer architecture natural language processing",
        "BERT language model pre-training",
        "attention mechanism NLP survey",
        "GPT generative pre-trained transformer",
        "self-attention neural network",
        "transformer-based text classification",
        "encoder decoder architecture NLP",
        "large language models fine-tuning",
        "multi-head attention mechanism",
        "transformer applications machine translation",
        "transfer learning NLP transformers",
        "pre-trained language models survey",
        "vision transformer ViT image recognition",
        "transformer NLP benchmark evaluation",
        "recent advances transformer models",
    ],
}


# ---------------------------------------------------------------------------
# TopicUnderstandingResult dataclass tests
# ---------------------------------------------------------------------------


class TestTopicUnderstandingResult:
    def test_fields_accessible(self):
        result = TopicUnderstandingResult(
            expanded_topic="An expanded topic.",
            keywords=["kw1", "kw2"],
            subdomains=["sd1"],
            search_queries=["q1", "q2"],
        )
        assert result.expanded_topic == "An expanded topic."
        assert result.keywords == ["kw1", "kw2"]
        assert result.subdomains == ["sd1"]
        assert result.search_queries == ["q1", "q2"]

    def test_default_lists_are_empty(self):
        result = TopicUnderstandingResult(expanded_topic="topic")
        assert result.keywords == []
        assert result.subdomains == []
        assert result.search_queries == []


# ---------------------------------------------------------------------------
# _safe_defaults helper tests
# ---------------------------------------------------------------------------


class TestSafeDefaults:
    def test_expanded_topic_equals_input(self):
        result = _safe_defaults("my topic")
        assert result.expanded_topic == "my topic"

    def test_keywords_contains_topic(self):
        result = _safe_defaults("my topic")
        assert "my topic" in result.keywords

    def test_search_queries_non_empty(self):
        result = _safe_defaults("my topic")
        assert len(result.search_queries) >= 1


# ---------------------------------------------------------------------------
# run_topic_understanding — successful path
# ---------------------------------------------------------------------------


class TestRunTopicUnderstanding:
    @pytest.mark.asyncio
    async def test_returns_correct_fields_on_valid_json(self):
        """Well-formed JSON response is parsed into TopicUnderstandingResult."""
        raw = json.dumps(_VALID_JSON_DATA)
        mock_response = _make_response(raw)

        with patch("agents.topic_understanding.genai") as mock_genai, \
             patch("asyncio.get_event_loop") as mock_loop:
            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model

            # Simulate run_in_executor returning the mock response directly
            mock_loop.return_value.run_in_executor = lambda _, fn, *a: _async_return(
                mock_response
            )

            result = await run_topic_understanding(
                topic="transformer architectures in NLP",
                api_key="fake-key",
            )

        assert isinstance(result, TopicUnderstandingResult)
        assert result.expanded_topic == _VALID_JSON_DATA["expanded_topic"]
        assert result.keywords == _VALID_JSON_DATA["keywords"]
        assert result.subdomains == _VALID_JSON_DATA["subdomains"]
        assert result.search_queries == _VALID_JSON_DATA["search_queries"]

    @pytest.mark.asyncio
    async def test_strips_markdown_json_fence(self):
        """Response wrapped in ```json ... ``` should be parsed correctly."""
        raw = f"```json\n{json.dumps(_VALID_JSON_DATA)}\n```"
        mock_response = _make_response(raw)

        with patch("agents.topic_understanding.genai") as mock_genai, \
             patch("asyncio.get_event_loop") as mock_loop:
            mock_genai.GenerativeModel.return_value = MagicMock()
            mock_loop.return_value.run_in_executor = lambda _, fn, *a: _async_return(
                mock_response
            )

            result = await run_topic_understanding(
                topic="transformers",
                api_key="fake-key",
            )

        assert result.expanded_topic == _VALID_JSON_DATA["expanded_topic"]
        assert len(result.keywords) == len(_VALID_JSON_DATA["keywords"])

    @pytest.mark.asyncio
    async def test_strips_plain_code_fence(self):
        """Response wrapped in ``` ... ``` (no language tag) is parsed."""
        raw = f"```\n{json.dumps(_VALID_JSON_DATA)}\n```"
        mock_response = _make_response(raw)

        with patch("agents.topic_understanding.genai") as mock_genai, \
             patch("asyncio.get_event_loop") as mock_loop:
            mock_genai.GenerativeModel.return_value = MagicMock()
            mock_loop.return_value.run_in_executor = lambda _, fn, *a: _async_return(
                mock_response
            )

            result = await run_topic_understanding(topic="test", api_key="k")

        assert result.subdomains == _VALID_JSON_DATA["subdomains"]

    @pytest.mark.asyncio
    async def test_json_parse_error_returns_safe_defaults(self):
        """Invalid JSON → no exception, safe defaults returned, WARNING logged."""
        mock_response = _make_response("this is not json at all {{{")

        with patch("agents.topic_understanding.genai") as mock_genai, \
             patch("asyncio.get_event_loop") as mock_loop, \
             patch("agents.topic_understanding.logger") as mock_logger:
            mock_genai.GenerativeModel.return_value = MagicMock()
            mock_loop.return_value.run_in_executor = lambda _, fn, *a: _async_return(
                mock_response
            )

            result = await run_topic_understanding(
                topic="deep learning", api_key="fake-key"
            )

        assert isinstance(result, TopicUnderstandingResult)
        assert result.expanded_topic == "deep learning"
        mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_gemini_exception_raises_runtime_error(self):
        """Any exception from the Gemini SDK is re-raised as RuntimeError."""
        with patch("agents.topic_understanding.genai") as mock_genai, \
             patch("asyncio.get_event_loop") as mock_loop:
            mock_genai.GenerativeModel.return_value = MagicMock()

            async def _raise(*_a, **_kw):
                raise ConnectionError("network down")

            mock_loop.return_value.run_in_executor = _raise

            with pytest.raises(RuntimeError, match="Topic understanding failed"):
                await run_topic_understanding(
                    topic="quantum computing", api_key="fake-key"
                )

    @pytest.mark.asyncio
    async def test_api_key_passed_to_genai_configure(self):
        """genai.configure is called with the provided api_key."""
        raw = json.dumps(_VALID_JSON_DATA)
        mock_response = _make_response(raw)

        with patch("agents.topic_understanding.genai") as mock_genai, \
             patch("asyncio.get_event_loop") as mock_loop:
            mock_genai.GenerativeModel.return_value = MagicMock()
            mock_loop.return_value.run_in_executor = lambda _, fn, *a: _async_return(
                mock_response
            )

            await run_topic_understanding(topic="AI safety", api_key="my-secret-key")

        mock_genai.configure.assert_called_once_with(api_key="my-secret-key")

    @pytest.mark.asyncio
    async def test_uses_gemini_2_5_flash_model(self):
        """The agent must use the gemini-3.6-flash model."""
        raw = json.dumps(_VALID_JSON_DATA)
        mock_response = _make_response(raw)

        with patch("agents.topic_understanding.genai") as mock_genai, \
             patch("asyncio.get_event_loop") as mock_loop:
            mock_genai.GenerativeModel.return_value = MagicMock()
            mock_loop.return_value.run_in_executor = lambda _, fn, *a: _async_return(
                mock_response
            )

            await run_topic_understanding(topic="robotics", api_key="k")

        mock_genai.GenerativeModel.assert_called_once_with("gemini-3.6-flash")

    @pytest.mark.asyncio
    async def test_missing_json_keys_fall_back_to_defaults(self):
        """Partial JSON (some keys missing) should not raise; missing fields default."""
        partial = {"expanded_topic": "Only expanded topic present."}
        mock_response = _make_response(json.dumps(partial))

        with patch("agents.topic_understanding.genai") as mock_genai, \
             patch("asyncio.get_event_loop") as mock_loop:
            mock_genai.GenerativeModel.return_value = MagicMock()
            mock_loop.return_value.run_in_executor = lambda _, fn, *a: _async_return(
                mock_response
            )

            result = await run_topic_understanding(
                topic="partial response test", api_key="k"
            )

        assert result.expanded_topic == "Only expanded topic present."
        assert result.keywords == []
        assert result.subdomains == []
        assert result.search_queries == []


# ---------------------------------------------------------------------------
# Async helper
# ---------------------------------------------------------------------------


async def _async_return(value):
    """Coroutine that immediately returns *value* — used as run_in_executor stub."""
    return value
