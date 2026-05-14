"""
utils/request_validator.py - API boundary validation.

All validation happens at the route handler level, before any service
is called. Bad requests get a clear 400 with a helpful error message
instead of a cryptic 500 from deep inside a service.

Usage:
    from utils.request_validator import RequestValidator
    v = RequestValidator(session_id=req.session_id, action=req.action,
                         params=req.params, df=session.df_current)
    v.run()   # raises HTTPException(400) on first failure
"""

from __future__ import annotations

import re
import uuid
from difflib import get_close_matches
from typing import Any, Dict, Optional

from fastapi import HTTPException

# ── Constants ──────────────────────────────────────────────────────────────────

# Complete list of valid cleaning actions (mirrors cleaning_engine._ACTIONS)
VALID_ACTIONS = frozenset(
    {
        "remove_duplicates",
        "trim_whitespace",
        "standardise_capitalisation",
        "normalise_categories",
        "fill_missing",
        "fill_missing_ffill",
        "fill_missing_bfill",
        "fill_missing_interpolate",
        "coerce_numeric",
        "standardise_dates",
        "standardise_mixed_dates",
        "flag_invalid_emails",
        "normalize_phone",
        "normalize_unicode",
        "strip_characters",
        "find_replace",
        "map_values",
        "split_column",
        "merge_columns",
        "extract_numeric",
        "clip_outliers",
        "replace_outliers",
        "round_numeric",
        "scale_numeric",
        "bin_numeric",
        "cast_type",
        "conditional_column",
        "drop_column",
        "rename_column",
        "rename_columns_bulk",
        "reorder_columns",
        "drop_constant_columns",
        "drop_high_missing_columns",
        "drop_rows_missing_threshold",
        "drop_rows_where",
        "drop_rows_matching",
        "extract_date_parts",
        "calculate_date_diff",
        "flag_future_dates",
        "flag_weekend_dates",
        "age_from_date",
        "fuzzy_remove_duplicates",
        "sql_apply",
        "apply_schema_suggestions",
        "normalize_column_names",
        "map_to_standard",
        # STEP 6: Custom validation
        "validate_regex",
        "validate_range",
        "validate_format",
    }
)

# Actions that require a specific param.
_REQUIRED_PARAMS: Dict[str, list] = {
    "fill_missing": ["strategy"],
    "cast_type": ["dtype"],
    "find_replace": ["find"],
    "map_values": ["mapping"],
    "rename_column": ["old_name", "new_name"],
    "bin_numeric": ["bins"],
    "split_column": ["delimiter"],
    "sql_apply": ["query"],
    # conditional_column: only "condition" is always required;
    # "value" is optional (not needed for "not_null" condition),
    # and true_label/false_label/new_col all have backend defaults.
    "conditional_column": ["condition"],
    # calculate_date_diff: frontend sends "column" (start date) and
    # optionally "column2" or "reference_date". Only "column" is mandatory.
    "calculate_date_diff": ["column"],
    "validate_regex": ["pattern"],
    "validate_range": ["min_val", "max_val"],
    "validate_format": ["format"],
}

# Actions that MUST have a column.
# NOTE: Actions that support "no column = apply to all eligible columns" mode
# must NOT appear here, otherwise the validator rejects all-column requests.
# Backend functions for fill_missing*, normalize_unicode, strip_characters,
# round_numeric, and scale_numeric all handle col=None gracefully.
_COLUMN_REQUIRED = frozenset(
    {
        # Numeric coercion / formatting - column is always needed
        "coerce_numeric",
        "extract_numeric",
        "clip_outliers",
        "replace_outliers",
        "bin_numeric",
        "cast_type",
        # Date - always need a specific date column
        "standardise_dates",
        "standardise_mixed_dates",
        "extract_date_parts",
        "calculate_date_diff",
        "flag_future_dates",
        "flag_weekend_dates",
        "age_from_date",
        # Email / phone - specific column needed
        "flag_invalid_emails",
        "normalize_phone",
        # String ops that require a target column
        "find_replace",
        "map_values",
        "split_column",
        # Structural - column required
        "drop_column",
        "rename_column",
        "conditional_column",
        # Custom validation - column always required
        "validate_regex",
        "validate_range",
        "validate_format",
        # NOTE: The following are intentionally NOT listed because they support
        # all-column mode when column is omitted:
        #   fill_missing, fill_missing_ffill, fill_missing_bfill,
        #   fill_missing_interpolate, normalize_unicode, strip_characters,
        #   round_numeric, scale_numeric
    }
)

# Dangerous SQL keywords blocked in sql_apply
_SQL_BLOCKED = frozenset(
    {
        "drop",
        "delete",
        "insert",
        "update",
        "alter",
        "truncate",
        "create",
        "exec",
        "execute",
        "grant",
        "revoke",
        "replace",
        "merge",
    }
)

MAX_STRING_PARAM_LEN = 10_000
MAX_SESSION_ID_LEN = 36  # UUID length


# ── Individual validators ─────────────────────────────────────────────────────


