"""
visualization_engine.py - auto-generates chart data from a profiled DataFrame.

Returns JSON-serialisable chart specs consumed by the frontend VisualizationDashboard.
No external charting dependency - all computation is in Python/pandas;
the frontend renders using Recharts (already installed).

Chart types generated:
  histogram      - numeric columns (bar chart of bins)
  bar            - categorical columns (top-N value counts)
  timeseries     - date columns × numeric columns
  correlation    - heatmap matrix for numeric columns
  missing_heatmap - % missing per column
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


# ── Public entry point ────────────────────────────────────────────────────────

def generate_charts(df: pd.DataFrame, max_charts: int = 12) -> Dict[str, Any]:
    """
    Analyse df and return a dict of chart specs ready for Recharts rendering.
    """
    charts: List[Dict[str, Any]] = []

    numeric_cols  = df.select_dtypes(include=[np.number]).columns.tolist()
    object_cols   = df.select_dtypes(include=["object"]).columns.tolist()
    date_cols     = _detect_date_columns(df)

    # 1) Histograms for numeric columns (up to 6)
    for col in numeric_cols[:6]:
        chart = _histogram(df[col], col)
        if chart:
            charts.append(chart)

    # 2) Bar charts for categorical columns (up to 4)
    for col in object_cols[:4]:
        chart = _bar_chart(df[col], col)
        if chart:
            charts.append(chart)

    # 3) Time series - first date col × first 3 numeric cols
    if date_cols and numeric_cols:
        ts = _timeseries(df, date_cols[0], numeric_cols[:3])
        if ts:
            charts.append(ts)

    # 4) Correlation heatmap (if ≥ 2 numeric cols)
    if len(numeric_cols) >= 2:
        corr = _correlation_heatmap(df[numeric_cols[:10]])
        if corr:
            charts.append(corr)

    # 5) Missing values bar chart
    missing = _missing_bar(df)
    if missing:
        charts.append(missing)

    return {
        "charts": charts[:max_charts],
        "numeric_cols":  numeric_cols,
        "object_cols":   object_cols,
        "date_cols":     date_cols,
        "total_charts":  len(charts),
    }



def suggest_visualizations(df, profile=None):
    """
    Wrapper around generate_charts for use by the AI orchestrator.
    Returns just the charts list.
    """
    result = generate_charts(df, max_charts=12)
    return result.get("charts", [])


# ── Chart builders ────────────────────────────────────────────────────────────

def _histogram(series: pd.Series, col: str, bins: int = 20) -> Optional[Dict[str, Any]]:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if len(clean) < 3:
        return None
    counts, edges = np.histogram(clean, bins=bins)
    data = [
        {
            "bin":   f"{edges[i]:.2g}-{edges[i+1]:.2g}",
            "count": int(counts[i]),
            "start": round(float(edges[i]), 4),
            "end":   round(float(edges[i+1]), 4),
        }
        for i in range(len(counts))
    ]
    return {
        "type":    "histogram",
        "title":   f"{col} - Distribution",
        "column":  col,
        "data":    data,
        "x_key":   "bin",
        "y_keys":  ["count"],
        "color":   "#6366f1",
        "stats": {
            "mean":   round(float(clean.mean()), 4),
            "median": round(float(clean.median()), 4),
            "std":    round(float(clean.std()), 4),
            "min":    round(float(clean.min()), 4),
            "max":    round(float(clean.max()), 4),
        },
    }


def _bar_chart(series: pd.Series, col: str, top_n: int = 15) -> Optional[Dict[str, Any]]:
    non_null = series.dropna()
    if len(non_null) == 0:
        return None
    unique_count = non_null.nunique()
    if unique_count > 200:  # skip near-unique / ID columns
        return None
    counts = non_null.astype(str).value_counts().head(top_n)
    data   = [{"value": k, "count": int(v)} for k, v in counts.items()]
    return {
        "type":   "bar",
        "title":  f"{col} - Top {min(top_n, len(data))} Values",
        "column": col,
        "data":   data,
        "x_key":  "value",
        "y_keys": ["count"],
        "color":  "#10b981",
    }


def _timeseries(
    df: pd.DataFrame,
    date_col: str,
    value_cols: List[str],
) -> Optional[Dict[str, Any]]:
    try:
        df2 = df[[date_col] + value_cols].copy()
        df2[date_col] = pd.to_datetime(df2[date_col], errors="coerce")
        df2 = df2.dropna(subset=[date_col])
        if len(df2) < 3:
            return None
        df2 = df2.sort_values(date_col)
        # Resample to reasonable granularity
        date_range = (df2[date_col].max() - df2[date_col].min()).days
        if date_range > 365 * 2:
            freq = "ME"     # monthly
        elif date_range > 60:
            freq = "W"      # weekly
        else:
            freq = "D"      # daily

        df2 = df2.set_index(date_col)
        agg_cols = [c for c in value_cols if pd.api.types.is_numeric_dtype(df2[c])]
        if not agg_cols:
            return None
        df2 = df2[agg_cols].resample(freq).mean().round(4).reset_index()
        df2[date_col] = df2[date_col].dt.strftime("%Y-%m-%d")

        data = df2.fillna(0).to_dict(orient="records")
        colors = ["#6366f1", "#10b981", "#f59e0b"]

        return {
            "type":    "timeseries",
            "title":   f"Trend over {date_col}",
            "column":  date_col,
            "data":    data,
            "x_key":   date_col,
            "y_keys":  agg_cols,
            "colors":  colors[:len(agg_cols)],
        }
    except Exception:
        return None


def _correlation_heatmap(numeric_df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    try:
        clean = numeric_df.dropna(thresh=int(len(numeric_df) * 0.5))
        if len(clean) < 5 or len(clean.columns) < 2:
            return None
        corr = clean.corr().round(3)
        cols  = list(corr.columns)
        cells = []
        for row in cols:
            for col in cols:
                val = corr.at[row, col]
                if not np.isnan(val):
                    cells.append({"row": row, "col": col, "value": float(val)})
        return {
            "type":    "heatmap",
            "title":   "Correlation Matrix",
            "columns": cols,
            "data":    cells,
        }
    except Exception:
        return None


def _missing_bar(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    missing_pct = (df.isnull().sum() / max(len(df), 1) * 100).round(2)
    data = [
        {"column": col, "missing_pct": float(pct)}
        for col, pct in missing_pct.items()
        if pct > 0
    ]
    if not data:
        return None
    data.sort(key=lambda x: -x["missing_pct"])
    return {
        "type":   "bar",
        "title":  "Missing Values (%) by Column",
        "column": None,
        "data":   data[:20],
        "x_key":  "column",
        "y_keys": ["missing_pct"],
        "color":  "#ef4444",
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

_DATE_KEYWORDS = ("date", "time", "created", "updated", "dob", "birth", "dt_", "timestamp")

def _detect_date_columns(df: pd.DataFrame) -> List[str]:
    date_cols = []
    for col in df.columns:
        col_lower = col.lower()
        if any(k in col_lower for k in _DATE_KEYWORDS):
            date_cols.append(col)
            continue
        # Try parsing a sample
        sample = df[col].dropna().head(20)
        if len(sample) == 0:
            continue
        try:
            parsed = pd.to_datetime(sample, errors="coerce")
            if parsed.notna().mean() > 0.8:
                date_cols.append(col)
        except Exception:
            pass
    return date_cols
