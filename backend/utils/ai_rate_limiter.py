"""
AI Rate Limiter - simple in-process sliding-window limiter for AI API calls.
Prevents hammering external LLM APIs and controls costs.
"""
import time
from collections import deque
from threading import Lock
from fastapi import HTTPException

from config import settings
from utils.logger import logger


class AIRateLimiter:
    """
    Thread-safe sliding-window rate limiter.
    Tracks timestamps of recent AI requests and enforces a per-minute cap.
    """

    def __init__(self, max_per_minute: int = None):
        self._max = max_per_minute or settings.AI_MAX_REQUESTS_PER_MINUTE
        self._timestamps: deque = deque()
        self._lock = Lock()

    def check(self) -> None:
        """
        Call before each AI API request.
        Raises HTTP 429 if the rate limit is exceeded.
        """
        now = time.time()
        window_start = now - 60.0

        with self._lock:
            # Evict timestamps older than 1 minute
            while self._timestamps and self._timestamps[0] < window_start:
                self._timestamps.popleft()

            if len(self._timestamps) >= self._max:
                retry_after = int(60 - (now - self._timestamps[0])) + 1
                logger.warning(f"AI rate limit hit ({self._max}/min). Retry after {retry_after}s")
                raise HTTPException(
                    status_code=429,
                    detail=f"AI request rate limit exceeded ({self._max}/min). "
                           f"Please wait {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)},
                )

            self._timestamps.append(now)


# Shared singleton - import and call `.check()` before every AI API call
ai_rate_limiter = AIRateLimiter()
