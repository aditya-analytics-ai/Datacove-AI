"""
power_routes.py - new power-feature endpoints:

  POST /api/visualize      - auto-generate chart data for a session
  POST /api/pii/detect     - detect PII columns in the dataset
  POST /api/pii/mask       - mask PII in one or more columns
  POST /api/formula        - add a computed column from a formula expression
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from models.dataset_session import get_session, persist_dataset
from services.visualization_engine import generate_charts
from services.pii_detector import detect_pii_columns, mask_pii_column
from utils.logger import logger
from utils.preview import safe_preview
from utils.auth import get_current_user, AuthUser
from utils.session_guard import require_session

import pandas as pd
import numpy as np

router = APIRouter(dependencies=[Depends(get_current_user)])


# ── Visualization ─────────────────────────────────────────────────────────────


class SessionRequest(BaseModel):
    session_id: str


@router.post("/visualize")
async def visualize(req: SessionRequest, user: AuthUser = Depends(get_current_user)):
    """Auto-generate chart specs from the current dataset."""
    try:
        session = require_session(req.session_id, owner_id=user.user_id)
        logger.info(f"Visualize: session={req.session_id}")
        result = await run_in_threadpool(generate_charts, session.df_current)
        return JSONResponse(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Visualize failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── PII Detection ─────────────────────────────────────────────────────────────


@router.post("/pii/detect")
async def detect_pii(req: SessionRequest, user: AuthUser = Depends(get_current_user)):
    """Scan all columns and return PII candidates with confidence scores."""
    try:
        session = require_session(req.session_id, owner_id=user.user_id)
        logger.info(f"PII detect: session={req.session_id}")
        result = await run_in_threadpool(detect_pii_columns, session.df_current)
        return JSONResponse({"pii_columns": result, "count": len(result)})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PII detect failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── PII Masking ───────────────────────────────────────────────────────────────


class MaskRequest(BaseModel):
    session_id: str
    columns: List[Dict[str, str]]  # [{column, pii_type, strategy}, ...]


@router.post("/pii/mask")
async def mask_pii(req: MaskRequest, user: AuthUser = Depends(get_current_user)):
    """Apply PII masking to specified columns."""
    try:
        session = require_session(req.session_id, owner_id=user.user_id)
        df_before = session.df_current.copy()
        df = session.df_current.copy()

        masked_cols = []
        for item in req.columns:
            col = item.get("column")
            pii_type = item.get("pii_type", "")
            strategy = item.get("strategy", "redact")
            if col and col in df.columns:
                df[col] = mask_pii_column(df[col], pii_type, strategy)
                masked_cols.append(col)

        if not masked_cols:
            raise HTTPException(status_code=400, detail="No valid columns to mask.")

        session.push_history(df_before, "mask_pii", {"columns": req.columns})
        session.df_current = df
        persist_dataset(req.session_id, df, session.filename)

        logger.info(f"PII mask: cols={masked_cols} session={req.session_id}")
        return JSONResponse(
            {
                "success": True,
                "masked_cols": masked_cols,
                "rows": len(df),
                "columns": list(df.columns),
                "preview": safe_preview(df),
                "history": session.history_as_list(),
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PII mask failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Formula / Computed Columns ────────────────────────────────────────────────


class FormulaRequest(BaseModel):
    session_id: str
    new_column: str
    expression: str  # e.g. "price * quantity" or "age.fillna(0) * 2"


import ast
import re as _re
from utils.auth import AuthUser

# Safe builtins allowed in formula eval
_SAFE_GLOBALS = {
    "__builtins__": {},
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "len": len,
    "str": str,
    "int": int,
    "float": float,
    "pd": pd,
    "np": np,
}


def _validate_expr_syntax(expr: str) -> bool:
    """Validate expression using AST - reject any statement-level nodes."""
    try:
        tree = ast.parse(expr, mode="eval")
        for node in ast.walk(tree):
            if isinstance(
                node,
                (
                    ast.stmt,
                    ast.FunctionDef,
                    ast.ClassDef,
                    ast.Lambda,
                    ast.Yield,
                    ast.YieldFrom,
                    ast.comprehension,
                    ast.Try,
                    ast.With,
                ),
            ):
                return False
        return True
    except SyntaxError:
        return False


def _sanitize_name(col: str) -> str:
    """Convert any column name to a valid Python identifier."""
    s = _re.sub(r"[^a-zA-Z0-9_]", "_", col)
    if s and s[0].isdigit():
        s = "_" + s
    return s or "_col"


def _build_eval_ns(df: pd.DataFrame, expr: str):
    """
    Returns (local_namespace, processed_expression).
    Columns with invalid Python names (spaces, slashes, etc.) are mapped to
    sanitized equivalents, and those names are replaced in the expression.
    Sort replacements longest-first to avoid partial-match substitutions.
    """
    local_ns: dict = {"df": df, "pd": pd, "np": np}
    replacements: list = []

    for col in df.columns:
        san = _sanitize_name(col)
        local_ns[san] = df[col]
        if col != san:
            replacements.append((col, san))
        else:
            local_ns[col] = df[col]

    processed = expr
    for orig, san in sorted(replacements, key=lambda x: -len(x[0])):
        processed = processed.replace(orig, san)

    return local_ns, processed


class FormulaPreviewRequest(BaseModel):
    session_id: str
    expression: str
    preview_rows: int = 5


@router.post("/formula/preview")
async def preview_formula(
    req: FormulaPreviewRequest, user: AuthUser = Depends(get_current_user)
):
    """
    Dry-run a formula expression on the first N rows without saving.
    Returns preview values + detected output type + any error message.
    Used for live validation in the UI before the user clicks 'Add Column'.
    """
    try:
        session = require_session(req.session_id, owner_id=user.user_id)
        df = session.df_current.head(req.preview_rows).copy()

        expr = req.expression.strip()
        if not expr:
            return JSONResponse({"ok": False, "error": "Empty expression."})

        _BLOCKED = ["import", "__", "exec", "eval", "open", "os.", "sys.", "subprocess"]
        for kw in _BLOCKED:
            if kw in expr:
                return JSONResponse({"ok": False, "error": f"Blocked keyword: '{kw}'"})

        if not _validate_expr_syntax(expr):
            return JSONResponse({"ok": False, "error": "Invalid expression syntax."})

        def _eval():
            local_ns, processed_expr = _build_eval_ns(df, expr)
            return eval(processed_expr, _SAFE_GLOBALS, local_ns)  # noqa: S307

        result = await run_in_threadpool(_eval)

        # Build preview values
        if hasattr(result, "tolist"):
            preview_vals = [
                str(v) if not pd.isna(v) else "NaN" for v in result.tolist()
            ]
        elif hasattr(result, "__iter__") and not isinstance(result, str):
            preview_vals = [str(v) for v in list(result)]
        else:
            preview_vals = [str(result)] * len(df)

        # Detect output type
        import pandas as _pd

        try:
            series = _pd.Series(result)
            if _pd.api.types.is_numeric_dtype(series):
                out_type = "numeric"
            elif _pd.api.types.is_bool_dtype(series):
                out_type = "boolean"
            elif _pd.api.types.is_datetime64_any_dtype(series):
                out_type = "datetime"
            else:
                out_type = "text"
        except Exception:
            out_type = "unknown"

        return JSONResponse(
            {
                "ok": True,
                "preview_vals": preview_vals,
                "out_type": out_type,
                "row_count": len(df),
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@router.post("/formula")
async def add_formula_column(
    req: FormulaRequest, user: AuthUser = Depends(get_current_user)
):
    """
    Evaluate a pandas expression and add the result as a new column.
    The expression can reference any column by name.

    Examples:
      expression: "Price * Quantity"
      expression: "Age.fillna(0)"
      expression: "FirstName + ' ' + LastName"
      expression: "np.log1p(Revenue)"
    """
    try:
        session = require_session(req.session_id, owner_id=user.user_id)
        df = session.df_current

        new_col = req.new_column.strip()
        expr = req.expression.strip()

        if not new_col:
            raise HTTPException(status_code=400, detail="new_column name is required.")
        if not expr:
            raise HTTPException(status_code=400, detail="expression is required.")

        # Security: block dangerous keywords
        _BLOCKED = ["import", "__", "exec", "eval", "open", "os.", "sys.", "subprocess"]
        for kw in _BLOCKED:
            if kw in expr:
                raise HTTPException(
                    status_code=400,
                    detail=f"Expression contains blocked keyword: '{kw}'",
                )

        if not _validate_expr_syntax(expr):
            raise HTTPException(status_code=400, detail="Invalid expression syntax.")

        def _eval():
            local_ns, processed_expr = _build_eval_ns(df, expr)
            return eval(processed_expr, _SAFE_GLOBALS, local_ns)  # noqa: S307

        df_before = df.copy()
        result = await run_in_threadpool(_eval)

        df = df.copy()
        df[new_col] = result

        session.push_history(
            df_before, "formula_column", {"new_column": new_col, "expression": expr}
        )
        session.df_current = df
        persist_dataset(req.session_id, df, session.filename)

        logger.info(f"Formula col '{new_col}' = '{expr}' session={req.session_id}")
        return JSONResponse(
            {
                "success": True,
                "new_column": new_col,
                "expression": expr,
                "rows": len(df),
                "columns": list(df.columns),
                "preview": safe_preview(df),
                "history": session.history_as_list(),
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Formula column failed: {e}")
        raise HTTPException(status_code=400, detail=f"Formula error: {str(e)}")
