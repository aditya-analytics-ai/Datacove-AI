"""
Issue detector v2 - finds data quality problems across the dataset.

New in v2
─────────
  constant_column          - zero-variance columns (all identical values)
  all_null_column          - 100% missing columns
  empty_string_values      - "" cells invisible to isnull()
  negative_in_positive_col - negative numbers in age/price/count-like columns
  encoding_garbage         - non-printable / control characters in strings
  likely_id_column         - near-unique columns that shouldn't be cleaned
  date_out_of_range        - dates in implausible year ranges
  mixed_date_formats       - multiple date formats in the same column
  unparseable_dates        - values in a date column that cannot be parsed
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
from pandas import Series, Timestamp

from utils.validation_utils import is_valid_email, is_valid_phone

# ── Keyword heuristics ────────────────────────────────────────────────────────
_POSITIVE_KEYWORDS = (
    "age",
    "price",
    "amount",
    "salary",
    "revenue",
    "cost",
    "score",
    "rating",
    "weight",
    "height",
    "distance",
    "quantity",
    "count",
    "size",
    "duration",
    "rate",
)
_DATE_KEYWORDS = ("date", "dob", "birth", "created", "updated", "time", "year", "dt_")


# ══════════════════════════════════════════════════════════════════════════════
# ── Public entry point ────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════


def detect_issues(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Returns a list of issue objects, each describing a problem in the dataset
    with affected row counts, severity, and the recommended fix_action.
    """
    issues: List[Dict[str, Any]] = []

    # ── Dataset-level: duplicate rows ────────────────────────────────────────
    # Cast to plain bool to avoid numpy boolean subtract error
    # on DataFrames with nullable dtypes (BooleanDtype)
    dup_mask: Series[bool] = df.duplicated(keep="first").astype(bool)
    dup_count = int(dup_mask.sum())
    if dup_count > 0:
        issues.append(
            {
                "type": "duplicate_rows",
                "severity": "high",
                "count": dup_count,
                "column": None,
                "description": f"{dup_count} exact duplicate row(s) detected.",
                "fix_action": "remove_duplicates",
            }
        )

    # ─ Column-level checks ──────────────────────────────────────────────────
    for col in df.columns:
        issues.extend(_check_column(df[col], col, len(df)))

    return issues


# ══════════════════════════════════════════════════════════════════════════════
# ── Per-column checks ─────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════


