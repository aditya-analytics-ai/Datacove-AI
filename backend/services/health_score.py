"""
Health score v3 - data quality score 0-100 with full issue coverage.

Covers all 17 issue types from issue_detector v2 across 7 penalty categories.
Each category has its own cap so no single problem zeroes the score.
Response includes `breakdown` (per-category totals) for the UI heatmap.
"""
from __future__ import annotations
from typing import Any, Dict, List
import pandas as pd

_SEV: Dict[str, float] = {"high": 1.0, "medium": 0.6, "low": 0.25}

_TYPE_CFG: Dict[str, tuple] = {
    # (category, per_col_penalty, cap)
    "empty_string_values":          ("Completeness",  3.0,   8.0),
    "all_null_column":              ("Completeness",  8.0,  30.0),
    "constant_column":              ("Structural",    4.0,  12.0),
    "encoding_garbage":             ("Structural",    4.0,  10.0),
    "likely_id_column":             ("Structural",    1.5,   4.0),
    "invalid_email":                ("Format",        0.0,   6.0),
    "invalid_phone":                ("Format",        0.0,   4.0),
    "category_inconsistency":       ("Format",        2.5,   6.0),
    "capitalisation_inconsistency": ("Format",        1.0,   3.0),
    "extra_whitespace":             ("Format",        0.5,   2.0),
    "mixed_data_types":             ("Type",          4.0,  10.0),
    "negative_in_positive_col":     ("Type",          0.0,   5.0),
    "date_out_of_range":            ("Date",          0.0,   6.0),
    "mixed_date_formats":           ("Date",          3.5,   6.0),
    "unparseable_dates":            ("Date",          0.0,   5.0),
    "outlier":                      ("Anomalies",     0.0,   8.0),
    "anomaly":                      ("Anomalies",     0.0,   8.0),
}

_RATIO_MULT: Dict[str, float] = {
    "invalid_email": 6.0, "invalid_phone": 4.0,
    "negative_in_positive_col": 5.0,
    "date_out_of_range": 6.0, "unparseable_dates": 5.0,
    "outlier": 8.0, "anomaly": 8.0,
}
_RATIO_SCALED: set[str] = set(_RATIO_MULT)

_TYPE_LABELS: Dict[str, str] = {
    "empty_string_values":          "Empty string values",
    "all_null_column":              "Entirely empty column(s)",
    "constant_column":              "Constant / zero-variance column(s)",
    "encoding_garbage":             "Encoding garbage (control chars)",
    "likely_id_column":             "Likely ID column(s)",
    "invalid_email":                "Invalid email addresses",
    "invalid_phone":                "Invalid phone numbers",
    "category_inconsistency":       "Category value inconsistencies",
    "capitalisation_inconsistency": "Capitalisation inconsistencies",
    "extra_whitespace":             "Extra whitespace in values",
    "mixed_data_types":             "Mixed data types in column(s)",
    "negative_in_positive_col":     "Negative values in positive-only column(s)",
    "date_out_of_range":            "Dates outside plausible range",
    "mixed_date_formats":           "Mixed date formats in column(s)",
    "unparseable_dates":            "Unparseable date values",
    "outlier":                      "Statistical outliers",
    "anomaly":                      "Anomalies detected",
}


