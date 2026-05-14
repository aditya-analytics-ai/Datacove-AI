"""
AI Safety Layer - validation, confidence scoring, and human-in-the-loop gating.

Every AI suggestion passes through this module before being applied.
The flow is:
  1. Score confidence (based on action type, issue severity, data size)
  2. Validate the suggestion is structurally sound
  3. Gate: auto-apply if confidence > threshold, else require user confirmation

This makes AI-driven cleaning safe for production use.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from utils.logger import logger


# ── Confidence thresholds ─────────────────────────────────────────────────────

AUTO_APPLY_THRESHOLD   = 0.80   # confidence ≥ this → safe to auto-apply
WARN_THRESHOLD         = 0.50   # confidence < this → show strong warning
BLOCK_THRESHOLD        = 0.20   # confidence < this → block, never auto-apply


# ── Action risk ratings (0 = safest, 1 = most risky) ─────────────────────────

_ACTION_RISK: Dict[str, float] = {
    # Zero-risk: pure metadata
    "trim_whitespace":             0.05,
    "normalize_unicode":           0.05,
    "standardise_capitalisation":  0.10,
    "normalise_categories":        0.15,
    "round_numeric":               0.10,
    "normalize_column_names":      0.10,

    # Low risk: well-understood transforms
    "remove_duplicates":           0.15,
    "fill_missing":                0.20,
    "fill_missing_ffill":          0.20,
    "fill_missing_bfill":          0.20,
    "fill_missing_interpolate":    0.25,
    "coerce_numeric":              0.20,
    "standardise_dates":           0.20,
    "standardise_mixed_dates":     0.25,
    "flag_invalid_emails":         0.10,
    "normalize_phone":             0.15,
    "strip_characters":            0.20,
    "extract_numeric":             0.25,

    # Medium risk: data loss or structural changes possible
    "drop_rows_where":             0.40,
    "drop_rows_matching":          0.40,
    "drop_rows_missing_threshold": 0.35,
    "drop_column":                 0.45,
    "drop_constant_columns":       0.30,
    "drop_high_missing_columns":   0.35,
    "clip_outliers":               0.30,
    "replace_outliers":            0.35,
    "cast_type":                   0.30,
    "find_replace":                0.30,
    "map_values":                  0.35,
    "bin_numeric":                 0.30,

    # Higher risk: significant data changes
    "scale_numeric":               0.45,
    "split_column":                0.45,
    "merge_columns":               0.40,
    "sql_apply":                   0.60,
    "fuzzy_remove_duplicates":     0.50,
    "apply_schema_suggestions":    0.40,
}


def score_confidence(
    suggestion: Dict[str, Any],
    profile: Optional[Dict] = None,
) -> float:
    """
    Compute a confidence score in [0, 1] for an AI suggestion.

    Higher = safer to auto-apply.
    Factors:
      - action risk rating
      - priority declared by AI
      - whether the column actually exists in the profile
      - row count (large datasets warrant more caution)
    """
    action   = suggestion.get("action", "")
    priority = suggestion.get("priority", "medium")
    col      = suggestion.get("column")

    # Base confidence: inverse of action risk
    base_risk = _ACTION_RISK.get(action, 0.50)
    confidence = 1.0 - base_risk

    # Priority boost / penalty
    if priority == "high":
        confidence = min(1.0, confidence + 0.05)
    elif priority == "low":
        confidence = max(0.0, confidence - 0.10)

    # Column existence check (if profile provided)
    if col and profile:
        known_cols = {cp["column"] for cp in profile.get("columns_profile", [])}
        if col not in known_cols:
            confidence -= 0.25   # column not in dataset → suspicious
            logger.warning(f"AI suggestion references unknown column '{col}' - penalising confidence")

    # Scale penalty for very large datasets (conservative on big data)
    if profile:
        rows = profile.get("rows", 0)
        if rows > 500_000:
            confidence = max(0.0, confidence - 0.10)
        elif rows > 100_000:
            confidence = max(0.0, confidence - 0.05)

    # Clamp to [0, 1]
    return round(max(0.0, min(1.0, confidence)), 3)


def validate_suggestion(
    suggestion: Dict[str, Any],
    df: pd.DataFrame,
) -> Tuple[bool, str]:
    """
    Structurally validate an AI suggestion before applying it.

    Returns (is_valid, reason_if_invalid).
    """
    action = suggestion.get("action", "")
    params = suggestion.get("params", {})
    col    = params.get("column") or suggestion.get("column")

    # 1. Action must exist in the cleaning engine
    from services.cleaning_engine import _ACTIONS
    if action not in _ACTIONS:
        return False, f"Unknown action '{action}' - not in cleaning engine registry."

    # 2. If a column is named, it must exist
    if col and col not in df.columns:
        return False, f"Column '{col}' does not exist in the dataset (has {list(df.columns[:5])}...)."

    # 3. Action-specific param checks
    if action in ("fill_missing",) and "strategy" not in params:
        return False, "fill_missing requires a 'strategy' param (mean|median|mode|ffill|bfill|value)."

    if action == "map_values" and not params.get("mapping"):
        return False, "map_values requires a non-empty 'mapping' dict."

    if action == "sql_apply" and not params.get("query"):
        return False, "sql_apply requires a 'query' param."

    if action in ("split_column", "merge_columns") and not col:
        return False, f"{action} requires a 'column' param."

    return True, ""


def gate_suggestion(
    suggestion: Dict[str, Any],
    df: pd.DataFrame,
    profile: Optional[Dict] = None,
    force_confirm: bool = False,
) -> Dict[str, Any]:
    """
    Full safety gate for a single AI suggestion.

    Returns an enriched suggestion dict with:
      - confidence:    float score
      - gate:          "auto" | "confirm" | "blocked"
      - gate_reason:   human-readable explanation
      - valid:         bool
      - error:         validation error string (if invalid)
    """
    # Step 1: Validate structure
    is_valid, error_msg = validate_suggestion(suggestion, df)

    # Step 2: Score confidence
    confidence = score_confidence(suggestion, profile)

    # Step 3: Determine gate
    if not is_valid:
        gate        = "blocked"
        gate_reason = f"Validation failed: {error_msg}"
    elif force_confirm or confidence < AUTO_APPLY_THRESHOLD:
        if confidence < BLOCK_THRESHOLD:
            gate        = "blocked"
            gate_reason = f"Confidence too low ({confidence:.0%}) - manual review required."
        else:
            gate        = "confirm"
            gate_reason = (
                f"Confidence {confidence:.0%} - below auto-apply threshold. "
                f"Please review before applying."
            )
    else:
        gate        = "auto"
        gate_reason = f"Confidence {confidence:.0%} - safe to auto-apply."

    result = {**suggestion,
              "confidence":  confidence,
              "gate":        gate,
              "gate_reason": gate_reason,
              "valid":       is_valid,
              "error":       error_msg if not is_valid else None}

    logger.info(
        f"AI safety gate: action='{suggestion.get('action')}' col='{suggestion.get('column')}' "
        f"confidence={confidence:.2f} gate={gate}"
    )
    return result


def gate_all(
    suggestions: List[Dict[str, Any]],
    df: pd.DataFrame,
    profile: Optional[Dict] = None,
) -> List[Dict[str, Any]]:
    """Apply the safety gate to a list of AI suggestions."""
    return [gate_suggestion(s, df, profile) for s in suggestions]


def split_by_gate(
    gated: List[Dict[str, Any]],
) -> Tuple[List, List, List]:
    """
    Partition gated suggestions into (auto_apply, needs_confirm, blocked).
    """
    auto     = [s for s in gated if s["gate"] == "auto"]
    confirm  = [s for s in gated if s["gate"] == "confirm"]
    blocked  = [s for s in gated if s["gate"] == "blocked"]
    return auto, confirm, blocked
