"""
utils/retry.py - Production retry with exponential backoff + jitter.

Usage (sync):
    from utils.retry import retry, AI_RETRY
    result = retry(my_fn, args=(a, b), config=AI_RETRY)

Usage (async):
    from utils.retry import async_retry, AI_RETRY
    result = await async_retry(my_async_fn, args=(a,), config=AI_RETRY)

Usage (decorator):
    from utils.retry import retry_decorator, AI_RETRY
    @retry_decorator(AI_RETRY)
    def call_api(): ...
"""
from __future__ import annotations

import asyncio
import functools
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Tuple, Type

from utils.logger import logger


# ── Config ────────────────────────────────────────────────────────────────────

@dataclass
class RetryConfig:
    max_attempts:      int   = 3
    base_delay:        float = 1.0    # seconds before first retry
    backoff_factor:    float = 2.0    # multiply delay by this each attempt
    max_delay:         float = 60.0   # cap on delay between retries
    jitter:            float = 0.25   # ± fraction of delay added randomly
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,)
    retryable_status_codes: Tuple[int, ...] = ()   # for HTTP errors
    on_retry: Optional[Callable[[int, Exception], None]] = None  # callback


# Pre-built configs for common use cases
AI_RETRY = RetryConfig(
    max_attempts=4,
    base_delay=2.0,
    backoff_factor=2.0,
    max_delay=30.0,
    jitter=0.3,
    retryable_status_codes=(429, 500, 502, 503, 529),
)

CONNECTOR_RETRY = RetryConfig(
    max_attempts=3,
    base_delay=1.0,
    backoff_factor=2.0,
    max_delay=15.0,
    jitter=0.2,
    retryable_status_codes=(429, 500, 502, 503, 504),
)

FAST_RETRY = RetryConfig(
    max_attempts=2,
    base_delay=0.5,
    backoff_factor=2.0,
    max_delay=5.0,
    jitter=0.1,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_retryable(exc: Exception, config: RetryConfig) -> bool:
    """Return True if this exception should trigger a retry."""
    # Check retryable exception types
    if isinstance(exc, config.retryable_exceptions):
        return True

    # Check HTTP status codes embedded in the exception
    if config.retryable_status_codes:
        status = (
            getattr(exc, "status_code", None)
            or getattr(exc, "status", None)
            or getattr(getattr(exc, "response", None), "status_code", None)
        )
        if status in config.retryable_status_codes:
            return True

    return False


def _compute_delay(attempt: int, config: RetryConfig) -> float:
    """Exponential backoff with jitter."""
    delay = min(config.base_delay * (config.backoff_factor ** attempt), config.max_delay)
    jitter_amount = delay * config.jitter * (2 * random.random() - 1)
    return max(0.0, delay + jitter_amount)


# ── Sync retry ────────────────────────────────────────────────────────────────

def retry(
    fn: Callable,
    args: tuple = (),
    kwargs: dict | None = None,
    config: RetryConfig = AI_RETRY,
    context: str = "",
) -> Any:
    """
    Call fn(*args, **kwargs) with retry on failure.

    Args:
        fn:      The callable to invoke
        args:    Positional arguments
        kwargs:  Keyword arguments
        config:  RetryConfig controlling behavior
        context: Human label for log messages

    Returns:
        The return value of fn on success.

    Raises:
        The last exception if all attempts are exhausted.
    """
    kwargs = kwargs or {}
    label  = context or getattr(fn, "__name__", str(fn))
    last_exc: Exception | None = None

    for attempt in range(config.max_attempts):
        try:
            result = fn(*args, **kwargs)
            if attempt > 0:
                logger.info(f"Retry succeeded: {label} (attempt {attempt + 1}/{config.max_attempts})")
            return result
        except Exception as exc:
            last_exc = exc
            if attempt == config.max_attempts - 1:
                break  # final attempt - don't sleep

            if not _is_retryable(exc, config):
                logger.warning(f"Non-retryable error in {label}: {type(exc).__name__}: {exc}")
                raise

            delay = _compute_delay(attempt, config)
            logger.warning(
                f"Retry {attempt + 1}/{config.max_attempts - 1} for {label} "
                f"after {delay:.1f}s - {type(exc).__name__}: {exc}"
            )
            if config.on_retry:
                try:
                    config.on_retry(attempt + 1, exc)
                except Exception:
                    pass
            time.sleep(delay)

    logger.error(f"All {config.max_attempts} attempts failed for {label}: {last_exc}")
    raise last_exc


# ── Async retry ───────────────────────────────────────────────────────────────

async def async_retry(
    fn: Callable,
    args: tuple = (),
    kwargs: dict | None = None,
    config: RetryConfig = AI_RETRY,
    context: str = "",
) -> Any:
    """Async version of retry - uses asyncio.sleep between attempts."""
    kwargs = kwargs or {}
    label  = context or getattr(fn, "__name__", str(fn))
    last_exc: Exception | None = None

    for attempt in range(config.max_attempts):
        try:
            result = await fn(*args, **kwargs)
            if attempt > 0:
                logger.info(f"Async retry succeeded: {label} (attempt {attempt + 1})")
            return result
        except Exception as exc:
            last_exc = exc
            if attempt == config.max_attempts - 1:
                break

            if not _is_retryable(exc, config):
                logger.warning(f"Non-retryable async error in {label}: {type(exc).__name__}: {exc}")
                raise

            delay = _compute_delay(attempt, config)
            logger.warning(
                f"Async retry {attempt + 1}/{config.max_attempts - 1} for {label} "
                f"after {delay:.1f}s - {type(exc).__name__}: {exc}"
            )
            if config.on_retry:
                try:
                    config.on_retry(attempt + 1, exc)
                except Exception:
                    pass
            await asyncio.sleep(delay)

    logger.error(f"All {config.max_attempts} async attempts failed for {label}: {last_exc}")
    raise last_exc


# ── Decorator ─────────────────────────────────────────────────────────────────

def retry_decorator(config: RetryConfig = AI_RETRY):
    """
    Decorator that wraps a function with retry logic.

    @retry_decorator(AI_RETRY)
    def call_anthropic(): ...
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            return retry(fn, args=args, kwargs=kwargs, config=config)

        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            return await async_retry(fn, args=args, kwargs=kwargs, config=config)

        if asyncio.iscoroutinefunction(fn):
            return async_wrapper
        return sync_wrapper

    return decorator
