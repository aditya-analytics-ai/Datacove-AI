"""
sql_engine.py - DuckDB SQL execution on session DataFrames.

Key fixes over original:
  1. Auto-quotes column names that contain spaces before execution.
     e.g. "Transaction ID" → "Transaction ID" in the query automatically.
     Users can write natural queries without worrying about quoting.
  2. Uses duckdb.connect() + con.register() which works across all DuckDB versions.
  3. Proper NaN → NULL handling (DuckDB does this natively via Arrow).
  4. Thread-safe: fresh connection per call, closed in finally block.

Safety:
  - Only SELECT / WITH / EXPLAIN statements allowed.
  - Results capped at MAX_RESULT_ROWS.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from duckdb import DuckDBPyConnection
import pandas as pd
from pandas import DataFrame

from utils.preview import safe_preview
from utils.errors import SQLValidationError

MAX_RESULT_ROWS = 100_000
_SELECT_ONLY: re.Pattern[str] = re.compile(
    r"^\s*(SELECT|WITH|EXPLAIN)\b", re.IGNORECASE
)


def _auto_quote_columns(query: str, df: pd.DataFrame) -> str:
    """
    Wrap column names that contain spaces (or special chars) with double quotes,
    but only when they appear unquoted in the query.

    Handles: spaces, hyphens, dots, parentheses in column names.
    Skips columns already surrounded by double quotes.
    """
    # Sort by length descending so "Price Per Unit" is matched before "Price"
    cols_with_spaces: list[str] = sorted(
        [c for c in df.columns if re.search(r"[\s\-\.\(\)]", c)], key=len, reverse=True
    )
    for col in cols_with_spaces:
        escaped: str = re.escape(col)
        # Match the column name NOT already inside double quotes
        pattern: str = r'(?<!")\b' + escaped + r'\b(?!")'
        replacement: str = f'"{col}"'
        query = re.sub(pattern, replacement, query)
    return query


def _sanitise_query(query: str) -> str:
    """Strip semicolons and trailing whitespace."""
    return query.strip().rstrip(";").strip()


def run_sql(df: pd.DataFrame, query: str) -> Dict[str, Any]:
    """
    Execute a read-only SQL query against the DataFrame (table name: df).

    Returns:
        { "rows": int, "columns": [...], "preview": [...], "truncated": bool }
    Raises ValueError with a human-readable message on any failure.
    """
    try:
        import duckdb
    except ImportError:
        raise SQLValidationError("DuckDB is not installed. Run: pip install duckdb")

    query = _sanitise_query(query)

    if not _SELECT_ONLY.match(query):
        raise SQLValidationError(
            "Only SELECT queries are allowed here. "
            "Use the cleaning toolbar or AI Chat to modify data."
        )

    # Auto-quote columns with spaces so users can write natural queries
    query = _auto_quote_columns(query, df)

    con: Optional[DuckDBPyConnection] = None
    try:
        con = duckdb.connect()
        con.register("df", df)
        result_df: DataFrame = con.execute(query).df()
    except Exception as exc:
        msg = str(exc)
        if "Referenced column" in msg and "not found" in msg:
            raise SQLValidationError(
                f"Column not found. Tip: column names with spaces need double quotes, "
                f'e.g. "Transaction ID". Available columns: {list(df.columns)}\n\nDetail: {msg}'
            )
        if "syntax error" in msg.lower():
            raise SQLValidationError(
                f"SQL syntax error. Tip: use single quotes for string values, "
                f"e.g. WHERE Location = 'In-store'\n\nDetail: {msg}"
            )
        raise SQLValidationError(f"SQL error: {msg}")
    finally:
        if con:
            con.close()

    truncated: bool = len(result_df) > MAX_RESULT_ROWS
    result_df: DataFrame = result_df.head(MAX_RESULT_ROWS)
    preview = safe_preview(result_df)

    return {
        "rows": len(result_df),
        "columns": list(result_df.columns),
        "preview": preview,
        "truncated": truncated,
        "query_used": query,  # return the auto-quoted query so frontend can show it
    }


def sql_to_dataframe(df: pd.DataFrame, query: str) -> pd.DataFrame:
    """Run a SELECT query and return the result as a DataFrame (for Apply)."""
    try:
        import duckdb
    except ImportError:
        raise SQLValidationError("DuckDB is not installed. Run: pip install duckdb")

    query = _sanitise_query(query)

    if not _SELECT_ONLY.match(query):
        raise SQLValidationError("Only SELECT queries are allowed.")

    query = _auto_quote_columns(query, df)

    con_exec: Optional[DuckDBPyConnection] = None
    try:
        con_exec = duckdb.connect()
        con_exec.register("df", df)
        result: DataFrame = con_exec.execute(query).df()
        return result
    except Exception as exc:
        msg = str(exc)
        if "Referenced column" in msg and "not found" in msg:
            raise SQLValidationError(
                f"Column not found. Available columns: {list(df.columns)}\nDetail: {msg}"
            )
        raise SQLValidationError(f"SQL error: {msg}")
    finally:
        if con_exec:
            con_exec.close()
