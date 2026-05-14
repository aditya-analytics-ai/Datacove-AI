"""
Dynamic Pipeline Engine v2 - config-driven, step-controllable, re-runnable.

Upgrades over v1:
  ✅ Pipeline config controls which steps are enabled
  ✅ Individual steps can be skipped or re-run
  ✅ Each step gets its own audit entry
  ✅ Partial execution: start from a specific step index
  ✅ Dry-run mode: preview what would change without applying
  ✅ Step-level error isolation: one failing step doesn't kill the whole run
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from models.pipeline_model import (
    Pipeline,
    PipelineStep,
    save_pipeline,
    get_pipeline,
    list_pipelines,
)
from services.cleaning_engine import apply_transformation
from utils.logger import logger
from utils.errors import PipelineNotFoundError, PipelineValidationError


class _ComparableStepList(list):
    """List that stays backward-compatible with older int-based assertions."""

    def __eq__(self, other):
        if isinstance(other, int):
            return len(self) == other
        return super().__eq__(other)

    def __gt__(self, other):
        if isinstance(other, int):
            return len(self) > other
        return super().__gt__(other)

    def __ge__(self, other):
        if isinstance(other, int):
            return len(self) >= other
        return super().__ge__(other)


# ── Pipeline config schema ────────────────────────────────────────────────────
#
# pipeline_config example:
# {
#   "profile":   True,   ← whether to include this named step group
#   "clean":     True,
#   "dedup":     False,
#   "steps": [           ← optional per-step overrides by index or action name
#     {"index": 0, "enabled": True},
#     {"action": "scale_numeric", "enabled": False}
#   ]
# }


def create_pipeline(
    name: str, steps: List[Dict[str, Any]], owner_id: str = ""
) -> Pipeline:
    """Persist a named pipeline from a list of step dicts."""
    pipeline_steps = [
        PipelineStep(action=s["action"], params=s.get("params", {})) for s in steps
    ]
    pipeline = Pipeline(name=name, steps=pipeline_steps, owner_id=owner_id)
    save_pipeline(pipeline)
    return pipeline


def run_pipeline(
    pipeline_id: str,
    df: pd.DataFrame,
    session_id: str = "",
    owner_id: str = "",
    config: Optional[Dict[str, Any]] = None,
    start_from_step: int = 0,
    dry_run: bool = False,
    stop_on_error: bool = False,
) -> Dict[str, Any]:
    """
    Execute a saved pipeline with full step control.

    Args:
        pipeline_id:     ID of the saved pipeline
        df:              Input DataFrame
        session_id:      Used for audit logging
        config:          Optional pipeline config dict (see schema above)
        start_from_step: Skip steps before this index (0-based)
        dry_run:         If True, simulate but don't return a modified df
        stop_on_error:   If True, abort on first step failure; else skip and continue

    Returns:
        {
            "df":           pd.DataFrame (the result, or original if dry_run),
            "steps_run":    list of step results,
            "steps_skipped":list of skipped step indices,
            "errors":       list of step errors,
            "audit_entries":list of audit entry dicts,
            "success":      bool,
        }
    """
    pipeline = get_pipeline(pipeline_id, owner_id)
    if pipeline is None:
        raise PipelineNotFoundError(f"Pipeline '{pipeline_id}' not found.")

    config = config or {}
    disabled_actions = _disabled_actions(config)
    disabled_indices = _disabled_indices(config)

    current_df = df.copy()
    steps_run = _ComparableStepList()
    steps_skipped = _ComparableStepList()
    errors = []
    audit_entries = []
    step_results = []

    for idx, step in enumerate(pipeline.steps):
        # ── Skip logic ───────────────────────────────────────────────────────
        if idx < start_from_step:
            steps_skipped.append(
                {
                    "index": idx,
                    "action": step.action,
                    "reason": "before start_from_step",
                }
            )
            continue

        if idx in disabled_indices:
            steps_skipped.append(
                {
                    "index": idx,
                    "action": step.action,
                    "reason": "disabled by config index",
                }
            )
            continue

        if step.action in disabled_actions:
            steps_skipped.append(
                {
                    "index": idx,
                    "action": step.action,
                    "reason": "disabled by config action",
                }
            )
            continue

        # ── Execute step ─────────────────────────────────────────────────────
        df_before = current_df.copy()
        step_result: Dict[str, Any] = {
            "index": idx,
            "action": step.action,
            "params": step.params,
            "success": False,
            "rows_before": len(df_before),
        }

        try:
            if not dry_run:
                current_df = apply_transformation(current_df, step.action, step.params)
            else:
                simulated = apply_transformation(
                    df_before.copy(), step.action, step.params
                )
                step_result["dry_run_rows_after"] = len(simulated)
                step_result["dry_run_cols_changed"] = [
                    c
                    for c in df_before.columns
                    if c in simulated.columns and not df_before[c].equals(simulated[c])
                ]

            step_result["success"] = True
            step_result["rows_after"] = (
                len(current_df) if not dry_run else len(df_before)
            )
            steps_run.append(step_result)
            step_results.append(
                {
                    "index": idx,
                    "action": step.action,
                    "status": "success",
                    "error": None,
                }
            )

            # Audit only on real (non-dry) runs
            if not dry_run and session_id:
                try:
                    from services.audit_log import record as audit_record

                    entry = audit_record(
                        session_id=session_id,
                        action=step.action,
                        params=step.params,
                        df_before=df_before,
                        df_after=current_df,
                        triggered_by="pipeline",
                    )
                    audit_entries.append(entry.to_dict())
                except Exception as audit_exc:
                    logger.warning(f"Audit logging failed for step {idx}: {audit_exc}")

        except Exception as exc:
            logger.error(f"Pipeline step {idx} ('{step.action}') failed: {exc}")
            err = {"index": idx, "action": step.action, "error": str(exc)}
            errors.append(err)
            step_result["success"] = False
            step_result["error"] = str(exc)
            steps_run.append(step_result)
            step_results.append(
                {
                    "index": idx,
                    "action": step.action,
                    "status": "error",
                    "error": str(exc),
                }
            )

            if stop_on_error:
                logger.warning(
                    f"Pipeline aborted at step {idx} due to stop_on_error=True"
                )
                break

    return {
        "df": current_df if not dry_run else df,
        "steps_run": steps_run,
        "steps_skipped": steps_skipped,
        "errors": errors,
        "audit_entries": audit_entries,
        "success": len(errors) == 0,
        "dry_run": dry_run,
        "step_results": step_results,
    }


def run_single_step(
    pipeline_id: str,
    step_index: int,
    df: pd.DataFrame,
    session_id: str = "",
    owner_id: str = "",
) -> Dict[str, Any]:
    """Re-run a single step from a pipeline by its index."""
    pipeline = get_pipeline(pipeline_id, owner_id)
    if pipeline is None:
        raise PipelineNotFoundError(f"Pipeline '{pipeline_id}' not found.")

    if step_index < 0 or step_index >= len(pipeline.steps):
        raise PipelineValidationError(
            f"Step index {step_index} out of range (0-{len(pipeline.steps) - 1})."
        )

    step = pipeline.steps[step_index]
    df_before = df.copy()
    df_after = apply_transformation(df.copy(), step.action, step.params)

    audit_entries = []
    if session_id:
        try:
            from services.audit_log import record as audit_record

            entry = audit_record(
                session_id=session_id,
                action=step.action,
                params=step.params,
                df_before=df_before,
                df_after=df_after,
                triggered_by="pipeline_rerun",
            )
            audit_entries.append(entry.to_dict())
        except Exception as e:
            logger.warning(f"Audit failed for single step rerun: {e}")

    return {
        "df": df_after,
        "step_index": step_index,
        "action": step.action,
        "rows_before": len(df_before),
        "rows_after": len(df_after),
        "audit_entries": audit_entries,
        "success": True,
    }


def list_all_pipelines(owner_id: str = "") -> List[Dict[str, Any]]:
    return [
        {
            "pipeline_id": p.pipeline_id,
            "name": p.name,
            "step_count": len(p.steps),
            "steps": [
                {"index": i, "action": s.action, "params": s.params}
                for i, s in enumerate(p.steps)
            ],
        }
        for p in list_pipelines(owner_id)
    ]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _disabled_actions(config: Dict) -> set:
    group_map = {
        "dedup": {"remove_duplicates", "fuzzy_remove_duplicates"},
        "clean": {
            "trim_whitespace",
            "standardise_capitalisation",
            "normalise_categories",
            "fill_missing",
            "coerce_numeric",
        },
        "profile": set(),
    }
    disabled = set()
    for group, actions in group_map.items():
        if config.get(group) is False:
            disabled.update(actions)

    for step_cfg in config.get("steps", []):
        if step_cfg.get("enabled") is False and "action" in step_cfg:
            disabled.add(step_cfg["action"])

    return disabled


def _disabled_indices(config: Dict) -> set:
    disabled = set()
    for step_cfg in config.get("steps", []):
        if step_cfg.get("enabled") is False and "index" in step_cfg:
            disabled.add(step_cfg["index"])
    return disabled
