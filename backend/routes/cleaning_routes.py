"""
Cleaning routes - apply transformations and auto-clean.

Updated to use HistoryEntry.history_as_list() and fixed undo to use stored snapshot.
Enhanced with smart auto-clean and domain detection.
"""

from contextlib import asynccontextmanager, contextmanager
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from models.dataset_session import get_session, save_version, persist_dataset
from services.cleaning_engine import (
    apply_transformation,
    auto_clean,
    auto_clean_explained,
)
from services.audit_log import record as audit_record
from services.dataset_profiler import DatasetProfiler
from services.schema_inferrer import SchemaInferrer
from services.smart_auto_clean import SmartAutoClean
from utils.logger import logger
from utils.preview import safe_preview
from utils.auth import get_current_user, AuthUser
from utils.errors import (
    CleaningValidationError,
    PermissionDomainError,
    NotFoundDomainError,
    ValidationDomainError,
)
from utils.session_guard import require_session
from utils.explainability import explain_action
from utils.request_validator import RequestValidator
from schemas.cleaning_schema import AutoCleanRequest, UndoRequest

router = APIRouter(dependencies=[Depends(get_current_user)])


class CleanRequest(BaseModel):
    session_id: str
    action: str
    params: Dict[str, Any] = {}


def _df_preview(df, n: int = 100):
    return safe_preview(df, n)


