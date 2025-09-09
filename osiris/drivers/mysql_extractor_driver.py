"""MySQL extractor driver implementation."""

import logging
from typing import Any, Optional

import pandas as pd
import sqlalchemy as sa

logger = logging.getLogger(__name__)


class MySQLExtractorDriver:
    """Driver for extracting data from MySQL databases."""

    def run(
        self,
        *,
        step_id: str,
        config: dict,
        inputs: Optional[dict] = None,  # noqa: ARG002
        ctx: Any = None,
    ) -> dict:
        """Extract data from MySQL using SQL query.

        Args:
            step_id: Step identifier
            config: Must contain 'query' and 'resolved_connection'
            inputs: Not used for extractors
            ctx: Execution context for logging metrics

        Returns:
            {"df": DataFrame} with query results
        """
        # Get query
        query = config.get("query")
        if not query:
            raise ValueError(f"Step {step_id}: 'query' is required in config")

        # Get connection details
        conn_info = config.get("resolved_connection", {})
        if not conn_info:
            raise ValueError(f"Step {step_id}: 'resolved_connection' is required")

        # Build connection URL
        host = conn_info.get("host", "localhost")
        port = conn_info.get("port", 3306)
        database = conn_info.get("database")
        user = conn_info.get("user", "root")
        password = conn_info.get("password", "")

        if not database:
            raise ValueError(f"Step {step_id}: 'database' is required in connection")

        # Create engine
        connection_url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
        engine = sa.create_engine(connection_url)

        try:
            # Execute query
            logger.info(f"Executing MySQL query for step {step_id}")
            df = pd.read_sql_query(query, engine)

            # Log metrics
            rows_read = len(df)
            logger.info(f"Step {step_id}: Read {rows_read} rows from MySQL")

            if ctx and hasattr(ctx, "log_metric"):
                ctx.log_metric("rows_read", rows_read)

            return {"df": df}

        finally:
            engine.dispose()
