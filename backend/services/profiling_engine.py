"""
Profiling engine - generates column-level and dataset-level statistics.
"""

from typing import Any, Dict, List, Optional
import pandas as pd
import numpy as np
from pandas import Series
from utils.validation_utils import is_valid_email, is_valid_phone, looks_like_date


def profile_dataset(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Returns full dataset profile including per-column stats.
    """
    rows, cols = df.shape
    duplicate_count = int(df.duplicated().sum())

    columns_profile = []
    for col in df.columns:
        columns_profile.append(_profile_column(df, col))

    return {
        "rows": rows,
        "columns": cols,
        "duplicate_rows": duplicate_count,
        "duplicate_pct": round(duplicate_count / max(rows, 1) * 100, 2),
        "total_missing": int(df.isnull().sum().sum()),
        "columns_profile": columns_profile,
    }


def _profile_column(df: pd.DataFrame, col: str) -> Dict[str, Any]:
    series: Series[Any] = df[col]
    total: int = len(series)
    missing_count = int(series.isnull().sum())
    missing_pct: float = round(missing_count / max(total, 1) * 100, 2)
    unique_count = int(series.nunique())

    # Infer semantic type
    detected_type: str = _detect_semantic_type(series)

    # Value distribution (top 10 most frequent)
    value_counts: Series[int] = series.dropna().value_counts().head(10)
    distribution = [{"value": str(k), "count": int(v)} for k, v in value_counts.items()]

    # Numeric stats (with percentiles for outlier visualization)
    numeric_stats = {}
    if pd.api.types.is_numeric_dtype(series):
        # Cast boolean columns to int64 BEFORE quantile/sparkline calls.
        # bool dtype passes is_numeric_dtype() but numpy's quantile uses
        # linear interpolation (b - a) which crashes on boolean arrays.
        if series.dtype == bool or str(series.dtype) == "boolean":
            clean: Series[Any] = series.dropna().astype("int64")
        else:
            clean: Series[Any] = series.dropna()
        numeric_stats = {
            "min": _safe_num(series.min()),
            "max": _safe_num(series.max()),
            "mean": _safe_num(series.mean()),
            "std": _safe_num(series.std()),
            "median": _safe_num(series.median()),
            "p5": _safe_num(clean.quantile(0.05)) if len(clean) else None,
            "p25": _safe_num(clean.quantile(0.25)) if len(clean) else None,
            "p75": _safe_num(clean.quantile(0.75)) if len(clean) else None,
            "p95": _safe_num(clean.quantile(0.95)) if len(clean) else None,
            # 8-bar sparkline histogram for outlier visualization
            "sparkline": _compute_sparkline(clean),
        }

    # Invalid email/phone counts
    invalid_format_count = 0
    if detected_type == "email":
        invalid_format_count = int(
            series.dropna().apply(lambda x: not is_valid_email(str(x))).sum()
        )
    elif detected_type == "phone":
        invalid_format_count = int(
            series.dropna().apply(lambda x: not is_valid_phone(str(x))).sum()
        )

    # Whitespace issues
    whitespace_count = 0
    if series.dtype == object:
        whitespace_count = int(
            series.dropna()
            .apply(lambda x: str(x) != str(x).strip() or "  " in str(x))
            .sum()
        )

    # Mixed type detection (numeric column with string values)
    mixed_types = False
    if detected_type == "numeric" and series.dtype == object:
        non_numeric = (
            series.dropna()
            .apply(
                lambda x: not str(x).replace(".", "", 1).replace("-", "", 1).isdigit()
            )
            .sum()
        )
        mixed_types: bool = int(non_numeric) > 0

    return {
        "column": col,
        "dtype": str(series.dtype),
        "detected_type": detected_type,
        "total": total,
        "missing_count": missing_count,
        "missing_pct": missing_pct,
        "unique_count": unique_count,
        "distribution": distribution,
        "numeric_stats": numeric_stats,
        "invalid_format_count": invalid_format_count,
        "whitespace_count": whitespace_count,
        "mixed_types": mixed_types,
    }


def _detect_semantic_type(series: pd.Series) -> str:
    """Heuristic semantic type detection."""
    col_lower = str(series.name).lower() if series.name else ""
    sample: List[str] = series.dropna().astype(str).head(100).tolist()

    if pd.api.types.is_numeric_dtype(series):
        return "numeric"

    # Email heuristic
    if "email" in col_lower or "e-mail" in col_lower:
        return "email"
    if (
        sample
        and sum(is_valid_email(v) for v in sample[:30]) / max(len(sample[:30]), 1) > 0.7
    ):
        return "email"

    # Phone heuristic
    if any(k in col_lower for k in ("phone", "mobile", "tel", "contact")):
        return "phone"

    # Date heuristic
    if any(k in col_lower for k in ("date", "time", "dob", "created", "updated")):
        return "date"
    if sample and looks_like_date(sample):
        return "date"

    # Country / city heuristic
    if any(k in col_lower for k in ("country", "nation")):
        return "country"
    if any(k in col_lower for k in ("city", "town", "region")):
        return "city"

    # Currency heuristic
    if any(k in col_lower for k in ("price", "amount", "salary", "revenue", "cost")):
        return "currency"

    return "text"


def _compute_sparkline(clean: pd.Series, bins: int = 8) -> List[float]:
    """
    Return an 8-bar normalised histogram suitable for a sparkline.
    Values are normalised to [0, 1] relative to the tallest bar.
    Returns an empty list if there are fewer than 2 non-null values.
    """
    if len(clean) < 2:
        return []
    try:
        counts, _ = np.histogram(clean.dropna(), bins=bins)
        max_count = counts.max()
        if max_count == 0:
            return [0.0] * bins
        return [round(float(c) / float(max_count), 4) for c in counts]
    except Exception:
        return []


def _safe_num(val) -> Optional[float]:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    return round(float(val), 4)
