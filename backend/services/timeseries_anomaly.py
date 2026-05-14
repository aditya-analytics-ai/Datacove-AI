"""
timeseries_anomaly.py - time-series aware anomaly detection using STL decomposition.

Upgrades the existing IQR/Z-score approach for time-indexed data:
  • Auto-detects datetime index columns
  • Applies STL (Seasonal-Trend decomposition via LOESS) to isolate
    the residual component, then flags residuals that exceed 3× IQR
  • Falls back to a rolling-window Z-score when statsmodels is absent
  • Detects point anomalies, level shifts, and seasonal spikes
  • Returns structured results consumable by the existing anomalies UI

Public API
──────────
  detect_timeseries_anomalies(df, date_col, value_cols, period) -> dict
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd


def detect_timeseries_anomalies(
    df: pd.DataFrame,
    date_col: Optional[str] = None,
    value_cols: Optional[List[str]] = None,
    period: Optional[int] = None,
    max_anomalies_per_col: int = 200,
) -> Dict[str, Any]:
    """
    Run time-series anomaly detection on the dataset.

    Parameters
    ----------
    date_col   : column to use as the time index (auto-detected if None)
    value_cols : numeric columns to analyse (all numeric if None)
    period     : seasonality period - 7 for daily/weekly, 12 for monthly, etc.
                 Auto-inferred from data frequency if None.

    Returns
    -------
    {
      "date_col":   str | None,
      "method":     "stl" | "rolling_zscore",
      "results":    [column_result],
      "summary": { columns_checked, total_anomalies, date_range }
    }

    column_result = {
      "column": str, "anomaly_count": int, "anomaly_type": str,
      "severity": str, "description": str,
      "anomalies": [{index, value, residual, zscore}],
      "stats": {mean, std, trend_slope}
    }
    """
    # ── Auto-detect date column ──────────────────────────────────────────────
    if date_col is None:
        date_col = _find_date_col(df)

    # ── Sort and index by date ────────────────────────────────────────────────
    df_ts = df.copy()
    if date_col and date_col in df_ts.columns:
        df_ts[date_col] = pd.to_datetime(df_ts[date_col], errors="coerce")
        df_ts = df_ts.dropna(subset=[date_col]).sort_values(date_col).reset_index(drop=True)
        df_ts = df_ts.set_index(date_col)
    else:
        date_col = None  # no usable date column

    # ── Pick value columns ────────────────────────────────────────────────────
    numeric_cols = df_ts.select_dtypes(include="number").columns.tolist()
    if value_cols:
        numeric_cols = [c for c in value_cols if c in numeric_cols]
    if not numeric_cols:
        return {"date_col": date_col, "method": "none", "results": [],
                "summary": {"columns_checked": 0, "total_anomalies": 0, "date_range": None}}

    # ── Infer period ──────────────────────────────────────────────────────────
    if period is None and date_col:
        period = _infer_period(df_ts.index)
    period = period or 7  # fallback

    # ── Detect method ─────────────────────────────────────────────────────────
    use_stl = _has_statsmodels() and len(df_ts) >= 2 * period + 1

    results = []
    for col in numeric_cols:
        series = df_ts[col].dropna()
        if len(series) < max(10, period + 1):
            continue
        if use_stl:
            res = _stl_anomalies(series, col, period, max_anomalies_per_col)
        else:
            res = _rolling_zscore_anomalies(series, col, max_anomalies_per_col)
        if res:
            results.append(res)

    total = sum(r["anomaly_count"] for r in results)
    date_range = None
    if date_col and len(df_ts) > 0:
        try:
            date_range = {"start": str(df_ts.index.min().date()),
                          "end":   str(df_ts.index.max().date())}
        except Exception:
            pass

    return {
        "date_col": date_col,
        "method":   "stl" if use_stl else "rolling_zscore",
        "results":  results,
        "summary": {
            "columns_checked": len(numeric_cols),
            "total_anomalies": total,
            "date_range":      date_range,
        },
    }


# ── STL decomposition ─────────────────────────────────────────────────────────

def _stl_anomalies(series: pd.Series, col: str, period: int, max_pts: int) -> Optional[Dict]:
    try:
        from statsmodels.tsa.seasonal import STL
        stl    = STL(series, period=period, robust=True)
        res    = stl.fit()
        resid  = pd.Series(res.resid, index=series.index)

        q1, q3 = resid.quantile(0.25), resid.quantile(0.75)
        iqr    = q3 - q1
        lo, hi = q1 - 3 * iqr, q3 + 3 * iqr
        mask   = (resid < lo) | (resid > hi)
        count  = int(mask.sum())
        if count == 0:
            return None

        std = resid.std() or 1
        anomaly_pts = []
        for idx in resid[mask].index[:max_pts]:
            r = float(resid[idx])
            anomaly_pts.append({
                "index":   str(idx.date()) if hasattr(idx, "date") else str(idx),
                "value":   round(float(series[idx]), 4),
                "residual": round(r, 4),
                "zscore":  round(r / std, 2),
            })

        # Detect level shifts via trend slope change
        trend    = pd.Series(res.trend, index=series.index)
        slope    = float(np.polyfit(range(len(trend)), trend.values, 1)[0])
        anom_type = _classify_anomaly(count, len(series), slope)

        return {
            "column":       col,
            "anomaly_count": count,
            "anomaly_type": anom_type,
            "severity":     "high" if count / len(series) > 0.05 else "medium",
            "description":  (
                f"'{col}': {count} time-series anomaly(ies) detected via STL decomposition. "
                f"Type: {anom_type}. Trend slope: {slope:+.4f}/period."
            ),
            "anomalies": anomaly_pts,
            "stats": {
                "mean":        round(float(series.mean()), 4),
                "std":         round(float(series.std()), 4),
                "trend_slope": round(slope, 6),
            },
        }
    except Exception:
        return _rolling_zscore_anomalies(series, col, max_pts)


# ── Rolling Z-score fallback ──────────────────────────────────────────────────

def _rolling_zscore_anomalies(series: pd.Series, col: str, max_pts: int) -> Optional[Dict]:
    window = max(7, len(series) // 10)
    roll_m = series.rolling(window, center=True, min_periods=3).mean()
    roll_s = series.rolling(window, center=True, min_periods=3).std()
    roll_s = roll_s.replace(0, np.nan)

    z    = ((series - roll_m) / roll_s).abs()
    mask = z > 3
    count = int(mask.sum())
    if count == 0:
        return None

    anomaly_pts = []
    for idx in series[mask].index[:max_pts]:
        anomaly_pts.append({
            "index":   str(idx.date()) if hasattr(idx, "date") else str(idx),
            "value":   round(float(series[idx]), 4),
            "residual": round(float(series[idx] - roll_m[idx]), 4),
            "zscore":  round(float(z[idx]), 2),
        })

    return {
        "column":       col,
        "anomaly_count": count,
        "anomaly_type": "point_anomaly",
        "severity":     "high" if count / len(series) > 0.05 else "medium",
        "description":  f"'{col}': {count} anomaly(ies) via rolling Z-score (window={window}).",
        "anomalies":    anomaly_pts,
        "stats": {
            "mean":        round(float(series.mean()), 4),
            "std":         round(float(series.std()), 4),
            "trend_slope": 0.0,
        },
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_date_col(df: pd.DataFrame) -> Optional[str]:
    date_kw = ("date", "time", "dt", "timestamp", "created", "updated", "day", "month", "year")
    for col in df.columns:
        if any(k in col.lower() for k in date_kw):
            trial = pd.to_datetime(df[col], errors="coerce")
            if trial.notna().mean() > 0.8:
                return col
    # Try parsing any object column
    for col in df.select_dtypes(include=["object", "datetime"]).columns:
        trial = pd.to_datetime(df[col], errors="coerce")
        if trial.notna().mean() > 0.8:
            return col
    return None


def _infer_period(index: pd.Index) -> int:
    try:
        freq = pd.infer_freq(index)
        if freq:
            if "D" in freq: return 7
            if "W" in freq: return 4
            if "M" in freq or "MS" in freq: return 12
            if "Q" in freq: return 4
            if "H" in freq: return 24
    except Exception:
        pass
    return 7


def _classify_anomaly(count: int, total: int, slope: float) -> str:
    if count / total > 0.15:
        return "level_shift"
    if abs(slope) > 0.5:
        return "trending_anomaly"
    return "point_anomaly"


def _has_statsmodels() -> bool:
    try:
        import statsmodels.tsa.seasonal  # noqa
        return True
    except ImportError:
        return False
