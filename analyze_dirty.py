"""
Deep analysis of dirty vs clean datasets across all domains.
Finds EXACTLY what issues exist per column, per domain.
"""
import pandas as pd
import glob, os, re
from collections import defaultdict

BASE = r"D:\datacove_out\Datasets"
DOMAINS = ["crm","ecommerce","finance","healthcare","hr","logistics",
           "inventory","realestate","iot","student","survey"]

DIRTY_TOKENS = {
    "n/a","na","none","null","nil","unknown","-","--","---","?","??",
    "tbd","tba","not available","not applicable","missing","undefined",
    "nan","#n/a","n.a.","n.a","na.","", "0", "00","000","N/A","NULL","None"
}

def pct(x): return round(x*100, 1)

def col_issues(s, col_name):
    issues = {}
    vals = s.fillna("").astype(str).str.strip()

    # --- True NaN / empty ---
    null_rate = s.isnull().mean()
    if null_rate > 0:
        issues["true_nulls"] = pct(null_rate)

    # --- Dirty null tokens ---
    dirty_mask = vals.str.lower().isin({v.lower() for v in DIRTY_TOKENS})
    if null_rate < 1:  # avoid double-counting fully null columns
        dirty_rate = dirty_mask[~s.isnull()].mean()
        if dirty_rate > 0.01:
            sample = vals[dirty_mask].value_counts().head(4).to_dict()
            issues["dirty_nulls"] = {"rate": pct(dirty_rate), "values": sample}

    # --- Whitespace ---
    non_null = s.dropna().astype(str)
    if len(non_null):
        ws = (non_null != non_null.str.strip()).mean()
        if ws > 0.01:
            issues["extra_whitespace"] = pct(ws)

    # --- Currency symbols ---
    has_curr = non_null.str.contains(r"[$€£₹¥]", regex=True, na=False).mean()
    if has_curr > 0.05:
        issues["currency_symbols"] = pct(has_curr)

    # --- Numbers with commas (e.g. "1,200") ---
    has_comma_num = non_null.str.match(r"^[$€£₹¥]?[\d,]+\.?\d*$").mean()
    if has_comma_num > 0.05:
        issues["number_with_commas"] = pct(has_comma_num)

    # --- Phone formatting noise ---
    if any(k in col_name.lower() for k in ["phone","mobile","tel","contact"]):
        # Non-digit chars other than + at start
        noisy = non_null.str.contains(r"[\(\)\-\s\.]", regex=True, na=False).mean()
        if noisy > 0.1:
            issues["phone_noise"] = pct(noisy)

    # --- Date format inconsistency ---
    if any(k in col_name.lower() for k in ["date","dob","dt","_at","time"]):
        date_patterns = [
            r"\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}",
            r"\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2}",
            r"[A-Za-z]{3,9}[\s\-]\d{1,2},?\s*\d{4}",
            r"\d{1,2}\s[A-Za-z]{3,9},?\s*\d{4}",
        ]
        seen = set()
        for p in date_patterns:
            matches = non_null.str.contains(p, regex=True, na=False)
            if matches.any():
                seen.add(p)
        if len(seen) >= 2:
            issues["mixed_date_formats"] = True

    # --- Capitalisation inconsistency (text columns) ---
    if s.dtype == object and len(non_null) > 10:
        low_p  = (non_null == non_null.str.lower()).mean()
        up_p   = (non_null == non_null.str.upper()).mean()
        tit_p  = (non_null == non_null.str.title()).mean()
        mixed  = 1 - low_p - up_p - tit_p
        if mixed > 0.15:
            issues["case_inconsistency"] = pct(mixed)

    # --- Numeric stored as object ---
    if s.dtype == object:
        # Strip currency/commas and try to coerce
        cleaned = non_null.str.replace(r"[$€£₹¥,]", "", regex=True)
        numeric_mask = pd.to_numeric(cleaned, errors="coerce").notna()
        numeric_rate = numeric_mask.mean()
        if numeric_rate > 0.6 and s.dtype == object:
            issues["numeric_as_text"] = pct(numeric_rate)

    # --- Outliers / negative values in numeric ---
    if pd.api.types.is_numeric_dtype(s):
        if (s < 0).any():
            neg_rate = (s < 0).mean()
            if neg_rate > 0:
                issues["negative_values"] = pct(neg_rate)

    # --- Duplicates in ID-like columns ---
    if any(k in col_name.lower() for k in ["_id","_no","id","order","txn","shipment","emp","patient"]):
        non_empty = non_null[non_null != ""]
        if len(non_empty):
            dup_rate = non_empty.duplicated().mean()
            if dup_rate > 0.01:
                issues["duplicate_ids"] = pct(dup_rate)

    return issues


