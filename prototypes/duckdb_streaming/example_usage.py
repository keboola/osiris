"""Example usage of the DuckDB streaming test harness.

This script demonstrates how to use the test harness components
to test DuckDB streaming operations.
"""

from pathlib import Path
import tempfile

from duckdb_helpers import (
    create_table_from_records,
    get_table_row_count,
    read_table_to_records,
)
from test_fixtures import (
    create_test_csv,
    get_expected_filtered_actors,
    get_sample_actors_data,
    get_sample_query_filter_by_age,
)
from test_harness import MockContext, setup_test_db


def example_basic_usage():
    """Example: Basic test harness usage."""
    print("=" * 60)
    print("Example 1: Basic Test Harness Usage")
    print("=" * 60)

    # Create temporary session directory
    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = Path(tmpdir)

        # Setup database
        db_path = setup_test_db(session_dir)
        print(f"Created database: {db_path}")

        # Create context
        ctx = MockContext(session_dir)

        # Get database connection
        con = ctx.get_db_connection()

        # Create test table
        actors = get_sample_actors_data()
        create_table_from_records(con, "actors", actors)
        print(f"Created table with {get_table_row_count(con, 'actors')} rows")

        # Log some metrics
        ctx.log_metric("rows_read", 10)
        ctx.log_metric("rows_written", 10)
        print(f"Logged metrics: {ctx.metrics}")

        # Close context
        ctx.close()

        # Cleanup is automatic when tempfile context exits
        print("Test complete\n")


def example_query_testing():
    """Example: Testing SQL queries."""
    print("=" * 60)
    print("Example 2: Testing SQL Queries")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = Path(tmpdir)
        setup_test_db(session_dir)

        ctx = MockContext(session_dir)
        con = ctx.get_db_connection()

        # Load sample data
        actors = get_sample_actors_data()
        create_table_from_records(con, "actors", actors)
        print(f"Loaded {len(actors)} actors into database")

        # Execute test query
        query = get_sample_query_filter_by_age()
        result = con.execute(query).fetchall()
        columns = [desc[0] for desc in con.description]
        result_dicts = [dict(zip(columns, row, strict=False)) for row in result]

        print(f"\nQuery returned {len(result_dicts)} rows:")
        for actor in result_dicts:
            print(f"  - {actor['name']}, age {actor['age']}")

        # Verify against expected results
        expected = get_expected_filtered_actors()
        if result_dicts == expected:
            print("\n✓ Query results match expected output")
        else:
            print("\n✗ Query results DO NOT match expected output")

        ctx.close()
        print()


def example_csv_to_duckdb():
    """Example: Loading CSV into DuckDB."""
    print("=" * 60)
    print("Example 3: CSV to DuckDB")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = Path(tmpdir)
        setup_test_db(session_dir)

        # Create test CSV
        csv_path = session_dir / "actors.csv"
        create_test_csv(csv_path)
        print(f"Created CSV file: {csv_path}")

        ctx = MockContext(session_dir)
        con = ctx.get_db_connection()

        # Load CSV into DuckDB
        con.execute(
            f"""
            CREATE TABLE actors AS
            SELECT * FROM read_csv_auto('{csv_path}')
        """
        )

        # Verify data
        count = get_table_row_count(con, "actors")
        print(f"Loaded {count} rows into actors table")

        # Read back a few rows
        records = read_table_to_records(con, "actors")
        print("\nFirst 3 actors:")
        for actor in records[:3]:
            print(f"  - {actor['name']}, age {actor['age']}")

        ctx.close()
        print()


def example_metrics_tracking():
    """Example: Tracking metrics during operations."""
    print("=" * 60)
    print("Example 4: Metrics Tracking")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = Path(tmpdir)
        setup_test_db(session_dir)

        ctx = MockContext(session_dir)

        # Simulate a multi-step pipeline
        print("Simulating pipeline execution...")

        # Step 1: Extract
        ctx.log_metric("rows_read", 100)
        ctx.log_metric("extract_duration_ms", 1234)
        print("  Step 1 (Extract): Read 100 rows in 1234ms")

        # Step 2: Transform
        ctx.log_metric("rows_read", 100)
        ctx.log_metric("rows_written", 95)
        ctx.log_metric("transform_duration_ms", 456)
        print("  Step 2 (Transform): Processed 100 rows -> 95 rows in 456ms")

        # Step 3: Load
        ctx.log_metric("rows_read", 95)
        ctx.log_metric("rows_written", 95)
        ctx.log_metric("load_duration_ms", 789)
        print("  Step 3 (Load): Wrote 95 rows in 789ms")

        # Analyze metrics
        print("\nMetrics summary:")
        print(f"  Total rows read: {sum(ctx.get_metric_values('rows_read'))}")
        print(f"  Final rows written: {ctx.get_last_metric_value('rows_written')}")
        print(
            f"  Total duration: {sum(ctx.get_metric_values('extract_duration_ms') + ctx.get_metric_values('transform_duration_ms') + ctx.get_metric_values('load_duration_ms'))}ms"
        )

        ctx.close()
        print()


if __name__ == "__main__":
    example_basic_usage()
    example_query_testing()
    example_csv_to_duckdb()
    example_metrics_tracking()

    print("=" * 60)
    print("All examples completed successfully!")
    print("=" * 60)
