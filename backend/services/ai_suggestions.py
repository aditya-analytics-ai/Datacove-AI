"""
AI suggestions v4 - Anthropic claude-sonnet powered cleaning recommendations.
Falls back to rule-based suggestions if no API key is set.

Changes from v3:
  - get_ai_suggestions() now accepts an optional `df` parameter
  - Column profile enriched with sample_values, sentinel_values, null_count, dtype
  - Sample rows (first 5) appended to prompt so Claude sees real data, not just stats
  - System prompt tightened with concrete sentinel/cast/ordering rules
  - _build_column_profile() helper centralises per-column enrichment
"""
import json
from typing import Any, Dict, List, Optional

import pandas as pd

from utils.ai_rate_limiter import ai_rate_limiter
from utils.logger import logger

try:
    from config import ANTHROPIC_API_KEY, GOOGLE_API_KEY, GOOGLE_MODEL
except ImportError:
    ANTHROPIC_API_KEY = None
    GOOGLE_API_KEY = None
    GOOGLE_MODEL = "gemini-1.5-flash"


_MODEL = "claude-sonnet-4-20250514"

# Sentinel strings that are not real nulls but should be treated as missing
_SENTINEL_STRINGS = {
    "unknown", "error", "n/a", "na", "null", "none", "-", "?", "nil",
    "not available", "not applicable", "missing", "#n/a", "#null!", "nan",
}

# Full param schema - tells Claude exactly what each action expects so it
# produces ready-to-execute suggestions with correct, concrete params.
_ACTION_SCHEMA = """
remove_duplicates           params: {} or {"subset": ["col1","col2"]}
trim_whitespace             params: {} or {"columns": ["col1"]}
standardise_capitalisation  params: {"strategy": "title|upper|lower"} or {}
normalise_categories        params: {} or {"columns": ["col1"]}
fill_missing                params: {"column": "x", "strategy": "mean|median|mode|value|ffill|bfill|drop"} - strategy optional, defaults to mode
fill_missing_ffill          params: {} or {"column": "x"}
fill_missing_bfill          params: {} or {"column": "x"}
fill_missing_interpolate    params: {} or {"column": "x", "method": "linear"}
coerce_numeric              params: {"column": "x"}
cast_type                   params: {"column": "x", "dtype": "int|float|string|bool|date|category"}
standardise_dates           params: {"column": "x", "output_format": "%Y-%m-%d", "dayfirst": true}
standardise_mixed_dates     params: {"column": "x", "dayfirst": true, "output_format": "%Y-%m-%d"}
extract_date_parts          params: {"column": "x", "parts": ["year","month","day","weekday","quarter"]}
calculate_date_diff         params: {"column": "x", "column2": "y"} or {"column": "x", "reference_date": "2024-01-01", "unit": "days|weeks|months|years"}
flag_future_dates           params: {"column": "x"} or {"column": "x", "cutoff_date": "2024-12-31"}
flag_weekend_dates          params: {"column": "x"}
age_from_date               params: {"column": "x", "unit": "years|months|days", "new_col": "age"}
flag_invalid_emails         params: {"column": "x"}
normalize_phone             params: {"column": "x"} or {"column": "x", "country_code": "+1"}
normalize_unicode           params: {} or {"column": "x"}
drop_column                 params: {"column": "x"}
rename_column               params: {"old_name": "x", "new_name": "y"}
rename_columns_bulk         params: {"mapping": {"old1": "new1", "old2": "new2"}}
reorder_columns             params: {"order": ["col1","col2","col3"]}
normalize_column_names      params: {"style": "snake_case|camel_case|lower|upper"}
drop_rows_where             params: {"column": "x", "value": "UNKNOWN"} - use for single exact sentinel
drop_rows_matching          params: {"column": "x", "pattern": "regex", "flags": "i"}
drop_rows_missing_threshold params: {"threshold": 0.5}
drop_constant_columns       params: {}
drop_high_missing_columns   params: {"threshold": 0.5}
map_values                  params: {"column": "x", "mapping": {"UNKNOWN": null, "ERROR": null, "old": "new"}} - use when multiple sentinels present
find_replace                params: {"column": "x", "find": "old", "replace": "new", "regex": false}
strip_characters            params: {"column": "x", "mode": "special|html|non_printable|custom"} or {"chars": "abc"}
extract_numeric             params: {"column": "x"}
clip_outliers               params: {"column": "x", "method": "iqr|manual"} - add "lower": 0 for positive-only cols
replace_outliers            params: {"column": "x", "method": "iqr|zscore", "strategy": "mean|median|nan"}
round_numeric               params: {"column": "x", "decimals": 2}
scale_numeric               params: {"column": "x", "method": "min_max|z_score"}
bin_numeric                 params: {"column": "x", "bins": 5, "strategy": "equal_width|quantile", "new_col": "x_bin"}
split_column                params: {"column": "x", "delimiter": " ", "new_col_1": "a", "new_col_2": "b"}
merge_columns               params: {"col1": "x", "col2": "y", "separator": " ", "new_col": "z"}
conditional_column          params: {"column": "x", "condition": "gt|gte|lt|lte|eq|neq|contains|starts_with|ends_with|not_null", "value": "v", "new_col": "flag", "true_label": "yes", "false_label": "no"}
fuzzy_remove_duplicates     params: {"threshold": 85} or {"columns": ["col1"], "threshold": 85}
sql_apply                   params: {"query": "SELECT ..."}
apply_schema_suggestions    params: {"suggestions": [{"column": "x", "suggested_dtype": "int"}]}
map_to_standard             params: {"column": "x", "vocab": "country_name|country_code|currency|us_state|gender|boolean"}
"""

