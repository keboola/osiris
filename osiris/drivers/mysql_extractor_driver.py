"""MySQL extractor driver implementation."""

import logging
from typing import Any

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
        inputs: dict | None = None,  # noqa: ARG002
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

        # Create engine with separate URLs for logging and connection
        # Masked URL for logging/errors (SAFE to log)
        masked_url = f"mysql+pymysql://{user}:***@{host}:{port}/{database}"  # noqa: F841  # Reserved for stack traces
        # Real URL for connection ONLY (NEVER log this!)
        connection_url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
        engine = sa.create_engine(connection_url)

        try:
            # Test connection first
            logger.info(f"Testing MySQL connection for step {step_id}: {user}@{host}:{port}/{database}")
            with engine.connect() as conn:
                # Test basic connection
                result = conn.execute(sa.text("SELECT 1 as test"))
                result.fetchone()

            # Execute query
            logger.info(f"Executing MySQL query for step {step_id}")
            df = pd.read_sql_query(query, engine)

            # Log metrics
            rows_read = len(df)
            logger.info(f"Step {step_id}: Read {rows_read} rows from MySQL")

            if ctx and hasattr(ctx, "log_metric"):
                ctx.log_metric("rows_read", rows_read)

            return {"df": df}

        except sa.exc.OperationalError as e:
            # Connection/network issues - use generic error + masked debug logging
            error_msg = f"MySQL connection failed for step {step_id}"
            logger.error(error_msg)

            # Log details separately with masking
            from osiris.core.secrets_masking import mask_sensitive_string  # noqa: PLC0415

            logger.debug(f"Connection error details: {mask_sensitive_string(str(e))}")
            raise RuntimeError(error_msg) from e

        except sa.exc.ProgrammingError as e:
            # SQL syntax or permission issues
            error_msg = f"MySQL query failed: {str(e)}"
            logger.error(f"Step {step_id}: {error_msg}")
            raise RuntimeError(error_msg) from e

        except Exception as e:
            # Any other database errors
            error_msg = f"MySQL execution failed: {type(e).__name__}: {str(e)}"
            logger.error(f"Step {step_id}: {error_msg}")
            raise RuntimeError(error_msg) from e

        finally:
            engine.dispose()
