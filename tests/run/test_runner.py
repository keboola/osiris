"""The runner verifies pins before the first call and records evidence."""

import httpx
import pytest

from osiris.cfng.client import TRANSPORT_ERROR, CfngClient
from osiris.cfng.pins import tool_pin
from osiris.evidence.session import Session
from osiris.fsc.config import FilesystemConfig
from osiris.fsc.paths import Paths
from osiris.plan.model import DriftAction, Plan
from osiris.run.runner import DriftError, PinIntegrityError, PinProbeError, Runner

IMDB_TOOL = {"name": "search", "inputSchema": {"type": "object"}}
IMDB_TOOL_WITH_OUTPUT = {"name": "search", "inputSchema": {"type": "object"}, "outputSchema": {"type": "array"}}
TMDB_TOOL = {"name": "detail", "inputSchema": {"type": "object"}}


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


def _catalog_client(
    tools_by_connector: dict[str, list[dict]],
    *,
    catalog: str = "sha256:cat1",
    requests: list[str] | None = None,
    unreachable: bool = False,
) -> CfngClient:
    """A cf-ng that routes /connectors/{id}/tools per connector and 404s the rest.

    `requests` records *every* path, not just tool calls, so a test can assert
    both "nothing was executed" and "the catalog was actually probed".
    """

    def handler(request):
        path = request.url.path
        if requests is not None:
            requests.append(path)
        if unreachable:
            raise httpx.ConnectError("cf-ng is unreachable")
        if path == "/catalog/version":
            return httpx.Response(200, json={"catalog_version": catalog})
        if path.startswith("/connectors/") and path.endswith("/tools"):
            connector = path.split("/")[2]
            if connector not in tools_by_connector:
                return httpx.Response(404, json={"detail": f"connector '{connector}' not found"})
            return httpx.Response(200, json={"connector": connector, "tools": tools_by_connector[connector]})
        return httpx.Response(
            200,
            json={"connector": "imdb", "tool": "search", "result": [{"a": 1}], "_meta": {"server_ms": 1.0}},
        )

    c = CfngClient("https://cfng.test", token="cfng_x")  # pragma: allowlist secret
    c._http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://cfng.test")
    return c


def _run(client: CfngClient, plan: Plan, tmp_path, session: Session | None = None):
    session = session or Session(tmp_path / "ev", "s")
    runner = Runner(client, Paths(FilesystemConfig(base_path=tmp_path)))
    return runner.execute(plan, tmp_path / "run", session), session


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


# --- outputSchema drift, both directions -------------------------------------


def test_added_output_schema_aborts_before_any_tool_call(tmp_path):
    """The HIGH defect: the pin recorded no output, so adding one used to run clean."""
    requests: list[str] = []
    client = _catalog_client({"imdb": [IMDB_TOOL_WITH_OUTPUT]}, requests=requests)
    with pytest.raises(DriftError) as exc:
        _run(client, _plan(), tmp_path)
    assert "/tools/call" not in requests
    assert "outputSchema added since freeze" in exc.value.drifts[0].diff


def test_removed_output_schema_aborts_before_any_tool_call(tmp_path):
    """The control case, which already worked -- kept so the symmetry is pinned."""
    requests: list[str] = []
    plan = _plan(
        pins={
            "cfng": {"catalog_version": "sha256:cat1"},
            "tools": {"imdb__search": tool_pin(IMDB_TOOL_WITH_OUTPUT).model_dump()},
        }
    )
    client = _catalog_client({"imdb": [IMDB_TOOL]}, requests=requests)
    with pytest.raises(DriftError) as exc:
        _run(client, plan, tmp_path)
    assert "/tools/call" not in requests
    assert "outputSchema removed since freeze" in exc.value.drifts[0].diff


def test_added_output_schema_is_recorded_as_fatal_drift(tmp_path):
    session = Session(tmp_path / "ev", "s")
    client = _catalog_client({"imdb": [IMDB_TOOL_WITH_OUTPUT]})
    with pytest.raises(DriftError):
        _run(client, _plan(), tmp_path, session)
    events = session.read_events()
    assert any(e["event"] == "drift_fatal" and "outputSchema" in e["detail"] for e in events)
    assert not any(e["event"] == "pins_verified" for e in events)


# --- drift anywhere in the plan stops everything ------------------------------


