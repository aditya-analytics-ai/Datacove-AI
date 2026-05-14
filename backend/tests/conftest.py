"""
pytest conftest - shared fixtures and test configuration.
"""
import pytest
import pandas as pd


@pytest.fixture
def sample_df():
    """A minimal clean DataFrame for quick tests."""
    return pd.DataFrame({
        "name":   ["Alice", "Bob", "Charlie"],
        "age":    [25, 30, 35],
        "salary": [50000.0, 60000.0, 70000.0],
    })


@pytest.fixture
def messy_df():
    """A DataFrame with common data quality issues."""
    return pd.DataFrame({
        "name":   ["  Alice ", "bob", "BOB", "Alice", None],
        "age":    [25, 30, 30, 25, -1],
        "email":  ["alice@test.com", "notanemail", "bob@ok.com", "alice@test.com", ""],
        "city":   ["New York", "london", "London", "new york", "Chicago"],
        "salary": [50000, 60000, 60000, 50000, 9999999],
    })
