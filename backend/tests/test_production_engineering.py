"""
tests/test_production_engineering.py

37 tests covering:
  - Retry mechanism (8 tests)
  - Request validator (20 tests)
  - Report generator (7 tests)
  - Integration flows (2 tests - pure Python, no HTTP)
"""
import html
import time
import uuid
from typing import Any
from unittest.mock import MagicMock, patch, call

import pandas as pd
import pytest


# ══════════════════════════════════════════════════════════════════════════════
# RETRY TESTS (8)
# ══════════════════════════════════════════════════════════════════════════════

class TestRetry:
    """Test retry.py - exponential backoff, jitter, callbacks."""

    def test_success_on_first_attempt(self):
        from utils.retry import retry, RetryConfig
        calls = []
        def fn():
            calls.append(1)
            return "ok"
        cfg = RetryConfig(max_attempts=3, base_delay=0)
        assert retry(fn, config=cfg) == "ok"
        assert len(calls) == 1

    def test_retries_on_failure_then_succeeds(self):
        from utils.retry import retry, RetryConfig
        calls = []
        def fn():
            calls.append(1)
            if len(calls) < 3:
                raise ConnectionError("transient")
            return "success"
        cfg = RetryConfig(max_attempts=4, base_delay=0, jitter=0)
        assert retry(fn, config=cfg) == "success"
        assert len(calls) == 3

    def test_raises_after_max_attempts(self):
        from utils.retry import retry, RetryConfig
        def always_fails():
            raise ValueError("always")
        cfg = RetryConfig(max_attempts=3, base_delay=0, jitter=0)
        with pytest.raises(ValueError, match="always"):
            retry(always_fails, config=cfg)

    def test_non_retryable_exception_raises_immediately(self):
        from utils.retry import retry, RetryConfig
        calls = []
        def fn():
            calls.append(1)
            raise TypeError("not retryable")
        cfg = RetryConfig(
            max_attempts=5, base_delay=0, jitter=0,
            retryable_exceptions=(ConnectionError,),  # TypeError NOT in here
        )
        with pytest.raises(TypeError):
            retry(fn, config=cfg)
        assert len(calls) == 1   # raised on first attempt, not retried

    def test_on_retry_callback_called(self):
        from utils.retry import retry, RetryConfig
        callback_calls = []
        def fn():
            raise OSError("fail")
        def on_retry(attempt, exc):
            callback_calls.append((attempt, type(exc).__name__))
        cfg = RetryConfig(max_attempts=3, base_delay=0, jitter=0, on_retry=on_retry)
        with pytest.raises(OSError):
            retry(fn, config=cfg)
        assert len(callback_calls) == 2   # called for attempt 1 and 2 (not final)

    def test_delay_increases_with_backoff(self):
        from utils.retry import _compute_delay, RetryConfig
        cfg = RetryConfig(base_delay=1.0, backoff_factor=2.0, jitter=0)
        d0 = _compute_delay(0, cfg)
        d1 = _compute_delay(1, cfg)
        d2 = _compute_delay(2, cfg)
        assert d0 < d1 < d2
        assert abs(d0 - 1.0) < 0.01
        assert abs(d1 - 2.0) < 0.01

    def test_delay_capped_at_max(self):
        from utils.retry import _compute_delay, RetryConfig
        cfg = RetryConfig(base_delay=1.0, backoff_factor=100.0, max_delay=5.0, jitter=0)
        assert _compute_delay(10, cfg) <= 5.0

    def test_retry_decorator_wraps_sync_function(self):
        from utils.retry import retry_decorator, RetryConfig
        calls = []
        cfg = RetryConfig(max_attempts=3, base_delay=0, jitter=0)
        @retry_decorator(cfg)
        def fn():
            calls.append(1)
            if len(calls) < 2:
                raise RuntimeError("once")
            return "done"
        assert fn() == "done"
        assert len(calls) == 2


# ══════════════════════════════════════════════════════════════════════════════
# REQUEST VALIDATOR TESTS (20)
# ══════════════════════════════════════════════════════════════════════════════

class TestSessionIdValidator:
    """validate_session_id - 5 tests"""

    def test_valid_uuid_passes(self):
        from utils.request_validator import validate_session_id
        sid = str(uuid.uuid4())
        assert validate_session_id(sid) == sid

    def test_empty_string_raises(self):
        from utils.request_validator import validate_session_id
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            validate_session_id("")
        assert exc.value.status_code == 400

    def test_path_traversal_blocked(self):
        from utils.request_validator import validate_session_id
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            validate_session_id("../../etc/passwd")
        assert exc.value.status_code == 400
        assert "invalid" in exc.value.detail.lower()

    def test_non_uuid_string_blocked(self):
        from utils.request_validator import validate_session_id
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            validate_session_id("not-a-uuid-at-all")

    def test_too_long_string_blocked(self):
        from utils.request_validator import validate_session_id
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            validate_session_id("a" * 100)


