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
        """Extract data from MySQL and stream to DuckDB.

        Args:
            step_id: Step identifier (used as table name)
            config: Must contain 'query' and 'resolved_connection'.
                   May include 'batch_size' for streaming (default: 10000)
            inputs: Not used for extractors
            ctx: Execution context for logging metrics and database connection

        Returns:
            {"table": step_id, "rows": total_row_count}
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

        # Get batch size for streaming
        batch_size = config.get("batch_size", 10000)

        # Create engine with separate URLs for logging and connection
        # Masked URL for logging/errors (SAFE to log)
        masked_url = f"mysql+pymysql://{user}:***@{host}:{port}/{database}"  # noqa: F841  # Reserved for stack traces
        # Real URL for connection ONLY (NEVER log this!)
        connection_url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
        engine = sa.create_engine(connection_url)

        # Get DuckDB connection from context
        if not ctx or not hasattr(ctx, "get_db_connection"):
            raise RuntimeError(f"Step {step_id}: Context must provide get_db_connection() method")

        duckdb_conn = ctx.get_db_connection()
        table_name = step_id

        try:
            # Test connection first
            logger.info(f"[{step_id}] Testing MySQL connection: {user}@{host}:{port}/{database}")
            with engine.connect() as conn:
                # Test basic connection
                result = conn.execute(sa.text("SELECT 1 as test"))
                result.fetchone()

            # Execute query with streaming
            logger.info(
                f"[{step_id}] Starting MySQL streaming extraction: " f"database={database}, batch_size={batch_size}"
            )

            total_rows = 0
            first_batch = True

            # Use SQLAlchemy execution with yield_per for streaming
            with engine.connect() as conn:
                result = conn.execution_options(yield_per=batch_size).execute(sa.text(query))

                # Process results in batches
                batch_num = 0
                while True:
                    # Fetch batch_size rows
                    rows = result.fetchmany(batch_size)
                    if not rows:
                        break

                    batch_num += 1

                    # Convert to DataFrame
                    batch_df = pd.DataFrame(rows, columns=result.keys())

                    if batch_df.empty:
                        logger.warning(f"[{step_id}] Batch {batch_num} is empty, skipping")
                        continue

                    batch_rows = len(batch_df)

                    if first_batch:
                        # First batch: create table and insert data
                        logger.info(
                            f"[{step_id}] Creating table '{table_name}' from first batch "
                            f"({batch_rows} rows, {len(batch_df.columns)} columns)"
                        )

                        # DuckDB can create table directly from DataFrame
                        duckdb_conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM batch_df")
                        first_batch = False

                        logger.info(f"[{step_id}] Table created with schema: {list(batch_df.columns)}")
                    else:
                        # Subsequent batches: insert into existing table
                        logger.debug(f"[{step_id}] Inserting batch {batch_num} ({batch_rows} rows)")
                        duckdb_conn.execute(f"INSERT INTO {table_name} SELECT * FROM batch_df")

                    total_rows += batch_rows

                    # Log progress every 10 batches
                    if batch_num % 10 == 0:
                        logger.info(f"[{step_id}] Progress: {total_rows} rows processed")

            # Handle empty result set
            if first_batch:
                logger.warning(f"[{step_id}] Query returned no results, creating empty table")
                # Create empty table with placeholder column
                duckdb_conn.execute(f"CREATE TABLE {table_name} (placeholder VARCHAR)")
                duckdb_conn.execute(f"DELETE FROM {table_name}")  # Ensure it's empty

            # Log final metrics
            logger.info(f"[{step_id}] MySQL streaming completed: " f"table={table_name}, total_rows={total_rows}")

            if ctx and hasattr(ctx, "log_metric"):
                ctx.log_metric("rows_read", total_rows)

            return {"table": table_name, "rows": total_rows}

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
