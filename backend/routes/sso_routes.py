"""
sso_routes.py - SSO/SAML/OAuth integration.

Supports:
- Google OAuth
- GitHub OAuth
- Microsoft/Azure AD OAuth
- SAML 2.0 (Okta, Azure AD, etc.)
"""

from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
import secrets
import time
import hashlib

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from utils.auth import get_current_user, AuthUser, create_token
from utils.db import db
from utils.logger import logger

router = APIRouter()


class SSOProvider(str):
    GOOGLE = "google"
    GITHUB = "github"
    MICROSOFT = "microsoft"
    SAML = "saml"


SSO_CONFIGS = {
    "google": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://www.googleapis.com/oauth2/v2/userinfo",
        "scope": "openid email profile",
    },
    "github": {
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "scope": "user:email",
    },
    "microsoft": {
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "userinfo_url": "https://graph.microsoft.com/oidc/userinfo",
        "scope": "openid email profile",
    },
}


def _ensure_tables():
    """Create SSO tables if not exists."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS sso_providers (
            id VARCHAR(36) PRIMARY KEY,
            provider VARCHAR(32) NOT NULL UNIQUE,
            client_id VARCHAR(255) NOT NULL,
            client_secret_encrypted TEXT,
            enabled TINYINT(1) NOT NULL DEFAULT 0,
            created_at DOUBLE NOT NULL,
            INDEX idx_providers_enabled (enabled)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS sso_state (
            state VARCHAR(64) PRIMARY KEY,
            provider VARCHAR(32) NOT NULL,
            redirect_url TEXT,
            created_at DOUBLE NOT NULL,
            expires_at DOUBLE NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS saml_configs (
            id VARCHAR(36) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            entity_id VARCHAR(512) NOT NULL,
            sso_url VARCHAR(512) NOT NULL,
            x509_cert TEXT NOT NULL,
            enabled TINYINT(1) NOT NULL DEFAULT 0,
            created_at DOUBLE NOT NULL,
            updated_at DOUBLE NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def get_sso_config(provider: str) -> Dict[str, Any]:
    """Get SSO configuration for a provider."""
    _ensure_tables()

    row = db.fetchone(
        """
        SELECT * FROM sso_providers WHERE provider = ? AND enabled = 1
    """,
        (provider,),
    )

    if not row:
        return None

    import os

    return {
        "client_id": row["client_id"],
        "client_secret": os.getenv(f"{provider.upper()}_CLIENT_SECRET", ""),
    }


def create_oauth_state(provider: str, redirect_url: str = "") -> str:
    """Create OAuth state parameter for CSRF protection."""
    _ensure_tables()

    state = secrets.token_urlsafe(32)
    now = time.time()
    expires = now + 600

    db.execute(
        """
        INSERT INTO sso_state (state, provider, redirect_url, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?)
    """,
        (state, provider, redirect_url, now, expires),
    )

    return state


def verify_oauth_state(state: str) -> Optional[Dict[str, Any]]:
    """Verify and consume OAuth state."""
    _ensure_tables()

    row = db.fetchone("SELECT * FROM sso_state WHERE state = ?", (state,))

    if not row:
        return None

    if time.time() > row["expires_at"]:
        db.execute("DELETE FROM sso_state WHERE state = ?", (state,))
        return None

    db.execute("DELETE FROM sso_state WHERE state = ?", (state,))

    return {
        "provider": row["provider"],
        "redirect_url": row["redirect_url"],
    }


@router.get("/auth/sso/{provider}")
async def sso_login(
    provider: str,
    redirect_url: str = "",
    request: Request = None,
):
    """
    Initiate SSO login flow.

    Redirects to the OAuth provider's authorization page.
    After auth, user is redirected back to /auth/sso/callback/{provider}
    """
    _ensure_tables()

    if provider not in SSO_CONFIGS:
        raise HTTPException(status_code=400, detail="Unsupported SSO provider")

    config = get_sso_config(provider)
    if not config:
        raise HTTPException(
            status_code=501, detail=f"SSO provider '{provider}' not configured"
        )

    state = create_oauth_state(provider, redirect_url)

    base_url = str(request.base_url).rstrip("/")

    params = {
        "client_id": config["client_id"],
        "redirect_uri": f"{base_url}/api/auth/sso/callback/{provider}",
        "scope": SSO_CONFIGS[provider]["scope"],
        "response_type": "code",
        "state": state,
    }

    if provider == "google":
        params["access_type"] = "offline"
        params["prompt"] = "consent"

    auth_url = f"{SSO_CONFIGS[provider]['auth_url']}?{urlencode(params)}"

    return RedirectResponse(auth_url)


@router.get("/auth/sso/callback/{provider}")
async def sso_callback(
    provider: str,
    code: str,
    state: str,
    request: Request = None,
):
    """Handle OAuth callback from SSO provider."""
    _ensure_tables()

    state_data = verify_oauth_state(state)
    if not state_data:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    if state_data["provider"] != provider:
        raise HTTPException(status_code=400, detail="Provider mismatch")

    config = get_sso_config(provider)
    if not config:
        raise HTTPException(status_code=501, detail="SSO not configured")

    base_url = str(request.base_url).rstrip("/")

    token_data = await _exchange_code(
        provider, code, config, f"{base_url}/api/auth/sso/callback/{provider}"
    )

    user_info = await _get_user_info(provider, token_data["access_token"])

    user = _find_or_create_sso_user(provider, user_info)

    jwt_token = create_token(user["id"], role=user.get("role", "user"))

    if state_data["redirect_url"]:
        params = urlencode({"token": jwt_token})
        return RedirectResponse(f"{state_data['redirect_url']}?{params}")

    return JSONResponse(
        {
            "token": jwt_token,
            "user": {
                "id": user["id"],
                "email": user.get("email"),
                "username": user.get("username"),
            },
        }
    )


async def _exchange_code(
    provider: str, code: str, config: Dict, redirect_uri: str
) -> Dict:
    """Exchange authorization code for access token."""
    import httpx

    token_url = SSO_CONFIGS[provider]["token_url"]

    data = {
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(token_url, data=data)
        response.raise_for_status()
        return response.json()


async def _get_user_info(provider: str, access_token: str) -> Dict:
    """Get user info from SSO provider."""
    import httpx

    userinfo_url = SSO_CONFIGS[provider]["userinfo_url"]

    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient() as client:
        response = await client.get(userinfo_url, headers=headers)
        response.raise_for_status()
        return response.json()


def _find_or_create_sso_user(provider: str, user_info: Dict) -> Dict:
    """Find existing user or create new one via SSO."""
    _ensure_tables()

    email = user_info.get("email", "").lower()
    if not email:
        raise HTTPException(
            status_code=400, detail="Email not provided by SSO provider"
        )

    existing = db.fetchone("SELECT * FROM users WHERE email = ?", (email,))
    if existing:
        return dict(existing)

    import uuid
    import hashlib
    import os

    user_id = str(uuid.uuid4())
    now = time.time()
    password_hash = hashlib.sha256(os.urandom(32)).hexdigest()[:32]

    username = user_info.get("name") or user_info.get("login") or email.split("@")[0]

    db.execute(
        """
        INSERT INTO users (id, username, email, password_hash, role, is_active, created_at)
        VALUES (?, ?, ?, ?, 'user', 1, ?)
    """,
        (user_id, username, email, password_hash, now),
    )

    logger.info(f"SSO user created: {email} via {provider}")

    return {
        "id": user_id,
        "email": email,
        "username": username,
        "role": "user",
    }


class SAMLConfig(BaseModel):
    name: str
    entity_id: str
    sso_url: str
    x509_cert: str


@router.post("/auth/saml/config")
async def configure_saml(
    req: SAMLConfig,
    user: AuthUser = Depends(get_current_user),
):
    """Configure SAML SSO (admin only)."""
    from utils.auth import _is_admin

    if not _is_admin(user.user_id):
        raise HTTPException(status_code=403, detail="Admin only")

    _ensure_tables()

    config_id = hashlib.md5(req.entity_id.encode()).hexdigest()[:12]
    now = time.time()

    db.execute(
        """
        INSERT INTO saml_configs (id, name, entity_id, sso_url, x509_cert, enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 1, ?, ?)
        ON DUPLICATE KEY UPDATE
            name = VALUES(name),
            sso_url = VALUES(sso_url),
            x509_cert = VALUES(x509_cert),
            updated_at = VALUES(updated_at)
    """,
        (config_id, req.name, req.entity_id, req.sso_url, req.x509_cert, now, now),
    )

    return JSONResponse(
        {
            "config_id": config_id,
            "entity_id": req.entity_id,
            "acs_url": f"/api/auth/saml/{config_id}/acs",
        }
    )


@router.get("/auth/saml/{config_id}/metadata")
async def get_saml_metadata(config_id: str):
    """Get SAML SP metadata for IdP configuration."""
    _ensure_tables()

    row = db.fetchone(
        "SELECT * FROM saml_configs WHERE id = ? AND enabled = 1", (config_id,)
    )
    if not row:
        raise HTTPException(status_code=404, detail="SAML config not found")

    metadata = f"""<?xml version="1.0"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" entityID="{row["entity_id"]}">
    <md:SPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
        <md:AssertionConsumerService 
            Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST" 
            Location="{{acs_url}}" 
            index="0"/>
    </md:SPSSODescriptor>
</md:EntityDescriptor>"""

    return Response(content=metadata, media_type="application/xml")


@router.get("/auth/sso/providers")
def list_sso_providers():
    """List available and configured SSO providers."""
    _ensure_tables()

    available = {}
    for provider in SSO_CONFIGS:
        config = get_sso_config(provider)
        available[provider] = {
            "available": config is not None,
            "configured": bool(config),
        }

    return JSONResponse({"providers": available})
