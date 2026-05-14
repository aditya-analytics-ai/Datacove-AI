"""
referential_integrity.py - auto-detect PK/FK columns and flag violations.
Detects: duplicate PKs, null FKs, orphaned FK values.
"""
from __future__ import annotations
import re
from typing import Any, Dict, List, Set
import pandas as pd

_ID_SUFFIXES = re.compile(r"(_id|_key|_code|_no|_num|_ref|_uuid|_pk|_fk)$", re.I)
_ID_PREFIXES = re.compile(r"^(id_|pk_|fk_)", re.I)
_PK_UNIQUENESS = 0.95
_FK_MAX_UNIQUE  = 0.50


def check_referential_integrity(df: pd.DataFrame, max_violations: int = 500) -> Dict[str, Any]:
    rows    = max(len(df), 1)
    pk_cols = _find_pk(df, rows)
    fk_cols = _find_fk(df, pk_cols, rows)
    violations: List[Dict[str, Any]] = []
    orphaned = dup_pk = null_fk = 0

    for col in pk_cols:
        dc = int(df[col].dropna().duplicated().sum())
        if dc:
            samples = df[col][df[col].duplicated(keep=False)].dropna().unique()[:5].tolist()
            violations.append({"type": "duplicate_pk", "column": col, "ref_column": None,
                "count": dc, "severity": "high",
                "description": f"'{col}' has {dc:,} duplicate value(s) - primary keys must be unique.",
                "sample_values": [str(s) for s in samples]})
            dup_pk += dc

    pk_sets = {c: set(df[c].dropna().astype(str).unique()) for c in pk_cols}

    for fk in fk_cols:
        nf = int(df[fk].isnull().sum())
        if nf:
            violations.append({"type": "null_fk", "column": fk, "ref_column": None,
                "count": nf, "severity": "medium",
                "description": f"'{fk}' has {nf:,} null value(s) - these rows have no parent reference.",
                "sample_values": []})
            null_fk += nf

        fk_str = df[fk].dropna().astype(str)
        if fk_str.empty or not pk_sets: continue
        best_pk, best_ov = None, -1
        for pk, pv in pk_sets.items():
            if pk == fk: continue
            ov = int(fk_str.isin(pv).sum())
            if ov > best_ov: best_ov, best_pk = ov, pk

        if best_pk:
            pv       = pk_sets[best_pk]
            ov_ratio = best_ov / max(len(fk_str), 1)
            orphan_m = ~fk_str.isin(pv)
            oc       = int(orphan_m.sum())
            if oc > 0 and ov_ratio > 0.10:
                samples = fk_str[orphan_m].unique()[:5].tolist()
                violations.append({"type": "orphaned_fk", "column": fk, "ref_column": best_pk,
                    "count": oc,
                    "severity": "high" if oc / rows > 0.05 else "medium",
                    "description": f"'{fk}' has {oc:,} value(s) not in '{best_pk}' - possible orphaned records.",
                    "sample_values": samples})
                orphaned += oc

    return {
        "pk_candidates": pk_cols, "fk_candidates": fk_cols,
        "violations": violations[:max_violations],
        "summary": {"pk_columns_found": len(pk_cols), "fk_columns_found": len(fk_cols),
                    "total_violations": len(violations),
                    "orphaned_fk_values": orphaned, "duplicate_pk_values": dup_pk, "null_fk_values": null_fk},
    }


def _find_pk(df, rows):
    return [c for c in df.columns
            if (_ID_SUFFIXES.search(c.lower()) or _ID_PREFIXES.search(c.lower()) or c.lower() in {"id","key","uuid","pk"})
            and df[c].nunique() / rows >= _PK_UNIQUENESS]


def _find_fk(df, pk_cols, rows):
    pk_set = set(pk_cols)
    return [c for c in df.columns if c not in pk_set
            and (_ID_SUFFIXES.search(c.lower()) or _ID_PREFIXES.search(c.lower()))
            and df[c].nunique() / rows <= _FK_MAX_UNIQUE]
