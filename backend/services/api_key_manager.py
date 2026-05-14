"""
API Key Management - create, manage, and authenticate API keys for public API access.

Features:
  ✅ API key generation with configurable scopes and rate limits
  ✅ Per-key usage tracking and quotas
  ✅ Key expiration and revocation
  ✅ Scope-based access control (read, write, admin)
  ✅ IP whitelisting for enterprise security
  ✅ Usage analytics and billing attribution
  ✅ Key rotation without downtime
"""

from __future__ import annotations

import json
import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional

import pandas as pd
from pydantic import BaseModel, Field

from utils.db import db
from utils.errors import APIKeyNotFoundError
from utils.logger import logger
from config import settings


# ── Constants ──────────────────────────────────────────────────────────────────

API_KEY_LENGTH = 32
KEY_HASH_ROUNDS = 100_000

DEFAULT_RATE_LIMITS = {
    "free": {
        "requests_per_minute": 60,
        "requests_per_day": 1000,
        "requests_per_month": 10000,
    },
    "basic": {
        "requests_per_minute": 300,
        "requests_per_day": 10000,
        "requests_per_month": 100000,
    },
    "pro": {
        "requests_per_minute": 1000,
        "requests_per_day": 100000,
        "requests_per_month": 1000000,
    },
    "enterprise": {
        "requests_per_minute": 10000,
        "requests_per_day": 1000000,
        "requests_per_month": 10000000,
    },
}

SCOPES = {
    "datasets:read": "Read datasets and metadata",
    "datasets:write": "Create and modify datasets",
    "datasets:delete": "Delete datasets",
    "pipelines:read": "Read pipeline configurations",
    "pipelines:write": "Create and modify pipelines",
    "pipelines:execute": "Execute pipeline runs",
    "cleaning:execute": "Execute cleaning transformations",
    "analysis:read": "Read analysis results",
    "analysis:execute": "Run analysis operations",
    "export:execute": "Export data to external destinations",
    "admin": "Full administrative access",
}


# ── Models ─────────────────────────────────────────────────────────────────────


class APIKeyCreate(BaseModel):
    name: str = Field(description="Human-readable name for this API key")
    tier: Literal["free", "basic", "pro", "enterprise"] = "free"
    scopes: List[str] = Field(
        default=["datasets:read", "datasets:write"],
        description="List of permission scopes",
    )
    expires_in_days: Optional[int] = Field(
        default=None,
        ge=1,
        le=365,
        description="Days until expiration (None = never expires)",
    )
    ip_whitelist: Optional[List[str]] = Field(
        default=None,
        description="Allowed IP addresses (None = any IP)",
    )
    rate_limit_override: Optional[Dict[str, int]] = Field(
        default=None,
        description="Override default rate limits",
    )


class APIKey(BaseModel):
    key_id: str
    name: str
    key_prefix: str
    tier: str
    scopes: List[str]
    rate_limits: Dict[str, int]
    created_at: str
    expires_at: Optional[str]
    last_used_at: Optional[str]
    is_active: bool
    ip_whitelist: Optional[List[str]]


class APIKeyResponse(BaseModel):
    key_id: str
    name: str
    key: str = Field(description="The full API key (only shown once at creation time)")
    key_prefix: str
    tier: str
    scopes: List[str]
    rate_limits: Dict[str, int]
    created_at: str
    expires_at: Optional[str]
    message: str = "Store this key securely. It will not be shown again."


class UsageRecord(BaseModel):
    key_id: str
    endpoint: str
    method: str
    status_code: int
    response_time_ms: int
    timestamp: str


# ── Database Schema ─────────────────────────────────────────────────────────────


