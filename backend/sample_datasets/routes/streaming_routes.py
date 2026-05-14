"""
streaming_routes.py - SSE endpoints for large-file transforms.

POST /api/clean/stream      - single transform with live progress
POST /api/auto-clean/stream - full auto-clean suite with live progress

Events emitted:
  data: {"type":"progress","pct":42,"rows_done":21000,"total_rows":50000}
  data: {"type":"done","rows":50000,"columns":[...],"preview":[...]}
  data: {"type":"error","detail":"..."}

Small datasets (<STREAM_THRESHOLD rows) get the fast-path: one immediate
progress:100 + done event, no chunking overhead.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, AsyncGenerator, Dict

import pandas as pd
from fastapi import APIRouter, HTTPException, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import settings
from models.dataset_session import get_session, persist_dataset, save_version
from services.streaming_engine import (
    DEFAULT_CHUNK_SIZE, is_streamable,
    stream_auto_clean, stream_transform,
)
from utils.logger import logger
from utils.preview import safe_preview
from utils.auth import get_current_user, AuthUser
from utils.session_guard import require_session

router = APIRouter(dependencies=[Depends(get_current_user)])


class StreamCleanRequest(BaseModel):
    session_id: str
    action: str
    params: Dict[str, Any] = {}
    chunk_size: int = DEFAULT_CHUNK_SIZE


class StreamAutoCleanRequest(BaseModel):
    session_id: str
    chunk_size: int = DEFAULT_CHUNK_SIZE




def _sse(event: Dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _preview(df: "pd.DataFrame", n: int = 100) -> list:
    return safe_preview(df, n)


@router.post("/clean/stream")
async def stream_clean(req: StreamCleanRequest):
    """Stream a single transformation with SSE progress events."""
    session = require_session(req.session_id)

    # ── Fast path for small datasets ──────────────────────────────────────────
    if len(session.df_current) < settings.STREAM_THRESHOLD or not is_streamable(req.action):
        from services.cleaning_engine import apply_transformation
        df_before = session.df_current.copy()
        version = len(session.versions) + 1
        session.versions.append(save_version(req.session_id, df_before, version))
        df_after = await run_in_threadpool(apply_transformation, session.df_current, req.action, req.params)
        session.push_history(df_before, req.action, req.params)
        session.df_current = df_after
        persist_dataset(req.session_id, df_after, session.filename)

        async def _fast():
            yield _sse({"type": "progress", "pct": 100,
                        "rows_done": len(df_after), "total_rows": len(df_after)})
            yield _sse({"type": "done", "rows": len(df_after),
                        "columns": list(df_after.columns),
                        "preview": _preview(df_after),
                        "history": session.history_as_list()})
        return StreamingResponse(_fast(), media_type="text/event-stream")

    # ── Streaming path for large datasets ─────────────────────────────────────
    source_path = Path(persist_dataset(req.session_id, session.df_current, session.filename))
    df_before = session.df_current.copy()
    version = len(session.versions) + 1
    session.versions.append(save_version(req.session_id, df_before, version))
    # NOTE: push_history is called AFTER the transform succeeds (see _stream below)

    out_holder: list[str] = []

    async def _stream() -> AsyncGenerator[str, None]:
        def _run():
            return list(stream_transform(req.session_id, source_path,
                                         req.action, req.params, req.chunk_size))
        events = await run_in_threadpool(_run)
        for evt in events:
            if evt["type"] == "done":
                out_holder.append(evt["output_path"])
            else:
                yield _sse(evt)

        if out_holder:
            try:
                df_result = pd.read_csv(out_holder[0])
                # Push history only after successful transform - snapshot is correct
                session.push_history(df_before, req.action, req.params)
                session.df_current = df_result
                persist_dataset(req.session_id, df_result, session.filename)
                yield _sse({"type": "done", "rows": len(df_result),
                             "columns": list(df_result.columns),
                             "preview": _preview(df_result),
                             "history": session.history_as_list()})
                Path(out_holder[0]).unlink(missing_ok=True)
            except Exception as exc:
                yield _sse({"type": "error", "detail": str(exc)})

    return StreamingResponse(_stream(), media_type="text/event-stream")


@router.post("/auto-clean/stream")
async def stream_auto_clean_endpoint(req: StreamAutoCleanRequest):
    """Stream the full auto-clean suite with SSE progress events."""
    session = require_session(req.session_id)
    source_path = Path(persist_dataset(req.session_id, session.df_current, session.filename))
    df_before = session.df_current.copy()
    version = len(session.versions) + 1
    session.versions.append(save_version(req.session_id, df_before, version))

    out_holder: list[str] = []

    async def _stream() -> AsyncGenerator[str, None]:
        def _run():
            return list(stream_auto_clean(req.session_id, source_path, req.chunk_size))
        events = await run_in_threadpool(_run)
        for evt in events:
            if evt["type"] == "done":
                out_holder.append(evt["output_path"])
            else:
                yield _sse(evt)

        if out_holder:
            try:
                df_result = pd.read_csv(out_holder[0])
                # Push history only after successful transform (mirrors /clean/stream behaviour)
                session.push_history(df_before, "auto_clean_stream", {})
                session.df_current = df_result
                persist_dataset(req.session_id, df_result, session.filename)
                yield _sse({"type": "done", "rows": len(df_result),
                             "columns": list(df_result.columns),
                             "preview": _preview(df_result),
                             "message": "Auto-clean complete.",
                             "history": session.history_as_list()})
                Path(out_holder[0]).unlink(missing_ok=True)
            except Exception as exc:
                yield _sse({"type": "error", "detail": str(exc)})

    return StreamingResponse(_stream(), media_type="text/event-stream")