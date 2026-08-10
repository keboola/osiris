"""Session-scoped evidence: two append-only JSONL streams, redacted at write time."""

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

REDACTED = "***"


def redact(value: Any, secrets: list[str]) -> Any:
    """Replace every occurrence of each secret, recursing through containers."""
    live = [s for s in secrets if s]
    if not live:
        return value
    if isinstance(value, str):
        for secret in live:
            value = value.replace(secret, REDACTED)
        return value
    if isinstance(value, dict):
        return {k: redact(v, live) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, live) for v in value]
    return value


class Session:
    """Append-only evidence for one exploration session or one run."""

    def __init__(self, directory: Path, session_id: str, secrets: list[str] | None = None) -> None:
        self.session_id = session_id
        self._secrets = list(secrets or [])
        self._dir = Path(directory) / session_id
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def directory(self) -> Path:
        return self._dir

    def _append(self, filename: str, record: dict[str, Any]) -> None:
        record = {
            "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "session_id": self.session_id,
            **record,
        }
        safe = redact(record, self._secrets)
        line = json.dumps(safe, ensure_ascii=False, separators=(",", ":")) + "\n"
        with (self._dir / filename).open("a", encoding="utf-8") as fh:
            fh.write(line)

    def log_event(self, event: str, **fields: Any) -> None:
        self._append("events.jsonl", {"event": event, **fields})

    def log_metric(self, name: str, value: float, **fields: Any) -> None:
        self._append("metrics.jsonl", {"name": name, "value": value, **fields})

    def _read(self, filename: str) -> list[dict[str, Any]]:
        path = self._dir / filename
        if not path.exists():
            return []
        out: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def read_events(self) -> list[dict[str, Any]]:
        return self._read("events.jsonl")

    def read_metrics(self) -> list[dict[str, Any]]:
        return self._read("metrics.jsonl")