def _check_column(series: pd.Series, col: str, total: int) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    col_lower: str = col.lower()

    # ────────────────────────────────────────────────────────────────────────
    # NEW ① all_null_column  (check first; skip all other checks if true)
    # ────────────────────────────────────────────────────────────────────────
    if series.isnull().all():
        issues.append(
            {
                "type": "all_null_column",
                "severity": "high",
                "count": total,
                "column": col,
                "description": f"'{col}': column is entirely empty - 100% missing values.",
                "fix_action": "drop_column",
            }
        )
        return issues  # no further checks make sense

    # ────────────────────────────────────────────────────────────────────────
    # NEW ② constant_column - zero variance (a single value or all NaN)
    # ────────────────────────────────────────────────────────────────────────
    non_null: Series[Any] = series.dropna()
    if non_null.nunique() <= 1 and len(non_null) > 0:
        issues.append(
            {
                "type": "constant_column",
                "severity": "medium",
                "count": len(non_null),
                "column": col,
                "description": (
                    f"'{col}': all non-null values are identical "
                    f"('{non_null.iloc[0]}'). Zero-variance column."
                ),
                "fix_action": "drop_column",
            }
        )
        return issues  # no further cleaning helps

    # ────────────────────────────────────────────────────────────────────────
    # EXISTING: missing values
    # ────────────────────────────────────────────────────────────────────────
    missing = int(series.isnull().sum())
    if missing > 0:
        pct: float = round(missing / total * 100, 1)
        severity: str = "high" if pct > 20 else ("medium" if pct > 5 else "low")
        issues.append(
            {
                "type": "missing_values",
                "severity": severity,
                "count": missing,
                "column": col,
                "description": f"'{col}': {missing} missing values ({pct}%).",
                "fix_action": "fill_missing",
            }
        )

    # ────────────────────────────────────────────────────────────────────────
    # NEW ③ negative_in_positive_col - numeric columns that should be ≥ 0
    # ────────────────────────────────────────────────────────────────────────
    if pd.api.types.is_numeric_dtype(series) and any(
        k in col_lower for k in _POSITIVE_KEYWORDS
    ):
        neg_count = int((series < 0).sum())
        if neg_count > 0:
            issues.append(
                {
                    "type": "negative_in_positive_col",
                    "severity": "high",
                    "count": neg_count,
                    "column": col,
                    "description": (
                        f"'{col}': {neg_count} negative value(s) in a column "
                        "that is expected to be non-negative."
                    ),
                    "fix_action": "clip_outliers",
                }
            )

    # ────────────────────────────────────────────────────────────────────────
    # String-only checks below
    # ────────────────────────────────────────────────────────────────────────
    if not (pd.api.types.is_string_dtype(series) or series.dtype == object):
        # Date-range check for datetime-typed OR string-typed date columns
        if any(k in col_lower for k in _DATE_KEYWORDS):
            issues.extend(_check_date_range(series, col))
            # Mixed format detection works on any string-representable column
            issues.extend(_detect_mixed_date_formats(series, col))
            issues.extend(_detect_unparseable_dates(series, col))
        return issues

    # From here: dtype == object
    # ────────────────────────────────────────────────────────────────────────
    # Date-range check for string columns with date keywords (e.g. "birth_date"
    # stored as CSV strings). _check_date_range calls pd.to_datetime internally.
    # ────────────────────────────────────────────────────────────────────────
    if any(k in col_lower for k in _DATE_KEYWORDS):
        issues.extend(_check_date_range(series, col))
    # ────────────────────────────────────────────────────────────────────────
    # NEW ④ empty_string_values - "" cells that isnull() misses
    # ────────────────────────────────────────────────────────────────────────
    # Cast to object first so fillna works on Int64/BooleanDtype extension arrays
    empty_str_count = int(
        series.astype(object).fillna("_NOT_NULL_").astype(str).str.strip().eq("").sum()
    )
    if empty_str_count > 0:
        issues.append(
            {
                "type": "empty_string_values",
                "severity": "medium",
                "count": empty_str_count,
                "column": col,
                "description": (
                    f"'{col}': {empty_str_count} cell(s) contain empty strings "
                    '("") - these are invisible to standard null checks.'
                ),
                "fix_action": "find_replace",
            }
        )

    # ────────────────────────────────────────────────────────────────────────
    # NEW ⑤ encoding_garbage - non-printable / control characters
    # ────────────────────────────────────────────────────────────────────────
    def _has_garbage(val: Any) -> bool:
        if pd.isna(val):
            return False
        return any(not ch.isprintable() and ch not in "\n\r\t" for ch in str(val))

    garbage_count = int(series.apply(_has_garbage).sum())
    if garbage_count > 0:
        issues.append(
            {
                "type": "encoding_garbage",
                "severity": "medium",
                "count": garbage_count,
                "column": col,
                "description": (
                    f"'{col}': {garbage_count} cell(s) contain non-printable "
                    "or garbage characters (encoding artefacts)."
                ),
                "fix_action": "strip_characters",
            }
        )

    # ────────────────────────────────────────────────────────────────────────
    # NEW ⑥ likely_id_column - near-unique columns (should not be cleaned)
    # ────────────────────────────────────────────────────────────────────────
    unique_ratio: float = non_null.nunique() / max(len(non_null), 1)
    if unique_ratio > 0.95 and len(non_null) >= 20:
        issues.append(
            {
                "type": "likely_id_column",
                "severity": "low",
                "count": int(non_null.nunique()),
                "column": col,
                "description": (
                    f"'{col}': {non_null.nunique()} unique values out of "
                    f"{len(non_null)} rows ({unique_ratio * 100:.0f}% unique) - "
                    "likely an ID or key column; cleaning may be counterproductive."
                ),
                "fix_action": "drop_column",
            }
        )

    # ────────────────────────────────────────────────────────────────────────
    # EXISTING: whitespace
    # ────────────────────────────────────────────────────────────────────────
    ws_count = int(
        non_null.apply(lambda x: str(x) != str(x).strip() or "  " in str(x)).sum()
    )
    if ws_count > 0:
        issues.append(
            {
                "type": "extra_whitespace",
                "severity": "low",
                "count": ws_count,
                "column": col,
                "description": f"'{col}': {ws_count} cell(s) have leading/trailing/extra whitespace.",
                "fix_action": "trim_whitespace",
            }
        )

    # ────────────────────────────────────────────────────────────────────────
    # EXISTING: capitalisation inconsistency
    # ────────────────────────────────────────────────────────────────────────
    # Guard: object columns can hold non-str values (int/float as Python objects).
    # Always cast to str before .str accessor to avoid "Can only use .str
    # accessor with string values!" TypeError on mixed-type columns.
    non_null_str: Series[str] = non_null.astype(str)
    lowered: Series[str] = non_null_str.str.lower().str.strip()
    unique_raw: int = non_null_str.str.strip().nunique()
    unique_normal: int = lowered.nunique()
    if unique_normal < unique_raw and unique_normal >= 2:
        cap_issues = int(unique_raw - unique_normal)
        issues.append(
            {
                "type": "capitalisation_inconsistency",
                "severity": "medium",
                "count": cap_issues,
                "column": col,
                "description": f"'{col}': {cap_issues} capitalisation variant(s) detected.",
                "fix_action": "standardise_capitalisation",
            }
        )

    # ────────────────────────────────────────────────────────────────────────
    # EXISTING: invalid email
    # ────────────────────────────────────────────────────────────────────────
    col_has_at: bool = non_null.head(30).apply(lambda x: "@" in str(x)).mean() > 0.5
    if "email" in col_lower or col_has_at:
        invalid_emails = int(non_null.apply(lambda x: not is_valid_email(str(x))).sum())
        if invalid_emails > 0:
            issues.append(
                {
                    "type": "invalid_email",
                    "severity": "medium",
                    "count": invalid_emails,
                    "column": col,
                    "description": f"'{col}': {invalid_emails} invalid email address(es).",
                    "fix_action": "flag_invalid_emails",
                }
            )

    # ────────────────────────────────────────────────────────────────────────
    # EXISTING: invalid phone
    # ────────────────────────────────────────────────────────────────────────
    if any(k in col_lower for k in ("phone", "mobile", "tel")):
        invalid_phones = int(non_null.apply(lambda x: not is_valid_phone(str(x))).sum())
        if invalid_phones > 0:
            issues.append(
                {
                    "type": "invalid_phone",
                    "severity": "medium",
                    "count": invalid_phones,
                    "column": col,
                    "description": f"'{col}': {invalid_phones} invalid phone number(s).",
                    "fix_action": "normalize_phone",
                }
            )

    # ────────────────────────────────────────────────────────────────────────
    # EXISTING: mixed data types
    # ────────────────────────────────────────────────────────────────────────
    numeric_like: Series[bool] = pd.to_numeric(non_null, errors="coerce").notna()
    numeric_pct: float = numeric_like.mean()
    if 0.05 < numeric_pct < 0.95:
        mixed_count = int((~numeric_like).sum())
        issues.append(
            {
                "type": "mixed_data_types",
                "severity": "high",
                "count": mixed_count,
                "column": col,
                "description": f"'{col}': mixed text and numeric values detected.",
                "fix_action": "coerce_numeric",
            }
        )

    # ────────────────────────────────────────────────────────────────────────
    # EXISTING: category inconsistency
    # ────────────────────────────────────────────────────────────────────────
    unique_vals_norm: int = non_null.astype(str).str.strip().str.lower().nunique()
    raw_unique: int = non_null.nunique()
    if 2 <= unique_vals_norm <= 30 and raw_unique > unique_vals_norm:
        issues.append(
            {
                "type": "category_inconsistency",
                "severity": "medium",
                "count": int(raw_unique - unique_vals_norm),
                "column": col,
                "description": (
                    f"'{col}': {raw_unique - unique_vals_norm} inconsistent "
                    "category variant(s) (e.g. 'yes' vs 'Yes' vs 'YES')."
                ),
                "fix_action": "normalise_categories",
            }
        )

    # ── NEW: mixed date formats + unparseable dates (string date columns) ─────
    if any(k in col_lower for k in _DATE_KEYWORDS):
        issues.extend(_detect_mixed_date_formats(series, col))
        issues.extend(_detect_unparseable_dates(series, col))

    return issues


