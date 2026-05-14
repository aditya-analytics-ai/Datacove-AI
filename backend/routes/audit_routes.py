"""
Audit routes - expose the change log for a session.

Endpoints:
  GET  /audit/{session_id}            → full JSON audit log
  GET  /audit/{session_id}/summary    → stats (total changes, by action, by column)
  GET  /audit/{session_id}/export     → CSV download
  DELETE /audit/{session_id}          → clear the log
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse, Response

from models.dataset_session import get_session
from services.audit_log import get_log, clear_log, export_csv
from utils.auth import get_current_user, AuthUser
from utils.logger import logger
from utils.session_guard import require_session

router = APIRouter(dependencies=[Depends(get_current_user)])




@router.get("/audit/{session_id}")
def get_audit_log(session_id: str, user: AuthUser = Depends(get_current_user)):
    """Return the full audit log for a session."""
    require_session(session_id, owner_id=user.user_id)
    entries = get_log(session_id)
    return JSONResponse({
        "session_id":   session_id,
        "entry_count":  len(entries),
        "entries":      entries,
    })


@router.get("/audit/{session_id}/summary")
def get_audit_summary(session_id: str, user: AuthUser = Depends(get_current_user)):
    """Return aggregated statistics from the audit log."""
    require_session(session_id, owner_id=user.user_id)
    entries = get_log(session_id)

    if not entries:
        return JSONResponse({
            "session_id":    session_id,
            "total_actions": 0,
            "total_rows_removed": 0,
            "total_cells_changed": 0,
            "by_action": {},
            "by_column": {},
            "triggered_by": {},
        })

    by_action: dict = {}
    by_column: dict = {}
    by_trigger: dict = {}
    total_rows_removed  = 0
    total_cells_changed = 0

    for e in entries:
        action  = e["action"]
        col     = e["params"].get("column") or "(all)"
        trigger = e.get("triggered_by", "user")

        # Action aggregation
        if action not in by_action:
            by_action[action] = {"count": 0, "rows_removed": 0, "cells_changed": 0}
        by_action[action]["count"]         += 1
        by_action[action]["rows_removed"]  += max(0, e["rows_before"] - e["rows_after"])
        by_action[action]["cells_changed"] += e["cells_changed"]

        # Column aggregation
        if col not in by_column:
            by_column[col] = {"count": 0, "cells_changed": 0}
        by_column[col]["count"]         += 1
        by_column[col]["cells_changed"] += e["cells_changed"]

        # Trigger aggregation
        by_trigger[trigger] = by_trigger.get(trigger, 0) + 1

        total_rows_removed  += max(0, e["rows_before"] - e["rows_after"])
        total_cells_changed += e["cells_changed"]

    return JSONResponse({
        "session_id":          session_id,
        "total_actions":       len(entries),
        "total_rows_removed":  total_rows_removed,
        "total_cells_changed": total_cells_changed,
        "by_action":           by_action,
        "by_column":           by_column,
        "triggered_by":        by_trigger,
    })


@router.get("/audit/{session_id}/export")
def export_audit_csv(session_id: str, user: AuthUser = Depends(get_current_user)):
    """Download the audit log as a CSV file."""
    require_session(session_id, owner_id=user.user_id)
    csv_content = export_csv(session_id)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=audit_log_{session_id[:8]}.csv"
        },
    )


@router.delete("/audit/{session_id}")
def clear_audit_log(session_id: str, user: AuthUser = Depends(get_current_user)):
    """Clear the audit log for a session."""
    require_session(session_id, owner_id=user.user_id)
    clear_log(session_id)
    logger.info(f"Audit log cleared for session={session_id}")
    return JSONResponse({"success": True, "message": "Audit log cleared."})
