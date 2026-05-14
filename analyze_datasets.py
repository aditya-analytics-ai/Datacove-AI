import pandas as pd
import glob
import os

base = r"D:\datacove_out\Datasets"
domains = ["crm", "ecommerce", "finance", "healthcare", "hr", "logistics"]

for domain in domains:
    files = glob.glob(os.path.join(base, domain, domain + "_heavy_seed42.csv"))
    if not files:
        continue
    df = pd.read_csv(files[0])
    null_pct = round(df.isnull().mean().mean() * 100, 1)
    dup_pct = round(df.duplicated().mean() * 100, 1)
    mixed_cols = [c for c in df.columns if df[c].dtype == object]
    num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    print("=== " + domain.upper() + " ===")
    print("  Rows:", len(df), " | Cols:", len(df.columns))
    print("  Nulls:", null_pct, "%  | Dupes:", dup_pct, "%")
    print("  Text cols:", mixed_cols)
    print("  Numeric cols:", num_cols)
    print()