_SYSTEM = """\
You are a senior data quality engineer. Analyse the dataset profile, sample rows, \
and detected issues, then recommend the most impactful cleaning actions.

Rules:
1.  Return ONLY a valid JSON array - no markdown fences, no preamble, no trailing text.
2.  Each element must have: title (≤6 words), description (1-2 sentences quoting real \
values and counts from the profile), action (from schema), priority (high|medium|low), \
column (exact column name or null), params (object matching the schema exactly - \
use the real column name, real sentinel values, real counts).
3.  Return 3-12 suggestions ordered high→medium→low priority.
4.  No duplicate (action, column) pairs.
5.  SENTINELS: When sentinel_values is non-empty for a column, use map_values with the \
exact sentinel strings in the mapping (e.g. {"UNKNOWN": null, "ERROR": null}), or \
drop_rows_where if there is only one sentinel. Never use fill_missing to clear sentinels - \
fill_missing only acts on real NaN cells, not string sentinels.
6.  ORDERING: Suggest actions in safe execution order - sentinel cleanup first (map_values / \
drop_rows_where), then fill_missing on the remaining real NaNs, then cast_type last. \
Never suggest cast_type before sentinels are cleared in a string column or the cast will \
silently coerce sentinels to NaN instead of removing them intentionally.
7.  TYPES: When dtype is "object" or "string" but sample_values contains only numbers or \
ISO dates, suggest cast_type with the correct dtype (float if decimals present, int if \
all whole numbers, date if ISO format). Do not suggest coerce_numeric unless sample_values \
shows genuine mixed content (e.g. "25", "abc", "30").
8.  OUTLIERS: For clip_outliers on positive-only columns (prices, quantities, ages, counts) \
always include {"lower": 0} in params. Derive the column's positivity from sample_values.
9.  CONCRETENESS: Every param value must come from the profile - real column name, real \
sentinel string, real threshold from missing_pct. Never emit a placeholder like "x" or \
a value you are guessing.
10. DESCRIPTION quality: Each description must mention the specific column, the exact \
count or percentage of affected cells, and what the action will do - e.g. \
"Location has 3,961 cells containing UNKNOWN or NaN (39.6%). map_values will remap \
UNKNOWN to null so fill_missing can handle all missing values uniformly."
11. SENTINEL MAPPING: When sentinel_values lists multiple values (e.g. ["UNKNOWN","ERROR"]), \
include ALL of them in the map_values mapping - never emit a partial mapping.
"""


# ── Per-column profile enrichment ─────────────────────────────────────────────