def _two_step_plan(**overrides) -> Plan:
    base = {
        "metadata": {"name": "demo"},
        "pins": {
            "cfng": {"catalog_version": "sha256:cat1"},
            "tools": {
                "imdb__search": tool_pin(IMDB_TOOL).model_dump(),
                "tmdb__detail": tool_pin(TMDB_TOOL).model_dump(),
            },
        },
        "policy": {},
        "params": {},
        "steps": [
            {"id": "first", "uses": "cfng_call", "with": {"connector": "imdb", "tool": "search"}},
            {"id": "last", "uses": "cfng_call", "with": {"connector": "tmdb", "tool": "detail"}},
        ],
        "fingerprints": {},
    }
    return Plan(**(base | overrides))


def test_drift_in_the_last_step_aborts_before_the_first_call(tmp_path):
    """Verification is whole-plan and up front: step 1 must not run to earn step 2's abort."""
    requests: list[str] = []
    moved = {"name": "detail", "inputSchema": {"type": "object", "required": ["id"]}}
    client = _catalog_client({"imdb": [IMDB_TOOL], "tmdb": [moved]}, requests=requests)
    with pytest.raises(DriftError) as exc:
        _run(client, _two_step_plan(), tmp_path)
    assert "/tools/call" not in requests
    assert exc.value.drifts[0].subject == "tmdb__detail"


def test_added_output_schema_on_the_last_step_also_aborts(tmp_path):
    requests: list[str] = []
    gained = {"name": "detail", "inputSchema": {"type": "object"}, "outputSchema": {"type": "object"}}
    client = _catalog_client({"imdb": [IMDB_TOOL], "tmdb": [gained]}, requests=requests)
    with pytest.raises(DriftError) as exc:
        _run(client, _two_step_plan(), tmp_path)
    assert "/tools/call" not in requests
    assert "outputSchema added since freeze" in exc.value.drifts[0].diff


# --- the probe itself failing -------------------------------------------------


def test_missing_connector_aborts_with_evidence(tmp_path):
    """A 404 used to escape as a raw traceback with nothing in the ledger."""
    requests: list[str] = []
    session = Session(tmp_path / "ev", "s")
    client = _catalog_client({"imdb": [IMDB_TOOL]}, requests=requests)
    with pytest.raises(PinProbeError) as exc:
        _run(client, _two_step_plan(), tmp_path, session)
    assert exc.value.status == 404
    assert "/tools/call" not in requests
    assert any(e["event"] == "pin_probe_failed" for e in session.read_events())


def test_unreachable_cfng_aborts_with_evidence(tmp_path):
    requests: list[str] = []
    session = Session(tmp_path / "ev", "s")
    client = _catalog_client({"imdb": [IMDB_TOOL]}, requests=requests, unreachable=True)
    with pytest.raises(PinProbeError) as exc:
        _run(client, _plan(), tmp_path, session)
    # Transport failures now carry a synthetic status instead of escaping raw.
    assert exc.value.status == TRANSPORT_ERROR
    assert "unreachable" in str(exc.value)
    assert "/tools/call" not in requests
    assert any(e["event"] == "pin_probe_failed" for e in session.read_events())


def test_pin_probe_failure_is_catchable_as_drift_error(tmp_path):
    """osiris/cli.py catches (DriftError, StepError); the new errors must land there."""
    client = _catalog_client({}, unreachable=True)
    with pytest.raises(DriftError):
        _run(client, _plan(), tmp_path)


# --- pins that are not worth verifying ----------------------------------------


def test_empty_pins_on_a_tool_calling_plan_is_a_hard_failure(tmp_path):
    """An unpinned plan must not be indistinguishable from a verified one."""
    requests: list[str] = []
    session = Session(tmp_path / "ev", "s")
    plan = _plan(pins={"cfng": {"catalog_version": "sha256:cat1"}, "tools": {}})
    client = _catalog_client({"imdb": [IMDB_TOOL]}, requests=requests)
    with pytest.raises(PinIntegrityError) as exc:
        _run(client, plan, tmp_path, session)
    assert "never frozen" in str(exc.value)
    assert requests == []  # cf-ng was not even asked
    events = session.read_events()
    assert any(e["event"] == "pins_unusable" for e in events)
    assert not any(e["event"] == "pins_verified" for e in events)


