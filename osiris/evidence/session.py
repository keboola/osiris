"""Session-scoped evidence: two append-only JSONL streams, redacted at write time.

This module owns the single redaction seam. Anything that writes to disk under
base_path — evidence streams, the run ledger, step artifacts — routes its
payload through `redact()` here rather than growing its own ad-hoc filter.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Any

REDACTED = "***"

# Environment variables that hold a live credential. `ambient_secrets()` reads
# them so a writer constructed without an explicit secret list still redacts the
# credential this process is actually holding. Names only, never values.
SECRET_ENV_VARS = ("CFNG_TOKEN",)  # nosec B105 - the names of variables, never their values

# Deepest container level `redact()` will walk. Beyond it the branch is replaced
# wholesale by REDACTED rather than returned unredacted: a value nested 64 deep
# is not legitimate evidence, and collapsing it keeps the function total (no
# RecursionError) while failing in the safe direction.
MAX_REDACT_DEPTH = 64


def ambient_secrets() -> list[str]:
    """Credentials this process holds, discovered from the environment.

    Used as the fallback for writers that were not handed an explicit secret
    list. It is a backstop, not a substitute: an explicit list still wins,
    because a session may carry secrets that were never environment variables.
    """
    return [value for name in SECRET_ENV_VARS if (value := os.environ.get(name))]


def _live(secrets: Sequence[Any] | None) -> list[str]:
    """The non-empty string secrets in `secrets`. Tolerates None entries."""
    return [s for s in (secrets or []) if isinstance(s, str) and s]


def _redact_str(value: str, live: list[str]) -> str:
    for secret in live:
        value = value.replace(secret, REDACTED)
    return value


def _redact(value: Any, live: list[str], depth: int) -> Any:
    if depth > MAX_REDACT_DEPTH:
        return REDACTED
    if isinstance(value, str):
        return _redact_str(value, live)
    if isinstance(value, bytes | bytearray):
        # Bytes never reach json.dumps, but a caller may hand them to redact()
        # directly; falling through would return the secret untouched.
        out = bytes(value)
        for secret in live:
            out = out.replace(secret.encode("utf-8", "surrogateescape"), REDACTED.encode())
        return out
    if isinstance(value, dict):
        # Keys as well as values: the agent chooses the keys of the MCP
        # arguments it sends, so `{token: "x"}` is exactly as reachable as
        # `{"x": token}` and the old code redacted only the latter.
        return {_redact_key(k, live): _redact(v, live, depth + 1) for k, v in value.items()}
    if isinstance(value, list | tuple):
        # A tuple is serialized by json.dumps as an array, so it must be walked;
        # the old fallthrough `return value` wrote tuple contents verbatim.
        # The result is a list because that is the shape it serializes to anyway.
        return [_redact(v, live, depth + 1) for v in value]
    if isinstance(value, set | frozenset):
        # Sorted by their redacted string form: set iteration order depends on
        # PYTHONHASHSEED, and evidence must not.
        return sorted((_redact(v, live, depth + 1) for v in value), key=repr)
    return value


def _redact_key(key: Any, live: list[str]) -> Any:
    """Redact a mapping key.

    Only string keys are rewritten. Redacting a non-string key could return an
    unhashable value (a tuple key would become a list) and turn a total function
    into one that raises; non-string keys are also not JSON-encodable as-is, so
    there is nothing to protect there.
    """
    return _redact_str(key, live) if isinstance(key, str) else key


def redact(value: Any, secrets: Sequence[Any] | None) -> Any:
    """Replace every occurrence of each secret, recursing through containers.

    Total and side-effect-free for any acyclic value: nothing is mutated in
    place, every input maps to a value of the same JSON shape, and no branch
    raises. Strings, bytes, dict keys, dict values, lists, tuples and sets are
    all walked; anything else (int, float, bool, None) cannot carry a substring
    and is returned as-is.
    """
    live = _live(secrets)
    if not live:
        return value
    return _redact(value, live, 0)


class Session:
    """Append-only evidence for one exploration session or one run."""

    def __init__(self, directory: Path, session_id: str, secrets: Sequence[str] | None = None) -> None:
        self.session_id = session_id
        self._secrets = list(secrets or [])
        self._dir = Path(directory) / session_id
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def directory(self) -> Path:
        return self._dir

    @property
    def secrets(self) -> list[str]:
        """The secrets this session redacts. Exposed so that other writers in
        the same run (step artifacts, the ledger) can strip the same values."""
        return list(self._secrets)

    def redact(self, value: Any) -> Any:
        """Apply this session's redaction to an arbitrary payload."""
        return redact(value, self._secrets)

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
