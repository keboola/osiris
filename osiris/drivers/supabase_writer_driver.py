"""Supabase writer driver for runtime execution."""

from datetime import date, datetime
from decimal import Decimal
import logging
from pathlib import Path
import random
import socket
import time
from typing import Any
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import requests

from ..connectors.supabase.client import SupabaseClient
from ..core.driver import Driver
from ..core.session_logging import log_event, log_metric

logger = logging.getLogger(__name__)


def retry_with_backoff(func, max_attempts=3, initial_delay=1.0, max_delay=10.0):
    """Execute function with exponential backoff and jitter.

    Args:
        func: Function to execute
        max_attempts: Maximum retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds

    Returns:
        Function result

    Raises:
        Last exception if all retries fail
    """
    last_exception = None
    delay = initial_delay

    for attempt in range(max_attempts):
        try:
            return func()
        except Exception as e:
            last_exception = e
            if attempt < max_attempts - 1:
                # Add jitter: 0.5x to 1.5x the base delay
                jittered_delay = delay * (0.5 + random.random())
                logger.warning(
                    f"Attempt {attempt + 1} failed: {str(e)[:100]}. " f"Retrying in {jittered_delay:.2f}s..."
                )
                time.sleep(jittered_delay)
                # Exponential backoff with cap
                delay = min(delay * 2, max_delay)
            else:
                logger.error(f"All {max_attempts} attempts failed")

    raise last_exception


