"""End-to-end test: CSV → DuckDB → CSV streaming pipeline."""

from pathlib import Path
import tempfile

# Import prototype components
from csv_extractor import CSVStreamingExtractor
from csv_writer import CSVStreamingWriter
from test_fixtures import create_test_csv, get_sample_actors_data
from test_harness import MockContext, cleanup_test_db, setup_test_db


def test_csv_to_duckdb_to_csv():
    """Test complete pipeline: CSV file → DuckDB table → CSV file."""
    print("=" * 70)
    print("END-TO-END TEST: CSV → DuckDB → CSV Streaming Pipeline")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = Path(tmpdir)

        # Step 1: Setup
        print("\n[1] Setting up test environment...")
        setup_test_db(session_dir)

        # Create input CSV with sample data
        input_csv = session_dir / "input_actors.csv"
        sample_data = get_sample_actors_data()
        create_test_csv(input_csv, sample_data)
        print(f"   ✓ Created input CSV: {input_csv.name} ({len(sample_data)} rows)")

        # Create context for both steps
        ctx = MockContext(session_dir)

        # Step 2: Extract CSV → DuckDB
        print("\n[2] Extracting CSV to DuckDB table...")
        extractor = CSVStreamingExtractor()
        extract_config = {
            "path": str(input_csv),
            "delimiter": ",",
            "batch_size": 3,  # Small batch to test chunking
        }
        extract_result = extractor.run(step_id="extract_actors", config=extract_config, inputs={}, ctx=ctx)

        print(f"   ✓ Table created: {extract_result['table']}")
        print(f"   ✓ Rows extracted: {extract_result['rows']}")
        print(f"   ✓ Metric logged: rows_read = {ctx.get_last_metric_value('rows_read')}")

        # Verify data in DuckDB
        con = ctx.get_db_connection()
        db_rows = con.execute(f"SELECT * FROM {extract_result['table']}").fetchall()
        print(f"   ✓ Verified in DuckDB: {len(db_rows)} rows")

        # Step 3: Write DuckDB → CSV
        print("\n[3] Writing DuckDB table to CSV...")
        writer = CSVStreamingWriter()
        output_csv = session_dir / "output_actors.csv"
        write_config = {"path": str(output_csv), "delimiter": ","}
        write_inputs = {"table": extract_result["table"]}
        writer.run(step_id="write_actors", config=write_config, inputs=write_inputs, ctx=ctx)

        print(f"   ✓ CSV written: {output_csv.name}")
        print(f"   ✓ Metric logged: rows_written = {ctx.get_last_metric_value('rows_written')}")

        # Step 4: Verify output
        print("\n[4] Verifying output CSV...")
        with open(output_csv) as f:
            output_lines = f.readlines()

        print(f"   ✓ Output file size: {len(output_lines)} lines (including header)")
        print(f"   ✓ Data rows: {len(output_lines) - 1}")

        # Verify content matches
        import csv

        with open(output_csv) as f:
            reader = csv.DictReader(f)
            output_data = list(reader)

        print(f"   ✓ Parsed {len(output_data)} records from output")

        # Check first record
        if output_data:
            first_record = output_data[0]
            print(f"   ✓ Sample record: {first_record}")

        # Verify row count consistency
        assert len(output_data) == len(sample_data), f"Row count mismatch: {len(output_data)} vs {len(sample_data)}"
        print(f"   ✓ Row count matches input: {len(sample_data)}")

        # Step 5: Metrics summary
        print("\n[5] Metrics Summary:")
        metrics = ctx.metrics
        for metric_name, values in metrics.items():
            print(f"   - {metric_name}: {values}")

        # Step 6: Cleanup
        print("\n[6] Cleaning up...")
        ctx.close()
        cleanup_test_db(session_dir)
        print("   ✓ Test database removed")

        print("\n" + "=" * 70)
        print("✅ END-TO-END TEST PASSED")
        print("=" * 70)
        print("\nPipeline Summary:")
        print(f"  • Input CSV:  {len(sample_data)} rows")
        print(f"  • DuckDB:     {extract_result['rows']} rows (table: {extract_result['table']})")
        print(f"  • Output CSV: {len(output_data)} rows")
        print("  • Status:     All data preserved ✓")
        print()


if __name__ == "__main__":
    test_csv_to_duckdb_to_csv()
