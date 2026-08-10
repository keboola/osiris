"""The run context handed to every step.

One class, constructed once by the runner. v0.5.4 had two divergent inline
context classes and neither provided get_db_connection(), so every driver
raised AttributeError. Steps depend on this seam and nothing else.
"""

from pathlib import Path
from typing import Any

import duckdb

from osiris.evidence.session import Session

DB_FILENAME = "pipeline_data.duckdb"


class RunContext:
    """Shared DuckDB connection, artifact directory, and metric sink for one run."""

    def __init__(self, run_dir: Path, session: Session) -> None:
        self._run_dir = Path(run_dir)
        self._run_dir.mkdir(parents=True, exist_ok=True)
        self._session = session
        self._conn: duckdb.DuckDBPyConnection | None = None
        self.output_dir = self._run_dir / "artifacts"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def db_path(self) -> Path:
        """On-disk data bus. Steps exchange tables here, so volume is bounded by disk, not RAM."""
        return self._run_dir / DB_FILENAME

    def get_db_connection(self) -> duckdb.DuckDBPyConnection:
        """The shared connection for this run, opened lazily.

        DuckDB takes an exclusive lock on the file, so exactly one RunContext
        may hold it open at a time. The runner builds one per run.
        """
        if self._conn is None:
            self._conn = duckdb.connect(str(self.db_path))
        return self._conn

    def log_metric(self, name: str, value: float, **fields: Any) -> None:
        self._session.log_metric(name, value, **fields)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "RunContext":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
