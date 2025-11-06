"""Filesystem CSV writer driver implementation."""

import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


class FilesystemCsvWriterDriver:
    """Driver for writing DataFrames to CSV files."""

    def run(self, *, step_id: str, config: dict, inputs: dict | None = None, ctx: Any = None) -> dict:
        """Write DataFrame to CSV file.

        Args:
            step_id: Step identifier
            config: Must contain 'path' and optional CSV settings
            inputs: Must contain 'df' key with DataFrame to write
            ctx: Execution context for logging metrics

        Returns:
            {} (empty dict for writers)
        """
        # Validate inputs - find DataFrame in df_* keys
        if not inputs:
            raise ValueError(f"Step {step_id}: FilesystemCsvWriterDriver requires inputs with DataFrame")

        # Find the DataFrame (should be in df_* key from upstream processor/extractor)
        df = None
        df_key = None
        for key, value in inputs.items():
            if key.startswith("df_") and isinstance(value, pd.DataFrame):
                df = value
                df_key = key
                break

        if df is None:
            raise ValueError(
                f"Step {step_id}: FilesystemCsvWriterDriver requires DataFrame input. "
                f"Expected key starting with 'df_'. Got: {list(inputs.keys())}"
            )

        logger.debug(f"Step {step_id}: Using DataFrame from {df_key} ({len(df)} rows)")

        # Get configuration
        file_path = config.get("path")
        if not file_path:
            raise ValueError(f"Step {step_id}: 'path' is required in config")

        # CSV options with defaults
        delimiter = config.get("delimiter", ",")
        encoding = config.get("encoding", "utf-8")
        header = config.get("header", True)
        newline_config = config.get("newline", "lf")

        # Resolve path
        output_path = Path(file_path)
        if not output_path.is_absolute():
            # Make relative to current working directory
            output_path = Path.cwd() / output_path

        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Sort columns lexicographically for deterministic output
        df_sorted = df[sorted(df.columns)]

        # Map newline config to actual character
        newline_map = {"lf": "\n", "crlf": "\r\n", "cr": "\r"}
        lineterminator = newline_map.get(newline_config, "\n")

        # Write CSV
        logger.info(f"Writing CSV to {output_path}")
        df_sorted.to_csv(
            output_path,
            sep=delimiter,
            encoding=encoding,
            header=header,
            index=False,
            lineterminator=lineterminator,
        )

        # Log metrics
        rows_written = len(df)
        logger.info(f"Step {step_id}: Wrote {rows_written} rows to {output_path}")

        if ctx and hasattr(ctx, "log_metric"):
            ctx.log_metric("rows_written", rows_written)

        return {}
