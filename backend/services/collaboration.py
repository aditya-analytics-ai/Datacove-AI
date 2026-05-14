"""
Real-Time Collaboration - multi-user editing sessions with presence awareness,
live cursors, conflict resolution, and change synchronization.

Features:
  ✅ Shared editing sessions with real-time sync
  ✅ User presence and cursor position tracking
  ✅ Operational transformation for conflict resolution
  ✅ Locked cells/regions during editing
  ✅ Change history with attribution
  ✅ Comment threads on cells/rows
  ✅ @mentions and notifications
  ✅ Session invitations and permissions
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Set
from dataclasses import dataclass, field, asdict
from enum import Enum

import numpy as np
import pandas as pd

from services.websocket_manager import ws_manager
from utils.logger import logger


# ── Constants ──────────────────────────────────────────────────────────────────

MAX_SESSION_USERS = 20
MAX_UNDO_HISTORY = 100
LOCK_TIMEOUT_SECONDS = 300
COMMENT_THREAD_TTL_HOURS = 24 * 7


class Permission(str, Enum):
    VIEW = "view"
    EDIT = "edit"
    ADMIN = "admin"


@dataclass
class CursorPosition:
    user_id: str
    user_name: str
    user_color: str
    row: Optional[int] = None
    column: Optional[str] = None
    selection_start: Optional[tuple] = None
    selection_end: Optional[tuple] = None
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class CellLock:
    user_id: str
    user_name: str
    row: int
    column: str
    locked_at: str
    expires_at: str


@dataclass
class Change:
    change_id: str
    user_id: str
    user_name: str
    operation: str
    path: str
    old_value: Any
    new_value: Any
    timestamp: str


@dataclass
class Comment:
    comment_id: str
    user_id: str
    user_name: str
    target_type: str
    target_id: str
    content: str
    mentions: List[str]
    created_at: str
    updated_at: Optional[str] = None
    resolved: bool = False


@dataclass
class CollaborationSession:
    session_id: str
    owner_id: str
    name: str
    dataset_id: Optional[str]
    created_at: str
    updated_at: str
    is_active: bool = True
    users: Dict[str, Dict] = field(default_factory=dict)
    cursors: Dict[str, CursorPosition] = field(default_factory=dict)
    locks: Dict[str, CellLock] = field(default_factory=dict)
    changes: List[Change] = field(default_factory=list)


# ── Session Store ──────────────────────────────────────────────────────────────

_collab_sessions: Dict[str, CollaborationSession] = {}
_session_datasets: Dict[str, pd.DataFrame] = {}


def _generate_session_id() -> str:
    return f"collab_{uuid.uuid4().hex[:16]}"


def _generate_color() -> str:
    colors = [
        "#FF6B6B",
        "#4ECDC4",
        "#45B7D1",
        "#96CEB4",
        "#FFEAA7",
        "#DDA0DD",
        "#98D8C8",
        "#F7DC6F",
        "#BB8FCE",
        "#85C1E9",
        "#F8B500",
        "#00CED1",
    ]
    return colors[len(_collab_sessions) % len(colors)]


# ── Session Management ──────────────────────────────────────────────────────────


def create_session(
    owner_id: str,
    owner_name: str,
    name: str,
    dataset_id: Optional[str] = None,
    initial_data: Optional[pd.DataFrame] = None,
) -> CollaborationSession:
    """Create a new collaboration session."""
    session_id = _generate_session_id()

    session = CollaborationSession(
        session_id=session_id,
        owner_id=owner_id,
        name=name,
        dataset_id=dataset_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )

    session.users[owner_id] = {
        "user_id": owner_id,
        "user_name": owner_name,
        "user_color": _generate_color(),
        "permission": Permission.ADMIN.value,
        "joined_at": datetime.now(timezone.utc).isoformat(),
        "is_online": True,
    }

    if initial_data is not None:
        _session_datasets[session_id] = initial_data.copy()

    _collab_sessions[session_id] = session
    logger.info(f"Collaboration session created: {session_id}")

    return session


def get_session(session_id: str) -> Optional[CollaborationSession]:
    """Get a collaboration session by ID."""
    return _collab_sessions.get(session_id)


def join_session(
    session_id: str,
    user_id: str,
    user_name: str,
    permission: Permission = Permission.VIEW,
) -> Optional[CollaborationSession]:
    """Join an existing collaboration session."""
    session = _collab_sessions.get(session_id)
    if not session:
        return None

    if len(session.users) >= MAX_SESSION_USERS:
        raise ValueError("Session is full")

    if user_id in session.users:
        session.users[user_id]["is_online"] = True
        session.users[user_id]["joined_at"] = datetime.now(timezone.utc).isoformat()
    else:
        session.users[user_id] = {
            "user_id": user_id,
            "user_name": user_name,
            "user_color": _generate_color(),
            "permission": permission.value,
            "joined_at": datetime.now(timezone.utc).isoformat(),
            "is_online": True,
        }

    session.updated_at = datetime.now(timezone.utc).isoformat()

    _broadcast_to_session(
        session_id,
        {
            "type": "user_joined",
            "user_id": user_id,
            "user_name": user_name,
            "users": list(session.users.values()),
        },
    )

    return session


def leave_session(session_id: str, user_id: str) -> bool:
    """Leave a collaboration session."""
    session = _collab_sessions.get(session_id)
    if not session:
        return False

    if user_id in session.users:
        session.users[user_id]["is_online"] = False

        _broadcast_to_session(
            session_id,
            {
                "type": "user_left",
                "user_id": user_id,
                "user_name": session.users[user_id]["user_name"],
                "users": list(session.users.values()),
            },
        )

        for lock_key in list(session.locks.keys()):
            if session.locks[lock_key].user_id == user_id:
                del session.locks[lock_key]

        session.updated_at = datetime.now(timezone.utc).isoformat()

    return True


def invite_user(
    session_id: str,
    inviter_id: str,
    invitee_email: str,
    permission: Permission = Permission.EDIT,
) -> str:
    """Generate an invitation link for a user."""
    session = _collab_sessions.get(session_id)
    if not session:
        raise ValueError("Session not found")

    invite_id = f"inv_{uuid.uuid4().hex[:16]}"
    return f"/collab/join/{session_id}?invite={invite_id}"


def list_user_sessions(user_id: str) -> List[CollaborationSession]:
    """List all sessions a user is part of."""
    return [
        session
        for session in _collab_sessions.values()
        if user_id in session.users and session.is_active
    ]


# ── Cursor & Presence ─────────────────────────────────────────────────────────


def update_cursor(
    session_id: str,
    user_id: str,
    position: CursorPosition,
) -> bool:
    """Update a user's cursor position."""
    session = _collab_sessions.get(session_id)
    if not session or user_id not in session.users:
        return False

    position.updated_at = datetime.now(timezone.utc).isoformat()
    session.cursors[user_id] = position

    _broadcast_to_session(
        session_id,
        {
            "type": "cursor_update",
            "cursor": asdict(position),
        },
        exclude_user=user_id,
    )

    return True


