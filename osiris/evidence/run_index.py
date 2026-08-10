"""Append-only run ledger.

One JSON object per line. Appends take an exclusive advisory lock and fsync,
so concurrent writers cannot interleave a partial line.
"""

import json
import os
from pathlib import Path

from pydantic import BaseModel

try:  # pragma: no cover - platform dependent
    import fcntl

    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover - Windows
    _HAVE_FCNTL = False


class RunRecord(BaseModel):
    """One row of the run ledger."""

    run_id: str
    plan_name: str
    manifest_hash: str
    started_at: str
    finished_at: str | None = None
    status: str = "running"
    error: str | None = None


class RunIndex:
    """Append-only JSONL ledger of runs."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def append(self, record: RunRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record.model_dump(), ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._path.open("a", encoding="utf-8") as fh:
            if _HAVE_FCNTL:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())
            finally:
                if _HAVE_FCNTL:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    def read_all(self) -> list[RunRecord]:
        """All records in append order. A corrupt line is skipped, not fatal."""
        if not self._path.exists():
            return []
        records: list[RunRecord] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                records.append(RunRecord(**json.loads(line)))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        return records

    def latest(self, n: int = 1) -> list[RunRecord]:
        """The n most recent records, newest first."""
        return list(reversed(self.read_all()))[:n]
