"""
Cleaning engine v3 — applies transformations to the DataFrame.
All operations are non-destructive; the caller manages session state.

New in v3
─────────
Chunked processing: large DataFrames (>CHUNK_THRESHOLD rows) are processed
in 50 000-row chunks for row-wise transforms, avoiding full-memory copies.
Column-stat transforms (scale, bin, clip, etc.) still use the full df since
they require global min/max/quantile stats.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable, Dict, Hashable, List, Optional

import numpy as np
import pandas as pd
from pandas import DataFrame, Series

# Dirty null tokens - text placeholders that should be converted to real NaN
DIRTY_NULL_TOKENS: frozenset[str] = frozenset(
    {
        "n/a", "na", "na ", "--", "-", "?", "unknown", "unknown ",
        "null", "none", "missing", "tbd", "tba", "n/d", "n\\d",
        ".", "", " ", "~", "-999", "-9999", "n\\a", "None",
    }
)


# Row-wise ops safe to chunk (don't need global column stats)
# IMPORTANT: "remove_duplicates" is intentionally excluded — chunked dedup only
# removes duplicates within each 50k-row window, silently missing cross-chunk
# duplicates. It must always run on the full DataFrame.
# "fill_missing" and "drop_rows_missing_threshold" replace the former incorrect
# aliases "fill_missing_value" and "drop_rows_with_nulls" which never existed
# in _ACTIONS and caused silent no-ops on large datasets.
_CHUNKABLE_ACTIONS: frozenset[str] = frozenset(
    {
        "trim_whitespace",
        "standardise_capitalisation",
        "find_replace",
        "strip_characters",
        "normalize_unicode",
        "normalize_phone",
        "map_values",
        "fill_missing",
        "fill_missing_ffill",
        "fill_missing_bfill",
        "drop_rows_missing_threshold",
        "drop_rows_matching",
        "cast_type",
        "conditional_column",
    }
)

# Rows above this threshold → chunked processing
_CHUNK_THRESHOLD = 100_000
_CHUNK_SIZE = 50_000


def _is_string_col(series: pd.Series) -> bool:
    """True for both legacy object dtype and modern StringDtype."""
    return pd.api.types.is_string_dtype(series) or series.dtype == object


def _safe_categorical_conversion(series: pd.Series) -> pd.Series | Any:
    """
    Safely convert a series to categorical dtype, avoiding
    "Cannot setItem on Categorical with a new category" errors.

    Uses string dtype instead of categorical to avoid assignment issues,
    since categorical columns cannot have new values assigned after creation.
    This maintains data type consistency while preventing downstream errors.
    """
    try:
        # Convert to string - this is safer than categorical dtype
        # because it allows new values to be assigned if needed later
        str_series = series.astype(str)
        # Replace 'nan' strings with empty string for cleaner display
        str_series = str_series.where(series.notna(), "")
        return str_series
    except Exception:
        # Fallback: keep as original dtype if conversion fails
        return series


# ── Public entry point ────────────────────────────────────────────────────────


def apply_transformation(
    df: pd.DataFrame, action: str, params: Dict[str, Any]
) -> pd.DataFrame:
    """
    Dispatch a named cleaning action.
    Returns a NEW DataFrame (original never mutated).

    For large DataFrames (>_CHUNK_THRESHOLD rows), row-wise actions are
    processed in _CHUNK_SIZE-row chunks to reduce peak memory usage.
    """
    handler: Any | None = _ACTIONS.get(action)
    if handler is None:
        raise ValueError(f"Unknown cleaning action: '{action}'")

    # Chunked path — row-wise actions on large datasets
    if action in _CHUNKABLE_ACTIONS and len(df) > _CHUNK_THRESHOLD:
        chunks = []
        for start in range(0, len(df), _CHUNK_SIZE):
            chunk = df.iloc[start : start + _CHUNK_SIZE].copy()
            chunks.append(handler(chunk, params))
        return pd.concat(chunks, ignore_index=True)

    # Standard path — operates on a full copy
    return handler(df.copy(), params)


def auto_clean(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply the safe default cleaning suite in one call.
    Large DataFrames use chunked processing where possible.
    """
    df = df.copy()
    df = _remove_duplicates(df, {})
    df = _convert_dirty_nulls(df, {})
    df = _trim_whitespace(df, {})
    df = _standardise_capitalisation(df, {})
    df = _normalise_categories(df, {})
    return df


