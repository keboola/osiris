"""Supabase writer driver for runtime execution."""

import logging
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from ..connectors.supabase.client import SupabaseClient
from ..core.driver import Driver
from ..core.session_logging import log_event, log_metric

logger = logging.getLogger(__name__)


class SupabaseWriterDriver(Driver):
    """Driver for writing data to Supabase."""

    def run(
        self, *, step_id: str, config: dict, inputs: Optional[dict] = None, ctx: Any = None
    ) -> dict:
        """Execute Supabase write operation.

        Args:
            step_id: Identifier of the step being executed
            config: Step configuration including resolved connections
            inputs: Input data from upstream steps (expects {"df": DataFrame})
            ctx: Execution context for logging

        Returns:
            Empty dict {} for writers

        Raises:
            ValueError: If configuration is invalid or inputs missing
            RuntimeError: If write operation fails
        """
        # Validate inputs
        if not inputs or "df" not in inputs:
            raise ValueError(f"Step {step_id}: SupabaseWriterDriver requires 'df' input")

        df = inputs["df"]
        if not isinstance(df, pd.DataFrame):
            raise ValueError(f"Step {step_id}: Input 'df' must be a pandas DataFrame")

        # Extract configuration (strict - reject unknown keys)
        known_keys = {
            "resolved_connection",
            "table",
            "schema",
            "mode",  # OML uses 'mode' which maps to 'write_mode'
            "write_mode",
            "primary_key",
            "returning",
            "create_if_missing",
            "batch_size",
            "timeout",
            "retries",
            "prefer",
        }

        unknown_keys = set(config.keys()) - known_keys
        if unknown_keys:
            raise ValueError(
                f"Step {step_id}: Unknown configuration keys: {', '.join(sorted(unknown_keys))}"
            )

        # Get resolved connection
        connection_config = config.get("resolved_connection", {})
        if not connection_config:
            raise ValueError(f"Step {step_id}: Missing resolved_connection in config")

        # Get table name (required)
        table_name = config.get("table")
        if not table_name:
            raise ValueError(f"Step {step_id}: 'table' is required in config")

        # Get write mode - handle both 'mode' (from OML) and 'write_mode' (component spec)
        write_mode = config.get("write_mode", config.get("mode", "insert"))

        # Map write modes: append -> insert, replace -> replace, upsert -> upsert
        mode_mapping = {
            "append": "insert",
            "replace": "replace",
            "upsert": "upsert",
            "insert": "insert",
        }
        write_mode = mode_mapping.get(write_mode, write_mode)

        # Get primary key for upsert
        primary_key = config.get("primary_key")
        if write_mode == "upsert" and not primary_key:
            raise ValueError(f"Step {step_id}: 'primary_key' is required when mode is 'upsert'")

        # Normalize primary_key to list
        if primary_key and not isinstance(primary_key, list):
            primary_key = [primary_key]

        # Get optional configuration
        schema = config.get("schema", "public")
        batch_size = config.get("batch_size", 500)
        create_if_missing = config.get("create_if_missing", False)
        timeout = config.get("timeout", 30)
        retries = config.get("retries", 3)

        # Log operation start
        if ctx:
            log_event(
                "write.start",
                step_id=step_id,
                table=table_name,
                mode=write_mode,
                rows=len(df),
                batch_size=batch_size,
            )

        start_time = datetime.now()
        rows_written = 0

        # Determine output directory for artifacts (if ctx has it)
        output_dir = None
        if hasattr(ctx, "output_dir"):
            output_dir = Path(ctx.output_dir)
        elif step_id:
            # Try to infer from step_id
            output_dir = Path(
                f"logs/run_{int(datetime.now().timestamp() * 1000)}/artifacts/{step_id}"
            )
            output_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Initialize Supabase client
            client_config = {**connection_config, "timeout": timeout}
            supabase_client = SupabaseClient(client_config)

            with supabase_client as client:
                # Pre-flight check: verify table exists
                try:
                    # Try to fetch 0 rows to check table existence
                    client.table(table_name).select("*").limit(0).execute()
                except Exception as e:
                    if create_if_missing:
                        # Generate CREATE TABLE SQL
                        create_sql = self._generate_create_table_sql(
                            df, table_name, schema, primary_key
                        )

                        # Save DDL plan as artifact
                        if output_dir:
                            ddl_path = output_dir / "ddl_plan.sql"
                            with open(ddl_path, "w") as f:
                                f.write(create_sql)
                            logger.info(f"DDL plan saved to: {ddl_path}")

                        # Check if we have a SQL channel (DSN or SQL client)
                        has_sql_channel = self._has_sql_channel(connection_config)

                        if has_sql_channel:
                            # Execute DDL via SQL channel
                            try:
                                self._execute_ddl(connection_config, create_sql, schema, table_name)
                                logger.info(f"Successfully created table {schema}.{table_name}")
                                log_event(
                                    "table.ddl_executed",
                                    step_id=step_id,
                                    table=table_name,
                                    schema=schema,
                                    ddl_path=str(ddl_path) if output_dir else None,
                                    executed=True,
                                )
                                # Wait for PostgREST schema cache to refresh
                                import time

                                logger.info("Waiting 3s for PostgREST schema cache refresh...")
                                time.sleep(3)
                            except Exception as ddl_error:
                                logger.error(f"Failed to execute DDL: {str(ddl_error)}")
                                log_event(
                                    "table.ddl_failed",
                                    step_id=step_id,
                                    table=table_name,
                                    error=str(ddl_error),
                                )
                                raise RuntimeError(
                                    f"Table creation failed: {str(ddl_error)}"
                                ) from ddl_error
                        else:
                            # No SQL channel available, only log the plan
                            logger.warning(
                                f"Table {table_name} does not exist. DDL plan saved but not executed (no SQL channel). "
                                f"Please create the table manually:\n{create_sql}"
                            )
                            log_event(
                                "table.ddl_planned",
                                step_id=step_id,
                                table=table_name,
                                schema=schema,
                                ddl_path=str(ddl_path) if output_dir else None,
                                executed=False,
                                reason="No SQL channel available",
                            )
                            # Continue with write attempt (may fail)
                            pass
                    else:
                        raise RuntimeError(f"Table {table_name} does not exist: {str(e)}") from e

                # Convert DataFrame to records
                records = self._prepare_records(df)

                # Process in batches
                for i in range(0, len(records), batch_size):
                    batch = records[i : i + batch_size]

                    try:
                        if write_mode == "insert":
                            client.table(table_name).insert(batch).execute()
                        elif write_mode == "upsert":
                            client.table(table_name).upsert(
                                batch, on_conflict=",".join(primary_key)
                            ).execute()
                        elif write_mode == "replace":
                            # Replace mode: delete all then insert
                            if i == 0:  # Only delete on first batch
                                client.table(table_name).delete().neq(
                                    "id", "0"
                                ).execute()  # Delete all
                            client.table(table_name).insert(batch).execute()
                        else:
                            raise ValueError(f"Unsupported write mode: {write_mode}")

                        rows_written += len(batch)

                        # Log progress
                        if ctx and (i + batch_size) % (batch_size * 10) == 0:
                            log_event(
                                "write.progress",
                                step_id=step_id,
                                rows_written=rows_written,
                                total_rows=len(df),
                            )

                    except Exception as e:
                        logger.error(f"Failed to write batch {i // batch_size}: {str(e)}")
                        if retries > 0:
                            # Simple retry logic (could be enhanced with backoff)
                            logger.info(f"Retrying batch {i // batch_size}...")
                            try:
                                if write_mode == "insert":
                                    client.table(table_name).insert(batch).execute()
                                elif write_mode == "upsert":
                                    client.table(table_name).upsert(
                                        batch, on_conflict=",".join(primary_key)
                                    ).execute()
                                rows_written += len(batch)
                            except Exception as retry_e:
                                raise RuntimeError(
                                    f"Batch write failed after retry: {str(retry_e)}"
                                ) from retry_e
                        else:
                            raise

            # Calculate metrics
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            # Log metrics
            if ctx:
                log_metric("rows_written", rows_written, step_id=step_id)
                log_metric("duration_ms", duration_ms, step_id=step_id)
                log_event(
                    "write.complete",
                    step_id=step_id,
                    table=table_name,
                    rows_written=rows_written,
                    duration_ms=duration_ms,
                )

            logger.info(f"Successfully wrote {rows_written} rows to {table_name}")

            return {}  # Writers return empty dict

        except Exception as e:
            # Log error
            if ctx:
                log_event("write.error", step_id=step_id, error=str(e))
            raise RuntimeError(f"Supabase write failed: {str(e)}") from e

    def _prepare_records(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Convert DataFrame to list of records with proper serialization.

        Args:
            df: DataFrame to convert

        Returns:
            List of dictionaries ready for Supabase API
        """
        records = []
        for _, row in df.iterrows():
            record = {}
            for col, value in row.items():
                # Handle NaN/None
                if pd.isna(value):
                    record[col] = None
                # Handle datetime types
                elif isinstance(value, (pd.Timestamp, np.datetime64)):
                    record[col] = pd.Timestamp(value).isoformat()
                elif isinstance(value, (datetime, date)):
                    record[col] = value.isoformat()
                # Handle numeric types
                elif isinstance(value, (np.integer, np.int64, np.int32)):
                    record[col] = int(value)
                elif isinstance(value, (np.floating, np.float64, np.float32)):
                    if np.isnan(value):
                        record[col] = None
                    else:
                        record[col] = float(value)
                elif isinstance(value, Decimal):
                    record[col] = float(value)
                elif isinstance(value, np.bool_):
                    record[col] = bool(value)
                # Pass through other types
                else:
                    record[col] = value
            records.append(record)
        return records

    def _generate_create_table_sql(
        self, df: pd.DataFrame, table_name: str, schema: str, primary_key: Optional[List[str]]
    ) -> str:
        """Generate CREATE TABLE SQL based on DataFrame schema (display only).

        Args:
            df: DataFrame to infer schema from
            table_name: Table name
            schema: Schema name
            primary_key: Primary key columns

        Returns:
            SQL CREATE TABLE statement
        """
        columns = []
        for col in df.columns:
            dtype = str(df[col].dtype)
            if "int" in dtype:
                pg_type = "INTEGER"
            elif "float" in dtype:
                pg_type = "DOUBLE PRECISION"
            elif "bool" in dtype:
                pg_type = "BOOLEAN"
            elif "datetime" in dtype:
                pg_type = "TIMESTAMP"
            else:
                pg_type = "TEXT"
            columns.append(f"    {col} {pg_type}")

        sql = f"CREATE TABLE IF NOT EXISTS {schema}.{table_name} (\n"
        sql += ",\n".join(columns)
        if primary_key:
            sql += f",\n    PRIMARY KEY ({', '.join(primary_key)})"
        sql += "\n);"
        return sql

    def _has_sql_channel(self, connection_config: Dict[str, Any]) -> bool:
        """Check if connection config provides SQL execution capability.

        Args:
            connection_config: Resolved connection configuration

        Returns:
            True if SQL channel is available (DSN or SQL client config)
        """
        # Check for PostgreSQL DSN variants
        if any(k in connection_config for k in ["dsn", "sql_dsn", "pg_dsn"]):
            return True

        # Check for SQL endpoint variants
        if any(k in connection_config for k in ["sql_url", "sql_endpoint"]):
            return True

        # Check for separate PostgreSQL connection parameters (pg_ prefixed)
        pg_params = ["pg_host", "pg_database", "pg_user", "pg_password"]
        if all(param in connection_config for param in pg_params):
            return True

        # Check for standard PostgreSQL connection parameters
        std_params = ["host", "database", "user", "password"]
        return all(param in connection_config for param in std_params)

    def _execute_ddl(
        self, connection_config: Dict[str, Any], ddl_sql: str, schema: str, table_name: str
    ) -> None:
        """Execute DDL statement via SQL channel if available.

        Args:
            connection_config: Resolved connection configuration
            ddl_sql: DDL statement to execute
            schema: Schema name
            table_name: Table name

        Raises:
            RuntimeError: If DDL execution fails
        """
        # Try to get DSN - check multiple possible keys
        dsn = (
            connection_config.get("dsn")
            or connection_config.get("sql_dsn")
            or connection_config.get("pg_dsn")
        )

        # If no DSN, try to build one from separate params
        if not dsn:
            # Try pg_ prefixed params first
            if all(
                k in connection_config for k in ["pg_host", "pg_database", "pg_user", "pg_password"]
            ):
                pg_port = connection_config.get("pg_port", 5432)
                dsn = (
                    f"postgresql://{connection_config['pg_user']}:{connection_config['pg_password']}"
                    f"@{connection_config['pg_host']}:{pg_port}/{connection_config['pg_database']}"
                )
                logger.info(
                    f"Built PostgreSQL DSN from pg_ parameters (host={connection_config['pg_host']})"
                )
            # Try standard params
            elif all(k in connection_config for k in ["host", "database", "user", "password"]):
                port = connection_config.get("port", 5432)
                dsn = (
                    f"postgresql://{connection_config['user']}:{connection_config['password']}"
                    f"@{connection_config['host']}:{port}/{connection_config['database']}"
                )
                logger.info(
                    f"Built PostgreSQL DSN from standard parameters (host={connection_config['host']})"
                )

        if dsn:
            try:
                import psycopg2

                logger.info(f"SQL channel detected: psycopg2 (schema={schema}, table={table_name})")
                with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
                    cur.execute(ddl_sql)
                    conn.commit()
                logger.info(f"Successfully executed DDL for {schema}.{table_name}")
                return
            except ImportError:
                logger.warning("psycopg2 not installed, cannot execute DDL via DSN")
                raise RuntimeError(
                    "SQL channel available but psycopg2 not installed. "
                    "Install with: pip install psycopg2-binary"
                ) from None
            except Exception as e:
                logger.error(f"Failed to execute DDL: {str(e)}")
                raise RuntimeError(f"DDL execution failed: {str(e)}") from e

        # No SQL channel available - this is not an error, just log it
        logger.info("SQL channel detected: none - DDL plan saved but not executed")
        raise NotImplementedError(
            "SQL channel DDL execution not available. "
            "Please create the table manually using the generated DDL plan."
        )