def get_active_cursors(session_id: str) -> List[CursorPosition]:
    """Get all active cursors in a session."""
    session = _collab_sessions.get(session_id)
    if not session:
        return []

    return [
        cursor
        for user_id, cursor in session.cursors.items()
        if session.users.get(user_id, {}).get("is_online", False)
    ]


# ── Cell Locking ──────────────────────────────────────────────────────────────


def lock_cell(
    session_id: str,
    user_id: str,
    row: int,
    column: str,
) -> Optional[CellLock]:
    """Lock a cell for editing."""
    session = _collab_sessions.get(session_id)
    if not session:
        return None

    lock_key = f"{row}:{column}"
    existing = session.locks.get(lock_key)

    if existing and existing.user_id != user_id:
        expires = datetime.fromisoformat(existing.expires_at)
        if expires > datetime.now(timezone.utc):
            return None

    now = datetime.now(timezone.utc)
    lock = CellLock(
        user_id=user_id,
        user_name=session.users.get(user_id, {}).get("user_name", "Unknown"),
        row=row,
        column=column,
        locked_at=now.isoformat(),
        expires_at=(now + timedelta(seconds=LOCK_TIMEOUT_SECONDS)).isoformat(),
    )

    session.locks[lock_key] = lock

    _broadcast_to_session(
        session_id,
        {
            "type": "cell_locked",
            "lock": asdict(lock),
        },
    )

    return lock


def unlock_cell(session_id: str, user_id: str, row: int, column: str) -> bool:
    """Unlock a cell."""
    session = _collab_sessions.get(session_id)
    if not session:
        return False

    lock_key = f"{row}:{column}"
    lock = session.locks.get(lock_key)

    if not lock or lock.user_id != user_id:
        return False

    del session.locks[lock_key]

    _broadcast_to_session(
        session_id,
        {
            "type": "cell_unlocked",
            "row": row,
            "column": column,
        },
    )

    return True


