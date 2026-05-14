"""
API Key Management Routes - create, manage, and monitor API keys.

Base path: /api/api-keys
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query

from middleware.auth import get_current_user_id
from services.api_key_manager import (
    APIKeyCreate,
    APIKeyResponse,
    APIKey,
    authenticate_api_key,
    create_api_key,
    get_api_keys,
    get_api_key,
    revoke_api_key,
    rotate_api_key,
    delete_api_key,
    get_usage_stats,
    SCOPES,
    DEFAULT_RATE_LIMITS,
)
from utils.errors import APIKeyNotFoundError
from utils.logger import logger


router = APIRouter(prefix="/api-keys", tags=["API Keys"])


@router.get("/scopes")
def list_scopes():
    """List all available API scopes and their descriptions."""
    return {"scopes": SCOPES}


@router.get("/tiers")
def list_tiers():
    """List available API tiers with their rate limits."""
    return {
        "tiers": [
            {
                "name": name,
                "rate_limits": limits,
            }
            for name, limits in DEFAULT_RATE_LIMITS.items()
        ]
    }


@router.post("", response_model=APIKeyResponse)
def create_key(
    request: APIKeyCreate,
    user_id: str = Depends(get_current_user_id),
):
    """
    Create a new API key.

    Returns the full API key only once. Store it securely.
    """
    for scope in request.scopes:
        if scope not in SCOPES:
            raise HTTPException(status_code=400, detail=f"Invalid scope: {scope}")

    return create_api_key(user_id, request)


@router.get("", response_model=List[APIKey])
def list_keys(user_id: str = Depends(get_current_user_id)):
    """List all API keys for the current user."""
    return get_api_keys(user_id)


@router.get("/{key_id}", response_model=APIKey)
def get_key(
    key_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get details of a specific API key."""
    key = get_api_key(key_id, user_id)
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    return key


@router.post("/{key_id}/rotate", response_model=APIKeyResponse)
def rotate_key(
    key_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Rotate an API key: revoke the old key and create a new one with same config.

    This enables zero-downtime key rotation for security compliance.
    """
    try:
        return rotate_api_key(key_id, user_id)
    except APIKeyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{key_id}/revoke")
def revoke_key(
    key_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Revoke an API key (soft delete)."""
    if revoke_api_key(key_id, user_id):
        return {"status": "ok", "message": "API key revoked"}
    raise HTTPException(status_code=404, detail="API key not found")


@router.delete("/{key_id}")
def delete_key(
    key_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Permanently delete an API key and its usage history."""
    if delete_api_key(key_id, user_id):
        return {"status": "ok", "message": "API key deleted"}
    raise HTTPException(status_code=404, detail="API key not found")


@router.get("/{key_id}/usage")
def key_usage(
    key_id: str,
    days: int = Query(default=30, ge=1, le=365),
    user_id: str = Depends(get_current_user_id),
):
    """Get usage statistics for an API key."""
    key = get_api_key(key_id, user_id)
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")

    return get_usage_stats(key_id, days)
