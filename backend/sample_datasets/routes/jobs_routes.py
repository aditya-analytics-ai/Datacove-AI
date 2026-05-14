"""
jobs_routes.py - Background job status endpoints.

Large-file operations (uploads > LARGE_FILE_ROWS, AI agent on big datasets)
submit a job and return a job_id. The frontend polls these endpoints.

Endpoints:
  GET /jobs/{job_id}         - get status + result
  GET /jobs                  - list active jobs for this user
  POST /upload/async         - async upload for large files
  POST /ai-agent/run/async   - async AI agent for large datasets
"""
import uuid
import io
import pandas as pd
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from utils.auth import get_current_user, AuthUser
from utils.job_store import job_store
from utils.file_utils import validate_upload, save_upload_sync
from utils.billing import enforce_upload, record_usage
from utils.logger import logger
from utils.preview import safe_preview
from services.dataset_loader import load_dataset, infer_schema_suggestions
from models.dataset_session import DatasetSession, save_session, get_session, save_version, persist_dataset
from services.ai_agent import run_ai_agent

router = APIRouter(dependencies=[Depends(get_current_user)])

# Files larger than this row count go async
LARGE_FILE_ROWS = 50_000


# ── Job status ────────────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}")
def get_job(job_id: str, user: AuthUser = Depends(get_current_user)):
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    # Strip full result payload for pending/running - saves bandwidth
    if job["status"] in ("pending", "running"):
        job.pop("result", None)
    return JSONResponse(job)


@router.get("/jobs")
def list_jobs(user: AuthUser = Depends(get_current_user)):
    return JSONResponse({"jobs": job_store.list_active()})


# ── Async upload ──────────────────────────────────────────────────────────────

def _process_upload(file_path: Path, filename: str, user_id: str) -> dict:
    """Runs in background thread. Loads dataset, creates session, returns result dict."""
    df = load_dataset(file_path)
    session_id = str(uuid.uuid4())
    session    = DatasetSession(df=df, filename=filename, owner_id=user_id)
    save_session(session_id, session)
    record_usage(user_id, "upload")
    schema_suggestions = infer_schema_suggestions(df)
    return {
        "session_id":         session_id,
        "filename":           filename,
        "rows":               len(df),
        "columns":            list(df.columns),
        "preview":            safe_preview(df),
        "schema_suggestions": schema_suggestions,
    }


@router.post("/upload/async")
async def upload_async(
    file: UploadFile = File(...),
    user: AuthUser = Depends(get_current_user),
):
    """
    Upload a file and process it in the background.
    Returns a job_id immediately. Poll GET /jobs/{job_id} for status.
    When status='done', result contains the session_id and preview.
    """
    validate_upload(file)
    enforce_upload(user.user_id, 0)   # check tier before saving the file

    # Save file bytes synchronously (fast - just disk write)
    file_path = await save_upload_sync(file)
    job_id = job_store.submit(
        _process_upload,
        file_path,
        file.filename or "dataset",
        user.user_id,
        job_id=str(uuid.uuid4()),
    )
    logger.info(f"Async upload: job {job_id} for user {user.user_id} file='{file.filename}'")
    return JSONResponse({
        "job_id":  job_id,
        "status":  "pending",
        "message": "File received. Processing in background - poll /api/jobs/{job_id}",
    })


# ── Async AI agent ────────────────────────────────────────────────────────────

class AsyncAgentRequest(BaseModel):
    session_id: str


def _run_agent_job(session_id: str) -> dict:
    """Runs in background thread."""
    session   = get_session(session_id)
    if session is None:
        raise ValueError(f"Session {session_id} not found")
    df_before = session.df_current.copy()
    df_cleaned, report = run_ai_agent(df_before)
    version = len(session.versions) + 1
    path    = save_version(session_id, df_before, version)
    session.versions.append(path)
    session.push_history(df_before, "ai_agent_run", {})
    session.df_current = df_cleaned
    persist_dataset(session_id, df_cleaned, session.filename)
    return {
        "success": True,
        "report":  report,
        "rows":    len(df_cleaned),
        "columns": list(df_cleaned.columns),
        "preview": safe_preview(df_cleaned),
    }


@router.post("/ai-agent/run/async")
def run_agent_async(
    req: AsyncAgentRequest,
    user: AuthUser = Depends(get_current_user),
):
    """
    Run the AI cleaning agent in the background.
    Useful for datasets > 50k rows where the synchronous route times out.
    Returns job_id - poll GET /jobs/{job_id} for status + result.
    """
    session = get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if session.owner_id != user.user_id and not user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied.")

    job_id = job_store.submit(_run_agent_job, req.session_id)
    logger.info(f"Async AI agent: job {job_id} session={req.session_id}")
    return JSONResponse({
        "job_id":  job_id,
        "status":  "pending",
        "message": "AI agent started. Poll /api/jobs/{job_id} for progress.",
    })
