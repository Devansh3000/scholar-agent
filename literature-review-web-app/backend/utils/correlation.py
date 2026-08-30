"""
Correlation ID middleware for the Literature Review Web Application.

This module provides async-safe per-request correlation ID tracking using
Python's :mod:`contextvars` module.  A :class:`contextvars.ContextVar` holds
the correlation ID for the duration of each async execution context, which
means every ``await``-ed coroutine spawned during a request automatically
inherits the same correlation ID without any explicit parameter threading.

The middleware injects a :class:`CorrelationIdFilter` directly into the root
logger so that every log record emitted during the request carries the correct
``correlation_id`` field, regardless of which logger or handler produced it.

Components
----------
- :data:`correlation_id_var` — module-level :class:`~contextvars.ContextVar`
- :class:`CorrelationIdFilter` — stamps every :class:`logging.LogRecord`
- :class:`CorrelationIdMiddleware` — Starlette/FastAPI ASGI middleware
- :func:`get_correlation_id` — convenience accessor for the current context

Usage::

    from utils.correlation import (
        CorrelationIdMiddleware,
        CorrelationIdFilter,
        get_correlation_id,
    )

    # Register the middleware in your FastAPI app:
    app.add_middleware(CorrelationIdMiddleware)

    # Retrieve the current correlation ID anywhere in the call stack:
    cid = get_correlation_id()
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ---------------------------------------------------------------------------
# Module-level context variable
# ---------------------------------------------------------------------------

#: Holds the correlation ID for the current async execution context.
#: Defaults to an empty string when no request is active (e.g. during startup
#: or in background tasks that do not originate from an HTTP request).
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


# ---------------------------------------------------------------------------
# Logging filter
# ---------------------------------------------------------------------------


class CorrelationIdFilter(logging.Filter):
    """Inject the current correlation ID into every log record.

    Add this filter to a :class:`logging.Logger` (or to any handler) to ensure
    that ``record.correlation_id`` is always populated before the record is
    emitted.  The JSON formatter in :mod:`config.logging_config` already reads
    ``record.correlation_id``; this filter is the bridge between the async
    context variable and the logging pipeline.

    Example::

        logging.getLogger().addFilter(CorrelationIdFilter())
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        """Attach the current correlation ID to *record* and allow emission.

        Args:
            record: The :class:`logging.LogRecord` being processed.

        Returns:
            ``True`` — this filter never suppresses records; it only annotates
            them.
        """
        record.correlation_id = correlation_id_var.get()
        return True


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Starlette/FastAPI middleware that manages per-request correlation IDs.

    For every incoming HTTP request the middleware:

    1. Reads the ``X-Correlation-ID`` header value; if the header is absent or
       its value is empty a new UUID v4 is generated.
    2. Stores the correlation ID on ``request.state.correlation_id`` so route
       handlers can access it via ``request.state``.
    3. Sets :data:`correlation_id_var` in the current async context so that any
       ``await``-ed code (agents, tools, services) inherits the value without
       needing explicit parameter threading.
    4. Injects a :class:`CorrelationIdFilter` into the **root logger** so that
       every log record emitted during the request carries the correct
       correlation ID.
    5. Resets the context variable to its previous value in a ``finally`` block
       to prevent context leakage between requests.
    6. Removes the filter from the root logger in the same ``finally`` block.
    7. Adds the ``X-Correlation-ID`` header to the outgoing response so that
       clients can correlate their logs with server logs.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process *request* and return the downstream *response*.

        Args:
            request:   The incoming :class:`~starlette.requests.Request`.
            call_next: The next middleware or route handler in the chain.

        Returns:
            The :class:`~starlette.responses.Response` produced by the
            downstream handler, augmented with the ``X-Correlation-ID`` header.
        """
        # ------------------------------------------------------------------
        # 1. Resolve correlation ID
        # ------------------------------------------------------------------
        correlation_id: str = request.headers.get("X-Correlation-ID", "").strip()
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # ------------------------------------------------------------------
        # 2. Attach to request state so route handlers can read it directly
        # ------------------------------------------------------------------
        request.state.correlation_id = correlation_id

        # ------------------------------------------------------------------
        # 3. Set context variable (returns a Token for later reset)
        # ------------------------------------------------------------------
        token = correlation_id_var.set(correlation_id)

        # ------------------------------------------------------------------
        # 4. Inject filter into the root logger
        # ------------------------------------------------------------------
        _filter = CorrelationIdFilter()
        root_logger = logging.getLogger()
        root_logger.addFilter(_filter)

        # ------------------------------------------------------------------
        # 5. Delegate to downstream; always clean up in finally
        # ------------------------------------------------------------------
        try:
            response: Response = await call_next(request)
        finally:
            # 6. Remove the filter we added to avoid duplicate filters on
            #    subsequent requests.
            root_logger.removeFilter(_filter)

            # 5. Reset the ContextVar to its value before this request.
            correlation_id_var.reset(token)

        # ------------------------------------------------------------------
        # 7. Echo correlation ID back to the caller
        # ------------------------------------------------------------------
        response.headers["X-Correlation-ID"] = correlation_id
        return response


# ---------------------------------------------------------------------------
# Convenience accessor
# ---------------------------------------------------------------------------


def get_correlation_id() -> str:
    """Return the correlation ID for the current async execution context.

    Returns:
        The correlation ID string set by :class:`CorrelationIdMiddleware`, or
        an empty string when called outside of an active request context (e.g.
        during application startup or in background tasks that have not
        inherited a request context).

    Example::

        logger.info("Starting pipeline", extra={"cid": get_correlation_id()})
    """
    return correlation_id_var.get()
