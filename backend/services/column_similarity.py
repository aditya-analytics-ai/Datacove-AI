"""
column_similarity.py - detect semantically similar columns and suggest merges.
Uses name similarity (RapidFuzz or fallback) + Jaccard value overlap.
"""
from __future__ import annotations
import re, unicodedata
from itertools import combinations
from collections import defaultdict
from typing import Any, Dict, List, Set
import pandas as pd

try:
    from rapidfuzz import fuzz as _fuzz
    _HAS_RF = True
except ImportError:
    _HAS_RF = False

_NAME_THRESHOLD  = 75
_FINAL_THRESHOLD = 78
_VALUE_BONUS     = 15


def find_similar_columns(df: pd.DataFrame, max_groups: int = 20, sample_rows: int = 500) -> Dict[str, Any]:
    cols  = list(df.columns)
    if len(cols) < 2:
        return {"groups": [], "total_pairs_checked": 0, "similar_pairs_found": 0}

    norms  = {c: _norm(c) for c in cols}
    sample = df.sample(min(sample_rows, len(df)), random_state=42) if len(df) > sample_rows else df
    val_sets = {c: set(sample[c].dropna().astype(str).str.strip().str.lower().unique()) for c in cols}

    checked, pairs = 0, []
    for a, b in combinations(cols, 2):
        checked += 1
        ns  = _name_sim(norms[a], norms[b])
        ov  = _jaccard(val_sets[a], val_sets[b])
        cs  = min(ns + (_VALUE_BONUS if ov > 0.30 else 0), 100)
        if cs < _FINAL_THRESHOLD: continue

        if ov > 0.70:   sug, reason = "drop_duplicate", f"Name sim {ns:.0f}/100 + {ov*100:.0f}% value overlap - likely same data."
        elif cs >= 85:  sug, reason = "merge",          f"Name sim {ns:.0f}/100 - same field, different naming convention."
        else:           sug, reason = "review",          f"Name sim {ns:.0f}/100 - worth reviewing before cleaning."

        sample_disp = {c: [str(v) for v in df[c].dropna().value_counts().head(4).index.tolist()] for c in (a, b)}
        pairs.append({"columns": [a, b], "name_score": round(ns, 1), "value_overlap": round(ov, 3),
                      "combined_score": round(cs, 1), "suggestion": sug, "reason": reason, "sample": sample_disp})

    groups = _to_groups(pairs)[:max_groups]
    return {"groups": groups, "total_pairs_checked": checked, "similar_pairs_found": len(groups)}


def _norm(col):
    col = unicodedata.normalize("NFKD", col).encode("ascii", "ignore").decode()
    col = re.sub(r"([a-z])([A-Z])", r"\1 \2", col)
    col = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", col)
    return re.sub(r"[^a-z0-9]+", " ", col.lower()).strip()


def _name_sim(a, b):
    if a == b: return 100.0
    if _HAS_RF: return float(_fuzz.token_sort_ratio(a, b))
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb: return 0.0
    return round(len(ta & tb) / len(ta | tb) * 100, 1)


def _jaccard(a: Set, b: Set):
    if not a or not b: return 0.0
    return len(a & b) / len(a | b)


def _to_groups(pairs):
    parent: Dict[str, str] = {}
    def find(x):
        while parent.get(x, x) != x: parent[x] = parent.get(parent[x], parent[x]); x = parent[x]
        return x
    def union(x, y): parent[find(x)] = find(y)
    for p in pairs:
        a, b = p["columns"]
        for c in (a, b):
            if c not in parent: parent[c] = c
        union(a, b)
    comps: Dict[str, List[str]] = defaultdict(list)
    for c in parent: comps[find(c)].append(c)
    groups = []
    for members in comps.values():
        if len(members) < 2: continue
        best = max((p for p in pairs if set(p["columns"]).issubset(set(members))),
                   key=lambda p: p["combined_score"], default=None)
        if not best: continue
        merged_sample: Dict = {}
        for p in pairs:
            if set(p["columns"]).issubset(set(members)): merged_sample.update(p["sample"])
        groups.append({**best, "columns": sorted(members), "sample": merged_sample})
    return sorted(groups, key=lambda g: -g["combined_score"])