# ══════════════════════════════════════════════════════════════════════════════
# ── NEW ⑦ date_out_of_range ──────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════


def _check_date_range(series: pd.Series, col: str) -> List[Dict[str, Any]]:
    """
    Detect dates outside the plausible range [1900, current year + 5].
    Works on both datetime-typed columns and string columns with date keywords.
    """
    import datetime

    issues: List[Dict[str, Any]] = []

    try:
        parsed: Series[Timestamp] = pd.to_datetime(series, errors="coerce")
    except Exception:
        return issues

    valid_dates: Series[Timestamp] = parsed.dropna()
    if len(valid_dates) == 0:
        return issues

    current_year: int = datetime.datetime.now().year
    min_year = 1900
    max_year: int = current_year + 5

    out_of_range: Series[bool] = (valid_dates.dt.year < min_year) | (
        valid_dates.dt.year > max_year
    )
    bad_count = int(out_of_range.sum())

    if bad_count > 0:
        issues.append(
            {
                "type": "date_out_of_range",
                "severity": "medium",
                "count": bad_count,
                "column": col,
                "description": (
                    f"'{col}': {bad_count} date(s) fall outside the expected range "
                    f"({min_year}-{max_year}). Possible parsing errors or typos."
                ),
                "fix_action": "standardise_dates",
            }
        )

    return issues


