"""
middleware/rate_limit.py - global per-IP rate limiting for all API endpoints.

Uses a simple in-process sliding window counter (no Redis required for single-worker).
For multi-worker setups, set REDIS_URL in env to share state via Redis.

Limits (configurable via env):
  - API_RATE_LIMIT_GLOBAL:  300 requests / 60 seconds per IP (default)
  - API_RATE_LIMIT_UPLOAD:   10 requests / 60 seconds per IP (for /upload, /connectors)
  - These sit on top of the existing AI-specific limiter and auth limiter.
"""
from __future__ import annotations

import time
import os
import threading
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# ── Configuration ──────────────────────────────────────────────────────────────
_GLOBAL_LIMIT    = int(os.getenv("API_RATE_LIMIT_GLOBAL", "300"))   # requests
_GLOBAL_WINDOW   = int(os.getenv("API_RATE_LIMIT_WINDOW", "60"))    # seconds
_UPLOAD_LIMIT    = int(os.getenv("API_RATE_LIMIT_UPLOAD", "10"))    # requests
_UPLOAD_WINDOW   = int(os.getenv("API_RATE_LIMIT_UPLOAD_WINDOW", "60"))

# Paths that carry tighter upload limits
_UPLOAD_PREFIXES = ("/api/upload", "/api/connectors")

# Paths exempt from global rate limiting (health probes, frontend static)
_EXEMPT_PREFIXES  = ("/health", "/docs", "/openapi", "/static", "/")


class _SlidingWindow:
    """Thread-safe per-IP sliding window counter."""
    def __init__(self):
        self._windows: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def is_allowed(self, key: str, limit: int, window: int) -> Tuple[bool, int]:
        """
        Returns (allowed, remaining_requests).
        Adds a timestamp and checks against the limit.
        """
        now = time.monotonic()
        cutoff = now - window
        with self._lock:
            dq = self._windows[key]
            # Evict old entries
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= limit:
                return False, 0
            dq.append(now)
            return True, limit - len(dq)


_global_limiter = _SlidingWindow()
_upload_limiter = _SlidingWindow()


def _client_ip(request: Request) -> str:
    """Best-effort client IP extraction (honours X-Forwarded-For from load balancers)."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class GlobalRateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware that applies per-IP rate limits to all API endpoints.

    Response headers added:
      X-RateLimit-Limit     - configured limit
      X-RateLimit-Remaining - requests remaining in current window
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Skip exempt paths
        for prefix in _EXEMPT_PREFIXES:
            if path == prefix or (prefix != "/" and path.startswith(prefix)):
                return await call_next(request)

        ip = _client_ip(request)

        # Tighter limit for upload/connector paths
        for prefix in _UPLOAD_PREFIXES:
            if path.startswith(prefix):
                allowed, remaining = _upload_limiter.is_allowed(
                    ip, _UPLOAD_LIMIT, _UPLOAD_WINDOW
                )
                if not allowed:
                    return JSONResponse(
                        status_code=429,
                        content={"detail": f"Too many upload requests. Limit: {_UPLOAD_LIMIT}/{_UPLOAD_WINDOW}s per IP."},
                        headers={
                            "X-RateLimit-Limit": str(_UPLOAD_LIMIT),
                            "X-RateLimit-Remaining": "0",
                            "Retry-After": str(_UPLOAD_WINDOW),
                        },
                    )
                break

        # Global limit
        allowed, remaining = _global_limiter.is_allowed(ip, _GLOBAL_LIMIT, _GLOBAL_WINDOW)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": f"Too many requests. Limit: {_GLOBAL_LIMIT}/{_GLOBAL_WINDOW}s per IP."},
                headers={
                    "X-RateLimit-Limit": str(_GLOBAL_LIMIT),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": str(_GLOBAL_WINDOW),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(_GLOBAL_LIMIT)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
