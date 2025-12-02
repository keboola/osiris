"""Tests for DuckDB processor with multiple input tables."""

import duckdb
import pandas as pd
import pytest
from pathlib import Path

from osiris.drivers.duckdb_processor_driver import DuckDBProcessorDriver


class MockContext:
    """Mock context for testing with DuckDB connection."""

    def __init__(self, tmpdir):
        self.base_path = Path(tmpdir)
        self._db_connection = None
        self.metrics = {}

    def get_db_connection(self):
        """Get or create DuckDB connection."""
        if self._db_connection is None:
            db_path = self.base_path / "pipeline_data.duckdb"
            self._db_connection = duckdb.connect(str(db_path))
        return self._db_connection

    def log_metric(self, name: str, value):
        """Log a metric."""
        self.metrics[name] = value

    def cleanup(self):
        """Close DuckDB connection."""
        if self._db_connection is not None:
            self._db_connection.close()
            self._db_connection = None


@pytest.fixture
def duckdb_driver():
    """Create DuckDB driver instance."""
    return DuckDBProcessorDriver()


@pytest.fixture
def mock_ctx(tmp_path):
    """Create mock context with DuckDB connection."""
    ctx = MockContext(tmp_path)
    yield ctx
    ctx.cleanup()


@pytest.fixture
def multi_input_tables(mock_ctx):
    """Create multiple input tables in DuckDB."""
    conn = mock_ctx.get_db_connection()

    # Create movies table
    df_movies = pd.DataFrame({"id": [1, 2, 3], "title": ["Movie A", "Movie B", "Movie C"], "budget": [100, 200, 150]})
    conn.execute("CREATE TABLE extract_movies AS SELECT * FROM df_movies")

    # Create reviews table
    df_reviews = pd.DataFrame({"movie_id": [1, 1, 2, 3, 3], "rating": [5, 4, 3, 5, 4]})
    conn.execute("CREATE TABLE extract_reviews AS SELECT * FROM df_reviews")

    return {"table": "extract_movies", "table2": "extract_reviews"}


def test_duckdb_registers_multiple_tables(duckdb_driver, multi_input_tables, mock_ctx):
    """DuckDB should work with multiple input tables."""
    config = {
        "query": """
            SELECT
                m.title,
                AVG(r.rating) as avg_rating
            FROM extract_reviews r
            JOIN extract_movies m ON r.movie_id = m.id
            GROUP BY m.title
            ORDER BY avg_rating DESC
        """
    }

    result = duckdb_driver.run(step_id="test_calc", config=config, inputs=multi_input_tables, ctx=mock_ctx)

    # Verify new API returns table name and row count
    assert "table" in result
    assert "rows" in result
    assert result["table"] == "test_calc"
    assert result["rows"] == 3  # 3 movies

    # Verify data in the result table
    conn = mock_ctx.get_db_connection()
    df = conn.execute(f"SELECT * FROM {result['table']} ORDER BY avg_rating DESC").fetchdf()
    assert len(df) == 3
    assert "avg_rating" in df.columns


def test_duckdb_allows_data_generation(duckdb_driver, mock_ctx):
    """DuckDB allows empty inputs for data generation queries (e.g., SELECT 1).

    This test verifies that DuckDB can handle data generation queries without
    requiring input tables. This is useful for generating synthetic data.
    """
    config = {"query": "SELECT 1 as value"}

    result = duckdb_driver.run(
        step_id="test_step", config=config, inputs={}, ctx=mock_ctx  # Empty inputs - allowed for data generation
    )

    # Should successfully generate data without input tables
    assert "table" in result
    assert "rows" in result
    assert result["table"] == "test_step"
    assert result["rows"] == 1

    # Verify data in the result table
    conn = mock_ctx.get_db_connection()
    df = conn.execute(f"SELECT * FROM {result['table']}").fetchdf()
    assert len(df) == 1
    assert list(df.columns) == ["value"]


def test_duckdb_works_with_table_reference(duckdb_driver, mock_ctx):
    """DuckDB should work with table references from inputs."""
    conn = mock_ctx.get_db_connection()

    # Create a test table
    df = pd.DataFrame({"col": [1, 2, 3]})
    conn.execute("CREATE TABLE test_table AS SELECT * FROM df")

    inputs = {
        "table": "test_table",
        "metadata": {"source": "test"},  # Should be ignored
        "upstream_id": {"other": "data"},  # Should be ignored
    }

    config = {"query": "SELECT * FROM test_table"}

    result = duckdb_driver.run(step_id="test_step", config=config, inputs=inputs, ctx=mock_ctx)

    assert "table" in result
    assert "rows" in result
    assert result["rows"] == 3

    # Verify data in the result table
    df_result = conn.execute(f"SELECT * FROM {result['table']}").fetchdf()
    assert len(df_result) == 3


def test_duckdb_table_not_found_error(duckdb_driver, multi_input_tables, mock_ctx):
    """DuckDB should fail with clear error if SQL references non-existent table."""
    config = {"query": "SELECT * FROM nonexistent_table"}

    with pytest.raises(RuntimeError, match="DuckDB transformation failed"):
        duckdb_driver.run(step_id="test_step", config=config, inputs=multi_input_tables, ctx=mock_ctx)
