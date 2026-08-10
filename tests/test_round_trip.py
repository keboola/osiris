"""Freeze then run twice: the same plan must produce the same evidence."""

import json

import httpx
import pytest
from typer.testing import CliRunner
import yaml

from osiris.cfng.client import CfngClient
from osiris.cli import app
from osiris.determinism.fingerprint import FingerprintMismatch, require_fingerprint
from osiris.evidence.run_index import RunIndex
from osiris.evidence.session import Session
from osiris.fsc.config import FilesystemConfig
from osiris.fsc.paths import Paths
from osiris.plan.freeze import freeze
from osiris.plan.model import Plan
from osiris.run.runner import Runner

# `fetch` and `check` are DuckDB reserved words, chosen on purpose: a step id is
# an author-supplied name, and the engine has to quote it rather than hope.
DRAFT = {
    "metadata": {"name": "cinema-listings"},
    "params": {"min_rating": 7.5},
    "steps": [
        {"id": "fetch", "uses": "cfng_call", "with": {"connector": "imdb", "tool": "search"}},
        {"id": "pick", "uses": "sql", "with": {"query": 'SELECT * FROM "fetch" WHERE rating >= ${params.min_rating}'}},
        {"id": "check", "uses": "assert", "with": {"table": "pick", "min_rows": 1}},
    ],
}
TOOLS = [{"name": "search", "inputSchema": {"type": "object"}, "outputSchema": {"type": "array"}}]
ROWS = [{"title": "Dune", "rating": 8.1}, {"title": "Flop", "rating": 3.2}]

# Only one of the two rows clears min_rating, so a run that silently skipped the
# filter would report 2 rows for `pick` and be caught here.
EXPECTED_STEPS = {"fetch": 2, "pick": 1, "check": 1}

# Fields that legitimately differ between two runs of the same plan. Everything
# else in the evidence must match, or the run is not reproducible.
VOLATILE_EVIDENCE_FIELDS = frozenset({"ts", "run_id", "duration_ms"})


def _client() -> CfngClient:
    def handler(request):
        if request.url.path == "/catalog/version":
            return httpx.Response(200, json={"catalog_version": "sha256:cat1"})
        if request.url.path.endswith("/tools"):
            return httpx.Response(200, json={"connector": "imdb", "tools": TOOLS})
        return httpx.Response(
            200, json={"connector": "imdb", "tool": "search", "result": ROWS, "_meta": {"server_ms": 3.0}}
        )

    c = CfngClient("https://cfng.test", token="cfng_x")  # pragma: allowlist secret
    c._http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://cfng.test")
    return c


def _stable(records: list[dict]) -> list[dict]:
    """Evidence with the per-invocation fields removed, so two runs are comparable."""
    return [{k: v for k, v in record.items() if k not in VOLATILE_EVIDENCE_FIELDS} for record in records]


def test_freeze_then_run_twice_is_identical(tmp_path):
    """The product claim: one frozen artifact, two runs, the same evidence both times.

    Comparing the summaries alone would only prove the row counts matched. The
    event and metric streams are compared too, because the evidence is the
    deliverable -- a run whose ledger differs from the last one is not replayable
    even when its totals happen to agree.
    """
    paths = Paths(FilesystemConfig(base_path=tmp_path))
    frozen = freeze(DRAFT, _client(), paths)

    plan = Plan(**yaml.safe_load((frozen.build_dir / "manifest.yaml").read_text()))
    sessions = [Session(tmp_path / f"ev{i}", "s") for i in (1, 2)]
    summaries = [
        Runner(_client(), paths).execute(plan, tmp_path / f"run{i}", session)
        for i, session in zip((1, 2), sessions, strict=True)
    ]

    assert summaries[0].steps == summaries[1].steps == EXPECTED_STEPS
    assert summaries[0].status == summaries[1].status == "success"
    # Distinct run ids, so the comparison below is between two real executions.
    assert summaries[0].run_id != summaries[1].run_id

    assert _stable(sessions[0].read_events()) == _stable(sessions[1].read_events())
    assert _stable(sessions[0].read_metrics()) == _stable(sessions[1].read_metrics())

    # Naming the streams keeps the two comparisons above from passing vacuously
    # on a pair of empty files, which is how a broken runner would read.
    assert [m["name"] for m in sessions[0].read_metrics()] == [
        "rows_read",
        "server_ms",
        "rows_written",
        "asserted_rows",
    ]
    assert [e["event"] for e in sessions[0].read_events()] == [
        "run_start",
        "step_start",
        "step_finish",
        "step_start",
        "step_finish",
        "step_start",
        "step_finish",
        "run_finish",
    ]


