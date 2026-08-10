"""Each step type reads and writes DuckDB tables addressed by step id."""

import json

import httpx
import pytest

from osiris.cfng.client import CfngClient
from osiris.evidence.session import Session
from osiris.plan.model import Step
from osiris.run.context import RunContext
from osiris.run.steps.assert_step import run_assert
from osiris.run.steps.cfng_call import run_cfng_call
from osiris.run.steps.sql import StepError, run_sql


def _ctx(tmp_path) -> RunContext:
    return RunContext(tmp_path / "run", Session(tmp_path / "ev", "s"))


def _client(payload) -> CfngClient:
    def handler(request):
        return httpx.Response(
            200, json={"connector": "imdb", "tool": "search", "result": payload, "_meta": {"server_ms": 1.0}}
        )

    c = CfngClient("https://cfng.test", token="cfng_x")  # pragma: allowlist secret
    c._http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://cfng.test")
    return c


def test_cfng_call_lands_a_list_result_as_a_table(tmp_path):
    step = Step(id="fetch", uses="cfng_call", **{"with": {"connector": "imdb", "tool": "search"}})
    with _ctx(tmp_path) as ctx:
        result = run_cfng_call(step, ctx, _client([{"title": "Dune", "rating": 8.1}]), {})
        assert result["rows"] == 1
        assert result["table"] == "fetch"
        # `fetch` is a reserved word in DuckDB, so the identifier must be quoted
        # here exactly as the step quotes it when creating the table.
        assert ctx.get_db_connection().execute('SELECT title FROM "fetch"').fetchone() == ("Dune",)


def test_cfng_call_wraps_a_dict_result_as_one_row(tmp_path):
    step = Step(id="fetch", uses="cfng_call", **{"with": {"connector": "imdb", "tool": "search"}})
    with _ctx(tmp_path) as ctx:
        assert run_cfng_call(step, ctx, _client({"title": "Dune"}), {})["rows"] == 1


def test_cfng_call_substitutes_params(tmp_path):
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content)["arguments"])
        return httpx.Response(200, json={"connector": "imdb", "tool": "s", "result": [], "_meta": {"server_ms": 1.0}})

    c = CfngClient("https://cfng.test", token="cfng_x")  # pragma: allowlist secret
    c._http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://cfng.test")
    step = Step(
        id="f",
        uses="cfng_call",
        **{"with": {"connector": "imdb", "tool": "s", "args": {"min": "${params.min_rating}"}}},
    )
    with _ctx(tmp_path) as ctx:
        run_cfng_call(step, ctx, c, {"min_rating": 7.5})
    assert seen == {"min": 7.5}


def test_cfng_call_unions_the_keys_of_heterogeneous_rows(tmp_path):
    """Tool results are JSON, not a table: rows need not agree on their keys."""
    payload = [
        {"title": "Dune", "rating": 8.1},
        {"title": "Solaris — 日本", "year": 1972, "tags": ["scifi"]},
        {"nested": {"a": 1}},
    ]
    step = Step(id="fetch", uses="cfng_call", **{"with": {"connector": "imdb", "tool": "search"}})
    with _ctx(tmp_path) as ctx:
        assert run_cfng_call(step, ctx, _client(payload), {})["rows"] == 3
        conn = ctx.get_db_connection()
        assert conn.execute('SELECT title FROM "fetch" ORDER BY rowid').fetchall() == [
            ("Dune",),
            ("Solaris — 日本",),
            (None,),
        ]
        assert conn.execute("SELECT year, tags, nested FROM \"fetch\" WHERE title LIKE 'Solaris%'").fetchone() == (
            1972,
            ["scifi"],
            None,
        )


def test_cfng_call_leaves_the_raw_rows_as_an_artifact(tmp_path):
    """The NDJSON the table was built from stays on disk as evidence."""
    step = Step(id="fetch", uses="cfng_call", **{"with": {"connector": "imdb", "tool": "search"}})
    with _ctx(tmp_path) as ctx:
        run_cfng_call(step, ctx, _client([{"title": "Solaris — 日本"}]), {})
        artifact = ctx.output_dir / "fetch.ndjson"
        assert json.loads(artifact.read_text(encoding="utf-8").splitlines()[0]) == {"title": "Solaris — 日本"}


def test_cfng_call_handles_an_empty_result(tmp_path):
    """An empty result is a table with no rows, not a missing table."""
    step = Step(id="fetch", uses="cfng_call", **{"with": {"connector": "imdb", "tool": "search"}})
    with _ctx(tmp_path) as ctx:
        assert run_cfng_call(step, ctx, _client([]), {}) == {"table": "fetch", "rows": 0}
        assert ctx.get_db_connection().execute('SELECT count(*) FROM "fetch"').fetchone() == (0,)


def test_sql_creates_a_table_named_for_the_step(tmp_path):
    with _ctx(tmp_path) as ctx:
        ctx.get_db_connection().execute("CREATE TABLE \"fetch\" AS SELECT 'Dune' AS title, 8.1 AS rating")
        step = Step(
            id="pick", uses="sql", **{"with": {"query": 'SELECT * FROM "fetch" WHERE rating >= ${params.min_rating}'}}
        )
        result = run_sql(step, ctx, {"min_rating": 7.5})
        assert result == {"table": "pick", "rows": 1}


def test_sql_reports_the_step_id_on_failure(tmp_path):
    with _ctx(tmp_path) as ctx:
        step = Step(id="pick", uses="sql", **{"with": {"query": "SELECT * FROM nonexistent"}})
        with pytest.raises(StepError) as exc:
            run_sql(step, ctx, {})
        assert exc.value.step_id == "pick"


def test_assert_passes_when_condition_holds(tmp_path):
    with _ctx(tmp_path) as ctx:
        ctx.get_db_connection().execute("CREATE TABLE t AS SELECT 1")
        step = Step(id="check", uses="assert", **{"with": {"query": "SELECT count(*) FROM t", "min_rows": 1}})
        assert run_assert(step, ctx, {})["rows"] == 1


def test_assert_halts_on_empty_result(tmp_path):
    """A silent upstream change must stop the run, not produce an empty digest."""
    with _ctx(tmp_path) as ctx:
        ctx.get_db_connection().execute("CREATE TABLE t AS SELECT 1 WHERE false")
        step = Step(id="check", uses="assert", **{"with": {"table": "t", "min_rows": 1}})
        with pytest.raises(StepError, match="expected at least 1 row"):
            run_assert(step, ctx, {})
