"""SQL step: a declarative transformation over the run's DuckDB tables."""

import re
from typing import Any

from osiris.plan.model import Step
from osiris.run.context import RunContext

_PARAM = re.compile(r"\$\{params\.([A-Za-z_][A-Za-z0-9_]*)\}")


class StepError(Exception):
    """A step failed. Carries the step id so evidence and the CLI can name it."""

    def __init__(self, step_id: str, message: str) -> None:
        super().__init__(f"step '{step_id}': {message}")
        self.step_id = step_id


def quote_ident(name: str) -> str:
    """Quote an identifier built from plan data.

    Step ids are author-supplied strings, not SQL identifiers: `fetch`, `order`
    and `select` are all plausible step names and all reserved words in DuckDB,
    so an unquoted `CREATE TABLE fetch` is a parser error. Embedded double
    quotes are doubled, which is what makes the interpolation safe rather than
    merely conventional.
    """
    escaped = str(name).replace('"', '""')
    return f'"{escaped}"'


def substitute(value: Any, params: dict[str, Any]) -> Any:
    """Replace ${params.x} references. A whole-string reference keeps the param's type."""
    if isinstance(value, str):
        whole = _PARAM.fullmatch(value)
        if whole:
            return params.get(whole.group(1))
        return _PARAM.sub(lambda m: str(params.get(m.group(1), m.group(0))), value)
    if isinstance(value, dict):
        return {k: substitute(v, params) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute(v, params) for v in value]
    return value


def run_sql(step: Step, ctx: RunContext, params: dict[str, Any]) -> dict[str, Any]:
    query = substitute(step.with_.get("query"), params)
    if not query:
        raise StepError(step.id, "sql step requires 'query'")
    conn = ctx.get_db_connection()
    table = quote_ident(step.id)
    try:
        conn.execute(f"CREATE OR REPLACE TABLE {table} AS {query}")
        rows = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    except Exception as exc:
        raise StepError(step.id, str(exc)) from exc
    ctx.log_metric("rows_written", int(rows), step=step.id)
    return {"table": step.id, "rows": int(rows)}
