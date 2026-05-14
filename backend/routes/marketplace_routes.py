"""
marketplace_routes.py - Pipeline template marketplace API.

GET  /api/marketplace              - list templates
GET  /api/marketplace/featured    - get featured templates
GET  /api/marketplace/categories  - list categories
GET  /api/marketplace/{id}        - get template details
POST /api/marketplace             - publish a template
PUT  /api/marketplace/{id}        - update template
DELETE /api/marketplace/{id}      - delete template
POST /api/marketplace/{id}/rate   - rate a template
POST /api/marketplace/{id}/install - install template to workspace
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from services.marketplace import (
    publish_template,
    get_template,
    list_templates,
    get_featured_templates,
    rate_template,
    increment_downloads,
    delete_template,
    feature_template,
    verify_template,
    CATEGORIES,
)
from services.workspaces import can_admin_workspace
from utils.auth import get_current_user, AuthUser
from utils.logger import logger

router = APIRouter(prefix="/marketplace", dependencies=[Depends(get_current_user)])


class PublishTemplateRequest(BaseModel):
    name: str
    description: str
    category: str
    tags: List[str]
    steps: List[Dict[str, Any]]


class UpdateTemplateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None


class RateTemplateRequest(BaseModel):
    rating: int


class InstallTemplateRequest(BaseModel):
    workspace_id: Optional[str] = None


@router.get("/categories")
def list_categories():
    """Get all available template categories."""
    return JSONResponse(
        {
            "categories": CATEGORIES,
        }
    )


@router.get("/featured")
def get_featured():
    """Get featured templates."""
    templates = get_featured_templates(limit=10)
    return JSONResponse(
        {
            "templates": [_template_to_dict(t) for t in templates],
        }
    )


@router.get("")
def list_marketplace_templates(
    category: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: Optional[str] = "downloads",
    limit: int = 20,
    offset: int = 0,
):
    """List marketplace templates with filtering."""
    if category and category not in CATEGORIES:
        category = None

    templates = list_templates(
        category=category,
        search=search,
        sort_by=sort_by or "downloads",
        limit=min(limit, 100),
        offset=offset,
    )

    return JSONResponse(
        {
            "templates": [_template_to_dict(t) for t in templates],
            "count": len(templates),
        }
    )


@router.get("/{template_id}")
def get_marketplace_template(template_id: str):
    """Get template details."""
    template = get_template(template_id)

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return JSONResponse(_template_to_dict(template, include_steps=True))


@router.post("")
def create_template(
    req: PublishTemplateRequest, user: AuthUser = Depends(get_current_user)
):
    """Publish a pipeline template to the marketplace."""
    if req.category not in CATEGORIES:
        raise HTTPException(
            status_code=400, detail=f"Invalid category. Choose from: {CATEGORIES}"
        )

    template = publish_template(
        name=req.name,
        description=req.description,
        author_id=user.user_id,
        author_name=user.email or user.user_id,
        category=req.category,
        tags=req.tags,
        steps=req.steps,
    )

    return JSONResponse(
        {
            "id": template.id,
            "name": template.name,
            "created_at": template.created_at,
        }
    )


@router.put("/{template_id}")
def update_template(
    template_id: str,
    req: UpdateTemplateRequest,
    user: AuthUser = Depends(get_current_user),
):
    """Update a template. Only author can update."""
    template = get_template(template_id)

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if template.author_id != user.user_id:
        raise HTTPException(
            status_code=403, detail="Not authorized to update this template"
        )

    pass

    return JSONResponse({"updated": True})


@router.delete("/{template_id}")
def remove_template(template_id: str, user: AuthUser = Depends(get_current_user)):
    """Delete a template. Only author can delete."""
    success = delete_template(template_id, user.user_id)

    if not success:
        raise HTTPException(
            status_code=404, detail="Template not found or not authorized"
        )

    return JSONResponse({"deleted": True})


@router.post("/{template_id}/rate")
def rate_marketplace_template(
    template_id: str,
    req: RateTemplateRequest,
    user: AuthUser = Depends(get_current_user),
):
    """Rate a template (1-5 stars)."""
    template = get_template(template_id)

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    success = rate_template(template_id, user.user_id, req.rating)

    if not success:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

    updated = get_template(template_id)

    return JSONResponse(
        {
            "rated": True,
            "new_rating": updated.rating if updated else 0,
            "rating_count": updated.rating_count if updated else 0,
        }
    )


@router.post("/{template_id}/install")
async def install_template(
    template_id: str,
    req: InstallTemplateRequest,
    user: AuthUser = Depends(get_current_user),
):
    """Install a template to user's workspace."""
    template = get_template(template_id)

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    increment_downloads(template_id)

    from services.pipeline_engine import create_pipeline

    pipeline = create_pipeline(
        name=f"{template.name} (from template)",
        steps=[
            {"action": s["action"], "params": s.get("params", {})}
            for s in template.steps
        ],
        owner_id=user.user_id,
    )

    logger.info(
        f"Template {template_id} installed by {user.user_id} as pipeline {pipeline.pipeline_id}"
    )

    return JSONResponse(
        {
            "installed": True,
            "pipeline_id": pipeline.pipeline_id,
            "pipeline_name": pipeline.name,
            "source_template": template_id,
        }
    )


def _template_to_dict(template, include_steps: bool = False) -> Dict[str, Any]:
    """Convert PipelineTemplate to dict for JSON response."""
    result = {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "author_id": template.author_id,
        "author_name": template.author_name,
        "category": template.category,
        "tags": template.tags,
        "downloads": template.downloads,
        "rating": template.rating,
        "rating_count": template.rating_count,
        "is_featured": template.is_featured,
        "is_verified": template.is_verified,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }

    if include_steps:
        result["steps"] = template.steps
        result["step_count"] = len(template.steps)

    return result
