"""Append-only run ledger.

One JSON object per line. Appends take an exclusive advisory lock and fsync,
so concurrent writers cannot interleave a partial line.

Every record is redacted on the way out. `RunRecord.error` carries a cf-ng
error verbatim, and a 403 from cf-ng echoes the credential that was presented:
without this the ledger held in plaintext the same sentence that events.jsonl
already wrote as `***`.
"""

from collections.abc import Sequence
import json
import os
from pathlib import Path

from pydantic import BaseModel

from osiris.evidence.session import ambient_secrets, redact

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

    def __init__(self, path: Path, *, secrets: Sequence[str] | None = None) -> None:
        """`secrets` is keyword-only and optional so `RunIndex(path)` keeps working.

        Omitting it does not mean "write in the clear": it means "redact whatever
        credential this process is holding", resolved from the environment at
        append time. A caller that knows better passes the list explicitly, and
        an explicit empty list genuinely disables redaction.
        """
        self._path = Path(path)
        self._secrets = list(secrets) if secrets is not None else None

    def _redaction_secrets(self) -> list[str]:
        """Resolved per append, not per construction: the ledger outlives the
        moment it was opened, and the credential may be set after that."""
        return self._secrets if self._secrets is not None else ambient_secrets()

    def append(self, record: RunRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = redact(record.model_dump(), self._redaction_secrets())
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
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
