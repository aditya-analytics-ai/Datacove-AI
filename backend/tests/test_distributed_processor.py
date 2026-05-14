"""
Unit tests for services/distributed_processor.py

Run with:  pytest tests/test_distributed_processor.py -v
"""

import pytest
import pandas as pd
import numpy as np
from services.distributed_processor import (
    DistributedProcessingEngine,
    DistributedConfig,
    ProcessingMode,
    process_large_dataframe,
    get_recommended_config,
)


@pytest.fixture
def small_df():
    return pd.DataFrame(
        {
            "name": ["Alice", "Bob", "Charlie"],
            "age": [25, 30, 35],
            "salary": [50000.0, 60000.0, 70000.0],
        }
    )


@pytest.fixture
def medium_df():
    np.random.seed(42)
    n = 10000
    return pd.DataFrame(
        {
            "value": np.random.randn(n),
            "category": np.random.choice(["A", "B", "C"], n),
            "amount": np.random.uniform(0, 1000, n),
        }
    )


class TestDistributedConfig:
    def test_default_config(self):
        config = DistributedConfig()
        assert config.mode == ProcessingMode.PANDAS
        assert config.n_workers == 4
        assert config.threads_per_worker == 2

    def test_custom_config(self):
        config = DistributedConfig(
            mode=ProcessingMode.DASK_LOCAL,
            n_workers=8,
            memory_limit_per_worker="8GB",
        )
        assert config.mode == ProcessingMode.DASK_LOCAL
        assert config.n_workers == 8
        assert config.memory_limit_per_worker == "8GB"


class TestDetectMode:
    def test_small_dataset_pandas(self, small_df):
        engine = DistributedProcessingEngine()
        mode = engine.detect_mode(len(small_df))
        assert mode == ProcessingMode.PANDAS

    def test_medium_dataset_dask(self, medium_df):
        engine = DistributedProcessingEngine()
        mode = engine.detect_mode(len(medium_df))
        # If Dask is available, should be DASK_LOCAL for medium datasets
        # If not, should be PANDAS
        assert mode in [ProcessingMode.PANDAS, ProcessingMode.DASK_LOCAL]


class TestProcessDataFrame:
    def test_process_pandas_small(self, small_df):
        engine = DistributedProcessingEngine()
        result = engine.process_dataframe(
            small_df,
            [{"action": "trim_whitespace", "params": {"columns": ["name"]}}],
            mode=ProcessingMode.PANDAS,
        )
        assert result.success is True
        assert result.rows_total == 3
        assert result.partitions_completed >= 1

    def test_process_returns_result(self, small_df):
        engine = DistributedProcessingEngine()
        result = engine.process_dataframe(
            small_df,
            [],
            mode=ProcessingMode.PANDAS,
        )
        assert result.success is True
        assert result.mode == ProcessingMode.PANDAS


class TestProcessLargeDataFrame:
    def test_convenience_function(self, small_df):
        result = process_large_dataframe(
            small_df,
            [],
            mode="pandas",
        )
        assert result.success is True


class TestRecommendedConfig:
    def test_small_dataset(self):
        config = get_recommended_config(1000)
        assert config.mode == ProcessingMode.PANDAS

    def test_large_with_cluster(self):
        config = get_recommended_config(5_000_000_000, has_dask_cluster=True)
        assert config.mode == ProcessingMode.DASK_CLUSTER

    def test_medium_local(self):
        config = get_recommended_config(50_000_000, available_memory_gb=16)
        # Falls back to streaming if Dask cluster not available
        assert config.mode in [ProcessingMode.DASK_LOCAL, ProcessingMode.STREAMING]


class TestProfileDistributed:
    def test_profile_returns_stats(self, small_df):
        engine = DistributedProcessingEngine()
        stats = engine.profile_distributed(small_df)
        assert stats["row_count"] == 3
        assert stats["column_count"] == 3
        assert "memory_mb" in stats
        assert "recommended_mode" in stats
