"""Mock DuckDB processor driver for testing."""

from typing import Any

import pandas as pd


class DuckDBProcessorDriver:
    """Mock DuckDB processor driver for testing parity between local and E2B execution."""

    def run(
        self,
        step_id: str,
        config: dict[str, Any],
        inputs: dict[str, Any] | None,
        ctx: Any,
    ) -> dict[str, Any]:
        """Execute the mock DuckDB processor step.

        This is a simplified mock that generates test data or transforms input data
        based on the query pattern in the config.
        """
        query = config.get("query", "")

        # Simple pattern matching for test queries
        if "generate_series" in query:
            # Extract the range from the query
            import re

            match = re.search(r"generate_series\((\d+),\s*(\d+)\)", query)
            if match:
                start = int(match.group(1))
                end = int(match.group(2))
                # Generate simple test data
                df = pd.DataFrame({"id": range(start, end + 1)})
            else:
                # Default test data
                df = pd.DataFrame({"id": [1, 2, 3, 4, 5]})

            # Check if query has more complex SELECT
            if "as id," in query.lower():
                # Parse for additional columns
                if "'user_' || i as username" in query:
                    df["username"] = ["user_" + str(i) for i in df["id"]]
                if "i * 100 as score" in query:
                    df["score"] = df["id"] * 100

        elif "input_df" in query and inputs and "df" in inputs:
            # Transform existing data
            df = inputs["df"].copy()

            # Apply simple transformations based on query patterns
            if "CASE" in query and "score" in df.columns:
                # Add category based on score
                df["category"] = df["score"].apply(lambda x: "high" if x >= 500 else ("medium" if x >= 300 else "low"))

            if "ORDER BY" in query and "ORDER BY id" in query:
                # Sort by id if specified
                df = df.sort_values("id").reset_index(drop=True)

        else:
            # Default: pass through or create empty DataFrame
            df = inputs["df"].copy() if inputs and "df" in inputs else pd.DataFrame()

        # Log metrics
        if hasattr(ctx, "log_metric"):
            ctx.log_metric("rows_written", len(df))

        return {"df": df}
