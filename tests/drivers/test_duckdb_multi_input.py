"""Tests for DuckDB processor with multiple input tables."""

import pandas as pd
import pytest

from osiris.drivers.duckdb_processor_driver import DuckDBProcessorDriver


@pytest.fixture
def duckdb_driver():
    """Create DuckDB driver instance."""
    return DuckDBProcessorDriver()


@pytest.fixture
def multi_input_dataframes():
    """Create multiple input DataFrames."""
    df_movies = pd.DataFrame({"id": [1, 2, 3], "title": ["Movie A", "Movie B", "Movie C"], "budget": [100, 200, 150]})
    df_reviews = pd.DataFrame({"movie_id": [1, 1, 2, 3, 3], "rating": [5, 4, 3, 5, 4]})
    return {"df_extract_movies": df_movies, "df_extract_reviews": df_reviews}


def test_duckdb_registers_multiple_tables(duckdb_driver, multi_input_dataframes, tmp_path):
    """DuckDB should register all df_* inputs as separate tables."""
    config = {
        "query": """
            SELECT
                m.title,
                AVG(r.rating) as avg_rating
            FROM df_extract_reviews r
            JOIN df_extract_movies m ON r.movie_id = m.id
            GROUP BY m.title
            ORDER BY avg_rating DESC
        """
    }

    result = duckdb_driver.run(step_id="test-calc", config=config, inputs=multi_input_dataframes, ctx=None)

    assert "df" in result
    assert len(result["df"]) == 3  # 3 movies
    assert "avg_rating" in result["df"].columns


def test_duckdb_fails_with_no_dataframes(duckdb_driver, tmp_path):
    """DuckDB now allows empty inputs for data generation queries (e.g., SELECT 1).

    This test verifies that DuckDB can handle data generation queries without
    requiring input DataFrames. This is useful for generating synthetic data.
    """
    config = {"query": "SELECT 1 as value"}

    result = duckdb_driver.run(
        step_id="test-step", config=config, inputs={}, ctx=None  # Empty inputs - now allowed for data generation
    )

    # Should successfully generate data without input tables
    assert "df" in result
    assert len(result["df"]) == 1
    assert list(result["df"].columns) == ["value"]


def test_duckdb_ignores_non_df_keys(duckdb_driver, tmp_path):
    """DuckDB should only register keys starting with df_."""
    df = pd.DataFrame({"col": [1, 2, 3]})
    inputs = {
        "df_test": df,
        "metadata": {"source": "test"},  # Should be ignored
        "upstream_id": {"other": "data"},  # Should be ignored
    }

    config = {"query": "SELECT * FROM df_test"}

    result = duckdb_driver.run(step_id="test-step", config=config, inputs=inputs, ctx=None)

    assert "df" in result
    assert len(result["df"]) == 3


def test_duckdb_table_not_found_error(duckdb_driver, multi_input_dataframes, tmp_path):
    """DuckDB should fail with clear error if SQL references non-existent table."""
    config = {"query": "SELECT * FROM df_nonexistent"}

    with pytest.raises(RuntimeError, match="DuckDB transformation failed"):
        duckdb_driver.run(step_id="test-step", config=config, inputs=multi_input_dataframes, ctx=None)
