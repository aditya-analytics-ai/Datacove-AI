"""
admin_routes.py - Admin-only management endpoints.

All routes require role=admin. Non-admins receive 403.

Endpoints:
  GET  /admin/users                - list all users
  GET  /admin/users/{id}          - get single user
  POST /admin/users/{id}/deactivate - disable login
  POST /admin/users/{id}/activate   - re-enable login
  POST /admin/users/{id}/role       - change role (user|admin)
  GET  /admin/audit-log            - recent audit events (paginated)
  GET  /admin/stats                - platform-wide usage stats
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from utils.auth import require_admin, AuthUser
from utils.db import db
from utils.logger import logger

router = APIRouter(dependencies=[Depends(require_admin)])


# ── User management ───────────────────────────────────────────────────────────

@router.get("/admin/users")
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    admin: AuthUser = Depends(require_admin),
):
    offset = (page - 1) * page_size
    rows = db.fetchall(
        "SELECT id, username, role, is_active, created_at FROM users "
        "ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (page_size, offset),
    )
    total = db.fetchone("SELECT COUNT(*) as n FROM users")["n"]
    return JSONResponse({
        "users": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.get("/admin/users/{user_id}")
def get_user(user_id: str, admin: AuthUser = Depends(require_admin)):
    row = db.fetchone(
        "SELECT id, username, role, is_active, created_at FROM users WHERE id = ?",
        (user_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found.")
    return JSONResponse(dict(row))


@router.post("/admin/users/{user_id}/deactivate")
def deactivate_user(user_id: str, admin: AuthUser = Depends(require_admin)):
    if user_id == admin.user_id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account.")
    result = db.execute(
        "UPDATE users SET is_active = 0 WHERE id = ?", (user_id,)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found.")
    db.log_audit(admin.user_id, admin.username, "deactivate_user", resource=user_id)
    logger.info(f"Admin {admin.username} deactivated user {user_id}")
    return JSONResponse({"success": True, "user_id": user_id, "is_active": False})


@router.post("/admin/users/{user_id}/activate")
def activate_user(user_id: str, admin: AuthUser = Depends(require_admin)):
    result = db.execute(
        "UPDATE users SET is_active = 1 WHERE id = ?", (user_id,)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found.")
    db.log_audit(admin.user_id, admin.username, "activate_user", resource=user_id)
    return JSONResponse({"success": True, "user_id": user_id, "is_active": True})


class RoleUpdate(BaseModel):
    role: str  # "user" | "admin"


@router.post("/admin/users/{user_id}/role")
def set_role(user_id: str, body: RoleUpdate, admin: AuthUser = Depends(require_admin)):
    if body.role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="role must be 'user' or 'admin'.")
    result = db.execute(
        "UPDATE users SET role = ? WHERE id = ?", (body.role, user_id)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found.")
    db.log_audit(
        admin.user_id, admin.username, "change_role",
        resource=user_id, detail=f"new_role={body.role}",
    )
    logger.info(f"Admin {admin.username} set user {user_id} role → {body.role}")
    return JSONResponse({"success": True, "user_id": user_id, "role": body.role})


# ── Audit log ─────────────────────────────────────────────────────────────────

@router.get("/admin/audit-log")
def audit_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    user_id: str | None = Query(None),
    action: str | None = Query(None),
    admin: AuthUser = Depends(require_admin),
):
    filters, params = [], []
    if user_id:
        filters.append("user_id = ?"); params.append(user_id)
    if action:
        filters.append("action = ?"); params.append(action)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    offset = (page - 1) * page_size
    rows = db.fetchall(
        f"SELECT * FROM audit_log {where} ORDER BY ts DESC LIMIT ? OFFSET ?",
        tuple(params) + (page_size, offset),
    )
    total = db.fetchone(f"SELECT COUNT(*) as n FROM audit_log {where}", tuple(params))["n"]
    return JSONResponse({
        "events": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


# ── Platform stats ────────────────────────────────────────────────────────────

@router.get("/admin/stats")
def platform_stats(admin: AuthUser = Depends(require_admin)):
    total_users  = db.fetchone("SELECT COUNT(*) as n FROM users")["n"]
    active_users = db.fetchone("SELECT COUNT(*) as n FROM users WHERE is_active = 1")["n"]
    admin_count  = db.fetchone("SELECT COUNT(*) as n FROM users WHERE role = 'admin'")["n"]
    total_events = db.fetchone("SELECT COUNT(*) as n FROM audit_log")["n"]
    recent_logins = db.fetchone(
        "SELECT COUNT(*) as n FROM audit_log WHERE action = 'login' AND ts > ?",
        ((__import__("time").time() - 86400),),
    )["n"]

    # Active sessions from in-memory store
    try:
        from models.dataset_session import _sessions
        active_sessions = len(_sessions)
    except Exception:
        active_sessions = -1

    return JSONResponse({
        "users": {
            "total": total_users,
            "active": active_users,
            "admins": admin_count,
        },
        "activity": {
            "total_audit_events": total_events,
            "logins_last_24h": recent_logins,
        },
        "sessions": {
            "active_in_memory": active_sessions,
        },
    })
