"""Filesystem CSV writer for deterministic CSV output."""

from collections.abc import Iterator
import csv
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FilesystemCSVWriter:
    """Write data to CSV files with deterministic output."""

    def __init__(self, config: dict[str, Any]):
        """Initialize CSV writer.

        Args:
            config: Writer configuration with keys:
                - path: Output file path (required)
                - delimiter: Field delimiter (default: ",")
                - header: Include headers (default: true)
                - encoding: File encoding (default: "utf-8")
                - newline: Newline style "lf" or "crlf" (default: "lf")
                - quoting: Quoting strategy (default: "minimal")
                - chunk_size: Rows to buffer (default: 1000)
                - create_dirs: Create parent dirs (default: true)
        """
        self.path = Path(config["path"])
        self.delimiter = config.get("delimiter", ",")
        self.header = config.get("header", True)
        self.encoding = config.get("encoding", "utf-8")
        self.newline_style = config.get("newline", "lf")
        self.quoting = config.get("quoting", "minimal")
        self.chunk_size = config.get("chunk_size", 1000)
        self.create_dirs = config.get("create_dirs", True)

        # Map quoting strategy to csv module constants
        self.quoting_map = {
            "minimal": csv.QUOTE_MINIMAL,
            "all": csv.QUOTE_ALL,
            "nonnumeric": csv.QUOTE_NONNUMERIC,
            "none": csv.QUOTE_NONE,
        }

    def write(self, data: list[dict[str, Any]] | Iterator[dict[str, Any]]) -> dict[str, Any]:
        """Write data to CSV file.

        Args:
            data: List or iterator of dictionaries (rows)

        Returns:
            Dictionary with write statistics:
                - rows_written: Number of rows written
                - path: Output file path
                - bytes_written: File size in bytes
        """
        # Create parent directories if needed
        if self.create_dirs:
            self.path.parent.mkdir(parents=True, exist_ok=True)

        rows_written = 0
        columns = None
        buffer = []

        # Open file with proper encoding and newline handling
        # Always use newline='' for CSV module and handle line endings manually
        with open(self.path, "w", encoding=self.encoding, newline="") as f:
            writer = None

            for row in data:
                # Establish column order from first row (lexicographic)
                if columns is None:
                    columns = sorted(row.keys())
                    # Configure line terminator based on newline style
                    lineterminator = "\n" if self.newline_style == "lf" else "\r\n"
                    if self.header:
                        writer = csv.DictWriter(
                            f,
                            fieldnames=columns,
                            delimiter=self.delimiter,
                            quoting=self.quoting_map[self.quoting],
                            lineterminator=lineterminator,
                        )
                        writer.writeheader()
                    else:
                        writer = csv.DictWriter(
                            f,
                            fieldnames=columns,
                            delimiter=self.delimiter,
                            quoting=self.quoting_map[self.quoting],
                            lineterminator=lineterminator,
                        )

                # Validate row has expected columns
                row_keys = set(row.keys())
                expected_keys = set(columns)
                if row_keys != expected_keys:
                    missing = expected_keys - row_keys
                    extra = row_keys - expected_keys
                    logger.warning(
                        f"Row {rows_written + 1} has column mismatch. " f"Missing: {missing}, Extra: {extra}"
                    )
                    # Fill missing with None, ignore extra
                    for col in missing:
                        row[col] = None

                # Buffer rows for efficient writing
                buffer.append({k: row.get(k) for k in columns})

                # Write buffer when it reaches chunk size
                if len(buffer) >= self.chunk_size:
                    writer.writerows(buffer)
                    rows_written += len(buffer)
                    buffer.clear()
                    logger.debug(f"Written {rows_written} rows to {self.path}")

            # Write remaining buffer
            if buffer and writer:
                writer.writerows(buffer)
                rows_written += len(buffer)

        # Get file stats
        file_stats = self.path.stat()
        bytes_written = file_stats.st_size

        logger.info(f"Successfully wrote {rows_written} rows ({bytes_written} bytes) to {self.path}")

        return {
            "rows_written": rows_written,
            "path": str(self.path.absolute()),
            "bytes_written": bytes_written,
        }

    async def write_async(self, data: list[dict[str, Any]] | Iterator[dict[str, Any]]) -> dict[str, Any]:
        """Async wrapper for write method (delegates to sync implementation)."""
        return self.write(data)

    def run(self, data: list[dict[str, Any]] | Iterator[dict[str, Any]]) -> dict[str, Any]:
        """Alias for write method for runner compatibility."""
        return self.write(data)
