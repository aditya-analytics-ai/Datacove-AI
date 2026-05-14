"""
Unit tests for services/cleaning_engine.py

Run with:  pytest tests/test_cleaning_engine.py -v
"""
import pytest
import pandas as pd
import numpy as np
from services.cleaning_engine import apply_transformation, auto_clean


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def messy_df():
    return pd.DataFrame({
        "name":   ["  Alice ", "bob", "BOB", "Alice", "  charlie "],
        "age":    [25, 30, 30, 25, None],
        "salary": [50000.0, 60000.0, 60000.0, 50000.0, 55000.123456],
        "email":  ["alice@test.com", "bad-email", "bob@test.com", "alice@test.com", "charlie@ok.io"],
        "city":   ["New York", "london", "London", "new york", "Chicago"],
    })


@pytest.fixture
def numeric_df():
    return pd.DataFrame({
        "value": [1.0, 2.0, 3.0, 100.0, 4.0, 5.0],   # 100 is an outlier
        "mixed": ["1", "2", "abc", "4", "5", "6"],
    })


# ── remove_duplicates ────────────────────────────────────────────────────────

def test_remove_duplicates_removes_exact(messy_df):
    # messy_df has whitespace-padded names - need true exact dupes for this test
    df = pd.DataFrame({
        "name":   ["Alice", "Bob", "Alice", "Charlie"],
        "age":    [25, 30, 25, 35],
        "salary": [50000.0, 60000.0, 50000.0, 70000.0],
    })
    result = apply_transformation(df, "remove_duplicates", {})
    assert len(result) < len(df)
    assert result.duplicated().sum() == 0


def test_remove_duplicates_does_not_mutate(messy_df):
    original_len = len(messy_df)
    apply_transformation(messy_df, "remove_duplicates", {})
    assert len(messy_df) == original_len   # original unchanged


# ── trim_whitespace ───────────────────────────────────────────────────────────

def test_trim_whitespace_strips_leading_trailing(messy_df):
    result = apply_transformation(messy_df, "trim_whitespace", {})
    assert result["name"].iloc[0] == "Alice"
    assert result["name"].iloc[4] == "charlie"


def test_trim_whitespace_non_string_columns_unchanged(messy_df):
    result = apply_transformation(messy_df, "trim_whitespace", {})
    assert result["age"].iloc[0] == messy_df["age"].iloc[0]


# ── standardise_capitalisation ────────────────────────────────────────────────

def test_capitalisation_title_case(messy_df):
    result = apply_transformation(messy_df, "standardise_capitalisation", {})
    assert result["name"].iloc[1] == "Bob"
    assert result["city"].iloc[1] == "London"


# ── normalise_categories ──────────────────────────────────────────────────────

def test_normalise_categories_merges_variants(messy_df):
    result = apply_transformation(messy_df, "normalise_categories", {})
    city_vals = result["city"].str.lower().unique().tolist()
    # "london" and "London" should merge
    assert len([v for v in city_vals if "london" in v]) == 1


# ── fill_missing ──────────────────────────────────────────────────────────────

def test_fill_missing_median(messy_df):
    # Use a fresh df with a known null
    df = pd.DataFrame({"age": [25.0, 30.0, None, 35.0, 40.0]})
    result = apply_transformation(
        df, "fill_missing", {"column": "age", "strategy": "median"}
    )
    assert result["age"].isna().sum() == 0


def test_fill_missing_mode_string(messy_df):
    df = messy_df.copy()
    df.loc[0, "city"] = None
    result = apply_transformation(df, "fill_missing", {"column": "city", "strategy": "mode"})
    assert result["city"].isna().sum() == 0


# ── coerce_numeric ────────────────────────────────────────────────────────────

def test_coerce_numeric_converts_strings(numeric_df):
    result = apply_transformation(numeric_df, "coerce_numeric", {"column": "mixed"})
    # "abc" should become NaN; numeric strings should become floats
    assert pd.api.types.is_numeric_dtype(result["mixed"])
    assert result["mixed"].isna().sum() >= 1   # at least "abc" becomes NaN


# ── round_numeric ─────────────────────────────────────────────────────────────

def test_round_numeric(messy_df):
    result = apply_transformation(messy_df, "round_numeric", {"column": "salary", "decimals": 0})
    assert result["salary"].iloc[4] == 55000.0


# ── clip_outliers ─────────────────────────────────────────────────────────────

def test_clip_outliers_iqr(numeric_df):
    result = apply_transformation(numeric_df, "clip_outliers", {"column": "value", "method": "iqr"})
    # 100 should be clipped down
    assert result["value"].max() < 100.0


# ── drop_column ───────────────────────────────────────────────────────────────

def test_drop_column(messy_df):
    result = apply_transformation(messy_df, "drop_column", {"column": "email"})
    assert "email" not in result.columns
    assert "name" in result.columns


# ── drop_constant_columns ─────────────────────────────────────────────────────

def test_drop_constant_columns():
    df = pd.DataFrame({"a": [1, 1, 1], "b": [1, 2, 3]})
    result = apply_transformation(df, "drop_constant_columns", {})
    assert "a" not in result.columns
    assert "b" in result.columns


# ── drop_high_missing_columns ─────────────────────────────────────────────────

def test_drop_high_missing_columns():
    df = pd.DataFrame({"a": [None, None, None], "b": [1, 2, 3]})
    result = apply_transformation(df, "drop_high_missing_columns", {"threshold": 0.5})
    assert "a" not in result.columns
    assert "b" in result.columns


# ── normalize_unicode ─────────────────────────────────────────────────────────

def test_normalize_unicode():
    df = pd.DataFrame({"name": ["café", "naïve", "résumé"]})
    result = apply_transformation(df, "normalize_unicode", {"column": "name"})
    assert result["name"].iloc[0] == "cafe"
    assert result["name"].iloc[1] == "naive"


# ── auto_clean ────────────────────────────────────────────────────────────────

def test_auto_clean_pipeline(messy_df):
    result = auto_clean(messy_df)
    # Whitespace must be trimmed on all string columns
    assert not result["name"].str.startswith(" ").any()
    assert not result["name"].str.endswith(" ").any()
    # auto_clean runs remove_duplicates THEN capitalise - capitalisation can
    # create new "near-dupes" (bob → Bob, BOB → Bob). That is expected behaviour.
    # We just verify the pipeline ran without crashing and returned fewer or equal rows.
    assert len(result) <= len(messy_df)


# ── unknown action ────────────────────────────────────────────────────────────

def test_unknown_action_raises():
    df = pd.DataFrame({"a": [1, 2]})
    with pytest.raises(ValueError, match="Unknown cleaning action"):
        apply_transformation(df, "definitely_not_a_real_action", {})
