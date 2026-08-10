"""cf-ng call step: execute one tool and land its result as a DuckDB table.

Results arrive as JSON and must become a relation without pandas, which is
deliberately not a dependency. The route taken is DuckDB's own JSON reader over
a newline-delimited artifact written under `ctx.output_dir`: it unions the keys
of heterogeneous rows, maps nested values to STRUCT/LIST, falls back to a JSON
column when a key's type is inconsistent, and reads the payload off disk rather
than holding a second copy of it in the process. The artifact is durable
evidence of exactly what the tool returned.
"""

from collections.abc import Iterable
import json
from pathlib import Path
from typing import Any

import duckdb

from osiris.cfng.client import CfngClient, CfngError
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


def write_ndjson(rows: Iterable[dict[str, Any]], path: Path) -> int:
    """Stream rows to newline-delimited JSON. Returns the number written.

    Serialization is per row, so the encoder never holds the whole payload as a
    second in-memory copy. `ensure_ascii=False` keeps unicode intact; the file
    is UTF-8, which is what DuckDB's JSON reader expects.
    """
    written = 0
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            written += 1
    return written


def materialize_rows(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    rows: Iterable[dict[str, Any]],
    artifact: Path,
) -> int:
    """Land rows as `table`, writing `artifact` on the way. Returns the row count.

    An empty result gets an explicit empty table rather than whatever the JSON
    reader infers from an empty file, so downstream steps see a predictable
    shape instead of a schema that depends on the absence of data.
    """
    written = write_ndjson(rows, artifact)
    ident = quote_ident(table)
    if written == 0:
        conn.execute(f"CREATE OR REPLACE TABLE {ident} AS SELECT NULL AS value WHERE false")
        return 0
    conn.execute(
        f"CREATE OR REPLACE TABLE {ident} AS "
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
    try:
        body = client.call_tool(str(connector), str(tool), arguments)
    except CfngError as exc:
        raise StepError(step.id, f"{exc.detail} (status {exc.status}, retryable={exc.retryable})") from exc

    rows = _as_rows(body.get("result"))
    artifact = _artifact_path(ctx, step.id)
    try:
        written = materialize_rows(ctx.get_db_connection(), step.id, rows, artifact)
    except Exception as exc:
        raise StepError(step.id, f"could not land the tool result as a table: {exc}") from exc

    ctx.log_metric("rows_read", written, step=step.id)
    ctx.log_metric("server_ms", float(body.get("_meta", {}).get("server_ms", 0.0)), step=step.id)
    return {"table": step.id, "rows": written}
