"""
streaming_engine.py - chunk-based transform engine for large datasets.

How it works:
  - Reads the on-disk CSV in STREAM_CHUNK_SIZE row chunks via pandas
  - Applies the transformation independently to each chunk
  - Writes completed chunks to a temp output CSV
  - Yields SSE-compatible progress dicts after each chunk

Memory stays at roughly O(chunk_size × columns) regardless of total file size.

Global actions (need to see all rows to work correctly):
  remove_duplicates, normalise_categories
These fall back to a full-load pass automatically but still emit progress events.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Generator

import pandas as pd

from config import settings
from services.cleaning_engine import apply_transformation
from utils.logger import logger

_GLOBAL_ACTIONS = {"remove_duplicates", "normalise_categories"}

DEFAULT_CHUNK_SIZE = settings.STREAM_CHUNK_SIZE


def is_streamable(action: str) -> bool:
    return action not in _GLOBAL_ACTIONS


def _count_rows(path: Path) -> int:
    """Fast line count - O(file_size / buffer) without loading data."""
    with open(path, "rb") as f:
        return sum(1 for _ in f) - 1   # subtract header


def stream_transform(
    session_id: str,
    source_path: Path,
    action: str,
    params: Dict[str, Any],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Generator[Dict[str, Any], None, None]:
    """
    Apply a single transformation in chunks. Yields progress + done/error dicts.
    The caller reloads session.df_current from the output_path on 'done'.
    """
    if not source_path.exists():
        yield {"type": "error", "detail": f"Source file not found: {source_path}"}
        return

    try:
        total_rows = _count_rows(source_path)
    except Exception as exc:
        yield {"type": "error", "detail": f"Could not count rows: {exc}"}
        return

    if total_rows == 0:
        yield {"type": "error", "detail": "Source file is empty."}
        return

    out_path = Path(tempfile.mktemp(
        suffix=".csv",
        prefix=f"dc_stream_{session_id}_",
        dir=str(settings.DATASET_DIR),
    ))

    rows_done = 0
    header_written = False
    columns: list[str] = []

    try:
        for chunk_df in pd.read_csv(source_path, chunksize=chunk_size, low_memory=False):
            chunk_df = apply_transformation(chunk_df, action, params)
            chunk_df.to_csv(out_path, mode="a", header=not header_written, index=False)
            header_written = True
            columns = list(chunk_df.columns)
            rows_done += len(chunk_df)
            pct = min(int(rows_done / total_rows * 100), 99)
            yield {"type": "progress", "pct": pct, "rows_done": rows_done, "total_rows": total_rows}

        yield {"type": "done", "output_path": str(out_path), "rows": rows_done, "columns": columns}
        logger.info(f"stream_transform: done - {rows_done} rows, action={action}")

    except Exception as exc:
        logger.error(f"stream_transform failed: {exc}")
        out_path.unlink(missing_ok=True)
        yield {"type": "error", "detail": str(exc)}


def stream_auto_clean(
    session_id: str,
    source_path: Path,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Generator[Dict[str, Any], None, None]:
    """
    Two-pass auto-clean:
      Pass 1 (chunked): trim_whitespace → standardise_capitalisation → fill_missing
      Pass 2 (global):  remove_duplicates on the assembled result
    """
    try:
        total_rows = _count_rows(source_path)
    except Exception as exc:
        yield {"type": "error", "detail": str(exc)}
        return

    out_path = Path(tempfile.mktemp(
        suffix=".csv", prefix=f"dc_autoclean_{session_id}_", dir=str(settings.DATASET_DIR)
    ))

    rows_done = 0
    header_written = False
    columns: list[str] = []

    try:
        for chunk_df in pd.read_csv(source_path, chunksize=chunk_size, low_memory=False):
            chunk_df = apply_transformation(chunk_df, "trim_whitespace", {})
            chunk_df = apply_transformation(chunk_df, "standardise_capitalisation", {})
            chunk_df = apply_transformation(chunk_df, "fill_missing", {"strategy": "mode"})
            chunk_df.to_csv(out_path, mode="a", header=not header_written, index=False)
            header_written = True
            columns = list(chunk_df.columns)
            rows_done += len(chunk_df)
            pct = min(int(rows_done / total_rows * 70), 69)
            yield {"type": "progress", "pct": pct, "rows_done": rows_done,
                   "total_rows": total_rows, "message": "Cleaning chunks…"}

        yield {"type": "progress", "pct": 75, "rows_done": rows_done,
               "total_rows": total_rows, "message": "Removing duplicates…"}

        df_full = pd.read_csv(out_path)
        df_full = df_full.drop_duplicates(keep="first").reset_index(drop=True)
        final_path = Path(tempfile.mktemp(
            suffix=".csv", prefix=f"dc_autoclean_final_{session_id}_",
            dir=str(settings.DATASET_DIR)
        ))
        df_full.to_csv(final_path, index=False)
        out_path.unlink(missing_ok=True)

        yield {"type": "done", "output_path": str(final_path),
               "rows": len(df_full), "columns": list(df_full.columns)}

    except Exception as exc:
        logger.error(f"stream_auto_clean failed: {exc}")
        out_path.unlink(missing_ok=True)
        yield {"type": "error", "detail": str(exc)}
