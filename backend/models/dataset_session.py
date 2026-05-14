"""
Session store for uploaded datasets - v6.

Changes from v5:
  - DatasetSession now carries owner_id (user_id from auth token).
  - get_session() accepts optional owner_id; raises 403 if session belongs
    to a different user. Guest sessions (owner_id="guest") are accessible
    only to the guest user when AUTH_ENABLED=False.
  - Session metadata persisted to SQLite (datacove.db) so sessions survive
    server restarts and the 200-session in-memory cap.
  - list_sessions(owner_id) returns all sessions belonging to a user.
  - delete_session() removes both memory + SQLite + disk files.
"""
from __future__ import annotations

import json
import glob
import os
import time
import threading
import uuid
from typing import Dict, Any, List, Optional
from uuid import UUID

import pandas as pd

from config import settings as _settings
from utils.db import db
from utils.errors import SessionPermissionError, SessionValidationError
from models.redis_session_store import (
    save_session  as _redis_save,
    load_session  as _redis_load,
    delete_session as _redis_delete,
    ping           as _redis_ping,
)

DATASET_DIR = str(_settings.DATASET_DIR)
os.makedirs(DATASET_DIR, exist_ok=True)

MAX_HISTORY = 50


def _validate_sid(session_id: str) -> str:
    try:
        UUID(session_id)
    except (ValueError, AttributeError):
        raise SessionValidationError(f"Invalid session_id: {session_id!r}")
    return session_id


# Sessions table is created by utils/db.py _migrate() on startup.


# ── Column-level diff ─────────────────────────────────────────────────────────

def _compute_diff(df_before: pd.DataFrame, df_after: pd.DataFrame) -> Dict[str, Any]:
    diff: Dict[str, Any] = {
        "rows_before": len(df_before),
        "rows_after":  len(df_after),
        "cols_before": list(df_before.columns),
        "cols_after":  list(df_after.columns),
        "changed_cells": [],
    }
    common_cols = [c for c in df_before.columns if c in df_after.columns]
    min_rows = min(len(df_before), len(df_after))
    changed = 0
    for col in common_cols:
        mask = df_before[col].iloc[:min_rows].astype(str) != df_after[col].iloc[:min_rows].astype(str)
        for idx in mask[mask].index[:500]:
            diff["changed_cells"].append({
                "row": int(idx), "col": col,
                "before": str(df_before.at[idx, col]),
                "after":  str(df_after.at[idx, col]),
            })
            changed += 1
            if changed >= 5000:
                return diff
    return diff


class HistoryEntry:
    __slots__ = ("action", "params", "diff", "df_snapshot")

    def __init__(self, action: str, params: dict, diff: Dict[str, Any],
                 df_snapshot: Optional[pd.DataFrame] = None):
        self.action = action
        self.params = params
        self.diff = diff
        self.df_snapshot = df_snapshot


class DatasetSession:
    """Holds a DataFrame and metadata for one upload session."""

    def __init__(self, df: pd.DataFrame, filename: str, owner_id: str = "guest"):
        self.df_original: pd.DataFrame  = df.copy()
        self.df_current: pd.DataFrame   = df.copy()
        self.filename: str              = filename
        self.owner_id: str              = owner_id          # ← NEW
        self.history: List[HistoryEntry] = []
        self.metadata: Dict[str, Any]   = {}
        self.versions: List[str]        = []
        self.created_at: float          = time.time()
        self.last_accessed: float       = time.time()

    def touch(self) -> None:
        self.last_accessed = time.time()

    def push_history(self, df_before: pd.DataFrame, action: str, params: dict) -> None:
        diff = _compute_diff(df_before, self.df_current)
        entry = HistoryEntry(action=action, params=params, diff=diff,
                             df_snapshot=df_before.copy())
        self.history.append(entry)
        if len(self.history) > MAX_HISTORY:
            evicted = self.history.pop(0)
            evicted.df_snapshot = None

    def pop_history(self) -> Optional[HistoryEntry]:
        if not self.history:
            return None
        return self.history.pop()

    def history_as_list(self) -> List[Dict[str, Any]]:
        return [{"action": h.action, "params": h.params} for h in self.history]


# ── Global in-process store ───────────────────────────────────────────────────

_sessions: Dict[str, DatasetSession] = {}
_lock = threading.Lock()


