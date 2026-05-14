"""
preview.py - safe DataFrame → JSON-records serialisation.

Plain  df.fillna("").astype(str)  crashes with:
  "Invalid value '' for dtype Int64"
when the DataFrame contains pandas nullable extension types (Int64, BooleanDtype,
StringDtype, etc.).  These types cannot hold an empty string before the astype(str)
converts them.

_safe_preview() converts extension-array columns to plain Python objects first,
making NaN → None, then fillna("") replaces None with "", then astype(str) works.
"""

from __future__ import annotations
import pandas as pd
import numpy as np


def _sanitize_value(val):
    """Convert NaN, Inf, -Inf, Timestamp to JSON-serializable types."""
    if isinstance(val, float):
        if np.isnan(val) or np.isinf(val):
            return None
    if isinstance(val, pd.Timestamp):
        return val.isoformat()
    return val


def safe_preview(df: pd.DataFrame, n: int = 100) -> list:
    """Return the first *n* rows as a list of dicts, safe for JSON serialisation."""
    df2 = df.head(n).copy()
    for col in df2.columns:
        if pd.api.types.is_extension_array_dtype(df2[col]):
            df2[col] = df2[col].astype(object)
    records = df2.fillna("").to_dict(orient="records")
    sanitized = []
    for record in records:
        sanitized_record = {k: _sanitize_value(v) for k, v in record.items()}
        sanitized.append(sanitized_record)
    return sanitized


def ext_to_object(df: pd.DataFrame) -> pd.DataFrame:
    """Convert all extension-array dtype columns to plain object dtype.
    Use before any fillna(string_value) call to prevent
    'Invalid value for dtype Int64' errors."""
    df2 = df.copy()
    for col in df2.columns:
        if pd.api.types.is_extension_array_dtype(df2[col]):
            df2[col] = df2[col].astype(object)
    return df2
