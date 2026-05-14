"""
explainability.py - Standard structure for all AI action explanations.

Every AI-driven action in the system returns an ExplainedAction so the
frontend can always show: what happened, why, and how confident the AI is.

Usage:
    from utils.explainability import explain_action, ExplainedAction

    result = explain_action(
        action="fill_missing",
        column="revenue",
        what="Filled 142 missing values using median imputation.",
        why="Column has 18% missing values. Median is robust to outliers "
            "in numeric revenue data.",
        confidence=0.88,
        rows_affected=142,
    )
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class ExplainedAction:
    action:        str                    # machine-readable action name
    column:        Optional[str]          # column targeted, or None for dataset-wide
    what:          str                    # plain-English description of what happened
    why:           str                    # reasoning behind the choice
    confidence:    float                  # 0.0-1.0
    rows_affected: int = 0               # number of rows changed
    cells_changed: int = 0               # number of cells changed
    params:        Dict[str, Any] = field(default_factory=dict)
    status:        str = "applied"        # applied | skipped | failed
    error:         Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["confidence_label"] = self._confidence_label()
        return d

    def _confidence_label(self) -> str:
        if self.confidence >= 0.90:
            return "high"
        if self.confidence >= 0.70:
            return "medium"
        return "low"


# ── Confidence heuristics per action ─────────────────────────────────────────
# Rule-based actions are deterministic → high confidence.
# AI-inferred actions get lower confidence unless strongly signalled.

_CONFIDENCE: Dict[str, float] = {
    "remove_duplicates":           0.97,
    "trim_whitespace":             0.97,
    "drop_column":                 0.75,
    "drop_constant_columns":       0.95,
    "drop_high_missing_columns":   0.85,
    "fill_missing":                0.82,
    "fill_missing_ffill":          0.78,
    "fill_missing_bfill":          0.78,
    "fill_missing_interpolate":    0.80,
    "coerce_numeric":              0.88,
    "standardise_capitalisation":  0.93,
    "normalise_categories":        0.80,
    "standardise_dates":           0.85,
    "standardise_mixed_dates":     0.82,
    "clip_outliers":               0.78,
    "replace_outliers":            0.72,
    "flag_invalid_emails":         0.95,
    "normalize_phone":             0.90,
    "strip_characters":            0.88,
    "normalize_unicode":           0.92,
    "find_replace":                0.90,
    "cast_type":                   0.83,
    "drop_rows_missing_threshold": 0.87,
}

_DEFAULT_CONFIDENCE = 0.72

# Human-readable what/why templates per action
_TEMPLATES: Dict[str, Dict[str, str]] = {
    "remove_duplicates": {
        "what": "Removed {rows_affected} duplicate row{s}.",
        "why":  "Exact duplicate rows add no information and inflate row counts, "
                "skewing aggregations and model training.",
    },
    "trim_whitespace": {
        "what": "Trimmed leading/trailing whitespace across {cells_changed} cell{s}.",
        "why":  "Extra whitespace causes silent mismatches in joins, filters, and "
                "categorical encodings.",
    },
    "fill_missing": {
        "what": "Filled {rows_affected} missing value{s} in '{column}' using {strategy}.",
        "why":  "Missing values block statistical analysis and model training. "
                "{strategy_reason}",
    },
    "coerce_numeric": {
        "what": "Converted '{column}' to numeric, marking {rows_affected} unparseable value{s} as NaN.",
        "why":  "Column contains mixed types. Coercing to numeric enables "
                "aggregations and model features.",
    },
    "standardise_capitalisation": {
        "what": "Standardised capitalisation in {cells_changed} cell{s}.",
        "why":  "Inconsistent capitalisation ('UK', 'uk', 'Uk') creates false "
                "category splits and inflates unique counts.",
    },
    "normalise_categories": {
        "what": "Normalised {cells_changed} category variant{s} across string columns.",
        "why":  "Category variants (spacing, punctuation, abbreviations) fragment "
                "groupings and reduce model accuracy.",
    },
    "drop_column": {
        "what": "Dropped column '{column}'.",
        "why":  "Column was identified as problematic (all-null, constant, or "
                "likely an ID with no analytical value).",
    },
    "clip_outliers": {
        "what": "Clipped {rows_affected} outlier{s} in '{column}'.",
        "why":  "Extreme values distort mean-based statistics and model gradients. "
                "IQR clipping retains the distribution shape.",
    },
    "standardise_dates": {
        "what": "Standardised date format in '{column}' ({rows_affected} value{s}).",
        "why":  "Inconsistent date formats prevent chronological sorting, "
                "date arithmetic, and time-series analysis.",
    },
    "flag_invalid_emails": {
        "what": "Flagged {rows_affected} invalid email address{es} in '{column}'.",
        "why":  "Invalid emails should be reviewed before use in outreach or "
                "identity resolution.",
    },
}

_STRATEGY_REASONS = {
    "median": "Median is robust to outliers - suitable for skewed numeric distributions.",
    "mean":   "Mean imputation is appropriate when the distribution is approximately normal.",
    "mode":   "Mode imputation preserves the most common category for categorical data.",
    "ffill":  "Forward-fill carries the last known value forward - suitable for time-ordered data.",
    "bfill":  "Back-fill uses the next known value - suitable for time-ordered data.",
}


def explain_action(
    action: str,
    column: str | None = None,
    what: str | None = None,
    why: str | None = None,
    confidence: float | None = None,
    rows_affected: int = 0,
    cells_changed: int = 0,
    params: dict | None = None,
    status: str = "applied",
    error: str | None = None,
) -> ExplainedAction:
    """
    Build a standardised ExplainedAction.

    `what` and `why` are auto-generated from templates if not supplied.
    `confidence` defaults to the action-level heuristic.
    """
    params = params or {}
    conf   = confidence if confidence is not None else _CONFIDENCE.get(action, _DEFAULT_CONFIDENCE)

    tpl = _TEMPLATES.get(action, {})
    s   = "s" if rows_affected != 1 else ""
    cs  = "s" if cells_changed != 1 else ""
    es  = "es" if rows_affected != 1 else ""
    strategy = params.get("strategy", "median")
    strategy_reason = _STRATEGY_REASONS.get(strategy, "")

    fmt = dict(
        rows_affected=rows_affected,
        cells_changed=cells_changed,
        column=column or "dataset",
        s=s, cs=cs, es=es,
        strategy=strategy,
        strategy_reason=strategy_reason,
    )

    auto_what = tpl.get("what", f"Applied '{action}'" + (f" on '{column}'" if column else "") + ".").format(**fmt)
    auto_why  = tpl.get("why",  "Recommended by the data quality analysis.").format(**fmt)

    return ExplainedAction(
        action=action,
        column=column,
        what=what or auto_what,
        why=why or auto_why,
        confidence=conf,
        rows_affected=rows_affected,
        cells_changed=cells_changed,
        params=params,
        status=status,
        error=error,
    )


def enrich_suggestions(suggestions: List[Dict[str, Any]], profile: Dict) -> List[Dict[str, Any]]:
    """
    Add `explanation` block to each suggestion dict coming from ai_suggestions.
    Called before returning suggestions to the frontend.
    """
    enriched = []
    for s in suggestions:
        action   = s.get("action", "")
        column   = s.get("column")
        conf     = _CONFIDENCE.get(action, _DEFAULT_CONFIDENCE)

        # Estimate impact from profile
        rows_affected = 0
        if column:
            for cp in profile.get("columns_profile", []):
                if cp.get("column") == column:
                    rows_affected = int(
                        cp.get("missing_count", 0) or
                        cp.get("duplicate_count", 0) or 0
                    )
                    break

        explained = explain_action(
            action=action,
            column=column,
            why=s.get("description") or None,
            confidence=conf,
            rows_affected=rows_affected,
            params=s.get("params", {}),
        )
        enriched.append({**s, "explanation": explained.to_dict()})
    return enriched