def init_api_keys_table():
    """Create the API keys table if it doesn't exist."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS api_keys (
            key_id         VARCHAR(64) PRIMARY KEY,
            key_hash       VARCHAR(256) NOT NULL,
            key_prefix     VARCHAR(8)  NOT NULL,
            name           VARCHAR(255) NOT NULL,
            owner_id       VARCHAR(64) NOT NULL,
            tier           VARCHAR(32) NOT NULL DEFAULT 'free',
            scopes         JSON NOT NULL,
            rate_limits    JSON NOT NULL,
            expires_at     DATETIME NULL,
            last_used_at   DATETIME NULL,
            is_active      BOOLEAN NOT NULL DEFAULT TRUE,
            ip_whitelist   JSON NULL,
            created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_owner (owner_id),
            INDEX idx_active (is_active)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        (),
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS api_key_usage (
            id            BIGINT AUTO_INCREMENT PRIMARY KEY,
            key_id        VARCHAR(64) NOT NULL,
            endpoint      VARCHAR(255) NOT NULL,
            method        VARCHAR(10) NOT NULL,
            status_code   INT NOT NULL,
            response_time_ms INT NOT NULL,
            request_size  INT DEFAULT 0,
            response_size INT DEFAULT 0,
            ip_address    VARCHAR(45),
            user_agent    VARCHAR(512),
            timestamp     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_key_time (key_id, timestamp),
            INDEX idx_endpoint (endpoint)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        (),
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS api_key_rate_limits (
            key_id           VARCHAR(64) PRIMARY KEY,
            minute_requests  INT NOT NULL DEFAULT 0,
            minute_window    DATETIME NOT NULL,
            day_requests     INT NOT NULL DEFAULT 0,
            day_window       DATE NOT NULL,
            month_requests   INT NOT NULL DEFAULT 0,
            month_window     DATE NOT NULL,
            INDEX idx_key_minute (key_id, minute_window),
            INDEX idx_key_day (key_id, day_window),
            INDEX idx_key_month (key_id, month_window)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        (),
    )


# ── Key Generation ──────────────────────────────────────────────────────────────


def _generate_key_id() -> str:
    """Generate a unique key ID."""
    return f"dk_{secrets.token_hex(16)}"


def _generate_api_key() -> str:
    """Generate a secure API key."""
    return f"dk_live_{secrets.token_urlsafe(API_KEY_LENGTH)}"


def _hash_key(key: str) -> str:
    """Create a secure hash of the API key for storage."""
    salt = os.environ.get("API_KEY_SALT") or settings.JWT_SECRET
    return hashlib.pbkdf2_hmac(
        "sha256",
        key.encode(),
        salt.encode(),
        KEY_HASH_ROUNDS,
    ).hex()


def _get_prefix(key: str) -> str:
    """Get the visible prefix of a key for identification."""
    return key[:12]


def _serialize_json(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value)


def _parse_json_field(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode()
    if isinstance(value, str):
        return json.loads(value)
    return value


# ── CRUD Operations ─────────────────────────────────────────────────────────────


def create_api_key(
    owner_id: str,
    request: APIKeyCreate,
) -> APIKeyResponse:
    """
    Create a new API key for a user or organization.
    Returns the full key only at creation time.
    """
    init_api_keys_table()

    key_id = _generate_key_id()
    raw_key = _generate_api_key()
    key_hash = _hash_key(raw_key)
    key_prefix = _get_prefix(raw_key)

    rate_limits = request.rate_limit_override or DEFAULT_RATE_LIMITS.get(
        request.tier, DEFAULT_RATE_LIMITS["free"]
    )

    expires_at = None
    if request.expires_in_days:
        expires_at = (
            datetime.now(timezone.utc) + timedelta(days=request.expires_in_days)
        ).isoformat()

    db.execute(
        """
        INSERT INTO api_keys
            (key_id, key_hash, key_prefix, name, owner_id, tier, scopes, rate_limits, expires_at, ip_whitelist)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            key_id,
            key_hash,
            key_prefix,
            request.name,
            owner_id,
            request.tier,
            _serialize_json(request.scopes),
            _serialize_json(rate_limits),
            expires_at,
            _serialize_json(request.ip_whitelist),
        ),
    )

    db.execute(
        """
        INSERT INTO api_key_rate_limits
            (key_id, minute_window, day_window, month_window)
        VALUES (%s, %s, %s, %s)
        """,
        (
            key_id,
            datetime.now(timezone.utc).replace(second=0, microsecond=0),
            datetime.now(timezone.utc).date(),
            datetime.now(timezone.utc).date().replace(day=1),
        ),
    )

    logger.info(f"API key created: {key_id} for owner {owner_id}")

    return APIKeyResponse(
        key_id=key_id,
        name=request.name,
        key=raw_key,
        key_prefix=key_prefix,
        tier=request.tier,
        scopes=request.scopes,
        rate_limits=rate_limits,
        created_at=datetime.now(timezone.utc).isoformat(),
        expires_at=expires_at,
        message="Store this key securely. It will not be shown again.",
    )


