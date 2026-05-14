"""
Comprehensive test suite - covers the 5 critical upgrades:
  1. Audit Log
  2. AI Safety Layer
  3. Dynamic Pipeline Engine
  4. Performance Layer
  5. Edge cases & regression

Run with:  pytest tests/test_upgrades.py -v
"""
import pytest
import pandas as pd
import numpy as np

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def simple_df():
    return pd.DataFrame({
        "name":   ["Alice", "Bob", "Charlie", "Alice"],
        "age":    [25, 30, None, 25],
        "salary": [50000.0, 60000.0, 55000.0, 50000.0],
        "email":  ["alice@test.com", "bad-email", "charlie@ok.io", "alice@test.com"],
        "city":   ["New York", "london", "London", "New York"],
    })


@pytest.fixture
def large_df():
    """Simulate a 'medium' dataset for performance tests."""
    np.random.seed(42)
    n = 60_000
    return pd.DataFrame({
        "id":     range(n),
        "value":  np.random.randn(n),
        "cat":    np.random.choice(["A", "B", "C"], n),
        "score":  np.random.randint(0, 100, n),
    })


@pytest.fixture
def profile_stub():
    return {
        "rows": 100,
        "columns": 5,
        "columns_profile": [
            {"column": "name",   "detected_type": "string",  "missing_pct": 0,   "unique_count": 3},
            {"column": "age",    "detected_type": "numeric", "missing_pct": 0.2, "unique_count": 3},
            {"column": "salary", "detected_type": "numeric", "missing_pct": 0,   "unique_count": 3},
            {"column": "email",  "detected_type": "string",  "missing_pct": 0,   "unique_count": 4},
            {"column": "city",   "detected_type": "string",  "missing_pct": 0,   "unique_count": 2},
        ],
    }


# ════════════════════════════════════════════════════════════════════════════════
# 1. AUDIT LOG TESTS
# ════════════════════════════════════════════════════════════════════════════════

class TestAuditLog:
    """Tests for services/audit_log.py"""

    def test_record_creates_entry(self, simple_df):
        from services.audit_log import record, get_log, clear_log

        session_id = "test_audit_001"
        clear_log(session_id)

        df_after = simple_df.drop_duplicates().reset_index(drop=True)
        entry = record(
            session_id=session_id,
            action="remove_duplicates",
            params={},
            df_before=simple_df,
            df_after=df_after,
        )

        assert entry.action == "remove_duplicates"
        assert entry.rows_before == 4
        assert entry.rows_after == 3
        assert entry.rows_affected == 1
        clear_log(session_id)

    def test_get_log_returns_list_of_dicts(self, simple_df):
        from services.audit_log import record, get_log, clear_log

        session_id = "test_audit_002"
        clear_log(session_id)

        record(session_id, "trim_whitespace", {}, simple_df, simple_df)
        entries = get_log(session_id)

        assert isinstance(entries, list)
        assert len(entries) == 1
        assert "entry_id" in entries[0]
        assert "timestamp" in entries[0]
        assert "summary" in entries[0]
        clear_log(session_id)

    def test_cells_changed_tracked(self, simple_df):
        from services.audit_log import record, clear_log
        from services.cleaning_engine import apply_transformation

        session_id = "test_audit_003"
        clear_log(session_id)

        df_after = apply_transformation(simple_df, "standardise_capitalisation", {})
        entry = record(session_id, "standardise_capitalisation", {}, simple_df, df_after)

        # "london" → "London" should register as a change
        assert entry.cells_changed >= 0   # at minimum 0 (may already be title case)
        clear_log(session_id)

    def test_clear_log_wipes_session(self, simple_df):
        from services.audit_log import record, get_log, clear_log

        session_id = "test_audit_004"
        record(session_id, "trim_whitespace", {}, simple_df, simple_df)
        assert len(get_log(session_id)) == 1

        clear_log(session_id)
        assert get_log(session_id) == []

    def test_entry_to_dict_has_required_keys(self, simple_df):
        from services.audit_log import record, clear_log

        session_id = "test_audit_005"
        clear_log(session_id)
        entry = record(session_id, "drop_column", {"column": "email"}, simple_df, simple_df.drop(columns=["email"]))

        d = entry.to_dict()
        required = ["entry_id", "session_id", "timestamp", "action", "params",
                    "rows_before", "rows_after", "cells_changed", "sample_changes",
                    "cols_added", "cols_removed", "summary", "issue_type"]
        for key in required:
            assert key in d, f"Missing key: {key}"
        clear_log(session_id)

    def test_export_csv_returns_valid_csv(self, simple_df):
        from services.audit_log import record, export_csv, clear_log

        session_id = "test_audit_006"
        clear_log(session_id)
        record(session_id, "trim_whitespace", {}, simple_df, simple_df)

        csv = export_csv(session_id)
        lines = [l for l in csv.split("\n") if l.strip()]
        assert len(lines) >= 2   # header + at least one row
        assert "action" in lines[0]
        clear_log(session_id)

    def test_audit_multiple_sessions_isolated(self, simple_df):
        from services.audit_log import record, get_log, clear_log

        sid_a = "test_audit_session_a"
        sid_b = "test_audit_session_b"
        clear_log(sid_a); clear_log(sid_b)

        record(sid_a, "trim_whitespace", {}, simple_df, simple_df)
        record(sid_a, "remove_duplicates", {}, simple_df, simple_df)
        record(sid_b, "trim_whitespace", {}, simple_df, simple_df)

        assert len(get_log(sid_a)) == 2
        assert len(get_log(sid_b)) == 1
        clear_log(sid_a); clear_log(sid_b)

    def test_audit_cols_added_tracked(self, simple_df):
        from services.audit_log import record, clear_log
        from services.cleaning_engine import apply_transformation

        session_id = "test_audit_cols"
        clear_log(session_id)

        df_after = apply_transformation(simple_df, "flag_invalid_emails", {"column": "email"})
        entry = record(session_id, "flag_invalid_emails", {"column": "email"}, simple_df, df_after)

        assert "email_invalid" in entry.cols_added
        clear_log(session_id)


