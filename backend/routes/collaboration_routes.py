"""
Collaboration Routes - real-time multi-user editing sessions.

Base path: /api/collab
"""

from datetime import timedelta
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from middleware.auth import get_current_user_id, get_user_email
from services.collaboration import (
    Permission,
    CellLock,
    Change,
    Comment,
    CursorPosition,
    create_session,
    get_session,
    join_session,
    leave_session,
    invite_user,
    list_user_sessions,
    update_cursor,
    get_active_cursors,
    lock_cell,
    unlock_cell,
    get_cell_locks,
    apply_change,
    undo_change,
    get_change_history,
    add_comment,
    resolve_comment,
    get_comments,
    get_session_data,
    sync_data_update,
    broadcast_selection,
    check_permission,
    get_session_telemetry,
)
from services.websocket_manager import ws_manager
from utils.logger import logger


router = APIRouter(prefix="/collab", tags=["Collaboration"])


# ── Models ────────────────────────────────────────────────────────────────────


class SessionCreate(BaseModel):
    name: str
    dataset_id: Optional[str] = None
    invite_emails: Optional[List[str]] = None
    permission: Literal["view", "edit", "admin"] = "edit"


class SessionResponse(BaseModel):
    session_id: str
    name: str
    owner_id: str
    dataset_id: Optional[str]
    created_at: str
    users: List[Dict]
    is_active: bool


class ChangeApplyRequest(BaseModel):
    operation: str
    path: str
    old_value: Any
    new_value: Any


class CursorUpdateRequest(BaseModel):
    row: Optional[int] = None
    column: Optional[str] = None
    selection_start: Optional[tuple] = None
    selection_end: Optional[tuple] = None


class CommentCreate(BaseModel):
    target_type: Literal["cell", "row", "column", "session"]
    target_id: str
    content: str
    mentions: Optional[List[str]] = None


class LockRequest(BaseModel):
    row: int
    column: str


class SyncRequest(BaseModel):
    cells: List[Dict[str, Any]]


# ── Session Endpoints ─────────────────────────────────────────────────────────


@router.post("/sessions", response_model=SessionResponse)
def create_collab_session(
    request: SessionCreate,
    user_id: str = Depends(get_current_user_id),
    user_email: str = Depends(get_user_email),
):
    """
    Create a new collaboration session.

    Sessions allow multiple users to edit the same data in real-time
    with presence awareness and conflict resolution.
    """
    from services.dataset_loader import load_dataset_by_id

    initial_data = None
    if request.dataset_id:
        initial_data = load_dataset_by_id(request.dataset_id, None, user_id)

    session = create_session(
        owner_id=user_id,
        owner_name=user_email.split("@")[0],
        name=request.name,
        dataset_id=request.dataset_id,
        initial_data=initial_data,
    )

    return SessionResponse(
        session_id=session.session_id,
        name=session.name,
        owner_id=session.owner_id,
        dataset_id=session.dataset_id,
        created_at=session.created_at,
        users=list(session.users.values()),
        is_active=session.is_active,
    )