def _build_column_profile(col: str, series: pd.Series) -> Dict[str, Any]:
    """
    Enrich a single column's profile with real values Claude can reason about:
    sample values, detected sentinels, null count, and dtype string.
    """
    non_null = series.dropna()
    str_vals = non_null.astype(str).str.strip()

    # Detect sentinel strings present in this column
    sentinel_values = sorted({
        v for v in non_null.unique()
        if str(v).strip().lower() in _SENTINEL_STRINGS
    }, key=str)

    # Sample up to 8 non-sentinel, non-null values for context
    non_sentinel = non_null[~str_vals.str.lower().isin(_SENTINEL_STRINGS)]
    sample_values = [
        v if not isinstance(v, float) or not pd.isna(v) else None
        for v in non_sentinel.unique()[:8].tolist()
    ]

    return {
        "column":          col,
        "dtype":           str(series.dtype),
        "null_count":      int(series.isnull().sum()),
        "null_pct":        round(series.isnull().mean() * 100, 1),
        "sentinel_values": sentinel_values,
        "sentinel_count":  int(str_vals.str.lower().isin(_SENTINEL_STRINGS).sum()),
        "unique_count":    int(series.nunique(dropna=True)),
        "sample_values":   sample_values,
    }


# ── Public entry point ─────────────────────────────────────────────────────────

def get_ai_suggestions(
    profile: Dict,
    issues: List[Dict],
    df: Optional[pd.DataFrame] = None,
) -> List[Dict[str, Any]]:
    """
    Generate cleaning suggestions using Claude.

    Parameters
    ----------
    profile : dict   - dataset profile from profiling_engine
    issues  : list   - detected issues from issue_detector
    df      : DataFrame, optional - the actual dataset; when supplied, each column's
              profile is enriched with sample_values, sentinel_values, and null_count
              so Claude can produce concrete, value-aware suggestions.
    """
    if not GOOGLE_API_KEY and not ANTHROPIC_API_KEY:
        return _rule_based(issues, df)
    try:
        ai_rate_limiter.check()

        # ── Build enriched column profiles ────────────────────────────────────
        if df is not None:
            enriched_cols = [
                _build_column_profile(col, df[col])
                for col in df.columns[:30]
            ]
        else:
            # Fallback: use whatever the profiling engine gave us
            enriched_cols = [
                {
                    "column":       cp.get("column"),
                    "dtype":        cp.get("detected_type", "unknown"),
                    "null_count":   None,
                    "null_pct":     cp.get("missing_pct"),
                    "sentinel_values": [],
                    "sentinel_count":  0,
                    "unique_count": cp.get("unique_count"),
                    "sample_values": [],
                }
                for cp in profile.get("columns_profile", [])[:30]
            ]

        prof_s = json.dumps({
            "rows":           profile.get("rows"),
            "columns":        profile.get("columns"),
            "duplicate_rows": profile.get("duplicate_rows"),
            "total_missing":  profile.get("total_missing"),
            "columns_profile": enriched_cols,
        }, indent=2, default=str)

        # ── Sample rows - 5 real rows so Claude sees actual content ──────────
        if df is not None:
            sample_rows = df.head(5).to_dict(orient="records")
            sample_s = json.dumps(sample_rows, indent=2, default=str)
        else:
            sample_s = "[]"

        user_msg = (
            f"Action schema:\n{_ACTION_SCHEMA}\n\n"
            f"Dataset profile:\n{prof_s}\n\n"
            f"Sample rows (first 5):\n{sample_s}\n\n"
            f"Detected issues:\n{json.dumps(issues[:20], indent=2)}"
        )

        if GOOGLE_API_KEY:
            from google import genai as google_genai
            client = google_genai.Client(api_key=GOOGLE_API_KEY)
            response = client.models.generate_content(
                model=GOOGLE_MODEL,
                contents=user_msg,
                config=google_genai.types.GenerateContentConfig(
                    system_instruction=_SYSTEM,
                ),
            )
            text = response.text.strip()
        else:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            resp = client.messages.create(
                model=_MODEL,
                max_tokens=3000,
                system=_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )
            text = resp.content[0].text.strip()

        # Strip accidental markdown fences
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        parsed = json.loads(text)
        clean = []
        for s in parsed:
            if isinstance(s, dict) and "action" in s and "title" in s:
                s.setdefault("params", {})
                s.setdefault("column", None)
                s.setdefault("priority", "medium")
                clean.append(s)
        return clean

    except Exception as exc:
        logger.warning(
            f"AI suggestions failed ({type(exc).__name__}: {exc}), "
            "using rule-based fallback"
        )
        return _rule_based(issues, df)


