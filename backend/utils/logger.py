"""
Structured logging utility - production-grade logger for Datacove.

Features:
  - JSON-structured output (machine-parseable for log aggregators)
  - Separate human-readable format for local development
  - Request ID support for distributed tracing
  - Configurable log level via environment variable LOG_LEVEL
  - Retry/error context helpers

Usage:
    from utils.logger import logger
    logger.info("Profile complete", extra={"rows": 10000, "session_id": "abc123"})
    logger.error("Clean failed", exc_info=True)
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional


# ── Config from environment ───────────────────────────────────────────────────

LOG_LEVEL  = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = os.environ.get("LOG_FORMAT", "text")   # "text" | "json"


# ── JSON formatter ────────────────────────────────────────────────────────────

class JsonFormatter(logging.Formatter):
    """Emit one JSON object per line - ideal for log aggregators (Datadog, CloudWatch, etc.)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level":     record.levelname,
            "logger":    record.name,
            "message":   record.getMessage(),
            "module":    record.module,
            "funcName":  record.funcName,
            "lineno":    record.lineno,
        }

        # Include any extra fields passed via extra={}
        for key, value in record.__dict__.items():
            if key not in logging.LogRecord.__init__.__code__.co_varnames and \
               key not in ("msg", "args", "levelname", "levelno", "pathname",
                           "filename", "module", "funcName", "lineno", "exc_info",
                           "exc_text", "stack_info", "created", "msecs", "relativeCreated",
                           "thread", "threadName", "processName", "process", "name",
                           "message", "asctime"):
                payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


# ── Text formatter (development) ──────────────────────────────────────────────

_TEXT_FORMAT = "%(asctime)s [%(levelname)-8s] %(name)s (%(module)s:%(lineno)d): %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


# ── Build logger ──────────────────────────────────────────────────────────────

def _build_logger(name: str = "datacove") -> logging.Logger:
    log = logging.getLogger(name)

    if log.handlers:
        return log   # already configured (e.g., test re-import)

    log.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    handler = logging.StreamHandler(sys.stdout)

    if LOG_FORMAT == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(_TEXT_FORMAT, datefmt=_DATE_FORMAT))

    log.addHandler(handler)
    log.propagate = False
    return log


logger = _build_logger("datacove")


# ── Context helpers ───────────────────────────────────────────────────────────

class LogContext:
    """
    Attach structured fields to a block of log calls.

    Usage:
        with LogContext(session_id="abc", action="fill_missing"):
            logger.info("Starting clean")   # will include session_id & action
    """

    def __init__(self, **fields):
        self.fields = fields
        self._old_factory = None

    def __enter__(self):
        old_factory = logging.getLogRecordFactory()
        fields = self.fields

        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            for k, v in fields.items():
                setattr(record, k, v)
            return record

        self._old_factory = old_factory
        logging.setLogRecordFactory(record_factory)
        return self

    def __exit__(self, *args):
        if self._old_factory:
            logging.setLogRecordFactory(self._old_factory)


def log_retry(attempt: int, max_attempts: int, error: Exception, context: str = "") -> None:
    """Standardised retry log message."""
    logger.warning(
        f"Retry {attempt}/{max_attempts} - {context}: {type(error).__name__}: {error}"
    )


def log_performance(operation: str, duration_ms: float, **extra) -> None:
    """Log a performance measurement."""
    logger.info(
        f"PERF [{operation}] {duration_ms:.1f}ms",
        extra={"operation": operation, "duration_ms": duration_ms, **extra}
    )