def get_api_keys(owner_id: str) -> List[APIKey]:
    """List all API keys for an owner (without the secret)."""
    rows = db.fetchall(
        "SELECT key_id, key_prefix, name, tier, scopes, rate_limits, created_at, expires_at, last_used_at, is_active, ip_whitelist FROM api_keys WHERE owner_id = %s ORDER BY created_at DESC",
        (owner_id,),
    )
    return [
        APIKey(
            key_id=row[0],
            name=row[2],
            key_prefix=row[1],
            tier=row[3],
            scopes=_parse_json_field(row[4], []),
            rate_limits=_parse_json_field(row[5], {}),
            created_at=row[6].isoformat() if row[6] else None,
            expires_at=row[7].isoformat() if row[7] else None,
            last_used_at=row[8].isoformat() if row[8] else None,
            is_active=bool(row[9]),
            ip_whitelist=_parse_json_field(row[10], None),
        )
        for row in rows
    ]


def get_api_key(key_id: str, owner_id: str) -> Optional[APIKey]:
    """Get a specific API key by ID."""
    row = db.fetchone(
        "SELECT key_id, key_prefix, name, tier, scopes, rate_limits, created_at, expires_at, last_used_at, is_active, ip_whitelist FROM api_keys WHERE key_id = %s AND owner_id = %s",
        (key_id, owner_id),
    )
    if not row:
        return None

    return APIKey(
        key_id=row[0],
        name=row[2],
        key_prefix=row[1],
        tier=row[3],
        scopes=_parse_json_field(row[4], []),
        rate_limits=_parse_json_field(row[5], {}),
        created_at=row[6].isoformat() if row[6] else None,
        expires_at=row[7].isoformat() if row[7] else None,
        last_used_at=row[8].isoformat() if row[8] else None,
        is_active=bool(row[9]),
        ip_whitelist=_parse_json_field(row[10], None),
    )


def revoke_api_key(key_id: str, owner_id: str) -> bool:
    """Revoke an API key (soft delete)."""
    result = db.execute(
        "UPDATE api_keys SET is_active = FALSE WHERE key_id = %s AND owner_id = %s",
        (key_id, owner_id),
    )
    if result > 0:
        logger.info(f"API key revoked: {key_id}")
        return True
    return False


def rotate_api_key(key_id: str, owner_id: str) -> APIKeyResponse:
    """
    Rotate an API key: revoke old key and create a new one with same config.
    Allows zero-downtime key rotation.
    """
    old_key = get_api_key(key_id, owner_id)
    if not old_key:
        raise APIKeyNotFoundError(f"API key not found: {key_id}")

    revoke_api_key(key_id, owner_id)

    return create_api_key(
        owner_id,
        APIKeyCreate(
            name=f"{old_key.name} (rotated)",
            tier=old_key.tier,
            scopes=old_key.scopes,
            expires_in_days=None,
            ip_whitelist=old_key.ip_whitelist,
        ),
    )


def delete_api_key(key_id: str, owner_id: str) -> bool:
    """Permanently delete an API key and its usage history."""
    db.execute("DELETE FROM api_key_usage WHERE key_id = %s", (key_id,))
    db.execute("DELETE FROM api_key_rate_limits WHERE key_id = %s", (key_id,))
    result = db.execute(
        "DELETE FROM api_keys WHERE key_id = %s AND owner_id = %s", (key_id, owner_id)
    )
    if result > 0:
        logger.info(f"API key deleted: {key_id}")
        return True
    return False


# ── Authentication & Rate Limiting ─────────────────────────────────────────────


class APIKeyAuthResult(BaseModel):
    valid: bool
    key_id: Optional[str] = None
    owner_id: Optional[str] = None
    scopes: List[str] = []
    rate_limits: Dict[str, int] = {}
    error: Optional[str] = None
    is_rate_limited: bool = False
    retry_after: Optional[int] = None


