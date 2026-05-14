"""
fuzzy_dedup.py - fuzzy duplicate detection using RapidFuzz.

Exact deduplication misses near-duplicates like:
  "John Smith" vs "john smith" vs "Jon Smith" vs "John  Smith"

This engine:
  1. Selects string columns to compare (configurable)
  2. Builds a composite key per row (concatenated string columns)
  3. Uses RapidFuzz's process.cdist to compute pairwise similarity
  4. Groups rows whose similarity exceeds the threshold
  5. Returns duplicate groups for inspection + an action to remove them

Threshold: 0-100 (default 85). Higher = stricter matching.

Falls back gracefully if rapidfuzz is not installed - returns an
informative error rather than crashing.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import pandas as pd

DEFAULT_THRESHOLD = 85   # similarity score 0-100


def find_fuzzy_duplicates(
    df: pd.DataFrame,
    columns: Optional[List[str]] = None,
    threshold: int = DEFAULT_THRESHOLD,
    max_comparisons: int = 50_000,
) -> Dict[str, Any]:
    """
    Find near-duplicate rows in df.

    Returns:
        {
          "groups": [
            {
              "canonical_idx": int,       # row to keep
              "duplicate_idxs": [int],    # rows to remove
              "score": float,             # similarity score
              "canonical_row": {col: val},
              "sample_duplicate": {col: val},
            },
            ...
          ],
          "total_duplicates": int,        # rows that would be removed
          "method": "rapidfuzz",
          "threshold": int,
          "columns_used": [str],
        }
    """
    try:
        from rapidfuzz import process, fuzz
    except ImportError:
        raise ValueError(
            "RapidFuzz is not installed. Run: pip install rapidfuzz"
        )

    # Pick string columns to use for comparison
    if columns:
        str_cols = [c for c in columns if c in df.columns]
    else:
        str_cols = df.select_dtypes(include="object").columns.tolist()[:5]  # cap at 5

    if not str_cols:
        return {"groups": [], "total_duplicates": 0,
                "method": "rapidfuzz", "threshold": threshold, "columns_used": []}

    # Build composite key - only uses object/string columns so safe to fillna("")
    keys = df[str_cols].fillna("").astype(str).apply(
        lambda row: " | ".join(row.values), axis=1
    ).tolist()

    n = len(keys)
    if n * (n - 1) / 2 > max_comparisons:
        # Sample down to avoid O(n²) explosion on large datasets
        sample_size = int((2 * max_comparisons) ** 0.5) + 1
        keys = keys[:sample_size]
        n = sample_size

    # Compute pairwise similarity (vectorised)
    from rapidfuzz.distance import DamerauLevenshtein
    import numpy as np

    groups: List[Dict[str, Any]] = []
    visited: set = set()

    for i in range(n):
        if i in visited:
            continue
        dupes = []
        for j in range(i + 1, n):
            if j in visited:
                continue
            score = fuzz.token_sort_ratio(keys[i], keys[j])
            if score >= threshold:
                dupes.append((j, score))
                visited.add(j)

        if dupes:
            visited.add(i)

            def _row_to_dict(row):
                """Safely convert a Series row (may have Int64/ext types) to str dict."""
                s = row.astype(object)   # converts Int64→object (NaN→None) in one step
                return s.fillna("").astype(str).to_dict()

            groups.append({
                "canonical_idx":    i,
                "duplicate_idxs":   [d[0] for d in dupes],
                "score":            round(sum(d[1] for d in dupes) / len(dupes), 1),
                "canonical_row":    _row_to_dict(df.iloc[i]),
                "sample_duplicate": _row_to_dict(df.iloc[dupes[0][0]]),
            })

    total_dupes = sum(len(g["duplicate_idxs"]) for g in groups)

    return {
        "groups":           groups[:200],   # cap returned groups
        "total_duplicates": total_dupes,
        "method":           "rapidfuzz",
        "threshold":        threshold,
        "columns_used":     str_cols,
    }


def remove_fuzzy_duplicates(
    df: pd.DataFrame,
    columns: Optional[List[str]] = None,
    threshold: int = DEFAULT_THRESHOLD,
) -> pd.DataFrame:
    """
    Remove near-duplicate rows, keeping the first occurrence in each group.
    Returns a new DataFrame.
    """
    result = find_fuzzy_duplicates(df, columns=columns, threshold=threshold)
    drop_idxs: set = set()
    for group in result["groups"]:
        drop_idxs.update(group["duplicate_idxs"])

    return df.drop(index=list(drop_idxs)).reset_index(drop=True)
