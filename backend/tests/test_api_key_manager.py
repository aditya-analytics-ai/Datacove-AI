"""
Unit tests for services/api_key_manager.py

Run with:  pytest tests/test_api_key_manager.py -v
"""

import pytest
import time
from services.api_key_manager import (
    APIKeyCreate,
    SCOPES,
    DEFAULT_RATE_LIMITS,
    has_scope,
    has_any_scope,
    _generate_key_id,
    _generate_api_key,
    _get_prefix,
)


class TestKeyGeneration:
    def test_generate_key_id_unique(self):
        ids = [_generate_key_id() for _ in range(100)]
        assert len(set(ids)) == 100  # All unique

    def test_generate_key_id_format(self):
        key_id = _generate_key_id()
        assert key_id.startswith("dk_")
        assert len(key_id) > 10

    def test_generate_api_key_format(self):
        key = _generate_api_key()
        assert key.startswith("dk_live_")
        assert len(key) > 20

    def test_get_prefix(self):
        key = "dk_live_abc123xyz456"
        prefix = _get_prefix(key)
        assert prefix == "dk_live_abc1"
        assert len(prefix) == 12


class TestScopes:
    def test_all_scopes_defined(self):
        assert len(SCOPES) > 0
        assert "datasets:read" in SCOPES
        assert "datasets:write" in SCOPES
        assert "admin" in SCOPES

    def test_scope_descriptions(self):
        for scope, desc in SCOPES.items():
            assert isinstance(scope, str)
            assert isinstance(desc, str)
            assert len(desc) > 0


class TestTierLimits:
    def test_all_tiers_defined(self):
        assert "free" in DEFAULT_RATE_LIMITS
        assert "basic" in DEFAULT_RATE_LIMITS
        assert "pro" in DEFAULT_RATE_LIMITS
        assert "enterprise" in DEFAULT_RATE_LIMITS

    def test_free_tier_limits(self):
        limits = DEFAULT_RATE_LIMITS["free"]
        assert limits["requests_per_minute"] == 60
        assert limits["requests_per_day"] == 1000
        assert limits["requests_per_month"] == 10000

    def test_enterprise_tier_limits(self):
        limits = DEFAULT_RATE_LIMITS["enterprise"]
        assert limits["requests_per_minute"] == 10000
        assert limits["requests_per_month"] > 0


class TestScopeChecking:
    def test_has_scope_exact_match(self):
        class MockAuth:
            scopes = ["datasets:read", "datasets:write"]
            valid = True

        assert has_scope(MockAuth(), "datasets:read") is True
        assert has_scope(MockAuth(), "datasets:write") is True

    def test_has_scope_admin_always_true(self):
        class MockAuth:
            scopes = ["admin"]
            valid = True

        assert has_scope(MockAuth(), "datasets:read") is True
        assert has_scope(MockAuth(), "datasets:write") is True
        assert has_scope(MockAuth(), "admin") is True

    def test_has_scope_missing(self):
        class MockAuth:
            scopes = ["datasets:read"]
            valid = True

        assert has_scope(MockAuth(), "datasets:write") is False

    def test_has_scope_invalid_auth(self):
        class MockAuth:
            valid = False

        assert has_scope(MockAuth(), "datasets:read") is False

    def test_has_any_scope(self):
        class MockAuth:
            scopes = ["datasets:read"]
            valid = True

        assert has_any_scope(MockAuth(), ["datasets:read", "datasets:write"]) is True
        assert has_any_scope(MockAuth(), ["datasets:write", "datasets:delete"]) is False


class TestAPIKeyCreate:
    def test_default_values(self):
        key = APIKeyCreate(name="test-key")
        assert key.name == "test-key"
        assert key.tier == "free"
        assert key.scopes == ["datasets:read", "datasets:write"]
        assert key.expires_in_days is None

    def test_custom_values(self):
        key = APIKeyCreate(
            name="custom-key",
            tier="pro",
            scopes=["datasets:read", "datasets:write", "datasets:delete"],
            expires_in_days=90,
        )
        assert key.name == "custom-key"
        assert key.tier == "pro"
        assert len(key.scopes) == 3
        assert key.expires_in_days == 90
