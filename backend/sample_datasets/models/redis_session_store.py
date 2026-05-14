"""
models/redis_session_store.py - Optional Redis-backed session store.

When REDIS_URL is set in .env, this module provides a drop-in replacement
for the in-memory Dict in dataset_session.py.

Key design decisions:
  • DataFrame stored as Parquet bytes in Redis (compact, type-preserving)
  • Session metadata (history, filename, versions list) stored as JSON
  • TTL mirrors SESSION_TTL_SECONDS from config (default 1 hour)
  • Lock per session_id to prevent race conditions in concurrent transforms
  • Falls back gracefully when Redis is unavailable

How to activate
───────────────
1. Install: pip install "redis>=5.0.0" "pyarrow>=14.0.0"
2. Set in .env:  REDIS_URL=redis://localhost:6379/0
3. dataset_session.py will automatically use this store when REDIS_URL is set.

How it handles multi-worker deployments
────────────────────────────────────────
All uvicorn workers share the same Redis instance.
Session reads/writes go through Redis, so sessions created in worker A
are immediately visible to worker B - no session loss on load-balanced requests.
"""
from __future__ import annotations

import io
import json
import os
import time
from typing import Optional

import pandas as pd

from utils.logger import logger

REDIS_URL = os.getenv("REDIS_URL", "")
_TTL      = int(os.getenv("SESSION_TTL_SECONDS", "3600"))


def _is_available() -> bool:
    return bool(REDIS_URL)


def _get_client():
    """Lazy singleton Redis client - imported only when needed."""
    import redis as _redis
    if not hasattr(_get_client, "_client"):
        _get_client._client = _redis.from_url(
            REDIS_URL,
            decode_responses=False,   # binary for Parquet bytes
            socket_connect_timeout=3,
            socket_timeout=5,
            retry_on_timeout=True,
        )
    return _get_client._client


# ── Key helpers ───────────────────────────────────────────────────────────────

def _df_key(session_id: str)   -> str: return f"dc:df:{session_id}"
def _meta_key(session_id: str) -> str: return f"dc:meta:{session_id}"
def _lock_key(session_id: str) -> str: return f"dc:lock:{session_id}"


# ── Public interface ──────────────────────────────────────────────────────────

def save_session(session_id: str, df: pd.DataFrame, meta: dict) -> bool:
    """
    Persist a session to Redis.
    meta should be JSON-serialisable (no DataFrames inside).
    Returns True on success, False if Redis is unavailable.
    """
    if not _is_available():
        return False
    try:
        client = _get_client()
        pipe   = client.pipeline()

        # Serialize DataFrame as Parquet
        buf = io.BytesIO()
        df.to_parquet(buf, index=False, engine="pyarrow")
        df_bytes = buf.getvalue()

        meta_bytes = json.dumps(meta, default=str).encode("utf-8")

        pipe.setex(_df_key(session_id),   _TTL, df_bytes)
        pipe.setex(_meta_key(session_id), _TTL, meta_bytes)
        pipe.execute()
        return True
    except Exception as exc:
        logger.warning(f"Redis save_session failed: {exc}")
        return False


def load_session(session_id: str):
    """
    Load a session from Redis.
    Returns (df, meta) or (None, None) if not found.
    """
    if not _is_available():
        return None, None
    try:
        client    = _get_client()
        df_bytes  = client.get(_df_key(session_id))
        meta_bytes = client.get(_meta_key(session_id))

        if df_bytes is None or meta_bytes is None:
            return None, None

        df   = pd.read_parquet(io.BytesIO(df_bytes))
        meta = json.loads(meta_bytes.decode("utf-8"))

        # Refresh TTL on access
        client.expire(_df_key(session_id),   _TTL)
        client.expire(_meta_key(session_id), _TTL)
        return df, meta
    except Exception as exc:
        logger.warning(f"Redis load_session failed: {exc}")
        return None, None


def delete_session(session_id: str) -> bool:
    """Remove a session from Redis."""
    if not _is_available():
        return False
    try:
        client = _get_client()
        client.delete(_df_key(session_id), _meta_key(session_id))
        return True
    except Exception as exc:
        logger.warning(f"Redis delete_session failed: {exc}")
        return False


def list_active_sessions() -> list[str]:
    """Return all session IDs currently stored in Redis (for admin/debug)."""
    if not _is_available():
        return []
    try:
        client = _get_client()
        keys   = client.keys("dc:df:*")
        return [k.decode("utf-8").replace("dc:df:", "") for k in keys]
    except Exception as exc:
        logger.warning(f"Redis list_active_sessions failed: {exc}")
        return []


def ping() -> bool:
    """Check Redis connectivity."""
    if not _is_available():
        return False
    try:
        return _get_client().ping()
    except Exception:
        return False


class RedisSessionLock:
    """
    Simple distributed lock per session_id.
    Prevents concurrent transforms on the same session across workers.
    Uses SET NX EX (atomic) - no SETNX+EXPIRE race condition.
    """
    def __init__(self, session_id: str, ttl: int = 30):
        self._key = _lock_key(session_id)
        self._ttl = ttl
        self._acquired = False

    def __enter__(self):
        if not _is_available():
            return self
        try:
            client = _get_client()
            # SET key 1 NX EX ttl - returns True if lock acquired
            self._acquired = bool(client.set(self._key, 1, nx=True, ex=self._ttl))
            if not self._acquired:
                raise RuntimeError("Session is busy - another operation is in progress. Please try again.")
        except RuntimeError:
            raise
        except Exception as exc:
            logger.warning(f"Redis lock acquire failed: {exc}")
        return self

    def __exit__(self, *_):
        if not self._acquired:
            return
        try:
            _get_client().delete(self._key)
        except Exception:
            pass
