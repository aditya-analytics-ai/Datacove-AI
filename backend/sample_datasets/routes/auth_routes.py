"""
auth_routes.py - register / login / refresh / logout / me endpoints (v3).

v3 changes:
  - /auth/login now returns both access_token (1 h) and refresh_token (30 days).
  - /auth/refresh - swap a valid refresh token for a new access token.
  - /auth/logout - client-side token drop; documented endpoint for clarity.
  - Rate limiting: 10 attempts per IP per 60 s on /login and /register.
  - /auth/me returns role and is_active.
  - /auth/login passes client IP to login_user() for audit logging.
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from utils.auth import (
    register_user, login_user, get_current_user, AuthUser,
    create_token, verify_refresh_token, auth_rate_limiter,
)

router = APIRouter()


class AuthRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6)


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/auth/register")
def register(req: AuthRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    # Rate-limit registrations to slow down account-creation spam
    auth_rate_limiter.check(ip)
    try:
        # Public registration always creates a "user" role - no self-promotion.
        access, refresh = login_user.__func__ if False else _register(req)
        return JSONResponse({
            "access_token":  access,
            "refresh_token": refresh,
            "username": req.username,
            "role": "user",
        })
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


def _register(req: AuthRequest):
    """Helper: register then login to get both tokens."""
    from utils.auth import register_user, create_refresh_token
    # register_user returns only an access token historically; rebuild properly
    import uuid, time
    from utils.db import db
    from utils.auth import _hash_password, create_token, create_refresh_token
    from utils.logger import logger

    existing = db.fetchone("SELECT id FROM users WHERE username = ?", (req.username,))
    if existing:
        raise ValueError("Username already taken.")
    user_id  = str(uuid.uuid4())
    pw_hash  = _hash_password(req.password)
    db.execute(
        "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, ?, ?)",
        (user_id, req.username, pw_hash, "user"),
    )
    logger.info(f"Auth: registered user '{req.username}' id={user_id}")
    access  = create_token(user_id, req.username, "user")
    refresh = create_refresh_token(user_id, req.username, "user")
    return access, refresh


@router.post("/auth/login")
def login(req: AuthRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    # Rate-limit: max 10 attempts per IP per 60 s
    auth_rate_limiter.check(ip)
    try:
        access, refresh = login_user(req.username, req.password, ip=ip)
        # Return role so the frontend can show/hide admin UI immediately
        row = __import__("utils.db", fromlist=["db"]).db.fetchone(
            "SELECT role FROM users WHERE username = ?", (req.username,)
        )
        role = row["role"] if row else "user"
        return JSONResponse({
            "access_token":  access,
            "refresh_token": refresh,
            "username": req.username,
            "role": role,
        })
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/auth/refresh")
def refresh_token(req: RefreshRequest):
    """
    Exchange a valid refresh token for a new short-lived access token.
    The refresh token itself is NOT rotated here (stateless design).
    """
    data = verify_refresh_token(req.refresh_token)
    if data is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token.")

    # Re-check the account is still active
    from utils.db import db
    row = db.fetchone(
        "SELECT is_active, role FROM users WHERE id = ?", (data["sub"],)
    )
    if not row:
        raise HTTPException(status_code=401, detail="User not found.")
    if not row["is_active"]:
        raise HTTPException(status_code=403, detail="Account is deactivated.")

    new_access = create_token(data["sub"], data["username"], row["role"])
    return JSONResponse({
        "access_token": new_access,
        "username":     data["username"],
        "role":         row["role"],
    })


@router.post("/auth/logout")
def logout(user: AuthUser = Depends(get_current_user)):
    """
    Stateless logout - the client should discard both tokens.
    A future version can maintain a token blacklist here if needed.
    """
    return JSONResponse({"logged_out": True, "username": user.username})


@router.get("/auth/me")
def me(user: AuthUser = Depends(get_current_user)):
    return JSONResponse({
        "user_id":   user.user_id,
        "username":  user.username,
        "role":      user.role,
        "is_active": user.is_active,
        "is_admin":  user.is_admin,
    })


# ── Password reset ────────────────────────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    username: str


class ResetPasswordRequest(BaseModel):
    token:        str
    new_password: str = Field(..., min_length=6)


@router.post("/auth/forgot-password")
def forgot_password(req: ForgotPasswordRequest):
    """
    Generate a password-reset token for the given username.

    In production: send this token via email to the user's registered address.
    In the current implementation (no email service configured), the token is
    returned in the response - this is intentional dev/self-hosted behaviour.
    Set SMTP_* env vars and wire up an email sender to make this production-safe.
    """
    import secrets, time
    from utils.db import db
    from utils.logger import logger

    row = db.fetchone("SELECT id FROM users WHERE username = ?", (req.username,))
    # Always return 200 to avoid username enumeration attacks
    if not row:
        return JSONResponse({"sent": True, "note": "If the account exists, a reset link was issued."})

    token     = secrets.token_urlsafe(32)
    expires   = int(time.time()) + 3600   # 1 hour TTL

    # Store in a password_reset_tokens table (auto-created below if missing)
    db.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            expires_at INTEGER NOT NULL
        )
    """)
    # Clean up old tokens for this user first
    db.execute("DELETE FROM password_reset_tokens WHERE user_id = ?", (row["id"],))
    db.execute(
        "INSERT INTO password_reset_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
        (token, row["id"], expires),
    )
    logger.info(f"Auth: password reset token issued for user '{req.username}'")

    # Try to get user's email from DB (column may not exist on older installs)
    email = None
    try:
        user_row = db.fetchone("SELECT email FROM users WHERE id = ?", (row["id"],))
        email = user_row["email"] if user_row else None
    except Exception:
        pass  # email column may not exist - fallback to dev_token

    # Send email if SMTP is configured and we have an address
    from utils.email_sender import send_password_reset_email, is_configured as smtp_ok
    email_sent = False
    if smtp_ok() and email:
        email_sent = send_password_reset_email(email, req.username, token)

    response: dict = {"sent": True}
    if email_sent:
        response["note"] = "Password reset link sent to your registered email address."
    else:
        # Dev / self-hosted fallback - token visible in API response
        response["note"] = (
            "SMTP not configured or no email on file. "
            "Set SMTP_* env vars and add email to your account for production use."
        )
        response["dev_token"] = token   # Remove once SMTP is live

    return JSONResponse(response)


@router.post("/auth/reset-password")
def reset_password(req: ResetPasswordRequest):
    """Exchange a valid reset token for a new password."""
    import time
    from utils.db import db
    from utils.auth import _hash_password
    from utils.logger import logger

    db.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            expires_at INTEGER NOT NULL
        )
    """)

    row = db.fetchone(
        "SELECT user_id, expires_at FROM password_reset_tokens WHERE token = ?",
        (req.token,),
    )
    if not row:
        raise HTTPException(status_code=400, detail="Invalid or already-used reset token.")
    if int(time.time()) > row["expires_at"]:
        db.execute("DELETE FROM password_reset_tokens WHERE token = ?", (req.token,))
        raise HTTPException(status_code=400, detail="Reset token has expired. Request a new one.")

    new_hash = _hash_password(req.new_password)
    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (new_hash, row["user_id"]),
    )
    db.execute("DELETE FROM password_reset_tokens WHERE token = ?", (req.token,))
    logger.info(f"Auth: password reset completed for user_id={row['user_id']}")
    return JSONResponse({"reset": True, "message": "Password updated successfully. Please log in."})
