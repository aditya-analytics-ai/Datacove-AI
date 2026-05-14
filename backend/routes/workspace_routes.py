"""
workspace_routes.py - Multi-user workspace API.

POST /api/workspaces                - create workspace
GET  /api/workspaces              - list user's workspaces
GET  /api/workspaces/{id}         - get workspace details
PUT  /api/workspaces/{id}         - update workspace
DELETE /api/workspaces/{id}       - delete workspace

POST /api/workspaces/{id}/members     - add member
DELETE /api/workspaces/{id}/members/{user_id} - remove member
GET  /api/workspaces/{id}/members    - list members

POST /api/workspaces/{id}/invite     - create invite
POST /api/workspaces/invites/{token}/accept - accept invite
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from services.workspaces import (
    create_workspace,
    get_workspace,
    list_user_workspaces,
    update_workspace,
    delete_workspace,
    add_member,
    remove_member,
    list_members,
    create_invite,
    accept_invite,
    can_view_workspace,
    can_admin_workspace,
    get_member_role,
)
from utils.auth import get_current_user, AuthUser
from utils.logger import logger

router = APIRouter(prefix="/workspaces", dependencies=[Depends(get_current_user)])


class CreateWorkspaceRequest(BaseModel):
    name: str
    description: str = ""


class UpdateWorkspaceRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


class AddMemberRequest(BaseModel):
    user_id: str
    role: str = "member"


class CreateInviteRequest(BaseModel):
    email: str
    role: str = "member"
    expires_in_hours: int = 72


class AcceptInviteRequest(BaseModel):
    token: str


@router.post("")
def create(req: CreateWorkspaceRequest, user: AuthUser = Depends(get_current_user)):
    """Create a new workspace."""
    workspace = create_workspace(req.name, user.user_id, req.description)

    return JSONResponse(
        {
            "id": workspace.id,
            "name": workspace.name,
            "description": workspace.description,
            "owner_id": workspace.owner_id,
            "created_at": workspace.created_at,
        }
    )


@router.get("")
def list_workspaces(user: AuthUser = Depends(get_current_user)):
    """List all workspaces the user has access to."""
    workspaces = list_user_workspaces(user.user_id)

    return JSONResponse(
        {
            "workspaces": [
                {
                    "id": w.id,
                    "name": w.name,
                    "description": w.description,
                    "owner_id": w.owner_id,
                    "created_at": w.created_at,
                    "updated_at": w.updated_at,
                    "is_owner": w.owner_id == user.user_id,
                }
                for w in workspaces
            ]
        }
    )


@router.get("/{workspace_id}")
def get(workspace_id: str, user: AuthUser = Depends(get_current_user)):
    """Get workspace details."""
    if not can_view_workspace(user.user_id, workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace = get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    members = list_members(workspace_id)
    role = get_member_role(user.user_id, workspace_id)

    return JSONResponse(
        {
            "id": workspace.id,
            "name": workspace.name,
            "description": workspace.description,
            "owner_id": workspace.owner_id,
            "settings": workspace.settings,
            "created_at": workspace.created_at,
            "updated_at": workspace.updated_at,
            "user_role": role,
            "members": members,
        }
    )


@router.put("/{workspace_id}")
def update(
    workspace_id: str,
    req: UpdateWorkspaceRequest,
    user: AuthUser = Depends(get_current_user),
):
    """Update workspace settings."""
    if not can_admin_workspace(user.user_id, workspace_id):
        raise HTTPException(
            status_code=403, detail="Not authorized to update workspace"
        )

    success = update_workspace(
        workspace_id,
        user.user_id,
        name=req.name,
        description=req.description,
        settings=req.settings,
    )

    if not success:
        raise HTTPException(status_code=400, detail="Failed to update workspace")

    return JSONResponse({"updated": True})


@router.delete("/{workspace_id}")
def delete(workspace_id: str, user: AuthUser = Depends(get_current_user)):
    """Delete workspace. Only owner can delete."""
    workspace = get_workspace(workspace_id)

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if workspace.owner_id != user.user_id:
        raise HTTPException(status_code=403, detail="Only owner can delete workspace")

    delete_workspace(workspace_id, user.user_id)

    return JSONResponse({"deleted": True})


@router.get("/{workspace_id}/members")
def list_workspace_members(
    workspace_id: str, user: AuthUser = Depends(get_current_user)
):
    """List all members of a workspace."""
    if not can_view_workspace(user.user_id, workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")

    members = list_members(workspace_id)

    return JSONResponse({"members": members})


@router.post("/{workspace_id}/members")
def add_workspace_member(
    workspace_id: str, req: AddMemberRequest, user: AuthUser = Depends(get_current_user)
):
    """Add a member to workspace. Admin/owner only."""
    if not can_admin_workspace(user.user_id, workspace_id):
        raise HTTPException(status_code=403, detail="Not authorized to add members")

    add_member(workspace_id, req.user_id, req.role)

    return JSONResponse({"added": True, "user_id": req.user_id, "role": req.role})


@router.delete("/{workspace_id}/members/{member_user_id}")
def remove_workspace_member(
    workspace_id: str, member_user_id: str, user: AuthUser = Depends(get_current_user)
):
    """Remove a member from workspace. Admin/owner only."""
    if not can_admin_workspace(user.user_id, workspace_id):
        raise HTTPException(status_code=403, detail="Not authorized to remove members")

    success = remove_member(workspace_id, member_user_id, user.user_id)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to remove member")

    return JSONResponse({"removed": True})


@router.post("/{workspace_id}/invite")
def create_workspace_invite(
    workspace_id: str,
    req: CreateInviteRequest,
    user: AuthUser = Depends(get_current_user),
):
    """Create an invite link for a workspace."""
    if not can_admin_workspace(user.user_id, workspace_id):
        raise HTTPException(status_code=403, detail="Not authorized to create invites")

    workspace = get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    token = create_invite(
        workspace_id, req.email, req.role, user.user_id, req.expires_in_hours
    )

    invite_url = f"/invites/{token}"

    return JSONResponse(
        {
            "invite_url": invite_url,
            "token": token,
            "email": req.email,
            "role": req.role,
            "expires_in_hours": req.expires_in_hours,
        }
    )


@router.post("/invites/{token}/accept")
def accept_workspace_invite(token: str, user: AuthUser = Depends(get_current_user)):
    """Accept a workspace invite."""
    workspace_id = accept_invite(token, user.user_id, user.email)

    if not workspace_id:
        raise HTTPException(status_code=400, detail="Invalid or expired invite")

    workspace = get_workspace(workspace_id)

    return JSONResponse(
        {
            "success": True,
            "workspace_id": workspace_id,
            "workspace_name": workspace.name if workspace else "Unknown",
        }
    )
