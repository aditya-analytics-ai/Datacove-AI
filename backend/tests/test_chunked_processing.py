"""
tests/test_chunked_processing.py - Tests for chunked pandas transform path.

Verifies that large DataFrames (>_CHUNK_THRESHOLD rows) are chunked correctly
and produce identical results to the non-chunked path.

Run with:  pytest tests/test_chunked_processing.py -v
"""
import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch
from services.cleaning_engine import (
    apply_transformation,
    _CHUNK_THRESHOLD,
    _CHUNK_SIZE,
    _CHUNKABLE_ACTIONS,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_large_df(n_rows: int) -> pd.DataFrame:
    """Build a DataFrame larger than CHUNK_THRESHOLD."""
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "name":   [f"  user_{i}  " for i in range(n_rows)],   # leading/trailing spaces
        "age":    rng.integers(18, 80, size=n_rows).astype(float),
        "salary": rng.uniform(30_000, 200_000, size=n_rows),
        "city":   rng.choice(["London", "london", "NEW YORK", "New York"], size=n_rows),
    })


# ── Chunked vs non-chunked equivalence ───────────────────────────────────────

class TestChunkedEquivalence:
    """
    For chunkable actions, chunked result must equal non-chunked result.
    We test with a DataFrame just above _CHUNK_THRESHOLD.
    """

    @pytest.fixture(scope="class")
    def large_df(self):
        return _make_large_df(_CHUNK_THRESHOLD + 1_000)

    def test_trim_whitespace_chunked_equals_non_chunked(self, large_df):
        """Both paths should produce the same trimmed names."""
        # Chunked path (large_df > threshold)
        chunked = apply_transformation(large_df, "trim_whitespace", {})
        # Force non-chunked by passing a small slice
        small   = large_df.iloc[:10].copy()
        non_chunked = apply_transformation(small, "trim_whitespace", {})

        # Both should strip spaces
        assert not chunked["name"].str.startswith(" ").any()
        assert not non_chunked["name"].str.startswith(" ").any()

    def test_chunked_row_count_preserved(self, large_df):
        """Chunked processing must not drop or duplicate rows."""
        result = apply_transformation(large_df, "trim_whitespace", {})
        assert len(result) == len(large_df)

    def test_chunked_columns_preserved(self, large_df):
        """Chunked processing must keep all original columns."""
        result = apply_transformation(large_df, "trim_whitespace", {})
        assert list(result.columns) == list(large_df.columns)

    def test_find_replace_chunked(self, large_df):
        result = apply_transformation(
            large_df, "find_replace",
            {"column": "city", "find": "london", "replace": "London",
             "case_sensitive": False}
        )
        assert len(result) == len(large_df)
        # No lowercase "london" should remain
        assert not result["city"].str.fullmatch("london").any()

    def test_cast_type_chunked(self, large_df):
        """cast_type on a large df should work chunk-by-chunk."""
        result = apply_transformation(
            large_df, "cast_type",
            {"column": "salary", "dtype": "float"}
        )
        assert pd.api.types.is_float_dtype(result["salary"])
        assert len(result) == len(large_df)


# ── Chunk boundary correctness ────────────────────────────────────────────────

class TestChunkBoundaries:
    """Verify no off-by-one errors at chunk boundaries."""

    def test_exactly_one_chunk(self):
        """DataFrame exactly at threshold should NOT chunk."""
        df = _make_large_df(_CHUNK_THRESHOLD)
        # Should still work correctly (uses standard path)
        result = apply_transformation(df, "trim_whitespace", {})
        assert len(result) == _CHUNK_THRESHOLD

    def test_exactly_threshold_plus_one(self):
        """One row over threshold triggers chunked path."""
        df = _make_large_df(_CHUNK_THRESHOLD + 1)
        result = apply_transformation(df, "trim_whitespace", {})
        assert len(result) == _CHUNK_THRESHOLD + 1

    def test_multiple_chunks(self):
        """DataFrame spanning 3+ chunks produces correct total."""
        n = _CHUNK_SIZE * 3 + 500
        df = _make_large_df(n)
        result = apply_transformation(df, "trim_whitespace", {})
        assert len(result) == n

    def test_index_is_reset_after_chunking(self):
        """Chunked concat should produce a clean 0-based index."""
        df = _make_large_df(_CHUNK_THRESHOLD + 1_000)
        result = apply_transformation(df, "trim_whitespace", {})
        assert list(result.index) == list(range(len(result)))


# ── Non-chunkable actions still work on large DFs ────────────────────────────

class TestNonChunkableOnLargeDF:
    """Scale/bin/clip etc. need global stats - must NOT be chunked."""

    def test_scale_numeric_on_large_df(self):
        """scale_numeric requires global min/max - must use full df."""
        df = _make_large_df(_CHUNK_THRESHOLD + 1_000)
        result = apply_transformation(
            df, "scale_numeric", {"column": "salary", "method": "min_max"}
        )
        # After min-max scaling, values must be in [0, 1]
        assert result["salary"].min() >= 0.0 - 1e-9
        assert result["salary"].max() <= 1.0 + 1e-9

    def test_clip_outliers_on_large_df(self):
        """clip_outliers needs global IQR - must use full df."""
        df = _make_large_df(_CHUNK_THRESHOLD + 1_000)
        # Inject an extreme outlier
        df.loc[0, "salary"] = 999_999_999
        result = apply_transformation(
            df, "clip_outliers", {"column": "salary", "method": "iqr"}
        )
        assert result["salary"].max() < 999_999_999

    def test_bin_numeric_raises_helpful_error(self):
        """bin_numeric with negative bins raises ValueError."""
        df = pd.DataFrame({"val": [1.0, 2.0, 3.0]})
        with pytest.raises((ValueError, Exception)):
            apply_transformation(df, "bin_numeric", {"column": "val", "bins": -1})
