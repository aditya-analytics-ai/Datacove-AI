"""
Anomaly detector - statistical outlier detection using IQR, Z-score,
IsolationForest, text patterns, and domain-specific detection.
"""

from typing import Any, Dict, List, Optional
import pandas as pd
import numpy as np
from pandas import Series
import re


def detect_anomalies(df: pd.DataFrame, domain: str = None) -> Dict[str, Any]:
    """
    Detect statistical outliers and anomalies in all columns.
    Returns comprehensive anomaly report.
    """
    anomalies = []
    numeric_cols: List[str] = df.select_dtypes(include=[np.number]).columns.tolist()
    text_cols: List[str] = df.select_dtypes(include=["object"]).columns.tolist()

    for col in numeric_cols:
        series: Series[Any] = df[col].dropna()
        if len(series) < 10:
            continue

        iqr_result: Dict[str, Any] = _detect_iqr(series, col)
        zscore_result: Dict[str, Any] = _detect_zscore(series, col)
        isolation_result: Dict[str, Any] | None = _detect_isolation_forest(
            df[numeric_cols].dropna(), col
        )

        max_count = max(
            iqr_result.get("outlier_count", 0),
            zscore_result.get("outlier_count", 0),
            isolation_result.get("outlier_count", 0) if isolation_result else 0,
        )
        if max_count == 0:
            continue

        candidates = [r for r in [iqr_result, zscore_result, isolation_result] if r]
        primary = max(candidates, key=lambda r: r.get("outlier_count", 0))
        methods_ran: List[str] = ["IQR", "Z-score"]
        if isolation_result is not None:
            methods_ran.append("IsolationForest")
        primary["methods"] = methods_ran
        anomalies.append(primary)

    for col in text_cols:
        text_anomalies = _detect_text_anomalies(df[col], col)
        anomalies.extend(text_anomalies)

    if domain == "healthcare":
        anomalies.extend(_detect_healthcare_anomalies(df))
    elif domain == "financial":
        anomalies.extend(_detect_financial_anomalies(df))

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if len(numeric_cols) > 0 and len(df) >= 30:
        df_numeric = df[numeric_cols].dropna()
        if len(df_numeric) >= 30:
            for col in numeric_cols[:5]:
                cluster_result = _detect_clustering_anomalies(df_numeric, col)
                if cluster_result:
                    anomalies.append(cluster_result)

                statistical_result = _detect_statistical_anomalies(df_numeric, col)
                if statistical_result:
                    anomalies.append(statistical_result)

    pattern_anomalies = _detect_pattern_sequences(df, domain)
    anomalies.extend(pattern_anomalies)

    return {
        "total_anomalies": len(anomalies),
        "anomalies": anomalies,
        "high_severity": sum(1 for a in anomalies if a.get("severity") == "high"),
        "medium_severity": sum(1 for a in anomalies if a.get("severity") == "medium"),
    }


def _detect_text_anomalies(series: Series, col: str) -> List[Dict[str, Any]]:
    """Detect anomalies in text columns."""
    anomalies = []
    data = series.dropna().astype(str)

    if len(data) < 10:
        return anomalies

    lengths = data.str.len()
    mean_len = lengths.mean()
    std_len = lengths.std()

    if std_len > 0:
        z_scores = np.abs((lengths - mean_len) / std_len)
        unusual_length = data[z_scores > 2]
        if len(unusual_length) > 0 and len(unusual_length) / len(data) < 0.1:
            anomalies.append(
                {
                    "column": col,
                    "type": "unusual_length",
                    "severity": "medium",
                    "count": len(unusual_length),
                    "sample_values": unusual_length.head(5).tolist(),
                    "description": f"Unusual string length detected",
                }
            )

    suspicious = data[
        data.str.contains(r"[<>\"']|test|fake|sample", case=False, na=False)
    ]
    if len(suspicious) > 0:
        anomalies.append(
            {
                "column": col,
                "type": "suspicious_content",
                "severity": "medium",
                "count": len(suspicious),
                "sample_values": suspicious.head(5).tolist(),
                "description": f"Suspicious content detected",
            }
        )

    return anomalies