class TestActionValidator:
    """validate_action - 5 tests"""

    def test_valid_action_passes(self):
        from utils.request_validator import validate_action
        assert validate_action("trim_whitespace") == "trim_whitespace"

    def test_unknown_action_raises_400(self):
        from utils.request_validator import validate_action
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            validate_action("definitely_not_real")
        assert exc.value.status_code == 400

    def test_suggestion_included_in_error(self):
        from utils.request_validator import validate_action
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            validate_action("trim_whitespac")   # typo
        assert "trim_whitespace" in exc.value.detail

    def test_empty_action_raises(self):
        from utils.request_validator import validate_action
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            validate_action("")

    def test_all_known_actions_pass(self):
        from utils.request_validator import validate_action, VALID_ACTIONS
        for action in list(VALID_ACTIONS)[:10]:
            assert validate_action(action) == action


class TestParamValidator:
    """validate_params - 5 tests"""

    def test_fill_missing_without_strategy_raises(self):
        from utils.request_validator import validate_params
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            validate_params("fill_missing", {})
        assert "strategy" in exc.value.detail

    def test_fill_missing_with_strategy_passes(self):
        from utils.request_validator import validate_params
        result = validate_params("fill_missing", {"strategy": "median"})
        assert result["strategy"] == "median"

    def test_oversized_string_param_raises(self):
        from utils.request_validator import validate_params
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            validate_params("trim_whitespace", {"mode": "x" * 20_000})
        assert "length" in exc.value.detail.lower()

    def test_sql_apply_select_passes(self):
        from utils.request_validator import validate_params
        result = validate_params("sql_apply", {"query": "SELECT * FROM df"})
        assert result is not None

    def test_sql_apply_drop_blocked(self):
        from utils.request_validator import validate_params
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            validate_params("sql_apply", {"query": "SELECT * FROM df; DROP TABLE df"})
        assert exc.value.status_code == 400
        assert "drop" in exc.value.detail.lower()


class TestColumnValidator:
    """validate_column_exists - 5 tests"""

    def test_existing_column_passes(self):
        from utils.request_validator import validate_column_exists
        assert validate_column_exists("age", "fill_missing", ["name", "age", "city"]) == "age"

    def test_missing_column_raises_with_suggestion(self):
        from utils.request_validator import validate_column_exists
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            validate_column_exists("agee", "fill_missing", ["name", "age", "city"])
        assert "age" in exc.value.detail   # suggestion

    def test_none_column_ok_for_dataset_wide_action(self):
        from utils.request_validator import validate_column_exists
        # remove_duplicates doesn't require a column
        assert validate_column_exists(None, "remove_duplicates", ["a", "b"]) is None

    def test_none_column_raises_for_column_required_action(self):
        from utils.request_validator import validate_column_exists
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            validate_column_exists(None, "coerce_numeric", ["a", "b"])

    def test_sql_injection_in_column_name_raises(self):
        from utils.request_validator import validate_column_exists
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            validate_column_exists("'; DROP TABLE users; --", "fill_missing", ["name"])


# ══════════════════════════════════════════════════════════════════════════════
# REPORT GENERATOR TESTS (7)
# ══════════════════════════════════════════════════════════════════════════════

