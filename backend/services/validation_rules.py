"""
validation_rules.py - user-defined column validation constraints.

Users define rules like:
  { "column": "age",    "type": "range",  "min": 0, "max": 120 }
  { "column": "status", "type": "enum",   "values": ["active","inactive"] }
  { "column": "email",  "type": "regex",  "pattern": "^[\\w.]+@[\\w.]+$" }
  { "column": "price",  "type": "not_null" }
  { "column": "score",  "type": "positive" }

run_validation returns per-rule violation counts and sample bad rows.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import pandas as pd
from pandas import Series

from utils.preview import safe_preview


def run_validation(df: pd.DataFrame, rules: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Apply a list of validation rules to the DataFrame.

    Returns:
        {
          "passed": bool,
          "total_violations": int,
          "results": [
            {
              "rule": {...},
              "violations": int,
              "violation_pct": float,
              "sample_rows": [{...}, ...],
              "passed": bool,
            },
            ...
          ]
        }
    """
    results = []
    total_violations = 0

    for rule in rules:
        col: Any | None = rule.get("column")
        kind = rule.get("type", "")

        if col and col not in df.columns:
            results.append(
                {
                    "rule": rule,
                    "violations": 0,
                    "violation_pct": 0.0,
                    "sample_rows": [],
                    "passed": True,
                    "note": f"Column '{col}' not found - skipped.",
                }
            )
            continue

        series = df[col] if col else None
        mask: Series[Any] | None = _build_violation_mask(df, series, rule, kind)

        if mask is None:
            results.append(
                {
                    "rule": rule,
                    "violations": 0,
                    "violation_pct": 0.0,
                    "sample_rows": [],
                    "passed": True,
                    "note": f"Unknown rule type '{kind}' - skipped.",
                }
            )
            continue

        count = int(mask.sum())
        total_violations += count
        pct: float = round(count / max(len(df), 1) * 100, 2)
        sample = safe_preview(df[mask], n=5)

        results.append(
            {
                "rule": rule,
                "violations": count,
                "violation_pct": pct,
                "sample_rows": sample,
                "passed": count == 0,
            }
        )

    return {
        "passed": total_violations == 0,
        "total_violations": total_violations,
        "results": results,
    }


def _build_violation_mask(
    df: pd.DataFrame,
    series: Optional[pd.Series],
    rule: Dict[str, Any],
    kind: str,
) -> Optional[pd.Series]:
    """Return a boolean Series where True = row violates the rule."""

    # Type guard: return None if series is None
    assert series is not None, "series parameter cannot be None"

    if kind == "not_null":
        return series.isnull() | (series.astype(str).str.strip() == "")

    if kind == "positive":
        numeric = pd.to_numeric(series, errors="coerce")
        return ~(numeric > 0)

    if kind == "range":
        numeric = pd.to_numeric(series, errors="coerce")
        lo: Any | None = rule.get("min")
        hi: Any | None = rule.get("max")
        mask: Series[bool] = pd.Series([False] * len(df), index=df.index)
        if lo is not None:
            mask |= numeric < lo
        if hi is not None:
            mask |= numeric > hi
        mask |= numeric.isnull()  # non-numeric also violates
        return mask

    if kind == "enum":
        allowed: set[str] = {str(v).strip().lower() for v in rule.get("values", [])}
        return ~series.astype(object).fillna("").astype(
            str
        ).str.strip().str.lower().isin(allowed)

    if kind == "regex":
        pattern = rule.get("pattern", "")
        try:
            compiled = re.compile(pattern)
        except re.error:
            return pd.Series([False] * len(df), index=df.index)
        return ~series.astype(object).fillna("").astype(str).apply(
            lambda x: bool(compiled.search(x))
        )

    if kind == "unique":
        return series.duplicated(keep="first")

    if kind == "max_length":
        max_len = rule.get("max", 255)
        return series.astype(object).fillna("").astype(str).str.len() > max_len

    if kind == "cross_column":
        # Cross-column rule: compare two columns
        # e.g. {"type": "cross_column", "col_a": "start_date", "col_b": "end_date", "op": "lt"}
        col_a: Any | None = rule.get("col_a")
        col_b: Any | None = rule.get("col_b")
        op = rule.get("op", "lt")  # lt, lte, gt, gte, eq, ne
        if not col_a or not col_b or col_a not in df.columns or col_b not in df.columns:
            return None
        a = pd.to_numeric(df[col_a], errors="coerce")
        b = pd.to_numeric(df[col_b], errors="coerce")
        # Also handle datetime comparison
        if a.isna().all():
            a = pd.to_datetime(df[col_a], errors="coerce")
            b = pd.to_datetime(df[col_b], errors="coerce")
        ops = {
            "lt": a >= b,
            "lte": a > b,
            "gt": a <= b,
            "gte": a < b,
            "eq": a != b,
            "ne": a == b,
        }
        return ops.get(op, pd.Series([False] * len(df), index=df.index))

    if kind == "lambda":
        # Custom Python lambda: {"type": "lambda", "expression": "lambda row: row['age'] > 0"}
        expr = rule.get("expression", "")
        try:
            fn = eval(expr)  # noqa: S307 - user-supplied, sandboxed to row access
            mask: Series[bool] = df.apply(lambda row: not bool(fn(row)), axis=1)
            return mask
        except Exception as e:
            return pd.Series([False] * len(df), index=df.index)

    if kind == "not_equal":
        # Column must not equal a given value
        val: Any | None = rule.get("value")
        return (
            series.astype(object)
            .fillna("")
            .astype(str)
            .eq(str(val) if val is not None else "")
        )

    if kind == "contains":
        # Column must contain a substring
        substr = str(rule.get("value", ""))
        return ~series.astype(object).fillna("").astype(str).str.contains(
            substr, case=False, na=True
        )

    if kind == "starts_with":
        prefix = str(rule.get("value", ""))
        return ~series.astype(object).fillna("").astype(str).str.startswith(prefix)

    if kind == "pattern":
        # Validate against a named pattern from pattern_library
        pattern_name = rule.get("pattern_name", "")
        try:
            from services.pattern_library import _COMPILED

            # Rebuild mask: True where NOT matched
            rx = _COMPILED.get(pattern_name)
            if rx is None:
                return None
            return ~series.astype(object).fillna("").astype(str).apply(
                lambda v: bool(rx.search(v))
            )
        except Exception:
            return None

    return None