all_findings = {}

for domain in DOMAINS:
    folder = os.path.join(BASE, domain)
    if not os.path.isdir(folder):
        continue

    # pick heavy + extreme seeds for richest dirty signal
    dirty_files = sorted(glob.glob(os.path.join(folder, f"{domain}_heavy_seed42.csv")))
    clean_files = sorted(glob.glob(os.path.join(folder, f"{domain}_clean_seed42.csv")))
    extra_dirty = sorted(glob.glob(os.path.join(folder, f"{domain}_extreme_seed42.csv")))
    if extra_dirty:
        dirty_files += extra_dirty

    if not dirty_files:
        continue

    domain_findings = defaultdict(list)
    print(f"\n{'='*55}")
    print(f"  {domain.upper()}")
    print(f"{'='*55}")

    for df_path in dirty_files:
        df = pd.read_csv(df_path, dtype=str)
        print(f"  [{os.path.basename(df_path)}]  {df.shape}")
        for col in df.columns:
            issues = col_issues(df[col], col)
            if issues:
                for k, v in issues.items():
                    entry = f"{col}: {k}={v}"
                    domain_findings[k].append(col)
                print(f"    {col:30s} -> {list(issues.keys())}")

    all_findings[domain] = dict(domain_findings)
    print(f"\n  Total null%: {round(pd.read_csv(dirty_files[0], dtype=str).isnull().mean().mean()*100,1)}%")

print(f"\n\n{'='*55}")
print("CROSS-DOMAIN ISSUE TYPE FREQUENCY")
print(f"{'='*55}")
global_issues = defaultdict(int)
for d, issues in all_findings.items():
    for itype in issues:
        global_issues[itype] += len(issues[itype])

for itype, count in sorted(global_issues.items(), key=lambda x: -x[1]):
    print(f"  {itype:<30s} : {count} columns affected")

print("\n\nBY DOMAIN — WHAT RULES ARE NEEDED:")
domain_rules = {
    "crm":        ["dirty_nulls","extra_whitespace","phone_noise","mixed_date_formats","duplicate_ids","case_inconsistency"],
    "ecommerce":  ["dirty_nulls","currency_symbols","number_with_commas","numeric_as_text","mixed_date_formats","extra_whitespace"],
    "finance":    ["dirty_nulls","currency_symbols","number_with_commas","numeric_as_text","mixed_date_formats","case_inconsistency"],
    "healthcare": ["dirty_nulls","mixed_date_formats","numeric_as_text","case_inconsistency","extra_whitespace"],
    "hr":         ["dirty_nulls","numeric_as_text","mixed_date_formats","case_inconsistency","extra_whitespace","phone_noise"],
    "logistics":  ["dirty_nulls","numeric_as_text","mixed_date_formats","extra_whitespace","case_inconsistency"],
    "inventory":  ["dirty_nulls","numeric_as_text","currency_symbols","extra_whitespace"],
    "realestate": ["dirty_nulls","currency_symbols","numeric_as_text","mixed_date_formats"],
    "iot":        ["dirty_nulls","numeric_as_text","extra_whitespace"],
    "student":    ["dirty_nulls","case_inconsistency","numeric_as_text","mixed_date_formats"],
    "survey":     ["dirty_nulls","case_inconsistency","extra_whitespace"],
}
for d, rules in domain_rules.items():
    found = all_findings.get(d, {})
    detected = [r for r in rules if r in found]
    print(f"  {d}: {detected}")
