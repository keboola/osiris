"""Assert step: halt the run when a precondition does not hold."""

from typing import Any

from osiris.plan.model import Step
from osiris.run.context import RunContext
from osiris.run.steps.sql import StepError, quote_ident, substitute


def run_assert(step: Step, ctx: RunContext, params: dict[str, Any]) -> dict[str, Any]:
    min_rows = int(step.with_.get("min_rows", 1))
    table = step.with_.get("table")
    query = substitute(step.with_.get("query"), params)
    if not table and not query:
        raise StepError(step.id, "assert requires 'table' or 'query'")

    conn = ctx.get_db_connection()
    # Identifier is quote_ident'd; `query` is the plan author's SQL, and the plan is
    # fingerprint-verified before the run starts.
    sql = f"SELECT count(*) FROM {quote_ident(table)}" if table else f"SELECT count(*) FROM ({query})"  # nosec B608
    try:
        rows = int(conn.execute(sql).fetchone()[0])
    except Exception as exc:
        raise StepError(step.id, str(exc)) from exc

    if rows < min_rows:
        raise StepError(step.id, f"expected at least {min_rows} row(s), got {rows}")
    ctx.log_metric("asserted_rows", rows, step=step.id)
    return {"table": None, "rows": rows}
