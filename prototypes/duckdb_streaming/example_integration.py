"""
Example: CSV Streaming Extractor Integration with Osiris Context

Demonstrates how the CSV extractor would integrate with actual Osiris runtime context.
"""

import logging
from pathlib import Path

from csv_extractor import CSVStreamingExtractor
import duckdb


class OsirisContextSimulator:
    """
    Simulates Osiris runtime context with DuckDB support.

    This demonstrates the expected context interface:
    - get_db_connection() -> DuckDB connection
    - log_metric(name, value, **kwargs) -> logs to metrics.jsonl
    - output_dir -> Path to step's output directory
    """

    def __init__(self, db_path=":memory:", output_base="/tmp/osiris_output"):
        self.conn = duckdb.connect(db_path)
        self.output_base = Path(output_base)
        self.output_base.mkdir(parents=True, exist_ok=True)
        self.metrics = []

    def get_db_connection(self):
        """Returns DuckDB connection for data operations."""
        return self.conn

    def log_metric(self, name, value, **kwargs):
        """Logs metric to metrics.jsonl (simulated)."""
        metric_entry = {
            "name": name,
            "value": value,
            **kwargs,
        }
        self.metrics.append(metric_entry)
        print(f"METRIC: {name}={value}")

        # In real Osiris, this would write to metrics.jsonl
        metrics_file = self.output_base / "metrics.jsonl"
        with open(metrics_file, "a") as f:
            import json

            f.write(json.dumps(metric_entry) + "\n")

    @property
    def output_dir(self):
        """Returns output directory for step artifacts."""
        return self.output_base


def example_simple_extraction():
    """Example 1: Simple CSV extraction."""
    print("\n" + "=" * 70)
    print("EXAMPLE 1: Simple CSV Extraction")
    print("=" * 70)

    # Create sample CSV
    csv_path = Path("/tmp/customers.csv")
    csv_path.write_text(
        """customer_id,name,email,country
1,John Doe,john@example.com,USA
2,Jane Smith,jane@example.com,UK
3,Bob Johnson,bob@example.com,Canada
4,Alice Williams,alice@example.com,USA
5,Charlie Brown,charlie@example.com,Australia
"""
    )

    # Setup context
    ctx = OsirisContextSimulator(output_base="/tmp/osiris_example1")

    # Run extractor
    extractor = CSVStreamingExtractor()
    result = extractor.run(
        step_id="extract_customers",
        config={
            "path": str(csv_path),
            "batch_size": 2,  # Small batch for demonstration
        },
        inputs={},
        ctx=ctx,
    )

    print(f"\nResult: {result}")
    print(f"Metrics logged: {len(ctx.metrics)}")

    # Query the data
    print("\nQuerying extracted data:")
    df = ctx.conn.execute(
        """
        SELECT country, COUNT(*) as customer_count
        FROM extract_customers
        GROUP BY country
        ORDER BY customer_count DESC
    """
    ).fetchdf()
    print(df)

    # Cleanup
    csv_path.unlink()


def example_large_file_processing():
    """Example 2: Processing large CSV file in chunks."""
    print("\n" + "=" * 70)
    print("EXAMPLE 2: Large File Processing (100K rows)")
    print("=" * 70)

    # Generate large CSV
    import random

    csv_path = Path("/tmp/transactions_large.csv")
    print("Generating CSV with 100,000 rows...")

    with open(csv_path, "w") as f:
        f.write("transaction_id,user_id,amount,category,date\n")
        categories = ["food", "transport", "entertainment", "utilities", "shopping"]
        for i in range(1, 100001):
            user_id = random.randint(1, 1000)
            amount = round(random.uniform(5, 500), 2)
            category = random.choice(categories)
            date = f"2024-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
            f.write(f"{i},{user_id},{amount},{category},{date}\n")

    print(f"CSV file size: {csv_path.stat().st_size / 1024 / 1024:.2f} MB")

    # Setup context
    ctx = OsirisContextSimulator(output_base="/tmp/osiris_example2")

    # Run extractor with large batch size for efficiency
    import time

    start_time = time.time()

    extractor = CSVStreamingExtractor()
    result = extractor.run(
        step_id="extract_transactions",
        config={
            "path": str(csv_path),
            "batch_size": 5000,  # Larger batches for better performance
        },
        inputs={},
        ctx=ctx,
    )

    elapsed = time.time() - start_time

    print(f"\nResult: {result}")
    print(f"Processing time: {elapsed:.2f} seconds")
    print(f"Rows per second: {result['rows'] / elapsed:.0f}")

    # Run analytics query
    print("\nRunning analytics query:")
    df = ctx.conn.execute(
        """
        SELECT
            category,
            COUNT(*) as transaction_count,
            ROUND(SUM(amount), 2) as total_amount,
            ROUND(AVG(amount), 2) as avg_amount
        FROM extract_transactions
        GROUP BY category
        ORDER BY total_amount DESC
    """
    ).fetchdf()
    print(df)

    # Cleanup
    csv_path.unlink()


