"""
correlation_engine.py - cross-column correlation analysis.
Pearson / Spearman (numeric) · Cramér's V (categorical, pure NumPy chi²).
"""
from __future__ import annotations
import itertools
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

_MAX_COLS = 40
_MAX_CAT_CARDINALITY = 30


def detect_correlations(df: pd.DataFrame, method: str = "auto", threshold: float = 0.3) -> Dict[str, Any]:
    df = _prepare(df)
    if len(df.columns) > _MAX_COLS:
        num_c = df.select_dtypes(include="number").columns.tolist()[:_MAX_COLS // 2]
        cat_c = [c for c in df.select_dtypes(include=["object","category"]).columns if c not in num_c][:_MAX_COLS // 2]
        df = df[(num_c + cat_c)[:_MAX_COLS]]

    num_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = [c for c in df.columns if c not in num_cols and 2 <= df[c].nunique() <= _MAX_CAT_CARDINALITY]

    resolved = method
    if method == "auto":
        resolved = "pearson" if len(num_cols) >= len(cat_cols) else "cramers_v"

    if resolved in ("pearson", "spearman"):
        cols, matrix = _numeric_matrix(df, num_cols, resolved)
    elif resolved == "cramers_v":
        cols, matrix = _cramers_matrix(df, cat_cols)
    else:
        raise ValueError(f"Unknown method: {method!r}")

    col_types = {c: ("numeric" if c in num_cols else "categorical") for c in cols}
    strong_pairs = _extract_pairs(cols, matrix, threshold)
    flat = [abs(v) for row in matrix for v in row if v is not None and not np.isnan(v) and v != 1.0]

    return {
        "method": resolved, "columns": cols, "matrix": matrix,
        "strong_pairs": strong_pairs, "column_types": col_types,
        "summary": {
            "total_pairs": len(cols) * (len(cols) - 1) // 2,
            "strong_pairs_count": len(strong_pairs),
            "max_correlation": round(max(flat), 4) if flat else 0.0,
            "mean_correlation": round(float(np.mean(flat)), 4) if flat else 0.0,
            "columns_analysed": len(cols),
        },
    }


def _numeric_matrix(df, num_cols, method):
    if not num_cols:
        return [], []
    sub  = df[num_cols].dropna(axis=1, how="all")
    cols = sub.columns.tolist()
    corr = sub.corr(method=method)
    matrix = [[None if pd.isna(corr.loc[r, c]) else round(float(corr.loc[r, c]), 4) for c in cols] for r in cols]
    return cols, matrix


def _cramers_matrix(df, cat_cols):
    if not cat_cols:
        return [], []
    n   = len(cat_cols)
    mat = [[None] * n for _ in range(n)]
    for i in range(n): mat[i][i] = 1.0
    for i, j in itertools.combinations(range(n), 2):
        v = _cramers_v(df[cat_cols[i]], df[cat_cols[j]])
        mat[i][j] = mat[j][i] = v
    return cat_cols, mat


def _cramers_v(x, y):
    try:
        mask = x.notna() & y.notna()
        x, y = x[mask].astype(str), y[mask].astype(str)
        if len(x) < 5: return None
        ct  = pd.crosstab(x, y)
        obs = ct.values.astype(float)
        rs  = obs.sum(axis=1, keepdims=True); cs = obs.sum(axis=0, keepdims=True); tot = obs.sum()
        if tot == 0: return None
        exp = rs @ cs / tot
        chi2 = float(np.where(exp > 0, (obs - exp) ** 2 / exp, 0.0).sum())
        r, k = ct.shape
        denom = tot * (min(r, k) - 1)
        if denom <= 0: return None
        return round(min(float(np.sqrt(chi2 / denom)), 1.0), 4)
    except Exception:
        return None


def _extract_pairs(cols, matrix, threshold):
    pairs = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            v = matrix[i][j]
            if v is None or np.isnan(v) or abs(v) < threshold: continue
            pairs.append({
                "col_a": cols[i], "col_b": cols[j],
                "correlation": v, "abs_correlation": round(abs(v), 4),
                "strength": _strength(abs(v)),
                "direction": "positive" if v > 0 else "negative",
            })
    return sorted(pairs, key=lambda p: -p["abs_correlation"])


def _strength(r):
    if r >= 0.8: return "very strong"
    if r >= 0.6: return "strong"
    if r >= 0.4: return "moderate"
    if r >= 0.2: return "weak"
    return "negligible"


def _prepare(df):
    df = df.copy().dropna(axis=1, how="all")
    for col in df.select_dtypes(include="object").columns:
        c = pd.to_numeric(df[col], errors="coerce")
        if c.notna().mean() > 0.8: df[col] = c
    return df
