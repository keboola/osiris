"""cf-ng call step: execute one tool and land its result as a DuckDB table.

Results arrive as JSON and must become a relation without pandas, which is
deliberately not a dependency. The route taken is DuckDB's own JSON reader over
a newline-delimited artifact written under `ctx.output_dir`: it unions the keys
of heterogeneous rows, maps nested values to STRUCT/LIST, falls back to a JSON
column when a key's type is inconsistent, and reads the payload off disk rather
than holding a second copy of it in the process. The artifact is durable
evidence of exactly what the tool returned.

Rows are redacted before they are written, which is also before the table is
built from them — the DuckDB file is materialized from the artifact, so there is
no second place to clean up afterwards and nothing to clean up in a file format
that cannot be grepped and patched.
"""

from collections.abc import Iterable, Sequence
import json
from pathlib import Path
from typing import Any

import duckdb

from osiris.cfng.client import CfngClient, CfngError
from osiris.evidence.session import ambient_secrets, redact
from osiris.plan.model import Step
from osiris.run.context import RunContext
from osiris.run.steps.sql import StepError, quote_ident, substitute

ARTIFACT_SUFFIX = ".ndjson"

# -1 makes DuckDB infer the schema from every row rather than a leading sample,
# so a key that only appears late in a large result still becomes a column.
SCHEMA_SAMPLE_SIZE = -1

# Result envelopes that wrap the actual rows under a well-known key.
ROW_ENVELOPE_KEYS = ("rows", "records", "items", "data")


def _as_rows(result: Any) -> list[dict[str, Any]]:
    """Normalize a tool result into rows. Scalars and dicts become one row."""
    if isinstance(result, list):
        return [r if isinstance(r, dict) else {"value": r} for r in result]
    if isinstance(result, dict):
        for key in ROW_ENVELOPE_KEYS:
            if isinstance(result.get(key), list):
                return _as_rows(result[key])
        return [result]
    return [{"value": result}]


def _artifact_path(ctx: RunContext, step_id: str) -> Path:
    """Where this step's raw rows are kept.

    `Path(...).name` strips any directory components a step id might carry, so
    the artifact cannot be written outside the run's own artifact directory.
    """
    name = Path(step_id).name or "step"
    return ctx.output_dir / f"{name}{ARTIFACT_SUFFIX}"


def _redaction_secrets(ctx: RunContext) -> list[str]:
    """Secrets to strip from anything this step writes.

    Both sources are needed: the session may carry a secret that was never an
    environment variable, and a caller may hold one the session was never told
    about. Note that neither is load-bearing on its own — `redact()` also
    applies a credential-shape rule with no secrets at all — but a token this
    process actually holds should never depend on a pattern recognising it.
    """
    declared = ctx.secrets
    return declared + [s for s in ambient_secrets() if s not in declared]


def write_ndjson(rows: Iterable[dict[str, Any]], path: Path, secrets: Sequence[str]) -> int:
    """Stream rows to newline-delimited JSON, redacted. Returns the number written.

    Serialization is per row, so the encoder never holds the whole payload as a
    second in-memory copy. `ensure_ascii=False` keeps unicode intact; the file
    is UTF-8, which is what DuckDB's JSON reader expects.

    `secrets` is required rather than defaulted: an empty default would let a
    future caller lose redaction by forgetting an argument, and this function's
    output is read straight into the DuckDB file.

    Tradeoff, stated plainly: this redacts *result data*, so a legitimate payload
    that genuinely contains the token substring is corrupted into `***` — the
    artifact then misrepresents what the tool returned, which is the one thing it
    exists to record. That is accepted because a live credential appearing in a
    tool result is far more likely to be a leak (an error echoing the presented
    header, a config endpoint reflecting it back) than a coincidence, and because
    the failure directions are not symmetric: a corrupted cell is visible and
    recoverable by re-running, a leaked credential on disk is neither.
    """
    written = 0
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            safe = redact(row, secrets)
            fh.write(json.dumps(safe, ensure_ascii=False, separators=(",", ":")) + "\n")
            written += 1
    return written


def materialize_rows(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    rows: Iterable[dict[str, Any]],
    artifact: Path,
    secrets: Sequence[str],
) -> int:
    """Land rows as `table`, writing `artifact` on the way. Returns the row count.

    An empty result gets an explicit empty table rather than whatever the JSON
    reader infers from an empty file, so downstream steps see a predictable
    shape instead of a schema that depends on the absence of data.

    Redaction happens here, in the artifact, and the table is then built from
    that file — so the DuckDB pages never hold the secret in the first place.
    Redacting a .duckdb after the fact is not possible.
    """
    written = write_ndjson(rows, artifact, secrets)
    ident = quote_ident(table)
    if written == 0:
        conn.execute(f"CREATE OR REPLACE TABLE {ident} AS SELECT NULL AS value WHERE false")
        return 0
    conn.execute(
        # `ident` is quote_ident'd; the path and sample size are bound parameters,
        # so nothing else is interpolated.
        f"CREATE OR REPLACE TABLE {ident} AS "  # nosec B608
        "SELECT * FROM read_json_auto(?, format='newline_delimited', sample_size=?)",
        [str(artifact), SCHEMA_SAMPLE_SIZE],
    )
    return written


def run_cfng_call(step: Step, ctx: RunContext, client: CfngClient, params: dict[str, Any]) -> dict[str, Any]:
    connector = step.with_.get("connector")
    tool = step.with_.get("tool")
    if not connector or not tool:
        raise StepError(step.id, "cfng_call requires 'connector' and 'tool'")

    arguments = substitute(step.with_.get("args") or {}, params)
    secrets = _redaction_secrets(ctx)
    try:
        body = client.call_tool(str(connector), str(tool), arguments)
    except CfngError as exc:
        # cf-ng's detail is echoed back by the server and a 401/403 commonly
        # quotes the credential that was presented. This message ends up in the
        # ledger, in events.jsonl and on stdout, so it is redacted at the point
        # it is constructed rather than at each of the three sinks.
        detail = redact(exc.detail, secrets)
        raise StepError(step.id, f"{detail} (status {exc.status}, retryable={exc.retryable})") from exc

    rows = _as_rows(body.get("result"))
    artifact = _artifact_path(ctx, step.id)
    try:
        written = materialize_rows(ctx.get_db_connection(), step.id, rows, artifact, secrets)
    except Exception as exc:
        # DuckDB quotes the offending value in its errors, so this message can
        # carry a row back out of the payload that was just redacted.
        raise StepError(step.id, f"could not land the tool result as a table: {redact(str(exc), secrets)}") from exc

    ctx.log_metric("rows_read", written, step=step.id)
    ctx.log_metric("server_ms", float(body.get("_meta", {}).get("server_ms", 0.0)), step=step.id)
    return {"table": step.id, "rows": written}
