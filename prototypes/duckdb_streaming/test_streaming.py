"""
Comprehensive tests for CSV Streaming Extractor.

Tests streaming behavior, error handling, and edge cases.
"""

import logging
from pathlib import Path
import tempfile

from csv_extractor import CSVStreamingExtractor
import duckdb
import sys


class MockContext:
    """Mock context for testing."""

    def __init__(self, conn):
        self.conn = conn
        self.metrics = {}

    def get_db_connection(self):
        return self.conn

    def log_metric(self, name, value, **kwargs):
        self.metrics[name] = value
        print(f"  METRIC: {name} = {value}")


def test_basic_streaming():
    """Test basic CSV extraction with multiple chunks."""
    print("\n=== Test 1: Basic Streaming ===")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        # Create CSV with 10 rows
        f.write("id,name,value\n")
        for i in range(1, 11):
            f.write(f"{i},Item{i},{i * 10}\n")
        csv_path = f.name

    try:
        conn = duckdb.connect(":memory:")
        ctx = MockContext(conn)
        extractor = CSVStreamingExtractor()

        result = extractor.run(
            step_id="test_basic",
            config={
                "path": csv_path,
                "batch_size": 3,  # Will create 4 chunks (3+3+3+1)
            },
            inputs={},
            ctx=ctx,
        )

        assert result["table"] == "test_basic"
        assert result["rows"] == 10
        assert ctx.metrics["rows_read"] == 10

        # Verify data integrity
        df = conn.execute("SELECT * FROM test_basic ORDER BY id").fetchdf()
        assert len(df) == 10
        assert df["id"].tolist() == list(range(1, 11))
        assert df["value"].tolist() == [i * 10 for i in range(1, 11)]

        print("  ✓ Basic streaming works correctly")

    finally:
        Path(csv_path).unlink()


def test_large_file_simulation():
    """Test with larger dataset to verify memory efficiency."""
    print("\n=== Test 2: Large File Simulation ===")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        # Create CSV with 10,000 rows
        f.write("id,category,amount,description\n")
        for i in range(1, 10001):
            f.write(f"{i},cat{i % 10},{i * 1.5},Description for item {i}\n")
        csv_path = f.name

    try:
        conn = duckdb.connect(":memory:")
        ctx = MockContext(conn)
        extractor = CSVStreamingExtractor()

        result = extractor.run(
            step_id="test_large",
            config={
                "path": csv_path,
                "batch_size": 1000,  # 10 chunks
            },
            inputs={},
            ctx=ctx,
        )

        assert result["rows"] == 10000
        assert ctx.metrics["rows_read"] == 10000

        # Verify sample of data
        df = conn.execute("SELECT COUNT(*) as cnt FROM test_large").fetchdf()
        assert df["cnt"][0] == 10000

        # Check aggregations work correctly
        df = conn.execute("SELECT SUM(amount) as total FROM test_large").fetchdf()
        expected_sum = sum(i * 1.5 for i in range(1, 10001))
        assert abs(df["total"][0] - expected_sum) < 0.01

        print("  ✓ Large file (10,000 rows) processed correctly")

    finally:
        Path(csv_path).unlink()


def test_empty_file():
    """Test handling of empty CSV files."""
    print("\n=== Test 3: Empty File ===")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        # Empty file
        csv_path = f.name

    try:
        conn = duckdb.connect(":memory:")
        ctx = MockContext(conn)
        extractor = CSVStreamingExtractor()

        result = extractor.run(
            step_id="test_empty",
            config={"path": csv_path},
            inputs={},
            ctx=ctx,
        )

        assert result["rows"] == 0
        assert ctx.metrics["rows_read"] == 0

        # Table should exist but be empty
        df = conn.execute("SELECT * FROM test_empty").fetchdf()
        assert len(df) == 0

        print("  ✓ Empty file handled correctly")

    finally:
        Path(csv_path).unlink()