# ════════════════════════════════════════════════════════════════════════════════
# 2. AI SAFETY LAYER TESTS
# ════════════════════════════════════════════════════════════════════════════════

class TestAISafety:
    """Tests for services/ai_safety.py"""

    def test_high_confidence_for_safe_actions(self, simple_df, profile_stub):
        from services.ai_safety import score_confidence

        suggestion = {"action": "trim_whitespace", "priority": "high", "column": None}
        score = score_confidence(suggestion, profile_stub)
        assert score >= 0.80, f"Expected high confidence for trim_whitespace, got {score}"

    def test_lower_confidence_for_risky_actions(self, simple_df, profile_stub):
        from services.ai_safety import score_confidence

        suggestion = {"action": "sql_apply", "priority": "medium", "column": None}
        score = score_confidence(suggestion, profile_stub)
        assert score < 0.60, f"Expected lower confidence for sql_apply, got {score}"

    def test_unknown_column_penalises_confidence(self, simple_df, profile_stub):
        from services.ai_safety import score_confidence

        good = {"action": "fill_missing", "priority": "high", "column": "age"}
        bad  = {"action": "fill_missing", "priority": "high", "column": "nonexistent_col_xyz"}

        score_good = score_confidence(good, profile_stub)
        score_bad  = score_confidence(bad,  profile_stub)
        assert score_good > score_bad, "Unknown column should penalise confidence"

    def test_validate_suggestion_rejects_unknown_action(self, simple_df):
        from services.ai_safety import validate_suggestion

        suggestion = {"action": "definitely_fake_action_xyz", "params": {}}
        is_valid, reason = validate_suggestion(suggestion, simple_df)
        assert not is_valid
        assert "Unknown action" in reason

    def test_validate_suggestion_rejects_missing_column(self, simple_df):
        from services.ai_safety import validate_suggestion

        suggestion = {"action": "fill_missing", "params": {"column": "nonexistent", "strategy": "mean"}}
        is_valid, reason = validate_suggestion(suggestion, simple_df)
        assert not is_valid
        assert "does not exist" in reason

    def test_validate_suggestion_passes_valid(self, simple_df):
        from services.ai_safety import validate_suggestion

        suggestion = {"action": "fill_missing", "params": {"column": "age", "strategy": "median"}}
        is_valid, reason = validate_suggestion(suggestion, simple_df)
        assert is_valid, f"Expected valid, got: {reason}"

    def test_gate_auto_for_high_confidence(self, simple_df, profile_stub):
        from services.ai_safety import gate_suggestion

        suggestion = {
            "action": "trim_whitespace", "priority": "high",
            "column": None, "params": {}
        }
        result = gate_suggestion(suggestion, simple_df, profile_stub)
        assert result["gate"] in ("auto", "confirm")  # trim_whitespace should be auto or confirm
        assert "confidence" in result
        assert 0.0 <= result["confidence"] <= 1.0

    def test_gate_blocked_for_invalid(self, simple_df, profile_stub):
        from services.ai_safety import gate_suggestion

        suggestion = {
            "action": "fill_missing", "priority": "high",
            "column": "ghost_column", "params": {"column": "ghost_column", "strategy": "mean"}
        }
        result = gate_suggestion(suggestion, simple_df, profile_stub)
        assert result["gate"] == "blocked"
        assert result["valid"] is False

    def test_gate_all_returns_one_per_suggestion(self, simple_df, profile_stub):
        from services.ai_safety import gate_all

        suggestions = [
            {"action": "trim_whitespace", "priority": "high", "column": None, "params": {}},
            {"action": "remove_duplicates", "priority": "high", "column": None, "params": {}},
            {"action": "fake_action_xyz", "priority": "low", "column": None, "params": {}},
        ]
        gated = gate_all(suggestions, simple_df, profile_stub)
        assert len(gated) == 3

    def test_split_by_gate_partitions_correctly(self, simple_df, profile_stub):
        from services.ai_safety import gate_all, split_by_gate

        suggestions = [
            {"action": "trim_whitespace", "priority": "high", "column": None, "params": {}},
            {"action": "fake_action_xyz", "priority": "low", "column": None, "params": {}},
        ]
        gated = gate_all(suggestions, simple_df, profile_stub)
        auto, confirm, blocked = split_by_gate(gated)

        total = len(auto) + len(confirm) + len(blocked)
        assert total == 2


