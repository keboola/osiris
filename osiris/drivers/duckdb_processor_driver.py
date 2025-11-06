"""DuckDB processor driver for SQL transformations."""

import logging
from typing import Any

import duckdb
import pandas as pd


class DuckDBProcessorDriver:
    """DuckDB processor driver for executing SQL transformations on DataFrames."""

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
        """Execute a DuckDB SQL transformation.

        Args:
            step_id: Step identifier
            config: Configuration containing 'query' SQL string
            inputs: Optional inputs with keys starting with 'df_' containing input DataFrames
            ctx: Execution context for logging metrics

        Returns:
            Dictionary with 'df' key containing transformed DataFrame
        """
        # Get SQL query from config
        query = config.get("query", "").strip()
        if not query:
            raise ValueError(f"Step {step_id}: Missing 'query' in config")

        try:
            # Create in-memory DuckDB connection
            conn = duckdb.connect(":memory:")

            # Register all DataFrames from inputs dict
            registered = []
            if inputs:
                for key, value in inputs.items():
                    if key.startswith("df_") and isinstance(value, pd.DataFrame):
                        conn.register(key, value)
                        registered.append(key)
                        self.logger.debug(f"Step {step_id}: Registered table '{key}' with {len(value)} rows")

            # Allow empty inputs for data generation queries (e.g., generate_series)
            if registered:
                self.logger.info(f"Step {step_id}: Registered {len(registered)} tables: {registered}")
            else:
                self.logger.info(f"Step {step_id}: No input tables (data generation query)")

            # Execute the SQL query
            self.logger.debug(f"Step {step_id}: Executing DuckDB query")
            result = conn.execute(query).fetchdf()

            # Close connection
            conn.close()

            # Log metrics
            total_rows_read = sum(len(inputs[key]) for key in registered) if registered else 0
            if hasattr(ctx, "log_metric"):
                ctx.log_metric("rows_read", total_rows_read)
                ctx.log_metric("rows_written", len(result))

            self.logger.info(f"Step {step_id}: Transformed {total_rows_read} rows -> {len(result)} rows")

            return {"df": result}

        except Exception as e:
            self.logger.error(f"Step {step_id}: DuckDB execution failed: {e}")
            self.logger.error(f"Query was: {query[:500]}...")  # Log first 500 chars of query
            raise RuntimeError(f"DuckDB transformation failed: {e}") from e
