"""
Unit tests for services/health_score.py and services/issue_detector.py
"""
import pytest
import pandas as pd
import numpy as np
from services.health_score import calculate_health_score
from services.issue_detector import detect_issues


@pytest.fixture
def clean_df():
    return pd.DataFrame({
        "name":   ["Alice", "Bob", "Charlie"],
        "age":    [25, 30, 35],
        "email":  ["a@test.com", "b@test.com", "c@test.com"],
    })


@pytest.fixture
def dirty_df():
    return pd.DataFrame({
        "name":   ["Alice", "Alice", None, "  bob "],
        "age":    [-5, 30, 30, None],
        "email":  ["bad-email", "b@test.com", "also-bad", "c@test.com"],
        "const":  ["same", "same", "same", "same"],
    })


# ── Health score ───────────────────────────────────────────────────────────────

def test_clean_df_scores_high(clean_df):
    issues = detect_issues(clean_df)
    result = calculate_health_score(clean_df, issues)
    assert result["score"] >= 85
    assert result["grade"] in ("A", "B")


def test_dirty_df_scores_lower(dirty_df, clean_df):
    dirty_issues = detect_issues(dirty_df)
    clean_issues = detect_issues(clean_df)
    dirty_score = calculate_health_score(dirty_df, dirty_issues)["score"]
    clean_score = calculate_health_score(clean_df, clean_issues)["score"]
    assert dirty_score < clean_score


def test_score_bounded_0_100(dirty_df):
    issues = detect_issues(dirty_df)
    result = calculate_health_score(dirty_df, issues)
    assert 0 <= result["score"] <= 100


def test_score_has_grade(clean_df):
    issues = detect_issues(clean_df)
    result = calculate_health_score(clean_df, issues)
    assert result["grade"] in ("A", "B", "C", "D", "F")


def test_score_has_breakdown(dirty_df):
    issues = detect_issues(dirty_df)
    result = calculate_health_score(dirty_df, issues)
    assert isinstance(result["breakdown"], dict)


# ── Issue detector ─────────────────────────────────────────────────────────────

def test_detects_duplicates():
    df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
    issues = detect_issues(df)
    types = [i["type"] for i in issues]
    assert "duplicate_rows" in types


def test_detects_missing_values():
    df = pd.DataFrame({"a": [1, None, 3]})
    issues = detect_issues(df)
    types = [i["type"] for i in issues]
    assert "missing_values" in types


def test_detects_constant_column():
    df = pd.DataFrame({"a": [1, 1, 1], "b": [1, 2, 3]})
    issues = detect_issues(df)
    types = [i["type"] for i in issues]
    assert "constant_column" in types


def test_detects_invalid_email():
    df = pd.DataFrame({"email": ["bad", "also-bad", "good@test.com"]})
    issues = detect_issues(df)
    types = [i["type"] for i in issues]
    assert "invalid_email" in types


def test_no_false_positives_on_clean_data(clean_df):
    issues = detect_issues(clean_df)
    # Should be empty or minimal
    high_sev = [i for i in issues if i.get("severity") == "high"]
    assert len(high_sev) == 0