# ── Rule-based fallback ────────────────────────────────────────────────────────

_ISSUE_MAP: Dict[str, tuple] = {
    "duplicate_rows":               ("high",   "remove_duplicates",          {}, "Remove duplicate rows to deduplicate dataset", 0.95),
    "missing_values":               ("high",   "fill_missing",               {"strategy": "mode"}, "Fill missing values with mode/mean/median", 0.85),
    "extra_whitespace":             ("low",    "trim_whitespace",            {}, "Trim leading/trailing whitespace", 0.90),
    "capitalisation_inconsistency": ("medium", "standardise_capitalisation", {"strategy": "title"}, "Standardise text capitalisation", 0.80),
    "invalid_email":                ("medium", "flag_invalid_emails",        {}, "Flag rows with invalid email addresses", 0.90),
    "invalid_phone":                ("medium", "normalize_phone",            {}, "Normalise phone number formats", 0.85),
    "mixed_data_types":             ("high",   "coerce_numeric",             {}, "Coerce column to correct numeric type", 0.75),
    "category_inconsistency":       ("medium", "normalise_categories",       {}, "Normalise inconsistent category values", 0.80),
    "all_null_column":              ("high",   "drop_column",                {}, "Drop entirely empty columns", 0.95),
    "mixed_date_formats":           ("high",   "standardise_mixed_dates",    {"dayfirst": True}, "Standardise mixed date formats", 0.70),
    "unparseable_dates":            ("medium", "standardise_mixed_dates",    {"dayfirst": True}, "Parse unparseable date values", 0.70),
    "constant_column":              ("medium", "drop_constant_columns",      {}, "Drop zero-variance columns", 0.90),
    "empty_string_values":          ("medium", "map_values",               {}, "Replace sentinel placeholder values with null", 0.85),
    "negative_in_positive_col":     ("high",   "clip_outliers",              {"method": "iqr"}, "Clip negative values in positive-only columns", 0.80),
    "encoding_garbage":             ("medium", "strip_characters",           {"mode": "non_printable"}, "Remove non-printable characters", 0.85),
    "likely_id_column":             ("low",    "drop_column",                {}, "Drop likely ID columns", 0.70),
    "date_out_of_range":            ("medium", "standardise_dates",          {}, "Standardise date format", 0.75),
    "outliers":                    ("medium", "clip_outliers",              {"method": "iqr"}, "Clip statistical outliers", 0.75),
    "high_missing":                 ("high",   "drop_high_missing_columns",  {"threshold": 0.5}, "Drop columns with high missing rate", 0.90),
    "sentinel_values":              ("high",   "map_values",                 {}, "Replace sentinel placeholder values with null", 0.85),
    "whitespace":                  ("low",   "trim_whitespace",            {}, "Trim whitespace from text columns", 0.90),
    "mixed_case":                   ("medium", "standardise_capitalisation", {"strategy": "lower"}, "Normalise text case to lowercase", 0.80),
}

_TITLES: Dict[str, str] = {
    "remove_duplicates":       "Remove Duplicate Rows",
    "fill_missing":            "Fill Missing Values",
    "trim_whitespace":         "Trim Whitespace",
    "standardise_capitalisation": "Standardise Capitalisation",
    "flag_invalid_emails":     "Flag Invalid Emails",
    "normalize_phone":         "Normalise Phone Numbers",
    "coerce_numeric":          "Coerce to Numeric",
    "normalise_categories":    "Normalise Category Variants",
    "drop_column":             "Drop Problematic Column",
    "drop_constant_columns":   "Drop Zero-Variance Columns",
    "drop_high_missing_columns": "Drop High-Missing Columns",
    "find_replace":            "Replace Empty Strings",
    "clip_outliers":           "Clip Outliers",
    "strip_characters":        "Strip Non-Printable Characters",
    "standardise_dates":       "Standardise Date Format",
    "standardise_mixed_dates": "Fix Mixed Date Formats",
    "map_values":              "Replace Placeholder Values",
}


