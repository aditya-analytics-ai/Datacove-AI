"""
visual_pipeline_routes.py - visual pipeline builder API.

POST /api/visual-pipelines              - create new visual pipeline
GET  /api/visual-pipelines             - list user's visual pipelines
GET  /api/visual-pipelines/{id}        - get pipeline by ID
PUT  /api/visual-pipelines/{id}         - update pipeline
DELETE /api/visual-pipelines/{id}      - delete pipeline
POST /api/visual-pipelines/{id}/execute - execute the visual pipeline
GET  /api/visual-pipelines/templates   - get available node templates
POST /api/visual-pipelines/validate    - validate pipeline structure
"""

import uuid
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from models.dataset_session import persist_dataset
from utils.session_guard import require_session
from services.visual_pipeline_builder import (
    VisualPipeline,
    parse_visual_pipeline,
    get_node_templates,
    NODE_TEMPLATES,
    TransformType,
)
from services.cleaning_engine import apply_transformation
from utils.auth import get_current_user, AuthUser
from utils.db import db
from utils.logger import logger
from utils.preview import safe_preview

router = APIRouter(prefix="/visual-pipelines", dependencies=[Depends(get_current_user)])


class CreateVisualPipelineRequest(BaseModel):
    name: str
    description: str = ""
    tags: List[str] = []
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, str]] = []


class UpdateVisualPipelineRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    nodes: Optional[List[Dict[str, Any]]] = None
    edges: Optional[List[Dict[str, str]]] = None


class ExecutePipelineRequest(BaseModel):
    session_id: str
    source_columns: Optional[List[str]] = None


def _ensure_tables():
    """Create visual_pipelines table if not exists."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS visual_pipelines (
            id VARCHAR(36) PRIMARY KEY,
            owner_id VARCHAR(36) NOT NULL,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            tags TEXT,
            nodes TEXT NOT NULL,
            edges TEXT,
            created_at DOUBLE NOT NULL,
            updated_at DOUBLE NOT NULL,
            INDEX idx_vp_owner (owner_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


@router.get("/templates")
def list_templates():
    """Get all available node templates for the visual builder."""
    return JSONResponse({"templates": get_node_templates()})


@router.post("/validate")
def validate_pipeline(data: Dict[str, Any], user: AuthUser = Depends(get_current_user)):
    """Validate a visual pipeline without saving."""
    pipeline = parse_visual_pipeline(data, user.user_id)
    is_valid, errors = pipeline.validate()
    return JSONResponse(
        {
            "valid": is_valid,
            "errors": errors,
        }
    )


@router.post("")
def create_visual_pipeline(
    req: CreateVisualPipelineRequest, user: AuthUser = Depends(get_current_user)
):
    """Create a new visual pipeline."""
    _ensure_tables()

    pipeline = VisualPipeline(
        id=str(uuid.uuid4()),
        name=req.name,
        owner_id=user.user_id,
        description=req.description,
        tags=req.tags,
    )

    for node_data in req.nodes:
        from services.visual_pipeline_builder import NodeType

        node = pipeline.nodes.append(
            type(
                "Node",
                (),
                {
                    "id": node_data["id"],
                    "type": NodeType(node_data.get("type", "transform")),
                    "transform": TransformType(node_data["transform"])
                    if "transform" in node_data
                    else None,
                    "label": node_data.get("label", ""),
                    "params": node_data.get("params", {}),
                },
            )()
        )

    pipeline.edges = req.edges

    is_valid, errors = pipeline.validate()
    if not is_valid:
        raise HTTPException(status_code=400, detail={"errors": errors})

    now = time.time()
    db.execute(
        """
        INSERT INTO visual_pipelines (id, owner_id, name, description, tags, nodes, edges, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            pipeline.id,
            user.user_id,
            pipeline.name,
            pipeline.description,
            ",".join(pipeline.tags),
            str(req.nodes),
            str(req.edges),
            now,
            now,
        ),
    )

    logger.info(f"Visual pipeline created: {pipeline.id} by {user.user_id}")

    return JSONResponse(
        {
            "id": pipeline.id,
            "name": pipeline.name,
            "created_at": now,
        }
    )


