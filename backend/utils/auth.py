"""
auth.py - JWT-based authentication utilities (v3).

v3 changes:
  - AuthUser gains `role` (user | admin) and `is_active` fields.
  - create_token / _verify_token embed role in the JWT payload.
  - require_admin() dependency - raises 403 for non-admin callers.
  - Inactive accounts are rejected at login and token validation.
  - Audit log entry written on every login.
"""

from __future__ import annotations

import collections
import hashlib
import hmac
import json
import os
import threading
import time
import base64
import uuid
from dataclasses import dataclass, field
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import settings
from utils.db import db
from utils.errors import AuthConflictError, AuthCredentialsError, AuthInactiveError
from utils.logger import logger

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class AuthUser:
    user_id: str
    username: str
    role: str = "user"
    is_active: bool = True

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


# ── Password hashing ──────────────────────────────────────────────────────────


def _hash_password(password: str, salt: bytes | None = None) -> str:
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{salt.hex()}:{dk.hex()}"


def _check_password(password: str, stored: str) -> bool:
    try:
        salt_hex, _ = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        expected = _hash_password(password, salt)
        return hmac.compare_digest(stored, expected)
    except Exception:
        return False


# ── Minimal JWT (HS256, stdlib only) ─────────────────────────────────────────


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * pad)


def create_token(user_id: str, username: str, role: str = "user") -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    exp = int(time.time()) + settings.JWT_EXPIRE_MINUTES * 60
    payload = _b64url(
        json.dumps(
            {
                "sub": user_id,
                "username": username,
                "role": role,
                "exp": exp,
                "type": "access",
            }
        ).encode()
    )
    sig_input = f"{header}.{payload}".encode()
    sig = _b64url(
        hmac.new(settings.JWT_SECRET.encode(), sig_input, hashlib.sha256).digest()
    )
    return f"{header}.{payload}.{sig}"


def create_refresh_token(user_id: str, username: str, role: str = "user") -> str:
    """Long-lived refresh token (default 30 days)."""
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    exp = int(time.time()) + settings.JWT_REFRESH_EXPIRE_DAYS * 86400
    payload = _b64url(
        json.dumps(
            {
                "sub": user_id,
                "username": username,
                "role": role,
                "exp": exp,
                "type": "refresh",
            }
        ).encode()
    )
    sig_input = f"{header}.{payload}".encode()
    sig = _b64url(
        hmac.new(settings.JWT_SECRET.encode(), sig_input, hashlib.sha256).digest()
    )
    return f"{header}.{payload}.{sig}"


def _verify_token(token: str) -> Optional[dict]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, payload, sig = parts
        sig_input = f"{header}.{payload}".encode()
        expected = _b64url(
            hmac.new(settings.JWT_SECRET.encode(), sig_input, hashlib.sha256).digest()
        )
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(_b64url_decode(payload))
        if data.get("exp", 0) < time.time():
            return None
        # Reject refresh tokens used as access tokens
        if data.get("type") == "refresh":
            return None
        return data
    except Exception:
        return None


def verify_token(token: str) -> Optional[dict]:
    """Public wrapper for _verify_token."""
    return _verify_token(token)


def verify_refresh_token(token: str) -> Optional[dict]:
    """Validate a refresh token. Rejects access tokens."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, payload, sig = parts
        sig_input = f"{header}.{payload}".encode()
        expected = _b64url(
            hmac.new(settings.JWT_SECRET.encode(), sig_input, hashlib.sha256).digest()
        )
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(_b64url_decode(payload))
        if data.get("exp", 0) < time.time():
            return None
        if data.get("type") != "refresh":
            return None
        return data
    except Exception:
        return None


# ── FastAPI dependencies ──────────────────────────────────────────────────────


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthUser:
    """
    Returns the authenticated user.
    AUTH_ENABLED=False  →  guest user (local dev only).
    AUTH_ENABLED=True   →  validates Bearer token, raises 401 on failure.
    Inactive accounts raise 403.
    """
    if not settings.AUTH_ENABLED:
        return AuthUser(user_id="guest", username="guest", role="admin")

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    data = _verify_token(credentials.credentials)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Re-check is_active against DB (admin may have deactivated the account)
    row = db.fetchone("SELECT is_active, role FROM users WHERE id = ?", (data["sub"],))
    if row and not row["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    return AuthUser(
        user_id=data["sub"],
        username=data["username"],
        role=data.get("role", "user"),
        is_active=True,
    )


def require_auth(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    """Alias - always enforces auth regardless of AUTH_ENABLED."""
    return user


def require_admin(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    """Dependency that restricts an endpoint to admin-role users only."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return user


# ── Register / login ──────────────────────────────────────────────────────────


def register_user(username: str, password: str, role: str = "user") -> str:
    """Create user in DB, return JWT. Raises ValueError if username taken."""
    existing = db.fetchone("SELECT id FROM users WHERE username = ?", (username,))
    if existing:
        raise AuthConflictError("Username already taken.")
    user_id = str(uuid.uuid4())
    pw_hash = _hash_password(password)
    db.execute(
        "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, ?, ?)",
        (user_id, username, pw_hash, role),
    )
    logger.info(f"Auth: registered user '{username}' id={user_id} role={role}")
    return create_token(user_id, username, role)


def login_user(username: str, password: str, ip: str | None = None) -> tuple[str, str]:
    """Verify credentials, return (access_token, refresh_token). Raises ValueError on bad credentials."""
    row = db.fetchone(
        "SELECT id, password_hash, role, is_active FROM users WHERE username = ?",
        (username,),
    )
    if not row or not _check_password(password, row["password_hash"]):
        raise AuthCredentialsError("Invalid username or password.")
    if not row["is_active"]:
        raise AuthInactiveError("Account is deactivated.")

    db.log_audit(row["id"], username, "login", ip_address=ip)
    logger.info(f"Auth: login '{username}'")
    access = create_token(row["id"], username, row["role"])
    refresh = create_refresh_token(row["id"], username, row["role"])
    return access, refresh


# ── Auth rate limiter ─────────────────────────────────────────────────────────────


class AuthRateLimiter:
    """
    Simple in-process per-IP sliding-window rate limiter for auth endpoints.
    Default: max 10 attempts per 60 seconds per IP address.
    Thread-safe via a reentrant lock.
    """

    def __init__(self, max_attempts: int = 10, window_seconds: int = 60):
        self._max = max_attempts
        self._window = window_seconds
        self._buckets: dict[str, collections.deque] = {}
        self._lock = threading.Lock()

    def check(self, ip: str) -> None:
        """
        Record an attempt for `ip`.
        Raises HTTPException 429 if the limit is exceeded.
        """
        now = time.time()
        with self._lock:
            if ip not in self._buckets:
                self._buckets[ip] = collections.deque()
            dq = self._buckets[ip]
            # Evict timestamps outside the window
            while dq and dq[0] < now - self._window:
                dq.popleft()
            if len(dq) >= self._max:
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"Too many login attempts. "
                        f"Please wait {self._window} seconds before trying again."
                    ),
                    headers={"Retry-After": str(self._window)},
                )
            dq.append(now)


# Singleton - shared across all auth route calls
auth_rate_limiter = AuthRateLimiter(max_attempts=10, window_seconds=60)
