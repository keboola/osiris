"""The runner verifies pins before the first call and records evidence."""

import httpx
import pytest

from osiris.cfng.client import CfngClient
from osiris.cfng.pins import tool_pin
from osiris.evidence.session import Session
from osiris.fsc.config import FilesystemConfig
from osiris.fsc.paths import Paths
from osiris.plan.model import DriftAction, Plan
from osiris.run.runner import DriftError, Runner

IMDB_TOOL = {"name": "search", "inputSchema": {"type": "object"}}


def _plan(**overrides) -> Plan:
    base = {
        "metadata": {"name": "demo"},
        "pins": {
            "cfng": {"catalog_version": "sha256:cat1"},
            "tools": {"imdb__search": tool_pin(IMDB_TOOL).model_dump()},
        },
        "policy": {},
        "params": {},
        "steps": [{"id": "fetch", "uses": "cfng_call", "with": {"connector": "imdb", "tool": "search"}}],
        "fingerprints": {},
    }
    return Plan(**(base | overrides))


def _client(tool_manifest, catalog="sha256:cat1", calls=None) -> CfngClient:
    def handler(request):
        if request.url.path == "/catalog/version":
            return httpx.Response(200, json={"catalog_version": catalog})
        if request.url.path.endswith("/tools"):
            return httpx.Response(200, json={"connector": "imdb", "tools": [tool_manifest]})
        if calls is not None:
            calls.append(request.url.path)
        return httpx.Response(
            200, json={"connector": "imdb", "tool": "search", "result": [{"a": 1}], "_meta": {"server_ms": 1.0}}
        )

    c = CfngClient("https://cfng.test", token="cfng_x")  # pragma: allowlist secret
    c._http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://cfng.test")
    return c


def test_run_succeeds_when_pins_match(tmp_path):
    runner = Runner(_client(IMDB_TOOL), Paths(FilesystemConfig(base_path=tmp_path)))
    summary = runner.execute(_plan(), tmp_path / "run", Session(tmp_path / "ev", "s"))
    assert summary.status == "success"
    assert summary.steps == {"fetch": 1}


def test_contract_drift_aborts_before_any_tool_call(tmp_path):
    """Nothing may be called when the contract moved."""
    calls: list[str] = []
    changed = {"name": "search", "inputSchema": {"type": "object", "required": ["region"]}}
    runner = Runner(_client(changed, calls=calls), Paths(FilesystemConfig(base_path=tmp_path)))
    with pytest.raises(DriftError) as exc:
        runner.execute(_plan(), tmp_path / "run", Session(tmp_path / "ev", "s"))
    assert calls == []
    assert "inputSchema changed" in exc.value.drifts[0].diff


def test_contract_drift_can_be_downgraded_to_a_warning(tmp_path):
    changed = {"name": "search", "inputSchema": {"type": "object", "required": ["region"]}}
    plan = _plan(policy={"on_tool_contract_drift": DriftAction.WARN})
    runner = Runner(_client(changed), Paths(FilesystemConfig(base_path=tmp_path)))
    summary = runner.execute(plan, tmp_path / "run", Session(tmp_path / "ev", "s"))
    assert summary.status == "success"
    assert any("inputSchema changed" in w for w in summary.warnings)


def test_catalog_drift_only_warns_by_default(tmp_path):
    runner = Runner(_client(IMDB_TOOL, catalog="sha256:cat2"), Paths(FilesystemConfig(base_path=tmp_path)))
    summary = runner.execute(_plan(), tmp_path / "run", Session(tmp_path / "ev", "s"))
    assert summary.status == "success"
    assert any("catalog_version" in w for w in summary.warnings)


def test_evidence_records_every_step(tmp_path):
    session = Session(tmp_path / "ev", "s")
    Runner(_client(IMDB_TOOL), Paths(FilesystemConfig(base_path=tmp_path))).execute(_plan(), tmp_path / "run", session)
    events = [e["event"] for e in session.read_events()]
    assert "run_start" in events
    assert "step_start" in events
    assert "step_finish" in events
    assert "run_finish" in events


def test_two_runs_produce_identical_step_results(tmp_path):
    """The determinism claim, exercised end to end."""
    paths = Paths(FilesystemConfig(base_path=tmp_path))
    a = Runner(_client(IMDB_TOOL), paths).execute(_plan(), tmp_path / "r1", Session(tmp_path / "e1", "s"))
    b = Runner(_client(IMDB_TOOL), paths).execute(_plan(), tmp_path / "r2", Session(tmp_path / "e2", "s"))
    assert a.steps == b.steps
    assert a.status == b.status