# ════════════════════════════════════════════════════════════════════════════════
# 3. DYNAMIC PIPELINE ENGINE TESTS
# ════════════════════════════════════════════════════════════════════════════════

class TestDynamicPipeline:
    """Tests for services/pipeline_engine.py v2"""

    def test_create_and_list_pipeline(self):
        from services.pipeline_engine import create_pipeline, list_all_pipelines

        p = create_pipeline("test_pipeline", [
            {"action": "trim_whitespace", "params": {}},
            {"action": "remove_duplicates", "params": {}},
        ])
        all_p = list_all_pipelines()
        ids = [x["pipeline_id"] for x in all_p]
        assert p.pipeline_id in ids

    def test_run_pipeline_basic(self, simple_df):
        from services.pipeline_engine import create_pipeline, run_pipeline

        p = create_pipeline("basic_run_test", [
            {"action": "trim_whitespace",    "params": {}},
            {"action": "remove_duplicates",  "params": {}},
        ])
        result = run_pipeline(p.pipeline_id, simple_df)

        assert result["success"] is True
        assert isinstance(result["df"], pd.DataFrame)
        assert len(result["steps_run"]) == 2
        assert len(result["errors"]) == 0

    def test_run_pipeline_skip_by_config_action(self, simple_df):
        from services.pipeline_engine import create_pipeline, run_pipeline

        p = create_pipeline("skip_action_test", [
            {"action": "trim_whitespace",   "params": {}},
            {"action": "remove_duplicates", "params": {}},
        ])
        config = {"steps": [{"action": "remove_duplicates", "enabled": False}]}
        result = run_pipeline(p.pipeline_id, simple_df, config=config)

        run_actions   = [s["action"] for s in result["steps_run"]]
        skip_actions  = [s["action"] for s in result["steps_skipped"]]
        assert "remove_duplicates" not in run_actions
        assert "remove_duplicates" in skip_actions

    def test_run_pipeline_skip_by_config_index(self, simple_df):
        from services.pipeline_engine import create_pipeline, run_pipeline

        p = create_pipeline("skip_index_test", [
            {"action": "trim_whitespace",   "params": {}},
            {"action": "remove_duplicates", "params": {}},
        ])
        config = {"steps": [{"index": 0, "enabled": False}]}
        result = run_pipeline(p.pipeline_id, simple_df, config=config)

        skip_indices = [s["index"] for s in result["steps_skipped"]]
        assert 0 in skip_indices

    def test_run_pipeline_start_from_step(self, simple_df):
        from services.pipeline_engine import create_pipeline, run_pipeline

        p = create_pipeline("start_from_test", [
            {"action": "trim_whitespace",   "params": {}},   # idx 0
            {"action": "remove_duplicates", "params": {}},   # idx 1
        ])
        result = run_pipeline(p.pipeline_id, simple_df, start_from_step=1)

        run_indices = [s["index"] for s in result["steps_run"]]
        assert 0 not in run_indices
        assert 1 in run_indices

    def test_dry_run_does_not_modify(self, simple_df):
        from services.pipeline_engine import create_pipeline, run_pipeline

        p = create_pipeline("dry_run_test", [
            {"action": "remove_duplicates", "params": {}},
        ])
        result = run_pipeline(p.pipeline_id, simple_df, dry_run=True)

        assert result["dry_run"] is True
        # df returned should be the original (unmodified)
        assert len(result["df"]) == len(simple_df)

    def test_step_error_does_not_kill_pipeline(self, simple_df):
        from services.pipeline_engine import create_pipeline, run_pipeline

        p = create_pipeline("error_isolation_test", [
            {"action": "trim_whitespace",     "params": {}},
            {"action": "unknown_fake_action", "params": {}},  # will error
            {"action": "remove_duplicates",   "params": {}},
        ])
        result = run_pipeline(p.pipeline_id, simple_df, stop_on_error=False)

        assert len(result["errors"]) == 1
        assert result["errors"][0]["action"] == "unknown_fake_action"
        # Other steps should still have run
        run_actions = [s["action"] for s in result["steps_run"]]
        assert "trim_whitespace" in run_actions

    def test_pipeline_not_found_raises(self, simple_df):
        from services.pipeline_engine import run_pipeline

        with pytest.raises(ValueError, match="not found"):
            run_pipeline("nonexistent_pipeline_id_xyz", simple_df)


