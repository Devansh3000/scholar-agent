"""
Unit tests for backend/utils/retry.py

Tests cover:
- Sync and async functions
- Success on first attempt (no retries)
- Retry then succeed (1 or more failures before success)
- Exhausted retries raising RetryExhaustedError
- Non-retryable exceptions propagate immediately
- httpx.HTTPStatusError retry/no-retry based on status code
- Correct delay formula: initial_delay * backoff_factor ** attempt
- Logging at WARNING level on each retry
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import httpx
import pytest

from utils.retry import RetryExhaustedError, retry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_http_error(status_code: int) -> httpx.HTTPStatusError:
    """Create a minimal httpx.HTTPStatusError for testing."""
    request = httpx.Request("GET", "https://example.com")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(
        f"HTTP {status_code}",
        request=request,
        response=response,
    )


# ---------------------------------------------------------------------------
# Sync tests
# ---------------------------------------------------------------------------


class TestSyncRetry:
    def test_success_on_first_attempt(self):
        call_count = 0

        @retry(max_attempts=3)
        def always_succeeds():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = always_succeeds()
        assert result == "ok"
        assert call_count == 1

    def test_retry_then_succeed(self):
        """Fails twice, then succeeds on the third attempt."""
        attempts = []

        @retry(max_attempts=3, initial_delay_seconds=0.0, backoff_factor=1.0)
        def flaky():
            attempts.append(1)
            if len(attempts) < 3:
                raise ValueError("transient")
            return "done"

        with patch("time.sleep"):
            result = flaky()

        assert result == "done"
        assert len(attempts) == 3

    def test_exhausted_raises_retry_exhausted_error(self):
        """All attempts fail → RetryExhaustedError wrapping last exception."""

        @retry(max_attempts=2, initial_delay_seconds=0.0, backoff_factor=1.0)
        def always_fails():
            raise RuntimeError("boom")

        with patch("time.sleep"):
            with pytest.raises(RetryExhaustedError) as exc_info:
                always_fails()

        assert isinstance(exc_info.value.last_exception, RuntimeError)
        assert "boom" in str(exc_info.value.last_exception)

    def test_non_retryable_exception_propagates_immediately(self):
        """TypeError is not in retryable_exceptions → immediate re-raise."""
        call_count = 0

        @retry(
            max_attempts=3,
            initial_delay_seconds=0.0,
            retryable_exceptions=(ValueError,),
        )
        def raises_type_error():
            nonlocal call_count
            call_count += 1
            raise TypeError("not retryable")

        with pytest.raises(TypeError, match="not retryable"):
            raises_type_error()

        assert call_count == 1  # no retries

    def test_zero_failures_no_sleep(self):
        @retry(max_attempts=3, initial_delay_seconds=1.0)
        def always_succeeds():
            return 42

        with patch("time.sleep") as mock_sleep:
            result = always_succeeds()

        assert result == 42
        mock_sleep.assert_not_called()

    def test_delay_is_called_between_retries(self):
        """Verify time.sleep is called with the correct exponential values."""
        attempts = []

        @retry(max_attempts=3, initial_delay_seconds=1.0, backoff_factor=2.0)
        def flaky():
            attempts.append(1)
            if len(attempts) < 3:
                raise ValueError("transient")
            return "ok"

        with patch("time.sleep") as mock_sleep:
            flaky()

        # First pause: 1.0 * 2.0**0 = 1.0
        # Second pause: 1.0 * 2.0**1 = 2.0
        sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleep_calls == pytest.approx([1.0, 2.0])

    def test_http_status_error_retryable_code(self):
        """429 is retryable by default."""
        call_count = 0

        @retry(max_attempts=2, initial_delay_seconds=0.0, backoff_factor=1.0)
        def calls_api():
            nonlocal call_count
            call_count += 1
            raise _make_http_error(429)

        with patch("time.sleep"):
            with pytest.raises(RetryExhaustedError):
                calls_api()

        assert call_count == 2

    def test_http_status_error_non_retryable_code(self):
        """404 is NOT in default retryable status codes → immediate re-raise."""
        call_count = 0

        @retry(max_attempts=3, initial_delay_seconds=0.0)
        def calls_api():
            nonlocal call_count
            call_count += 1
            raise _make_http_error(404)

        with pytest.raises(httpx.HTTPStatusError):
            calls_api()

        assert call_count == 1

    def test_retry_exhausted_error_wraps_last_exception(self):
        """RetryExhaustedError.__cause__ and .last_exception are the last exc."""
        exc = ValueError("final error")

        @retry(max_attempts=1, initial_delay_seconds=0.0)
        def one_shot():
            raise exc

        with pytest.raises(RetryExhaustedError) as exc_info:
            one_shot()

        assert exc_info.value.last_exception is exc
        assert exc_info.value.__cause__ is exc

    def test_warnings_logged_on_retry(self):
        attempts = []

        @retry(max_attempts=3, initial_delay_seconds=0.0, backoff_factor=1.0)
        def flaky():
            attempts.append(1)
            if len(attempts) < 3:
                raise ValueError("oops")
            return "good"

        with patch("time.sleep"), patch("utils.retry.logger") as mock_logger:
            flaky()

        assert mock_logger.warning.call_count == 2


# ---------------------------------------------------------------------------
# Async tests
# ---------------------------------------------------------------------------


class TestAsyncRetry:
    @pytest.mark.asyncio
    async def test_async_success_on_first_attempt(self):
        call_count = 0

        @retry(max_attempts=3)
        async def always_succeeds():
            nonlocal call_count
            call_count += 1
            return "async_ok"

        result = await always_succeeds()
        assert result == "async_ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_retry_then_succeed(self):
        attempts = []

        @retry(max_attempts=3, initial_delay_seconds=0.0, backoff_factor=1.0)
        async def flaky():
            attempts.append(1)
            if len(attempts) < 3:
                raise ValueError("transient")
            return "async_done"

        with patch("asyncio.sleep", new_callable=lambda: lambda: asyncio.coroutine(lambda _: None)):
            pass  # reset

        # Patch asyncio.sleep to avoid actual sleeping
        async def fast_sleep(_):
            pass

        with patch("asyncio.sleep", side_effect=fast_sleep):
            result = await flaky()

        assert result == "async_done"
        assert len(attempts) == 3

    @pytest.mark.asyncio
    async def test_async_exhausted_raises_retry_exhausted_error(self):
        @retry(max_attempts=2, initial_delay_seconds=0.0, backoff_factor=1.0)
        async def always_fails():
            raise RuntimeError("async boom")

        async def fast_sleep(_):
            pass

        with patch("asyncio.sleep", side_effect=fast_sleep):
            with pytest.raises(RetryExhaustedError) as exc_info:
                await always_fails()

        assert isinstance(exc_info.value.last_exception, RuntimeError)

    @pytest.mark.asyncio
    async def test_async_non_retryable_propagates_immediately(self):
        call_count = 0

        @retry(
            max_attempts=3,
            initial_delay_seconds=0.0,
            retryable_exceptions=(ValueError,),
        )
        async def raises_type_error():
            nonlocal call_count
            call_count += 1
            raise TypeError("not retryable async")

        with pytest.raises(TypeError):
            await raises_type_error()

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_http_status_error_retryable(self):
        call_count = 0

        @retry(max_attempts=2, initial_delay_seconds=0.0, backoff_factor=1.0)
        async def calls_api():
            nonlocal call_count
            call_count += 1
            raise _make_http_error(503)

        async def fast_sleep(_):
            pass

        with patch("asyncio.sleep", side_effect=fast_sleep):
            with pytest.raises(RetryExhaustedError):
                await calls_api()

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_async_http_status_error_non_retryable(self):
        call_count = 0

        @retry(max_attempts=3, initial_delay_seconds=0.0)
        async def calls_api():
            nonlocal call_count
            call_count += 1
            raise _make_http_error(403)

        with pytest.raises(httpx.HTTPStatusError):
            await calls_api()

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_delay_formula(self):
        """Verify asyncio.sleep is called with correct exponential values."""
        attempts = []

        @retry(max_attempts=3, initial_delay_seconds=1.0, backoff_factor=2.0)
        async def flaky():
            attempts.append(1)
            if len(attempts) < 3:
                raise ValueError("transient")
            return "ok"

        sleep_calls: list[float] = []

        async def recording_sleep(delay: float):
            sleep_calls.append(delay)

        with patch("asyncio.sleep", side_effect=recording_sleep):
            await flaky()

        assert sleep_calls == pytest.approx([1.0, 2.0])

    @pytest.mark.asyncio
    async def test_async_custom_retryable_status_codes(self):
        """Only retry on 500; 502 should propagate immediately."""
        call_count = 0

        @retry(
            max_attempts=3,
            initial_delay_seconds=0.0,
            retryable_status_codes=[500],
        )
        async def calls_api():
            nonlocal call_count
            call_count += 1
            raise _make_http_error(502)

        with pytest.raises(httpx.HTTPStatusError):
            await calls_api()

        assert call_count == 1


# ---------------------------------------------------------------------------
# RetryExhaustedError standalone tests
# ---------------------------------------------------------------------------


class TestRetryExhaustedError:
    def test_inherits_from_exception(self):
        assert issubclass(RetryExhaustedError, Exception)

    def test_stores_last_exception(self):
        cause = ValueError("root cause")
        err = RetryExhaustedError("msg", cause)
        assert err.last_exception is cause
        assert err.__cause__ is cause

    def test_string_representation(self):
        cause = RuntimeError("oops")
        err = RetryExhaustedError("all attempts failed", cause)
        assert "all attempts failed" in str(err)