def authenticate_api_key(
    raw_key: str, ip_address: Optional[str] = None
) -> APIKeyAuthResult:
    """
    Authenticate an API key and check rate limits.

    Returns authentication result with key metadata or error details.
    """
    if not raw_key or not raw_key.startswith("dk_live_"):
        return APIKeyAuthResult(valid=False, error="Invalid API key format")

    key_prefix = _get_prefix(raw_key)

    row = db.fetchone(
        "SELECT key_id, key_hash, owner_id, scopes, rate_limits, expires_at, is_active, ip_whitelist FROM api_keys WHERE key_prefix = %s",
        (key_prefix,),
    )

    if not row:
        return APIKeyAuthResult(valid=False, error="API key not found")

    (
        key_id,
        key_hash,
        owner_id,
        scopes,
        rate_limits,
        expires_at,
        is_active,
        ip_whitelist,
    ) = row

    computed_hash = _hash_key(raw_key)
    if not hmac.compare_digest(computed_hash, key_hash):
        return APIKeyAuthResult(valid=False, error="Invalid API key")

    if not is_active:
        return APIKeyAuthResult(valid=False, error="API key has been revoked")

    if expires_at:
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at < datetime.now(timezone.utc):
            return APIKeyAuthResult(valid=False, error="API key has expired")

    if ip_whitelist:
        ip_whitelist = _parse_json_field(ip_whitelist, [])
        if ip_address and ip_address not in ip_whitelist:
            return APIKeyAuthResult(valid=False, error="IP address not allowed")

    scopes = _parse_json_field(scopes, [])
    rate_limits = _parse_json_field(rate_limits, {})

    rate_limit_result = check_rate_limit(key_id, rate_limits)
    if rate_limit_result["limited"]:
        return APIKeyAuthResult(
            valid=True,
            key_id=key_id,
            owner_id=owner_id,
            scopes=scopes,
            rate_limits=rate_limits,
            is_rate_limited=True,
            retry_after=rate_limit_result["retry_after"],
        )

    db.execute(
        "UPDATE api_keys SET last_used_at = %s WHERE key_id = %s",
        (datetime.now(timezone.utc), key_id),
    )

    return APIKeyAuthResult(
        valid=True,
        key_id=key_id,
        owner_id=owner_id,
        scopes=scopes,
        rate_limits=rate_limits,
    )


def check_rate_limit(key_id: str, rate_limits: Dict[str, int]) -> Dict[str, Any]:
    """
    Check if a key has exceeded its rate limits.
    Returns whether the request should be rate-limited and retry info.
    """
    now = datetime.now(timezone.utc)
    today = now.date()
    month_start = today.replace(day=1)

    row = db.fetchone(
        "SELECT minute_requests, minute_window, day_requests, day_window, month_requests, month_window FROM api_key_rate_limits WHERE key_id = %s",
        (key_id,),
    )

    if not row:
        return {"limited": False}

    (
        minute_requests,
        minute_window,
        day_requests,
        day_window,
        month_requests,
        month_window,
    ) = row

    minute_limit = rate_limits.get("requests_per_minute", 60)
    day_limit = rate_limits.get("requests_per_day", 1000)
    month_limit = rate_limits.get("requests_per_month", 10000)

    if now >= minute_window + timedelta(minutes=1):
        db.execute(
            "UPDATE api_key_rate_limits SET minute_requests = 0, minute_window = %s WHERE key_id = %s",
            (now.replace(second=0, microsecond=0), key_id),
        )
        minute_requests = 0

    if now.date() > day_window:
        db.execute(
            "UPDATE api_key_rate_limits SET day_requests = 0, day_window = %s WHERE key_id = %s",
            (today, key_id),
        )
        day_requests = 0

    if now.date().replace(day=1) > month_window:
        db.execute(
            "UPDATE api_key_rate_limits SET day_requests = 0, day_window = %s WHERE key_id = %s",
            (month_start, key_id),
        )
        month_requests = 0

    if minute_requests >= minute_limit:
        retry_after = int((minute_window + timedelta(minutes=1) - now).total_seconds())
        return {"limited": True, "reason": "minute", "retry_after": max(1, retry_after)}

    if day_requests >= day_limit:
        tomorrow = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        retry_after = int((tomorrow - now).total_seconds())
        return {"limited": True, "reason": "day", "retry_after": retry_after}

    if month_requests >= month_limit:
        next_month = month_start.replace(day=28) + timedelta(days=4)
        next_month = next_month.replace(day=1)
        retry_after = int((next_month - now).total_seconds())
        return {"limited": True, "reason": "month", "retry_after": retry_after}

    db.execute(
        """
        UPDATE api_key_rate_limits 
        SET minute_requests = minute_requests + 1,
            day_requests = day_requests + 1,
            month_requests = month_requests + 1
        WHERE key_id = %s
        """,
        (key_id,),
    )

    return {"limited": False}