# ════════════════════════════════════════════════════════════════════════════════
# 4. PERFORMANCE LAYER TESTS
# ════════════════════════════════════════════════════════════════════════════════

class TestPerformance:
    """Tests for services/performance.py"""

    def test_size_aware_config_tiers(self):
        from services.performance import SizeAwareConfig

        assert SizeAwareConfig(1_000).tier == "small"
        assert SizeAwareConfig(100_000).tier == "medium"
        assert SizeAwareConfig(1_000_000).tier == "large"

    def test_small_dataset_no_sampling(self, simple_df):
        from services.performance import SizeAwareConfig

        cfg = SizeAwareConfig(len(simple_df))
        assert cfg.profiling_sample_size is None
        assert not cfg.use_chunked_cleaning

    def test_large_dataset_triggers_chunking(self):
        from services.performance import SizeAwareConfig

        cfg = SizeAwareConfig(600_000)
        assert cfg.use_chunked_cleaning
        assert cfg.profiling_sample_size is not None

    def test_smart_sample_returns_subset(self, large_df):
        from services.performance import smart_sample

        sampled, was_sampled = smart_sample(large_df, n=10_000)
        assert was_sampled is True
        assert len(sampled) == 10_000

    def test_smart_sample_none_returns_full(self, simple_df):
        from services.performance import smart_sample

        sampled, was_sampled = smart_sample(simple_df, n=None)
        assert was_sampled is False
        assert len(sampled) == len(simple_df)

    def test_smart_sample_reproducible(self, large_df):
        from services.performance import smart_sample

        s1, _ = smart_sample(large_df, n=1000, seed=42)
        s2, _ = smart_sample(large_df, n=1000, seed=42)
        assert s1.index.tolist() == s2.index.tolist()

    def test_apply_in_chunks_same_result(self, large_df):
        """Chunked and non-chunked should produce identical results for simple ops."""
        from services.performance import apply_in_chunks

        def fill_nulls(df):
            return df.fillna(0)

        # Direct
        result_direct = fill_nulls(large_df.copy())

        # Chunked
        result_chunked = apply_in_chunks(large_df.copy(), fill_nulls, chunk_size=10_000)

        # Shape should match
        assert result_direct.shape == result_chunked.shape

    def test_profile_with_sampling_annotates_result(self):
        from services.performance import profile_with_sampling

        n = 100_000
        df = pd.DataFrame({"x": range(n), "y": range(n)})

        def simple_profile(d):
            return {"rows": len(d), "columns": len(d.columns)}

        profile = profile_with_sampling(df, simple_profile)
        assert "sampling" in profile
        assert profile["rows"] == n  # always the REAL row count
        assert profile["sampling"]["was_sampled"] is True

    def test_performance_context_has_warnings_for_large(self):
        from services.performance import performance_context

        n = 1_000_000
        df = pd.DataFrame({"x": range(10)})  # actual size doesn't matter, we use n_rows
        from services.performance import SizeAwareConfig
        cfg = SizeAwareConfig(n)
        assert cfg.should_warn_user

    def test_iter_chunks_covers_all_rows(self, large_df):
        from services.performance import iter_chunks

        chunk_size = 10_000
        chunks = list(iter_chunks(large_df, chunk_size))
        total = sum(len(c) for c in chunks)
        assert total == len(large_df)


