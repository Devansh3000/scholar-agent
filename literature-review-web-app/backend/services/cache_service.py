"""
Cache service for the Literature Review Web Application.

Provides an async-compatible ``CacheService`` that uses Redis as its primary
backend (via ``aioredis``) and transparently falls back to an in-process
dictionary when Redis is unavailable.  Values are serialised with ``pickle``
so any picklable Python object can be stored.

Usage::

    from services.cache_service import get_cache_service
    from config.settings import get_settings

    cache = get_cache_service(get_settings())
    await cache.set("my_key", {"data": 123}, ttl_seconds=600)
    value = await cache.get("my_key")  # → {"data": 123}
    await cache.close()
"""

from __future__ import annotations

import asyncio
import logging
import pickle
import time
from typing import Any

from redis.asyncio import Redis as AsyncRedis
from redis.asyncio import from_url as redis_from_url

from config.settings import Settings

logger = logging.getLogger(__name__)


class CacheService:
    """Async cache service backed by Redis with an in-memory fallback."""

    def __init__(self, redis_url: str = "redis://localhost:6379") -> None:
        self._redis_url: str = redis_url
        self._redis: AsyncRedis | None = None
        self._memory: dict[str, tuple[Any, float]] = {}
        self._redis_failed_at: float = 0.0  # track last failure to avoid spam
        self._redis_retry_interval: float = 300.0  # retry Redis every 5 minutes

    async def _get_redis(self) -> AsyncRedis | None:
        if self._redis is not None:
            return self._redis

        # Don't retry Redis if it failed recently — use a 5-minute backoff
        now = time.monotonic()
        if self._redis_failed_at > 0 and (now - self._redis_failed_at) < self._redis_retry_interval:
            return None

        try:
            client: AsyncRedis = redis_from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=False,
                socket_connect_timeout=2.0,  # fail fast instead of blocking
                socket_timeout=2.0,
            )
            await asyncio.wait_for(client.ping(), timeout=3.0)
            self._redis = client
            self._redis_failed_at = 0.0  # reset on success
            logger.debug("CacheService: connected to Redis at %s", self._redis_url)
            return self._redis
        except Exception as exc:  # noqa: BLE001
            self._redis_failed_at = time.monotonic()  # record failure time
            logger.warning(
                "CacheService: Redis unavailable (%s); using in-memory fallback for %ds.",
                exc,
                int(self._redis_retry_interval),
            )
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get(self, key: str) -> Any | None:
        """Retrieve a cached value by *key*.

        Returns ``None`` on cache miss or if the entry has expired.
        Logs HIT/MISS at DEBUG level including the key and backend used.
        """
        redis = await self._get_redis()

        if redis is not None:
            try:
                raw: bytes | None = await redis.get(key)
                if raw is None:
                    logger.debug("Cache MISS (redis) key=%s", key)
                    return None
                logger.debug("Cache HIT (redis) key=%s", key)
                return pickle.loads(raw)  # noqa: S301
            except Exception as exc:  # noqa: BLE001
                logger.warning("CacheService.get: Redis error for key=%s: %s", key, exc)
                self._redis = None  # reset so _get_redis retries next call

        # In-memory path
        entry = self._memory.get(key)
        if entry is None:
            logger.debug("Cache MISS (memory) key=%s", key)
            return None
        value, expire_at = entry
        if time.monotonic() > expire_at:
            del self._memory[key]
            logger.debug("Cache MISS (memory, expired) key=%s", key)
            return None
        logger.debug("Cache HIT (memory) key=%s", key)
        return value

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int = 86400,
    ) -> None:
        """Store *value* under *key* with an optional TTL.

        Parameters
        ----------
        key:
            Cache key string.
        value:
            Any picklable Python object.
        ttl_seconds:
            Time-to-live in seconds.  Defaults to 86 400 (24 hours).
        """
        redis = await self._get_redis()

        if redis is not None:
            try:
                serialised = pickle.dumps(value)
                await redis.set(key, serialised, ex=ttl_seconds)
                logger.debug("Cache SET (redis) key=%s ttl=%ds", key, ttl_seconds)
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("CacheService.set: Redis error for key=%s: %s", key, exc)
                self._redis = None  # reset for retry on next call

        # In-memory path
        expire_at = time.monotonic() + ttl_seconds
        self._memory[key] = (value, expire_at)
        logger.debug("Cache SET (memory) key=%s ttl=%ds", key, ttl_seconds)

    async def delete(self, key: str) -> None:
        """Remove *key* from the cache (no-op if key does not exist)."""
        redis = await self._get_redis()

        if redis is not None:
            try:
                await redis.delete(key)
                logger.debug("Cache DELETE (redis) key=%s", key)
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "CacheService.delete: Redis error for key=%s: %s", key, exc
                )
                self._redis = None

        # In-memory path
        self._memory.pop(key, None)
        logger.debug("Cache DELETE (memory) key=%s", key)

    async def exists(self, key: str) -> bool:
        """Return ``True`` if *key* is present in the cache and not expired."""
        redis = await self._get_redis()

        if redis is not None:
            try:
                result: int = await redis.exists(key)
                exists = bool(result)
                logger.debug("Cache EXISTS=%s (redis) key=%s", exists, key)
                return exists
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "CacheService.exists: Redis error for key=%s: %s", key, exc
                )
                self._redis = None

        # In-memory path
        entry = self._memory.get(key)
        if entry is None:
            return False
        _, expire_at = entry
        if time.monotonic() > expire_at:
            del self._memory[key]
            return False
        return True

    async def close(self) -> None:
        """Close the Redis connection if one is open."""
        if self._redis is not None:
            try:
                await self._redis.close()
                logger.debug("CacheService: Redis connection closed.")
            except Exception as exc:  # noqa: BLE001
                logger.warning("CacheService.close: error closing Redis: %s", exc)
            finally:
                self._redis = None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_cache_service(settings: Settings) -> CacheService:
    """Construct and return a :class:`CacheService` from application settings.

    Parameters
    ----------
    settings:
        Application :class:`~config.settings.Settings` instance; the
        ``REDIS_URL`` attribute is used as the Redis connection URL.

    Returns
    -------
    CacheService
        A ready-to-use cache service instance.
    """
    return CacheService(redis_url=settings.REDIS_URL)
