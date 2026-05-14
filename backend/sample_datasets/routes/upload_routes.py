"""
Upload routes v2 - stamps owner_id on every new session.
"""
import uuid
import pandas as pd
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from utils.file_utils import validate_upload, save_upload
from utils.preview import safe_preview
from utils.logger import logger
from utils.auth import get_current_user, AuthUser
from services.dataset_loader import load_dataset, infer_schema_suggestions
from models.dataset_session import DatasetSession, save_session
from utils.billing import enforce_upload, record_usage

router = APIRouter(dependencies=[Depends(get_current_user)])


class PasteRequest(BaseModel):
    csv_text: str
    filename: str = "pasted_data.csv"


@router.post("/upload")
async def upload_dataset(
    file: UploadFile = File(...),
    user: AuthUser = Depends(get_current_user),
):
    try:
        validate_upload(file)
        logger.info(f"Upload: received '{file.filename}' by user={user.user_id}")

        file_path: Path = await save_upload(file)
        df = await run_in_threadpool(load_dataset, file_path)
        logger.info(f"Upload: parsed - {len(df)} rows, {len(df.columns)} columns")

        enforce_upload(user.user_id, len(df))   # raises 402 if over tier limit
        session_id = str(uuid.uuid4())
        session    = DatasetSession(df=df, filename=file.filename or "dataset",
                                    owner_id=user.user_id)
        save_session(session_id, session)
        record_usage(user.user_id, "upload")

        schema_suggestions = infer_schema_suggestions(df)
        logger.info(f"Upload: session created - {session_id} owner={user.user_id}")

        # Auto-trigger AI orchestrator - non-fatal if it fails
        ai_insights = None
        try:
            from services.ai_orchestrator import orchestrate_ai_analysis
            ai_insights = await run_in_threadpool(
                orchestrate_ai_analysis, df, file.filename or "dataset", None
            )
            logger.info(f"Upload: orchestrator completed - {len(ai_insights.get('actions', []))} actions")
        except Exception as oe:
            logger.warning(f"Upload: orchestrator failed (non-fatal): {oe}")

        return JSONResponse({
            "session_id":         session_id,
            "filename":           file.filename,
            "rows":               len(df),
            "columns":            list(df.columns),
            "preview":            safe_preview(df),
            "schema_suggestions": schema_suggestions,
            "ai_insights":        ai_insights,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed for '{file.filename}': {e}")
        raise HTTPException(status_code=500, detail=f"Upload processing failed: {str(e)}")


@router.post("/upload/paste")
async def upload_paste(
    req: PasteRequest,
    user: AuthUser = Depends(get_current_user),
):
    try:
        import io
        df = pd.read_csv(io.StringIO(req.csv_text))
        df.columns = [str(c).strip() for c in df.columns]
        if len(df) > 1_000_000:
            raise HTTPException(status_code=413, detail="Pasted data too large.")

        session_id = str(uuid.uuid4())
        session    = DatasetSession(df=df, filename=req.filename,
                                    owner_id=user.user_id)    # ← stamped
        save_session(session_id, session)
        schema_suggestions = infer_schema_suggestions(df)

        # Auto-trigger AI orchestrator - non-fatal if it fails
        ai_insights = None
        try:
            from services.ai_orchestrator import orchestrate_ai_analysis
            ai_insights = await run_in_threadpool(
                orchestrate_ai_analysis, df, req.filename, None
            )
        except Exception as oe:
            logger.warning(f"Paste upload: orchestrator failed (non-fatal): {oe}")

        return JSONResponse({
            "session_id":         session_id,
            "filename":           req.filename,
            "rows":               len(df),
            "columns":            list(df.columns),
            "preview":            safe_preview(df),
            "schema_suggestions": schema_suggestions,
            "ai_insights":        ai_insights,
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not parse pasted CSV: {e}")
