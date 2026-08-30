"""
PDF extractor tool for the Literature Review Web Application.

Downloads a PDF from a URL, extracts its text content, and optionally caches
the result.  Uses ``pypdf`` (with a fallback to ``PyPDF2``) for text
extraction, ``httpx`` for async HTTP downloads, and the shared retry decorator
for transient failure resilience.

The extracted text is normalised (collapsed whitespace) and truncated to
50 000 characters to keep downstream processing tractable.
"""

from __future__ import annotations

import io
import logging
import re
from typing import TYPE_CHECKING

import httpx

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    from PyPDF2 import PdfReader  # type: ignore[no-redef]

from utils.retry import retry

if TYPE_CHECKING:
    from services.cache_service import CacheService

logger = logging.getLogger(__name__)

_CACHE_TTL = 3600  # 1 hour in seconds
_MAX_TEXT_LENGTH = 50_000


@retry(max_attempts=3)
async def extract_pdf_text(
    url: str,
    cache: "CacheService | None" = None,
) -> str | None:
    """Download a PDF from *url* and return its extracted text content.

    Parameters
    ----------
    url:
        Public HTTP/HTTPS URL pointing to a PDF document.
    cache:
        Optional :class:`~services.cache_service.CacheService` instance.
        When provided, results are stored and retrieved using a URL-scoped
        key with a 1-hour TTL.

    Returns
    -------
    str | None
        Extracted and normalised text (up to 50 000 characters), or ``None``
        if the URL does not appear to serve a PDF, or if any error occurs
        during download or extraction.
    """
    cache_key = f"pdf:{url}"

    # --- Cache look-up ---
    if cache is not None:
        cached = await cache.get(cache_key)
        if cached is not None:
            logger.info("PDF cache HIT for url=%r", url)
            return cached
        logger.info("PDF cache MISS for url=%r", url)

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url)
            response.raise_for_status()

        # --- Content-type guard ---
        content_type = response.headers.get("content-type", "")
        if "pdf" not in content_type.lower() and not url.lower().endswith(".pdf"):
            logger.info(
                "extract_pdf_text: skipping non-PDF response for url=%r "
                "(content-type=%r)",
                url,
                content_type,
            )
            return None

        # --- PDF text extraction ---
        pdf_file = io.BytesIO(response.content)
        reader = PdfReader(pdf_file)
        raw_text: str = "".join(page.extract_text() or "" for page in reader.pages)

        # --- Normalise and truncate ---
        text = re.sub(r"\s+", " ", raw_text).strip()[:_MAX_TEXT_LENGTH]

        logger.info(
            "extract_pdf_text: extracted %d chars from url=%r", len(text), url
        )

        # --- Cache store ---
        if cache is not None and text:
            await cache.set(cache_key, text, ttl_seconds=_CACHE_TTL)

        return text or None

    except Exception as exc:  # noqa: BLE001
        logger.warning("extract_pdf_text: failed for url=%r: %s", url, exc)
        return None


__all__ = ["extract_pdf_text"]
