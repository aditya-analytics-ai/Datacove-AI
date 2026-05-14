"""
Pipeline routes - create, list, and run transformation pipelines.
"""
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from models.dataset_session import get_session, save_version, persist_dataset
from utils.logger import logger
from utils.preview import safe_preview
from services.pipeline_engine import create_pipeline, run_pipeline, list_all_pipelines
from utils.auth import get_current_user, AuthUser
from utils.session_guard import require_session

router = APIRouter(dependencies=[Depends(get_current_user)])


class CreatePipelineRequest(BaseModel):
    name: str
    steps: List[Dict[str, Any]]


class RunPipelineRequest(BaseModel):
    session_id: str
    pipeline_id: str




@router.post("/pipelines")
def create(req: CreatePipelineRequest):
    try:
        pipeline = create_pipeline(req.name, req.steps)
        logger.info(f"Pipeline created: {pipeline.pipeline_id} - '{pipeline.name}'")
        return JSONResponse({
            "pipeline_id": pipeline.pipeline_id,
            "name":        pipeline.name,
            "steps":       [{"action": s.action, "params": s.params} for s in pipeline.steps],
        })
    except Exception as e:
        logger.error(f"Create pipeline failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipelines")
def list_pipelines():
    try:
        return JSONResponse(list_all_pipelines())
    except Exception as e:
        logger.error(f"List pipelines failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pipelines/run")
async def run(req: RunPipelineRequest):
    try:
        session   = require_session(req.session_id)
        df_before = session.df_current.copy()
        df_after  = await run_in_threadpool(run_pipeline, req.pipeline_id, session.df_current)
        version = len(session.versions) + 1
        session.versions.append(save_version(req.session_id, df_before, version))
        session.df_current = df_after
        session.push_history(df_before, "run_pipeline", {"pipeline_id": req.pipeline_id})
        persist_dataset(req.session_id, df_after, session.filename)
        logger.info(f"Pipeline run: {req.pipeline_id} for session={req.session_id}")
        preview = safe_preview(df_after)
        return JSONResponse({
            "success": True,
            "rows":    len(df_after),
            "columns": list(df_after.columns),
            "preview": preview,
            "history": session.history_as_list(),
        })
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as e:
        logger.error(f"Run pipeline failed for session={req.session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))