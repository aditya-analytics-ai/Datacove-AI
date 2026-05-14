"""
vocab_routes.py - Vocabulary mapping endpoints.

Migrated from new_routes.py (was tagged "V3 Features") to give vocab
its own ownership and proper tag in the API docs.

GET  /vocab/list       - list all built-in vocab dictionaries
POST /vocab/preview    - preview mapping of sample values
POST /vocab/apply      - apply vocab mapping to a column
"""
from __future__ import annotations
from typing import List

from fastapi import APIRouter, HTTPException, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from utils.auth import get_current_user, AuthUser
from utils.session_guard import require_session
from utils.preview import safe_preview
from models.dataset_session import save_version, persist_dataset

router = APIRouter(prefix="/vocab", dependencies=[Depends(get_current_user)])


@router.get("/list")
def vocab_list():
    """Return metadata for all built-in vocabulary dictionaries."""
    from services.vocab_mapper import VOCAB_META
    return JSONResponse({"vocabs": VOCAB_META})


class VocabPreviewRequest(BaseModel):
    values: List[str]
    vocab: str


@router.post("/preview")
def vocab_preview(req: VocabPreviewRequest):
    """Preview how a list of sample values would be mapped through a vocabulary."""
    from services.vocab_mapper import preview_mapping
    try:
        results = preview_mapping(req.values, req.vocab)
        return JSONResponse({"results": results})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class VocabApplyRequest(BaseModel):
    session_id: str
    column: str
    vocab: str
    unmapped: str = "keep"   # "keep" | "blank" | "error"


@router.post("/apply")
async def vocab_apply(req: VocabApplyRequest, user: AuthUser = Depends(get_current_user)):
    """Apply a vocabulary mapping to a column and record lineage."""
    from services.vocab_mapper import map_column_to_standard

    try:
        session   = require_session(req.session_id, user.user_id)
        df_before = session.df_current.copy()

        version = len(session.versions) + 1
        session.versions.append(save_version(req.session_id, df_before, version))

        df_after, stats = await run_in_threadpool(
            map_column_to_standard,
            df_before, req.column, req.vocab, req.unmapped,
        )

        session.push_history(df_before, "map_to_standard",
                             {"column": req.column, "vocab": req.vocab,
                              "unmapped": req.unmapped})
        session.df_current = df_after
        persist_dataset(req.session_id, df_after, session.filename)

        return JSONResponse({
            "success":  True,
            "stats":    stats,
            "rows":     len(df_after),
            "columns":  list(df_after.columns),
            "preview":  safe_preview(df_after),
            "history":  session.history_as_list(),
        })
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