def _translate_cleaning_error(exc: Exception) -> HTTPException:
    if isinstance(exc, CleaningValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, ValidationDomainError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, PermissionDomainError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, NotFoundDomainError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@asynccontextmanager
async def _cleaning_boundary(operation: str, session_id: str | None = None):
    try:
        yield
    except HTTPException:
        raise
    except Exception as exc:
        suffix = f" for session={session_id}" if session_id else ""
        logger.error(f"{operation} failed{suffix}: {exc}")
        raise _translate_cleaning_error(exc)


@contextmanager
def _cleaning_boundary_sync(operation: str, session_id: str | None = None):
    try:
        yield
    except HTTPException:
        raise
    except Exception as exc:
        suffix = f" for session={session_id}" if session_id else ""
        logger.error(f"{operation} failed{suffix}: {exc}")
        raise _translate_cleaning_error(exc)


@router.post("/clean")
async def clean(req: CleanRequest, user: AuthUser = Depends(get_current_user)):
    """Apply a single transformation to the current dataset."""
    async with _cleaning_boundary("Clean", req.session_id):
        session = require_session(req.session_id, owner_id=user.user_id)
        # Validate at API boundary before touching any service
        RequestValidator(
            session_id=req.session_id,
            action=req.action,
            params=req.params,
            df_columns=list(session.df_current.columns),
        ).run()
        df_before = session.df_current.copy()
        logger.info(
            f"Clean: action='{req.action}' params={req.params} session={req.session_id}"
        )
        version = len(session.versions) + 1
        session.versions.append(save_version(req.session_id, df_before, version))
        df_after = await run_in_threadpool(
            apply_transformation, session.df_current, req.action, req.params
        )
        session.push_history(df_before, req.action, req.params)
        session.df_current = df_after
        persist_dataset(req.session_id, df_after, session.filename)
        audit_entry = audit_record(
            req.session_id, req.action, req.params, df_before, df_after
        )
        explanation = explain_action(
            action=req.action,
            column=req.params.get("column"),
            rows_affected=abs(len(df_before) - len(df_after)),
            params=req.params,
            status="applied",
        ).to_dict()
        return JSONResponse(
            {
                "success": True,
                "rows": len(df_after),
                "columns": list(df_after.columns),
                "preview": _df_preview(df_after),
                "history": session.history_as_list(),
                "audit_entry": audit_entry.to_dict(),
                "explanation": explanation,
            }
        )


@router.post("/auto-clean")
async def auto_clean_endpoint(
    req: AutoCleanRequest, user: AuthUser = Depends(get_current_user)
):
    """Apply the complete safe cleaning suite automatically."""
    async with _cleaning_boundary("Auto-clean", req.session_id):
        session = require_session(req.session_id, owner_id=user.user_id)
        df_before = session.df_current.copy()
        logger.info(f"Auto-clean: session={req.session_id}")
        version = len(session.versions) + 1
        session.versions.append(save_version(req.session_id, df_before, version))
        result = await run_in_threadpool(auto_clean_explained, session.df_current)
        df_after = result["df"]
        session.push_history(df_before, "auto_clean", {"summary": result["summary"]})
        session.df_current = df_after
        persist_dataset(req.session_id, df_after, session.filename)
        logger.info(
            f"Auto-clean: session={req.session_id} summary={result['summary']!r}"
        )
        return JSONResponse(
            {
                "success": True,
                "rows": len(df_after),
                "columns": list(df_after.columns),
                "preview": _df_preview(df_after),
                "summary": result["summary"],
                "steps": result["steps"],
                "version_saved": version,
                "history": session.history_as_list(),
            }
        )


@router.post("/undo")
def undo(req: UndoRequest, user: AuthUser = Depends(get_current_user)):
    """Undo the last cleaning action using stored snapshot."""
    with _cleaning_boundary_sync("Undo", req.session_id):
        session = require_session(req.session_id, owner_id=user.user_id)
        entry = session.pop_history()
        if entry is None:
            return JSONResponse(
                {
                    "success": False,
                    "message": "Nothing to undo.",
                    "rows": len(session.df_current),
                    "columns": list(session.df_current.columns),
                    "preview": _df_preview(session.df_current),
                    "history": session.history_as_list(),
                }
            )
        if entry.df_snapshot is None:
            return JSONResponse(
                {
                    "success": False,
                    "message": "Snapshot for this action has been evicted (too far back).",
                    "rows": len(session.df_current),
                    "columns": list(session.df_current.columns),
                    "preview": _df_preview(session.df_current),
                    "history": session.history_as_list(),
                }
            )
        session.df_current = entry.df_snapshot
        persist_dataset(req.session_id, entry.df_snapshot, session.filename)
        logger.info(f"Undo: reverted '{entry.action}' for session={req.session_id}")
        return JSONResponse(
            {
                "success": True,
                "undone": entry.action,
                "rows": len(session.df_current),
                "columns": list(session.df_current.columns),
                "preview": _df_preview(session.df_current),
                "history": session.history_as_list(),
            }
        )


@router.post("/reset")
def reset(req: UndoRequest, user: AuthUser = Depends(get_current_user)):
    """Reset dataset to the original uploaded version."""
    with _cleaning_boundary_sync("Reset", req.session_id):
        session = require_session(req.session_id, owner_id=user.user_id)
        session.df_current = session.df_original.copy()
        session.history.clear()
        persist_dataset(req.session_id, session.df_current, session.filename)
        logger.info(f"Reset: session={req.session_id}")
        return JSONResponse(
            {
                "success": True,
                "rows": len(session.df_current),
                "columns": list(session.df_current.columns),
                "preview": _df_preview(session.df_current),
                "history": [],
            }
        )


class CellEditRequest(BaseModel):
    session_id: str
    row_index: int
    column: str
    value: Any
    propagate: bool = False  # apply to ALL matching rows


@router.post("/edit-cell")
async def edit_cell(req: CellEditRequest, user: AuthUser = Depends(get_current_user)):
    """Edit a single cell (or propagate the fix to all matching values)."""
    async with _cleaning_boundary("Edit cell", req.session_id):
        session = require_session(req.session_id, owner_id=user.user_id)
        df = session.df_current
        if req.column not in df.columns:
            raise ValidationDomainError(f"Column '{req.column}' not found.")
        if req.row_index < 0 or req.row_index >= len(df):
            raise ValidationDomainError(f"Row index {req.row_index} out of range.")

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

        session.push_history(
            df_before,
            action_desc,
            {
                "column": req.column,
                "row": req.row_index,
                "old": str(old_value),
                "new": str(req.value),
            },
        )
        session.df_current = df
        persist_dataset(req.session_id, df, session.filename)

        logger.info(
            f"Cell edit: col='{req.column}' row={req.row_index} "
            f"propagate={req.propagate} ({count} cells) session={req.session_id}"
        )

        return JSONResponse(
            {
                "success": True,
                "rows": len(df),
                "columns": list(df.columns),
                "preview": _df_preview(df),
                "history": session.history_as_list(),
                "cells_affected": count,
            }
        )


class FixAllRequest(BaseModel):
    session_id: str
    suggestions: list  # [{action, column, params}, ...]


@router.post("/fix-all")
async def fix_all(req: FixAllRequest, user: AuthUser = Depends(get_current_user)):
    """Apply a list of cleaning actions in sequence (Fix All from Insights panel)."""
    async with _cleaning_boundary("Fix all", req.session_id):
        session = require_session(req.session_id, owner_id=user.user_id)
        applied = []
        errors = []

        for sug in req.suggestions:
            action = sug.get("action")
            params = sug.get("params", {})
            col = sug.get("column")
            if col and "column" not in params:
                params = {**params, "column": col}
            try:
                df_before = session.df_current.copy()
                version = len(session.versions) + 1
                session.versions.append(
                    save_version(req.session_id, df_before, version)
                )
                df_after = await run_in_threadpool(
                    apply_transformation, session.df_current, action, params
                )
                session.push_history(df_before, action, params)
                session.df_current = df_after
                audit_record(
                    req.session_id,
                    action,
                    params,
                    df_before,
                    df_after,
                    triggered_by="ai",
                )
                applied.append(action)
            except Exception as e:
                errors.append({"action": action, "error": str(e)})

        persist_dataset(req.session_id, session.df_current, session.filename)
        df = session.df_current

        return JSONResponse(
            {
                "success": True,
                "applied": applied,
                "errors": errors,
                "rows": len(df),
                "columns": list(df.columns),
                "preview": _df_preview(df),
                "history": session.history_as_list(),
            }
        )


class BatchCleanRequest(BaseModel):
    session_id: str
    operations: list  # [{action, column, params}, ...]


@router.post("/smart-auto-clean")
async def smart_auto_clean_endpoint(
    req: AutoCleanRequest, user: AuthUser = Depends(get_current_user)
):
    """
    Apply intelligent auto-cleaning with domain detection.

    Detects the type of dataset (sales, customer, financial, etc.) and
    applies targeted cleaning strategies accordingly.

    intensity: 'gentle' (basic), 'standard' (recommended), or 'aggressive' (comprehensive)
    dry_run: If true, returns planned steps without applying
    """
    async with _cleaning_boundary("Smart auto-clean", req.session_id):
        session = require_session(req.session_id, owner_id=user.user_id)
        df_before = session.df_current.copy()
        logger.info(f"Smart auto-clean: session={req.session_id}")

        intensity = getattr(req, "intensity", "standard")
        dry_run = getattr(req, "dry_run", False)

        result = await run_in_threadpool(
            lambda: SmartAutoClean().clean(
                session.df_current, intensity=intensity, dry_run=dry_run
            )
        )

        if dry_run:
            return JSONResponse(
                {
                    "success": True,
                    "detected_domain": result.original_profile.domain_type,
                    "confidence": result.original_profile.domain_confidence,
                    "quality_score": result.original_profile.quality_score,
                    "planned_steps": len(result.steps),
                    "steps_summary": [
                        {
                            "action": s.action,
                            "reason": s.reason,
                            "affected_columns": s.affected_columns,
                            "skipped": s.skipped,
                        }
                        for s in result.steps
                    ],
                    "recommendations": result.recommended_next_steps,
                }
            )

        version = len(session.versions) + 1
        session.versions.append(save_version(req.session_id, df_before, version))

        session.push_history(
            df_before,
            "smart_auto_clean",
            {
                "summary": result.summary,
                "domain": result.original_profile.domain_type,
                "quality_improvement": result.quality_improvement,
            },
        )

        session.df_current = result.df
        persist_dataset(req.session_id, result.df, session.filename)

        logger.info(f"Smart auto-clean: session={req.session_id} {result.summary}")

        return JSONResponse(
            {
                "success": True,
                "rows": len(result.df),
                "columns": list(result.df.columns),
                "preview": _df_preview(result.df),
                "summary": result.summary,
                "detected_domain": result.original_profile.domain_type,
                "domain_confidence": result.original_profile.domain_confidence,
                "quality_score_before": result.original_profile.quality_score,
                "quality_score_after": result.original_profile.quality_score
                + result.quality_improvement,
                "quality_improvement": result.quality_improvement,
                "steps_applied": [
                    {
                        "action": s.action,
                        "reason": s.reason,
                        "cells_changed": s.cells_changed,
                        "rows_affected": abs(s.after_rows - s.before_rows),
                        "affected_columns": s.affected_columns,
                        "error": s.error,
                    }
                    for s in result.steps
                    if not s.skipped
                ],
                "recommended_next_steps": result.recommended_next_steps,
                "version_saved": version,
                "history": session.history_as_list(),
            }
        )


@router.get("/profile")
async def profile_dataset(session_id: str, user: AuthUser = Depends(get_current_user)):
    """
    Profile the current dataset - detect type, analyze columns, identify issues.

    Returns comprehensive analysis including:
    - Detected domain type (sales, customer, financial, etc.)
    - Column profiles (types, formats, quality)
    - Data quality issues
    - Cleaning recommendations
    """
    async with _cleaning_boundary("Profile", session_id):
        session = require_session(session_id, owner_id=user.user_id)

        profiler = DatasetProfiler()
        profile = profiler.profile(session.df_current)

        schema_inferrer = SchemaInferrer()
        type_suggestions = schema_inferrer.get_conversion_suggestions(
            session.df_current
        )

        return JSONResponse(
            {
                "success": True,
                "total_rows": profile.total_rows,
                "total_columns": profile.total_columns,
                "detected_domain": profile.domain_type,
                "domain_confidence": profile.domain_confidence,
                "quality_score": profile.quality_score,
                "issues": profile.issues,
                "column_profiles": {
                    col: {
                        "dtype": p.dtype,
                        "is_numeric": p.is_numeric,
                        "is_date": p.is_date,
                        "is_categorical": p.is_categorical,
                        "is_id": p.is_id,
                        "is_mixed_type": p.is_mixed_type,
                        "null_pct": p.null_pct,
                        "unique_count": p.unique_count,
                        "cardinality": p.cardinality,
                        "detected_format": p.detected_format,
                        "detected_category": p.detected_category,
                        "sample_values": p.sample_values[:5],
                    }
                    for col, p in profile.column_profiles.items()
                },
                "column_types": {
                    "numeric": profile.numeric_columns,
                    "date": profile.date_columns,
                    "categorical": profile.categorical_columns,
                    "text": profile.text_columns,
                    "id": profile.id_columns,
                },
                "type_suggestions": type_suggestions,
                "recommendations": profile.recommendations,
            }
        )


@router.get("/type-suggestions")
async def get_type_suggestions(
    session_id: str, user: AuthUser = Depends(get_current_user)
):
    """
    Get type conversion suggestions for the current dataset.

    Returns recommendations for converting columns to more appropriate types
    based on content analysis.
    """
    async with _cleaning_boundary("Type suggestions", session_id):
        session = require_session(session_id, owner_id=user.user_id)

        inferrer = SchemaInferrer()
        suggestions = inferrer.get_conversion_suggestions(session.df_current)

        return JSONResponse({"success": True, "suggestions": suggestions})


@router.get("/detect-domain")
async def detect_domain(session_id: str, user: AuthUser = Depends(get_current_user)):
    """
    Detect the domain/type of the current dataset.

    Returns the detected domain (sales, customer, financial, etc.)
    with confidence score.
    """
    async with _cleaning_boundary("Domain detection", session_id):
        session = require_session(session_id, owner_id=user.user_id)

        profiler = DatasetProfiler()
        profile = profiler.profile(session.df_current)

        return JSONResponse(
            {
                "success": True,
                "detected_domain": profile.domain_type,
                "confidence": profile.domain_confidence,
                "quality_score": profile.quality_score,
                "row_count": profile.total_rows,
                "column_count": profile.total_columns,
                "suggested_cleaning": [
                    {"action": r["action"], "reason": r.get("reason", "")}
                    for r in profile.recommendations[:5]
                ],
            }
        )


@router.post("/batch-clean")
async def batch_clean(
    req: BatchCleanRequest, user: AuthUser = Depends(get_current_user)
):
    """Apply multiple cleaning operations atomically (all succeed or all fail via rollback)."""
    async with _cleaning_boundary("Batch-clean", req.session_id):
        session = require_session(req.session_id, owner_id=user.user_id)
        df_before = session.df_current.copy()

        # 1. Validate ALL operations before applying any
        for op in req.operations:
            action = op.get("action")
            params = op.get("params", {})
            col = op.get("column")
            if col and "column" not in params:
                params = {**params, "column": col}
            RequestValidator(
                session_id=req.session_id,
                action=action,
                params=params,
                df_columns=list(session.df_current.columns),
            ).run()

        # 2. Save undo snapshot
        version = len(session.versions) + 1
        session.versions.append(save_version(req.session_id, df_before, version))

        # 3. Apply all operations sequentially to working copy
        df_working = df_before.copy()
        applied = []
        errors = []

        for op in req.operations:
            action = op.get("action")
            params = op.get("params", {})
            col = op.get("column")
            if col and "column" not in params:
                params = {**params, "column": col}
            try:
                df_working = await run_in_threadpool(
                    apply_transformation, df_working, action, params
                )
                applied.append({"action": action, "params": params})
            except Exception as e:
                errors.append({"action": action, "error": str(e)})

        # 4. If errors occurred, rollback entirely (atomic behavior)
        if errors:
            raise CleaningValidationError(
                f"Batch failed: {len(errors)} operation(s) failed. Rolled back. Errors: {errors}"
            )

        # 5. Apply to session and persist once
        session.df_current = df_working
        persist_dataset(req.session_id, df_working, session.filename)

        # 6. Record single audit entry for entire batch
        rows_affected = abs(len(df_before) - len(df_working))
        batch_desc = f"batch_clean ({len(applied)} operations)"
        session.push_history(
            df_before, batch_desc, {"count": len(applied), "operations": applied}
        )
        audit_record(
            req.session_id, batch_desc, {"operations": applied}, df_before, df_working
        )

        logger.info(
            f"Batch-clean: session={req.session_id} count={len(applied)} rows_affected={rows_affected}"
        )

        return JSONResponse(
            {
                "success": True,
                "operations": len(applied),
                "rows_affected": rows_affected,
                "columns": list(df_working.columns),
                "rows": len(df_working),
                "preview": _df_preview(df_working),
                "applied": applied,
                "history": session.history_as_list(),
            }
        )


# =============================================================================
# Deep Learning Cleaning System API
# =============================================================================


@router.get("/learning/status")
async def get_learning_status(user: AuthUser = Depends(get_current_user)):
    """Get the current learning system status and statistics."""
    async with _cleaning_boundary("Learning status"):
        from pathlib import Path
        import json

        reports_folder = Path("D:/datacove_out/cleaning_reports")
        summary_path = reports_folder / "summary.json"
        pattern_path = reports_folder / "pattern_analysis.json"

        status = {
            "learning_active": True,
            "datasets_processed": 0,
            "total_rules": 0,
            "avg_quality_score": 0,
            "last_updated": None,
        }

        if summary_path.exists():
            with open(summary_path) as f:
                summary = json.load(f)
                status["datasets_processed"] = summary.get("total_datasets", 0)
                status["total_rows"] = summary.get("total_rows_processed", 0)
                status["total_cells_cleaned"] = summary.get("total_cells_cleaned", 0)
                status["last_updated"] = summary.get("generated_at")
                quality = summary.get("quality_summary", {})
                status["avg_quality_score"] = quality.get("avg_final_quality", 0)
                status["domains"] = summary.get("domains_distribution", {})

        if pattern_path.exists():
            with open(pattern_path) as f:
                patterns = json.load(f)
                status["cleaning_actions"] = patterns.get("cleaning_actions", {})
                status["column_types"] = patterns.get("column_types", {})
                status["common_issues"] = patterns.get("top_issues", {})

        return JSONResponse(status)


@router.post("/learning/analyze")
async def analyze_dataset(file_path: str, user: AuthUser = Depends(get_current_user)):
    """Analyze a dataset and return detailed insights."""
    async with _cleaning_boundary("Learning analyze"):
        from services.deep_dataset_cleaner import DeepDatasetCleaner

        cleaner = DeepDatasetCleaner()
        report = cleaner.process_dataset(file_path)

        return JSONResponse(
            {
                "success": True,
                "filename": report.filename,
                "domain": report.detected_domain,
                "domain_confidence": report.domain_confidence,
                "quality_score": report.final_quality_score,
                "rows": report.total_rows,
                "columns": report.total_columns,
                "cells_cleaned": report.cells_cleaned,
                "issues_found": len(report.issues_found),
                "cleaning_steps": len(report.cleaning_steps),
                "column_insights": [
                    {
                        "column": ci.column,
                        "type": ci.detected_type,
                        "confidence": ci.confidence,
                        "has_issues": ci.has_issues,
                    }
                    for ci in report.column_insights
                ],
            }
        )


@router.get("/learning/rules")
async def get_learning_rules(
    domain: str = None, user: AuthUser = Depends(get_current_user)
):
    """Get learned cleaning rules, optionally filtered by domain."""
    async with _cleaning_boundary("Learning rules"):
        from pathlib import Path
        import json

        reports_folder = Path("D:/datacove_out/cleaning_reports")

        rules = []

        # Extract rules from pattern analysis
        pattern_path = reports_folder / "pattern_analysis.json"
        if pattern_path.exists():
            with open(pattern_path) as f:
                patterns = json.load(f)

            # Convert patterns to rules
            for action, count in patterns.get("cleaning_actions", {}).items():
                rules.append(
                    {
                        "action": action,
                        "times_applied": count,
                        "domain": domain or "all",
                        "confidence": min(
                            1.0, count / 100
                        ),  # Higher count = higher confidence
                    }
                )

        # Sort by confidence
        rules.sort(key=lambda x: -x["confidence"])

        if domain:
            rules = [r for r in rules if r["domain"] == domain]

        return JSONResponse(
            {
                "success": True,
                "total_rules": len(rules),
                "rules": rules,
            }
        )


@router.get("/learning/domains")
async def get_learning_domains(user: AuthUser = Depends(get_current_user)):
    """Get all detected domains and their statistics."""
    async with _cleaning_boundary("Learning domains"):
        from pathlib import Path
        import json

        reports_folder = Path("D:/datacove_out/cleaning_reports")
        summary_path = reports_folder / "summary.json"

        domains = {}

        if summary_path.exists():
            with open(summary_path) as f:
                summary = json.load(f)
                domains = summary.get("domains_distribution", {})

        # Add quality stats per domain
        domain_stats = {}
        for filepath in reports_folder.glob("report_*.json"):
            with open(filepath) as f:
                report = json.load(f)
                domain = report.get("detected_domain", "unknown")

                if domain not in domain_stats:
                    domain_stats[domain] = {
                        "count": 0,
                        "total_quality": 0,
                        "total_cells_cleaned": 0,
                    }

                domain_stats[domain]["count"] += 1
                domain_stats[domain]["total_quality"] += report.get(
                    "final_quality_score", 0
                )
                domain_stats[domain]["total_cells_cleaned"] += report.get(
                    "cells_cleaned", 0
                )

        # Calculate averages
        for domain, stats in domain_stats.items():
            if stats["count"] > 0:
                stats["avg_quality"] = stats["total_quality"] / stats["count"]
                stats["avg_cells_cleaned"] = (
                    stats["total_cells_cleaned"] / stats["count"]
                )

        return JSONResponse(
            {
                "success": True,
                "domains": domains,
                "domain_stats": domain_stats,
            }
        )


@router.get("/learning/patterns")
async def get_common_patterns(user: AuthUser = Depends(get_current_user)):
    """Get common patterns found across datasets."""
    async with _cleaning_boundary("Learning patterns"):
        from pathlib import Path
        import json

        reports_folder = Path("D:/datacove_out/cleaning_reports")
        pattern_path = reports_folder / "pattern_analysis.json"

        patterns = {
            "column_types": {},
            "common_issues": {},
            "data_types": {},
            "columns_with_nulls": {},
        }

        if pattern_path.exists():
            with open(pattern_path) as f:
                data = json.load(f)
                patterns["column_types"] = data.get("column_types", {})
                patterns["common_issues"] = data.get("top_issues", {})
                patterns["patterns"] = data.get("patterns", {})

        return JSONResponse(
            {
                "success": True,
                "patterns": patterns,
            }
        )


# =============================================================================
# Rule Learning System API
# =============================================================================


@router.post("/learning/learn-from-reports")
async def learn_from_reports(user: AuthUser = Depends(get_current_user)):
    """Trigger learning from all cleaning reports."""
    async with _cleaning_boundary("Learn from reports"):
        from services.rule_learner import learn_from_reports

        learner = learn_from_reports()
        return JSONResponse(
            {
                "success": True,
                "total_rules": len(learner.rules),
                "message": f"Learned {len(learner.rules)} rules from reports",
            }
        )


@router.get("/learning/rules/export")
async def export_rules(user: AuthUser = Depends(get_current_user)):
    """Export learned rules to a file."""
    async with _cleaning_boundary("Export rules"):
        from services.rule_learner import RuleLearner

        learner = RuleLearner()
        output_path = learner.export_rules(
            "D:/datacove_out/cleaning_reports/exported_rules.json"
        )

        return JSONResponse(
            {
                "success": True,
                "total_rules": len(learner.rules),
                "export_path": output_path,
            }
        )


@router.post("/learning/rules/import")
async def import_rules(file_path: str, user: AuthUser = Depends(get_current_user)):
    """Import rules from a file."""
    async with _cleaning_boundary("Import rules"):
        from services.rule_learner import RuleLearner

        learner = RuleLearner()
        imported = learner.import_rules(file_path)

        return JSONResponse(
            {
                "success": True,
                "rules_imported": imported,
                "total_rules": len(learner.rules),
            }
        )


@router.get("/learning/rules/suggest")
async def suggest_rules(
    domain: str, columns: str, user: AuthUser = Depends(get_current_user)
):
    """Get suggested rules based on domain and columns."""
    async with _cleaning_boundary("Suggest rules"):
        from services.rule_learner import RuleLearner

        learner = RuleLearner()
        col_list = columns.split(",")
        suggestions = learner.suggest_rules(domain, col_list)

        return JSONResponse(
            {
                "success": True,
                "domain": domain,
                "columns": col_list,
                "suggestions": suggestions,
            }
        )


@router.get("/learning/summary")
async def get_learning_summary(user: AuthUser = Depends(get_current_user)):
    """Get a comprehensive summary of the learning system."""
    async with _cleaning_boundary("Learning summary"):
        from services.rule_learner import RuleLearner
        from pathlib import Path
        import json

        learner = RuleLearner()

        summary = {
            "total_rules": len(learner.rules),
            "rules_by_confidence": {},
            "rules_by_action": {},
            "top_rules": [],
            "domains_covered": set(),
        }

        for rule in learner.rules.values():
            if rule.domain:
                summary["domains_covered"].add(rule.domain)

            action = rule.action
            if action not in summary["rules_by_action"]:
                summary["rules_by_action"][action] = 0
            summary["rules_by_action"][action] += 1

            conf_bucket = int(rule.confidence * 10) / 10
            conf_key = f"{conf_bucket:.0%}-{conf_bucket + 0.1:.0%}"
            if conf_key not in summary["rules_by_confidence"]:
                summary["rules_by_confidence"][conf_key] = 0
            summary["rules_by_confidence"][conf_key] += 1

        summary["top_rules"] = [
            {"pattern": r.pattern, "action": r.action, "confidence": r.confidence}
            for r in sorted(learner.rules.values(), key=lambda x: -x.confidence)[:20]
        ]
        summary["domains_covered"] = list(summary["domains_covered"])

        return JSONResponse(summary)


@router.post("/learning/auto-apply")
async def auto_apply_learned_rules(
    req: AutoCleanRequest, user: AuthUser = Depends(get_current_user)
):
    """Automatically apply learned cleaning rules to the current dataset."""
    async with _cleaning_boundary("Auto-apply learned rules", req.session_id):
        session = require_session(req.session_id, owner_id=user.user_id)
        from services.auto_applier import AutoRuleApplier
        from services.domain_rules import get_cleaner_for_domain

        domain = req.domain or "general"
        min_confidence = req.min_confidence if hasattr(req, "min_confidence") else 0.5

        df_before = session.df_current.copy()
        logger.info(
            f"Auto-apply learned rules: session={req.session_id} domain={domain}"
        )

        applier = AutoRuleApplier()
        df_after, report = applier.apply_rules_to_dataset(
            session.df_current, domain, min_confidence
        )

        if report["rules_applied"]:
            version = len(session.versions) + 1
            session.versions.append(save_version(req.session_id, df_before, version))
            session.push_history(
                df_before,
                "auto_apply_rules",
                {"domain": domain, "rules": len(report["rules_applied"])},
            )
            session.df_current = df_after
            persist_dataset(req.session_id, df_after, session.filename)

        logger.info(
            f"Auto-apply: session={req.session_id} rules_applied={len(report['rules_applied'])}"
        )

        return JSONResponse(
            {
                "success": True,
                "rows": len(df_after),
                "columns": list(df_after.columns),
                "preview": _df_preview(df_after),
                "rules_applied": report["rules_applied"],
                "total_cells_cleaned": report["cells_cleaned"],
                "changes": report["changes"][:10],
                "version_saved": len(session.versions)
                if report["rules_applied"]
                else None,
                "history": session.history_as_list(),
            }
        )