def test_manifest_fingerprint_survives_a_reload(tmp_path):
    """The artifact on disk must hash to what freeze recorded."""
    paths = Paths(FilesystemConfig(base_path=tmp_path))
    frozen = freeze(DRAFT, _client(), paths)
    reloaded = Plan(**yaml.safe_load((frozen.build_dir / "manifest.yaml").read_text()))
    fps = json.loads((frozen.build_dir / "fingerprints.json").read_text())

    require_fingerprint(reloaded.canonical_without_fingerprints(), fps["plan"])


def test_tampered_manifest_is_detected(tmp_path):
    """The guarantee test: editing the artifact must be caught, not ignored."""
    paths = Paths(FilesystemConfig(base_path=tmp_path))
    frozen = freeze(DRAFT, _client(), paths)
    manifest_path = frozen.build_dir / "manifest.yaml"
    data = yaml.safe_load(manifest_path.read_text())
    data["params"]["min_rating"] = 0.0
    tampered = Plan(**data)
    fps = json.loads((frozen.build_dir / "fingerprints.json").read_text())

    with pytest.raises(FingerprintMismatch) as excinfo:
        require_fingerprint(tampered.canonical_without_fingerprints(), fps["plan"])

    # The check compared against the recorded fingerprint, not something incidental.
    assert excinfo.value.expected == fps["plan"]
    assert excinfo.value.actual != fps["plan"]


def test_the_whole_pipeline_round_trips_through_the_cli(tmp_path, monkeypatch):
    """The same claim through the real entry point, twice over one build directory.

    `tests/test_cli.py` already covers freeze-then-run and tamper rejection, but
    only for a single-step plan. What is proved here and nowhere else is that a
    multi-step plan -- whose params carry a float and whose step ids are DuckDB
    reserved words -- survives the YAML round trip that `osiris run` performs,
    fingerprint check included, and that re-running one frozen artifact is
    repeatable rather than merely possible.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CFNG_BASE_URL", "https://cfng.test")
    monkeypatch.setenv("CFNG_TOKEN", "cfng_x")  # pragma: allowlist secret
    # The CLI resolves CfngClient through its own module namespace at call time,
    # which is the seam that lets a transport-mocked factory stand in for it.
    monkeypatch.setattr("osiris.cli.CfngClient", lambda *args, **kwargs: _client())

    cli = CliRunner()
    assert cli.invoke(app, ["init"]).exit_code == 0
    (tmp_path / "draft.json").write_text(json.dumps(DRAFT))

    frozen = cli.invoke(app, ["freeze", "draft.json"])
    assert frozen.exit_code == 0, frozen.output
    build_dir = next((tmp_path / "build").rglob("manifest.yaml")).parent

    for _ in range(2):
        ran = cli.invoke(app, ["run", str(build_dir)])
        assert ran.exit_code == 0, ran.output
        for step_id, rows in EXPECTED_STEPS.items():
            assert f"{step_id}: {rows} rows" in ran.output

    records = RunIndex(tmp_path / ".osiris" / "index" / "runs.jsonl").read_all()
    assert [r.status for r in records] == ["success", "success"]
    # Both rows name the same artifact, so the ledger shows a replay rather than
    # two unrelated runs that happened to agree.
    assert records[0].manifest_hash == records[1].manifest_hash
    assert records[0].run_id != records[1].run_id