def calculate_health_score(df: pd.DataFrame, issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows: int  = max(len(df), 1)
    cols: int  = max(len(df.columns), 1)
    cells: int = rows * cols

    deductions: List[Dict[str, Any]] = []
    category_totals: Dict[str, float] = {}

    def _emit(reason, pts, category, detail="") -> None:
        if pts <= 0:
            return
        pts = round(pts, 2)
        entry: Dict[str, Any] = {"reason": reason, "points": -pts}
        if detail:
            entry["detail"] = detail
        deductions.append(entry)
        category_totals[category] = round(category_totals.get(category, 0.0) + pts, 2)

    # 1. Missing values
    missing_cells = int(df.isnull().sum().sum())
    missing_ratio: float = missing_cells / cells
    missing_pct: float   = round(missing_ratio * 100, 1)
    missing_pen: float   = round(min(missing_ratio * 30.0, 30.0), 2)
    if missing_pen > 0:
        _emit(f"Missing values ({missing_pct}% of cells)", missing_pen, "Completeness",
              f"{missing_cells:,} missing cells across {cols} columns")

    # 2. Duplicate rows - cast to plain bool to avoid numpy boolean subtract error
    dup_count = int(df.duplicated(keep="first").astype(bool).sum())
    dup_ratio: float = dup_count / rows
    dup_pct: float   = round(dup_ratio * 100, 1)
    dup_pen: float   = round(min(dup_ratio * 20.0, 20.0), 2)
    if dup_pen > 0:
        _emit(f"Duplicate rows ({dup_pct}% of rows)", dup_pen, "Duplicates",
              f"{dup_count:,} exact duplicate rows")

    # 3. All other issue types
    type_accum:  Dict[str, float]     = {}
    type_detail: Dict[str, List[str]] = {}

    for issue in issues:
        itype = issue.get("type", "")
        count: Any | int = issue.get("count", 0) or 0
        col: Any | None   = issue.get("column")
        sev   = issue.get("severity", "medium")

        if itype in ("missing_values", "duplicate_rows"):
            continue

        cfg_key: Any | str = "outlier" if "outlier" in itype else itype
        cfg = _TYPE_CFG.get(cfg_key)
        if cfg is None:
            continue

        category, per_col_pen, cap = cfg
        sev_mult: float = _SEV.get(sev, 0.6)

        if cfg_key in _RATIO_SCALED:
            denom: int = rows
            if col and col in df.columns:
                denom: int = max(len(df[col].dropna()), 1)
            ratio: Any | float = min(count / denom, 1.0)
            pen   = ratio * (_RATIO_MULT.get(cfg_key, per_col_pen) or 1.0) * (sev_mult or 1.0)
        else:
            pen = per_col_pen * sev_mult

        type_accum[cfg_key] = type_accum.get(cfg_key, 0.0) + pen
        detail_str: str = f"col '{col}'" if col else ""
        if detail_str:
            type_detail.setdefault(cfg_key, [])
            if detail_str not in type_detail[cfg_key]:
                type_detail[cfg_key].append(detail_str)

    for cfg_key, raw_pen in type_accum.items():
        cfg = _TYPE_CFG.get(cfg_key)
        if not cfg:
            continue
        category, _, cap = cfg
        capped: float     = round(min(raw_pen, cap), 2)
        details: List[str]    = type_detail.get(cfg_key, [])
        detail_str: str = ("; ".join(details[:5]) + ("…" if len(details) > 5 else "")) if details else ""
        reason: str     = _TYPE_LABELS.get(cfg_key, cfg_key.replace("_", " ").title())
        _emit(reason, capped, category, detail_str)

    total_pen: int = sum(abs(d["points"]) for d in deductions)
    score: float     = max(0.0, round(100.0 - total_pen, 1))
    grade: str     = _grade(score)
    deductions.sort(key=lambda d: d["points"])

    issue_type_counts: Dict[str, int] = {}
    for iss in issues:
        t = iss.get("type", "unknown")
        issue_type_counts[t] = issue_type_counts.get(t, 0) + 1

    return {
        "score":             score,
        "grade":             grade,
        "deductions":        deductions,
        "breakdown":         {k: round(v, 2) for k, v in sorted(category_totals.items(), key=lambda x: -x[1])},
        "total_issues":      len(issues),
        "missing_pct":       missing_pct,
        "duplicate_pct":     dup_pct,
        "issue_type_counts": issue_type_counts,
    }


def _grade(score: float) -> str:
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 70: return "C"
    if score >= 60: return "D"
    return "F"