@router.get("")
def list_visual_pipelines(user: AuthUser = Depends(get_current_user)):
    """List all visual pipelines for the current user."""
    _ensure_tables()

    rows = db.fetchall(
        "SELECT id, name, description, tags, created_at, updated_at FROM visual_pipelines WHERE owner_id = ? ORDER BY updated_at DESC",
        (user.user_id,),
    )

    pipelines = []
    for row in rows:
        pipelines.append(
            {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "tags": row["tags"].split(",") if row["tags"] else [],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )

    return JSONResponse({"pipelines": pipelines})


@router.get("/{pipeline_id}")
def get_visual_pipeline(pipeline_id: str, user: AuthUser = Depends(get_current_user)):
    """Get a visual pipeline by ID."""
    _ensure_tables()

    row = db.fetchone(
        "SELECT * FROM visual_pipelines WHERE id = ? AND owner_id = ?",
        (pipeline_id, user.user_id),
    )

    if not row:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    import ast

    return JSONResponse(
        {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "tags": row["tags"].split(",") if row["tags"] else [],
            "nodes": ast.literal_eval(row["nodes"]) if row["nodes"] else [],
            "edges": ast.literal_eval(row["edges"]) if row["edges"] else [],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    )


@router.put("/{pipeline_id}")
def update_visual_pipeline(
    pipeline_id: str,
    req: UpdateVisualPipelineRequest,
    user: AuthUser = Depends(get_current_user),
):
    """Update a visual pipeline."""
    _ensure_tables()

    row = db.fetchone(
        "SELECT * FROM visual_pipelines WHERE id = ? AND owner_id = ?",
        (pipeline_id, user.user_id),
    )

    if not row:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    updates = []
    params = []

    if req.name is not None:
        updates.append("name = ?")
        params.append(req.name)
    if req.description is not None:
        updates.append("description = ?")
        params.append(req.description)
    if req.tags is not None:
        updates.append("tags = ?")
        params.append(",".join(req.tags))
    if req.nodes is not None:
        updates.append("nodes = ?")
        params.append(str(req.nodes))
    if req.edges is not None:
        updates.append("edges = ?")
        params.append(str(req.edges))

    updates.append("updated_at = ?")
    params.append(time.time())

    params.extend([pipeline_id, user.user_id])

    db.execute(
        f"UPDATE visual_pipelines SET {', '.join(updates)} WHERE id = ? AND owner_id = ?",
        tuple(params),
    )

    logger.info(f"Visual pipeline updated: {pipeline_id}")

    return JSONResponse({"updated": True})


@router.delete("/{pipeline_id}")
def delete_visual_pipeline(
    pipeline_id: str, user: AuthUser = Depends(get_current_user)
):
    """Delete a visual pipeline."""
    _ensure_tables()

    result = db.execute(
        "DELETE FROM visual_pipelines WHERE id = ? AND owner_id = ?",
        (pipeline_id, user.user_id),
    )

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    logger.info(f"Visual pipeline deleted: {pipeline_id}")

    return JSONResponse({"deleted": True})


@router.post("/{pipeline_id}/execute")
async def execute_visual_pipeline(
    pipeline_id: str,
    req: ExecutePipelineRequest,
    user: AuthUser = Depends(get_current_user),
):
    """Execute a visual pipeline on a dataset session."""
    _ensure_tables()

    row = db.fetchone(
        "SELECT * FROM visual_pipelines WHERE id = ? AND owner_id = ?",
        (pipeline_id, user.user_id),
    )

    if not row:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    import ast

    nodes = ast.literal_eval(row["nodes"]) if row["nodes"] else []
    edges = ast.literal_eval(row["edges"]) if row["edges"] else []

    pipeline = parse_visual_pipeline(
        {
            "id": pipeline_id,
            "name": row["name"],
            "nodes": nodes,
            "edges": edges,
        },
        user.user_id,
    )

    is_valid, errors = pipeline.validate()
    if not is_valid:
        raise HTTPException(status_code=400, detail={"errors": errors})

    session = require_session(req.session_id, owner_id=user.user_id)
    df = session.df_current.copy()
    df_before = df.copy()

    step_results = []

    for step in pipeline.to_pipeline_definition()["steps"]:
        action = step["action"]
        params = step.get("params", {})

        try:
            df = await run_in_threadpool(apply_transformation, df, action, params)
            step_results.append(
                {
                    "action": action,
                    "status": "success",
                    "rows": len(df),
                    "columns": list(df.columns),
                }
            )
        except Exception as e:
            step_results.append(
                {
                    "action": action,
                    "status": "error",
                    "error": str(e),
                }
            )
            logger.error(f"Pipeline step '{action}' failed: {e}")

    session.df_current = df
    persist_dataset(req.session_id, df, session.filename)

    return JSONResponse(
        {
            "success": True,
            "session_id": req.session_id,
            "rows": len(df),
            "columns": list(df.columns),
            "preview": safe_preview(df),
            "step_results": step_results,
        }
    )