def auto_clean_explained(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Same 4-step auto_clean suite but returns a plain-English report with
    per-step before/after diffs.

    Returns {"df": pd.DataFrame, "steps": [step], "summary": str}
    """
    steps: List[Dict[str, Any]] = []
    current: DataFrame = df.copy()
    total_cell_changes = 0

    def _str_cols(frame):
        return [c for c in frame.columns if _is_string_col(frame[c])]

    def _count_changed(before, after, cols) -> int:
        total = 0
        for c in cols:
            if c not in before.columns or c not in after.columns:
                continue
            b = before[c].fillna("").astype(str).reset_index(drop=True)
            a = after[c].fillna("").astype(str).reset_index(drop=True)
            n: int = min(len(b), len(a))
            total += int((b.iloc[:n] != a.iloc[:n]).sum())
        return total

    def _samples(before, after, cols, max_s=5):
        out = []
        for c in cols:
            if len(out) >= max_s or c not in before.columns or c not in after.columns:
                break
            b = before[c].fillna("").astype(str).reset_index(drop=True)
            a = after[c].fillna("").astype(str).reset_index(drop=True)
            for i in range(min(len(b), len(a))):
                if b.iloc[i] != a.iloc[i] and len(out) < max_s:
                    out.append({"column": c, "before": b.iloc[i], "after": a.iloc[i]})
        return out

    def _affected(before, after, cols):
        return [
            c
            for c in cols
            if c in before.columns
            and c in after.columns
            and before[c]
            .fillna("")
            .astype(str)
            .reset_index(drop=True)
            .ne(after[c].fillna("").astype(str).reset_index(drop=True))
            .any()
        ]

    # Step 1 — remove duplicates
    snap: DataFrame = current.copy()
    current: DataFrame = _remove_duplicates(current, {})
    removed: int = len(snap) - len(current)
    steps.append(
        {
            "action": "remove_duplicates",
            "label": "Remove duplicate rows",
            "description": (
                f"Scanned {len(snap):,} rows. "
                + (
                    "No duplicates found."
                    if removed == 0
                    else f"Removed {removed:,} duplicate row(s), keeping the first occurrence. {len(current):,} rows remain."
                )
            ),
            "before_count": len(snap),
            "after_count": len(current),
            "delta": -removed,
            "affected_cols": [],
            "sample_changes": [],
        }
    )

    # Step 2 — trim whitespace
    snap: DataFrame = current.copy()
    sc: List[str] = _str_cols(snap)
    current: DataFrame = _trim_whitespace(current, {})
    ch: int = _count_changed(snap, current, sc)
    steps.append(
        {
            "action": "trim_whitespace",
            "label": "Trim whitespace",
            "description": (
                f"Stripped leading/trailing spaces across {len(sc)} text column(s). "
                + (
                    "No whitespace issues found."
                    if ch == 0
                    else f"Cleaned {ch:,} cell(s)."
                )
            ),
            "before_count": len(snap),
            "after_count": len(current),
            "delta": 0,
            "affected_cols": _affected(snap, current, sc)[:10],
            "sample_changes": _samples(snap, current, sc),
        }
    )
    total_cell_changes += ch

    # Step 3 — capitalisation
    snap: DataFrame = current.copy()
    current: DataFrame = _standardise_capitalisation(current, {})
    ch: int = _count_changed(snap, current, sc)
    steps.append(
        {
            "action": "standardise_capitalisation",
            "label": "Standardise capitalisation",
            "description": (
                f"Applied title-case to all text columns. "
                + (
                    "All values already correctly cased."
                    if ch == 0
                    else f"Updated {ch:,} cell(s)."
                )
            ),
            "before_count": len(snap),
            "after_count": len(current),
            "delta": 0,
            "affected_cols": _affected(snap, current, sc)[:10],
            "sample_changes": _samples(snap, current, sc),
        }
    )
    total_cell_changes += ch

    # Step 4 — normalise categories
    snap: DataFrame = current.copy()
    current: DataFrame = _normalise_categories(current, {})
    ch: int = _count_changed(snap, current, sc)
    steps.append(
        {
            "action": "normalise_categories",
            "label": "Normalise category values",
            "description": (
                f"Unified inconsistent category labels (e.g. 'yes'/'YES'/'Yes'). "
                + (
                    "No inconsistencies found."
                    if ch == 0
                    else f"Normalised {ch:,} cell(s)."
                )
            ),
            "before_count": len(snap),
            "after_count": len(current),
            "delta": 0,
            "affected_cols": _affected(snap, current, sc)[:10],
            "sample_changes": _samples(snap, current, sc),
        }
    )
    total_cell_changes += ch

    row_delta: int = len(df) - len(current)
    if row_delta == 0 and total_cell_changes == 0:
        summary = "Auto-clean ran all 4 steps — the dataset was already clean, no changes required."
    else:
        parts = []
        if row_delta > 0:
            parts.append(f"removed {row_delta:,} duplicate row(s)")
        if total_cell_changes > 0:
            parts.append(f"updated {total_cell_changes:,} cell(s)")
        summary: str = "Auto-clean complete: " + " and ".join(parts) + "."

    return {"df": current, "steps": steps, "summary": summary}


# ══════════════════════════════════════════════════════════════════════════════
# ── EXISTING transformations ──────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════


def _remove_duplicates(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Remove exact duplicate rows."""
    subset = params.get("subset")
    return df.drop_duplicates(subset=subset, keep="first").reset_index(drop=True)


def _convert_dirty_nulls(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Convert dirty null tokens (like 'n/a', 'unknown', '--', etc.) to real NaN.
    Uses the DIRTY_NULL_TOKENS constant.
    """
    cols = params.get("columns", [c for c in df.columns if _is_string_col(df[c])])
    dirty_tokens = DIRTY_NULL_TOKENS
    for col in cols:
        if col in df.columns and _is_string_col(df[col]):
            df[col] = df[col].replace(list(dirty_tokens), pd.NA)
    return df


def _trim_whitespace(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Strip leading/trailing whitespace and collapse multiple spaces."""
    cols = params.get("columns", [c for c in df.columns if _is_string_col(df[c])])
    for col in cols:
        if col in df.columns and _is_string_col(df[col]):
            df[col] = df[col].where(
                df[col].isna(),
                df[col].astype(str).str.strip().str.replace(r"\s+", " ", regex=True),
            )
    return df


def _standardise_capitalisation(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Normalise capitalisation. Default: title-case. Preserves NaN cells."""
    strategy = params.get("strategy", "title")
    cols = params.get("columns", [c for c in df.columns if _is_string_col(df[c])])
    for col in cols:
        if col not in df.columns:
            continue
        if strategy == "upper":
            df[col] = df[col].where(df[col].isna(), df[col].astype(str).str.upper())
        elif strategy == "lower":
            df[col] = df[col].where(df[col].isna(), df[col].astype(str).str.lower())
        else:
            df[col] = df[col].where(df[col].isna(), df[col].astype(str).str.title())
    return df


def _normalise_categories(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    For low-cardinality string columns, normalise variants by lowercasing +
    stripping, then map back to the most-frequent canonical form.
    """
    cols = params.get("columns", [c for c in df.columns if _is_string_col(df[c])])
    for col in cols:
        if col not in df.columns:
            continue
        series = df[col].dropna()
        unique_raw = series.nunique()
        series_str = series.astype(str)
        unique_normal = series_str.str.strip().str.lower().nunique()
        if 2 <= unique_normal <= 30 and unique_raw > unique_normal:
            mapping: Dict[str, str] = {}
            for key, group in series.groupby(series_str.str.strip().str.lower()):
                mapping[key] = group.value_counts().index[0]
            df[col] = df[col].map(
                lambda x: mapping.get(str(x).strip().lower(), x) if pd.notna(x) else x
            )
    return df


def _fill_missing(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Fill missing values.
    Supported strategies: mean | median | mode | value | ffill | bfill | drop.

    New: group-based imputation using `by` or `group_by` param (column name or list).
    Example: {"column": "age", "strategy": "mean", "group_by": "city"}
    """
    col = params.get("column")
    strategy = params.get("strategy", "mode")
    fill_val = params.get("value")
    # Support group-based imputation: 'by' or 'group_by' can be a column name or list
    group_by = params.get("by") or params.get("group_by")
    if isinstance(group_by, str):
        group_cols = [group_by]
    elif isinstance(group_by, (list, tuple)):
        group_cols = list(group_by)
    else:
        group_cols = None

    cols = [col] if col else df.columns.tolist()
    for c in cols:
        if c not in df.columns:
            continue

        # Grouped imputation
        if group_cols:
            if not all(gc in df.columns for gc in group_cols):
                raise ValueError(f"Group-by column(s) not found: {group_cols}")

            if strategy == "mean" and pd.api.types.is_numeric_dtype(df[c]):
                df[c] = df.groupby(group_cols)[c].transform(
                    lambda s: s.fillna(s.mean())
                )
            elif strategy == "median" and pd.api.types.is_numeric_dtype(df[c]):
                df[c] = df.groupby(group_cols)[c].transform(
                    lambda s: s.fillna(s.median())
                )
            elif strategy == "mode":

                def _group_mode_fill(s: Series) -> Series:
                    m = s.mode()
                    if m.empty:
                        return s
                    return s.fillna(m.iloc[0])

                df[c] = df.groupby(group_cols)[c].transform(_group_mode_fill)
            elif strategy in ("ffill", "forward_fill"):
                df[c] = df.groupby(group_cols)[c].transform(lambda s: s.ffill())
            elif strategy in ("bfill", "backward_fill"):
                df[c] = df.groupby(group_cols)[c].transform(lambda s: s.bfill())
            elif strategy == "value" and fill_val is not None:
                df[c] = df.groupby(group_cols)[c].transform(
                    lambda s: s.fillna(fill_val)
                )
            elif strategy == "drop":
                df = df.dropna(subset=[c])
            else:
                # Fallback: scalar fill
                if strategy == "value" and fill_val is not None:
                    df[c] = df[c].fillna(fill_val)
        else:
            # Non-grouped (legacy) behaviour
            if strategy == "mean" and pd.api.types.is_numeric_dtype(df[c]):
                df[c] = df[c].fillna(df[c].mean())
            elif strategy == "median" and pd.api.types.is_numeric_dtype(df[c]):
                df[c] = df[c].fillna(df[c].median())
            elif strategy == "mode":
                mode: Series[Any] = df[c].mode()
                if not mode.empty:
                    df[c] = df[c].fillna(mode.iloc[0])
            elif strategy == "value" and fill_val is not None:
                df[c] = df[c].fillna(fill_val)
            elif strategy in ("ffill", "forward_fill"):
                df[c] = df[c].ffill()
            elif strategy in ("bfill", "backward_fill"):
                df[c] = df[c].bfill()
            elif strategy == "drop":
                df = df.dropna(subset=[c])
    return df


def _coerce_numeric(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Coerce a column to numeric, turning non-numeric values to NaN."""
    col = params.get("column")
    if col and col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _standardise_dates(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Parse dates and reformat to ISO 8601 (YYYY-MM-DD)."""
    col = params.get("column")
    dayfirst = bool(params.get("dayfirst", True))
    fmt = params.get("output_format", "%Y-%m-%d")
    if col and col in df.columns:
        from dateutil import parser as _dp

        def _parse_one(val: Any) -> Any:
            if pd.isna(val) or str(val).strip() == "":
                return None
            try:
                return _dp.parse(str(val).strip(), dayfirst=dayfirst).strftime(fmt)
            except Exception:
                return None

        df[col] = df[col].apply(_parse_one)
    return df


def _flag_invalid_emails(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Add a boolean flag column for invalid emails."""
    from utils.validation_utils import is_valid_email

    col = params.get("column")
    flag_col: str = f"{col}_invalid"
    if col and col in df.columns:
        df[flag_col] = df[col].apply(
            lambda x: not is_valid_email(str(x)) if pd.notna(x) else True
        )
    return df


def _validate_regex(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Add a boolean flag column for values that DON'T match a regex pattern.
    params:
      column    – target column
      pattern   – regex pattern to match (required)
      flag_col  – flag column name (default: "{column}_invalid_format")
      invert    – bool (default False); if True, flag MATCHES instead of non-matches
    """
    col = params.get("column")
    pattern = params.get("pattern")
    flag_col = params.get("flag_col") or f"{col}_invalid_format"
    invert = bool(params.get("invert", False))

    if not (col and pattern and col in df.columns):
        return df

    try:
        regex = re.compile(pattern)

        def _check(x: Any) -> bool:
            if pd.isna(x):
                return True
            matches = bool(regex.search(str(x)))
            return (not matches) if not invert else matches

        df[flag_col] = df[col].apply(_check)
    except re.error:
        raise ValueError(f"Invalid regex pattern: {pattern}")

    return df


def _validate_range(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Add a boolean flag column for numeric values outside a range.
    params:
      column    – target column
      min_val   – minimum allowed value (inclusive)
      max_val   – maximum allowed value (inclusive)
      flag_col  – flag column name (default: "{column}_out_of_range")
    """
    col = params.get("column")
    min_val = params.get("min_val")
    max_val = params.get("max_val")
    flag_col = params.get("flag_col") or f"{col}_out_of_range"

    if not (col and col in df.columns):
        return df

    try:
        numeric = pd.to_numeric(df[col], errors="coerce")
        out_of_range = ~numeric.between(min_val, max_val, inclusive="both")
        df[flag_col] = out_of_range.fillna(True)  # NaN values are flagged as invalid
    except (TypeError, ValueError):
        raise ValueError(f"Cannot validate range on non-numeric column '{col}'")

    return df


def _validate_format(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Add a boolean flag column for values that don't match a specific format.
    params:
      column    – target column
      format    – "email" | "phone" | "url" | "date" | "ipv4" | "credit_card" | "zip_code"
      flag_col  – flag column name (default: "{column}_invalid_format")
    """
    col = params.get("column")
    fmt = params.get("format", "").lower()
    flag_col = params.get("flag_col") or f"{col}_invalid_format"

    if not (col and fmt and col in df.columns):
        return df

    # Define format validators
    validators: Dict[str, Callable[[Any], bool]] = {
        "email": lambda x: bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", str(x))),
        "phone": lambda x: bool(re.match(r"^[\d\s\-\(\)\+]+$", str(x))),
        "url": lambda x: bool(re.match(r"^https?://", str(x))),
        "date": lambda x: bool(pd.to_datetime(str(x), errors="coerce") is not pd.NaT),
        "ipv4": lambda x: bool(re.match(r"^(\d{1,3}\.){3}\d{1,3}$", str(x))),
        "credit_card": lambda x: bool(
            re.match(r"^\d{13,19}$", str(x).replace(" ", "").replace("-", ""))
        ),
        "zip_code": lambda x: bool(re.match(r"^\d{5}(-\d{4})?$", str(x))),
    }

    if fmt not in validators:
        raise ValueError(
            f"Unknown format: {fmt}. Must be: {', '.join(validators.keys())}"
        )

    validator = validators[fmt]

    def _check(x: Any) -> bool:
        if pd.isna(x):
            return True
        try:
            return not validator(x)
        except Exception:
            return True

    df[flag_col] = df[col].apply(_check)
    return df


def _rename_column(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    old = params.get("old_name")
    new = params.get("new_name")
    if old and new and old in df.columns:
        df = df.rename(columns={old: new})
    return df


def _drop_column(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    col = params.get("column")
    if col and col in df.columns:
        df = df.drop(columns=[col])
    return df


def _drop_rows_where(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Drop rows where column value exactly equals a given value.
    Coerces val to match the column dtype to prevent type-mismatch misses
    (e.g. JSON string '0' vs int 0).
    """
    col = params.get("column")
    val = params.get("value")
    if col and col in df.columns and val is not None:
        try:
            typed_val = df[col].dtype.type(val)
        except (ValueError, TypeError):
            typed_val = val
        df = df[df[col] != typed_val].reset_index(drop=True)
    return df


# ══════════════════════════════════════════════════════════════════════════════
# ── NEW: String transformations ───────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════


def _find_replace(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Find & replace text inside a column (exact or regex).
    params:
      column         – target column (required)
      find           – text to find (default "")
      replace        – replacement text (default "")
      regex          – bool, treat 'find' as a regex pattern (default False)
      case_sensitive – bool (default True); only honoured in regex mode
    """
    col = params.get("column")
    find = params.get("find", "")
    replace = params.get("replace", "")
    use_regex = bool(params.get("regex", False))
    case_sensitive = bool(params.get("case_sensitive", True))

    if not (col and col in df.columns and find):
        return df

    flags: int | re.RegexFlag = 0 if case_sensitive else re.IGNORECASE

    if use_regex:
        df[col] = (
            df[col].astype(str).str.replace(find, replace, regex=True, flags=flags)
        )
    else:
        if case_sensitive:
            df[col] = df[col].astype(str).str.replace(find, replace, regex=False)
        else:
            pattern = re.escape(find)
            df[col] = (
                df[col]
                .astype(str)
                .str.replace(pattern, replace, regex=True, flags=flags)
            )
    return df


def _strip_characters(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Remove unwanted characters from string columns.
    params:
      column  – target column; omit to apply to all string columns
      mode    – "special"       strip non-alphanumeric except spaces (default)
                "html"          strip HTML/XML tags
                "non_printable" strip non-printable / control characters
                "custom"        strip only characters listed in 'chars'
      chars   – characters to strip when mode="custom"
    """
    col = params.get("column")
    mode = params.get("mode", "special")
    custom = params.get("chars", "")

    cols = [col] if col else [c for c in df.columns if _is_string_col(df[c])]

    for c in cols:
        if c not in df.columns:
            continue

        if mode == "html":
            df[c] = df[c].astype(str).str.replace(r"<[^>]+>", "", regex=True)

        elif mode == "non_printable":
            df[c] = (
                df[c]
                .astype(str)
                .apply(
                    lambda x: (
                        "".join(ch for ch in x if ch.isprintable())
                        if pd.notna(x)
                        else x
                    )
                )
            )

        elif mode == "custom" and custom:
            escaped = re.escape(custom)
            df[c] = df[c].astype(str).str.replace(f"[{escaped}]", "", regex=True)

        else:  # special — keep alphanumeric + spaces
            df[c] = df[c].astype(str).str.replace(r"[^a-zA-Z0-9\s]", "", regex=True)

    return df


def _normalize_unicode(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Strip diacritic accents and normalize Unicode to ASCII.
    e.g. 'café' → 'cafe', 'naïve' → 'naive', 'Ñ' → 'N'
    params:
      column – target column; omit to apply to all string columns
    """
    col = params.get("column")
    cols = [col] if col else [c for c in df.columns if _is_string_col(df[c])]

    def _to_ascii(val: Any) -> Any:
        if pd.isna(val):
            return val
        nfkd: str = unicodedata.normalize("NFKD", str(val))
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    for c in cols:
        if c in df.columns:
            df[c] = df[c].apply(_to_ascii)
    return df


def _normalize_phone(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Standardise phone numbers by stripping non-digit characters and
    optionally prepending a country code.
    params:
      column       – target column (required)
      country_code – e.g. "+1", "+91" (optional; prepended if no leading '+')
    """
    col = params.get("column")
    country_code = params.get("country_code", "")

    if not (col and col in df.columns):
        return df

    def _clean(val: Any) -> Any:
        if pd.isna(val):
            return val
        s: str = str(val).strip()
        has_plus: bool = s.startswith("+")
        digits: str = re.sub(r"\D", "", s)
        if country_code and not has_plus:
            return country_code + digits
        return ("+" if has_plus else "") + digits

    df[col] = df[col].apply(_clean)
    return df


def _map_values(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Replace values in a column using an explicit dictionary mapping.
    params:
      column  – target column (required)
      mapping – {"old_value": "new_value", ...}
      default – value for unmatched entries; omit to keep original
    """
    col = params.get("column")
    mapping = params.get("mapping", {})
    default = params.get("default", "__keep__")

    if not (col and col in df.columns and mapping):
        return df

    str_map = {str(k): v for k, v in mapping.items()}

    def _remap(x: Any) -> Any:
        if pd.isna(x):
            return x
        key = str(x)
        if key in str_map:
            return str_map[key]
        return x if default == "__keep__" else default

    df[col] = df[col].apply(_remap)
    return df


def _split_column(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Split one column into two new columns on the first occurrence of a delimiter.
    params:
      column         – column to split (required)
      delimiter      – split on this string / regex (default " ")
      new_col_1      – name of left part  (default "{column}_1")
      new_col_2      – name of right part (default "{column}_2")
      keep_original  – bool, keep the source column (default False)
      regex          – bool, treat delimiter as regex (default False)
    """
    col = params.get("column")
    delimiter = params.get("delimiter", " ")
    keep_original = bool(params.get("keep_original", False))
    use_regex = bool(params.get("regex", False))

    if not (col and col in df.columns):
        return df

    new1 = params.get("new_col_1", f"{col}_1")
    new2 = params.get("new_col_2", f"{col}_2")

    split = (
        df[col]
        .astype(str)
        .str.split(
            delimiter if not use_regex else re.compile(delimiter),
            n=1,
            expand=True,
            regex=use_regex,
        )
    )
    df[new1] = split[0] if 0 in split.columns else ""
    df[new2] = split[1] if 1 in split.columns else ""

    if not keep_original:
        df = df.drop(columns=[col])

    return df


def _merge_columns(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Concatenate two columns into a single new column.
    params:
      col1           – first column (required)
      col2           – second column (required)
      separator      – string between values (default " ")
      new_col        – name of result column (default "{col1}_{col2}")
      keep_originals – bool, keep the source columns (default False)
    """
    col1 = params.get("col1")
    col2 = params.get("col2")
    separator = params.get("separator", " ")
    keep_originals = bool(params.get("keep_originals", False))

    if not (col1 and col2 and col1 in df.columns and col2 in df.columns):
        return df

    new_col = params.get("new_col", f"{col1}_{col2}")

    df[new_col] = (
        df[col1].astype(object).fillna("").astype(str)
        + separator
        + df[col2].astype(object).fillna("").astype(str)
    ).str.strip(separator)

    if not keep_originals:
        to_drop = [c for c in (col1, col2) if c != new_col]
        df = df.drop(columns=to_drop)

    return df


# ══════════════════════════════════════════════════════════════════════════════
# ── NEW: Numeric transformations ──────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════


def _extract_numeric(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Extract the first numeric value found in a mixed-content string column.
    e.g. "$1,234.56 USD" → 1234.56,  "Age: 25 years" → 25.
    params:
      column – target column (required)
    """
    col = params.get("column")
    if col and col in df.columns:
        # Match optional leading minus, digits, optional decimal point
        extracted = (
            df[col]
            .astype(str)
            .str.replace(",", "", regex=False)  # remove thousand separators
            .str.extract(r"(-?\d+(?:\.\d+)?)", expand=False)
        )
        df[col] = pd.to_numeric(extracted, errors="coerce")
    return df


def _clip_outliers(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Clamp numeric values to [lower, upper] bounds.
    params:
      column  – target column (required; must be numeric)
      method  – "iqr" (default) or "manual"
      lower   – manual lower bound (used when method="manual")
      upper   – manual upper bound (used when method="manual")
      iqr_factor – multiplier for IQR fence (default 1.5)
    """
    col = params.get("column")
    method = params.get("method", "iqr")
    iqr_factor = float(params.get("iqr_factor", 1.5))

    if not (col and col in df.columns and pd.api.types.is_numeric_dtype(df[col])):
        return df

    if method == "iqr":
        q1 = df[col].quantile(0.25)
        q3 = df[col].quantile(0.75)
        iqr = q3 - q1
        lower = q1 - iqr_factor * iqr
        upper = q3 + iqr_factor * iqr
    else:
        lower = params.get("lower")
        upper = params.get("upper")

    df[col] = df[col].clip(lower=lower, upper=upper)
    return df


def _replace_outliers(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Replace outlier values with mean, median, or NaN instead of clipping.
    params:
      column      – target column (required; must be numeric)
      method      – outlier detection: "iqr" (default) or "zscore"
      strategy    – replacement: "mean" | "median" | "nan" (default "median")
      iqr_factor  – IQR fence multiplier (default 1.5)
      z_threshold – Z-score threshold (default 3.0)
    """
    col = params.get("column")
    method = params.get("method", "iqr")
    strategy = params.get("strategy", "median")
    iqr_factor = float(params.get("iqr_factor", 1.5))
    z_threshold = float(params.get("z_threshold", 3.0))

    if not (col and col in df.columns and pd.api.types.is_numeric_dtype(df[col])):
        return df

    if method == "zscore":
        mean = df[col].mean()
        std = df[col].std()
        if std == 0:
            return df
        outlier_mask = ((df[col] - mean).abs() / std) > z_threshold
    else:  # iqr
        q1 = df[col].quantile(0.25)
        q3 = df[col].quantile(0.75)
        iqr = q3 - q1
        outlier_mask = (df[col] < q1 - iqr_factor * iqr) | (
            df[col] > q3 + iqr_factor * iqr
        )

    non_outlier = df[col][~outlier_mask]

    if strategy == "mean":
        fill = non_outlier.mean()
    elif strategy == "median":
        fill = non_outlier.median()
    else:  # nan
        fill: float = np.nan

    df.loc[outlier_mask, col] = fill
    return df


def _round_numeric(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Round numeric column(s) to N decimal places.
    params:
      column   – target column; omit to round all numeric columns
      decimals – int (default 2)
    """
    col = params.get("column")
    decimals = int(params.get("decimals", 2))
    cols = [col] if col else df.select_dtypes(include=np.number).columns.tolist()

    for c in cols:
        if c in df.columns and pd.api.types.is_numeric_dtype(df[c]):
            df[c] = df[c].round(decimals)
    return df


def _scale_numeric(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Normalise / standardise numeric column(s).
    params:
      column – target column; omit to apply to all numeric columns
      method – "min_max" (default) or "z_score"
    """
    col = params.get("column")
    method = params.get("method", "min_max")
    cols = [col] if col else df.select_dtypes(include=np.number).columns.tolist()

    for c in cols:
        if c not in df.columns or not pd.api.types.is_numeric_dtype(df[c]):
            continue
        if method == "z_score":
            mean, std = df[c].mean(), df[c].std()
            if std > 0:
                df[c] = (df[c] - mean) / std
        else:  # min_max
            mn, mx = df[c].min(), df[c].max()
            if mx != mn:
                df[c] = (df[c] - mn) / (mx - mn)

    return df


def _bin_numeric(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Bucketize a continuous numeric column into N discrete bins.
    params:
      column   – target column (required)
      bins     – number of bins (default 5)
      strategy – "equal_width" (default) or "quantile"
      labels   – optional list of bin labels (must equal bins count)
      new_col  – name for the new binned column (default "{column}_bin")
    """
    col = params.get("column")
    bins = int(params.get("bins", 5))
    strategy = params.get("strategy", "equal_width")
    labels = params.get("labels")  # list or None
    new_col = params.get("new_col", f"{col}_bin" if col else "bin")

    if not (col and col in df.columns and pd.api.types.is_numeric_dtype(df[col])):
        return df

    label_list: Optional[list] = labels if labels and len(labels) == bins else None

    try:
        if strategy == "quantile":
            df[new_col] = pd.qcut(
                df[col], q=bins, labels=label_list, duplicates="drop"
            ).astype(str)
        else:
            df[new_col] = pd.cut(df[col], bins=bins, labels=label_list).astype(str)
    except ValueError as exc:
        # Surface binning failures clearly — e.g. all-identical values, non-numeric data
        raise ValueError(
            f"Cannot bin column '{col}' into {bins} bins: {exc}. "
            "Try fewer bins or check the column has sufficient unique numeric values."
        )
    except Exception as exc:
        raise ValueError(f"Binning failed for column '{col}': {exc}")

    return df


# ══════════════════════════════════════════════════════════════════════════════
# ── NEW: Missing value strategies ─────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════


def _fill_missing_ffill(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Forward-fill (propagate last valid observation forward).
    Essential for time-series data.
    params:
      column – target column; omit to forward-fill entire DataFrame
    """
    col = params.get("column")
    if col and col in df.columns:
        df[col] = df[col].ffill()
    else:
        df = df.ffill()
    return df


def _fill_missing_bfill(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Backward-fill (propagate next valid observation backward).
    params:
      column – target column; omit to back-fill entire DataFrame
    """
    col = params.get("column")
    if col and col in df.columns:
        df[col] = df[col].bfill()
    else:
        df = df.bfill()
    return df


def _fill_missing_interpolate(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Interpolate missing values (numeric columns only).
    params:
      column – target column; omit to interpolate all numeric columns
      method – pandas interpolation method (default "linear")
    """
    col = params.get("column")
    method = params.get("method", "linear")

    if col and col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            df[col] = df[col].interpolate(method=method)
    else:
        for c in df.select_dtypes(include=np.number).columns:
            df[c] = df[c].interpolate(method=method)
    return df


def _drop_rows_missing_threshold(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Drop rows that have more than `threshold` fraction of missing values.
    params:
      threshold – float 0–1; rows with > threshold missing fraction are dropped
                  (default 0.5 = drop rows missing more than 50% of columns)
    """
    threshold = float(params.get("threshold", 0.5))
    total_cols: int = len(df.columns)
    min_non_null: int = max(1, int(total_cols * (1 - threshold)))
    df = df.dropna(thresh=min_non_null).reset_index(drop=True)
    return df


# ══════════════════════════════════════════════════════════════════════════════
# ── NEW: Structure / schema transformations ───────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════


def _cast_type(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Cast a column to a different data type with graceful error handling.
    params:
      column        – target column (required)
      dtype         – "int" | "float" | "string" | "bool" | "category" | "date"
      ignore_errors – bool (default True); if True, silently converts invalid values to NaN
    """
    col = params.get("column")
    target_type = params.get("dtype")
    ignore_errors = bool(params.get("ignore_errors", True))

    if not (col and col in df.columns and target_type):
        return df

    if target_type == "int":
        # Silently convert invalid values to NaN (Int64 supports missing values)
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    elif target_type == "float":
        df[col] = pd.to_numeric(df[col], errors="coerce")

    elif target_type == "string":
        df[col] = df[col].astype(str)

    elif target_type == "bool":
        truthy: set[str] = {"true", "1", "yes", "y", "on"}
        falsy: set[str] = {"false", "0", "no", "n", "off"}

        def _to_bool(x: Any) -> Any:
            if pd.isna(x):
                return pd.NA
            s: str = str(x).strip().lower()
            if s in truthy:
                return True
            if s in falsy:
                return False
            return pd.NA

        df[col] = df[col].apply(_to_bool).astype("boolean")

    elif target_type == "category":
        # Use safe categorical conversion that handles NaN and edge cases
        df[col] = _safe_categorical_conversion(df[col])

    elif target_type == "date":
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y-%m-%d")

    return df


def _conditional_column(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Add a new boolean / label column derived from a condition on another column.
    params:
      column      – source column (required)
      condition   – "gt" | "gte" | "lt" | "lte" | "eq" | "neq" |
                    "contains" | "starts_with" | "ends_with" | "not_null"
      value       – comparison value (not needed for not_null)
      true_label  – value for matching rows (default "yes")
      false_label – value for non-matching rows (default "no")
      new_col     – name of the new column (default "{column}_flag")
    """
    col = params.get("column")
    condition = params.get("condition", "gt")
    value = params.get("value")
    true_label = params.get("true_label", "yes")
    false_label = params.get("false_label", "no")
    new_col = params.get("new_col", f"{col}_flag" if col else "new_flag")

    if not (col and col in df.columns):
        return df

    series = df[col]
    numeric = pd.to_numeric(series, errors="coerce")

    if value is None:
        return df

    condition_map: Dict[str, Callable[[], Any]] = {
        "gt": lambda: numeric > float(value),  # type: ignore
        "gte": lambda: numeric >= float(value),  # type: ignore
        "lt": lambda: numeric < float(value),  # type: ignore
        "lte": lambda: numeric <= float(value),  # type: ignore
        "eq": lambda: series.astype(str) == str(value),
        "neq": lambda: series.astype(str) != str(value),
        "contains": lambda: series.astype(str).str.contains(
            str(value), na=False, case=False
        ),
        "starts_with": lambda: series.astype(str).str.startswith(str(value)),
        "ends_with": lambda: series.astype(str).str.endswith(str(value)),
        "not_null": lambda: series.notna(),
    }

    fn: Callable[[], Any] | None = condition_map.get(condition)
    if fn is None:
        return df

    try:
        mask = fn()
    except (ValueError, TypeError):
        return df

    df[new_col] = mask.map({True: true_label, False: false_label})
    return df


def _drop_constant_columns(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Remove columns with zero variance (all values identical or all NaN).
    params: (none)
    """
    constant_cols: List[str] = [c for c in df.columns if df[c].dropna().nunique() <= 1]
    if constant_cols:
        df = df.drop(columns=constant_cols)
    return df


def _drop_high_missing_columns(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Remove columns where the fraction of missing values exceeds the threshold.
    params:
      threshold – float 0–1 (default 0.5 = drop columns with > 50% missing)
    """
    threshold = float(params.get("threshold", 0.5))
    total: int = len(df)
    cols_to_drop: List[str] = [
        c for c in df.columns if total > 0 and df[c].isnull().sum() / total > threshold
    ]
    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)
    return df


# ══════════════════════════════════════════════════════════════════════════════
# ── NEW: Date transformations ─────────────────────────────────────────────────
# ISO 8601 pattern: YYYY-MM-DD or YYYY/MM/DD — must NOT use dayfirst
import re as _re

_ISO_DATE_RE: re.Pattern[str] = _re.compile(r"^\d{4}[-/]\d{2}[-/]\d{2}")


def _smart_parse_dates(series: pd.Series, dayfirst: bool = True) -> pd.Series:
    """
    Parse a Series of mixed-format date strings using dateutil.
    Automatically detects ISO format (YYYY-MM-DD) and overrides dayfirst=False
    for those cells to avoid misparses like 2024-01-07 → July 1st.
    Returns a proper pandas datetime64 Series so .dt accessor works correctly.
    """
    from dateutil import parser as _dp

    def _one(val: Any) -> Any:
        if pd.isna(val) or str(val).strip() == "":
            return pd.NaT
        s: str = str(val).strip()
        # ISO dates: YYYY-MM-DD — always parse year-first, never dayfirst
        use_dayfirst: bool = dayfirst and not bool(_ISO_DATE_RE.match(s))
        try:
            return _dp.parse(s, dayfirst=use_dayfirst)
        except Exception:
            return pd.NaT

    # apply() returns object dtype; cast to datetime64 so .dt accessor works
    raw: Series[Any] = series.apply(_one)
    return pd.to_datetime(raw, errors="coerce", utc=False)


# ══════════════════════════════════════════════════════════════════════════════


def _standardise_mixed_dates(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Detect and standardise mixed date formats in a column.

    Handles all common formats automatically:
      DD-MM-YYYY, MM-DD-YYYY, D/M/YYYY, M/D/YYYY,
      YYYY/MM/DD, D.M.YYYY, "Jan 15 2020", "15 Jan 2020", Unix timestamps, etc.

    Uses dateutil for per-cell parsing (most flexible) and falls back to
    pandas for speed on large columns.

    params:
      column    – target column (required)
      dayfirst  – bool, hint for ambiguous dates like 05-06-2020
                  True  → 5th June (DD-MM) [default]
                  False → May 6th  (MM-DD)
      output_format – strftime format string (default "%Y-%m-%d" = ISO 8601)
    """
    from dateutil import parser as _dateutil_parser

    col = params.get("column")
    dayfirst = bool(params.get("dayfirst", True))
    output_format = params.get("output_format", "%Y-%m-%d")

    if not (col and col in df.columns):
        return df

    def _parse_one(val: Any) -> Any:
        if pd.isna(val) or str(val).strip() == "":
            return pd.NaT
        try:
            return _dateutil_parser.parse(str(val).strip(), dayfirst=dayfirst)
        except Exception:
            return pd.NaT

    parsed = df[col].apply(_parse_one)
    df[col] = parsed.apply(lambda x: x.strftime(output_format) if pd.notna(x) else None)
    return df


def _extract_date_parts(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Extract year, month, day (and optionally weekday / quarter / week) from
    a date column into separate new columns.

    params:
      column  – source date column (required)
      parts   – list of parts to extract; any of:
                "year", "month", "day", "weekday", "quarter",
                "week", "hour", "minute", "second"
                default: ["year", "month", "day"]
      prefix  – prefix for new column names (default: "{column}_")
      dayfirst – bool, passed to pd.to_datetime (default True)
    """
    col = params.get("column")
    parts = params.get("parts", ["year", "month", "day"])
    prefix = params.get("prefix") or f"{col}_"
    dayfirst = bool(params.get("dayfirst", True))

    if not (col and col in df.columns):
        return df

    # _smart_parse_dates now returns a proper datetime64 Series
    parsed: Series[Any] = _smart_parse_dates(df[col], dayfirst=dayfirst)

    part_extractors = {
        "year": lambda s: s.dt.year.astype("Int64"),
        "month": lambda s: s.dt.month.astype("Int64"),
        "day": lambda s: s.dt.day.astype("Int64"),
        "weekday": lambda s: s.dt.day_name(),
        "quarter": lambda s: s.dt.quarter,
        "week": lambda s: s.dt.isocalendar().week.astype("int64"),
        "hour": lambda s: s.dt.hour,
        "minute": lambda s: s.dt.minute,
        "second": lambda s: s.dt.second,
    }

    for part in parts:
        extractor = part_extractors.get(part)
        if extractor:
            new_col: str = f"{prefix}{part}"
            # Guard: avoid double-suffix if prefix already ends with the part name
            # e.g. prefix="date_year_", part="year" → would create "date_year_year"
            if prefix.rstrip("_").endswith(part):
                new_col = prefix.rstrip("_")
            df[new_col] = extractor(parsed)

    return df


def _calculate_date_diff(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Calculate the difference between two date columns (or between one column
    and a fixed reference date) and store the result in a new column.

    params:
      column      – first date column (required)
      column2     – second date column (optional; mutually exclusive with reference_date)
      reference_date – fixed ISO date string e.g. "2024-01-01" (optional)
      unit        – "days" | "weeks" | "months" | "years" (default "days")
      new_col     – name for result column (default "{column}_diff_days")
      absolute    – bool, return absolute (positive) difference (default True)
      dayfirst    – bool (default True)
    """
    import math

    col = params.get("column")
    col2 = params.get("column2")
    ref_str = params.get("reference_date")
    unit = params.get("unit", "days")
    new_col = params.get("new_col") or f"{col}_diff_{unit}"
    absolute = bool(params.get("absolute", True))
    dayfirst = bool(params.get("dayfirst", True))

    if not (col and col in df.columns):
        return df

    date_a: Series[Any] = _smart_parse_dates(df[col], dayfirst=dayfirst)

    if col2 and col2 in df.columns:
        date_b: Series[Any] = _smart_parse_dates(df[col2], dayfirst=dayfirst)
    elif ref_str:
        date_b = pd.to_datetime(ref_str, errors="coerce")
    else:
        return df

    delta_days = (date_a - date_b).dt.days
    if absolute:
        delta_days = delta_days.abs()

    if unit == "days":
        df[new_col] = delta_days
    elif unit == "weeks":
        df[new_col] = (delta_days / 7).round(1)
    elif unit == "months":
        df[new_col] = (delta_days / 30.4375).round(1)
    elif unit == "years":
        df[new_col] = (delta_days / 365.25).round(2)
    else:
        df[new_col] = delta_days

    return df


def _flag_future_dates(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Add a boolean flag column marking dates that are in the future
    (or beyond a custom cutoff date).

    params:
      column      – date column (required)
      cutoff_date – ISO date string; dates after this are flagged (default: today)
      flag_col    – name of the new flag column (default "{column}_is_future")
      dayfirst    – bool (default True)
    """
    import datetime

    col = params.get("column")
    cutoff_str = params.get("cutoff_date")
    flag_col = params.get("flag_col") or f"{col}_is_future"
    dayfirst = bool(params.get("dayfirst", True))

    if not (col and col in df.columns):
        return df

    parsed: Series[Any] = _smart_parse_dates(df[col], dayfirst=dayfirst)
    cutoff = (
        pd.to_datetime(cutoff_str, errors="coerce")
        if cutoff_str
        else pd.Timestamp(datetime.datetime.now().date())
    )

    df[flag_col] = parsed > cutoff
    return df


def _flag_weekend_dates(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Add a boolean flag column marking dates that fall on a weekend
    (Saturday or Sunday).

    params:
      column   – date column (required)
      flag_col – name of the new flag column (default "{column}_is_weekend")
      dayfirst – bool (default True)
    """
    col = params.get("column")
    flag_col = params.get("flag_col") or f"{col}_is_weekend"
    dayfirst = bool(params.get("dayfirst", True))

    if not (col and col in df.columns):
        return df

    parsed: Series[Any] = _smart_parse_dates(df[col], dayfirst=dayfirst)
    df[flag_col] = parsed.dt.dayofweek >= 5  # 5=Sat, 6=Sun
    return df


def _age_from_date(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Calculate age in years (or other unit) from a date-of-birth column.

    params:
      column      – date column (required)
      reference_date – ISO date string to calculate age from (default: today)
      unit        – "years" | "months" | "days" (default "years")
      new_col     – name of the new column (default "{column}_age")
      dayfirst    – bool (default True)
    """
    import datetime

    col = params.get("column")
    ref_str = params.get("reference_date")
    unit = params.get("unit", "years")
    new_col = params.get("new_col") or f"{col}_age"
    dayfirst = bool(params.get("dayfirst", True))

    if not (col and col in df.columns):
        return df

    parsed: Series[Any] = _smart_parse_dates(df[col], dayfirst=dayfirst)
    ref = (
        pd.to_datetime(ref_str, errors="coerce")
        if ref_str
        else pd.Timestamp(datetime.datetime.now().date())
    )

    delta_days = (ref - parsed).dt.days

    if unit == "years":
        df[new_col] = (delta_days / 365.25).apply(
            lambda x: int(x) if pd.notna(x) and x >= 0 else None
        )
    elif unit == "months":
        df[new_col] = (delta_days / 30.4375).apply(
            lambda x: round(x, 1) if pd.notna(x) and x >= 0 else None
        )
    else:
        df[new_col] = delta_days.apply(
            lambda x: int(x) if pd.notna(x) and x >= 0 else None
        )

    return df


# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
# ── NEW: Power features ───────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════


def _drop_rows_matching(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Drop rows where a column value matches a regex pattern.
    Unlike drop_rows_where (exact equality), this supports partial/regex matching.
    params:
      column   – target column (required)
      pattern  – regex pattern (required)
      keep     – bool; if True, KEEP matching rows instead of dropping (default False)
      flags    – regex flags string e.g. "i" for case-insensitive (default "")
    """
    col = params.get("column")
    pattern = params.get("pattern", "")
    keep = bool(params.get("keep", False))
    flags_s = params.get("flags", "")

    if not (col and col in df.columns and pattern):
        return df

    import re

    re_flags = 0
    if "i" in flags_s:
        re_flags |= re.IGNORECASE
    if "m" in flags_s:
        re_flags |= re.MULTILINE

    mask = (
        df[col].astype(str).str.contains(pattern, regex=True, flags=re_flags, na=False)
    )
    if keep:
        return df[mask].reset_index(drop=True)
    return df[~mask].reset_index(drop=True)


def _reorder_columns(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Reorder DataFrame columns.
    params:
      order – list of column names in desired order (required)
              Columns not listed are appended at the end in original order.
    """
    order = params.get("order", [])
    if not order:
        return df

    # Build final order: listed cols first, then remaining in original order
    listed = [c for c in order if c in df.columns]
    remaining: List[str] = [c for c in df.columns if c not in listed]
    return df[listed + remaining]


def _rename_columns_bulk(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Rename multiple columns at once via a mapping dict.
    params:
      mapping – {"old_name": "new_name", ...} (required)
    """
    mapping = params.get("mapping", {})
    if not mapping:
        return df
    # Only rename columns that exist
    valid_mapping = {k: v for k, v in mapping.items() if k in df.columns and v}
    if valid_mapping:
        df = df.rename(columns=valid_mapping)
    return df


def _apply_schema_suggestions(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Apply a batch of type-cast suggestions from schema inference.
    params:
      suggestions – list of {column, suggested_dtype} dicts
                    (same format returned by infer_schema_suggestions)
    """
    suggestions = params.get("suggestions", [])
    for s in suggestions:
        col = s.get("column")
        dtype = s.get("suggested_dtype")
        if col and dtype and col in df.columns:
            df = _cast_type(df, {"column": col, "dtype": dtype})
    return df


def _normalize_column_names(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Normalize all column names to snake_case:
      "Transaction ID"  → "transaction_id"
      "  First Name  "  → "first_name"
      "DOB (DD/MM/YYYY)"→ "dob_dd_mm_yyyy"
    params:
      style – "snake_case" (default) | "camel_case" | "lower" | "upper"
    """
    import re as _re

    style = params.get("style", "snake_case")

    def _to_snake(name: str) -> str:
        # Remove special chars, replace spaces/dashes with underscores
        s: str = _re.sub(r"[^a-zA-Z0-9\s_]", " ", str(name).strip())
        s: str = _re.sub(r"[\s\-]+", "_", s)
        s: str = _re.sub(r"_+", "_", s).strip("_").lower()
        return s or "col"

    def _to_camel(name: str) -> str:
        parts: List[str] = _to_snake(name).split("_")
        return parts[0] + "".join(p.capitalize() for p in parts[1:])

    if style == "camel_case":
        df.columns = [_to_camel(c) for c in df.columns]
    elif style == "upper":
        df.columns = [c.strip().upper().replace(" ", "_") for c in df.columns]
    elif style == "lower":
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    else:  # snake_case
        df.columns = [_to_snake(c) for c in df.columns]

    return df


# ── Delegating actions (fuzzy / SQL) ─────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════


def _fuzzy_remove_duplicates(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Remove near-duplicate rows using RapidFuzz."""
    from services.fuzzy_dedup import remove_fuzzy_duplicates

    threshold = params.get("threshold", 85)
    columns = params.get("columns")
    return remove_fuzzy_duplicates(df, columns=columns, threshold=threshold)


def _sql_apply(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Apply a SQL SELECT query and return the result as the new DataFrame."""
    from services.sql_engine import sql_to_dataframe

    query = params.get("query", "")
    if not query:
        raise ValueError("sql_apply requires a 'query' param.")
    return sql_to_dataframe(df, query)


# ══════════════════════════════════════════════════════════════════════════════
# ── Action registry ───────────────────────────────────════════════════════════
# ══════════════════════════════════════════════════════════════════════════════

# ── Vocabulary mapper ──────────────────────────────────────────────────────────


def _map_to_standard(df, params) -> Hashable:
    """
    Map a column through a built-in vocabulary dictionary.
    params: column, vocab (country_name|country_code|currency|us_state|gender|boolean),
            unmapped ("keep"|"blank"|"error")
    """
    from services.vocab_mapper import map_column_to_standard

    column = params.get("column")
    vocab = params.get("vocab")
    unmapped = params.get("unmapped", "keep")
    if not column:
        raise ValueError("map_to_standard: 'column' param is required.")
    if not vocab:
        raise ValueError("map_to_standard: 'vocab' param is required.")
    df_out, _stats = map_column_to_standard(df, column, vocab, unmapped)
    return df_out





# ══════════════════════════════════════════════════════════════════════════════
# ── ADVANCED: Text & NLP ─────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════


def _extract_email_domain(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Extract domain from email addresses into a new column."""
    col = params.get("column")
    new_col = params.get("new_col", f"{col}_domain")
    if not (col and col in df.columns):
        return df
    df[new_col] = df[col].astype(str).str.extract(r"@([^@]+)", expand=False)
    return df


def _extract_url_parts(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Extract parts of URLs (domain, path, params) into separate columns."""
    col = params.get("column")
    parts = params.get("parts", ["domain", "path", "protocol"])
    if not (col and col in df.columns):
        return df
    for part in parts:
        new_col = f"{col}_{part}"
        if part == "domain":
            df[new_col] = (
                df[col].astype(str).str.extract(r"https?://([^/]+)", expand=False)
            )
        elif part == "path":
            df[new_col] = (
                df[col]
                .astype(str)
                .str.extract(r"https?://[^/]+(/[^\?]*)?", expand=False)
            )
        elif part == "protocol":
            df[new_col] = df[col].astype(str).str.extract(r"(https?)://", expand=False)
    return df


def _parse_currency(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Extract numeric value from currency strings like '$1,234.56' or '€99,99'."""
    col = params.get("column")
    currency_symbol = params.get("symbol", "")
    new_col = params.get("new_col", f"{col}_amount")
    if not (col and col in df.columns):
        return df
    pattern = r"[-+]?\$?€?£?¥?[\d,]+\.?\d*"
    df[new_col] = df[col].astype(str).str.extract(pattern, expand=False)
    df[new_col] = df[new_col].str.replace(r"[^\d.\-]", "", regex=True)
    df[new_col] = pd.to_numeric(df[new_col], errors="coerce")
    return df


def _parse_number_formatted(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Parse formatted numbers like '1,000.00' or '1.000,00' (EU format)."""
    col = params.get("column")
    decimal = params.get("decimal_format", "us")  # us or eu
    new_col = params.get("new_col", f"{col}_parsed")
    if not (col and col in df.columns):
        return df
    if decimal == "eu":
        df[new_col] = (
            df[col]
            .astype(str)
            .str.replace(r"[.\s]", "", regex=True)
            .str.replace(",", ".", regex=False)
        )
    else:
        df[new_col] = df[col].astype(str).str.replace(",", "", regex=False)
    df[new_col] = pd.to_numeric(df[new_col], errors="coerce")
    return df


def _extract_regex_groups(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Extract regex capture groups into new columns."""
    col = params.get("column")
    pattern = params.get("pattern")
    group_names = params.get("group_names", [])
    if not (col and col in df.columns and pattern):
        return df
    try:
        extracted = df[col].astype(str).str.extract(pattern, expand=True)
        for i, name in enumerate(group_names[: len(extracted.columns)]):
            if name and name != i:
                extracted.columns.values[i] = name
        df = pd.concat([df, extracted], axis=1)
    except Exception:
        pass
    return df


def _tokenize_text(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Split text into tokens/words."""
    col = params.get("column")
    new_col = params.get("new_col", f"{col}_tokens")
    delimiter = params.get("delimiter", " ")
    if not (col and col in df.columns):
        return df
    df[new_col] = df[col].astype(str).str.split(delimiter)
    return df


def _remove_stopwords(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Remove common stopwords from text."""
    col = params.get("column")
    language = params.get("language", "english")
    stopwords_set = {
        "english": {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "shall",
            "can",
            "need",
            "dare",
            "ought",
            "used",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "under",
            "again",
            "further",
            "then",
            "once",
            "here",
            "there",
            "when",
            "where",
            "why",
            "how",
            "all",
            "each",
            "few",
            "more",
            "most",
            "other",
            "some",
            "such",
            "no",
            "nor",
            "not",
            "only",
            "own",
            "same",
            "so",
            "than",
            "too",
            "very",
            "just",
            "but",
            "and",
            "or",
            "if",
            "because",
            "until",
            "while",
            "although",
            "this",
            "that",
            "these",
            "those",
            "am",
            "its",
            "it",
            "i",
            "you",
            "he",
            "she",
            "we",
            "they",
        },
    }
    words = stopwords_set.get(language, stopwords_set["english"])
    cols = [col] if col else [c for c in df.columns if _is_string_col(df[c])]
    for c in cols:
        if c not in df.columns:
            continue
        df[c] = (
            df[c]
            .astype(str)
            .apply(lambda x: " ".join(w for w in x.split() if w.lower() not in words))
        )
    return df


def _stem_text(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Apply stemming to reduce words to root form."""
    col = params.get("column")
    stemmer = params.get("stemmer", "porter")
    if not (col and col in df.columns):
        return df
    try:
        from nltk.stem import PorterStemmer, SnowballStemmer

        stem = (
            SnowballStemmer("english").stem
            if stemmer == "snowball"
            else PorterStemmer().stem
        )
        df[col] = (
            df[col].astype(str).apply(lambda x: " ".join(stem(w) for w in x.split()))
        )
    except ImportError:
        pass
    return df


def _lemmatize_text(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Apply lemmatization to reduce words to dictionary form."""
    col = params.get("column")
    if not (col and col in df.columns):
        return df
    try:
        from nltk.stem import WordNetLemmatizer

        lemmatizer = WordNetLemmatizer()
        df[col] = (
            df[col]
            .astype(str)
            .apply(lambda x: " ".join(lemmatizer.lemmatize(w) for w in x.split()))
        )
    except ImportError:
        pass
    return df


def _detect_encoding(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Detect character encoding of text columns."""
    col = params.get("column")
    new_col = params.get("new_col", f"{col}_encoding")
    if not (col and col in df.columns):
        return df

    def _detect(sample):
        import chardet

        result = chardet.detect(sample.encode() if isinstance(sample, str) else sample)
        return result.get("encoding", "unknown")

    df[new_col] = df[col].astype(str).apply(lambda x: _detect(x[:100]))
    return df


def _convert_encoding(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Convert text from one encoding to another."""
    col = params.get("column")
    from_encoding = params.get("from", "latin-1")
    to_encoding = params.get("to", "utf-8")
    if not (col and col in df.columns):
        return df

    def _convert(text):
        try:
            return text.encode(to_encoding).decode(to_encoding)
        except Exception:
            return text

    df[col] = df[col].astype(str).apply(_convert)
    return df


# ══════════════════════════════════════════════════════════════════════════════
# ── ADVANCED: Data Transforms ─────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════


def _pivot_table(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Create a pivot table."""
    index = params.get("index")
    columns = params.get("columns")
    values = params.get("values")
    aggfunc = params.get("aggfunc", "sum")
    if not (index and columns and values):
        return df
    result = df.pivot_table(
        index=index, columns=columns, values=values, aggfunc=aggfunc, fill_value=0
    )
    result.columns = [f"{c[0]}_{c[1]}" for c in result.columns]
    return result.reset_index()


def _unpivot(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Unpivot/melt a pivot table."""
    id_cols = params.get("id_columns", [])
    value_cols = params.get("value_columns", None)
    var_name = params.get("var_name", "variable")
    val_name = params.get("val_name", "value")
    if not id_cols:
        return df
    result = pd.melt(
        df, id_vars=id_cols, value_vars=value_cols, var_name=var_name, val_name=val_name
    )
    return result.dropna(subset=[val_name])


def _cross_column_ratio(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Calculate ratio between two columns."""
    col1 = params.get("column1")
    col2 = params.get("column2")
    new_col = params.get("new_col", f"{col1}_div_{col2}")
    if not (col1 and col2 and col1 in df.columns and col2 in df.columns):
        return df
    df[new_col] = pd.to_numeric(df[col1], errors="coerce") / pd.to_numeric(
        df[col2], errors="coerce"
    ).replace(0, np.nan)
    return df


def _cross_column_diff(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Calculate difference between two columns."""
    col1 = params.get("column1")
    col2 = params.get("column2")
    new_col = params.get("new_col", f"{col1}_minus_{col2}")
    if not (col1 and col2 and col1 in df.columns and col2 in df.columns):
        return df
    df[new_col] = pd.to_numeric(df[col1], errors="coerce") - pd.to_numeric(
        df[col2], errors="coerce"
    )
    return df


def _percentage_change(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Calculate percentage change between column values."""
    col = params.get("column")
    periods = params.get("periods", 1)
    new_col = params.get("new_col", f"{col}_pct_change")
    if not (col and col in df.columns):
        return df
    df[new_col] = df[col].pct_change(periods=periods) * 100
    return df


def _add_rank(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Add ranking column based on a numeric column."""
    col = params.get("column")
    new_col = params.get("new_col", f"{col}_rank")
    method = params.get("method", "average")
    if not (col and col in df.columns):
        return df
    df[new_col] = df[col].rank(method=method, ascending=False).astype(int)
    return df


def _add_percentile(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Add percentile rank column."""
    col = params.get("column")
    new_col = params.get("new_col", f"{col}_percentile")
    if not (col and col in df.columns):
        return df
    df[new_col] = df[col].rank(pct=True) * 100
    return df


def _rolling_stats(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Calculate rolling statistics."""
    col = params.get("column")
    window = params.get("window", 7)
    operations = params.get("operations", ["mean"])
    partition_by = params.get("partition_by")
    if not (col and col in df.columns):
        return df
    for op in operations:
        new_col = f"{col}_rolling_{op}_{window}"
        if partition_by and partition_by in df.columns:
            df[new_col] = df.groupby(partition_by)[col].transform(
                lambda x: getattr(x.rolling(window), op)()
            )
        else:
            df[new_col] = getattr(df[col].rolling(window), op)()
    return df


def _cumulative_sum(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Add cumulative sum column."""
    col = params.get("column")
    new_col = params.get("new_col", f"{col}_cumsum")
    partition_by = params.get("partition_by")
    if not (col and col in df.columns):
        return df
    if partition_by and partition_by in df.columns:
        df[new_col] = df.groupby(partition_by)[col].cumsum()
    else:
        df[new_col] = df[col].cumsum()
    return df


def _cumulative_stats(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Add multiple cumulative statistics."""
    col = params.get("column")
    operations = params.get("operations", ["sum", "max", "min"])
    window = params.get("window", None)
    if not (col and col in df.columns):
        return df
    for op in operations:
        new_col = f"{col}_cum_{op}"
        if window:
            df[new_col] = getattr(df[col].rolling(window), op)()
        else:
            df[new_col] = getattr(df[col].expanding(), op)()
    return df


def _lag_column(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Add lagged version of a column."""
    col = params.get("column")
    periods = params.get("periods", 1)
    new_col = params.get("new_col", f"{col}_lag_{periods}")
    partition_by = params.get("partition_by")
    if not (col and col in df.columns):
        return df
    if partition_by and partition_by in df.columns:
        df[new_col] = df.groupby(partition_by)[col].shift(periods)
    else:
        df[new_col] = df[col].shift(periods)
    return df


def _lead_column(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Add lead (future) version of a column."""
    col = params.get("column")
    periods = params.get("periods", 1)
    new_col = params.get("new_col", f"{col}_lead_{periods}")
    partition_by = params.get("partition_by")
    if not (col and col in df.columns):
        return df
    if partition_by and partition_by in df.columns:
        df[new_col] = df.groupby(partition_by)[col].shift(-periods)
    else:
        df[new_col] = df[col].shift(-periods)
    return df


# ══════════════════════════════════════════════════════════════════════════════
# ── ADVANCED: Sampling & Split ───────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════


def _sample_random(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Random sampling from dataframe."""
    n = params.get("n")
    frac = params.get("frac")
    seed = params.get("seed", 42)
    if n:
        return df.sample(n=min(n, len(df)), random_state=seed)
    elif frac:
        return df.sample(frac=frac, random_state=seed)
    return df


def _sample_stratified(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Stratified sampling based on a column."""
    col = params.get("column")
    n = params.get("n", 1)
    seed = params.get("seed", 42)
    if not (col and col in df.columns):
        return df
    return df.groupby(col, group_keys=False).apply(
        lambda x: x.sample(min(len(x), n), random_state=seed)
    )


def _train_test_split(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Split into train/test sets. Returns train by default, test if return_test=True."""
    test_size = params.get("test_size", 0.2)
    seed = params.get("seed", 42)
    return df.sample(frac=1 - test_size, random_state=seed)


# ══════════════════════════════════════════════════════════════════════════════
# ── ADVANCED: Deduplication ────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════


def _fuzzy_match_merge(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Find fuzzy matches and merge/consolidate duplicates."""
    col = params.get("column")
    threshold = params.get("threshold", 85)
    strategy = params.get("strategy", "keep_first")
    if not (col and col in df.columns):
        return df
    unique_vals = df[col].dropna().unique()
    mapping = {}
    for val in unique_vals:
        if val not in mapping:
            for other in unique_vals:
                if other != val and other not in mapping:
                    if _strings_similar(str(val), str(other), threshold):
                        mapping[other] = val
    if mapping:
        df[col] = df[col].map(lambda x: mapping.get(x, x))
    return df.drop_duplicates() if strategy == "keep_first" else df


def _strings_similar(s1: str, s2: str, threshold: float) -> bool:
    """Check if two strings are similar using rapidfuzz."""
    try:
        from rapidfuzz import fuzz

        return fuzz.ratio(s1.lower(), s2.lower()) >= threshold
    except ImportError:
        return s1.lower() == s2.lower()


def _remove_exact_duplicates(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Remove exact duplicate rows."""
    subset = params.get("subset")
    keep = params.get("keep", "first")
    return df.drop_duplicates(subset=subset, keep=keep).reset_index(drop=True)


def _dedupe_by_key(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Deduplicate by key column, keeping best row based on score column."""
    key_col = params.get("key_column")
    score_col = params.get("score_column")
    keep = params.get("keep", "max")
    if not (key_col and key_col in df.columns):
        return df
    if score_col and score_col in df.columns:
        ascending = keep == "min"
        return df.sort_values(score_col, ascending=ascending).drop_duplicates(
            subset=[key_col], keep="first"
        )
    return df.drop_duplicates(subset=[key_col], keep=keep)


# ══════════════════════════════════════════════════════════════════════════════
# ── ADVANCED: Data Shaping ──────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════


def _transpose_data(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Transpose dataframe (rows become columns)."""
    first_col = params.get("index_column")
    if first_col and first_col in df.columns:
        df = df.set_index(first_col)
    return df.T.reset_index()


def _stack_columns(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Stack multiple columns into key-value pairs."""
    cols = params.get("columns", [])
    if not cols:
        return df
    id_vars = [c for c in df.columns if c not in cols]
    return pd.melt(df, id_vars=id_vars, value_vars=cols)


def _one_hot_encode(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """One-hot encode a categorical column."""
    col = params.get("column")
    prefix = params.get("prefix", col)
    if not (col and col in df.columns):
        return df
    dummies = pd.get_dummies(df[col], prefix=prefix, dtype=int)
    return pd.concat([df, dummies], axis=1)


def _label_encode(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Label encode a categorical column."""
    col = params.get("column")
    new_col = params.get("new_col", f"{col}_encoded")
    if not (col and col in df.columns):
        return df
    categories = df[col].astype("category").cat.categories
    df[new_col] = df[col].astype("category").cat.codes
    return df


# ══════════════════════════════════════════════════════════════════════════════
# ── ADVANCED: Validation ────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════


def _validate_email_advanced(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Validate emails with more thorough checking."""
    col = params.get("column")
    flag_col = params.get("flag_col", f"{col}_email_valid")
    if not (col and col in df.columns):
        return df
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    df[flag_col] = df[col].astype(str).str.match(pattern)
    return df


def _validate_phone(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Validate phone numbers."""
    col = params.get("column")
    flag_col = params.get("flag_col", f"{col}_phone_valid")
    country = params.get("country", "US")
    patterns = {
        "US": r"^\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}$",
        "UK": r"^\+?44[-.\s]?\d{4}[-.\s]?\d{6}$",
        "INTL": r"^\+?[\d\s\-().]{10,}$",
    }
    pattern = patterns.get(country, patterns["INTL"])
    if not (col and col in df.columns):
        return df
    df[flag_col] = df[col].astype(str).str.match(pattern)
    return df


def _validate_postal_code(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Validate postal/zip codes."""
    col = params.get("column")
    flag_col = params.get("flag_col", f"{col}_postal_valid")
    country = params.get("country", "US")
    patterns = {
        "US": r"^\d{5}(-\d{4})?$",
        "UK": r"^[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}$",
        "CA": r"^[A-Z]\d[A-Z]\s?\d[A-Z]\d$",
        "IN": r"^\d{6}$",
    }
    pattern = patterns.get(country, r"^\d+")
    if not (col and col in df.columns):
        return df
    df[flag_col] = df[col].astype(str).str.match(pattern, flags=re.IGNORECASE)
    return df


def _validate_json(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Validate that a column contains valid JSON."""
    col = params.get("column")
    flag_col = params.get("flag_col", f"{col}_is_json")
    if not (col and col in df.columns):
        return df

    def _is_valid_json(x):
        try:
            import json

            json.loads(str(x))
            return True
        except Exception:
            return False

    df[flag_col] = df[col].astype(str).apply(_is_valid_json)
    return df


# ══════════════════════════════════════════════════════════════════════════════
# ── ADVANCED: Statistical ───────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════


def _winsorize(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Winsorize outliers (cap at percentiles)."""
    col = params.get("column")
    lower = params.get("lower", 0.05)
    upper = params.get("upper", 0.95)
    if not (col and col in df.columns and pd.api.types.is_numeric_dtype(df[col])):
        return df
    lower_val = df[col].quantile(lower)
    upper_val = df[col].quantile(upper)
    df[col] = df[col].clip(lower=lower_val, upper=upper_val)
    return df


def _zscore_normalize(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Z-score normalize a column."""
    col = params.get("column")
    new_col = params.get("new_col", f"{col}_zscore")
    if not (col and col in df.columns and pd.api.types.is_numeric_dtype(df[col])):
        return df
    mean, std = df[col].mean(), df[col].std()
    df[new_col] = (df[col] - mean) / std if std > 0 else 0
    return df


def _box_cox_transform(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Apply Box-Cox power transformation."""
    col = params.get("column")
    new_col = params.get("new_col", f"{col}_boxcox")
    if not (col and col in df.columns and pd.api.types.is_numeric_dtype(df[col])):
        return df
    from scipy import stats

    positive_data = df[col] - df[col].min() + 1
    transformed, _ = stats.boxcox(positive_data)
    df[new_col] = transformed
    return df


# ══════════════════════════════════════════════════════════════════════════════
# ── ADVANCED: String Distance ───────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════


def _calculate_similarity(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Calculate string similarity between two columns."""
    col1 = params.get("column1")
    col2 = params.get("column2")
    new_col = params.get("new_col", "similarity_score")
    method = params.get("method", "ratio")
    if not (col1 and col2 and col1 in df.columns and col2 in df.columns):
        return df
    try:
        from rapidfuzz import fuzz

        def _similarity(r1, r2):
            if method == "ratio":
                return fuzz.ratio(str(r1), str(r2)) / 100
            elif method == "partial":
                return fuzz.partial_ratio(str(r1), str(r2)) / 100
            elif method == "token_sort":
                return fuzz.token_sort_ratio(str(r1), str(r2)) / 100
            else:
                return fuzz.token_set_ratio(str(r1), str(r2)) / 100

        df[new_col] = df.apply(lambda r: _similarity(r[col1], r[col2]), axis=1)
    except ImportError:
        df[new_col] = (df[col1] == df[col2]).astype(float)
    return df


def _fuzzy_find_replace(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """Find and replace text using fuzzy matching."""
    col = params.get("column")
    mapping = params.get("mapping", {})
    threshold = params.get("threshold", 90)
    if not (col and col in df.columns and mapping):
        return df
    try:
        from rapidfuzz import fuzz

        def _fuzzy_replace(val):
            best_match, best_score = None, 0
            for k, v in mapping.items():
                score = fuzz.ratio(str(val).lower(), str(k).lower())
                if score > best_score and score >= threshold:
                    best_match, best_score = v, score
            return best_match if best_match else val

        df[col] = df[col].apply(_fuzzy_replace)
    except ImportError:
        pass
    return df

_ACTIONS: Dict[str, Any] = {
    # ── Existing ──────────────────────────────────────────────────────────────
    "remove_duplicates": _remove_duplicates,
    "convert_dirty_nulls": _convert_dirty_nulls,
    "trim_whitespace": _trim_whitespace,
    "standardise_capitalisation": _standardise_capitalisation,
    "normalise_categories": _normalise_categories,
    "fill_missing": _fill_missing,
    "coerce_numeric": _coerce_numeric,
    "standardise_dates": _standardise_dates,
    "flag_invalid_emails": _flag_invalid_emails,
    "rename_column": _rename_column,
    "drop_column": _drop_column,
    "drop_rows_where": _drop_rows_where,
    "fuzzy_remove_duplicates": _fuzzy_remove_duplicates,
    "sql_apply": _sql_apply,
    # ── New: String ───────────────────────────────────────────────────────────
    "find_replace": _find_replace,
    "strip_characters": _strip_characters,
    "normalize_unicode": _normalize_unicode,
    "normalize_phone": _normalize_phone,
    "map_values": _map_values,
    "split_column": _split_column,
    "merge_columns": _merge_columns,
    # ── New: Numeric ──────────────────────────────────────────────────────────
    "extract_numeric": _extract_numeric,
    "clip_outliers": _clip_outliers,
    "replace_outliers": _replace_outliers,
    "round_numeric": _round_numeric,
    "scale_numeric": _scale_numeric,
    "bin_numeric": _bin_numeric,
    # ── New: Missing ──────────────────────────────────────────────────────────
    "fill_missing_ffill": _fill_missing_ffill,
    "fill_missing_bfill": _fill_missing_bfill,
    "fill_missing_interpolate": _fill_missing_interpolate,
    "drop_rows_missing_threshold": _drop_rows_missing_threshold,
    # ── New: Date ─────────────────────────────────────────────────────────────
    "standardise_mixed_dates": _standardise_mixed_dates,
    "extract_date_parts": _extract_date_parts,
    "calculate_date_diff": _calculate_date_diff,
    "flag_future_dates": _flag_future_dates,
    "flag_weekend_dates": _flag_weekend_dates,
    "age_from_date": _age_from_date,
    # ── New: Structure ────────────────────────────────────────────────────────
    "cast_type": _cast_type,
    "conditional_column": _conditional_column,
    "drop_constant_columns": _drop_constant_columns,
    "drop_high_missing_columns": _drop_high_missing_columns,
    # ── New: Validation (STEP 6) ──────────────────────────────────────────────
    "validate_regex": _validate_regex,
    "validate_range": _validate_range,
    "validate_format": _validate_format,
    # ── New: Power features ───────────────────────────────────────────────────
    "drop_rows_matching": _drop_rows_matching,
    "reorder_columns": _reorder_columns,
    "rename_columns_bulk": _rename_columns_bulk,
    "apply_schema_suggestions": _apply_schema_suggestions,
    "normalize_column_names": _normalize_column_names,
    "map_to_standard": _map_to_standard,
    # ── NEW: Advanced Text & NLP ───────────────────────────────────────────────
    "extract_email_domain": _extract_email_domain,
    "extract_url_parts": _extract_url_parts,
    "parse_currency": _parse_currency,
    "parse_number_formatted": _parse_number_formatted,
    "extract_regex_groups": _extract_regex_groups,
    "tokenize_text": _tokenize_text,
    "remove_stopwords": _remove_stopwords,
    "stem_text": _stem_text,
    "lemmatize_text": _lemmatize_text,
    "detect_encoding": _detect_encoding,
    "convert_encoding": _convert_encoding,
    # ── NEW: Advanced Data Transforms ──────────────────────────────────────────
    "pivot_table": _pivot_table,
    "unpivot": _unpivot,
    "cross_column_ratio": _cross_column_ratio,
    "cross_column_diff": _cross_column_diff,
    "percentage_change": _percentage_change,
    "add_rank": _add_rank,
    "add_percentile": _add_percentile,
    "rolling_stats": _rolling_stats,
    "cumulative_sum": _cumulative_sum,
    "cumulative_stats": _cumulative_stats,
    "lag_column": _lag_column,
    "lead_column": _lead_column,
    # ── NEW: Sampling & Split ────────────────────────────────────────────────
    "sample_random": _sample_random,
    "sample_stratified": _sample_stratified,
    "train_test_split": _train_test_split,
    # ── NEW: Advanced Deduplication ─────────────────────────────────────────
    "fuzzy_match_merge": _fuzzy_match_merge,
    "remove_exact_duplicates": _remove_exact_duplicates,
    "dedupe_by_key": _dedupe_by_key,
    # ── NEW: Data Shaping ────────────────────────────────────────────────────
    "transpose_data": _transpose_data,
    "stack_columns": _stack_columns,
    "one_hot_encode": _one_hot_encode,
    "label_encode": _label_encode,
    # ── NEW: Advanced Validation ──────────────────────────────────────────────
    "validate_email_advanced": _validate_email_advanced,
    "validate_phone": _validate_phone,
    "validate_postal_code": _validate_postal_code,
    "validate_json": _validate_json,
    # ── NEW: Statistical ────────────────────────────────────────────────────
    "winsorize": _winsorize,
    "zscore_normalize": _zscore_normalize,
    "box_cox_transform": _box_cox_transform,
    # ── NEW: String Distance ────────────────────────────────────────────────
    "calculate_similarity": _calculate_similarity,
    "fuzzy_find_replace": _fuzzy_find_replace,
}