def example_pipeline_chaining():
    """Example 3: Chaining extractors (simulated multi-step pipeline)."""
    print("\n" + "=" * 70)
    print("EXAMPLE 3: Pipeline Chaining (Multiple Extractions)")
    print("=" * 70)

    # Create two CSV files
    customers_csv = Path("/tmp/pipeline_customers.csv")
    customers_csv.write_text(
        """customer_id,name,country
1,Alice,USA
2,Bob,UK
3,Charlie,USA
"""
    )

    orders_csv = Path("/tmp/pipeline_orders.csv")
    orders_csv.write_text(
        """order_id,customer_id,amount
101,1,50.00
102,1,75.00
103,2,100.00
104,3,25.00
105,3,150.00
"""
    )

    # Setup shared context
    ctx = OsirisContextSimulator(output_base="/tmp/osiris_example3")

    # Extract customers
    print("\nStep 1: Extracting customers...")
    extractor = CSVStreamingExtractor()
    result1 = extractor.run(
        step_id="extract_customers",
        config={"path": str(customers_csv)},
        inputs={},
        ctx=ctx,
    )
    print(f"  Extracted {result1['rows']} customers")

    # Extract orders
    print("\nStep 2: Extracting orders...")
    result2 = extractor.run(
        step_id="extract_orders",
        config={"path": str(orders_csv)},
        inputs={},
        ctx=ctx,
    )
    print(f"  Extracted {result2['rows']} orders")

    # Join and analyze
    print("\nStep 3: Joining data and analyzing...")
    df = ctx.conn.execute(
        """
        SELECT
            c.name,
            c.country,
            COUNT(o.order_id) as order_count,
            ROUND(SUM(o.amount), 2) as total_spent
        FROM extract_customers c
        LEFT JOIN extract_orders o ON c.customer_id = o.customer_id
        GROUP BY c.name, c.country
        ORDER BY total_spent DESC
    """
    ).fetchdf()
    print(df)

    # Cleanup
    customers_csv.unlink()
    orders_csv.unlink()


def example_error_handling():
    """Example 4: Error handling and validation."""
    print("\n" + "=" * 70)
    print("EXAMPLE 4: Error Handling")
    print("=" * 70)

    ctx = OsirisContextSimulator(output_base="/tmp/osiris_example4")
    extractor = CSVStreamingExtractor()

    # Test 1: Missing file
    print("\nTest 1: Missing file")
    try:
        extractor.run(
            step_id="test1",
            config={"path": "/nonexistent/file.csv"},
            inputs={},
            ctx=ctx,
        )
    except ValueError as e:
        print(f"  ✓ Caught expected error: {e}")

    # Test 2: Missing config
    print("\nTest 2: Missing 'path' config")
    try:
        extractor.run(
            step_id="test2",
            config={},  # Missing path
            inputs={},
            ctx=ctx,
        )
    except ValueError as e:
        print(f"  ✓ Caught expected error: {e}")

    # Test 3: Empty file (should succeed with 0 rows)
    print("\nTest 3: Empty CSV file")
    empty_csv = Path("/tmp/empty.csv")
    empty_csv.write_text("")

    result = extractor.run(
        step_id="test3",
        config={"path": str(empty_csv)},
        inputs={},
        ctx=ctx,
    )
    print(f"  ✓ Empty file handled: {result}")

    empty_csv.unlink()


if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("\n" + "=" * 70)
    print("CSV STREAMING EXTRACTOR - INTEGRATION EXAMPLES")
    print("=" * 70)

    # Run examples
    example_simple_extraction()
    example_large_file_processing()
    example_pipeline_chaining()
    example_error_handling()

    print("\n" + "=" * 70)
    print("ALL EXAMPLES COMPLETED SUCCESSFULLY")
    print("=" * 70)
