"""
Application configuration module.

Reads all configuration values from environment variables (or a `.env` file)
using `pydantic-settings`.  A cached singleton is exposed via `get_settings()`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List, Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings resolved from environment variables.

    Required (at least one LLM key must be set):
        OPENROUTER_API_KEY: API key for OpenRouter (primary LLM provider).
        GOOGLE_API_KEY: Legacy Gemini key — kept for embeddings fallback.

    Optional (all have sensible defaults):
        IEEE_API_KEY, SEMANTIC_SCHOLAR_API_KEY, SERPAPI_KEY,
        REDIS_URL, DATABASE_URL, LOG_LEVEL, CORS_ORIGINS,
        MAX_CONCURRENT_JOBS, APP_VERSION, ENVIRONMENT.
    """

    # ------------------------------------------------------------------ #
    # External API keys
    # ------------------------------------------------------------------ #
    OPENROUTER_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    IEEE_API_KEY: str = ""
    SEMANTIC_SCHOLAR_API_KEY: str = ""
    SERPAPI_KEY: str = ""

    # ------------------------------------------------------------------ #
    # Infrastructure
    # ------------------------------------------------------------------ #
    REDIS_URL: str = "redis://localhost:6379"
    DATABASE_URL: str = ""

    # ------------------------------------------------------------------ #
    # Observability
    # ------------------------------------------------------------------ #
    LOG_LEVEL: str = "INFO"

    # ------------------------------------------------------------------ #
    # HTTP / CORS
    # ------------------------------------------------------------------ #
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ------------------------------------------------------------------ #
    # Runtime limits
    # ------------------------------------------------------------------ #
    MAX_CONCURRENT_JOBS: int = 10

    # ------------------------------------------------------------------ #
    # Application metadata
    # ------------------------------------------------------------------ #
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"

    # ------------------------------------------------------------------ #
    # Pydantic-settings configuration
    # ------------------------------------------------------------------ #
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #
    @model_validator(mode="after")
    def _validate_required_keys(self) -> "Settings":
        """Fail fast at startup if no LLM API key is configured."""
        if not self.OPENROUTER_API_KEY and not self.GOOGLE_API_KEY:
            raise ValueError(
                "At least one of OPENROUTER_API_KEY or GOOGLE_API_KEY must be set."
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the application settings singleton.

    The instance is constructed once and cached for the lifetime of the
    process.  Use ``get_settings.cache_clear()`` in tests to reset it.
    """
    return Settings()
