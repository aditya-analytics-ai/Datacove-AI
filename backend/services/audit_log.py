"""
Audit Log Service - production-grade change tracking for every transformation.

Every action applied to a dataset is recorded here with:
  - what changed (column, action, params)
  - how many rows/cells were affected
  - before/after sample values
  - timestamp and session context

Consumers:
  - cleaning_routes.py  → records each /clean call
  - pipeline_engine.py  → records each pipeline step
  - report_generator.py → exports the full audit trail
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


# ── Data classes ──────────────────────────────────────────────────────────────

class AuditEntry:
    """One immutable record of a transformation that was applied."""

    def __init__(
        self,
        session_id: str,
        action: str,
        params: Dict[str, Any],
        df_before: pd.DataFrame,
        df_after: pd.DataFrame,
        triggered_by: str = "user",        # "user" | "ai" | "pipeline" | "auto"
        ai_confidence: Optional[float] = None,
    ):
        self.entry_id    = str(uuid.uuid4())[:8]
        self.session_id  = session_id
        self.timestamp   = datetime.now(timezone.utc).isoformat()
        self.action      = action
        self.params      = params
        self.triggered_by = triggered_by
        self.ai_confidence = ai_confidence

        # ── Compute diff stats ────────────────────────────────────────────────
        col = params.get("column")

        self.rows_before   = len(df_before)
        self.rows_after    = len(df_after)
        self.rows_affected = abs(self.rows_before - self.rows_after)

        self.cols_before = list(df_before.columns)
        self.cols_after  = list(df_after.columns)
        self.cols_added   = [c for c in self.cols_after if c not in self.cols_before]
        self.cols_removed = [c for c in self.cols_before if c not in self.cols_after]

        self.cells_changed, self.sample_changes = _diff_cells(
            df_before, df_after, focus_col=col
        )

        self.issue_type = _infer_issue(action)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id":      self.entry_id,
            "session_id":    self.session_id,
            "timestamp":     self.timestamp,
            "action":        self.action,
            "params":        self.params,
            "triggered_by":  self.triggered_by,
            "ai_confidence": self.ai_confidence,
            "issue_type":    self.issue_type,
            # Row-level
            "rows_before":   self.rows_before,
            "rows_after":    self.rows_after,
            "rows_affected": self.rows_affected,
            # Column-level
            "cols_added":    self.cols_added,
            "cols_removed":  self.cols_removed,
            # Cell-level
            "cells_changed": self.cells_changed,
            "sample_changes": self.sample_changes,
            # Human summary
            "summary":       self._summary(),
        }

    def _summary(self) -> str:
        action_label = self.action.replace("_", " ").title()
        col = self.params.get("column")
        col_str = f" on '{col}'" if col else ""

        parts = []
        if self.rows_affected:
            delta = self.rows_before - self.rows_after
            verb  = "Removed" if delta > 0 else "Added"
            parts.append(f"{verb} {abs(delta):,} row(s)")
        if self.cells_changed:
            parts.append(f"Updated {self.cells_changed:,} cell(s)")
        if self.cols_added:
            parts.append(f"Added column(s): {', '.join(self.cols_added)}")
        if self.cols_removed:
            parts.append(f"Removed column(s): {', '.join(self.cols_removed)}")
        if not parts:
            parts.append("No data changed")

        return f"{action_label}{col_str}: {'; '.join(parts)}."


# ── In-memory store (keyed by session_id) ─────────────────────────────────────

_AUDIT_STORE: Dict[str, List[AuditEntry]] = {}


def record(
    session_id: str,
    action: str,
    params: Dict[str, Any],
    df_before: pd.DataFrame,
    df_after: pd.DataFrame,
    triggered_by: str = "user",
    ai_confidence: Optional[float] = None,
) -> AuditEntry:
    """
    Create and store an AuditEntry.  Always call this AFTER the transformation.
    Returns the entry so callers can include it in API responses.
    """
    entry = AuditEntry(
        session_id=session_id,
        action=action,
        params=params,
        df_before=df_before,
        df_after=df_after,
        triggered_by=triggered_by,
        ai_confidence=ai_confidence,
    )
    _AUDIT_STORE.setdefault(session_id, []).append(entry)
    return entry


def get_log(session_id: str) -> List[Dict[str, Any]]:
    """Return the full audit log for a session as a list of dicts."""
    return [e.to_dict() for e in _AUDIT_STORE.get(session_id, [])]


def clear_log(session_id: str) -> None:
    """Wipe the log for a session (e.g. on session reset)."""
    _AUDIT_STORE.pop(session_id, None)


def export_csv(session_id: str) -> str:
    """Return the audit log as a CSV string for download."""
    entries = get_log(session_id)
    if not entries:
        return "entry_id,timestamp,action,column,rows_affected,cells_changed,summary\n"

    rows = []
    for e in entries:
        col = e["params"].get("column", "")
        rows.append({
            "entry_id":      e["entry_id"],
            "timestamp":     e["timestamp"],
            "action":        e["action"],
            "column":        col,
            "triggered_by":  e["triggered_by"],
            "ai_confidence": e.get("ai_confidence", ""),
            "rows_before":   e["rows_before"],
            "rows_after":    e["rows_after"],
            "rows_affected": e["rows_affected"],
            "cells_changed": e["cells_changed"],
            "cols_added":    "|".join(e["cols_added"]),
            "cols_removed":  "|".join(e["cols_removed"]),
            "summary":       e["summary"],
        })

    df = pd.DataFrame(rows)
    return df.to_csv(index=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _diff_cells(
    before: pd.DataFrame,
    after: pd.DataFrame,
    focus_col: Optional[str] = None,
    max_samples: int = 5,
) -> tuple[int, List[Dict]]:
    """
    Compare two DataFrames cell-by-cell.
    Returns (total_cells_changed, sample_list).
    """
    # Only compare shared columns that exist in both frames
    shared_cols = [c for c in before.columns if c in after.columns]
    if focus_col and focus_col in shared_cols:
        # Prioritise the target column for sampling
        shared_cols = [focus_col] + [c for c in shared_cols if c != focus_col]

    n_rows = min(len(before), len(after))
    total_changed = 0
    samples: List[Dict] = []

    for col in shared_cols:
        b = before[col].iloc[:n_rows].fillna("__NULL__").astype(str).reset_index(drop=True)
        a = after[col].iloc[:n_rows].fillna("__NULL__").astype(str).reset_index(drop=True)
        mask = b != a
        changed = int(mask.sum())
        total_changed += changed

        if changed and len(samples) < max_samples:
            for idx in mask[mask].index[:max_samples - len(samples)]:
                bv = before[col].iloc[idx]
                av = after[col].iloc[idx]
                samples.append({
                    "column": col,
                    "row":    int(idx),
                    "before": None if (isinstance(bv, float) and np.isnan(bv)) else str(bv),
                    "after":  None if (isinstance(av, float) and np.isnan(av)) else str(av),
                })

    # Also count rows that disappeared (entire row drop)
    if len(after) < len(before):
        total_changed += (len(before) - len(after)) * len(shared_cols)

    return total_changed, samples


_ACTION_TO_ISSUE: Dict[str, str] = {
    "remove_duplicates":          "duplicate_rows",
    "fuzzy_remove_duplicates":    "duplicate_rows",
    "fill_missing":               "missing_values",
    "fill_missing_ffill":         "missing_values",
    "fill_missing_bfill":         "missing_values",
    "fill_missing_interpolate":   "missing_values",
    "trim_whitespace":            "extra_whitespace",
    "standardise_capitalisation": "capitalisation_inconsistency",
    "normalise_categories":       "category_inconsistency",
    "coerce_numeric":             "mixed_data_types",
    "flag_invalid_emails":        "invalid_email",
    "normalize_phone":            "invalid_phone",
    "standardise_dates":          "date_format",
    "standardise_mixed_dates":    "mixed_date_formats",
    "clip_outliers":              "outliers",
    "replace_outliers":           "outliers",
    "drop_column":                "schema_change",
    "drop_constant_columns":      "constant_column",
    "drop_high_missing_columns":  "high_missing",
    "strip_characters":           "encoding_garbage",
    "normalize_unicode":          "encoding",
    "cast_type":                  "type_mismatch",
    "scale_numeric":              "normalization",
    "bin_numeric":                "binning",
}


def _infer_issue(action: str) -> str:
    return _ACTION_TO_ISSUE.get(action, "transformation")
