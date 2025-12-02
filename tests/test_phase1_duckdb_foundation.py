"""Phase 1: DuckDB Foundation - Smoke Tests

Tests that verify the foundation for DuckDB streaming is working:
- ExecutionContext.get_db_connection() works
- Database file is created in correct location
- Connection is cached properly
"""

from pathlib import Path
import tempfile

import duckdb
import pytest

from osiris.core.execution_adapter import ExecutionContext


def test_execution_context_get_db_connection():
    """Test that ExecutionContext.get_db_connection() creates database file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        # Create context
        context = ExecutionContext(
            session_id="test_session",
            base_path=base_path,
        )

        # Get connection
        conn = context.get_db_connection()

        # Verify connection is valid
        assert conn is not None
        assert isinstance(conn, duckdb.DuckDBPyConnection)

        # Verify database file exists
        db_path = base_path / "pipeline_data.duckdb"
        assert db_path.exists(), f"Database file not created at {db_path}"

        # Verify we can use the connection
        conn.execute("CREATE TABLE test_table (id INTEGER, name TEXT)")
        conn.execute("INSERT INTO test_table VALUES (1, 'test')")
        result = conn.execute("SELECT * FROM test_table").fetchone()
        assert result == (1, "test")


def test_connection_is_cached():
    """Test that get_db_connection() returns same instance on multiple calls."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        context = ExecutionContext(
            session_id="test_session",
            base_path=base_path,
        )

        # Get connection twice
        conn1 = context.get_db_connection()
        conn2 = context.get_db_connection()

        # Should be same object
        assert conn1 is conn2, "Connection not cached - got different instances"


def test_close_db_connection():
    """Test that close_db_connection() properly closes the connection."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        context = ExecutionContext(
            session_id="test_session",
            base_path=base_path,
        )

        # Get connection
        conn = context.get_db_connection()
        assert conn is not None

        # Close connection
        context.close_db_connection()

        # Verify connection is cleared
        assert context._db_connection is None

        # Getting connection again should create new one
        conn2 = context.get_db_connection()
        assert conn2 is not None
        assert conn2 is not conn  # Different instance


def test_database_path_location():
    """Test that database is created in correct location."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        context = ExecutionContext(
            session_id="test_session_123",
            base_path=base_path,
        )

        conn = context.get_db_connection()

        # Verify path
        expected_path = base_path / "pipeline_data.duckdb"
        assert expected_path.exists()

        # Verify it's a valid DuckDB file
        # Open it independently to verify
        independent_conn = duckdb.connect(str(expected_path))
        # If we can connect, it's valid
        independent_conn.close()


def test_multiple_tables_in_shared_database():
    """Test that multiple steps can create tables in shared database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)

        context = ExecutionContext(
            session_id="test_session",
            base_path=base_path,
        )

        conn = context.get_db_connection()

        # Simulate multiple pipeline steps creating tables
        conn.execute("CREATE TABLE extract_actors (id INTEGER, name TEXT)")
        conn.execute("CREATE TABLE transform_actors (id INTEGER, name TEXT, age INTEGER)")
        conn.execute("CREATE TABLE filter_actors (id INTEGER, name TEXT)")

        # Verify all tables exist
        tables = conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main'").fetchall()
        table_names = {t[0] for t in tables}

        assert "extract_actors" in table_names
        assert "transform_actors" in table_names
        assert "filter_actors" in table_names


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