def has_scope(auth_result: APIKeyAuthResult, required_scope: str) -> bool:
    """Check if authenticated key has a specific scope."""
    if not auth_result.valid:
        return False
    if "admin" in auth_result.scopes:
        return True
    return required_scope in auth_result.scopes


def has_any_scope(auth_result: APIKeyAuthResult, required_scopes: List[str]) -> bool:
    """Check if authenticated key has any of the specified scopes."""
    return any(has_scope(auth_result, scope) for scope in required_scopes)


# ── Usage Tracking ─────────────────────────────────────────────────────────────


def record_usage(
    key_id: str,
    endpoint: str,
    method: str,
    status_code: int,
    response_time_ms: int,
    request_size: int = 0,
    response_size: int = 0,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Record API usage for analytics and billing."""
    db.execute(
        """
        INSERT INTO api_key_usage
            (key_id, endpoint, method, status_code, response_time_ms, request_size, response_size, ip_address, user_agent)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            key_id,
            endpoint,
            method,
            status_code,
            response_time_ms,
            request_size,
            response_size,
            ip_address,
            user_agent,
        ),
    )


def get_usage_stats(key_id: str, days: int = 30) -> Dict[str, Any]:
    """Get usage statistics for an API key."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = db.fetchall(
        """
        SELECT 
            DATE(timestamp) as date,
            COUNT(*) as requests,
            AVG(response_time_ms) as avg_latency,
            SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) as errors
        FROM api_key_usage
        WHERE key_id = %s AND timestamp >= %s
        GROUP BY DATE(timestamp)
        ORDER BY date DESC
        """,
        (key_id, since),
    )

    total_row = db.fetchone(
        """
        SELECT 
            COUNT(*) as total_requests,
            AVG(response_time_ms) as avg_latency,
            SUM(response_size) as total_bytes
        FROM api_key_usage
        WHERE key_id = %s AND timestamp >= %s
        """,
        (key_id, since),
    )

    endpoint_row = db.fetchall(
        """
        SELECT endpoint, COUNT(*) as count
        FROM api_key_usage
        WHERE key_id = %s AND timestamp >= %s
        GROUP BY endpoint
        ORDER BY count DESC
        LIMIT 10
        """,
        (key_id, since),
    )

    return {
        "period_days": days,
        "total_requests": total_row[0] if total_row else 0,
        "avg_latency_ms": round(total_row[1], 2) if total_row and total_row[1] else 0,
        "total_bytes": total_row[2] if total_row else 0,
        "daily_stats": [
            {
                "date": str(row[0]),
                "requests": row[1],
                "avg_latency_ms": round(row[2], 2) if row[2] else 0,
                "errors": row[3],
            }
            for row in rows
        ],
        "top_endpoints": [
            {"endpoint": row[0], "requests": row[1]} for row in endpoint_row
        ],
    }


# ── API Key Dependency ──────────────────────────────────────────────────────────


def get_api_key_or_403(
    raw_key: str, required_scope: str, ip_address: Optional[str] = None
) -> APIKeyAuthResult:
    """
    FastAPI dependency for API key authentication with scope checking.
    Raises HTTPException if authentication fails.
    """
    from fastapi import HTTPException

    result = authenticate_api_key(raw_key, ip_address)

    if not result.valid:
        raise HTTPException(status_code=401, detail=result.error or "Invalid API key")

    if result.is_rate_limited:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Retry after {result.retry_after} seconds.",
            headers={"Retry-After": str(result.retry_after)},
        )

    if not has_scope(result, required_scope):
        raise HTTPException(
            status_code=403, detail=f"Missing required scope: {required_scope}"
        )

    return result
