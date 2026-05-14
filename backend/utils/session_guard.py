"""
session_guard.py - ownership-aware session lookup used by all routes.

Centralised helper that:
  1. Validates the session_id UUID
  2. Looks up the session (memory → disk → SQLite)
  3. Raises HTTP 404 if not found
  4. Raises HTTP 403 if the requesting user doesn't own it (when owner_id provided)

Replaces the per-file _require_session() helper that was duplicated across
13 route files. Use this import instead:
    from utils.session_guard import require_session
"""
from __future__ import annotations
from typing import Optional

from fastapi import HTTPException
from utils.errors import SessionPermissionError, SessionValidationError
from models.dataset_session import get_session, DatasetSession


def require_session(session_id: str, owner_id: Optional[str] = None) -> DatasetSession:
    """
    Fetch a session, optionally enforcing ownership.

    Args:
        session_id: the UUID of the dataset session.
        owner_id:   if provided, raises 403 if another user owns the session.
                    If None, ownership check is skipped (backward compat).

    Raises:
        HTTP 404 - session not found / expired
        HTTP 403 - authenticated user does not own the session
        HTTP 400 - invalid session_id format
    """
    try:
        session = get_session(session_id, owner_id=owner_id)
    except SessionPermissionError:
        raise HTTPException(
            status_code=403,
            detail="Access denied: this dataset belongs to another user.",
        )
    except SessionValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found. The dataset may have expired - please re-upload.",
        )
    return session
