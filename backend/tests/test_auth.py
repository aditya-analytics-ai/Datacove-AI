"""
Unit tests for utils/auth.py - password hashing and JWT creation/verification.
"""
import pytest
import time
from unittest.mock import patch
from utils.auth import (
    _hash_password, _check_password,
    create_token, _verify_token,
    register_user, login_user,
)


# ── Password hashing ──────────────────────────────────────────────────────────

def test_hash_is_not_plaintext():
    h = _hash_password("secret123")
    assert "secret123" not in h


def test_correct_password_verifies():
    h = _hash_password("mypassword")
    assert _check_password("mypassword", h) is True


def test_wrong_password_fails():
    h = _hash_password("mypassword")
    assert _check_password("wrongpassword", h) is False


def test_different_salts_different_hashes():
    h1 = _hash_password("same")
    h2 = _hash_password("same")
    # Random salt means hashes differ even for same password
    assert h1 != h2
    # But both verify correctly
    assert _check_password("same", h1)
    assert _check_password("same", h2)


# ── JWT ───────────────────────────────────────────────────────────────────────

def test_token_round_trip():
    token = create_token("user-123", "alice")
    data  = _verify_token(token)
    assert data is not None
    assert data["sub"] == "user-123"
    assert data["username"] == "alice"


def test_tampered_token_rejected():
    token = create_token("user-123", "alice")
    # Flip a character in the signature
    parts = token.split(".")
    bad_sig = parts[2][:-1] + ("A" if parts[2][-1] != "A" else "B")
    bad_token = ".".join([parts[0], parts[1], bad_sig])
    assert _verify_token(bad_token) is None


def test_expired_token_rejected():
    token = create_token("user-123", "alice")
    # Fast-forward time past expiry
    with patch("utils.auth.time") as mock_time:
        mock_time.time.return_value = time.time() + 999_999
        assert _verify_token(token) is None


# ── Register / Login ──────────────────────────────────────────────────────────

def test_register_returns_token(tmp_path, monkeypatch):
    # Patch db to avoid actual SQLite writes in unit tests
    calls = {}
    class FakeDB:
        def fetchone(self, sql, params):
            return None  # user doesn't exist yet
        def execute(self, sql, params):
            calls["inserted"] = params
    monkeypatch.setattr("utils.auth.db", FakeDB())
    token = register_user("testuser", "password123")
    assert isinstance(token, str)
    assert len(token.split(".")) == 3


def test_register_duplicate_raises(monkeypatch):
    class FakeDB:
        def fetchone(self, sql, params):
            return {"id": "existing"}  # simulate existing user
        def execute(self, sql, params): pass
    monkeypatch.setattr("utils.auth.db", FakeDB())
    with pytest.raises(ValueError, match="already taken"):
        register_user("existinguser", "password")


def test_login_bad_password_raises(monkeypatch):
    h = _hash_password("correctpassword")
    class FakeDB:
        def fetchone(self, sql, params):
            return {"id": "u1", "password_hash": h}
        def execute(self, sql, params): pass
    monkeypatch.setattr("utils.auth.db", FakeDB())
    with pytest.raises(ValueError, match="Invalid"):
        login_user("alice", "wrongpassword")
