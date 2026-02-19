"""Filesystem CSV writer driver implementation.

This driver writes data from DuckDB tables to CSV files, enabling streaming
pipelines that keep data in the database until final egress.
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FilesystemCsvWriterDriver:
    """Driver for writing DuckDB tables to CSV files."""

    def run(self, *, step_id: str, config: dict, inputs: dict | None = None, ctx: Any = None) -> dict:
        """Write DuckDB table to CSV file.

        Args:
            step_id: Step identifier
            config: Must contain 'path' and optional CSV settings:
                - path: Output CSV file path (required)
                - delimiter: CSV delimiter (default: ",")
                - encoding: File encoding (default: "utf-8")
                - header: Include header row (default: True)
                - newline: Line ending - "lf", "crlf", "cr" (default: "lf")
            inputs: Must contain 'table' key with name of DuckDB table to read from
            ctx: Execution context with get_db_connection() and log_metric()

        Returns:
            {} (empty dict for writers)
        """
        # Validate inputs
        if not inputs or "table" not in inputs:
            raise ValueError(f"Step {step_id}: FilesystemCsvWriterDriver requires 'table' in inputs")

        table_name = inputs["table"]

        # Get configuration
        file_path = config.get("path")
        if not file_path:
            raise ValueError(f"Step {step_id}: 'path' is required in config")

        # CSV options with defaults
        delimiter = config.get("delimiter", ",")
        encoding = config.get("encoding", "utf-8")
        header = config.get("header", True)
        newline_config = config.get("newline", "lf")

        # Resolve output path
        output_path = Path(file_path)
        if not output_path.is_absolute():
            # Make relative to current working directory
            output_path = Path.cwd() / output_path

        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Get shared DuckDB connection from context
        con = ctx.get_db_connection()

        # Verify table exists
        table_check = con.execute(
            f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = '{table_name}'"
        ).fetchone()[0]

        if table_check == 0:
            raise ValueError(f"Step {step_id}: Table '{table_name}' does not exist in DuckDB")

        # Get row count for metrics
        row_count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        logger.info(f"Step {step_id}: Reading {row_count} rows from table '{table_name}'")

        # Get column names for sorting
        # This is a small query - just column metadata, not data
        columns_result = con.execute(
            f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}' ORDER BY column_name"
        ).fetchall()
        sorted_columns = [col[0] for col in columns_result]

        logger.debug(f"Step {step_id}: Sorted columns: {sorted_columns}")

        # Map newline config to line terminator
        newline_map = {"lf": "\n", "crlf": "\r\n", "cr": "\r"}
        lineterminator = newline_map.get(newline_config, "\n")

        # Build SELECT with sorted columns
        # Note: We read into DataFrame for final write to ensure:
        # 1. Alphabetical column ordering (deterministic output)
        # 2. Custom line terminators (DuckDB COPY has limited support)
        # This is acceptable as writers are egress points where data leaves the streaming pipeline
        columns_sql = ", ".join([f'"{col}"' for col in sorted_columns])
        query = f"SELECT {columns_sql} FROM {table_name}"

        logger.debug(f"Step {step_id}: Executing query: {query[:100]}...")
        df = con.execute(query).df()

        # Write CSV with pandas for full control over formatting
        logger.info(f"Step {step_id}: Writing {len(df)} rows to {output_path}")

        df.to_csv(
            output_path,
            sep=delimiter,
            encoding=encoding,
            header=header,
            index=False,
            lineterminator=lineterminator,
        )

        # Log metrics
        logger.info(f"Step {step_id}: Successfully wrote {row_count} rows to {output_path}")

        if ctx and hasattr(ctx, "log_metric"):
            ctx.log_metric("rows_written", row_count)

        return {}