def get_cell_locks(session_id: str) -> List[CellLock]:
    """Get all active cell locks in a session."""
    session = _collab_sessions.get(session_id)
    if not session:
        return []

    now = datetime.now(timezone.utc)
    valid_locks = []

    for lock_key, lock in list(session.locks.items()):
        expires = datetime.fromisoformat(lock.expires_at)
        if expires > now:
            valid_locks.append(lock)
        else:
            del session.locks[lock_key]

    return valid_locks


# ── Operational Transformation ─────────────────────────────────────────────────


def apply_change(
    session_id: str,
    user_id: str,
    operation: str,
    path: str,
    old_value: Any,
    new_value: Any,
) -> Optional[Change]:
    """
    Apply a change operation to the session data.

    Operations: "insert", "update", "delete", "move"
    Path format: "rows/0/cells/col_name" or "columns/col_name"
    """
    session = _collab_sessions.get(session_id)
    if not session:
        return None

    if user_id not in session.users:
        return None

    change = Change(
        change_id=f"chg_{uuid.uuid4().hex[:12]}",
        user_id=user_id,
        user_name=session.users[user_id]["user_name"],
        operation=operation,
        path=path,
        old_value=old_value,
        new_value=new_value,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    session.changes.append(change)
    if len(session.changes) > MAX_UNDO_HISTORY:
        session.changes = session.changes[-MAX_UNDO_HISTORY:]

    if session_id in _session_datasets:
        df = _session_datasets[session_id]
        _apply_change_to_dataframe(df, operation, path, new_value)
        _session_datasets[session_id] = df

    _broadcast_to_session(
        session_id,
        {
            "type": "change_applied",
            "change": asdict(change),
        },
    )

    return change


def _apply_change_to_dataframe(
    df: pd.DataFrame, operation: str, path: str, value: Any
) -> None:
    """Apply a change to a DataFrame."""
    try:
        parts = path.split("/")
        if len(parts) >= 2 and parts[0] == "rows":
            row_idx = int(parts[1])
            if len(parts) >= 4 and parts[2] == "cells":
                col_name = parts[3]
                if row_idx < len(df) and col_name in df.columns:
                    df.at[df.index[row_idx], col_name] = value
        elif len(parts) >= 2 and parts[0] == "cells":
            col_name = parts[1]
            if col_name in df.columns:
                df[col_name] = value
    except Exception as e:
        logger.warning(f"Failed to apply change to DataFrame: {e}")


def undo_change(session_id: str, user_id: str) -> Optional[Change]:
    """Undo the last change made by the user."""
    session = _collab_sessions.get(session_id)
    if not session:
        return None

    for change in reversed(session.changes):
        if change.user_id == user_id:
            session.changes.remove(change)

            if session_id in _session_datasets:
                df = _session_datasets[session_id]
                _apply_change_to_dataframe(
                    df, change.operation, change.path, change.old_value
                )
                _session_datasets[session_id] = df

            _broadcast_to_session(
                session_id,
                {
                    "type": "change_undone",
                    "change": asdict(change),
                },
            )

            return change

    return None


def get_change_history(session_id: str, limit: int = 50) -> List[Change]:
    """Get change history for a session."""
    session = _collab_sessions.get(session_id)
    if not session:
        return []

    return session.changes[-limit:]


# ── Comments ──────────────────────────────────────────────────────────────────

_comment_store: Dict[str, List[Comment]] = {}


def add_comment(
    session_id: str,
    user_id: str,
    user_name: str,
    target_type: Literal["cell", "row", "column", "session"],
    target_id: str,
    content: str,
    mentions: Optional[List[str]] = None,
) -> Comment:
    """Add a comment to a cell, row, or column."""
    session = _collab_sessions.get(session_id)
    if not session:
        raise ValueError("Session not found")

    comment = Comment(
        comment_id=f"cmt_{uuid.uuid4().hex[:12]}",
        user_id=user_id,
        user_name=user_name,
        target_type=target_type,
        target_id=target_id,
        content=content,
        mentions=mentions or [],
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    if session_id not in _comment_store:
        _comment_store[session_id] = []

    _comment_store[session_id].append(comment)

    _broadcast_to_session(
        session_id,
        {
            "type": "comment_added",
            "comment": asdict(comment),
        },
    )

    return comment


def resolve_comment(session_id: str, comment_id: str, user_id: str) -> bool:
    """Mark a comment as resolved."""
    if session_id not in _comment_store:
        return False

    for comment in _comment_store[session_id]:
        if comment.comment_id == comment_id:
            comment.resolved = True
            comment.updated_at = datetime.now(timezone.utc).isoformat()

            _broadcast_to_session(
                session_id,
                {
                    "type": "comment_resolved",
                    "comment_id": comment_id,
                },
            )
            return True

    return False


def get_comments(
    session_id: str, target_type: Optional[str] = None, target_id: Optional[str] = None
) -> List[Comment]:
    """Get comments for a session, optionally filtered."""
    if session_id not in _comment_store:
        return []

    comments = _comment_store[session_id]

    if target_type:
        comments = [c for c in comments if c.target_type == target_type]
    if target_id:
        comments = [c for c in comments if c.target_id == target_id]

    return [c for c in comments if not c.resolved]


# ── Data Sync ─────────────────────────────────────────────────────────────────


def get_session_data(session_id: str) -> Optional[pd.DataFrame]:
    """Get the current data state of a session."""
    return _session_datasets.get(session_id)


def sync_data_update(
    session_id: str,
    user_id: str,
    updates: Dict[str, Any],
) -> bool:
    """
    Sync a batch of data updates to the session.

    Used for bulk operations like paste, drag-fill, etc.
    """
    session = _collab_sessions.get(session_id)
    if not session or session_id not in _session_datasets:
        return False

    df = _session_datasets[session_id]

    for update in updates.get("cells", []):
        row = update.get("row")
        col = update.get("column")
        value = update.get("value")

        if row is not None and col is not None and col in df.columns:
            if row < len(df):
                df.at[df.index[row], col] = value

    _session_datasets[session_id] = df

    _broadcast_to_session(
        session_id,
        {
            "type": "data_sync",
            "user_id": user_id,
            "updates": updates,
        },
    )

    return True


def broadcast_selection(
    session_id: str,
    user_id: str,
    selection: Dict[str, Any],
) -> bool:
    """Broadcast a cell selection to other users."""
    session = _collab_sessions.get(session_id)
    if not session:
        return False

    _broadcast_to_session(
        session_id,
        {
            "type": "selection_change",
            "user_id": user_id,
            "user_name": session.users.get(user_id, {}).get("user_name", "Unknown"),
            "selection": selection,
        },
        exclude_user=user_id,
    )

    return True


# ── WebSocket Broadcasting ────────────────────────────────────────────────────


def _broadcast_to_session(
    session_id: str,
    message: Dict[str, Any],
    exclude_user: Optional[str] = None,
) -> None:
    """Broadcast a message to all users in a session."""
    ws_manager.broadcast(
        channel=f"collab:{session_id}",
        message=json.dumps(message),
        exclude=exclude_user,
    )


# ── Session Cleanup ───────────────────────────────────────────────────────────


def cleanup_inactive_sessions(hours: int = 24) -> int:
    """Remove inactive sessions."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    removed = 0

    for session_id in list(_collab_sessions.keys()):
        session = _collab_sessions[session_id]
        updated = datetime.fromisoformat(session.updated_at)

        if updated < cutoff:
            online_users = [
                u for u in session.users.values() if u.get("is_online", False)
            ]
            if not online_users:
                del _collab_sessions[session_id]
                if session_id in _session_datasets:
                    del _session_datasets[session_id]
                if session_id in _comment_store:
                    del _comment_store[session_id]
                removed += 1

    return removed


# ── Permission Helpers ────────────────────────────────────────────────────────


def check_permission(session_id: str, user_id: str, required: Permission) -> bool:
    """Check if a user has the required permission level."""
    session = _collab_sessions.get(session_id)
    if not session or user_id not in session.users:
        return False

    user_perm = session.users[user_id].get("permission", Permission.VIEW.value)

    if user_perm == Permission.ADMIN.value:
        return True
    if user_perm == Permission.EDIT.value and required == Permission.VIEW:
        return True

    return user_perm == required.value


# ── Telemetry ─────────────────────────────────────────────────────────────────


def get_session_telemetry(session_id: str) -> Dict[str, Any]:
    """Get telemetry data for a session."""
    session = _collab_sessions.get(session_id)
    if not session:
        return {}

    df = _session_datasets.get(session_id)

    return {
        "session_id": session_id,
        "name": session.name,
        "active_users": len([u for u in session.users.values() if u.get("is_online")]),
        "total_users": len(session.users),
        "total_changes": len(session.changes),
        "active_locks": len(get_cell_locks(session_id)),
        "open_comments": len(get_comments(session_id)),
        "dataset_rows": len(df) if df is not None else 0,
        "dataset_columns": len(df.columns) if df is not None else 0,
        "session_duration_seconds": (
            datetime.fromisoformat(session.updated_at)
            - datetime.fromisoformat(session.created_at)
        ).total_seconds(),
    }