def test_csv_with_headers_only():
    """Test CSV with headers but no data rows."""
    print("\n=== Test 4: Headers Only ===")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("id,name,value\n")  # Just headers
        csv_path = f.name

    try:
        conn = duckdb.connect(":memory:")
        ctx = MockContext(conn)
        extractor = CSVStreamingExtractor()

        result = extractor.run(
            step_id="test_headers",
            config={"path": csv_path},
            inputs={},
            ctx=ctx,
        )

        assert result["rows"] == 0
        assert ctx.metrics["rows_read"] == 0

        print("  ✓ Headers-only file handled correctly")

    finally:
        Path(csv_path).unlink()


def test_custom_delimiter():
    """Test CSV with custom delimiter."""
    print("\n=== Test 5: Custom Delimiter ===")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        # Tab-separated values
        f.write("id\tname\tvalue\n")
        f.write("1\tAlice\t100\n")
        f.write("2\tBob\t200\n")
        csv_path = f.name

    try:
        conn = duckdb.connect(":memory:")
        ctx = MockContext(conn)
        extractor = CSVStreamingExtractor()

        result = extractor.run(
            step_id="test_delim",
            config={
                "path": csv_path,
                "delimiter": "\t",
            },
            inputs={},
            ctx=ctx,
        )

        assert result["rows"] == 2

        df = conn.execute("SELECT * FROM test_delim ORDER BY id").fetchdf()
        assert df["name"].tolist() == ["Alice", "Bob"]
        assert df["value"].tolist() == [100, 200]

        print("  ✓ Custom delimiter works correctly")

    finally:
        Path(csv_path).unlink()


def test_missing_file():
    """Test error handling for missing file."""
    print("\n=== Test 6: Missing File ===")

    conn = duckdb.connect(":memory:")
    ctx = MockContext(conn)
    extractor = CSVStreamingExtractor()

    try:
        extractor.run(
            step_id="test_missing",
            config={"path": "/nonexistent/file.csv"},
            inputs={},
            ctx=ctx,
        )
        raise AssertionError("Should have raised ValueError")
    except ValueError as e:
        assert "not found" in str(e)
        print(f"  ✓ Missing file error: {e}")


def test_missing_path_config():
    """Test error handling for missing 'path' in config."""
    print("\n=== Test 7: Missing Config ===")

    conn = duckdb.connect(":memory:")
    ctx = MockContext(conn)
    extractor = CSVStreamingExtractor()

    try:
        extractor.run(
            step_id="test_no_path",
            config={},  # Missing 'path'
            inputs={},
            ctx=ctx,
        )
        raise AssertionError("Should have raised ValueError")
    except ValueError as e:
        assert "path" in str(e).lower()
        assert "required" in str(e).lower()
        print(f"  ✓ Missing config error: {e}")


def test_data_types():
    """Test that data types are preserved correctly."""
    print("\n=== Test 8: Data Types ===")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        # Mixed data types
        f.write("id,name,price,active,created_at\n")
        f.write("1,Product A,19.99,true,2024-01-01\n")
        f.write("2,Product B,29.50,false,2024-01-02\n")
        csv_path = f.name

    try:
        conn = duckdb.connect(":memory:")
        ctx = MockContext(conn)
        extractor = CSVStreamingExtractor()

        extractor.run(
            step_id="test_types",
            config={"path": csv_path},
            inputs={},
            ctx=ctx,
        )

        # Check column types inferred by DuckDB
        schema = conn.execute("DESCRIBE test_types").fetchdf()
        print(f"  Schema:\n{schema}")

        df = conn.execute("SELECT * FROM test_types").fetchdf()
        assert len(df) == 2
        assert df["name"].tolist() == ["Product A", "Product B"]

        print("  ✓ Data types handled correctly")

    finally:
        Path(csv_path).unlink()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("=" * 60)
    print("CSV STREAMING EXTRACTOR - COMPREHENSIVE TESTS")
    print("=" * 60)

    tests = [
        test_basic_streaming,
        test_large_file_simulation,
        test_empty_file,
        test_csv_with_headers_only,
        test_custom_delimiter,
        test_missing_file,
        test_missing_path_config,
        test_data_types,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            import traceback

            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)
