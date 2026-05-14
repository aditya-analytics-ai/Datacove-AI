"""
Middleware auth helpers - simple wrappers around utils.auth for routes that need user_id directly.
"""

from fastapi import Depends

from utils.auth import get_current_user, AuthUser, require_admin as _require_admin


def get_current_user_id(user: AuthUser = Depends(get_current_user)) -> str:
    """FastAPI dependency that returns the current user's ID as a string."""
    return user.user_id


def get_user_email(user: AuthUser = Depends(get_current_user)) -> str:
    """FastAPI dependency that returns the current user's email/username."""
    return user.username


def require_admin(user: AuthUser = Depends(_require_admin)) -> AuthUser:
    """FastAPI dependency that requires admin role."""
    return user