# ── File helpers ──────────────────────────────────────────────────────────────

def _delete_session_files(session_id: str) -> None:
    try:
        base_csv = os.path.join(DATASET_DIR, f"{session_id}.csv")
        if os.path.exists(base_csv):
            os.unlink(base_csv)
        meta_json = os.path.join(DATASET_DIR, f"{session_id}.meta.json")
        if os.path.exists(meta_json):
            os.unlink(meta_json)
        for vf in glob.glob(os.path.join(DATASET_DIR, f"{session_id}_v*.csv")):
            os.unlink(vf)
    except Exception:
        pass


def persist_dataset(session_id: str, df: pd.DataFrame, filename: str = "") -> str:
    _validate_sid(session_id)
    path = os.path.join(DATASET_DIR, f"{session_id}.csv")
    df.to_csv(path, index=False)
    if filename:
        meta_path = os.path.join(DATASET_DIR, f"{session_id}.meta.json")
        with open(meta_path, "w") as mf:
            json.dump({"filename": filename}, mf)
    return path


def load_persisted_dataset(session_id: str):
    _validate_sid(session_id)
    path = os.path.join(DATASET_DIR, f"{session_id}.csv")
    if not os.path.exists(path):
        return None, None
    df = pd.read_csv(path)
    meta_path = os.path.join(DATASET_DIR, f"{session_id}.meta.json")
    filename = "recovered_dataset.csv"
    if os.path.exists(meta_path):
        try:
            with open(meta_path) as mf:
                filename = json.load(mf).get("filename", filename)
        except Exception:
            pass
    return df, filename


def save_version(session_id: str, df: pd.DataFrame, version: int) -> str:
    _validate_sid(session_id)
    path = os.path.join(DATASET_DIR, f"{session_id}_v{version}.csv")
    df.to_csv(path, index=False)
    old_path = os.path.join(DATASET_DIR, f"{session_id}_v{version - MAX_HISTORY}.csv")
    if os.path.exists(old_path):
        os.unlink(old_path)
    return path


# ── SQLite session registry helpers ──────────────────────────────────────────

def _upsert_session_meta(session_id: str, session: DatasetSession,
                         health_score: float | None = None) -> None:
    """Write or update session metadata row in MySQL."""
    df = session.df_current
    db.execute("""
        INSERT INTO sessions (id, owner_id, filename, `rows`, `columns`, health_score, created_at, last_accessed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON DUPLICATE KEY UPDATE
            `rows`        = VALUES(`rows`),
            `columns`     = VALUES(`columns`),
            health_score  = COALESCE(VALUES(health_score), health_score),
            last_accessed = VALUES(last_accessed)
    """, (
        session_id,
        session.owner_id,
        session.filename,
        len(df),
        len(df.columns),
        health_score,
        session.created_at,
        session.last_accessed,
    ))


def list_sessions(owner_id: str) -> List[Dict[str, Any]]:
    """Return all sessions belonging to owner_id, newest first."""
    rows = db.fetchall("""
        SELECT id, filename, `rows`, `columns`, health_score, created_at, last_accessed
        FROM sessions
        WHERE owner_id = ?
        ORDER BY last_accessed DESC
    """, (owner_id,))
    return [dict(r) for r in rows]


# ── Session store (public API) ────────────────────────────────────────────────

def save_session(session_id: str, session: DatasetSession,
                 health_score: float | None = None) -> None:
    _validate_sid(session_id)
    _evict_expired()

    # Try Redis first (multi-worker safe)
    meta = {
        "filename":    session.filename,
        "owner_id":    session.owner_id,
        "created_at":  session.created_at,
        "last_accessed": time.time(),
        "versions":    session.versions,
        "history":     session.history_as_list(),
    }
    _redis_save(session_id, session.df_current, meta)   # no-op if unconfigured

    # Always keep in-memory + disk as fallback
    with _lock:
        _sessions[session_id] = session
    persist_dataset(session_id, session.df_current, session.filename)
    _upsert_session_meta(session_id, session, health_score)


