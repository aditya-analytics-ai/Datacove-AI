"""
Analysis routes - profiling, issue detection, health score, anomalies,
AI suggestions, dataset summary, NL commands, and dataset comparison.
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from typing import Any, Dict, List
from models.dataset_session import get_session
from services.profiling_engine import profile_dataset
from services.issue_detector import detect_issues
from services.health_score import calculate_health_score
from services.anomaly_detector import detect_anomalies
from services.ai_suggestions import get_ai_suggestions
from services.nl_query_engine import parse_command
from utils.logger import logger
from utils.explainability import enrich_suggestions
from utils.preview import safe_preview, ext_to_object
from utils.auth import get_current_user, AuthUser
from utils.session_guard import require_session


router = APIRouter(dependencies=[Depends(get_current_user)])


class SessionRequest(BaseModel):
    session_id: str


class NLCommandRequest(BaseModel):
    session_id: str
    command: str


class CompareRequest(BaseModel):
    session_id_a: str
    session_id_b: str




@router.post("/profile")
async def profile(req: SessionRequest):
    """Return full dataset profile (with smart sampling on large datasets)."""
    try:
        session = require_session(req.session_id)
        df      = session.df_current
        logger.info(f"Profile: session={req.session_id} rows={len(df):,}")
        from services.performance import profile_with_sampling, performance_context
        result = await run_in_threadpool(profile_with_sampling, df, profile_dataset)
        result["performance"] = performance_context(df)
        return JSONResponse(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Profile failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze")
async def analyze(req: SessionRequest):
    """Return issues + health score + anomalies + AI suggestions."""
    try:
        session     = require_session(req.session_id)
        df          = session.df_current
        prof        = await run_in_threadpool(profile_dataset, df)
        issues      = await run_in_threadpool(detect_issues, df)
        health      = await run_in_threadpool(calculate_health_score, df, issues)
        anomalies   = await run_in_threadpool(detect_anomalies, df)
        suggestions = await run_in_threadpool(get_ai_suggestions, prof, issues, df)
        # Enrich with explanations (what/why/confidence)
        suggestions = enrich_suggestions(suggestions, prof)
        # AI Safety gate: score & validate every suggestion before returning
        from services.ai_safety import gate_all, split_by_gate
        gated = gate_all(suggestions, df, prof)
        auto_apply, needs_confirm, blocked = split_by_gate(gated)
        # Cache health score in session so /summary can return it cheaply
        session.metadata["last_health"] = health
        logger.info(
            f"Analyze: session={req.session_id} score={health['score']} issues={len(issues)} "
            f"suggestions={len(gated)} (auto={len(auto_apply)} confirm={len(needs_confirm)} blocked={len(blocked)})"
        )
        return JSONResponse({
            "profile":          prof,
            "issues":           issues,
            "health":           health,
            "anomalies":        anomalies,
            "suggestions":      gated,          # all suggestions with gate metadata
            "auto_apply":       auto_apply,     # safe to apply immediately
            "needs_confirm":    needs_confirm,  # require user review
            "blocked":          blocked,        # invalid or very low confidence
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analyze failed for session={req.session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def summary(session_id: str):
    """
    Lightweight summary suitable for polling after every transform.
    Returns only cheap metadata - does NOT run detect_issues or calculate_health_score.
    Those are reserved for the explicit /analyze endpoint.

    Returns 202 (not ready) instead of 404 during the brief window between
    upload completion and session persistence so the frontend doesn't log errors.
    """
    try:
        from models.dataset_session import get_session as _gs
        session = _gs(session_id)
        if session is None:
            # Session not yet persisted - return a "not ready" response the
            # client can silently retry rather than a 404 that fills the console.
            return JSONResponse({"session_id": session_id, "ready": False}, status_code=202)
        df      = session.df_current
        # Return the cached health score from session metadata if available
        # (populated by the last /analyze call) so the UI can still show it.
        cached_health = session.metadata.get("last_health")
        return JSONResponse({
            "session_id":   session_id,
            "filename":     session.filename,
            "rows":         len(df),
            "columns":      len(df.columns),
            "column_names": list(df.columns),
            "health":       cached_health,
            "top_issues":   [],
            "history_len":  len(session.history),
            "versions":     len(session.versions),
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Summary failed for session={session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compare")
async def compare(req: CompareRequest):
    """Compare two dataset sessions - column/row/cell-level diffs."""
    try:
        session_a = require_session(req.session_id_a)
        session_b = require_session(req.session_id_b)
        df_a = session_a.df_current.copy()
        df_b = session_b.df_current.copy()

        cols_a = set(df_a.columns)
        cols_b = set(df_b.columns)
        added_columns   = sorted(cols_b - cols_a)
        removed_columns = sorted(cols_a - cols_b)
        common_columns  = sorted(cols_a & cols_b)

        df_a_c = ext_to_object(df_a[common_columns]).fillna("__NA__").astype(str)
        df_b_c = ext_to_object(df_b[common_columns]).fillna("__NA__").astype(str)

        key_a  = df_a_c.apply(tuple, axis=1)
        key_b  = df_b_c.apply(tuple, axis=1)
        set_a  = set(key_a)
        set_b  = set(key_b)

        def tuples_to_records(tuples, cols):
            return [dict(zip(cols, t)) for t in list(tuples)[:200]]

        new_rows     = tuples_to_records(set_b - set_a, common_columns)
        removed_rows = tuples_to_records(set_a - set_b, common_columns)

        df_a_c = df_a_c.reset_index(drop=True)
        df_b_c = df_b_c.reset_index(drop=True)

        changed_values: List[Dict[str, Any]] = []
        for idx in range(min(len(df_a_c), len(df_b_c))):
            row_a = df_a_c.iloc[idx]
            row_b = df_b_c.iloc[idx]
            for col in common_columns:
                if row_a[col] != row_b[col]:
                    changed_values.append({"row": idx, "column": col,
                                            "value_a": row_a[col], "value_b": row_b[col]})
            if len(changed_values) >= 500:
                break

        return JSONResponse({
            "added_columns":      added_columns,
            "removed_columns":    removed_columns,
            "row_count_a":        len(df_a),
            "row_count_b":        len(df_b),
            "row_count_delta":    len(df_b) - len(df_a),
            "new_rows_count":     len(set_b - set_a),
            "removed_rows_count": len(set_a - set_b),
            "new_rows":           new_rows,
            "removed_rows":       removed_rows,
            "changed_values":     changed_values,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Compare failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/nl-command")
async def nl_command(req: NLCommandRequest):
    """Parse a natural-language cleaning command into a structured action."""
    try:
        session = require_session(req.session_id)
        logger.info(f"NL command: '{req.command}' session={req.session_id}")
        result  = await run_in_threadpool(parse_command, req.command, list(session.df_current.columns))
        return JSONResponse(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"NL command failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Correlation ────────────────────────────────────────────────────────────────
from services.correlation_engine import detect_correlations  # noqa

class CorrelationRequest(BaseModel):
    session_id: str
    method:    str   = "auto"
    threshold: float = 0.3

@router.post("/correlations")
async def correlations(req: CorrelationRequest):
    """Pearson / Spearman / Cramér's V correlation heatmap."""
    try:
        session = require_session(req.session_id)
        result  = await run_in_threadpool(detect_correlations, session.df_current, req.method, req.threshold)
        return JSONResponse(result)
    except HTTPException: raise
    except ValueError as e: raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Correlations failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Referential integrity ──────────────────────────────────────────────────────
