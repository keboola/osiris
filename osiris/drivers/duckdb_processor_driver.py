"""DuckDB processor driver for SQL transformations."""

import logging
from typing import Any


class DuckDBProcessorDriver:
    """DuckDB processor driver for executing SQL transformations on tables."""

    def __init__(self):
        """Initialize the DuckDB processor driver."""
        self.logger = logging.getLogger(__name__)

    def run(
        self,
        step_id: str,
        config: dict[str, Any],
        inputs: dict[str, Any] | None,
        ctx: Any,
    ) -> dict[str, Any]:
        """Execute a DuckDB SQL transformation on input tables.

        Args:
            step_id: Step identifier (used as output table name)
            config: Configuration containing 'query' SQL string
            inputs: Dictionary containing input table names (e.g., {"table": "extract_step"})
            ctx: Execution context for logging metrics and database connection

        Returns:
            Dictionary with 'table' and 'rows' keys: {"table": step_id, "rows": count}
        """
        # Get SQL query from config
        query = config.get("query", "").strip()
        if not query:
            raise ValueError(f"Step {step_id}: Missing 'query' in config")

        # Get DuckDB connection from context
        if not ctx or not hasattr(ctx, "get_db_connection"):
            raise RuntimeError(f"Step {step_id}: Context must provide get_db_connection() method")

        conn = ctx.get_db_connection()
        table_name = step_id

        try:
            # Log input tables (for debugging)
            if inputs:
                input_table_names = [v for k, v in inputs.items() if k in {"table", "tables"}]
                if input_table_names:
                    self.logger.info(f"Step {step_id}: Input tables: {input_table_names}")
                else:
                    self.logger.info(f"Step {step_id}: No input tables specified (data generation query)")
            else:
                self.logger.info(f"Step {step_id}: No inputs (data generation query)")

            # Execute the SQL query and store result in new table
            self.logger.debug(f"Step {step_id}: Executing DuckDB query")
            self.logger.debug(f"Query: {query[:500]}{'...' if len(query) > 500 else ''}")

            # Create table from query result
            conn.execute(f"CREATE TABLE {table_name} AS {query}")

            # Count rows in the result table
            row_count_result = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
            row_count = row_count_result[0] if row_count_result else 0

            # Log metrics
            if hasattr(ctx, "log_metric"):
                ctx.log_metric("rows_written", row_count)

            self.logger.info(f"Step {step_id}: Created table '{table_name}' with {row_count} rows")

            return {"table": table_name, "rows": row_count}

        except Exception as e:
            self.logger.error(f"Step {step_id}: DuckDB execution failed: {e}")
            self.logger.error(f"Query was: {query[:500]}...")  # Log first 500 chars of query
            raise RuntimeError(f"DuckDB transformation failed: {e}") from e