def get_session(session_id: str,
                owner_id: str | None = None) -> Optional[DatasetSession]:
    """
    Fetch a session by ID.
    Resolution order:
      1. In-process dict (fastest - same worker)
      2. Redis (multi-worker safe - shared store)
      3. Disk CSV + DB metadata (restart recovery)
    """
    _validate_sid(session_id)

    with _lock:
        session = _sessions.get(session_id)
        if session is not None:
            session.touch()

    if session is None:
        # Try Redis (shared across workers)
        df_r, meta_r = _redis_load(session_id)
        if df_r is not None and meta_r is not None:
            session = DatasetSession(
                df=df_r,
                filename=meta_r.get("filename", ""),
                owner_id=meta_r.get("owner_id", "guest"),
            )
            session.created_at    = meta_r.get("created_at",   session.created_at)
            session.last_accessed = meta_r.get("last_accessed", session.last_accessed)
            session.versions      = meta_r.get("versions",      [])
            with _lock:
                _sessions[session_id] = session

    if session is None:
        # Try recovering from disk using DB registry
        row = db.fetchone(
            "SELECT owner_id, filename FROM sessions WHERE id = ?", (session_id,)
        )
        if row:
            df, filename = load_persisted_dataset(session_id)
            if df is not None:
                session = DatasetSession(df=df, filename=filename,
                                         owner_id=row["owner_id"])
                with _lock:
                    _sessions[session_id] = session

    if session is None:
        return None

    # Ownership check
    if owner_id is not None and session.owner_id != owner_id:
        raise SessionPermissionError(
            f"Session {session_id} belongs to another user."
        )

    return session


def delete_session(session_id: str, owner_id: str | None = None) -> None:
    """
    Delete a session by ID.

    Works even if the session has been evicted from memory and its CSV is gone
    from disk - as long as the SQLite metadata row still exists (which is what
    makes it visible in the My Datasets listing).

    Ownership is enforced via SQLite when the session is no longer in memory.
    """
    _validate_sid(session_id)

    # Try in-memory first
    with _lock:
        session = _sessions.get(session_id)

    if session is not None:
        # Session is live in memory - check ownership and remove
        if owner_id is not None and session.owner_id != owner_id:
            raise SessionPermissionError(
                f"Session {session_id} belongs to another user."
            )
        with _lock:
            _sessions.pop(session_id, None)
    else:
        # Session not in memory - check ownership via SQLite
        row = db.fetchone(
            "SELECT owner_id FROM sessions WHERE id = ?", (session_id,)
        )
        if row is None:
            # Already gone - nothing to do
            return
        if owner_id is not None and row["owner_id"] != owner_id:
            raise SessionPermissionError(
                f"Session {session_id} belongs to another user."
            )

    # Delete SQLite record and any remaining files
    db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    _delete_session_files(session_id)


# ── Eviction ──────────────────────────────────────────────────────────────────

def _evict_expired() -> None:
    now = time.time()
    ttl = _settings.SESSION_TTL_SECONDS
    cap = _settings.SESSION_MAX_COUNT
    with _lock:
        expired = [sid for sid, s in _sessions.items()
                   if (now - s.last_accessed) > ttl]
        for sid in expired:
            _sessions.pop(sid, None)
        to_evict_cap: list = []
        if len(_sessions) >= cap:
            sorted_sids = sorted(_sessions, key=lambda s: _sessions[s].last_accessed)
            to_evict_cap = sorted_sids[:len(_sessions) - cap + 1]
            for sid in to_evict_cap:
                _sessions.pop(sid, None)
    for sid in expired + to_evict_cap:
        _delete_session_files(sid)
        # Don't delete from SQLite - keep metadata for "my datasets" listing


def cleanup_orphaned_files() -> None:
    try:
        all_files = os.listdir(DATASET_DIR)
    except FileNotFoundError:
        return
    disk_sids: set = set()
    for f in all_files:
        base = f.split(".")[0]
        base = base.split("_v")[0]
        try:
            UUID(base)
            disk_sids.add(base)
        except (ValueError, AttributeError):
            continue
    with _lock:
        active_sids = set(_sessions.keys())
    orphaned = disk_sids - active_sids
    for sid in orphaned:
        _delete_session_files(sid)


def _background_cleanup_loop(interval: int = 600) -> None:
    while True:
        time.sleep(interval)
        try:
            _evict_expired()
            cleanup_orphaned_files()
        except Exception:
            pass


_cleanup_thread = threading.Thread(
    target=_background_cleanup_loop, args=(600,), daemon=True
)
_cleanup_thread.start()
cleanup_orphaned_files()