def test_partially_pinned_plan_is_a_hard_failure(tmp_path):
    """Dropping one pin must not silently exempt that step from verification."""
    plan = _two_step_plan(
        pins={
            "cfng": {"catalog_version": "sha256:cat1"},
            "tools": {"imdb__search": tool_pin(IMDB_TOOL).model_dump()},
        }
    )
    client = _catalog_client({"imdb": [IMDB_TOOL], "tmdb": [TMDB_TOOL]})
    with pytest.raises(PinIntegrityError) as exc:
        _run(client, plan, tmp_path)
    assert "not pinned" in str(exc.value)


def test_a_plan_without_tool_calls_needs_no_pins(tmp_path):
    """The refusal is about unpinned *tool calls*, not about pins existing."""
    plan = _plan(
        pins={"cfng": {"catalog_version": "sha256:cat1"}, "tools": {}},
        steps=[{"id": "only", "uses": "sql", "with": {"query": "SELECT 1 AS n"}}],
    )
    summary, _ = _run(_catalog_client({}), plan, tmp_path)
    assert summary.status == "success"


def test_colliding_pin_keys_are_a_hard_failure(tmp_path):
    """(x, y__z) and (x__y, z) flatten to one key, so one pin would cover two tools."""
    requests: list[str] = []
    plan = _plan(
        pins={"cfng": {"catalog_version": "sha256:cat1"}, "tools": {"x__y__z": tool_pin(IMDB_TOOL).model_dump()}},
        steps=[
            {"id": "a", "uses": "cfng_call", "with": {"connector": "x", "tool": "y__z"}},
            {"id": "b", "uses": "cfng_call", "with": {"connector": "x__y", "tool": "z"}},
        ],
    )
    client = _catalog_client({}, requests=requests)
    with pytest.raises(PinIntegrityError) as exc:
        _run(client, plan, tmp_path)
    assert "ambiguous" in str(exc.value)
    assert requests == []


def test_cfng_step_without_a_connector_cannot_be_verified(tmp_path):
    plan = _plan(steps=[{"id": "fetch", "uses": "cfng_call", "with": {"tool": "search"}}])
    with pytest.raises(PinIntegrityError) as exc:
        _run(_catalog_client({"imdb": [IMDB_TOOL]}), plan, tmp_path)
    assert "cannot be pinned" in str(exc.value)


# --- positive evidence --------------------------------------------------------


def test_pins_verified_event_records_how_many_tools_were_checked(tmp_path):
    """ "Pins verified" must be a recorded fact, not a print statement."""
    session = Session(tmp_path / "ev", "s")
    _run(_catalog_client({"imdb": [IMDB_TOOL]}), _plan(), tmp_path, session)
    verified = [e for e in session.read_events() if e["event"] == "pins_verified"]
    assert len(verified) == 1
    assert verified[0]["tools_checked"] == 1
    assert verified[0]["tool_calls_pinned"] == 1
    assert verified[0]["catalog_version"] == "sha256:cat1"


def test_pins_verified_is_not_emitted_when_drift_is_fatal(tmp_path):
    session = Session(tmp_path / "ev", "s")
    changed = {"name": "search", "inputSchema": {"type": "object", "required": ["region"]}}
    with pytest.raises(DriftError):
        _run(_catalog_client({"imdb": [changed]}), _plan(), tmp_path, session)
    assert not any(e["event"] == "pins_verified" for e in session.read_events())


def test_pins_verified_names_the_policy_that_was_in_force(tmp_path):
    """A clean assertion has to say what it was asserting under, or it says little."""
    session = Session(tmp_path / "ev", "s")
    _run(_catalog_client({"imdb": [IMDB_TOOL]}), _plan(), tmp_path, session)
    (verified,) = [e for e in session.read_events() if e["event"] == "pins_verified"]
    assert verified["drifts_found"] == 0
    assert verified["drift_subjects"] == []
    assert verified["on_tool_contract_drift"] == "fail"


# --- drift evidence must not be falsifiable by policy -------------------------
#
# `policy.on_tool_contract_drift: warn|ignore` switches the abort off. Under
# `ignore` the run used to emit `pins_verified {"warnings": 0}` -- byte-identical
# to a clean run -- so the record of a failed verification was indistinguishable
# from the record of a passed one. A positive integrity assertion must never
# appear for a run whose integrity check failed.

DRIFTED_TOOL = {"name": "search", "inputSchema": {"type": "object", "required": ["region"]}}


