#!/usr/bin/env python3
"""
DuckDB Sanity Check Script
Verifies DuckDB is available and functional in the execution environment.
No Osiris imports - standalone script for E2B environment validation.
"""

import sys
import tempfile
from pathlib import Path


def test_duckdb_import():
    """Test that DuckDB can be imported."""
    try:
        import duckdb

        print(f"✓ DuckDB import successful (version: {duckdb.__version__})")
        return True
    except ImportError as e:
        print(f"✗ DuckDB import failed: {e}")
        return False


def test_simple_query():
    """Test basic SQL execution."""
    try:
        import duckdb

        # Create in-memory connection
        conn = duckdb.connect(":memory:")

        # Test SELECT 1
        result = conn.execute("SELECT 1 as test_col").fetchone()
        assert result[0] == 1
        print("✓ Simple SELECT query successful")

        # Test generate_series (used in tests)
        result = conn.execute("SELECT COUNT(*) FROM generate_series(1, 10)").fetchone()
        assert result[0] == 10
        print("✓ generate_series function works")

        conn.close()
        return True
    except Exception as e:
        print(f"✗ Query execution failed: {e}")
        return False


def test_dataframe_interop():
    """Test pandas DataFrame interoperability."""
    try:
        import duckdb
        import pandas as pd

        # Create test DataFrame
        df = pd.DataFrame({"id": [1, 2, 3], "name": ["Alice", "Bob", "Charlie"], "score": [100, 200, 150]})

        # Query DataFrame directly
        conn = duckdb.connect(":memory:")
        result = conn.execute("SELECT AVG(score) FROM df").fetchone()
        assert result[0] == 150.0
        print("✓ DataFrame query successful")

        # Test input_df pattern (used in transforms)
        input_df = df.copy()  # noqa: F841 # DuckDB accesses it via variable name
        result = conn.execute("SELECT COUNT(*) FROM input_df").fetchone()
        assert result[0] == 3
        print("✓ input_df pattern works")

        conn.close()
        return True
    except ImportError:
        print("⚠ pandas not available - skipping DataFrame tests")
        return True  # Not critical for basic functionality
    except Exception as e:
        print(f"✗ DataFrame interop failed: {e}")
        return False


def test_parquet_io():
    """Test Parquet file operations."""
    try:
        import duckdb

        with tempfile.TemporaryDirectory() as tmpdir:
            parquet_path = Path(tmpdir) / "test.parquet"

            # Create test data and write to Parquet
            conn = duckdb.connect(":memory:")
            # Using parameterized queries would be ideal but DuckDB COPY doesn't support it
            # This is safe as parquet_path is from tempfile, not user input
            conn.execute(
                f"""
                COPY (SELECT i as id FROM generate_series(1, 5) as t(i))
                TO '{parquet_path}' (FORMAT PARQUET)
            """  # nosec B608 - path from tempfile.TemporaryDirectory
            )

            # Read back from Parquet
            result = conn.execute(
                f"SELECT COUNT(*) FROM read_parquet('{parquet_path}')"  # nosec B608 - path from tempfile
            ).fetchone()
            assert result[0] == 5
            print("✓ Parquet read/write successful")

            conn.close()
            return True
    except Exception as e:
        print(f"✗ Parquet operations failed: {e}")
        return False


def test_case_statement():
    """Test CASE statement (used in transform tests)."""
    try:
        import duckdb

        conn = duckdb.connect(":memory:")
        result = conn.execute(
            """
            SELECT
                CASE
                    WHEN 500 >= 500 THEN 'high'
                    WHEN 500 >= 300 THEN 'medium'
                    ELSE 'low'
                END as category
        """
        ).fetchone()
        assert result[0] == "high"
        print("✓ CASE statement works")

        conn.close()
        return True
    except Exception as e:
        print(f"✗ CASE statement failed: {e}")
        return False


def main():
    """Run all sanity checks."""
    print("DuckDB E2B Environment Sanity Check")
    print("=" * 40)

    tests = [
        test_duckdb_import,
        test_simple_query,
        test_dataframe_interop,
        test_parquet_io,
        test_case_statement,
    ]

    results = []
    for test_func in tests:
        print(f"\nRunning: {test_func.__name__}")
        success = test_func()
        results.append(success)

    print("\n" + "=" * 40)
    passed = sum(results)
    total = len(results)

    if passed == total:
        print(f"✓ All {total} tests passed - DuckDB is ready!")
        sys.exit(0)
    else:
        print(f"⚠ {passed}/{total} tests passed - check failures above")
        sys.exit(1)


if __name__ == "__main__":
    main()
