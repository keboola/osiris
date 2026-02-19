"""
CSV Streaming Extractor Prototype

Reads CSV files in chunks and streams data into DuckDB tables.
Designed to handle large files without loading entire dataset into memory.
"""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


class CSVStreamingExtractor:
    """
    Streams CSV data into DuckDB table chunk by chunk.

    Design:
    - Reads CSV in batches using pandas read_csv with chunksize
    - Creates DuckDB table from first chunk (schema inference)
    - Streams remaining chunks using INSERT statements
    - Never loads full dataset into memory
    """

    def run(self, *, step_id: str, config: dict, inputs: dict, ctx) -> dict:
        """
        Reads CSV file and streams data to DuckDB table.

        Args:
            step_id: Unique step identifier (used as table name)
            config: Configuration dictionary
                - path: Path to CSV file (required)
                - delimiter: CSV delimiter (default: ",")
                - batch_size: Number of rows per batch (default: 1000)
            inputs: Input data (not used for extractors)
            ctx: Runtime context with log_metric() and get_db_connection()

        Returns:
            dict: {"table": step_id, "rows": total_row_count}

        Raises:
            ValueError: If required config keys missing or file doesn't exist
        """
        # Validate config
        if "path" not in config:
            raise ValueError(f"Step {step_id}: 'path' is required in config")

        csv_path = Path(config["path"])
        if not csv_path.exists():
            raise ValueError(f"Step {step_id}: CSV file not found: {csv_path}")

        delimiter = config.get("delimiter", ",")
        batch_size = config.get("batch_size", 1000)

        logger.info(
            f"[{step_id}] Starting CSV streaming extraction: "
            f"file={csv_path}, delimiter='{delimiter}', batch_size={batch_size}"
        )

        # Get DuckDB connection
        conn = ctx.get_db_connection()
        table_name = step_id

        total_rows = 0
        first_chunk = True

        try:
            # Read CSV in chunks
            chunk_iterator = pd.read_csv(
                csv_path,
                delimiter=delimiter,
                chunksize=batch_size,
                # Preserve data types, let DuckDB infer schema
                low_memory=False,
            )

            for chunk_num, chunk_df in enumerate(chunk_iterator, start=1):
                if chunk_df.empty:
                    logger.warning(f"[{step_id}] Chunk {chunk_num} is empty, skipping")
                    continue

                chunk_rows = len(chunk_df)

                if first_chunk:
                    # First chunk: create table and insert data
                    logger.info(
                        f"[{step_id}] Creating table '{table_name}' from first chunk "
                        f"({chunk_rows} rows, {len(chunk_df.columns)} columns)"
                    )

                    # DuckDB can create table directly from DataFrame
                    conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM chunk_df")
                    first_chunk = False

                    logger.info(f"[{step_id}] Table created with schema: {list(chunk_df.columns)}")
                else:
                    # Subsequent chunks: insert into existing table
                    logger.debug(f"[{step_id}] Inserting chunk {chunk_num} ({chunk_rows} rows)")
                    conn.execute(f"INSERT INTO {table_name} SELECT * FROM chunk_df")

                total_rows += chunk_rows

                # Log progress every 10 chunks
                if chunk_num % 10 == 0:
                    logger.info(f"[{step_id}] Progress: {total_rows} rows processed")

            # Handle empty CSV file
            if first_chunk:
                logger.warning(f"[{step_id}] CSV file is empty, creating empty table")
                # Create empty table with single column as placeholder
                conn.execute(f"CREATE TABLE {table_name} (placeholder VARCHAR)")
                conn.execute(f"DELETE FROM {table_name}")  # Ensure it's empty

            # Log final metrics
            ctx.log_metric("rows_read", total_rows)

            logger.info(f"[{step_id}] CSV streaming completed: " f"table={table_name}, total_rows={total_rows}")

            return {
                "table": table_name,
                "rows": total_rows,
            }

        except pd.errors.EmptyDataError:
            logger.warning(f"[{step_id}] CSV file is empty: {csv_path}")
            # Create empty table
            conn.execute(f"CREATE TABLE {table_name} (placeholder VARCHAR)")
            conn.execute(f"DELETE FROM {table_name}")
            ctx.log_metric("rows_read", 0)
            return {"table": table_name, "rows": 0}

        except Exception as e:
            logger.error(f"[{step_id}] CSV streaming failed: {e}")
            raise


# Example usage for testing
if __name__ == "__main__":
    import duckdb

    # Mock context for standalone testing
    class MockContext:
        def __init__(self, conn):
            self.conn = conn
            self.metrics = {}

        def get_db_connection(self):
            return self.conn

        def log_metric(self, name, value, **kwargs):
            self.metrics[name] = value
            print(f"METRIC: {name} = {value}")

    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    # Create test CSV
    test_csv = Path("/tmp/test_streaming.csv")
    test_csv.write_text("id,name,age\n1,Alice,30\n2,Bob,25\n3,Charlie,35\n4,Diana,28\n")

    # Test extraction
    conn = duckdb.connect(":memory:")
    ctx = MockContext(conn)

    extractor = CSVStreamingExtractor()
    result = extractor.run(
        step_id="extract_users",
        config={
            "path": str(test_csv),
            "delimiter": ",",
            "batch_size": 2,  # Small batch to test chunking
        },
        inputs={},
        ctx=ctx,
    )

    print(f"\nResult: {result}")
    print(f"Metrics: {ctx.metrics}")

    # Verify data
    print("\nTable contents:")
    print(conn.execute("SELECT * FROM extract_users").fetchdf())

    # Cleanup
    test_csv.unlink()