@router.get("/sessions", response_model=List[SessionResponse])
def list_collab_sessions(user_id: str = Depends(get_current_user_id)):
    """List all collaboration sessions the user is part of."""
    sessions = list_user_sessions(user_id)
    return [
        SessionResponse(
            session_id=s.session_id,
            name=s.name,
            owner_id=s.owner_id,
            dataset_id=s.dataset_id,
            created_at=s.created_at,
            users=list(s.users.values()),
            is_active=s.is_active,
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_collab_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get details of a collaboration session."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if user_id not in session.users:
        raise HTTPException(status_code=403, detail="Not a member of this session")

    return SessionResponse(
        session_id=session.session_id,
        name=session.name,
        owner_id=session.owner_id,
        dataset_id=session.dataset_id,
        created_at=session.created_at,
        users=list(session.users.values()),
        is_active=session.is_active,
    )


@router.post("/sessions/{session_id}/join", response_model=SessionResponse)
def join_collab_session(
    session_id: str,
    permission: Literal["view", "edit", "admin"] = "view",
    user_id: str = Depends(get_current_user_id),
    user_email: str = Depends(get_user_email),
):
    """Join an existing collaboration session."""
    try:
        session = join_session(
            session_id=session_id,
            user_id=user_id,
            user_name=user_email.split("@")[0],
            permission=Permission(permission),
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        return SessionResponse(
            session_id=session.session_id,
            name=session.name,
            owner_id=session.owner_id,
            dataset_id=session.dataset_id,
            created_at=session.created_at,
            users=list(session.users.values()),
            is_active=session.is_active,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sessions/{session_id}/leave")
def leave_collab_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Leave a collaboration session."""
    if leave_session(session_id, user_id):
        return {"status": "ok", "message": "Left session"}
    raise HTTPException(status_code=404, detail="Session not found")


@router.post("/sessions/{session_id}/invite")
def create_invite(
    session_id: str,
    invitee_email: str,
    permission: Literal["view", "edit", "admin"] = "edit",
    user_id: str = Depends(get_current_user_id),
):
    """Generate an invitation link for a user."""
    if not check_permission(session_id, user_id, Permission.ADMIN):
        raise HTTPException(status_code=403, detail="Admin permission required")

    try:
        invite_link = invite_user(
            session_id, user_id, invitee_email, Permission(permission)
        )
        return {"invite_link": invite_link, "invitee_email": invitee_email}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Cursor & Presence ─────────────────────────────────────────────────────────


@router.get("/sessions/{session_id}/cursors")
def list_cursors(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get all active cursor positions in a session."""
    session = get_session(session_id)
    if not session or user_id not in session.users:
        raise HTTPException(status_code=403, detail="Not authorized")

    cursors = get_active_cursors(session_id)
    return {"cursors": [c.__dict__ for c in cursors]}


@router.post("/sessions/{session_id}/cursor")
def update_user_cursor(
    session_id: str,
    request: CursorUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    user_email: str = Depends(get_user_email),
):
    """Update the current user's cursor position."""
    session = get_session(session_id)
    if not session or user_id not in session.users:
        raise HTTPException(status_code=403, detail="Not authorized")

    cursor = CursorPosition(
        user_id=user_id,
        user_name=user_email.split("@")[0],
        user_color=session.users[user_id]["user_color"],
        row=request.row,
        column=request.column,
        selection_start=request.selection_start,
        selection_end=request.selection_end,
    )

    if update_cursor(session_id, user_id, cursor):
        return {"status": "ok"}
    raise HTTPException(status_code=500, detail="Failed to update cursor")


# ── Cell Locking ─────────────────────────────────────────────────────────────


@router.post("/sessions/{session_id}/lock")
def acquire_lock(
    session_id: str,
    request: LockRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Lock a cell for editing."""
    if not check_permission(session_id, user_id, Permission.EDIT):
        raise HTTPException(status_code=403, detail="Edit permission required")

    lock = lock_cell(session_id, user_id, request.row, request.column)
    if not lock:
        raise HTTPException(
            status_code=409, detail="Cell is already locked by another user"
        )

    return {"lock": lock.__dict__}


@router.delete("/sessions/{session_id}/lock")
def release_lock(
    session_id: str,
    request: LockRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Release a cell lock."""
    if unlock_cell(session_id, user_id, request.row, request.column):
        return {"status": "ok"}
    raise HTTPException(status_code=400, detail="Lock not found or not owned by you")


@router.get("/sessions/{session_id}/locks")
def list_locks(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get all active cell locks in a session."""
    session = get_session(session_id)
    if not session or user_id not in session.users:
        raise HTTPException(status_code=403, detail="Not authorized")

    locks = get_cell_locks(session_id)
    return {"locks": [l.__dict__ for l in locks]}


# ── Changes & History ─────────────────────────────────────────────────────────


@router.post("/sessions/{session_id}/changes")
def apply_session_change(
    session_id: str,
    request: ChangeApplyRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Apply a change operation to the session data."""
    if not check_permission(session_id, user_id, Permission.EDIT):
        raise HTTPException(status_code=403, detail="Edit permission required")

    change = apply_change(
        session_id=session_id,
        user_id=user_id,
        operation=request.operation,
        path=request.path,
        old_value=request.old_value,
        new_value=request.new_value,
    )

    if not change:
        raise HTTPException(status_code=400, detail="Failed to apply change")

    return {"change": change.__dict__}


@router.post("/sessions/{session_id}/undo")
def undo_last_change(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Undo the last change made by the user."""
    change = undo_change(session_id, user_id)
    if not change:
        raise HTTPException(status_code=400, detail="No changes to undo")

    return {"undone": change.__dict__}


@router.get("/sessions/{session_id}/history")
def get_history(
    session_id: str,
    limit: int = 50,
    user_id: str = Depends(get_current_user_id),
):
    """Get change history for a session."""
    session = get_session(session_id)
    if not session or user_id not in session.users:
        raise HTTPException(status_code=403, detail="Not authorized")

    changes = get_change_history(session_id, limit)
    return {"changes": [c.__dict__ for c in changes]}


# ── Data Sync ─────────────────────────────────────────────────────────────────


@router.get("/sessions/{session_id}/data")
def get_data(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get the current data state of a session."""
    session = get_session(session_id)
    if not session or user_id not in session.users:
        raise HTTPException(status_code=403, detail="Not authorized")

    df = get_session_data(session_id)
    if df is None:
        return {"data": None, "rows": 0, "columns": []}

    return {
        "data": df.to_dict(orient="records"),
        "rows": len(df),
        "columns": list(df.columns),
    }


@router.post("/sessions/{session_id}/sync")
def sync_batch(
    session_id: str,
    request: SyncRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Sync a batch of data updates."""
    if not check_permission(session_id, user_id, Permission.EDIT):
        raise HTTPException(status_code=403, detail="Edit permission required")

    if sync_data_update(session_id, user_id, {"cells": request.cells}):
        return {"status": "ok"}
    raise HTTPException(status_code=400, detail="Sync failed")


@router.post("/sessions/{session_id}/selection")
def update_selection(
    session_id: str,
    selection: Dict[str, Any],
    user_id: str = Depends(get_current_user_id),
):
    """Broadcast selection change to other users."""
    if broadcast_selection(session_id, user_id, selection):
        return {"status": "ok"}
    raise HTTPException(status_code=400, detail="Failed to broadcast selection")


# ── Comments ─────────────────────────────────────────────────────────────────


@router.post("/sessions/{session_id}/comments")
def create_comment(
    session_id: str,
    request: CommentCreate,
    user_id: str = Depends(get_current_user_id),
    user_email: str = Depends(get_user_email),
):
    """Add a comment to a cell, row, or column."""
    session = get_session(session_id)
    if not session or user_id not in session.users:
        raise HTTPException(status_code=403, detail="Not authorized")

    comment = add_comment(
        session_id=session_id,
        user_id=user_id,
        user_name=user_email.split("@")[0],
        target_type=request.target_type,
        target_id=request.target_id,
        content=request.content,
        mentions=request.mentions,
    )

    return {"comment": comment.__dict__}


@router.get("/sessions/{session_id}/comments")
def list_comments(
    session_id: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
):
    """Get comments for a session."""
    session = get_session(session_id)
    if not session or user_id not in session.users:
        raise HTTPException(status_code=403, detail="Not authorized")

    comments = get_comments(session_id, target_type, target_id)
    return {"comments": [c.__dict__ for c in comments]}


@router.post("/sessions/{session_id}/comments/{comment_id}/resolve")
def mark_comment_resolved(
    session_id: str,
    comment_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Mark a comment as resolved."""
    if resolve_comment(session_id, comment_id, user_id):
        return {"status": "ok"}
    raise HTTPException(status_code=404, detail="Comment not found")


# ── Telemetry ─────────────────────────────────────────────────────────────────


@router.get("/sessions/{session_id}/telemetry")
def session_telemetry(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get telemetry data for a session."""
    session = get_session(session_id)
    if not session or user_id not in session.users:
        raise HTTPException(status_code=403, detail="Not authorized")

    return get_session_telemetry(session_id)


# ── WebSocket Endpoint ─────────────────────────────────────────────────────────


@router.websocket("/ws/collab/{session_id}")
async def collab_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time collaboration.

    Clients connect with their session_id and authenticate via
    the first message containing their user_id.
    """
    await websocket.accept()

    user_id = None
    session = None

    try:
        auth_msg = await websocket.receive_json()
        user_id = auth_msg.get("user_id")
        user_email = auth_msg.get("user_email", "Unknown")

        if not user_id:
            await websocket.send_json({"type": "error", "message": "user_id required"})
            await websocket.close()
            return

        session = join_session(
            session_id=session_id,
            user_id=user_id,
            user_name=user_email.split("@")[0],
            permission=Permission.EDIT,
        )

        if not session:
            await websocket.send_json({"type": "error", "message": "Session not found"})
            await websocket.close()
            return

        ws_manager.connect(f"collab:{session_id}", websocket, user_id)

        await websocket.send_json(
            {
                "type": "connected",
                "session_id": session_id,
                "users": list(session.users.values()),
                "cursors": [c.__dict__ for c in get_active_cursors(session_id)],
                "locks": [l.__dict__ for l in get_cell_locks(session_id)],
            }
        )

        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")

            if msg_type == "cursor":
                cursor = CursorPosition(
                    user_id=user_id,
                    user_name=user_email.split("@")[0],
                    user_color=session.users[user_id]["user_color"],
                    row=msg.get("row"),
                    column=msg.get("column"),
                )
                update_cursor(session_id, user_id, cursor)

            elif msg_type == "lock":
                lock = lock_cell(session_id, user_id, msg["row"], msg["column"])
                await websocket.send_json(
                    {
                        "type": "lock_result",
                        "success": lock is not None,
                        "lock": lock.__dict__ if lock else None,
                    }
                )

            elif msg_type == "unlock":
                unlock_cell(session_id, user_id, msg["row"], msg["column"])

            elif msg_type == "change":
                apply_change(
                    session_id=session_id,
                    user_id=user_id,
                    operation=msg["operation"],
                    path=msg["path"],
                    old_value=msg.get("old_value"),
                    new_value=msg["new_value"],
                )

            elif msg_type == "undo":
                undo_change(session_id, user_id)

            elif msg_type == "comment":
                add_comment(
                    session_id=session_id,
                    user_id=user_id,
                    user_name=user_email.split("@")[0],
                    target_type=msg["target_type"],
                    target_id=msg["target_id"],
                    content=msg["content"],
                    mentions=msg.get("mentions"),
                )

            elif msg_type == "selection":
                broadcast_selection(session_id, user_id, msg.get("selection", {}))

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        if user_id:
            leave_session(session_id, user_id)
            ws_manager.disconnect(f"collab:{session_id}", websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.close()
