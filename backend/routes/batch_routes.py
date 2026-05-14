"""
batch_routes.py - Multi-file batch cleaning endpoints.

Migrated from new_routes.py (was tagged "V3 Features") to give batch
its own ownership and proper tag in the API docs.

POST /batch/upload     - upload multiple CSV files
POST /batch/run        - apply a transform pipeline to all files
GET  /batch/download   - download all cleaned files as a ZIP
"""

from __future__ import annotations
import io
import time
import zipfile
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from utils.auth import get_current_user

router = APIRouter(prefix="/batch", dependencies=[Depends(get_current_user)])

# In-memory batch store with TTL eviction
_batch_store: Dict[str, Dict[str, Any]] = {}
_BATCH_TTL_SECONDS = 3600  # 1 hour
_MAX_BATCH_COUNT = 50


def _evict_expired():
    """Remove expired batches and enforce max size limit."""
    now = time.time()
    expired = [
        k
        for k, v in _batch_store.items()
        if now - v.get("_created_at", 0) > _BATCH_TTL_SECONDS
    ]
    for k in expired:
        del _batch_store[k]
    while len(_batch_store) > _MAX_BATCH_COUNT:
        oldest = min(_batch_store, key=lambda k: _batch_store[k].get("_created_at", 0))
        del _batch_store[oldest]


class BatchRunRequest(BaseModel):
    batch_id: str
    pipeline: List[Dict[str, Any]]  # [{action, params}, ...]
    session_id: Optional[str] = None  # optional: copy schema from existing session


@router.post("/upload")
async def batch_upload(files: List[UploadFile] = File(...)):
    """
    Upload multiple CSV/Excel files for batch processing.
    Returns a batch_id and file manifest.
    """
    import uuid
    import pandas as pd

    _evict_expired()

    batch_id = str(uuid.uuid4())
    manifest = []
    dfs: Dict[str, Any] = {}

    for f in files:
        raw = await f.read()
        try:
            if f.filename.endswith((".xlsx", ".xls")):
                df = pd.read_excel(io.BytesIO(raw))
            else:
                df = pd.read_csv(io.BytesIO(raw))
            dfs[f.filename] = df
            manifest.append(
                {
                    "filename": f.filename,
                    "rows": len(df),
                    "columns": list(df.columns),
                    "status": "ready",
                }
            )
        except Exception as e:
            manifest.append(
                {
                    "filename": f.filename,
                    "status": "error",
                    "error": str(e),
                }
            )

    _batch_store[batch_id] = {
        "dfs": dfs,
        "cleaned": {},
        "manifest": manifest,
        "_created_at": time.time(),
    }
    return JSONResponse({"batch_id": batch_id, "files": manifest})


@router.post("/run")
async def batch_run(req: BatchRunRequest):
    """
    Apply a transformation pipeline to all files in a batch.
    Returns per-file results.
    """
    from services.cleaning_engine import apply_transformation

    _evict_expired()

    if req.batch_id not in _batch_store:
        raise HTTPException(status_code=404, detail="Batch not found.")

    batch = _batch_store[req.batch_id]
    results = []

    for filename, df in batch["dfs"].items():
        errors = []
        for step in req.pipeline:
            action = step.get("action")
            params = dict(step.get("params", {}))
            try:
                df = await run_in_threadpool(apply_transformation, df, action, params)
            except Exception as e:
                errors.append({"action": action, "error": str(e)})

        batch["cleaned"][filename] = df
        results.append(
            {
                "filename": filename,
                "rows": len(df),
                "columns": list(df.columns),
                "errors": errors,
                "status": "done" if not errors else "done_with_errors",
            }
        )

    return JSONResponse({"batch_id": req.batch_id, "results": results})


@router.get("/download")
def batch_download(batch_id: str):
    """
    Download all cleaned files in the batch as a ZIP archive.
    """
    _evict_expired()

    if batch_id not in _batch_store:
        raise HTTPException(status_code=404, detail="Batch not found.")

    batch = _batch_store[batch_id]
    cleaned = batch.get("cleaned", {})

    if not cleaned:
        raise HTTPException(
            status_code=400, detail="No cleaned files yet. Run /batch/run first."
        )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, df in cleaned.items():
            csv_bytes = df.to_csv(index=False).encode("utf-8")
            base = filename.rsplit(".", 1)[0]
            zf.writestr(f"{base}_cleaned.csv", csv_bytes)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="batch_{batch_id[:8]}_cleaned.zip"'
        },
    )
