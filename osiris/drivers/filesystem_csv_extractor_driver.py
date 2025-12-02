"""Filesystem CSV extractor driver implementation."""

import logging
from pathlib import Path
import subprocess
from typing import Any

import pandas as pd

from osiris.core.config import parse_connection_ref, resolve_connection

logger = logging.getLogger(__name__)


class FilesystemCsvExtractorDriver:
    """Driver for extracting data from CSV files."""

    def run(
        self,
        *,
        step_id: str,
        config: dict,
        inputs: dict | None = None,  # noqa: ARG002
        ctx: Any = None,
    ) -> dict:
        """Extract data from CSV file and stream to DuckDB.

        Args:
            step_id: Step identifier (used as table name)
            config: Must contain 'path' and optional CSV parsing settings.
                   May include 'connection' field for connection-based configuration.
                   May include 'chunk_size' for batch size (default: 10000)
            inputs: Not used for extractors
            ctx: Execution context for logging metrics and database connection

        Returns:
            {"table": step_id, "rows": total_row_count}
        """
        # Resolve connection if provided
        base_dir = None
        conn_ref = config.get("connection")

        if conn_ref:
            # Parse connection reference (format: @filesystem.alias)
            if isinstance(conn_ref, str) and conn_ref.startswith("@"):
                family, alias = parse_connection_ref(conn_ref)

                # Validate family is filesystem
                if family != "filesystem":
                    raise ValueError(f"Step {step_id}: Connection family must be 'filesystem', got '{family}'")

                # Resolve connection to get base_dir
                try:
                    connection_config = resolve_connection(family, alias)
                    base_dir = connection_config.get("base_dir")

                    if base_dir:
                        logger.info(f"Step {step_id}: Using base_dir from connection: {base_dir}")
                except Exception as e:
                    raise ValueError(f"Step {step_id}: Failed to resolve connection '{conn_ref}': {e}") from e
            else:
                raise ValueError(
                    f"Step {step_id}: Invalid connection format: '{conn_ref}'. Expected '@filesystem.alias'"
                )

        # Get required path
        file_path = config.get("path")
        if not file_path:
            raise ValueError(f"Step {step_id}: 'path' is required in config")

        # Check if discovery mode is requested
        if config.get("discovery", False):
            return self.discover(config, base_dir=base_dir)

        # Resolve path (with base_dir from connection if available)
        resolved_path = self._resolve_path(file_path, ctx, base_dir=base_dir)

        # Validate file exists
        if not resolved_path.exists():
            raise FileNotFoundError(f"Step {step_id}: CSV file not found: {resolved_path}")

        if not resolved_path.is_file():
            raise ValueError(f"Step {step_id}: Path is not a file: {resolved_path}")

        # Extract CSV parsing options with defaults
        delimiter = config.get("delimiter", ",")
        encoding = config.get("encoding", "utf-8")
        # Use chunk_size from spec (default 10000), fall back to batch_size for compatibility
        batch_size = config.get("chunk_size", config.get("batch_size", 10000))

        # Handle header: boolean (true=0, false=None) or integer (row number)
        # Spec supports: true (row 0), false (no header), or integer (specific row)
        header_config = config.get("header", True)
        if isinstance(header_config, bool):
            header = 0 if header_config else None
        else:
            # Integer row index to use as header
            header = header_config

        columns = config.get("columns")
        skip_rows = config.get("skip_rows")
        limit = config.get("limit")
        parse_dates = config.get("parse_dates")
        dtype = config.get("dtype")
        na_values = config.get("na_values")
        comment = config.get("comment")
        on_bad_lines = config.get("on_bad_lines", "error")

        # Additional pandas options exposed in spec
        skip_blank_lines = config.get("skip_blank_lines", True)
        compression = config.get("compression", "infer")

        # Get DuckDB connection from context
        if not ctx or not hasattr(ctx, "get_db_connection"):
            raise RuntimeError(f"Step {step_id}: Context must provide get_db_connection() method")

        conn = ctx.get_db_connection()
        table_name = step_id

        logger.info(
            f"[{step_id}] Starting CSV streaming extraction: "
            f"file={resolved_path}, delimiter='{delimiter}', batch_size={batch_size}"
        )

        try:
            # Build pandas read_csv parameters
            read_params = {
                "filepath_or_buffer": resolved_path,
                "sep": delimiter,
                "encoding": encoding,
                "header": header,
                "chunksize": batch_size,  # Enable streaming
                "low_memory": False,  # Let DuckDB infer schema
            }

            # Add optional parameters only if specified
            if columns is not None:
                read_params["usecols"] = columns
            if skip_rows is not None and skip_rows > 0:
                read_params["skiprows"] = skip_rows
            if limit is not None:
                # For streaming with limit, we'll handle it per-chunk
                read_params["nrows"] = limit
            if parse_dates is not None:
                read_params["parse_dates"] = parse_dates
            if dtype is not None:
                read_params["dtype"] = dtype
            if na_values is not None:
                read_params["na_values"] = na_values
            if comment is not None:
                read_params["comment"] = comment
            if on_bad_lines != "error":
                read_params["on_bad_lines"] = on_bad_lines

            # Add additional pandas options if not default
            if not skip_blank_lines:  # Only include if False (default is True)
                read_params["skip_blank_lines"] = skip_blank_lines
            if compression != "infer":  # Only include if not the default
                read_params["compression"] = compression

            # Read CSV in chunks and stream to DuckDB
            total_rows = 0
            first_chunk = True

            chunk_iterator = pd.read_csv(**read_params)

            for chunk_num, chunk_df in enumerate(chunk_iterator, start=1):
                if chunk_df.empty:
                    logger.warning(f"[{step_id}] Chunk {chunk_num} is empty, skipping")
                    continue

                # Reorder columns if specific columns were requested
                if columns is not None and isinstance(columns, list):
                    chunk_df = chunk_df[columns]  # noqa: PLW2901

                chunk_rows = len(chunk_df)

                if first_chunk:
                    # First chunk: create table and insert data
                    logger.info(
                        f"[{step_id}] Creating table '{table_name}' from first chunk "
                        f"({chunk_rows} rows, {len(chunk_df.columns)} columns)"
                    )

                    # DuckDB can create table directly from DataFrame
                    conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM chunk_df")
                    first_chunk = False

                    logger.info(f"[{step_id}] Table created with schema: {list(chunk_df.columns)}")
                else:
                    # Subsequent chunks: insert into existing table
                    logger.debug(f"[{step_id}] Inserting chunk {chunk_num} ({chunk_rows} rows)")
                    conn.execute(f"INSERT INTO {table_name} SELECT * FROM chunk_df")

                total_rows += chunk_rows

                # Log progress every 10 chunks
                if chunk_num % 10 == 0:
                    logger.info(f"[{step_id}] Progress: {total_rows} rows processed")

            # Handle empty CSV file
            if first_chunk:
                logger.warning(f"[{step_id}] CSV file is empty, creating empty table")
                # Create empty table with placeholder column
                conn.execute(f"CREATE TABLE {table_name} (placeholder VARCHAR)")
                conn.execute(f"DELETE FROM {table_name}")  # Ensure it's empty

            # Log final metrics
            logger.info(f"[{step_id}] CSV streaming completed: " f"table={table_name}, total_rows={total_rows}")

            if ctx and hasattr(ctx, "log_metric"):
                ctx.log_metric("rows_read", total_rows)

            return {"table": table_name, "rows": total_rows}

        except pd.errors.EmptyDataError:
            # Handle empty CSV file
            logger.warning(f"Step {step_id}: CSV file is empty: {resolved_path}")
            conn.execute(f"CREATE TABLE {table_name} (placeholder VARCHAR)")
            conn.execute(f"DELETE FROM {table_name}")

            if ctx and hasattr(ctx, "log_metric"):
                ctx.log_metric("rows_read", 0)

            return {"table": table_name, "rows": 0}

        except pd.errors.ParserError as e:
            error_msg = f"CSV parsing failed: {str(e)}"
            logger.error(f"Step {step_id}: {error_msg}")
            raise RuntimeError(error_msg) from e

        except UnicodeDecodeError as e:
            error_msg = f"CSV encoding error (tried {encoding}): {str(e)}"
            logger.error(f"Step {step_id}: {error_msg}")
            raise RuntimeError(error_msg) from e

        except Exception as e:
            error_msg = f"CSV extraction failed: {type(e).__name__}: {str(e)}"
            logger.error(f"Step {step_id}: {error_msg}")
            raise RuntimeError(error_msg) from e

    def _resolve_path(self, file_path: str, ctx: Any, base_dir: str | None = None) -> Path:
        """Resolve file path to absolute Path object.

        Resolution order for relative paths:
        1. base_dir from connection (if provided)
        2. ctx.base_path (if available)
        3. Current working directory (fallback)

        E2B COMPATIBLE - never uses Path.home().

        Args:
            file_path: Path string (absolute or relative)
            ctx: Execution context (may have base_path attribute)
            base_dir: Base directory from connection config (optional)

        Returns:
            Resolved absolute Path object
        """
        path = Path(file_path)

        # If already absolute, use as-is
        if path.is_absolute():
            return path

        # For relative paths, apply resolution order:
        # 1. Connection base_dir takes highest priority
        if base_dir:
            return Path(base_dir) / path

        # 2. Context base_path
        if ctx and hasattr(ctx, "base_path"):
            return ctx.base_path / path

        # 3. Fallback to current working directory
        return Path.cwd() / path

    def doctor(self, config: dict) -> dict:
        """Health check for CSV file accessibility.

        Args:
            config: Configuration dict with 'path'

        Returns:
            Dict with status and checks
        """
        results = {"status": "healthy", "checks": {}}

        # Check path configuration
        file_path = config.get("path")
        if not file_path:
            results["status"] = "unhealthy"
            results["checks"]["path"] = "missing path configuration"
            return results

        try:
            # Resolve path (no ctx available in doctor)
            path = Path(file_path)
            if not path.is_absolute():
                path = Path.cwd() / path

            # Check file exists
            if not path.exists():
                results["status"] = "unhealthy"
                results["checks"]["file_exists"] = f"file not found: {path}"
                return results

            results["checks"]["file_exists"] = "passed"

            # Check is a file (not directory)
            if not path.is_file():
                results["status"] = "unhealthy"
                results["checks"]["is_file"] = f"path is not a file: {path}"
                return results

            results["checks"]["is_file"] = "passed"

            # Check file is readable by reading first line
            encoding = config.get("encoding", "utf-8")
            delimiter = config.get("delimiter", ",")

            try:
                # Try reading just first row to validate CSV format
                df_sample = pd.read_csv(path, sep=delimiter, encoding=encoding, nrows=1)
                row_count = len(df_sample)
                col_count = len(df_sample.columns)
                results["checks"]["csv_format"] = f"passed ({row_count} row, {col_count} columns in sample)"
            except Exception as e:
                results["status"] = "unhealthy"
                results["checks"]["csv_format"] = f"invalid CSV format: {str(e)}"
                return results

            # Check file size
            file_size = path.stat().st_size
            results["checks"]["file_size"] = f"{file_size} bytes"

        except Exception as e:
            results["status"] = "unhealthy"
            results["checks"]["validation_error"] = f"unexpected error: {str(e)}"

        return results

    def discover(self, config: dict, base_dir: str | None = None) -> dict:
        """Discover CSV files in a directory.

        Args:
            config: Configuration dict with 'path' (directory path)
            base_dir: Base directory from connection config (optional)

        Returns:
            Dict with discovered files and metadata
        """
        results = {"files": [], "status": "success"}

        try:
            # Get directory path
            dir_path = config.get("path", ".")
            directory = Path(dir_path)

            # Resolve directory path using same logic as _resolve_path
            if not directory.is_absolute():
                if base_dir:
                    directory = Path(base_dir) / directory
                else:
                    directory = Path.cwd() / directory

            # Validate directory
            if not directory.exists():
                results["status"] = "error"
                results["error"] = f"Directory not found: {directory}"
                return results

            if not directory.is_dir():
                results["status"] = "error"
                results["error"] = f"Path is not a directory: {directory}"
                return results

            # Find all CSV files
            csv_files = sorted(directory.glob("*.csv"))

            for csv_file in csv_files:
                file_info = {
                    "name": csv_file.name,
                    "path": str(csv_file),
                    "size": csv_file.stat().st_size,
                }

                # Estimate row count using cross-platform approach
                file_info["estimated_rows"] = self._estimate_row_count(csv_file)

                # Try to get column info from sample
                try:
                    # Read just headers (nrows=0 is more efficient than nrows=1)
                    df_sample = pd.read_csv(csv_file, nrows=0)
                    file_info["column_names"] = list(df_sample.columns)
                    file_info["columns"] = len(df_sample.columns)

                    # Read 100 rows to get better type inference than nrows=1
                    df_types = pd.read_csv(csv_file, nrows=100)

                    # Try to detect datetime columns by attempting conversion
                    # This catches columns like "created_at" that contain datetime strings
                    for col in df_types.columns:
                        if df_types[col].dtype == "object":  # Only try on string columns
                            # Try common datetime formats first to avoid warnings
                            formats_to_try = [
                                "%Y-%m-%d %H:%M:%S",  # ISO datetime: 2025-03-03 11:53:20
                                "%Y-%m-%d",  # ISO date: 2025-03-03
                                "ISO8601",  # pandas ISO8601 format
                            ]

                            converted = None
                            for fmt in formats_to_try:
                                try:
                                    converted = pd.to_datetime(df_types[col], format=fmt, errors="coerce")
                                    # Guard against empty columns (headers-only CSV)
                                    if len(converted) > 0 and converted.notna().sum() / len(converted) > 0.8:
                                        df_types[col] = converted
                                        break
                                except (ValueError, TypeError):
                                    continue
                            else:
                                # Fallback to dateutil parser (suppress warning about format inference)
                                # BUT FIRST: Check if values look date-like to avoid false positives
                                # Problem: pd.to_datetime() interprets numeric strings as Unix timestamps
                                # Example: "12345" -> 1970-01-01 00:00:12.345 (WRONG!)
                                # Solution: Only apply fallback if strings contain date separators
                                #
                                # CHANGE 1: Expanded separator regex to include dots and spaces
                                # - Dots: European formats (17.03.2024)
                                # - Spaces: Text month formats (Mar 5 2024), space-separated dates (2024 03 17)
                                sample_values = df_types[col].dropna().astype(str).head(20)
                                has_date_separators = sample_values.str.contains(r"[-/:.\s]").any()

                                if has_date_separators:
                                    try:
                                        import warnings

                                        with warnings.catch_warnings():
                                            warnings.filterwarnings("ignore", category=UserWarning)

                                            # CHANGE 2: Calculate conversion rate on non-null values only
                                            # This handles sparse columns correctly:
                                            # Sparse example: 20 nulls + 10 dates
                                            # Old: 10/30 = 0.33 → rejected
                                            # New: 10/10 = 1.0 → accepted
                                            non_null_values = df_types[col].dropna()
                                            if len(non_null_values) > 0:
                                                # Convert only non-null values to check conversion rate
                                                converted_sample = pd.to_datetime(non_null_values, errors="coerce")
                                                conversion_rate = converted_sample.notna().sum() / len(non_null_values)

                                                # CHANGE 3: Unix epoch sanity check
                                                # Reject if all converted dates are in 1970 (likely numeric IDs)
                                                if conversion_rate > 0.8:
                                                    valid_dates = converted_sample.dropna()
                                                    if len(valid_dates) > 0:
                                                        # Check year range
                                                        min_year = valid_dates.dt.year.min()
                                                        max_year = valid_dates.dt.year.max()

                                                        # Accept if dates are NOT exclusively in Unix epoch range
                                                        if not (min_year == 1970 and max_year == 1970):
                                                            # Convert the ENTIRE column (including nulls)
                                                            # This ensures dtype is properly updated to datetime64
                                                            df_types[col] = pd.to_datetime(
                                                                df_types[col], errors="coerce"
                                                            )

                                    except Exception:  # noqa: S110
                                        pass  # Keep original dtype
                                # else: skip fallback, likely numeric IDs or other non-date strings

                    file_info["column_types"] = {
                        col: self._format_dtype(dtype) for col, dtype in df_types.dtypes.items()
                    }
                except Exception:  # noqa: S110
                    # Can't read file, skip details
                    pass

                results["files"].append(file_info)

            results["total_files"] = len(csv_files)
            logger.info(f"Discovered {len(csv_files)} CSV files in {directory}")

        except Exception as e:
            results["status"] = "error"
            results["error"] = f"Discovery failed: {str(e)}"
            logger.error(f"CSV discovery error: {e}")

        return results

    def _format_dtype(self, dtype) -> str:
        """Convert pandas dtype to user-friendly type name.

        Args:
            dtype: Pandas dtype object

        Returns:
            User-friendly type name
        """
        dtype_str = str(dtype)

        # Map pandas dtypes to user-friendly names
        type_mapping = {
            "object": "string",
            "int64": "integer",
            "int32": "integer",
            "int16": "integer",
            "int8": "integer",
            "float64": "float",
            "float32": "float",
            "bool": "boolean",
            "datetime64[ns]": "datetime",
            "datetime64": "datetime",
            "timedelta64[ns]": "timedelta",
            "category": "category",
        }

        # Check for datetime variants
        if dtype_str.startswith("datetime64"):
            return "datetime"
        if dtype_str.startswith("timedelta64"):
            return "timedelta"

        # Return mapped name or original dtype string
        return type_mapping.get(dtype_str, dtype_str)

    def _estimate_row_count(self, csv_file: Path, timeout: int = 5) -> int | str:
        """Estimate row count for CSV file using cross-platform approach.

        Uses fast 'wc -l' on Unix-like systems, falls back to Python counting on Windows.
        Respects timeout to prevent hanging on huge files.

        Args:
            csv_file: Path to CSV file
            timeout: Maximum seconds to spend on estimation

        Returns:
            Estimated row count (int) or "unknown" if estimation fails/times out
        """
        import os
        import time

        # Try fast path first: use wc -l on Unix-like systems (not Windows)
        if hasattr(os, "name") and os.name != "nt":
            try:
                result = subprocess.run(
                    ["wc", "-l", str(csv_file)],  # noqa: S603, S607
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=timeout,
                )
                line_count = int(result.stdout.split()[0])
                # Subtract 1 for header if present
                return max(0, line_count - 1)
            except (subprocess.SubprocessError, ValueError, IndexError):
                pass

        # Fallback: Python-only approach (cross-platform, works on Windows)
        try:
            start_time = time.time()
            line_count = 0

            with open(csv_file, encoding="utf-8", errors="ignore") as f:
                # Skip header
                next(f, None)

                # Count remaining lines until timeout
                for _ in f:
                    line_count += 1
                    if time.time() - start_time > timeout:
                        # Timeout: return unknown
                        logger.debug(f"Row counting timeout for {csv_file.name}, " "returning 'unknown'")
                        return "unknown"

            return max(0, line_count)

        except Exception as e:
            logger.debug(f"Row count estimation failed: {e}")
            return "unknown"