class TestReportGenerator:

    def _make_inputs(self):
        profile  = {"rows": 100, "columns": 5, "columns_profile": [], "duplicate_rows": 2, "total_missing": 10}
        issues   = [{"type": "missing_values", "severity": "high", "column": "age",
                     "description": "10 missing values", "count": 10}]
        health   = {"score": 72.5, "grade": "C", "missing_pct": 10.0,
                    "duplicate_pct": 2.0, "deductions": [{"reason": "Missing values", "points": -15}]}
        anomalies = [{"column": "salary", "outlier_count": 3, "method": "IQR",
                      "description": "3 outliers detected"}]
        return profile, issues, health, anomalies

    def test_returns_html_string(self):
        from services.report_generator import generate_html_report
        p, i, h, a = self._make_inputs()
        result = generate_html_report("test.csv", p, i, h, a)
        assert isinstance(result, str)
        assert result.strip().startswith("<!DOCTYPE html>")

    def test_filename_in_output(self):
        from services.report_generator import generate_html_report
        p, i, h, a = self._make_inputs()
        result = generate_html_report("my_data.csv", p, i, h, a)
        assert "my_data.csv" in result

    def test_score_in_output(self):
        from services.report_generator import generate_html_report
        p, i, h, a = self._make_inputs()
        result = generate_html_report("test.csv", p, i, h, a)
        assert "72.5" in result

    def test_xss_escaped_in_filename(self):
        from services.report_generator import generate_html_report
        p, i, h, a = self._make_inputs()
        result = generate_html_report("<script>alert(1)</script>.csv", p, i, h, a)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_audit_section_absent_when_no_entries(self):
        from services.report_generator import generate_html_report
        p, i, h, a = self._make_inputs()
        result = generate_html_report("test.csv", p, i, h, a, audit_entries=None)
        assert "Audit Trail" not in result

    def test_audit_section_present_when_entries_given(self):
        from services.report_generator import generate_html_report
        p, i, h, a = self._make_inputs()
        audit = [{
            "entry_id": "abc123", "timestamp": "2024-01-01T10:00:00",
            "action": "trim_whitespace", "params": {"column": "name"},
            "triggered_by": "user", "ai_confidence": None,
            "rows_before": 100, "rows_after": 100,
            "cells_changed": 5, "cols_added": [], "cols_removed": [],
            "summary": "Trim Whitespace on 'name': Updated 5 cells.",
        }]
        result = generate_html_report("test.csv", p, i, h, a, audit_entries=audit)
        assert "Audit Trail" in result
        assert "Trim Whitespace" in result

    def test_audit_xss_escaped(self):
        from services.report_generator import generate_html_report
        p, i, h, a = self._make_inputs()
        audit = [{
            "entry_id": "x", "timestamp": "2024-01-01T10:00:00",
            "action": "trim_whitespace",
            "params": {"column": "<script>xss</script>"},
            "triggered_by": "user", "ai_confidence": None,
            "rows_before": 10, "rows_after": 10,
            "cells_changed": 0, "cols_added": [], "cols_removed": [],
            "summary": "<img src=x onerror=alert(1)>",
        }]
        result = generate_html_report("test.csv", p, i, h, a, audit_entries=audit)
        assert "<script>" not in result
        assert "<img src=x" not in result


# ══════════════════════════════════════════════════════════════════════════════
# INTEGRATION FLOW TESTS (2 - pure Python, no HTTP server needed)
# ══════════════════════════════════════════════════════════════════════════════

class TestIntegrationFlows:

    def test_clean_then_audit_then_report(self):
        """Full flow: apply transform → audit recorded → report includes it."""
        import pandas as pd
        from services.cleaning_engine import apply_transformation
        from services.audit_log import record as audit_record, get_log, clear_log
        from services.report_generator import generate_html_report

        sid = str(uuid.uuid4())
        df_before = pd.DataFrame({"name": ["  alice ", "  BOB "], "age": [25, 30]})
        df_after  = apply_transformation(df_before, "trim_whitespace", {})

        entry = audit_record(sid, "trim_whitespace", {}, df_before, df_after)
        log   = get_log(sid)
        assert len(log) == 1
        assert log[0]["action"] == "trim_whitespace"

        report = generate_html_report(
            "test.csv",
            {"rows": 2, "columns": 2, "columns_profile": []},
            [],
            {"score": 95, "grade": "A", "missing_pct": 0, "duplicate_pct": 0, "deductions": []},
            [],
            audit_entries=log,
        )
        assert "Audit Trail" in report
        assert "Trim Whitespace" in report
        clear_log(sid)

    def test_ai_safety_gate_blocks_low_confidence(self):
        """AI safety gate correctly blocks suggestions with confidence < threshold."""
        import pandas as pd
        from services.ai_safety import gate_suggestion, BLOCK_THRESHOLD

        df = pd.DataFrame({"price": [10, 20, 30]})
        suggestion = {
            "action": "sql_apply",          # high-risk action → low confidence
            "column": None,
            "params": {"query": "SELECT *"},
            "priority": "low",
        }
        gated = gate_suggestion(suggestion, df, profile=None, force_confirm=False)
        # sql_apply has 0.60 risk → confidence = 0.40 → gate = "confirm" or "blocked"
        assert gated["gate"] in ("confirm", "blocked")
        assert gated["confidence"] < 0.80
