"""
Dataset loader - reads CSV / Excel into a Pandas DataFrame.
"""

from pathlib import Path
import pandas as pd
from config import MAX_ROWS


class DatasetLoaderError(Exception):
    """Base error for dataset loading failures."""


class UnsupportedDatasetFormatError(DatasetLoaderError):
    pass


class DatasetDecodeError(DatasetLoaderError):
    pass


class DatasetParseError(DatasetLoaderError):
    pass


class DatasetTooLargeError(DatasetLoaderError):
    pass


class DatasetNotFoundError(DatasetLoaderError):
    pass


def load_dataset(path: Path) -> pd.DataFrame:
    """
    Load file into DataFrame.  Enforces MAX_ROWS limit.
    """
    suffix = path.suffix.lower()

    try:
        if suffix == ".csv":
            # Try common encodings gracefully
            for enc in ("utf-8", "latin-1", "cp1252"):
                try:
                    df = pd.read_csv(path, encoding=enc, low_memory=False)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise DatasetDecodeError("Cannot decode CSV file.")
        elif suffix in (".xlsx", ".xls"):
            df = pd.read_excel(path)
        else:
            raise UnsupportedDatasetFormatError(f"Unsupported format: {suffix}")
    except Exception as exc:
        if isinstance(exc, DatasetLoaderError):
            raise
        raise DatasetParseError(f"Failed to parse file: {exc}")

    if len(df) > MAX_ROWS:
        raise DatasetTooLargeError(
            f"Dataset has {len(df):,} rows; maximum is {MAX_ROWS:,}."
        )

    # Strip leading/trailing spaces from column names
    df.columns = [str(c).strip() for c in df.columns]
    return df


def infer_schema_suggestions(df: pd.DataFrame) -> list:
    """
    Run a quick heuristic pass on upload and return suggested type casts.
    Returns list of {column, suggested_dtype, confidence, reason, sample_values}
    """
    from utils.validation_utils import looks_like_date

    suggestions = []

    for col in df.columns:
        series = df[col].dropna()
        if len(series) == 0:
            continue

        total = len(series)
        sample = series.head(5).astype(str).tolist()

        # Already numeric - skip
        if pd.api.types.is_numeric_dtype(df[col]):
            continue

        str_series = series.astype(str).str.strip()

        # ── Boolean check (yes/no, true/false, 0/1, on/off)
        BOOL_MAP = {
            "yes",
            "no",
            "true",
            "false",
            "1",
            "0",
            "on",
            "off",
            "y",
            "n",
            "t",
            "f",
        }
        unique_lower = set(str_series.str.lower().unique())
        if len(unique_lower) <= 2 and unique_lower.issubset(BOOL_MAP):
            suggestions.append(
                {
                    "column": col,
                    "suggested_dtype": "bool",
                    "confidence": 0.97,
                    "reason": f"Only {len(unique_lower)} unique value(s): {sorted(unique_lower)}",
                    "sample_values": sample,
                }
            )
            continue

        # ── Numeric check (>90% parseable as float)
        numeric_ok = pd.to_numeric(str_series, errors="coerce").notna().mean()
        if numeric_ok >= 0.90:
            suggestions.append(
                {
                    "column": col,
                    "suggested_dtype": "float",
                    "confidence": round(numeric_ok, 3),
                    "reason": f"{numeric_ok * 100:.0f}% of values parse as numeric",
                    "sample_values": sample,
                }
            )
            continue

        # ── Integer check (>90% parseable as int, no decimals)
        int_ok = str_series.str.match(r"^-?\d+$").mean()
        if int_ok >= 0.90:
            suggestions.append(
                {
                    "column": col,
                    "suggested_dtype": "int",
                    "confidence": round(int_ok, 3),
                    "reason": f"{int_ok * 100:.0f}% of values are integers",
                    "sample_values": sample,
                }
            )
            continue

        # ── Date check (>80% parseable as date)
        date_ok = series.apply(lambda x: looks_like_date([str(x)])).mean()
        if date_ok >= 0.80:
            suggestions.append(
                {
                    "column": col,
                    "suggested_dtype": "date",
                    "confidence": round(date_ok, 3),
                    "reason": f"{date_ok * 100:.0f}% of values look like dates",
                    "sample_values": sample,
                }
            )
            continue

        # ── Category check (low-cardinality string)
        unique_ratio = series.nunique() / max(total, 1)
        if unique_ratio <= 0.05 and series.nunique() <= 50:
            suggestions.append(
                {
                    "column": col,
                    "suggested_dtype": "category",
                    "confidence": round(1 - unique_ratio, 3),
                    "reason": f"{series.nunique()} unique values ({unique_ratio * 100:.1f}% cardinality)",
                    "sample_values": sample,
                }
            )

    return suggestions


def load_dataset_by_id(dataset_id: str, session_id: str, owner_id: str) -> pd.DataFrame:
    """
    Load a dataset by ID from the database.

    Args:
        dataset_id: The dataset ID
        session_id: Session ID (unused, for API compatibility)
        owner_id: Owner user ID

    Returns:
        DataFrame with the dataset data
    """
    from utils.db import db
    import uuid

    row = db.fetchone(
        "SELECT data FROM datasets WHERE id = %s AND owner_id = %s",
        (dataset_id, owner_id),
    )

    if not row:
        raise DatasetNotFoundError("Dataset not found")

    data = row[0]
    if isinstance(data, str):
        import io

        return pd.read_csv(io.StringIO(data))
    elif isinstance(data, bytes):
        import io

        return pd.read_csv(io.BytesIO(data))
    else:
        return pd.DataFrame(data)


def save_dataset(df: pd.DataFrame, name: str, owner_id: str) -> str:
    """
    Save a DataFrame as a dataset.

    Args:
        df: DataFrame to save
        name: Dataset name
        owner_id: Owner user ID

    Returns:
        Dataset ID
    """
    from utils.db import db
    import uuid

    dataset_id = str(uuid.uuid4())
    import io

    csv_data = df.to_csv(index=False)

    db.execute(
        "INSERT INTO datasets (id, name, owner_id, data, created_at) VALUES (%s, %s, %s, %s, NOW())",
        (dataset_id, name, owner_id, csv_data),
    )

    return dataset_id


def list_datasets(owner_id: str, limit: int = 100, offset: int = 0) -> list:
    """
    List datasets for an owner.

    Args:
        owner_id: Owner user ID
        limit: Max results
        offset: Offset for pagination

    Returns:
        List of dataset metadata dicts
    """
    from utils.db import db

    rows = db.fetchall(
        "SELECT id, name, created_at FROM datasets WHERE owner_id = %s ORDER BY created_at DESC LIMIT %s OFFSET %s",
        (owner_id, limit, offset),
    )

    return [
        {
            "id": row[0],
            "name": row[1],
            "created_at": row[2].isoformat() if row[2] else None,
        }
        for row in rows
    ]