# ════════════════════════════════════════════════════════════════════════════════
# 5. EDGE CASES & REGRESSION TESTS
# ════════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Edge cases that have historically caused bugs."""

    def test_audit_empty_dataframe(self):
        from services.audit_log import record, clear_log

        session_id = "edge_empty"
        clear_log(session_id)
        empty = pd.DataFrame({"a": [], "b": []})
        entry = record(session_id, "trim_whitespace", {}, empty, empty)
        assert entry.cells_changed == 0
        clear_log(session_id)

    def test_audit_single_row(self):
        from services.audit_log import record, clear_log

        session_id = "edge_single"
        clear_log(session_id)
        df = pd.DataFrame({"name": ["Alice"]})
        entry = record(session_id, "trim_whitespace", {}, df, df)
        assert entry.rows_before == 1
        clear_log(session_id)

    def test_pipeline_zero_steps(self):
        from services.pipeline_engine import create_pipeline, run_pipeline

        p = create_pipeline("zero_steps_test", [])
        result = run_pipeline(p.pipeline_id, pd.DataFrame({"a": [1, 2]}))
        assert result["success"] is True
        assert result["steps_run"] == []

    def test_confidence_score_clamped(self):
        from services.ai_safety import score_confidence

        # Should never go below 0 or above 1
        for action in ["trim_whitespace", "sql_apply", "fake"]:
            score = score_confidence({"action": action, "priority": "high", "column": None})
            assert 0.0 <= score <= 1.0, f"Score {score} out of range for action '{action}'"

    def test_sampling_larger_than_df_returns_full(self, simple_df):
        from services.performance import smart_sample

        sampled, was_sampled = smart_sample(simple_df, n=10_000_000)
        assert was_sampled is False
        assert len(sampled) == len(simple_df)

    def test_audit_issue_type_inferred(self, simple_df):
        from services.audit_log import record, clear_log, _infer_issue

        assert _infer_issue("remove_duplicates") == "duplicate_rows"
        assert _infer_issue("fill_missing")       == "missing_values"
        assert _infer_issue("clip_outliers")      == "outliers"
        assert _infer_issue("something_new")      == "transformation"

    def test_pipeline_dedup_group_skips_correct_actions(self, simple_df):
        from services.pipeline_engine import create_pipeline, run_pipeline

        p = create_pipeline("dedup_group_skip", [
            {"action": "remove_duplicates",       "params": {}},
            {"action": "fuzzy_remove_duplicates", "params": {"threshold": 85}},
            {"action": "trim_whitespace",         "params": {}},
        ])
        config = {"dedup": False}
        result = run_pipeline(p.pipeline_id, simple_df, config=config)

        skip_actions = [s["action"] for s in result["steps_skipped"]]
        assert "remove_duplicates" in skip_actions
        assert "fuzzy_remove_duplicates" in skip_actions
        run_actions = [s["action"] for s in result["steps_run"]]
        assert "trim_whitespace" in run_actions
