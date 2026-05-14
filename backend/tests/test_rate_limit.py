"""
tests/test_rate_limit.py - Unit tests for GlobalRateLimitMiddleware.

Tests the sliding-window rate limiter using the real _SlidingWindow API:
  is_allowed(key, limit, window) -> (bool, int remaining)

Run with:  pytest tests/test_rate_limit.py -v
"""
import time
import pytest
from middleware.rate_limit import _SlidingWindow, _UPLOAD_PREFIXES, _EXEMPT_PREFIXES


# ── _SlidingWindow ────────────────────────────────────────────────────────────

class TestSlidingWindow:

    def test_allows_up_to_limit(self):
        w = _SlidingWindow()
        for i in range(5):
            allowed, remaining = w.is_allowed("ip1", limit=5, window=60)
            assert allowed is True, f"Request {i+1} should be allowed"

    def test_blocks_beyond_limit(self):
        w = _SlidingWindow()
        for _ in range(3):
            w.is_allowed("ip2", limit=3, window=60)
        allowed, remaining = w.is_allowed("ip2", limit=3, window=60)
        assert allowed is False    # 4th request blocked
        assert remaining == 0

    def test_remaining_decreases(self):
        w = _SlidingWindow()
        _, r1 = w.is_allowed("ip3", limit=10, window=60)
        assert r1 == 9             # 10 - 1 = 9 after first hit
        _, r2 = w.is_allowed("ip3", limit=10, window=60)
        assert r2 == 8             # 10 - 2 = 8 after second hit

    def test_remaining_zero_when_blocked(self):
        w = _SlidingWindow()
        for _ in range(2):
            w.is_allowed("ip4", limit=2, window=60)
        allowed, remaining = w.is_allowed("ip4", limit=2, window=60)
        assert allowed is False
        assert remaining == 0

    def test_window_resets_after_expiry(self):
        w = _SlidingWindow()
        # Exhaust a 1-second window
        w.is_allowed("ip5", limit=1, window=1)
        allowed, _ = w.is_allowed("ip5", limit=1, window=1)
        assert allowed is False    # blocked immediately
        time.sleep(1.1)            # wait for window to expire
        allowed, _ = w.is_allowed("ip5", limit=1, window=1)
        assert allowed is True     # should pass again

    def test_different_keys_are_independent(self):
        w = _SlidingWindow()
        # Exhaust limit for key_a
        for _ in range(3):
            w.is_allowed("key_a", limit=3, window=60)
        allowed_a, _ = w.is_allowed("key_a", limit=3, window=60)
        allowed_b, _ = w.is_allowed("key_b", limit=3, window=60)
        assert allowed_a is False   # key_a exhausted
        assert allowed_b is True    # key_b untouched

    def test_zero_limit_always_blocks(self):
        w = _SlidingWindow()
        allowed, _ = w.is_allowed("ip6", limit=0, window=60)
        assert allowed is False


# ── Path classification ────────────────────────────────────────────────────────

class TestPathClassification:
    """Verify upload and exempt path lists are correct."""

    def test_upload_paths_are_restricted(self):
        restricted_paths = ["/api/upload", "/api/upload/async", "/api/connectors/s3"]
        for path in restricted_paths:
            assert any(path.startswith(p) for p in _UPLOAD_PREFIXES), \
                f"{path} should be in upload prefixes"

    def test_health_is_exempt(self):
        assert any("/health".startswith(p) or "/health" == p
                   for p in _EXEMPT_PREFIXES), "/health must be exempt"

    def test_docs_is_exempt(self):
        assert any("/docs".startswith(p) for p in _EXEMPT_PREFIXES), \
            "/docs must be exempt"

    def test_api_routes_not_exempt(self):
        api_path = "/api/clean"
        assert not any(
            api_path == p or (p != "/" and api_path.startswith(p))
            for p in _EXEMPT_PREFIXES
        ), "/api/* routes should NOT be exempt"
