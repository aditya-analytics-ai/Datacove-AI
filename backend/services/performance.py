"""
Performance Layer - makes Datacove scale beyond 10K rows.

Problem: Full DataFrame scans and fuzzy matching will timeout at 1M+ rows.
Solution:
  1. Smart sampling for profiling (representative, fast, deterministic)
  2. Chunk processing for cleaning operations (memory-safe)
  3. Blocking for dedup (partition-first, compare within blocks)
  4. Size-aware defaults (thresholds adjust based on dataset size)

Usage:
    from services.performance import profile_with_sampling, apply_in_chunks, SizeAwareConfig
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import numpy as np
import pandas as pd

from utils.logger import logger


# ── Dataset size tiers ────────────────────────────────────────────────────────

TIER_SMALL  = 50_000     # < 50K rows   → full scan, all features
TIER_MEDIUM = 500_000    # < 500K rows  → sampling for profiling, chunked cleaning
TIER_LARGE  = 5_000_000  # < 5M rows    → aggressive sampling + streaming hints


class SizeAwareConfig:
    """
    Returns sensible defaults based on row count.
    Prevents performance surprises when dataset size grows.
    """

    def __init__(self, n_rows: int):
        self.n_rows = n_rows

    @property
    def tier(self) -> str:
        if self.n_rows < TIER_SMALL:
            return "small"
        elif self.n_rows < TIER_MEDIUM:
            return "medium"
        else:
            return "large"

    @property
    def profiling_sample_size(self) -> Optional[int]:
        """How many rows to sample for profiling. None = use all."""
        if self.n_rows < TIER_SMALL:
            return None          # small: profile everything
        elif self.n_rows < TIER_MEDIUM:
            return 50_000        # medium: 50K sample
        else:
            return 100_000       # large: 100K sample

    @property
    def chunk_size(self) -> int:
        """Rows per chunk for chunked processing."""
        if self.n_rows < TIER_SMALL:
            return self.n_rows   # no chunking needed
        elif self.n_rows < TIER_MEDIUM:
            return 50_000
        else:
            return 100_000

    @property
    def fuzzy_sample_size(self) -> Optional[int]:
        """Max rows to use in fuzzy dedup. Fuzzy is O(n²) without blocking."""
        if self.n_rows < TIER_SMALL:
            return None          # full scan
        else:
            return 10_000        # sample for large datasets

    @property
    def use_chunked_cleaning(self) -> bool:
        return self.n_rows >= TIER_MEDIUM

    @property
    def should_warn_user(self) -> bool:
        return self.n_rows >= TIER_MEDIUM

    def summary(self) -> Dict[str, Any]:
        return {
            "tier":                  self.tier,
            "n_rows":                self.n_rows,
            "profiling_sample_size": self.profiling_sample_size,
            "chunk_size":            self.chunk_size,
            "fuzzy_sample_size":     self.fuzzy_sample_size,
            "use_chunked_cleaning":  self.use_chunked_cleaning,
        }


# ── Sampling utilities ────────────────────────────────────────────────────────

def smart_sample(
    df: pd.DataFrame,
    n: Optional[int],
    seed: int = 42,
    stratify_col: Optional[str] = None,
) -> Tuple[pd.DataFrame, bool]:
    """
    Draw a representative sample from df.

    Args:
        df:            Source DataFrame
        n:             Target sample size. If None or >= len(df), returns df unchanged.
        seed:          Random seed for reproducibility
        stratify_col:  If provided, sample proportionally from each category

    Returns:
        (sampled_df, was_sampled)
    """
    if n is None or n >= len(df):
        return df, False

    if stratify_col and stratify_col in df.columns and df[stratify_col].nunique() < 100:
        # Stratified sampling: maintain category proportions
        try:
            groups = df.groupby(stratify_col, group_keys=False)
            sampled = groups.apply(
                lambda g: g.sample(
                    n=max(1, int(n * len(g) / len(df))),
                    random_state=seed,
                )
            ).reset_index(drop=True)
            if len(sampled) > n:
                sampled = sampled.sample(n=n, random_state=seed)
            logger.info(f"Stratified sample: {len(df):,} → {len(sampled):,} rows (col='{stratify_col}')")
            return sampled, True
        except Exception as e:
            logger.warning(f"Stratified sampling failed ({e}), falling back to random")

    sampled = df.sample(n=min(n, len(df)), random_state=seed).reset_index(drop=True)
    logger.info(f"Random sample: {len(df):,} → {len(sampled):,} rows ({n/len(df)*100:.1f}%)")
    return sampled, True


def profile_with_sampling(
    df: pd.DataFrame,
    profile_fn: Callable[[pd.DataFrame], Dict],
    seed: int = 42,
) -> Dict[str, Any]:
    """
    Run a profiling function on a representative sample when df is large.
    The profile result is annotated with sampling metadata.

    Args:
        df:         Full DataFrame
        profile_fn: Function(df) → profile dict
        seed:       Reproducibility seed

    Returns:
        profile dict with added "sampling" key
    """
    cfg = SizeAwareConfig(len(df))
    sample_size = cfg.profiling_sample_size

    sampled_df, was_sampled = smart_sample(df, sample_size, seed=seed)

    profile = profile_fn(sampled_df)

    # Always record actual full-dataset row count
    profile["rows"]     = len(df)
    profile["sampling"] = {
        "was_sampled":   was_sampled,
        "sample_size":   len(sampled_df),
        "full_size":     len(df),
        "sample_pct":    round(100 * len(sampled_df) / len(df), 1) if len(df) else 100,
        "note": (
            f"Profile computed on {len(sampled_df):,}-row sample ({cfg.profiling_sample_size:,} max)."
            if was_sampled else "Profile computed on full dataset."
        ),
    }
    return profile


# ── Chunked processing ────────────────────────────────────────────────────────

def iter_chunks(df: pd.DataFrame, chunk_size: int) -> Iterator[pd.DataFrame]:
    """Yield successive non-overlapping chunks of df."""
    n = len(df)
    for start in range(0, n, chunk_size):
        yield df.iloc[start : start + chunk_size]


def apply_in_chunks(
    df: pd.DataFrame,
    transform_fn: Callable[[pd.DataFrame], pd.DataFrame],
    chunk_size: Optional[int] = None,
    concat_ignore_index: bool = True,
) -> pd.DataFrame:
    """
    Apply transform_fn to df in chunks and concatenate results.
    Falls back to a single-pass if chunk_size is None or df is small.

    This keeps memory usage bounded for large datasets.
    """
    cfg = SizeAwareConfig(len(df))
    effective_chunk = chunk_size or cfg.chunk_size

    if not cfg.use_chunked_cleaning or effective_chunk >= len(df):
        return transform_fn(df)

    logger.info(f"Chunked processing: {len(df):,} rows in chunks of {effective_chunk:,}")
    parts = []
    for i, chunk in enumerate(iter_chunks(df, effective_chunk)):
        try:
            parts.append(transform_fn(chunk))
        except Exception as exc:
            logger.error(f"Chunk {i} failed: {exc} - using original chunk")
            parts.append(chunk)

    return pd.concat(parts, ignore_index=concat_ignore_index)


# ── Fuzzy dedup with blocking ─────────────────────────────────────────────────

def fuzzy_dedup_with_blocking(
    df: pd.DataFrame,
    columns: Optional[List[str]],
    threshold: int = 85,
    blocking_col: Optional[str] = None,
) -> pd.DataFrame:
    """
    Fuzzy deduplication with blocking to avoid O(n²) comparisons.

    Blocking: partition rows by the first character of blocking_col.
    Fuzzy matching only happens within each block.

    Falls back to full fuzzy scan for small datasets.
    """
    from services.fuzzy_dedup import remove_fuzzy_duplicates

    cfg = SizeAwareConfig(len(df))

    # Small dataset: just run normally
    if cfg.fuzzy_sample_size is None or len(df) <= (cfg.fuzzy_sample_size or 0):
        return remove_fuzzy_duplicates(df, columns=columns, threshold=threshold)

    logger.warning(
        f"Dataset has {len(df):,} rows - fuzzy dedup limited to {cfg.fuzzy_sample_size:,} "
        f"rows via sampling to prevent timeout."
    )

    # Determine blocking column
    block_col = blocking_col
    if block_col is None and columns:
        block_col = columns[0]
    elif block_col is None and len(df.columns) > 0:
        # Use highest-cardinality string column
        str_cols = [c for c in df.columns if df[c].dtype == object]
        block_col = str_cols[0] if str_cols else None

    if block_col is None or block_col not in df.columns:
        # No blocking possible - sample and run
        sampled, _ = smart_sample(df, cfg.fuzzy_sample_size)
        return remove_fuzzy_duplicates(sampled, columns=columns, threshold=threshold)

    # Block by first character of blocking_col
    df = df.copy()
    df["__block_key__"] = df[block_col].astype(str).str[0].str.upper()
    blocks = df.groupby("__block_key__", group_keys=False)

    parts = []
    for key, block in blocks:
        block = block.drop(columns=["__block_key__"]).reset_index(drop=True)
        if len(block) > 5_000:
            # Block too large → sample within block
            block, _ = smart_sample(block, 5_000)
        try:
            parts.append(remove_fuzzy_duplicates(block, columns=columns, threshold=threshold))
        except Exception as e:
            logger.error(f"Fuzzy dedup failed for block '{key}': {e} - keeping block as-is")
            parts.append(block)

    result = pd.concat(parts, ignore_index=True)
    if "__block_key__" in result.columns:
        result = result.drop(columns=["__block_key__"])
    return result


# ── Convenience: annotate a response with performance context ─────────────────

def performance_context(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Returns a dict describing the performance tier and recommendations.
    Include this in API responses so the frontend can show warnings.
    """
    cfg = SizeAwareConfig(len(df))
    ctx = cfg.summary()

    if cfg.tier == "large":
        ctx["warnings"] = [
            "Dataset is very large - profiling uses sampling for speed.",
            "Fuzzy dedup is limited to a sample to prevent timeout.",
            "Consider exporting and processing in chunks for transforms on all rows.",
        ]
    elif cfg.tier == "medium":
        ctx["warnings"] = [
            "Large dataset - profiling may use sampling.",
        ]
    else:
        ctx["warnings"] = []

    return ctx