def _rule_based(issues: List[Dict], df: Optional[pd.DataFrame] = None) -> List[Dict[str, Any]]:
    suggestions, seen = [], set()
    priority_order = {"high": 0, "medium": 1, "low": 2}
    
    # Store sample values for preview
    sample_data = {}
    if df is not None and len(df) > 0:
        for col in df.columns:
            sample_data[col] = df[col].dropna().head(3).tolist()
    
    for iss in sorted(issues, key=lambda i: priority_order.get(i.get("severity"), 3)):
        itype, col = iss.get("type", ""), iss.get("column")
        m = _ISSUE_MAP.get(itype)
        if not m:
            continue
        if len(m) >= 5:
            priority, action, params, default_desc, confidence = m
        elif len(m) == 4:
            priority, action, params, default_desc = m
            confidence = 0.75
        else:
            priority, action, params = m
            default_desc = action.replace("_", " ").title()
            confidence = 0.75
        key = (action, col)
        if key in seen:
            continue
        seen.add(key)
        
        count = iss.get("count", 0)
        pct = iss.get("pct", 0)
        col_name = iss.get("column", "")
        
        if count > 0 or pct > 0:
            if col_name:
                if pct > 0:
                    desc = f"{col_name} has {count} issues ({pct:.1f}%). "
                else:
                    desc = f"{col_name} has {count} issues. "
            else:
                desc = f"Found {count} issues. "
        else:
            desc = default_desc
        
        final_desc = iss.get("description", "") or desc
        col_params = {} if col is None else {"column": col}
        
        final_params = {**params, **col_params}
        if action == "fill_missing" and "strategy" not in final_params:
            final_params = {"strategy": "mode", **col_params}
        
        # Build preview showing current vs. after-fix sample
        preview = None
        if col and col in sample_data and sample_data[col]:
            sample_val = str(sample_data[col][0])
            preview_col = [f"Before: {sample_data[col][0]}"]
            if action == "trim_whitespace":
                preview_col.append(f"After: '{sample_val.strip()}'")
            elif action == "standardise_capitalisation":
                params_strat = final_params.get("strategy", "title")
                if params_strat == "title":
                    preview_col.append(f"After: {sample_val.title()}")
                elif params_strat == "upper":
                    preview_col.append(f"After: {sample_val.upper()}")
                elif params_strat == "lower":
                    preview_col.append(f"After: {sample_val.lower()}")
                else:
                    preview_col.append(f"After: {sample_val.title()}")
            elif action == "fill_missing":
                preview_col.append("After: <mode value>")
            elif action == "map_values":
                preview_col.append("After: null")
            elif action == "coerce_numeric":
                preview_col.append("After: <numeric>")
            elif action == "clip_outliers":
                if col_name and df is not None and col_name in df.columns:
                    col_data = df[col_name].dropna()
                    if len(col_data) > 0:
                        q1, q3 = col_data.quantile(0.25), col_data.quantile(0.75)
                        iqr = q3 - q1
                        lower = max(0, q1 - 1.5 * iqr)
                        preview_col.append(f"After: clipped to >={lower}")
                else:
                    preview_col.append("After: <clipped>")
            else:
                preview_col.append(f"After: <transformed>")
            preview = preview_col[:2]
        
        suggestions.append({
            "title":       _TITLES.get(action, action.replace("_", " ").title()),
            "description": final_desc,
            "action":      action,
            "priority":    priority,
            "confidence":  confidence,
            "column":      col,
            "preview":     preview,
            "params":      final_params,
        })
    
    suggestions.sort(key=lambda x: (
        priority_order.get(x.get("priority"), 3),
        -x.get("confidence", 0),
    ))
    return suggestions