def validate_session_id(session_id: str) -> str:
    """
    Ensure session_id is a well-formed UUID.
    Blocks path traversal attempts like '../../etc/passwd'.
    """
    if not session_id or not isinstance(session_id, str):
        raise HTTPException(status_code=400, detail="session_id is required.")

    if len(session_id) > MAX_SESSION_ID_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"session_id too long (max {MAX_SESSION_ID_LEN} chars).",
        )

    # Block path traversal and injection patterns
    if ".." in session_id or "/" in session_id or "\\" in session_id:
        raise HTTPException(
            status_code=400, detail="session_id contains invalid characters."
        )

    try:
        uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"session_id '{session_id}' is not a valid UUID."
        )

    return session_id


def validate_action(action: str) -> str:
    """Ensure action is in the cleaning engine registry."""
    if not action or not isinstance(action, str):
        raise HTTPException(status_code=400, detail="action is required.")

    if action not in VALID_ACTIONS:
        suggestions = get_close_matches(action, VALID_ACTIONS, n=3, cutoff=0.5)
        hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        raise HTTPException(
            status_code=400,
            detail=f"Unknown action '{action}'.{hint} "
            f"See /docs for the full list of valid actions.",
        )
    return action


def validate_params(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check required params are present and values are within safe limits.
    """
    required = _REQUIRED_PARAMS.get(action, [])
    missing_params = [key for key in required if key not in params]

    if missing_params:
        provided = list(params.keys())
        suggestion = ""

        # Add specific hints for common mistakes
        if action == "find_replace":
            if "find_text" in provided or "replace_text" in provided:
                suggestion = " Hint: Use 'find' not 'find_text', and 'replace' not 'replace_text'."

        raise HTTPException(
            status_code=400,
            detail=f"Action '{action}' requires params: {sorted(required)}. "
            f"You provided: {sorted(provided)}.{suggestion}",
        )

    # String param length guard
    for k, v in params.items():
        if isinstance(v, str) and len(v) > MAX_STRING_PARAM_LEN:
            raise HTTPException(
                status_code=400,
                detail=f"Param '{k}' exceeds maximum length of "
                f"{MAX_STRING_PARAM_LEN:,} characters.",
            )

    # SQL injection guard for sql_apply
    if action == "sql_apply":
        _validate_sql_query(params.get("query", ""))

    return params


def _validate_sql_query(query: str) -> None:
    """Block non-SELECT SQL statements."""
    if not query or not isinstance(query, str):
        raise HTTPException(
            status_code=400, detail="sql_apply requires a non-empty 'query' param."
        )

    clean = query.strip().lower()

    # Tokenise the FULL query first - catches chained statements like SELECT...;DROP
    tokens = set(re.split(r"[\s;,()\[\]]+", clean))
    blocked = tokens & _SQL_BLOCKED
    if blocked:
        raise HTTPException(
            status_code=400,
            detail=f"SQL query contains blocked keyword(s): {', '.join(sorted(blocked))}. "
            "Only read-only SELECT queries are permitted.",
        )

    # Then check it starts with SELECT (must come after blocked-keyword check)
    if not clean.startswith("select"):
        raise HTTPException(
            status_code=400,
            detail="Only SELECT queries are allowed in sql_apply.",
        )


def validate_column_exists(
    column: Optional[str], action: str, df_columns: list
) -> Optional[str]:
    """
    If action requires a column, ensure it exists in the DataFrame.
    Returns helpful suggestions if the column name is close but wrong.
    """
    if column is None:
        if action in _COLUMN_REQUIRED:
            raise HTTPException(
                status_code=400,
                detail=f"Action '{action}' requires a 'column' param.",
            )
        return None

    if column not in df_columns:
        suggestions = get_close_matches(column, df_columns, n=3, cutoff=0.5)
        hint = (
            f" Did you mean: {suggestions}?"
            if suggestions
            else f" Available columns: {df_columns[:10]}"
        )
        raise HTTPException(
            status_code=400,
            detail=f"Column '{column}' not found in dataset.{hint}",
        )
    return column


# ── Composable validator ──────────────────────────────────────────────────────


class RequestValidator:
    """
    Chains all checks for a /clean request.

    Usage:
        v = RequestValidator(
            session_id=req.session_id,
            action=req.action,
            params=req.params,
            df_columns=list(session.df_current.columns),
        )
        v.run()   # raises HTTPException(400) on first problem
    """

    def __init__(
        self,
        session_id: str,
        action: str,
        params: Dict[str, Any],
        df_columns: Optional[list] = None,
    ):
        self.session_id = session_id
        self.action = action
        self.params = params
        self.df_columns = df_columns or []

    def run(self) -> None:
        validate_session_id(self.session_id)
        validate_action(self.action)
        validate_params(self.action, self.params)

        # NEW: Validate column exists early
        if self.action in _COLUMN_REQUIRED:
            col = self.params.get("column") or self.params.get("col")
            if not col:
                raise HTTPException(
                    status_code=400,
                    detail=f"Action '{self.action}' requires a 'column' parameter.",
                )

            # Check if column exists and offer suggestions for case mismatches
            if self.df_columns and col not in self.df_columns:
                # Try to find case-insensitive match
                suggestions = [c for c in self.df_columns if c.lower() == col.lower()]
                hint = f" Did you mean '{suggestions[0]}'?" if suggestions else ""

                # Show first 5 available columns
                available = ", ".join(self.df_columns[:5])
                if len(self.df_columns) > 5:
                    available += f", ... and {len(self.df_columns) - 5} more"

                raise HTTPException(
                    status_code=400,
                    detail=f"Column '{col}' not found in dataset.{hint} "
                    f"Available columns: {available}",
                )
