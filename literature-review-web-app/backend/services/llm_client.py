"""
LLM Client with OpenRouter backend and automatic model fallback.

This module provides :func:`llm_complete` — a single async function that sends
a text prompt to OpenRouter and retries through a prioritised list of free/cheap
models if the primary model is rate-limited (429) or returns an error.

Fallback model chain (in order):
  1. google/gemini-2.0-flash-exp:free
  2. meta-llama/llama-3.3-70b-instruct:free
  3. mistralai/mistral-7b-instruct:free
  4. microsoft/phi-3-mini-128k-instruct:free
  5. qwen/qwen-2.5-72b-instruct:free

All models are accessed through the OpenRouter unified API endpoint, which is
OpenAI-API-compatible, so we use ``httpx`` directly to keep the dependency
footprint small.

Usage::

    from services.llm_client import llm_complete

    text = await llm_complete(
        prompt="Say hello in three words.",
        api_key="sk-or-...",
    )
"""

from __future__ import annotations

import asyncio
import logging
from typing import Sequence

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fallback model list — ordered by preference
# ---------------------------------------------------------------------------

DEFAULT_MODELS: tuple[str, ...] = (
    "openrouter/auto",                          # OpenRouter's auto-router (picks best available)
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "minimax/minimax-m3:free",
    "thinkingmachines/inkling:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "minimax/minimax-m2.7:free",
    "nvidia/nemotron-3.5-lightning:free",
    "thinkingmachines/inkling-small:free",
    "z-ai/glm-5.2:free",
)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_TIMEOUT = 60.0  # seconds per attempt


async def llm_complete(
    prompt: str,
    api_key: str,
    models: Sequence[str] = DEFAULT_MODELS,
    system: str = "You are a helpful academic research assistant.",
) -> str:
    """Send *prompt* to OpenRouter and return the response text.

    Tries each model in *models* in order.  Moves to the next model on:
      - HTTP 429 (rate-limited / quota exceeded)
      - HTTP 5xx (server error)
      - Any network / timeout error

    Raises :exc:`RuntimeError` if every model in the list fails.

    Parameters
    ----------
    prompt:
        User prompt text.
    api_key:
        OpenRouter API key (``sk-or-...``).
    models:
        Ordered sequence of OpenRouter model IDs to try.
    system:
        System message prepended to every request.

    Returns
    -------
    str
        The text content of the first successful model response.

    Raises
    ------
    RuntimeError
        When all models have been exhausted without a successful response.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/scholar-agent",
        "X-Title": "Scholar Agent",
    }

    last_error: str = "unknown error"

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for model in models:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            }
            try:
                response = await client.post(
                    _OPENROUTER_URL, json=payload, headers=headers
                )

                if response.status_code == 200:
                    data = response.json()
                    content: str = (
                        data["choices"][0]["message"]["content"]
                    )
                    logger.info(
                        "llm_complete: success with model=%s chars=%d",
                        model,
                        len(content),
                    )
                    return content

                last_error = f"HTTP {response.status_code}: {response.text[:200]}"

                if response.status_code == 429:
                    logger.warning(
                        "llm_complete: model=%s rate-limited (429) — trying next.",
                        model,
                    )
                    continue

                if response.status_code >= 500:
                    logger.warning(
                        "llm_complete: model=%s server error %d — trying next.",
                        model,
                        response.status_code,
                    )
                    continue

                # 404 "No endpoints found" means model is unavailable — try next
                if response.status_code == 404:
                    logger.warning(
                        "llm_complete: model=%s not available (404) — trying next.",
                        model,
                    )
                    continue

                # Other 4xx — likely a bad request, no point retrying other models
                logger.error(
                    "llm_complete: model=%s returned %d — %s",
                    model,
                    response.status_code,
                    response.text[:300],
                )
                raise RuntimeError(
                    f"LLM request failed ({response.status_code}): {response.text[:200]}"
                )

            except httpx.TimeoutException:
                last_error = f"timeout after {_TIMEOUT}s"
                logger.warning(
                    "llm_complete: model=%s timed out — trying next.", model
                )
                continue

            except httpx.RequestError as exc:
                last_error = str(exc)
                logger.warning(
                    "llm_complete: model=%s network error %s — trying next.",
                    model,
                    exc,
                )
                continue

    raise RuntimeError(
        f"All LLM models exhausted. Last error: {last_error}. "
        f"Models tried: {list(models)}"
    )


async def llm_embed(
    texts: list[str],
    api_key: str,
) -> list[list[float]]:
    """Generate embeddings for *texts* via OpenRouter's embeddings endpoint.

    Falls back to a deterministic TF-IDF-style sparse embedding when the
    OpenRouter call fails (so thematic clustering always has *something* to
    work with).

    Parameters
    ----------
    texts:
        List of strings to embed.
    api_key:
        OpenRouter API key.

    Returns
    -------
    list[list[float]]
        One embedding vector per input text.  Vectors may vary in length
        between the real API path (1536 dims) and the fallback path.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "openai/text-embedding-3-small",
        "input": texts,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/embeddings",
                json=payload,
                headers=headers,
            )
            if response.status_code == 200:
                data = response.json()
                return [item["embedding"] for item in data["data"]]
            logger.warning(
                "llm_embed: OpenRouter returned %d — falling back to local embeddings.",
                response.status_code,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "llm_embed: request failed (%s) — falling back to local embeddings.", exc
        )

    # Local fallback: sentence-transformers (installed via requirements.txt)
    return await asyncio.get_event_loop().run_in_executor(
        None, _local_embed, texts
    )


def _local_embed(texts: list[str]) -> list[list[float]]:
    """Generate embeddings locally using sentence-transformers."""
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore

        model = SentenceTransformer("all-MiniLM-L6-v2")
        vectors = model.encode(texts, show_progress_bar=False)
        return [v.tolist() for v in vectors]
    except Exception as exc:  # noqa: BLE001
        logger.warning("_local_embed: sentence-transformers failed (%s) — using zeros.", exc)
        # Last resort: zero vectors so clustering still runs (will produce one cluster)
        dim = 384
        return [[0.0] * dim for _ in texts]


__all__ = ["llm_complete", "llm_embed", "DEFAULT_MODELS"]
