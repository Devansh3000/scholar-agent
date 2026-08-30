"""
Structured logging configuration for the Literature Review Web Application.

Provides a JSON-based logging formatter, a setup function that configures
the root logger with console (and optional rotating-file) handlers, and a
convenience factory for named loggers.

Usage::

    from config.logging_config import setup_logging, get_logger

    setup_logging(log_level="INFO", log_file="/var/log/app.log")
    logger = get_logger(__name__)
    logger.info("Server started", extra={"correlation_id": "abc-123"})
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
import datetime
from typing import Any


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON objects.

    The emitted JSON always contains the following fields:

    - ``timestamp``     — ISO 8601 UTC timestamp (e.g. ``2024-01-15T12:34:56.789012Z``)
    - ``level``         — Log level name (e.g. ``INFO``, ``ERROR``)
    - ``logger``        — Logger name (``record.name``)
    - ``message``       — The formatted log message
    - ``correlation_id``— Value of ``record.correlation_id`` when present, else ``""``
    - ``module``        — Source module (``record.module``)
    - ``function``      — Calling function (``record.funcName``)
    - ``line``          — Source line number (``record.lineno``)

    Any *extra* keys attached to the log record that are not part of the
    standard ``logging.LogRecord`` attribute set are appended to the JSON
    object so callers can pass arbitrary structured context::

        logger.info("paper fetched", extra={"paper_id": "arxiv-123", "source": "arxiv"})
    """

    # Attributes that are part of every LogRecord and should NOT be forwarded
    # as "extra" fields to avoid cluttering the JSON output.
    _RESERVED_ATTRS: frozenset[str] = frozenset(
        {
            "args",
            "asctime",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "message",
            "module",
            "msecs",
            "msg",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "taskName",
            "thread",
            "threadName",
        }
    )

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        """Serialise *record* to a JSON string."""
        # Ensure record.message is populated (calls record.getMessage())
        record.message = record.getMessage()

        # Build the base payload
        log_entry: dict[str, Any] = {
            "timestamp": self._utc_iso(record.created),
            "level": record.levelname,
            "logger": record.name,
            "message": record.message,
            "correlation_id": getattr(record, "correlation_id", ""),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Append exception info when present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        if record.stack_info:
            log_entry["stack_info"] = self.formatStack(record.stack_info)

        # Forward any extra fields the caller attached
        for key, value in record.__dict__.items():
            if key not in self._RESERVED_ATTRS and not key.startswith("_"):
                log_entry[key] = value

        return json.dumps(log_entry, default=str, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _utc_iso(created: float) -> str:
        """Convert a ``time.time()`` float to an ISO 8601 UTC string."""
        dt = datetime.datetime.fromtimestamp(created, tz=datetime.timezone.utc)
        return dt.isoformat()


def setup_logging(
    log_level: str = "INFO",
    log_file: str | None = None,
) -> None:
    """Configure the root logger with structured JSON output.

    Args:
        log_level: Logging level name accepted by :func:`logging.getLevelName`
                   (e.g. ``"DEBUG"``, ``"INFO"``, ``"WARNING"``, ``"ERROR"``).
                   Defaults to ``"INFO"``.
        log_file:  Optional path to a log file.  When provided a
                   :class:`~logging.handlers.RotatingFileHandler` is added
                   alongside the console handler (10 MB max size, 5 backups).
                   Defaults to ``None`` (console only).

    Side effects:
        - Reconfigures the root logger level and handlers.
        - Adds a :class:`~logging.StreamHandler` writing to ``sys.stdout``.
        - Sets ``uvicorn.access`` logger to ``WARNING`` to suppress per-request
          noise that duplicates the application-level request-logging middleware.
        - Sets ``httpx`` and ``httpcore`` loggers to ``WARNING`` to suppress
          verbose HTTP wire logs from the async HTTP client stack.
    """
    numeric_level = logging.getLevelName(log_level.upper())
    if not isinstance(numeric_level, int):
        # Fallback to INFO for unrecognised level strings
        numeric_level = logging.INFO

    formatter = JSONFormatter()

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove any handlers that may have been added by earlier calls or by
    # importing third-party libraries before setup_logging is called.
    root_logger.handlers.clear()

    # --- Console (stream) handler — explicitly stdout, not stderr ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # --- Optional rotating file handler ---
    if log_file is not None:
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # --- Suppress noisy third-party loggers ---
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named :class:`logging.Logger`.

    This is a thin convenience wrapper around :func:`logging.getLogger` so
    that application modules do not need to import ``logging`` directly.

    Args:
        name: Logger name — typically ``__name__`` of the calling module.

    Returns:
        A :class:`logging.Logger` instance.

    Example::

        logger = get_logger(__name__)
        logger.info("Processing started", extra={"job_id": job_id})
    """
    return logging.getLogger(name)