# ══════════════════════════════════════════════════════════════════════════════
# ── NEW: Date-specific detectors ─────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════


def _detect_mixed_date_formats(series: pd.Series, col: str) -> List[Dict[str, Any]]:
    """
    Detect columns that contain multiple different date formats.
    e.g. "11-08-2016" and "4/15/2017" in the same column.
    """
    import re

    DATE_PATTERNS: List[tuple[str, str]] = [
        (r"^\d{4}-\d{2}-\d{2}$", "YYYY-MM-DD"),
        (r"^\d{2}-\d{2}-\d{4}$", "DD-MM-YYYY"),
        (r"^\d{1,2}/\d{1,2}/\d{4}$", "M/D/YYYY"),
        (r"^\d{2}/\d{2}/\d{4}$", "MM/DD/YYYY"),
        (r"^\d{4}/\d{2}/\d{2}$", "YYYY/MM/DD"),
        (r"^\d{1,2}\.\d{1,2}\.\d{4}$", "D.M.YYYY"),
        (r"^[A-Za-z]+ \d{1,2},? \d{4}$", "Month D YYYY"),
        (r"^\d{1,2} [A-Za-z]+ \d{4}$", "D Month YYYY"),
    ]

    non_null: Series[str] = series.dropna().astype(str).str.strip()
    if len(non_null) == 0:
        return []

    formats_found: dict = {}
    for val in non_null:
        for pat, name in DATE_PATTERNS:
            if re.match(pat, val):
                formats_found.setdefault(name, 0)
                formats_found[name] += 1
                break

    if len(formats_found) <= 1:
        return []

    fmt_summary: str = ", ".join(
        f"{k} ({v})" for k, v in sorted(formats_found.items(), key=lambda x: -x[1])
    )
    total_affected: int = sum(formats_found.values())

    return [
        {
            "type": "mixed_date_formats",
            "severity": "high",
            "count": total_affected,
            "column": col,
            "description": (
                f"'{col}': {len(formats_found)} different date formats detected "
                f"({fmt_summary}). Standardise to ISO 8601 (YYYY-MM-DD)."
            ),
            "fix_action": "standardise_mixed_dates",
        }
    ]


def _detect_unparseable_dates(series: pd.Series, col: str) -> List[Dict[str, Any]]:
    """
    Detect values in a date-like column that cannot be parsed as any date.
    """
    non_null: Series[Any] = series.dropna()
    if len(non_null) == 0:
        return []

    parsed: Series[Timestamp] = pd.to_datetime(non_null, dayfirst=True, errors="coerce")
    unparseable_count = int(parsed.isna().sum())

    if unparseable_count == 0:
        return []

    pct: float = round(unparseable_count / len(non_null) * 100, 1)
    severity: str = "high" if pct > 10 else "medium"

    return [
        {
            "type": "unparseable_dates",
            "severity": severity,
            "count": unparseable_count,
            "column": col,
            "description": (
                f"'{col}': {unparseable_count} value(s) ({pct}%) cannot be parsed "
                "as a date. These will become NaT after standardisation."
            ),
            "fix_action": "standardise_mixed_dates",
        }
    ]
