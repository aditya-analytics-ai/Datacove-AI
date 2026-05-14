"""
session_routes.py - user's dataset listing and session management.

Endpoints:
  GET  /api/sessions          - list all datasets for the current user
  DELETE /api/sessions/{id}   - delete a dataset (must be owner)
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse

from utils.auth import get_current_user, AuthUser
from utils.errors import SessionPermissionError, SessionValidationError
from utils.session_guard import require_session
from models.dataset_session import list_sessions, delete_session, get_session

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/sessions")
def get_my_sessions(user: AuthUser = Depends(get_current_user)):
    """
    Return all datasets uploaded by the current user, newest first.
    Includes basic stats (rows, columns, health score) for the dashboard listing.
    """
    sessions = list_sessions(owner_id=user.user_id)
    return JSONResponse({"sessions": sessions, "count": len(sessions)})


@router.delete("/sessions/{session_id}")
def remove_session(session_id: str, user: AuthUser = Depends(get_current_user)):
    """
    Permanently delete a dataset session and all its files.
    Only the owner can delete their own session.

    Works even when the session has been evicted from memory - the SQLite
    record (which drives the My Datasets listing) is always cleaned up.
    """
    try:
        delete_session(session_id, owner_id=user.user_id)
    except SessionPermissionError:
        raise HTTPException(status_code=403, detail="Access denied.")
    except SessionValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse({"deleted": True, "session_id": session_id})


@router.get("/sessions/{session_id}")
def get_session_detail(session_id: str, user: AuthUser = Depends(get_current_user)):
    """Return basic metadata for a single session or 404 if it does not exist."""
    try:
        session = get_session(session_id, owner_id=user.user_id)
    except SessionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except SessionPermissionError:
        raise HTTPException(status_code=403, detail="Access denied.")

    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    return JSONResponse(
        {
            "session_id": session_id,
            "filename": session.filename,
            "owner_id": session.owner_id,
            "rows": len(session.df_current),
            "columns": list(session.df_current.columns),
            "created_at": session.created_at,
            "last_accessed": session.last_accessed,
        }
    )


@router.get("/sessions/{session_id}/rows")
def get_session_rows(
    session_id: str,
    startRow: int = 0,
    endRow: int = 100,
    user: AuthUser = Depends(get_current_user)
):
    """
    Fetch a targeted chunk of rows for Infinite Scrolling.
    """
    session = require_session(session_id, owner_id=user.user_id)
    
    # Bound the request
    startRow = max(0, startRow)
    endRow = min(len(session.df_current), endRow)
    
    if startRow >= endRow:
        return JSONResponse({"rows": [], "lastRow": len(session.df_current)})
        
    chunk_df = session.df_current.iloc[startRow:endRow]
    
    # Safe JSON serialization (similar to safe_preview but for specific chunk)
    from utils.preview import ext_to_object
    chunk_safe = ext_to_object(chunk_df)
    
    # Fill NA and convert to dict records
    records = chunk_safe.fillna("").astype(str).to_dict(orient="records")
    
    return JSONResponse({
        "rows": records,
        "lastRow": len(session.df_current)  # Tells AG grid the total size
    })
