"""Filesystem CSV extractor driver implementation."""

import logging
from pathlib import Path
import subprocess
from typing import Any

import pandas as pd

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
        """Extract data from CSV file.

        Args:
            step_id: Step identifier
            config: Must contain 'path' and optional CSV parsing settings
            inputs: Not used for extractors
            ctx: Execution context for logging metrics

        Returns:
            {"df": DataFrame} with CSV data
        """
        # Get required path
        file_path = config.get("path")
        if not file_path:
            raise ValueError(f"Step {step_id}: 'path' is required in config")

        # Check if discovery mode is requested
        if config.get("discovery", False):
            return self.discover(config)

        # Resolve path
        resolved_path = self._resolve_path(file_path, ctx)

        # Validate file exists
        if not resolved_path.exists():
            raise FileNotFoundError(f"Step {step_id}: CSV file not found: {resolved_path}")

        if not resolved_path.is_file():
            raise ValueError(f"Step {step_id}: Path is not a file: {resolved_path}")

        # Extract CSV parsing options with defaults
        delimiter = config.get("delimiter", ",")
        encoding = config.get("encoding", "utf-8")

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

        try:
            # Build pandas read_csv parameters
            read_params = {
                "filepath_or_buffer": resolved_path,
                "sep": delimiter,
                "encoding": encoding,
                "header": header,
            }

            # Add optional parameters only if specified
            if columns is not None:
                read_params["usecols"] = columns
            if skip_rows is not None and skip_rows > 0:
                read_params["skiprows"] = skip_rows
            if limit is not None:
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

            # Read CSV file
            logger.info(f"Step {step_id}: Reading CSV from {resolved_path}")
            df = pd.read_csv(**read_params)

            # Reorder columns if specific columns were requested
            if columns is not None and isinstance(columns, list):
                # Preserve the order specified in columns parameter
                df = df[columns]

            # Log metrics
            rows_read = len(df)
            logger.info(f"Step {step_id}: Read {rows_read} rows from CSV file")

            if ctx and hasattr(ctx, "log_metric"):
                ctx.log_metric("rows_read", rows_read, tags={"step": step_id})

            return {"df": df}

        except pd.errors.EmptyDataError:
            # Return empty DataFrame for empty files
            logger.warning(f"Step {step_id}: CSV file is empty: {resolved_path}")
            df = pd.DataFrame()

            if ctx and hasattr(ctx, "log_metric"):
                ctx.log_metric("rows_read", 0, tags={"step": step_id})

            return {"df": df}

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

    def _resolve_path(self, file_path: str, ctx: Any) -> Path:
        """Resolve file path to absolute Path object.

        Uses ctx.base_path for relative paths if available, otherwise uses cwd.
        E2B COMPATIBLE - never uses Path.home().

        Args:
            file_path: Path string (absolute or relative)
            ctx: Execution context (may have base_path attribute)

        Returns:
            Resolved absolute Path object
        """
        path = Path(file_path)

        # If already absolute, use as-is
        if path.is_absolute():
            return path

        # For relative paths, resolve to ctx.base_path if available
        if ctx and hasattr(ctx, "base_path"):
            return ctx.base_path / path

        # Fallback to current working directory
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

    def discover(self, config: dict) -> dict:
        """Discover CSV files in a directory.

        Args:
            config: Configuration dict with 'path' (directory path)

        Returns:
            Dict with discovered files and metadata
        """
        results = {"files": [], "status": "success"}

        try:
            # Get directory path
            dir_path = config.get("path", ".")
            directory = Path(dir_path)

            if not directory.is_absolute():
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

                # Try to get column count from sample
                try:
                    df_sample = pd.read_csv(csv_file, nrows=1)
                    file_info["columns"] = len(df_sample.columns)
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
