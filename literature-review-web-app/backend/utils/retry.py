"""
Retry decorator with exponential backoff for both sync and async functions.

Supports:
- Async and sync callables (detected via ``inspect.iscoroutinefunction``)
- Configurable maximum attempts, initial delay, and backoff factor
- Selective retry based on exception type or HTTP status code (for httpx errors)
- Per-attempt WARNING log with attempt number, exception message, and next delay
- ``RetryExhaustedError`` wrapping the final exception when all attempts are used up

Delay formula:
    delay_for_attempt_n = initial_delay_seconds * (backoff_factor ** n)

where ``n`` is 0-indexed (0 for the pause after the 1st failure, 1 after the 2nd, …).

For defaults (initial_delay=1.0, backoff_factor=2.0) this gives delays of 1 s, 2 s, 4 s.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import time
from typing import Any, Callable, TypeVar

import httpx

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------


class RetryExhaustedError(Exception):
    """Raised when all retry attempts have been exhausted.

    The ``__cause__`` attribute holds the last exception that triggered the
    final retry failure.
    """

    def __init__(self, message: str, last_exception: Exception) -> None:
        super().__init__(message)
        self.__cause__ = last_exception
        self.last_exception = last_exception


# ---------------------------------------------------------------------------
# Decorator factory
# ---------------------------------------------------------------------------


def retry(
    max_attempts: int = 3,
    initial_delay_seconds: float = 1.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    retryable_status_codes: list[int] | None = None,
) -> Callable[[F], F]:
    """Return a decorator that retries the wrapped function on transient failures.

    Parameters
    ----------
    max_attempts:
        Total number of calls allowed (including the first attempt).  Must be ≥ 1.
    initial_delay_seconds:
        Delay (in seconds) before the second attempt (attempt index 0).
    backoff_factor:
        Multiplier applied to the delay on each successive retry.
        ``delay_n = initial_delay_seconds * (backoff_factor ** n)``
    retryable_exceptions:
        Exception types that trigger a retry.  ``httpx.HTTPStatusError`` is
        handled separately via ``retryable_status_codes`` and does **not** need
        to be listed here.
    retryable_status_codes:
        HTTP status codes for which an ``httpx.HTTPStatusError`` should be
        retried.  Defaults to ``[429, 500, 502, 503, 504]``.

    Returns
    -------
    Callable
        The decorator.  Wraps both sync and async callables transparently.
    """
    if retryable_status_codes is None:
        retryable_status_codes = [429, 500, 502, 503, 504]

    def decorator(func: F) -> F:
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                last_exc: Exception | None = None

                for attempt in range(max_attempts):
                    try:
                        return await func(*args, **kwargs)
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code not in retryable_status_codes:
                            raise
                        last_exc = exc
                    except retryable_exceptions as exc:
                        last_exc = exc
                    except Exception:
                        # Non-retryable — propagate immediately
                        raise

                    # We only reach here if the attempt should be retried
                    if attempt < max_attempts - 1:
                        delay = initial_delay_seconds * (backoff_factor ** attempt)
                        logger.warning(
                            "Retry %d/%d for '%s' after error: %s. "
                            "Next attempt in %.2f s.",
                            attempt + 1,
                            max_attempts - 1,
                            func.__qualname__,
                            last_exc,
                            delay,
                        )
                        await asyncio.sleep(delay)

                # All attempts exhausted
                assert last_exc is not None  # always set when we exit the loop here
                raise RetryExhaustedError(
                    f"'{func.__qualname__}' failed after {max_attempts} attempt(s): {last_exc}",
                    last_exc,
                ) from last_exc

            return async_wrapper  # type: ignore[return-value]

        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                last_exc: Exception | None = None

                for attempt in range(max_attempts):
                    try:
                        return func(*args, **kwargs)
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code not in retryable_status_codes:
                            raise
                        last_exc = exc
                    except retryable_exceptions as exc:
                        last_exc = exc
                    except Exception:
                        raise

                    if attempt < max_attempts - 1:
                        delay = initial_delay_seconds * (backoff_factor ** attempt)
                        logger.warning(
                            "Retry %d/%d for '%s' after error: %s. "
                            "Next attempt in %.2f s.",
                            attempt + 1,
                            max_attempts - 1,
                            func.__qualname__,
                            last_exc,
                            delay,
                        )
                        time.sleep(delay)

                assert last_exc is not None
                raise RetryExhaustedError(
                    f"'{func.__qualname__}' failed after {max_attempts} attempt(s): {last_exc}",
                    last_exc,
                ) from last_exc

            return sync_wrapper  # type: ignore[return-value]

    return decorator


__all__ = ["retry", "RetryExhaustedError"]
