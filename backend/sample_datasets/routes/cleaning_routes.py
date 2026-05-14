"""
Cleaning routes - apply transformations and auto-clean.

Updated to use HistoryEntry.history_as_list() and fixed undo to use stored snapshot.
"""
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from models.dataset_session import get_session, save_version, persist_dataset
from services.cleaning_engine import apply_transformation, auto_clean, auto_clean_explained
from services.audit_log import record as audit_record
from utils.logger import logger
from utils.preview import safe_preview
from utils.auth import get_current_user, AuthUser
from utils.session_guard import require_session
from utils.explainability import explain_action
from utils.request_validator import RequestValidator

router = APIRouter(dependencies=[Depends(get_current_user)])


class CleanRequest(BaseModel):
    session_id: str
    action: str
    params: Dict[str, Any] = {}


class AutoCleanRequest(BaseModel):
    session_id: str


class UndoRequest(BaseModel):
    session_id: str



def _df_preview(df, n: int = 100):
    return safe_preview(df, n)


@router.post("/clean")
async def clean(req: CleanRequest):
    """Apply a single transformation to the current dataset."""
    try:
        session   = require_session(req.session_id)
        # Validate at API boundary before touching any service
        RequestValidator(
            session_id=req.session_id,
            action=req.action,
            params=req.params,
            df_columns=list(session.df_current.columns),
        ).run()
        df_before = session.df_current.copy()
        logger.info(f"Clean: action='{req.action}' params={req.params} session={req.session_id}")
        version = len(session.versions) + 1
        session.versions.append(save_version(req.session_id, df_before, version))
        df_after = await run_in_threadpool(apply_transformation, session.df_current, req.action, req.params)
        session.push_history(df_before, req.action, req.params)
        session.df_current = df_after
        persist_dataset(req.session_id, df_after, session.filename)
        audit_entry = audit_record(req.session_id, req.action, req.params, df_before, df_after)
        explanation = explain_action(
            action=req.action,
            column=req.params.get("column"),
            rows_affected=abs(len(df_before) - len(df_after)),
            params=req.params,
            status="applied",
        ).to_dict()
        return JSONResponse({
            "success":     True,
            "rows":        len(df_after),
            "columns":     list(df_after.columns),
            "preview":     _df_preview(df_after),
            "history":     session.history_as_list(),
            "audit_entry": audit_entry.to_dict(),
            "explanation": explanation,
        })
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as e:
        logger.error(f"Clean failed for session={req.session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auto-clean")
