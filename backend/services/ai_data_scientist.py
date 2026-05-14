"""
AI Data Scientist - auto-detects target column, trains a model,
and returns evaluation metrics.
"""
from typing import Any, Dict, List, Optional
import pandas as pd
import numpy as np
from utils.logger import logger


def run_ai_data_scientist(
    df: pd.DataFrame,
    target_column: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Auto-ML workflow:
      1. Detect (or use provided) target column
      2. Detect problem type (classification / regression)
      3. Encode features
      4. Train model
      5. Return evaluation metrics

    Returns a result dict with model info and metrics.
    """
    try:
        from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
        from sklearn.model_selection import train_test_split
        from sklearn.preprocessing import LabelEncoder
        from sklearn.metrics import (
            accuracy_score, classification_report,
            mean_absolute_error, r2_score,
        )
    except ImportError:
        return {"error": "scikit-learn is required. Run: pip install scikit-learn"}

    logger.info("AI Data Scientist: starting")

    # ── 1. Detect target column ───────────────────────────────────────────────
    if target_column is None:
        target_column = _detect_target(df)
    if target_column not in df.columns:
        return {"error": f"Target column '{target_column}' not found in dataset."}

    logger.info(f"AI Data Scientist: target = '{target_column}'")

    # ── 2. Detect problem type ────────────────────────────────────────────────
    target_series = df[target_column].dropna()
    n_unique      = target_series.nunique()
    is_regression = pd.api.types.is_numeric_dtype(target_series) and n_unique > 10

    problem_type = "regression" if is_regression else "classification"
    logger.info(f"AI Data Scientist: problem type = {problem_type}")

    # ── 3. Prepare features ───────────────────────────────────────────────────
    df_clean = df.dropna(subset=[target_column]).copy()
    feature_cols = [c for c in df_clean.columns if c != target_column]

    # Drop columns with too many missing values
    feature_cols = [c for c in feature_cols if df_clean[c].isnull().mean() < 0.5]

    X = df_clean[feature_cols].copy()
    y = df_clean[target_column].copy()

    # Encode categoricals
    encoders: Dict[str, LabelEncoder] = {}
    for col in X.select_dtypes(include="object").columns:
        le = LabelEncoder()
        X[col] = le.fit_transform(X[col].astype(str))
        encoders[col] = le

    # Fill remaining NaNs
    X = X.fillna(X.median(numeric_only=True))

    # Encode target if classification
    if not is_regression:
        le_target = LabelEncoder()
        y = le_target.fit_transform(y.astype(str))
        target_classes = list(le_target.classes_)
    else:
        target_classes = []

    if len(X) < 20:
        return {"error": "Not enough data to train a model (need at least 20 rows)."}

    # ── 4. Train/test split ───────────────────────────────────────────────────
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # ── 5. Train model ────────────────────────────────────────────────────────
    if is_regression:
        model = RandomForestRegressor(n_estimators=100, random_state=42)
    else:
        model = RandomForestClassifier(n_estimators=100, random_state=42)

    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    # ── 6. Evaluate ───────────────────────────────────────────────────────────
    metrics: Dict[str, Any] = {}
    if is_regression:
        metrics["mae"]  = round(float(mean_absolute_error(y_test, y_pred)), 4)
        metrics["r2"]   = round(float(r2_score(y_test, y_pred)), 4)
        metrics["rmse"] = round(float(np.sqrt(((y_test - y_pred) ** 2).mean())), 4)
    else:
        metrics["accuracy"] = round(float(accuracy_score(y_test, y_pred)), 4)
        try:
            report = classification_report(y_test, y_pred, output_dict=True)
            metrics["classification_report"] = report
        except Exception:
            pass

    # ── Feature importance ────────────────────────────────────────────────────
    importances = sorted(
        zip(feature_cols, model.feature_importances_.tolist()),
        key=lambda x: x[1],
        reverse=True,
    )
    feature_importance = [{"feature": f, "importance": round(i, 4)} for f, i in importances[:15]]

    logger.info(f"AI Data Scientist: done - {metrics}")

    return {
        "target":              target_column,
        "problem_type":        problem_type,
        "model":               "RandomForest",
        "n_estimators":        100,
        "train_rows":          len(X_train),
        "test_rows":           len(X_test),
        "features_used":       feature_cols,
        "target_classes":      target_classes,
        "metrics":             metrics,
        "feature_importance":  feature_importance,
    }


# ── Target column detection ───────────────────────────────────────────────────

def _detect_target(df: pd.DataFrame) -> str:
    """Heuristic: pick the most likely target column."""
    priority_keywords = ["target", "label", "class", "output", "result",
                         "churn", "default", "fraud", "status", "outcome",
                         "price", "salary", "revenue", "score"]
    for kw in priority_keywords:
        for col in df.columns:
            if kw in col.lower():
                return col
    # Fall back to last column
    return df.columns[-1]
