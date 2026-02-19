"""Test harness for DuckDB streaming prototype.

This module provides a mock execution context and database setup utilities
for testing DuckDB streaming components in isolation.
"""

from pathlib import Path
from typing import Any

import duckdb
from duckdb_helpers import get_shared_db_path


class MockContext:
    """Mock execution context for testing drivers.

    This class implements the minimal context interface required by Osiris drivers,
    providing database connections, metric logging, and output directory access.

    Attributes:
        session_dir: Path to the session directory
        metrics: Dictionary storing logged metrics
        db_connection: Cached DuckDB connection
    """

    def __init__(self, session_dir: Path):
        """Initialize the mock context.

        Args:
            session_dir: Path to the session directory where database and outputs are stored
        """
        self.session_dir = session_dir
        self.metrics: dict[str, list[Any]] = {}
        self._db_connection: duckdb.DuckDBPyConnection | None = None
        self._output_dir = session_dir / "output"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def get_db_connection(self) -> duckdb.DuckDBPyConnection:
        """Get or create a connection to the shared DuckDB database.

        Returns a connection to pipeline_data.duckdb in the session directory.
        The connection is cached and reused across calls.

        Returns:
            Active DuckDB connection

        Example:
            >>> ctx = MockContext(Path("/tmp/session"))
            >>> con = ctx.get_db_connection()
            >>> con.execute("CREATE TABLE test (id INT)")
        """
        if self._db_connection is None:
            db_path = get_shared_db_path(self.session_dir)
            self._db_connection = duckdb.connect(str(db_path))
        return self._db_connection

    def log_metric(self, name: str, value: Any, **kwargs) -> None:
        """Log a metric for later verification.

        Metrics are stored in a dictionary with metric names as keys and
        lists of values as values (to support multiple calls with the same name).

        Args:
            name: Metric name (e.g., "rows_read", "rows_written")
            value: Metric value (typically int or float)
            **kwargs: Additional metadata (stored but not currently used)

        Example:
            >>> ctx = MockContext(Path("/tmp/session"))
            >>> ctx.log_metric("rows_read", 100)
            >>> ctx.log_metric("rows_written", 95)
            >>> print(ctx.metrics)
            {'rows_read': [100], 'rows_written': [95]}
        """
        if name not in self.metrics:
            self.metrics[name] = []
        self.metrics[name].append(value)

    @property
    def output_dir(self) -> Path:
        """Get the output directory path.

        Returns:
            Path to the output directory within the session directory

        Example:
            >>> ctx = MockContext(Path("/tmp/session"))
            >>> print(ctx.output_dir)
            /tmp/session/output
        """
        return self._output_dir

    def get_metric_values(self, name: str) -> list[Any]:
        """Get all logged values for a specific metric.

        Args:
            name: Metric name

        Returns:
            List of values logged for this metric (empty list if never logged)

        Example:
            >>> ctx = MockContext(Path("/tmp/session"))
            >>> ctx.log_metric("rows_read", 100)
            >>> ctx.log_metric("rows_read", 200)
            >>> print(ctx.get_metric_values("rows_read"))
            [100, 200]
        """
        return self.metrics.get(name, [])

    def get_last_metric_value(self, name: str, default: Any = None) -> Any:
        """Get the most recently logged value for a specific metric.

        Args:
            name: Metric name
            default: Value to return if metric was never logged

        Returns:
            Most recent value for this metric, or default if not found

        Example:
            >>> ctx = MockContext(Path("/tmp/session"))
            >>> ctx.log_metric("rows_read", 100)
            >>> ctx.log_metric("rows_read", 200)
            >>> print(ctx.get_last_metric_value("rows_read"))
            200
        """
        values = self.metrics.get(name, [])
        return values[-1] if values else default

    def close(self) -> None:
        """Close the database connection if open.

        This should be called when done with the context to clean up resources.

        Example:
            >>> ctx = MockContext(Path("/tmp/session"))
            >>> con = ctx.get_db_connection()
            >>> # ... do work ...
            >>> ctx.close()
        """
        if self._db_connection is not None:
            self._db_connection.close()
            self._db_connection = None


def setup_test_db(session_dir: Path) -> Path:
    """Create a fresh DuckDB database for testing.

    Creates the session directory if it doesn't exist and initializes
    an empty DuckDB database file.

    Args:
        session_dir: Path to the session directory

    Returns:
        Path to the created database file

    Example:
        >>> session_dir = Path("/tmp/test_session")
        >>> db_path = setup_test_db(session_dir)
        >>> print(db_path.exists())
        True
    """
    # Create session directory if it doesn't exist
    session_dir.mkdir(parents=True, exist_ok=True)

    # Get database path
    db_path = get_shared_db_path(session_dir)

    # Remove existing database if present
    if db_path.exists():
        db_path.unlink()

    # Create new database (connection creation initializes the file)
    con = duckdb.connect(str(db_path))
    con.close()

    return db_path


def cleanup_test_db(session_dir: Path) -> None:
    """Remove the test database and session directory.

    Cleans up all files in the session directory, including the database file.
    If the directory doesn't exist, this function does nothing.

    Args:
        session_dir: Path to the session directory to clean up

    Example:
        >>> session_dir = Path("/tmp/test_session")
        >>> setup_test_db(session_dir)
        >>> cleanup_test_db(session_dir)
        >>> print(session_dir.exists())
        False
    """
    if not session_dir.exists():
        return

    # Remove database file
    db_path = get_shared_db_path(session_dir)
    if db_path.exists():
        db_path.unlink()

    # Remove output directory if it exists
    output_dir = session_dir / "output"
    if output_dir.exists():
        # Remove files in output directory
        for file_path in output_dir.iterdir():
            if file_path.is_file():
                file_path.unlink()
        output_dir.rmdir()

    # Remove session directory if empty
    try:
        session_dir.rmdir()
    except OSError:
        # Directory not empty - leave it
        pass