class SupabaseWriterDriver(Driver):
    """Driver for writing data to Supabase."""

    def run(self, *, step_id: str, config: dict, inputs: dict | None = None, ctx: Any = None) -> dict:
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
            "ddl_channel",
        }

        unknown_keys = set(config.keys()) - known_keys
        if unknown_keys:
            raise ValueError(f"Step {step_id}: Unknown configuration keys: {', '.join(sorted(unknown_keys))}")

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
        if write_mode in {"upsert", "replace"} and not primary_key:
            raise ValueError(f"Step {step_id}: 'primary_key' is required when mode is '{write_mode}'")

        # Normalize primary_key to list
        if primary_key and not isinstance(primary_key, list):
            primary_key = [primary_key]

        # Get optional configuration
        schema = config.get("schema", "public")
        batch_size = config.get("batch_size", 500)
        create_if_missing = config.get("create_if_missing", False)
        timeout = config.get("timeout", 30)
        retries = config.get("retries", 3)
        ddl_channel = config.get("ddl_channel", "auto").lower()
        if ddl_channel not in {"auto", "http_sql", "psycopg2"}:
            raise ValueError(
                f"Step {step_id}: Invalid ddl_channel '{ddl_channel}'. Expected auto, http_sql, or psycopg2"
            )

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
            output_dir = Path(f"logs/run_{int(datetime.now().timestamp() * 1000)}/artifacts/{step_id}")
            output_dir.mkdir(parents=True, exist_ok=True)

        effective_mode = "upsert" if write_mode == "replace" else write_mode
        primary_key_values = self._collect_primary_key_values(df, primary_key) if primary_key else []

        try:
            # Initialize Supabase client
            client_config = {**connection_config, "timeout": timeout}
            supabase_client = SupabaseClient(client_config)

            with supabase_client as client:
                table_exists = self._table_exists(client, table_name)
                if not table_exists:
                    if not create_if_missing:
                        raise RuntimeError(f"Table {table_name} does not exist and create_if_missing is false")

                    create_sql = self._generate_create_table_sql(df, table_name, schema, primary_key)
                    ddl_path = None
                    if output_dir:
                        ddl_path = output_dir / "ddl_plan.sql"
                        with open(ddl_path, "w", encoding="utf-8") as f:
                            f.write(create_sql)
                        logger.info(f"DDL plan saved to: {ddl_path}")

                    self._ensure_table_exists(
                        step_id=step_id,
                        connection_config=connection_config,
                        ddl_sql=create_sql,
                        schema=schema,
                        table_name=table_name,
                        ddl_channel=ddl_channel,
                        ddl_plan_path=ddl_path,
                    )

                    logger.info("Waiting 3s for PostgREST schema cache refresh...")
                    time.sleep(3)

                # Convert DataFrame to records
                records = self._prepare_records(df)

                # Process in batches
                for i in range(0, len(records), batch_size):
                    batch = records[i : i + batch_size]

                    try:
                        # Wrap Supabase operations in retry logic
                        def write_batch(batch_data=batch, batch_idx=i):
                            if effective_mode == "insert":
                                return client.table(table_name).insert(batch_data).execute()
                            elif effective_mode == "upsert":
                                return (
                                    client.table(table_name)
                                    .upsert(batch_data, on_conflict=",".join(primary_key))
                                    .execute()
                                )
                            else:
                                raise ValueError(f"Unsupported write mode: {effective_mode}")

                        # Execute with retry
                        retry_with_backoff(write_batch, max_attempts=3)

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
                                if effective_mode == "insert":
                                    client.table(table_name).insert(batch).execute()
                                elif effective_mode == "upsert":
                                    client.table(table_name).upsert(batch, on_conflict=",".join(primary_key)).execute()
                                rows_written += len(batch)
                            except Exception as retry_e:
                                raise RuntimeError(f"Batch write failed after retry: {str(retry_e)}") from retry_e
                        else:
                            raise

                if write_mode == "replace":
                    self._perform_replace_cleanup(
                        step_id=step_id,
                        client=client,
                        connection_config=connection_config,
                        table_name=table_name,
                        schema=schema,
                        primary_key=primary_key,
                        primary_key_values=primary_key_values,
                        ddl_channel=ddl_channel,
                    )

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

    def _prepare_records(self, df: pd.DataFrame) -> list[dict[str, Any]]:
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
                elif isinstance(value, pd.Timestamp | np.datetime64):
                    record[col] = pd.Timestamp(value).isoformat()
                elif isinstance(value, datetime | date):
                    record[col] = value.isoformat()
                # Handle numeric types
                elif isinstance(value, np.integer | np.int64 | np.int32):
                    record[col] = int(value)
                elif isinstance(value, np.floating | np.float64 | np.float32):
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
        self, df: pd.DataFrame, table_name: str, schema: str, primary_key: list[str] | None
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

    def _has_sql_channel(self, connection_config: dict[str, Any]) -> bool:
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

    def _has_http_sql_channel(self, connection_config: dict[str, Any]) -> bool:
        return any(k in connection_config for k in ["sql_url", "sql_endpoint"])

    def _execute_ddl(self, connection_config: dict[str, Any], ddl_sql: str, schema: str, table_name: str) -> None:
        self._execute_psycopg2_sql(connection_config, ddl_sql)

    def _execute_psycopg2_sql(self, connection_config: dict[str, Any], ddl_sql: str) -> None:
        try:
            import psycopg2
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError(
                "SQL channel available but psycopg2 not installed. Install with: pip install psycopg2-binary"
            ) from exc

        conn = self._connect_psycopg2(connection_config)
        if conn is None:
            raise RuntimeError("SQL channel DDL execution not available. Provide pg_dsn or connection parameters.")

        with conn:
            with conn.cursor() as cur:
                cur.execute(ddl_sql)
            conn.commit()

    def _table_exists(self, client, table_name: str) -> bool:
        try:
            client.table(table_name).select("count").limit(0).execute()
            return True
        except Exception:
            return False

    def _ensure_table_exists(
        self,
        *,
        step_id: str,
        connection_config: dict[str, Any],
        ddl_sql: str,
        schema: str,
        table_name: str,
        ddl_channel: str,
        ddl_plan_path: Path | None,
    ) -> None:
        channels = [ddl_channel] if ddl_channel != "auto" else ["http_sql", "psycopg2"]
        last_error: Exception | None = None

        if ddl_plan_path:
            log_event(
                "table.ddl_planned",
                step_id=step_id,
                table=table_name,
                schema=schema,
                ddl_path=str(ddl_plan_path),
                executed=False,
            )

        for channel in channels:
            if channel == "http_sql" and not self._has_http_sql_channel(connection_config):
                last_error = RuntimeError("HTTP SQL channel not configured")
                continue
            if channel == "psycopg2" and not self._has_sql_channel(connection_config):
                last_error = RuntimeError("psycopg2 channel not configured")
                continue

            self._ddl_attempt(
                step_id=step_id, table=table_name, schema=schema, operation="create_table", channel=channel
            )

            try:
                if channel == "http_sql":
                    self._execute_http_sql(connection_config, ddl_sql)
                else:
                    self._execute_psycopg2_sql(connection_config, ddl_sql)

                self._ddl_success(
                    step_id=step_id,
                    table=table_name,
                    schema=schema,
                    operation="create_table",
                    channel=channel,
                    ddl_path=str(ddl_plan_path) if ddl_plan_path else None,
                )
                return
            except Exception as exc:
                last_error = exc
                self._ddl_failed(
                    step_id=step_id,
                    table=table_name,
                    schema=schema,
                    operation="create_table",
                    channel=channel,
                    error=str(exc),
                )
                if ddl_channel == channel:
                    raise

        if last_error:
            raise RuntimeError(f"Table creation failed: {last_error}") from last_error

    def _execute_http_sql(self, connection_config: dict[str, Any], ddl_sql: str) -> None:
        sql_url = connection_config.get("sql_url") or connection_config.get("sql_endpoint")
        api_key = (
            connection_config.get("service_role_key")
            or connection_config.get("key")
            or connection_config.get("anon_key")
        )
        if not sql_url or not api_key:
            raise RuntimeError("HTTP SQL channel not configured (missing sql_url or key)")

        headers = {
            "apikey": api_key,
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {"query": ddl_sql}
        response = requests.post(sql_url, json=payload, headers=headers, timeout=30)
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP SQL request failed ({response.status_code}): {response.text}")

    def _connect_psycopg2(self, connection_config: dict[str, Any]):
        try:
            import psycopg2
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("psycopg2 not installed") from exc

        dsn = connection_config.get("dsn") or connection_config.get("sql_dsn") or connection_config.get("pg_dsn")

        if dsn:
            parsed = urlparse(dsn)
            host = parsed.hostname
            port = parsed.port or 5432
            user = parsed.username
            password = parsed.password
            dbname = parsed.path.lstrip("/")
            ipv4 = self._resolve_ipv4(host, port) if host else None
            sslmode = "require"
            return psycopg2.connect(
                host=ipv4 or host,
                port=port,
                user=user,
                password=password,
                dbname=dbname,
                sslmode=sslmode,
            )

        # Build DSN from discrete parameters
        host = connection_config.get("pg_host") or connection_config.get("host")
        if not host:
            return None

        port = connection_config.get("pg_port") or connection_config.get("port") or 5432
        user = connection_config.get("pg_user") or connection_config.get("user")
        password = connection_config.get("pg_password") or connection_config.get("password")
        database = connection_config.get("pg_database") or connection_config.get("database")
        if not all([user, password, database]):
            return None

        ipv4 = self._resolve_ipv4(host, port)
        try:
            import psycopg2

            return psycopg2.connect(
                host=ipv4 or host,
                port=port,
                user=user,
                password=password,
                dbname=database,
                sslmode="require",
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to connect via psycopg2: {exc}") from exc

    @staticmethod
    def _resolve_ipv4(host: str | None, port: int) -> str | None:
        if not host:
            return None
        try:
            result = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
            if result:
                return result[0][4][0]
        except socket.gaierror:
            return None
        return None

    def _collect_primary_key_values(self, df: pd.DataFrame, primary_key: list[str]) -> list[tuple[Any, ...]]:
        if not primary_key:
            return []

        pk_df = df[primary_key].drop_duplicates()
        values: list[tuple[Any, ...]] = []
        for _, row in pk_df.iterrows():
            values.append(tuple(row[col] for col in primary_key))
        return values

    def _perform_replace_cleanup(
        self,
        *,
        step_id: str,
        client,
        connection_config: dict[str, Any],
        table_name: str,
        schema: str,
        primary_key: list[str] | None,
        primary_key_values: list[tuple[Any, ...]],
        ddl_channel: str,
    ) -> None:
        if not primary_key:
            raise ValueError(f"Step {step_id}: 'primary_key' must be provided for replace mode")

        if not primary_key_values:
            # Delete all rows since new dataset is empty
            if ddl_channel in {"auto", "http_sql"} and self._has_http_sql_channel(connection_config):
                self._ddl_attempt(step_id, table_name, schema, "anti_delete", "http_sql")
                try:
                    self._delete_all_rows_http(client, table_name, primary_key[0])
                    self._ddl_success(step_id, table_name, schema, "anti_delete", "http_sql")
                    return
                except Exception as exc:
                    self._ddl_failed(step_id, table_name, schema, "anti_delete", "http_sql", str(exc))
                    if ddl_channel == "http_sql":
                        raise

            self._ddl_attempt(step_id, table_name, schema, "anti_delete", "psycopg2")
            self._delete_all_rows_psycopg2(connection_config, table_name, schema)
            self._ddl_success(step_id, table_name, schema, "anti_delete", "psycopg2")
            return

        channels = [ddl_channel] if ddl_channel != "auto" else ["http_sql", "psycopg2"]
        last_error: Exception | None = None

        for channel in channels:
            self._ddl_attempt(step_id, table_name, schema, "anti_delete", channel)
            try:
                if channel == "http_sql":
                    if len(primary_key) > 1:
                        raise RuntimeError("HTTP SQL anti-delete does not support composite primary keys")
                    if not self._has_http_sql_channel(connection_config):
                        raise RuntimeError("HTTP SQL channel not configured")
                    flat_values = [value[0] for value in primary_key_values]
                    self._delete_missing_rows_http(client, table_name, primary_key[0], flat_values)
                else:
                    self._delete_missing_rows_psycopg2(
                        connection_config,
                        table_name,
                        schema,
                        primary_key,
                        primary_key_values,
                    )

                self._ddl_success(step_id, table_name, schema, "anti_delete", channel)
                return
            except Exception as exc:
                last_error = exc
                self._ddl_failed(step_id, table_name, schema, "anti_delete", channel, str(exc))
                if ddl_channel == channel:
                    raise

        if last_error:
            raise RuntimeError(f"Replace cleanup failed: {last_error}") from last_error

    def _delete_missing_rows_http(
        self,
        client,
        table_name: str,
        primary_key: str,
        primary_key_values: list[Any],
    ) -> None:
        existing = client.table(table_name).select(primary_key).execute().data or []
        existing_values = {row[primary_key] for row in existing if primary_key in row}
        incoming_values = set(primary_key_values)
        missing = existing_values - incoming_values

        if not missing:
            return

        for chunk in self._chunk_list(list(missing), 100):
            client.table(table_name).delete().in_(primary_key, chunk).execute()

    def _delete_missing_rows_psycopg2(
        self,
        connection_config: dict[str, Any],
        table_name: str,
        schema: str,
        primary_key: list[str],
        primary_key_values: list[tuple[Any, ...]],
    ) -> None:

        conn = self._connect_psycopg2(connection_config)
        if conn is None:
            raise RuntimeError("psycopg2 channel not configured")

        with conn:
            with conn.cursor() as cur:
                select_sql = f"SELECT {', '.join(primary_key)} FROM {schema}.{table_name}"
                cur.execute(select_sql)
                existing = cur.fetchall()

                incoming_set = set(primary_key_values)
                missing = [row for row in existing if row not in incoming_set]

                if not missing:
                    return

                chunk_size = 100
                for chunk in self._chunk_list(missing, chunk_size):
                    conditions = []
                    params: list[Any] = []
                    for row in chunk:
                        condition = " AND ".join([f"{col} = %s" for col in primary_key])
                        conditions.append(f"({condition})")
                        params.extend(row)

                    delete_sql = f"DELETE FROM {schema}.{table_name} WHERE " + " OR ".join(conditions)
                    cur.execute(delete_sql, params)

            conn.commit()

    def _delete_all_rows_http(self, client, table_name: str, primary_key: str) -> None:
        try:
            client.table(table_name).delete().neq(primary_key, None).execute()
        except Exception:
            # If primary key can be NULL, fall back to match all values
            client.table(table_name).delete().execute()

    def _delete_all_rows_psycopg2(self, connection_config: dict[str, Any], table_name: str, schema: str) -> None:

        conn = self._connect_psycopg2(connection_config)
        if conn is None:
            raise RuntimeError("psycopg2 channel not configured")

        with conn:
            with conn.cursor() as cur:
                cur.execute(f"DELETE FROM {schema}.{table_name}")
            conn.commit()

    @staticmethod
    def _chunk_list(values: list[Any], size: int) -> list[list[Any]]:
        return [values[i : i + size] for i in range(0, len(values), size)]

    def _ddl_attempt(self, *, step_id: str, table: str, schema: str, operation: str, channel: str) -> None:
        log_event(
            "ddl_attempt",
            step_id=step_id,
            table=table,
            schema=schema,
            operation=operation,
            channel=channel,
        )

    def _ddl_success(
        self,
        step_id: str,
        table: str,
        schema: str,
        operation: str,
        channel: str,
        ddl_path: str | None = None,
    ) -> None:
        log_event(
            "ddl_succeeded",
            step_id=step_id,
            table=table,
            schema=schema,
            operation=operation,
            channel=channel,
            ddl_path=ddl_path,
        )
        log_event(
            "table.ddl_executed",
            step_id=step_id,
            table=table,
            schema=schema,
            channel=channel,
            ddl_path=ddl_path,
            executed=True,
        )

    def _ddl_failed(
        self,
        step_id: str,
        table: str,
        schema: str,
        operation: str,
        channel: str,
        error: str,
    ) -> None:
        log_event(
            "ddl_failed",
            step_id=step_id,
            table=table,
            schema=schema,
            operation=operation,
            channel=channel,
            error=error,
        )
        log_event(
            "table.ddl_failed",
            step_id=step_id,
            table=table,
            schema=schema,
            channel=channel,
            error=error,
        )