def _detect_healthcare_anomalies(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Detect healthcare-specific anomalies."""
    anomalies = []

    for col in df.columns:
        if "icd" in col.lower():
            data = df[col].dropna().astype(str)
            invalid = data[~data.str.match(r"^[A-Z]\d{2}(\.\d{1,2})?$", na=False)]
            if len(invalid) > 0:
                anomalies.append(
                    {
                        "column": col,
                        "type": "invalid_icd_code",
                        "severity": "high",
                        "count": len(invalid),
                        "sample_values": invalid.head(5).tolist(),
                        "description": "Invalid ICD code format",
                    }
                )

        if "ssn" in col.lower() or "social" in col.lower():
            data = df[col].dropna().astype(str)
            invalid = data[~data.str.match(r"^\d{3}-\d{2}-\d{4}$", na=False)]
            if len(invalid) > 0:
                anomalies.append(
                    {
                        "column": col,
                        "type": "invalid_ssn_format",
                        "severity": "high",
                        "count": len(invalid),
                        "sample_values": invalid.head(5).tolist(),
                        "description": "Invalid SSN format",
                    }
                )

    return anomalies


def _detect_financial_anomalies(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Detect financial-specific anomalies."""
    anomalies = []

    for col in df.columns:
        col_lower = col.lower()
        if any(kw in col_lower for kw in ["amount", "price", "cost", "balance"]):
            data = pd.to_numeric(df[col], errors="coerce").dropna()

            if len(data) > 0:
                negative = data[data < 0]
                if len(negative) > 0:
                    anomalies.append(
                        {
                            "column": col,
                            "type": "negative_amount",
                            "severity": "high",
                            "count": len(negative),
                            "sample_values": negative.head(5).tolist(),
                            "description": "Negative financial value detected",
                        }
                    )

                extreme = data[data > data.quantile(0.99) * 10]
                if len(extreme) > 0:
                    anomalies.append(
                        {
                            "column": col,
                            "type": "extreme_amount",
                            "severity": "medium",
                            "count": len(extreme),
                            "sample_values": extreme.head(5).tolist(),
                            "description": "Extremely large value detected",
                        }
                    )

    return anomalies


# ── IQR method ────────────────────────────────────────────────────────────────


def _detect_iqr(series: pd.Series, col: str) -> Dict[str, Any]:
    q1: float = series.quantile(0.25)
    q3: float = series.quantile(0.75)
    iqr: float = q3 - q1

    if iqr == 0:
        return {"column": col, "outlier_count": 0, "method": "IQR"}

    lower: float = q1 - 3.0 * iqr
    upper: float = q3 + 3.0 * iqr
    mask: Series[bool] = (series < lower) | (series > upper)
    count = int(mask.sum())

    return {
        "column": col,
        "method": "IQR",
        "outlier_count": count,
        "lower_bound": round(float(lower), 4),
        "upper_bound": round(float(upper), 4),
        "sample_values": [round(v, 4) for v in series[mask].tolist()[:10]],
        "severity": "high" if count > len(series) * 0.05 else "medium",
        "description": (
            f"'{col}': {count} outlier(s) detected via IQR "
            f"(expected range {lower:.2f} - {upper:.2f})."
        ),
    }


# ── Z-score method ────────────────────────────────────────────────────────────


def _detect_zscore(series: pd.Series, col: str) -> Dict[str, Any]:
    try:
        from scipy import stats

        z = np.abs(stats.zscore(series, nan_policy="omit"))  # type: ignore
    except ImportError:
        # Manual Z-score if scipy not installed
        mean, std = series.mean(), series.std()
        if std == 0:
            return {"column": col, "outlier_count": 0, "method": "Z-score"}
        z: np.ndarray[Any, Any] = np.abs((series - mean) / std)

    mask = z > 3
    count = int(mask.sum())

    return {
        "column": col,
        "method": "Z-score",
        "outlier_count": count,
        "sample_values": [round(v, 4) for v in series[mask].tolist()[:10]],
        "severity": "high" if count > len(series) * 0.05 else "medium",
        "description": f"'{col}': {count} outlier(s) detected via Z-score (|z| > 3).",
    }


# ── IsolationForest method ────────────────────────────────────────────────────


def _detect_isolation_forest(
    df_numeric: pd.DataFrame, col: str
) -> Optional[Dict[str, Any]]:
    """Optional - silently skipped if sklearn is unavailable."""
    try:
        from sklearn.ensemble import IsolationForest

        if len(df_numeric) < 20 or col not in df_numeric.columns:
            return None
        clf = IsolationForest(contamination=0.05, random_state=42)
        preds = clf.fit_predict(df_numeric[[col]])
        count = int((preds == -1).sum())
        return {
            "column": col,
            "method": "IsolationForest",
            "outlier_count": count,
            "sample_values": [],
            "severity": "high" if count > len(df_numeric) * 0.05 else "medium",
            "description": f"'{col}': {count} outlier(s) detected via IsolationForest.",
        }
    except Exception:
        return None


def _detect_clustering_anomalies(
    df_numeric: pd.DataFrame, col: str
) -> Optional[Dict[str, Any]]:
    """Detect anomalies using K-Means clustering - points far from centroids."""
    try:
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler

        if len(df_numeric) < 30 or col not in df_numeric.columns:
            return None

        data = df_numeric[[col]].dropna()
        if len(data) < 30:
            return None

        scaler = StandardScaler()
        scaled = scaler.fit_transform(data)

        kmeans = KMeans(n_clusters=min(3, len(data) // 10), random_state=42, n_init=10)
        labels = kmeans.fit_predict(scaled)

        distances = np.linalg.norm(scaled - kmeans.cluster_centers_[labels], axis=1)
        threshold = np.percentile(distances, 95)
        anomalies_mask = distances > threshold

        count = int(anomalies_mask.sum())
        if count == 0:
            return None

        return {
            "column": col,
            "method": "Clustering",
            "outlier_count": count,
            "sample_values": data[anomalies_mask].head(3).tolist(),
            "severity": "medium",
            "description": f"'{col}': {count} points far from cluster centroids.",
        }
    except Exception:
        return None


def _detect_statistical_anomalies(
    df_numeric: pd.DataFrame, col: str
) -> Optional[Dict[str, Any]]:
    """Detect anomalies using Grubbs' test for skewed distributions."""
    try:
        from scipy import stats

        if len(df_numeric) < 20 or col not in df_numeric.columns:
            return None

        data = df_numeric[col].dropna()
        if len(data) < 20:
            return None

        mean = data.mean()
        std = data.std()
        if std == 0:
            return None

        z_scores = np.abs((data - mean) / std)
        anomalies = z_scores > 3

        count = int(anomalies.sum())
        if count == 0:
            return None

        return {
            "column": col,
            "method": "GrubbsTest",
            "outlier_count": count,
            "sample_values": data[anomalies].head(3).tolist(),
            "severity": "high" if count > len(data) * 0.02 else "medium",
            "description": f"'{col}': {count} values beyond 3 standard deviations.",
        }
    except Exception:
        return None


def _detect_pattern_sequences(
    df: pd.DataFrame, domain: str = None
) -> List[Dict[str, Any]]:
    """Detect unusual patterns in sequential data."""
    anomalies = []

    for col in df.columns:
        if df[col].dtype == object:
            series = df[col].dropna().astype(str)
            if len(series) < 20:
                continue

            repeated_patterns = series.str.match(r"(.+?)\1{3,}")
            if repeated_patterns.sum() > 0:
                count = int(repeated_patterns.sum())
                anomalies.append(
                    {
                        "column": col,
                        "method": "PatternSequence",
                        "outlier_count": count,
                        "sample_values": series[repeated_patterns].head(3).tolist(),
                        "severity": "low",
                        "description": f"'{col}': {count} values with repeated character patterns.",
                    }
                )

            if "date" in col.lower() or "time" in col.lower():
                try:
                    dates = pd.to_datetime(series, errors="coerce")
                    valid_dates = dates.dropna()

                    if len(valid_dates) > 10:
                        future_dates = valid_dates[valid_dates > pd.Timestamp.now()]
                        if len(future_dates) > len(valid_dates) * 0.1:
                            anomalies.append(
                                {
                                    "column": col,
                                    "method": "FutureDate",
                                    "outlier_count": len(future_dates),
                                    "sample_values": future_dates.head(3)
                                    .astype(str)
                                    .tolist(),
                                    "severity": "medium",
                                    "description": f"'{col}': {len(future_dates)} future dates detected.",
                                }
                            )
                except:
                    pass

    return anomalies
