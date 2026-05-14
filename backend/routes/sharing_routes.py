"""
sharing_routes.py - dataset sharing and collaboration.

POST /api/share                    - create a share link for a session
GET  /api/share/{token}            - resolve a share token → session metadata
POST /api/share/{token}/fork       - fork a shared dataset into your own session
GET  /api/sessions/{id}/shares     - list active share links for a session
DELETE /api/share/{token}          - revoke a share link (owner only)
"""
import uuid
import time
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from utils.auth import get_current_user, AuthUser
from utils.session_guard import require_session
from utils.db import db
from utils.preview import safe_preview
from models.dataset_session import DatasetSession, save_session, get_session
from utils.logger import logger

router = APIRouter(dependencies=[Depends(get_current_user)])

# ── DB migration ───────────────────────────────────────────────────────────────
# Create share_links table (MySQL-compatible)
try:
    db.execute("""
        CREATE TABLE IF NOT EXISTS share_links (
            token        VARCHAR(64)  PRIMARY KEY,
            session_id   VARCHAR(36)  NOT NULL,
            owner_id     VARCHAR(36)  NOT NULL,
            label        VARCHAR(255) NOT NULL DEFAULT '',
            permission   VARCHAR(8)   NOT NULL DEFAULT 'view',
            expires_at   DOUBLE,
            created_at   DOUBLE       NOT NULL,
            access_count INT          NOT NULL DEFAULT 0
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
except Exception:
    pass

_DEFAULT_TTL_DAYS = 30


class CreateShareRequest(BaseModel):
    session_id: str
    label:      str = ""
    permission: str = "fork"          # 'view' or 'fork'
    expires_days: Optional[int] = 30  # None = never expires


class ForkRequest(BaseModel):
    token: str


@router.post("/share")
def create_share(req: CreateShareRequest, user: AuthUser = Depends(get_current_user)):
    """Create a shareable link for a dataset. Only the owner can share."""
    require_session(req.session_id, owner_id=user.user_id)

    if req.permission not in ("view", "fork"):
        raise HTTPException(status_code=400, detail="permission must be 'view' or 'fork'.")

    token      = uuid.uuid4().hex          # 32-char hex token
    now        = time.time()
    expires_at = now + (req.expires_days * 86400) if req.expires_days else None

    db.execute("""
        INSERT INTO share_links (token, session_id, owner_id, label, permission, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (token, req.session_id, user.user_id, req.label, req.permission, expires_at, now))

    logger.info(f"Share created: session={req.session_id} token={token[:8]}… by user={user.user_id}")

    return JSONResponse({
        "token":       token,
        "session_id":  req.session_id,
        "permission":  req.permission,
        "expires_at":  expires_at,
        "share_url":   f"/shared/{token}",    # frontend route
    })


@router.get("/share/{token}")
def resolve_share(token: str, user: AuthUser = Depends(get_current_user)):
    """Resolve a share token to session metadata (no auth required to view)."""
    row = db.fetchone("SELECT * FROM share_links WHERE token = ?", (token,))
    if not row:
        raise HTTPException(status_code=404, detail="Share link not found or revoked.")

    if row["expires_at"] and time.time() > row["expires_at"]:
        raise HTTPException(status_code=410, detail="This share link has expired.")

    # Increment access counter
    db.execute("UPDATE share_links SET access_count = access_count + 1 WHERE token = ?", (token,))

    session = get_session(row["session_id"])
    if session is None:
        raise HTTPException(status_code=404, detail="The shared dataset is no longer available.")

    df = session.df_current
    return JSONResponse({
        "token":        token,
        "label":        row["label"],
        "permission":   row["permission"],
        "filename":     session.filename,
        "rows":         len(df),
        "columns":      list(df.columns),
        "preview":      safe_preview(df, n=50),
        "expires_at":   row["expires_at"],
        "access_count": row["access_count"] + 1,
        "can_fork":     row["permission"] == "fork",
    })


@router.post("/share/{token}/fork")
def fork_shared_dataset(token: str, user: AuthUser = Depends(get_current_user)):
    """
    Fork a shared dataset into the current user's own session.
    Creates a full independent copy - edits don't affect the original.
    """
    row = db.fetchone("SELECT * FROM share_links WHERE token = ?", (token,))
    if not row:
        raise HTTPException(status_code=404, detail="Share link not found.")
    if row["permission"] != "fork":
        raise HTTPException(status_code=403, detail="This link is view-only and cannot be forked.")
    if row["expires_at"] and time.time() > row["expires_at"]:
        raise HTTPException(status_code=410, detail="This share link has expired.")

    source_session = get_session(row["session_id"])
    if source_session is None:
        raise HTTPException(status_code=404, detail="Source dataset no longer available.")

    # Create an independent copy owned by the forking user
    forked_id = str(uuid.uuid4())
    forked    = DatasetSession(
        df=source_session.df_current.copy(),
        filename=f"fork_of_{source_session.filename}",
        owner_id=user.user_id,
    )
    save_session(forked_id, forked)
    logger.info(f"Fork: token={token[:8]}… → new session={forked_id} by user={user.user_id}")

    return JSONResponse({
        "session_id": forked_id,
        "filename":   forked.filename,
        "rows":       len(forked.df_current),
        "columns":    list(forked.df_current.columns),
        "preview":    safe_preview(forked.df_current),
    })


@router.get("/sessions/{session_id}/shares")
def list_shares(session_id: str, user: AuthUser = Depends(get_current_user)):
    """List all active share links for a session (owner only)."""
    require_session(session_id, owner_id=user.user_id)
    rows = db.fetchall("""
        SELECT token, label, permission, expires_at, created_at, access_count
        FROM share_links WHERE session_id = ? AND owner_id = ?
        ORDER BY created_at DESC
    """, (session_id, user.user_id))
    now = time.time()
    links = []
    for r in rows:
        expired = bool(r["expires_at"] and now > r["expires_at"])
        links.append({**dict(r), "expired": expired, "share_url": f"/shared/{r['token']}"})
    return JSONResponse({"shares": links})


@router.delete("/share/{token}")
def revoke_share(token: str, user: AuthUser = Depends(get_current_user)):
    """Revoke a share link. Only the owner can revoke."""
    row = db.fetchone("SELECT owner_id FROM share_links WHERE token = ?", (token,))
    if not row:
        raise HTTPException(status_code=404, detail="Share link not found.")
    if row["owner_id"] != user.user_id:
        raise HTTPException(status_code=403, detail="Only the owner can revoke this link.")
    db.execute("DELETE FROM share_links WHERE token = ?", (token,))
    return JSONResponse({"revoked": True, "token": token})
