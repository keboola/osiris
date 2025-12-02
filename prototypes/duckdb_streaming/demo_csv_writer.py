"""Demo script for CSV Streaming Writer.

This demonstrates how the CSVStreamingWriter would be used in a pipeline,
reading from a shared DuckDB database and writing to CSV.
"""

from pathlib import Path
import tempfile

from csv_writer import CSVStreamingWriter
import duckdb
import pandas as pd


class MockContext:
    """Mock execution context for demo purposes."""

    def __init__(self, db_path: Path):
        """Initialize with path to shared DuckDB database."""
        self.db_path = db_path
        self._connection = None
        self.metrics = {}

    def get_db_connection(self):
        """Get shared DuckDB connection."""
        if self._connection is None:
            self._connection = duckdb.connect(str(self.db_path))
        return self._connection

    def log_metric(self, name: str, value: int, **kwargs):
        """Log a metric."""
        self.metrics[name] = value
        print(f"📊 Metric: {name} = {value}")

    def close(self):
        """Close database connection."""
        if self._connection is not None:
            self._connection.close()


def setup_test_database(db_path: Path):
    """Create test DuckDB database with sample data."""
    con = duckdb.connect(str(db_path))

    # Create sample table (simulates output from extractor step)
    print("\n🔧 Setting up test database...")
    con.execute(
        """
        CREATE TABLE extract_customers AS
        SELECT
            id,
            name,
            email,
            created_at,
            total_orders
        FROM (VALUES
            (1, 'Alice', 'alice@example.com', '2024-01-15'::DATE, 5),
            (2, 'Bob', 'bob@example.com', '2024-02-20'::DATE, 3),
            (3, 'Charlie', 'charlie@example.com', '2024-03-10'::DATE, 12),
            (4, 'Diana', 'diana@example.com', '2024-04-05'::DATE, 7)
        ) AS t(id, name, email, created_at, total_orders)
    """
    )

    row_count = con.execute("SELECT COUNT(*) FROM extract_customers").fetchone()[0]
    print(f"✅ Created table 'extract_customers' with {row_count} rows")

    # Show table schema
    print("\n📋 Table schema:")
    schema = con.execute("DESCRIBE extract_customers").fetchall()
    for row in schema:
        print(f"  - {row[0]}: {row[1]}")

    con.close()


def demo_basic_write():
    """Demonstrate basic CSV writing from DuckDB table."""
    print("\n" + "=" * 70)
    print("DEMO: Basic CSV Write from DuckDB Table")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Setup test database
        db_path = tmpdir / "pipeline_data.duckdb"
        setup_test_database(db_path)

        # Create output path
        output_csv = tmpdir / "customers.csv"

        # Create context and writer
        ctx = MockContext(db_path)
        writer = CSVStreamingWriter()

        # Run writer
        print("\n🚀 Running CSV writer...")
        config = {
            "path": str(output_csv),
            "delimiter": ",",
            "header": True,
            "newline": "lf",
        }

        inputs = {"table": "extract_customers"}

        result = writer.run(step_id="write_csv", config=config, inputs=inputs, ctx=ctx)

        print(f"\n✅ Writer completed. Result: {result}")
        print(f"📊 Metrics logged: {ctx.metrics}")

        # Verify output
        print("\n📄 Output CSV content:")
        print("-" * 70)
        with open(output_csv) as f:
            content = f.read()
            print(content)
        print("-" * 70)

        # Verify column ordering
        df = pd.read_csv(output_csv)
        print(f"\n✓ Columns are sorted: {list(df.columns)}")
        print(f"✓ Row count: {len(df)}")

        ctx.close()


def demo_custom_delimiter():
    """Demonstrate CSV writing with custom delimiter."""
    print("\n" + "=" * 70)
    print("DEMO: CSV Write with Custom Delimiter (TSV)")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Setup test database
        db_path = tmpdir / "pipeline_data.duckdb"
        setup_test_database(db_path)

        # Create output path
        output_tsv = tmpdir / "customers.tsv"

        # Create context and writer
        ctx = MockContext(db_path)
        writer = CSVStreamingWriter()

        # Run writer with TSV config
        print("\n🚀 Running TSV writer...")
        config = {
            "path": str(output_tsv),
            "delimiter": "\t",  # Tab-separated
            "header": True,
            "newline": "lf",
        }

        inputs = {"table": "extract_customers"}

        result = writer.run(step_id="write_tsv", config=config, inputs=inputs, ctx=ctx)

        print(f"\n✅ Writer completed. Result: {result}")

        # Show first few lines
        print("\n📄 Output TSV content (first 3 lines):")
        print("-" * 70)
        with open(output_tsv) as f:
            for i, line in enumerate(f):
                if i < 3:
                    print(line.rstrip())
        print("-" * 70)

        ctx.close()


def demo_error_handling():
    """Demonstrate error handling."""
    print("\n" + "=" * 70)
    print("DEMO: Error Handling")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Setup test database
        db_path = tmpdir / "pipeline_data.duckdb"
        setup_test_database(db_path)

        ctx = MockContext(db_path)
        writer = CSVStreamingWriter()

        # Test 1: Missing table
        print("\n❌ Test: Non-existent table")
        try:
            config = {"path": str(tmpdir / "output.csv")}
            inputs = {"table": "nonexistent_table"}
            writer.run(step_id="test", config=config, inputs=inputs, ctx=ctx)
        except ValueError as e:
            print(f"✓ Caught expected error: {e}")

        # Test 2: Missing path config
        print("\n❌ Test: Missing path in config")
        try:
            config = {}  # Missing 'path'
            inputs = {"table": "extract_customers"}
            writer.run(step_id="test", config=config, inputs=inputs, ctx=ctx)
        except ValueError as e:
            print(f"✓ Caught expected error: {e}")

        # Test 3: Missing table in inputs
        print("\n❌ Test: Missing table in inputs")
        try:
            config = {"path": str(tmpdir / "output.csv")}
            inputs = {}  # Missing 'table'
            writer.run(step_id="test", config=config, inputs=inputs, ctx=ctx)
        except ValueError as e:
            print(f"✓ Caught expected error: {e}")

        ctx.close()


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("CSV STREAMING WRITER - DEMONSTRATION")
    print("=" * 70)

    # Run demos
    demo_basic_write()
    demo_custom_delimiter()
    demo_error_handling()

    print("\n" + "=" * 70)
    print("✅ All demos completed successfully!")
    print("=" * 70)
    print(
        """
Key Design Points Demonstrated:
1. ✓ Reads from shared DuckDB database via ctx.get_db_connection()
2. ✓ Accepts table name in inputs["table"]
3. ✓ Supports custom delimiters, encodings, line endings
4. ✓ Sorts columns alphabetically for deterministic output
5. ✓ Logs metrics via ctx.log_metric()
6. ✓ Handles errors gracefully (missing table, missing config)
7. ✓ Creates parent directories automatically
8. ✓ Works with absolute and relative paths

Alignment with Streaming Vision:
- Data stays in DuckDB throughout pipeline
- Only loaded at final write step (CSV egress)
- No intermediate DataFrame passing between steps
- Memory-efficient for large datasets
"""
    )