async def auto_clean_endpoint(req: AutoCleanRequest):
    """Apply the complete safe cleaning suite automatically."""
    try:
        session   = require_session(req.session_id)
        df_before = session.df_current.copy()
        logger.info(f"Auto-clean: session={req.session_id}")
        version = len(session.versions) + 1
        session.versions.append(save_version(req.session_id, df_before, version))
        result   = await run_in_threadpool(auto_clean_explained, session.df_current)
        df_after = result["df"]
        session.push_history(df_before, "auto_clean", {"summary": result["summary"]})
        session.df_current = df_after
        persist_dataset(req.session_id, df_after, session.filename)
        logger.info(f"Auto-clean: session={req.session_id} summary={result['summary']!r}")
        return JSONResponse({
            "success":       True,
            "rows":          len(df_after),
            "columns":       list(df_after.columns),
            "preview":       _df_preview(df_after),
            "summary":       result["summary"],
            "steps":         result["steps"],
            "version_saved": version,
            "history":       session.history_as_list(),
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Auto-clean failed for session={req.session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/undo")
def undo(req: UndoRequest):
    """Undo the last cleaning action using stored snapshot."""
    try:
        session = require_session(req.session_id)
        entry = session.pop_history()
        if entry is None:
            raise HTTPException(status_code=400, detail="Nothing to undo.")
        if entry.df_snapshot is None:
            raise HTTPException(status_code=400,
                                detail="Snapshot for this action has been evicted (too far back).")
        session.df_current = entry.df_snapshot
        persist_dataset(req.session_id, entry.df_snapshot, session.filename)
        logger.info(f"Undo: reverted '{entry.action}' for session={req.session_id}")
        return JSONResponse({
            "success": True,
            "undone":  entry.action,
            "rows":    len(session.df_current),
            "columns": list(session.df_current.columns),
            "preview": _df_preview(session.df_current),
            "history": session.history_as_list(),
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Undo failed for session={req.session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset")
def reset(req: UndoRequest):
    """Reset dataset to the original uploaded version."""
    try:
        session = require_session(req.session_id)
        session.df_current = session.df_original.copy()
        session.history.clear()
        persist_dataset(req.session_id, session.df_current, session.filename)
        logger.info(f"Reset: session={req.session_id}")
        return JSONResponse({
            "success": True,
            "rows":    len(session.df_current),
            "columns": list(session.df_current.columns),
            "preview": _df_preview(session.df_current),
            "history": [],
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reset failed for session={req.session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class CellEditRequest(BaseModel):
    session_id: str
    row_index: int
    column: str
    value: Any
    propagate: bool = False   # apply to ALL matching rows


@router.post("/edit-cell")
async def edit_cell(req: CellEditRequest):
    """Edit a single cell (or propagate the fix to all matching values)."""
    try:
        session = require_session(req.session_id)
        df = session.df_current
        if req.column not in df.columns:
            raise HTTPException(status_code=400, detail=f"Column '{req.column}' not found.")
        if req.row_index < 0 or req.row_index >= len(df):
            raise HTTPException(status_code=400, detail=f"Row index {req.row_index} out of range.")

        # Save undo snapshot
        df_before = df.copy()
        version = len(session.versions) + 1
        session.versions.append(save_version(req.session_id, df_before, version))

        old_value = df.at[req.row_index, req.column]

        if req.propagate and old_value is not None:
            # Replace ALL cells in this column that have the same value
            mask = df[req.column].astype(str) == str(old_value)
            count = int(mask.sum())
            df.loc[mask, req.column] = req.value
            action_desc = f"propagate_edit ({count} cells)"
        else:
            df.at[req.row_index, req.column] = req.value
            count = 1
            action_desc = "edit_cell"

        session.push_history(df_before, action_desc,
                             {"column": req.column, "row": req.row_index,
                              "old": str(old_value), "new": str(req.value)})
        session.df_current = df
        persist_dataset(req.session_id, df, session.filename)

        logger.info(f"Cell edit: col='{req.column}' row={req.row_index} "
                     f"propagate={req.propagate} ({count} cells) session={req.session_id}")

        return JSONResponse({
            "success":        True,
            "rows":           len(df),
            "columns":        list(df.columns),
            "preview":        _df_preview(df),
            "history":        session.history_as_list(),
            "cells_affected": count,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cell edit failed for session={req.session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class FixAllRequest(BaseModel):
    session_id: str
    suggestions: list   # [{action, column, params}, ...]


@router.post("/fix-all")
async def fix_all(req: FixAllRequest):
    """Apply a list of cleaning actions in sequence (Fix All from Insights panel)."""
    try:
        session = require_session(req.session_id)
        applied = []
        errors  = []

        for sug in req.suggestions:
            action = sug.get("action")
            params = sug.get("params", {})
            col    = sug.get("column")
            if col and "column" not in params:
                params = {**params, "column": col}
            try:
                df_before = session.df_current.copy()
                version   = len(session.versions) + 1
                session.versions.append(save_version(req.session_id, df_before, version))
                df_after  = await run_in_threadpool(
                    apply_transformation, session.df_current, action, params
                )
                session.push_history(df_before, action, params)
                session.df_current = df_after
                audit_record(req.session_id, action, params, df_before, df_after, triggered_by="ai")
                applied.append(action)
            except Exception as e:
                errors.append({"action": action, "error": str(e)})

        persist_dataset(req.session_id, session.df_current, session.filename)
        df = session.df_current

        return JSONResponse({
            "success":  True,
            "applied":  applied,
            "errors":   errors,
            "rows":     len(df),
            "columns":  list(df.columns),
            "preview":  _df_preview(df),
            "history":  session.history_as_list(),
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"fix-all failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))