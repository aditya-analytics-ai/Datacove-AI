"""
AI Agent - automated end-to-end data cleaning workflow.
Runs: profiling → issue detection → suggestions → cleaning → health score.
"""
from typing import Any, Dict, Tuple
import pandas as pd

from services.profiling_engine import profile_dataset
from services.issue_detector import detect_issues
from services.ai_suggestions import get_ai_suggestions
from services.cleaning_engine import apply_transformation
from services.health_score import calculate_health_score
from utils.logger import logger
from utils.explainability import explain_action, ExplainedAction


def run_ai_agent(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Execute the full AI agent pipeline on a DataFrame.

    Steps:
      1. Profile dataset
      2. Detect issues
      3. Generate AI/rule-based suggestions
      4. Apply all safe auto-fixes
      5. Calculate final health score

    Returns:
      (cleaned_df, report_dict)
    """
    logger.info("AI Agent: starting pipeline")

    # Step 1 - Profile
    profile = profile_dataset(df)
    logger.info(f"AI Agent: profiled - {profile['rows']} rows, {profile['columns']} cols")

    # Step 2 - Detect issues
    issues = detect_issues(df)
    logger.info(f"AI Agent: detected {len(issues)} issue(s)")

    # Step 3 - Suggestions
    suggestions = get_ai_suggestions(profile, issues, df)
    logger.info(f"AI Agent: generated {len(suggestions)} suggestion(s)")

    # Step 4 - Apply fixes
    actions_applied = []
    df_cleaned = df.copy()

    for suggestion in suggestions:
        action = suggestion.get("action")
        column = suggestion.get("column")
        if not action:
            continue
        params = {"column": column} if column else {}
        # Add default strategy for fill_missing
        if action == "fill_missing":
            params["strategy"] = "median"
        try:
            rows_before = len(df_cleaned)
            df_cleaned  = apply_transformation(df_cleaned, action, params)
            rows_after  = len(df_cleaned)
            explained   = explain_action(
                action=action,
                column=column,
                rows_affected=abs(rows_before - rows_after) if action == "remove_duplicates"
                              else suggestion.get("rows_affected", 0),
                params=params,
                status="applied",
            )
            actions_applied.append(explained.to_dict())
            logger.info(f"AI Agent: applied '{action}' on '{column}'")
        except Exception as exc:
            explained = explain_action(
                action=action, column=column, params=params,
                status="failed", error=str(exc),
            )
            actions_applied.append(explained.to_dict())
            logger.warning(f"AI Agent: failed '{action}' - {exc}")

    # Step 5 - Final health score
    final_issues = detect_issues(df_cleaned)
    score_before = calculate_health_score(df, issues)
    score_after  = calculate_health_score(df_cleaned, final_issues)
    logger.info(f"AI Agent: score {score_before['score']} → {score_after['score']}")

    report = {
        "rows_before":      len(df),
        "rows_after":       len(df_cleaned),
        "issues_before":    len(issues),
        "issues_after":     len(final_issues),
        "score_before":     score_before["score"],
        "score_after":      score_after["score"],
        "grade_after":      score_after["grade"],
        "actions_applied":  actions_applied,
        "suggestions":      suggestions,
        "profile":          profile,
        "final_health":     score_after,
    }

    return df_cleaned, report
