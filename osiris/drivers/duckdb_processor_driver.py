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
            inputs: Optional inputs with 'df' key containing input DataFrame
            ctx: Execution context for logging metrics

        Returns:
            Dictionary with 'df' key containing transformed DataFrame
        """
        # Get SQL query from config
        query = config.get("query", "").strip()
        if not query:
            raise ValueError(f"Step {step_id}: Missing 'query' in config")

        # Get input DataFrame if provided
        input_df = None
        if inputs and "df" in inputs:
            input_df = inputs["df"]
            if not isinstance(input_df, pd.DataFrame):
                raise TypeError(f"Step {step_id}: Input 'df' must be a pandas DataFrame")

        try:
            # Create in-memory DuckDB connection
            conn = duckdb.connect(":memory:")

            # Register input DataFrame if provided
            if input_df is not None:
                conn.register("input_df", input_df)
                self.logger.debug(f"Step {step_id}: Registered input_df with {len(input_df)} rows")

            # Execute the SQL query
            self.logger.debug(f"Step {step_id}: Executing DuckDB query")
            result = conn.execute(query).fetchdf()

            # Close connection
            conn.close()

            # Log metrics
            if hasattr(ctx, "log_metric"):
                ctx.log_metric("rows_read", len(input_df) if input_df is not None else 0)
                ctx.log_metric("rows_written", len(result))

            self.logger.info(
                f"Step {step_id}: Transformed {len(input_df) if input_df is not None else 0} rows -> {len(result)} rows"
            )

            return {"df": result}

        except Exception as e:
            self.logger.error(f"Step {step_id}: DuckDB execution failed: {e}")
            self.logger.error(f"Query was: {query[:500]}...")  # Log first 500 chars of query
            raise RuntimeError(f"DuckDB transformation failed: {e}") from e