def _drift_evidence(tmp_path, policy: dict, live_tool: dict = DRIFTED_TOOL) -> list[dict]:
    """The pin-verification events of one run, stripped of per-invocation fields."""
    session = Session(tmp_path / "ev", "s")
    _run(_catalog_client({"imdb": [live_tool]}), _plan(policy=policy), tmp_path, session)
    return [
        {k: v for k, v in e.items() if k not in ("ts", "session_id")}
        for e in session.read_events()
        if e["event"].startswith(("pins_", "drift_"))
    ]


@pytest.mark.parametrize("action", [DriftAction.WARN, DriftAction.IGNORE])
def test_suppressed_drift_never_emits_a_positive_verification(tmp_path, action):
    events = _drift_evidence(tmp_path, {"on_tool_contract_drift": action})
    assert not any(e["event"] == "pins_verified" for e in events)
    (suppressed,) = [e for e in events if e["event"] == "pins_drift_suppressed"]
    assert suppressed["drifts_found"] == 1
    assert suppressed["drift_subjects"] == ["imdb__search"]
    assert suppressed["on_tool_contract_drift"] == action.value


def test_ignored_drift_is_distinguishable_from_a_clean_run(tmp_path):
    """The exact refutation: `ignore` produced evidence identical to a clean run."""
    ignored = _drift_evidence(tmp_path / "a", {"on_tool_contract_drift": DriftAction.IGNORE})
    clean = _drift_evidence(tmp_path / "b", {}, live_tool=IMDB_TOOL)
    assert clean == [e for e in clean if e["event"] == "pins_verified"]  # the clean run is clean
    assert ignored != clean


def test_an_ignored_drift_still_reaches_disk(tmp_path):
    """Under `ignore` the diff text was recorded nowhere at all."""
    events = _drift_evidence(tmp_path, {"on_tool_contract_drift": DriftAction.IGNORE})
    assert any(e["event"] == "drift_ignored" and "inputSchema changed" in e["detail"] for e in events)


def test_a_warned_catalog_drift_also_withholds_the_positive_assertion(tmp_path):
    """Catalog drift is the default-warn path, so the default run can lie too."""
    session = Session(tmp_path / "ev", "s")
    _run(_catalog_client({"imdb": [IMDB_TOOL]}, catalog="sha256:cat2"), _plan(), tmp_path, session)
    events = session.read_events()
    assert not any(e["event"] == "pins_verified" for e in events)
    (suppressed,) = [e for e in events if e["event"] == "pins_drift_suppressed"]
    assert suppressed["drift_subjects"] == ["catalog"]
    assert suppressed["on_catalog_drift"] == "warn"


# --- annotations are part of the contract the runner verifies -----------------

READ_ONLY_TOOL = {
    "name": "search",
    "inputSchema": {"type": "object"},
    "annotations": {"readOnlyHint": True, "destructiveHint": False},
}
DESTRUCTIVE_TOOL = {
    "name": "search",
    "inputSchema": {"type": "object"},
    "annotations": {"readOnlyHint": False, "destructiveHint": True},
}


def test_a_flipped_destructive_hint_aborts_before_any_tool_call(tmp_path):
    """Under the DEFAULT fail policy this used to run and issue a real call."""
    requests: list[str] = []
    plan = _plan(
        pins={
            "cfng": {"catalog_version": "sha256:cat1"},
            "tools": {"imdb__search": tool_pin(READ_ONLY_TOOL).model_dump()},
        }
    )
    client = _catalog_client({"imdb": [DESTRUCTIVE_TOOL]}, requests=requests)
    with pytest.raises(DriftError) as exc:
        _run(client, plan, tmp_path)
    assert "/tools/call" not in requests
    assert "annotations changed since freeze" in exc.value.drifts[0].diff


def test_an_inverted_input_schema_aborts_before_any_tool_call(tmp_path):
    """`{}` -> `false` inverts the contract; `or {}` made both pin identically."""
    requests: list[str] = []
    permissive = {"name": "search", "inputSchema": {}}
    closed = {"name": "search", "inputSchema": False}
    plan = _plan(
        pins={
            "cfng": {"catalog_version": "sha256:cat1"},
            "tools": {"imdb__search": tool_pin(permissive).model_dump()},
        }
    )
    with pytest.raises(DriftError) as exc:
        _run(_catalog_client({"imdb": [closed]}, requests=requests), plan, tmp_path)
    assert "/tools/call" not in requests
    assert "inputSchema changed since freeze" in exc.value.drifts[0].diff