from services.referential_integrity import check_referential_integrity  # noqa

@router.post("/referential-integrity")
async def referential_integrity(req: SessionRequest):
    """Auto-detect PK/FK columns; flag orphaned values, duplicate PKs, null FKs."""
    try:
        session = require_session(req.session_id)
        result  = await run_in_threadpool(check_referential_integrity, session.df_current)
        return JSONResponse(result)
    except HTTPException: raise
    except Exception as e:
        logger.error(f"Referential integrity failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Column similarity ─────────────────────────────────────────────────────────
from services.column_similarity import find_similar_columns  # noqa

@router.post("/column-similarity")
async def column_similarity(req: SessionRequest):
    """Detect semantically similar columns and suggest merges / drops."""
    try:
        session = require_session(req.session_id)
        result  = await run_in_threadpool(find_similar_columns, session.df_current)
        return JSONResponse(result)
    except HTTPException: raise
    except Exception as e:
        logger.error(f"Column similarity failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Time-series anomaly detection ──────────────────────────────────────────────
from services.timeseries_anomaly import detect_timeseries_anomalies  # noqa

class TimeseriesRequest(BaseModel):
    session_id: str
    date_col:   str   = None
    value_cols: list  = None
    period:     int   = None

@router.post("/anomalies/timeseries")
async def timeseries_anomalies(req: TimeseriesRequest):
    """STL decomposition time-series anomaly detection."""
    try:
        session = require_session(req.session_id)
        result  = await run_in_threadpool(
            detect_timeseries_anomalies,
            session.df_current,
            req.date_col,
            req.value_cols,
            req.period,
        )
        return JSONResponse(result)
    except HTTPException: raise
    except Exception as e:
        logger.error(f"TS anomalies failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Pattern library ────────────────────────────────────────────────────────────
from services.pattern_library import list_patterns, validate_column as _validate_col, test_value  # noqa
from pydantic import BaseModel as _BM

class PatternValidateRequest(BaseModel):
    session_id:   str
    column:       str
    pattern_name: str

class PatternTestRequest(BaseModel):
    value:        str
    pattern_name: str

@router.get("/patterns")
async def get_patterns():
    """Return all 50+ named patterns from the pattern library."""
    return JSONResponse({"patterns": list_patterns()})

@router.post("/patterns/validate")
async def pattern_validate(req: PatternValidateRequest):
    """Validate a column against a named pattern."""
    try:
        session = require_session(req.session_id)
        result  = await run_in_threadpool(_validate_col, session.df_current, req.column, req.pattern_name)
        return JSONResponse(result)
    except HTTPException: raise
    except ValueError as e: raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Pattern validate failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/patterns/test")
async def pattern_test(req: PatternTestRequest):
    """Test a single value against a named pattern."""
    try:
        return JSONResponse(test_value(req.value, req.pattern_name))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))