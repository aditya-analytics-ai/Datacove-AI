"""
ai_orchestrator.py - coordinates all AI analysis capabilities.

After upload, this runs automatically to give users a complete picture:
  1. Profile the data
  2. Detect issues
  3. Generate actionable suggestions
  4. Calculate health score
  5. Suggest visualizations
  6. Return a unified action plan

Bug fixes applied vs deliverable:
  - Uses session.df_current (not session.df which doesn't exist)
  - Uses session.push_history() (not add_to_history which doesn't exist)
  - Uses require_session() from session_guard (not validate_session_access)
  - Action ID parsing uses rsplit('_', 1) to handle multi-word action names
"""
from typing import Any, Dict, List, Optional
import pandas as pd

from services.profiling_engine import profile_dataset
from services.issue_detector import detect_issues
from services.ai_suggestions import get_ai_suggestions
from services.health_score import calculate_health_score
from services.visualization_engine import suggest_visualizations
from utils.logger import logger


# Actions safe to run without user review
_AUTO_SAFE_ACTIONS = {
    "trim_whitespace",
    "standardise_capitalisation",
    "drop_constant_columns",
    "remove_duplicates",
    "normalise_categories",
}


def orchestrate_ai_analysis(
    df: pd.DataFrame,
    filename: str = "dataset",
    user_goal: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run comprehensive AI analysis and return a unified action plan.

    Args:
        df:        DataFrame to analyse (must be df_current from session)
        filename:  Original filename for context
        user_goal: Optional user-stated goal

    Returns dict with: profile, issues, health_score, actions,
                       visualizations, summary, metadata
    """
    logger.info(f"Orchestrator: analysing '{filename}' ({len(df)} rows, {len(df.columns)} cols)")

    profile  = profile_dataset(df)
    issues   = detect_issues(df)
    health   = calculate_health_score(df, issues)
    suggestions = get_ai_suggestions(profile, issues, df)
    actions  = _build_action_schema(suggestions, issues, df)
    visuals  = suggest_visualizations(df, profile)
    summary  = _generate_summary(profile, issues, health, actions, user_goal)

    logger.info(
        f"Orchestrator: done - score={health['score']}, "
        f"issues={len(issues)}, actions={len(actions)}"
    )

    return {
        "profile":        profile,
        "issues":         issues,
        "health_score":   health,
        "actions":        actions,
        "visualizations": visuals,
        "summary":        summary,
        "metadata": {
            "filename":  filename,
            "rows":      len(df),
            "columns":   len(df.columns),
            "user_goal": user_goal,
        },
    }


def _build_action_schema(
    suggestions: List[Dict[str, Any]],
    issues: List[Dict[str, Any]],
    df: pd.DataFrame,
) -> List[Dict[str, Any]]:
    """Convert raw suggestions into structured, executable action objects."""
    actions = []

    for suggestion in suggestions:
        action_type = suggestion.get("action")
        if not action_type:
            continue

        column   = suggestion.get("column")
        severity = suggestion.get("priority", "medium")

        # BUG FIX 4: use a delimiter that survives multi-word action names.
        # ID format: "{action_type}|{column_or_dataset}"
        action_id = f"{action_type}|{column or 'dataset'}"

        params: Dict[str, Any] = {}
        if column:
            params["column"] = column
        if action_type == "fill_missing":
            params["strategy"] = suggestion.get("params", {}).get("strategy", "median")

        action: Dict[str, Any] = {
            "id":              action_id,
            "problem":         suggestion.get("description", f"Data quality issue in {column or 'dataset'}"),
            "solution":        suggestion.get("title", f"Apply {action_type}"),
            "action_api":      action_type,
            "params":          params,
            "auto_executable": action_type in _AUTO_SAFE_ACTIONS and severity != "critical",
            "impact": {
                "rows_affected":    suggestion.get("rows_affected", 0),
                "columns_affected": 1 if column else len(df.columns),
                "severity":         severity,
            },
            "confidence": _calc_confidence(action_type, suggestion, df),
            "category":   _categorize(action_type),
        }
        actions.append(action)

    # Auto-executable first, then by confidence descending
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    actions.sort(key=lambda x: (
        not x["auto_executable"],
        -x["confidence"],
        severity_order.get(x["impact"]["severity"], 4),
    ))
    return actions


def _calc_confidence(
    action_type: str,
    suggestion: Dict[str, Any],
    df: pd.DataFrame,
) -> float:
    base = {
        "trim_whitespace":             0.95,
        "remove_duplicates":           0.92,
        "drop_constant_columns":       0.92,
        "standardise_capitalisation":  0.88,
        "normalise_categories":        0.82,
        "fill_missing":                0.75,
        "coerce_numeric":              0.80,
        "standardise_dates":           0.78,
        "clip_outliers":               0.70,
        "flag_invalid_emails":         0.95,
    }.get(action_type, 0.65)

    rows_affected = suggestion.get("rows_affected", 0)
    if rows_affected and len(df) > 0:
        if rows_affected / len(df) > 0.5:
            base *= 0.9

    return round(base, 2)


def _categorize(action_type: str) -> str:
    return {
        "trim_whitespace":             "formatting",
        "standardise_capitalisation":  "formatting",
        "normalise_categories":        "formatting",
        "remove_duplicates":           "deduplication",
        "drop_constant_columns":       "cleanup",
        "drop_high_missing_columns":   "cleanup",
        "fill_missing":                "imputation",
        "clip_outliers":               "quality",
        "coerce_numeric":              "schema",
        "standardise_dates":           "schema",
        "flag_invalid_emails":         "validation",
    }.get(action_type, "other")


def _generate_summary(
    profile: Dict[str, Any],
    issues: List[Dict[str, Any]],
    health: Dict[str, Any],
    actions: List[Dict[str, Any]],
    user_goal: Optional[str],
) -> str:
    rows   = profile.get("rows", 0)
    cols   = profile.get("columns", 0)
    score  = health.get("score", 0)
    grade  = health.get("grade", "F")
    auto   = sum(1 for a in actions if a["auto_executable"])
    manual = len(actions) - auto

    if score >= 90:
        quality = f"✨ Data quality is excellent ({score}/100, grade {grade})."
    elif score >= 70:
        quality = f"👍 Data quality is good ({score}/100, grade {grade}), with room for improvement."
    elif score >= 50:
        quality = f"⚠️ Data quality is moderate ({score}/100, grade {grade}). Several issues detected."
    else:
        quality = f"🚨 Data quality needs attention ({score}/100, grade {grade}). Multiple issues found."

    parts = [
        f"📊 Your dataset has {rows:,} rows and {cols} columns.",
        quality,
    ]
    if issues:
        affected_cols = len(set(i.get("column", "") for i in issues if i.get("column")))
        parts.append(f"Found {len(issues)} issue{'s' if len(issues) != 1 else ''} across {affected_cols} column{'s' if affected_cols != 1 else ''}.")
    if auto:
        parts.append(f"✅ {auto} fix{'es' if auto != 1 else ''} can be applied automatically.")
    if manual:
        parts.append(f"🔧 {manual} additional improvement{'s' if manual != 1 else ''} recommended for review.")
    if user_goal:
        parts.append(f"\n💡 For your goal of '{user_goal}', start with the auto-fixes then review the visualizations.")

    return " ".join(parts)
