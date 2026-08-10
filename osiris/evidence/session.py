"""Session-scoped evidence: two append-only JSONL streams, redacted at write time.

This module owns the single redaction seam. Anything that writes to disk under
base_path — evidence streams, the run ledger, step artifacts — routes its
payload through `redact()` here rather than growing its own ad-hoc filter.

`redact()` applies two independent rules, in this order:

1. **Shape.** Anything carrying a vendor credential prefix is masked whether or
   not this process has ever seen the value. See `SECRET_SHAPED`.
2. **Value.** Every string in `secrets` is replaced wherever it occurs.

Shape runs first on purpose. A `secrets` entry that happens to be a *substring*
of a longer credential would otherwise punch a hole in the middle of it and
leave both ends readable — masking `cfng_XXXdefgh12` rather than the whole token.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
from typing import Any

REDACTED = "***"
_REDACTED_BYTES = REDACTED.encode("ascii")

# Credential *shapes*, masked whether or not this process holds the value.
#
# Exact-substring redaction can only ever cover the one credential Osiris was
# started with. Everything a third party hands us is a credential this process
# has never seen and cannot match by value: the `credentials` argument the cf-ng
# gateway injects into every tool's inputSchema by design (see
# `osiris/cfng/client.py`), a token another agent pasted into a tool argument, a
# token a cf-ng rejection quotes back. Those reached events.jsonl and runs.jsonl
# verbatim — in the same sentence where our own token showed as ***.
#
# Where the line is drawn between a credential and ordinary text, and why:
#
#   * **Prefix-anchored, never entropy-based.** Nothing is masked for being long
#     or random-looking. Evidence is full of long opaque strings that have to
#     survive intact — sha256 fingerprints, run ids, schema hashes, base64
#     payloads — and an entropy rule would hollow out the record to protect
#     nothing. Only a literal vendor prefix qualifies.
#   * **The prefix must begin a token.** The lookbehind stops `sk-` from firing
#     inside `task-`, `disk-`, `risk-`.
#   * **A minimum body length.** `cfng_call` — the plan's own `uses` value, which
#     is in every event this engine writes — is 4 characters past the prefix and
#     is not a credential.
#   * **The match ends at the first character outside the credential alphabet,
#     and must end *on* an alphanumeric or `=`.** A token embedded in JSON or in
#     a sentence is therefore masked exactly: the quote, comma, brace or full
#     stop around it is left alone, so redacted evidence stays parseable and
#     readable rather than being chewed up around the edges.
#
# The residual false positive is a lowercase identifier that genuinely starts
# with `cfng_` and runs 8 further characters — `cfng_base_url` written in prose
# would become ***. That is accepted deliberately. The discriminator that would
# save it (demand mixed case plus a digit, i.e. "looks random") also lets an
# all-lowercase credential such as `cfng_realsecretvalue` through, and a masked
# word in a log line costs an operator a re-read while a leaked credential costs
# a rotation.
_CREDENTIAL_SHAPES = (
    # cf-ng: the flat form and the `cfng_v1.<base64url>` form. The `.`, `+`, `/`
    # and `=` are exactly what a `[A-Za-z0-9_\-]{8,}` body could not see, which
    # is how a real-shaped token walked past the freeze-time guard.
    r"cfng_[A-Za-z0-9_.+/=\-]{7,}[A-Za-z0-9=]",
    # OpenAI, including the `sk-proj-` family — hence `-` inside the body.
    r"sk-[A-Za-z0-9_\-]{15,}[A-Za-z0-9]",
    # Slack bot/app/user/refresh tokens.
    r"xox[baprs]-[A-Za-z0-9_.\-]{9,}[A-Za-z0-9]",
)
SECRET_SHAPED = re.compile(r"(?<![A-Za-z0-9_])(?:" + "|".join(_CREDENTIAL_SHAPES) + r")")

# The same rule over bytes. `redact()` accepts bytes, and a shape rule that only
# knew about `str` would mask a token in events.jsonl and miss the identical one
# in a binary artifact. Derived from the one pattern above rather than written
# twice, so the two can never disagree; the source is pure ASCII by construction.
_SECRET_SHAPED_BYTES = re.compile(SECRET_SHAPED.pattern.encode("ascii"))

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
    value = SECRET_SHAPED.sub(REDACTED, value)
    for secret in live:
        value = value.replace(secret, REDACTED)
    return value


def _redact_bytes(value: bytes | bytearray, live: list[str]) -> bytes:
    out = _SECRET_SHAPED_BYTES.sub(_REDACTED_BYTES, bytes(value))
    for secret in live:
        out = out.replace(secret.encode("utf-8", "surrogateescape"), _REDACTED_BYTES)
    return out


def _redact(value: Any, live: list[str], depth: int) -> Any:
    if depth > MAX_REDACT_DEPTH:
        return REDACTED
    if isinstance(value, str):
        return _redact_str(value, live)
    if isinstance(value, bytes | bytearray):
        # Bytes never reach json.dumps, but a caller may hand them to redact()
        # directly; falling through would return the secret untouched.
        return _redact_bytes(value, live)
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
    """Mask every credential-shaped run and every occurrence of each secret.

    Total and side-effect-free for any acyclic value: nothing is mutated in
    place, every input maps to a value of the same JSON shape, and no branch
    raises. Strings, bytes, dict keys, dict values, lists, tuples and sets are
    all walked; anything else (int, float, bool, None) cannot carry a substring
    and is returned as-is.

    The walk runs even when `secrets` is empty. It used to return `value`
    untouched in that case, which was the whole leak: a writer that holds no
    credential is exactly the one most likely to be handed somebody else's.
    """
    return _redact(value, _live(secrets), 0)


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
