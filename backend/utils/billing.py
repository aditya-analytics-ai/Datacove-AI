"""
billing.py - usage tracking and tier enforcement.

Tiers:
  free    - 3 datasets, 10k rows/dataset, no AI features, no pipelines
  pro     - unlimited datasets, 1M rows, all features, 100 AI calls/day
  team    - everything in pro + sharing + schedules + connectors

Usage is tracked per user in SQLite. Tier is stored on the user record.
Stripe integration: set STRIPE_SECRET_KEY in .env and use the /billing/* routes.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Optional
from fastapi import HTTPException

from utils.db import db
from utils.logger import logger

# ── DB migrations ──────────────────────────────────────────────────────────────
# Create billing tables on import (MySQL-compatible, one statement at a time)
try:
    db.execute("""
        CREATE TABLE IF NOT EXISTS user_tiers (
            user_id            VARCHAR(36)  PRIMARY KEY,
            tier               VARCHAR(16)  NOT NULL DEFAULT 'free',
            stripe_customer_id VARCHAR(128),
            stripe_sub_id      VARCHAR(128),
            updated_at         DOUBLE       NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS usage_events (
            id          VARCHAR(36)  PRIMARY KEY,
            user_id     VARCHAR(36)  NOT NULL,
            event_type  VARCHAR(32)  NOT NULL,
            `value`     INT          NOT NULL DEFAULT 1,
            recorded_at DOUBLE       NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    try:
        db.execute("""
            CREATE INDEX idx_usage_user_type_date
            ON usage_events(user_id, event_type, recorded_at)
        """)
    except Exception:
        pass  # Index already exists
except Exception as e:
    logger.warning(f"Billing table creation: {e}")


@dataclass
class TierLimits:
    name: str
    max_datasets: Optional[int]  # None = unlimited
    max_rows: Optional[int]
    ai_calls_per_day: Optional[int]
    pipelines: bool
    sharing: bool
    schedules: bool
    connectors: bool


TIERS: dict[str, TierLimits] = {
    "free": TierLimits(
        name="free",
        max_datasets=3,
        max_rows=10_000,
        ai_calls_per_day=0,
        pipelines=False,
        sharing=False,
        schedules=False,
        connectors=False,
    ),
    "pro": TierLimits(
        name="pro",
        max_datasets=None,
        max_rows=1_000_000,
        ai_calls_per_day=100,
        pipelines=True,
        sharing=True,
        schedules=True,
        connectors=True,
    ),
    "team": TierLimits(
        name="team",
        max_datasets=None,
        max_rows=None,
        ai_calls_per_day=None,
        pipelines=True,
        sharing=True,
        schedules=True,
        connectors=True,
    ),
}


# ── Tier lookup ────────────────────────────────────────────────────────────────


def get_tier(user_id: str) -> TierLimits:
    row = db.fetchone("SELECT tier FROM user_tiers WHERE user_id = ?", (user_id,))
    tier_name = row["tier"] if row else "free"
    return TIERS.get(tier_name, TIERS["free"])


def set_tier(
    user_id: str, tier: str, stripe_customer_id: str = "", stripe_sub_id: str = ""
) -> None:
    if tier not in TIERS:
        raise ValueError(f"Unknown tier: {tier}")
    db.execute(
        """
        INSERT INTO user_tiers (user_id, tier, stripe_customer_id, stripe_sub_id, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON DUPLICATE KEY UPDATE
            tier               = VALUES(tier),
            stripe_customer_id = COALESCE(VALUES(stripe_customer_id), stripe_customer_id),
            stripe_sub_id      = COALESCE(VALUES(stripe_sub_id), stripe_sub_id),
            updated_at         = VALUES(updated_at)
    """,
        (user_id, tier, stripe_customer_id, stripe_sub_id, time.time()),
    )
    logger.info(f"Billing: user={user_id} tier → {tier}")


# ── Usage tracking ─────────────────────────────────────────────────────────────


def record_usage(user_id: str, event_type: str, value: int = 1) -> None:
    db.execute(
        """
        INSERT INTO usage_events (id, user_id, event_type, `value`, recorded_at)
        VALUES (?, ?, ?, ?, ?)
    """,
        (str(uuid.uuid4()), user_id, event_type, value, time.time()),
    )


def get_usage_today(user_id: str, event_type: str) -> int:
    day_start = time.time() - (time.time() % 86400)
    row = db.fetchone(
        """
        SELECT COALESCE(SUM(`value`), 0) as total
        FROM usage_events
        WHERE user_id = ? AND event_type = ? AND recorded_at >= ?
    """,
        (user_id, event_type, day_start),
    )
    return row["total"] if row else 0


def get_dataset_count(user_id: str) -> int:
    row = db.fetchone(
        "SELECT COUNT(*) as cnt FROM sessions WHERE owner_id = ?", (user_id,)
    )
    return row["cnt"] if row else 0


# ── Enforcement helpers (raise HTTP 402 if limit exceeded) ────────────────────


def _is_admin(user_id: str) -> bool:
    """Check if user has admin role."""
    row = db.fetchone("SELECT role FROM users WHERE id = ?", (user_id,))
    return row and row.get("role") == "admin"


def enforce_upload(user_id: str, row_count: int) -> None:
    if _is_admin(user_id):
        return
    limits = get_tier(user_id)
    if limits.max_datasets is not None:
        current = get_dataset_count(user_id)
        if current >= limits.max_datasets:
            raise HTTPException(
                status_code=402,
                detail=f"Free tier limit: {limits.max_datasets} datasets. "
                "Upgrade to Pro for unlimited datasets.",
            )
    if limits.max_rows is not None and row_count > limits.max_rows:
        raise HTTPException(
            status_code=402,
            detail=f"Free tier limit: {limits.max_rows:,} rows per dataset. "
            f"Your file has {row_count:,} rows. Upgrade to Pro.",
        )


def enforce_ai(user_id: str) -> None:
    if _is_admin(user_id):
        return
    limits = get_tier(user_id)
    if limits.ai_calls_per_day == 0:
        raise HTTPException(
            status_code=402,
            detail="AI features require a Pro or Team plan. Upgrade to unlock.",
        )
    if limits.ai_calls_per_day is not None:
        used = get_usage_today(user_id, "ai_call")
        if used >= limits.ai_calls_per_day:
            raise HTTPException(
                status_code=429,
                detail=f"Daily AI limit reached ({limits.ai_calls_per_day} calls). "
                "Resets at midnight UTC.",
            )


def enforce_feature(user_id: str, feature: str) -> None:
    """feature: 'pipelines' | 'sharing' | 'schedules' | 'connectors'"""
    if _is_admin(user_id):
        return
    limits = get_tier(user_id)
    if not getattr(limits, feature, False):
        tier_name = limits.name
        raise HTTPException(
            status_code=402,
            detail=f"'{feature}' is not available on the {tier_name} plan. "
            "Upgrade to unlock this feature.",
        )
