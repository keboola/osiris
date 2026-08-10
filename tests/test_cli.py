"""The CLI wires the pieces together and fails with actionable messages."""

import json
import os
from pathlib import Path
import shutil

import httpx
import pytest
from typer.testing import CliRunner
import yaml

from osiris.cli import BASE_URL_ENV, TOKEN_ENV, app, load_env

runner = CliRunner()

DRAFT = {
    "metadata": {"name": "demo"},
    "params": {},
    "steps": [{"id": "fetch", "uses": "cfng_call", "with": {"connector": "imdb", "tool": "search"}}],
}
IMDB = [{"name": "search", "inputSchema": {"type": "object"}}]

# Shaped like a real credential so that a leak is greppable, and long enough
# that it cannot occur in a payload by chance.
LIVE_TOKEN = "cfng_LiVeT0kenAbCdEf0123456789"  # pragma: allowlist secret


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    return tmp_path


@pytest.fixture
def credentials(monkeypatch):
    monkeypatch.setenv("CFNG_BASE_URL", "https://cfng.test")
    monkeypatch.setenv("CFNG_TOKEN", "cfng_x")  # pragma: allowlist secret


@pytest.fixture
def live_credentials(monkeypatch):
    """Credentials whose token is long and distinctive, for the leak sweeps."""
    monkeypatch.setenv("CFNG_BASE_URL", "https://cfng.test")
    monkeypatch.setenv("CFNG_TOKEN", LIVE_TOKEN)


@pytest.fixture
def fake_cfng(monkeypatch):
    """Swap the client factory the CLI looks up, keeping the real client's logic.

    Returns a mutable dict of server behaviour. Tests need to turn cf-ng hostile
    *after* freezing — freezing requires a server that answers — so the
    behaviour has to be reconfigurable rather than baked into the fixture.

    `fail` is either `(status, detail)` for an HTTP error or an exception
    instance to raise, which is how an unreachable cf-ng is simulated.
    """
    state = {
        "tools": IMDB,
        "fail": None,
        "fail_call": None,
        "result": [{"a": 1}],
    }

    def handler(request):
        if request.url.path == "/catalog/version":
            return httpx.Response(200, json={"catalog_version": "sha256:cat1"})
        # `fail_call` fails only the tool call, leaving the pin probe healthy —
        # the only way to reach a failure *after* the run has started.
        failure = state["fail_call"] if request.url.path == "/tools/call" else state["fail"]
        if failure is not None:
            if isinstance(failure, Exception):
                raise failure
            status, detail = failure
            return httpx.Response(status, json={"detail": detail})
        if request.url.path.endswith("/tools"):
            return httpx.Response(200, json={"connector": "imdb", "tools": state["tools"]})
        return httpx.Response(
            200,
            json={
                "connector": "imdb",
                "tool": "search",
                "result": state["result"],
                "_meta": {"server_ms": 1.0},
            },
        )

    import osiris.cli as cli_module

    original = cli_module.CfngClient

    def patched(*args, **kwargs):
        client = original(*args, **kwargs)
        client._http = httpx.Client(transport=httpx.MockTransport(handler), base_url=client.base_url)
        return client

    monkeypatch.setattr(cli_module, "CfngClient", patched)
    return state


def _freeze(project) -> Path:
    """Freeze DRAFT and return the build directory."""
    (project / "draft.json").write_text(json.dumps(DRAFT))
    frozen = runner.invoke(app, ["freeze", "draft.json"])
    assert frozen.exit_code == 0, frozen.output
    return next((project / "build").rglob("manifest.yaml")).parent


def _manifest(build_dir: Path) -> dict:
    return yaml.safe_load((build_dir / "manifest.yaml").read_text())


def _write_manifest(build_dir: Path, data: dict, **dump_kwargs) -> None:
    (build_dir / "manifest.yaml").write_text(yaml.safe_dump(data, **dump_kwargs))


def _fingerprints(build_dir: Path) -> dict:
    return json.loads((build_dir / "fingerprints.json").read_text())


def _write_fingerprints(build_dir: Path, values: dict, **dump_kwargs) -> None:
    (build_dir / "fingerprints.json").write_text(json.dumps(values, **{"indent": 2, "sort_keys": True, **dump_kwargs}))


def _recompute(data: dict) -> dict:
    """The fingerprints freeze would have written for this manifest.

    Deliberately built from the repo's own public API, exactly as an attacker
    who has read `osiris/plan/freeze.py` would build them.
    """
    from osiris.determinism.canonical import canonical_yaml
    from osiris.determinism.fingerprint import compute_fingerprint
    from osiris.plan.model import Plan

    plan = Plan(**data)
    plan_fp = compute_fingerprint(plan.canonical_without_fingerprints())
    pins_fp = compute_fingerprint(canonical_yaml(plan.pins.model_dump(mode="json")))
    return {"plan": plan_fp, "pins": pins_fp, "manifest": compute_fingerprint(plan_fp + pins_fp)}


def _files_under(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def _leaking_files(root: Path, secret: str) -> list[Path]:
    """Every file under root whose *bytes* contain secret.

    Bytes rather than text, and every file rather than one glob: the DuckDB file
    is binary and the ledger is not under run_logs/, so a text-only sweep of a
    single directory is how four live leaks coexisted with a green suite.
    """
    needle = secret.encode()
    return [path for path in _files_under(root) if needle in path.read_bytes()]


def _assert_handled(result) -> None:
    """Fail if the CLI let an exception escape.

    CliRunner stashes an unhandled exception in `result.exception` instead of
    printing it, so a traceback in production is invisible here unless it is
    asserted on directly. `SystemExit` is what a deliberate `typer.Exit` becomes.
    """
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"unhandled {type(result.exception).__name__}: {result.exception}"


def test_init_writes_osiris_yaml_with_absolute_base_path(project):
    config = yaml.safe_load((project / "osiris.yaml").read_text())
    assert config["filesystem"]["base_path"] == str(project)


def test_init_does_not_clobber_an_existing_config(project):
    (project / "osiris.yaml").write_text("version: mine\n")
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert (project / "osiris.yaml").read_text() == "version: mine\n"


def test_freeze_then_run(project, fake_cfng, credentials):
    build_dir = _freeze(project)

    ran = runner.invoke(app, ["run", str(build_dir)])
    assert ran.exit_code == 0, ran.output
    assert "success" in ran.output


def test_run_records_the_run_in_the_ledger(project, fake_cfng, credentials):
    """Evidence is the product; a run that leaves no ledger row did not happen."""
    from osiris.evidence.run_index import RunIndex

    build_dir = _freeze(project)
    assert runner.invoke(app, ["run", str(build_dir)]).exit_code == 0

    records = RunIndex(project / ".osiris" / "index" / "runs.jsonl").read_all()
    assert [r.status for r in records] == ["success"]
    assert records[0].plan_name == "demo"
    assert records[0].manifest_hash.startswith("sha256:")


def test_ledger_run_id_resolves_to_the_evidence_directory(project, fake_cfng, credentials):
    """A ledger row is only useful if it names the evidence it produced."""
    from osiris.evidence.run_index import RunIndex
    from osiris.fsc.config import FilesystemConfig
    from osiris.fsc.paths import Paths

    build_dir = _freeze(project)
    assert runner.invoke(app, ["run", str(build_dir)]).exit_code == 0

    record = RunIndex(project / ".osiris" / "index" / "runs.jsonl").latest()[0]
    log_dir = Paths(FilesystemConfig.load(project)).run_log_dir(record.plan_name, record.run_id)
    assert (log_dir / "events.jsonl").exists()


def test_a_failed_run_is_recorded_too(project, fake_cfng, credentials):
    """A ledger that only holds successes cannot answer 'what happened last night'."""
    from osiris.evidence.run_index import RunIndex

    draft = json.loads(json.dumps(DRAFT))
    draft["steps"].append({"id": "check", "uses": "assert", "with": {"table": "fetch", "min_rows": 99}})
    (project / "draft.json").write_text(json.dumps(draft))
    assert runner.invoke(app, ["freeze", "draft.json"]).exit_code == 0
    build_dir = next((project / "build").rglob("manifest.yaml")).parent

    result = runner.invoke(app, ["run", str(build_dir)])
    assert result.exit_code != 0
    assert "check" in result.output

    record = RunIndex(project / ".osiris" / "index" / "runs.jsonl").latest()[0]
    assert record.status == "failed"
    assert "at least 99" in (record.error or "")


def test_dry_run_verifies_pins_without_executing(project, fake_cfng, credentials):
    build_dir = _freeze(project)
    result = runner.invoke(app, ["run", str(build_dir), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "Nothing executed" in result.output
    # No ledger row, because nothing ran.
    assert not (project / ".osiris" / "index" / "runs.jsonl").exists()


def test_run_rejects_a_manifest_edited_after_freezing(project, fake_cfng, credentials):
    """The fingerprint beside the manifest is checked, not merely written."""
    build_dir = _freeze(project)
    manifest_path = build_dir / "manifest.yaml"
    data = yaml.safe_load(manifest_path.read_text())
    data["steps"][0]["with"]["tool"] = "somethingelse"
    manifest_path.write_text(yaml.safe_dump(data))

    result = runner.invoke(app, ["run", str(build_dir)])
    assert result.exit_code != 0
    assert "fingerprint" in result.output


def test_run_reports_missing_token_actionably(project, monkeypatch):
    """Credentials are a precondition of every run, so they are reported first."""
    monkeypatch.setenv("CFNG_BASE_URL", "https://cfng.test")
    monkeypatch.delenv("CFNG_TOKEN", raising=False)
    result = runner.invoke(app, ["run", str(project)])
    assert result.exit_code != 0
    assert "CFNG_TOKEN" in result.output


def test_run_reports_every_missing_variable_at_once(project, monkeypatch):
    monkeypatch.delenv("CFNG_BASE_URL", raising=False)
    monkeypatch.delenv("CFNG_TOKEN", raising=False)
    result = runner.invoke(app, ["run", str(project)])
    assert result.exit_code != 0
    assert "CFNG_BASE_URL" in result.output
    assert "CFNG_TOKEN" in result.output


def test_run_reports_a_missing_manifest_actionably(project, credentials):
    result = runner.invoke(app, ["run", str(project)])
    assert result.exit_code != 0
    assert "manifest.yaml" in result.output
    assert "osiris freeze" in result.output


def test_run_without_a_config_says_to_init(tmp_path, monkeypatch, credentials):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["run", str(tmp_path)])
    assert result.exit_code != 0
    assert "osiris init" in result.output


def test_freeze_reports_a_malformed_draft_actionably(project, fake_cfng, credentials):
    (project / "draft.json").write_text("{not json")
    result = runner.invoke(app, ["freeze", "draft.json"])
    assert result.exit_code != 0
    assert "draft.json" in result.output


def test_freeze_reports_a_draft_that_is_not_a_plan(project, fake_cfng, credentials):
    (project / "draft.json").write_text(json.dumps({"metadata": {"name": "x"}, "steps": []}))
    result = runner.invoke(app, ["freeze", "draft.json"])
    assert result.exit_code != 0
    assert "Freeze failed" in result.output


def test_freeze_reports_an_unknown_tool_actionably(project, fake_cfng, credentials):
    draft = json.loads(json.dumps(DRAFT))
    draft["steps"][0]["with"]["tool"] = "nope"
    (project / "draft.json").write_text(json.dumps(draft))

    result = runner.invoke(app, ["freeze", "draft.json"])
    assert result.exit_code != 0
    assert "no tool 'nope'" in result.output


def test_freeze_refuses_a_literal_secret_in_the_draft(project, fake_cfng, credentials):
    draft = json.loads(json.dumps(DRAFT))
    draft["steps"][0]["with"]["args"] = {"token": "cfng_livetoken123456"}  # pragma: allowlist secret
    (project / "draft.json").write_text(json.dumps(draft))

    result = runner.invoke(app, ["freeze", "draft.json"])
    assert result.exit_code != 0
    assert "literal secret" in result.output


def test_doctor_reports_config_and_token_state(project, credentials):
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "osiris.yaml" in result.output
    assert "CFNG_TOKEN" in result.output


def test_doctor_fails_when_the_config_is_absent(tmp_path, monkeypatch, credentials):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code != 0
    assert "osiris.yaml" in result.output


def test_doctor_fails_when_credentials_are_absent(project, monkeypatch):
    monkeypatch.delenv("CFNG_BASE_URL", raising=False)
    monkeypatch.delenv("CFNG_TOKEN", raising=False)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code != 0
    assert "CFNG_TOKEN is not set" in result.output


def test_doctor_never_prints_the_token_value(project, monkeypatch):
    monkeypatch.setenv("CFNG_BASE_URL", "https://cfng.test")
    monkeypatch.setenv("CFNG_TOKEN", "cfng_supersecretvalue")  # pragma: allowlist secret
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "supersecretvalue" not in result.output


def test_serve_refuses_to_start_without_credentials(project, monkeypatch):
    """The credential check runs before the relay is started or a session opened."""
    monkeypatch.delenv("CFNG_BASE_URL", raising=False)
    monkeypatch.delenv("CFNG_TOKEN", raising=False)

    import osiris.relay.server as relay_module

    def explode(*args, **kwargs):
        raise AssertionError("serve reached the relay before checking credentials")

    monkeypatch.setattr(relay_module, "serve_stdio", explode)

    result = runner.invoke(app, ["serve"])
    assert result.exit_code != 0
    assert "CFNG_TOKEN" in result.output
    # Nothing was created on the way out: no session directory, no evidence.
    assert not (project / ".osiris" / "sessions").exists()


def test_a_successful_run_leaves_the_token_in_no_file_anywhere(project, fake_cfng, live_credentials):
    """Every file under base_path, byte-grepped, on the path that writes the most.

    The predecessor of this test asserted `exit_code == 0` and grepped only
    `run_logs/demo/**/events.jsonl` — the one file that was already correct —
    while the same token sat in plaintext in the ledger, in the NDJSON artifact
    and in the DuckDB file. Scope is the whole point here.
    """
    # cf-ng echoes the presented credential back inside a tool result, which is
    # what a misconfigured connector or a reflective debug endpoint does.
    fake_cfng["result"] = [{"a": 1, "note": f"authenticated with {LIVE_TOKEN}"}]
    build_dir = _freeze(project)

    result = runner.invoke(app, ["run", str(build_dir)])
    assert result.exit_code == 0, result.output

    # The sweep is only meaningful if it looked at the files that carry data.
    swept = {path.name for path in _files_under(project)}
    assert {"events.jsonl", "runs.jsonl", "pipeline_data.duckdb", "fetch.ndjson"} <= swept, swept
    assert _leaking_files(project, LIVE_TOKEN) == []
    assert LIVE_TOKEN not in result.output

    # The payload did arrive and was scrubbed, rather than never arriving.
    artifact = next(iter((project / "run_logs").rglob("fetch.ndjson"))).read_text()
    assert "***" in artifact

    # Control: the sweep can find what it is looking for.
    (project / "decoy.txt").write_bytes(LIVE_TOKEN.encode())
    assert _leaking_files(project, LIVE_TOKEN) == [project / "decoy.txt"]


def test_a_failed_run_leaves_the_token_in_no_file_anywhere(project, fake_cfng, live_credentials):
    """The failure path writes different files than the success path, and leaked worse.

    A cf-ng 403 quotes the credential it rejected. That sentence reaches the
    ledger, the evidence stream and stdout; `runs.jsonl` used to hold it in
    plaintext while `events.jsonl` wrote the identical sentence as `***`.
    """
    build_dir = _freeze(project)
    fake_cfng["fail"] = (403, f"token {LIVE_TOKEN} is not authorized for connector imdb")

    result = runner.invoke(app, ["run", str(build_dir)])
    assert result.exit_code == 1, result.output
    _assert_handled(result)

    swept = {path.name for path in _files_under(project)}
    assert {"events.jsonl", "runs.jsonl"} <= swept, swept
    assert _leaking_files(project, LIVE_TOKEN) == []
    assert LIVE_TOKEN not in result.output

    # The rejecting sentence did reach the ledger, redacted rather than dropped.
    ledger = (project / ".osiris" / "index" / "runs.jsonl").read_text()
    assert "***" in ledger
    assert "not authorized" in ledger


def test_freeze_never_prints_the_token_when_cfng_echoes_it(project, fake_cfng, live_credentials):
    """`osiris freeze > build.log` must not persist what events.jsonl would mask."""
    fake_cfng["fail"] = (403, f"token {LIVE_TOKEN} is not authorized")
    (project / "draft.json").write_text(json.dumps(DRAFT))

    result = runner.invoke(app, ["freeze", "draft.json"])
    assert result.exit_code != 0
    assert LIVE_TOKEN not in result.output
    assert "***" in result.output
    assert _leaking_files(project, LIVE_TOKEN) == []


def test_run_refuses_a_tampered_manifest_whose_plan_fingerprint_was_recomputed(project, fake_cfng, credentials):
    """The report's exact attack, and the reason this defect was rated HIGH.

    Edit the manifest, then recompute `fingerprints["plan"]` — the only value
    the checker used to read — with the repo's own public API. Two lines, no
    privileged knowledge, and the tampered plan executed with exit 0 while the
    ledger certified the pre-tamper hash.
    """
    build_dir = _freeze(project)
    data = _manifest(build_dir)
    data["steps"].append({"id": "pwned", "uses": "sql", "with": {"query": "SELECT * FROM (VALUES (1),(2)) t(pwned)"}})
    _write_manifest(build_dir, data)

    recorded = _fingerprints(build_dir)
    recorded["plan"] = _recompute(data)["plan"]
    _write_fingerprints(build_dir, recorded)

    result = runner.invoke(app, ["run", str(build_dir)])
    assert result.exit_code == 1, result.output
    _assert_handled(result)
    assert "fingerprint" in result.output
    # Nothing executed and nothing was recorded as having executed.
    assert not (project / "run_logs").exists()
    assert not (project / ".osiris" / "index" / "runs.jsonl").exists()


def test_run_refuses_a_tampered_artifact_with_every_fingerprint_recomputed(project, fake_cfng, credentials):
    """The next move: recompute all three consistently and rewrite both files.

    Every fingerprint then verifies and the internal relation holds. What the
    attacker has not done is move the artifact: freeze names the directory after
    the manifest hash, so the name still says who the artifact used to be.

    Renaming the directory as well would produce a coherent artifact — an
    unkeyed checksum stored beside the thing it protects cannot prevent that.
    Closing it needs a signature; what this closes is every partial edit.
    """
    build_dir = _freeze(project)
    data = _manifest(build_dir)
    data["steps"].append({"id": "pwned", "uses": "sql", "with": {"query": "SELECT 1 AS pwned"}})
    values = _recompute(data)
    data["fingerprints"] = values
    _write_manifest(build_dir, data)
    _write_fingerprints(build_dir, values)

    result = runner.invoke(app, ["run", str(build_dir)])
    assert result.exit_code == 1, result.output
    _assert_handled(result)
    assert build_dir.name in result.output
    assert "fingerprint" in result.output
    assert not (project / "run_logs").exists()


def test_run_refuses_an_artifact_whose_pins_were_edited(project, fake_cfng, credentials):
    """Pins are what make a frozen plan a contract, so they get their own check."""
    build_dir = _freeze(project)
    data = _manifest(build_dir)
    pin = next(iter(data["pins"]["tools"]))
    data["pins"]["tools"][pin]["input"] = "sha256:" + "0" * 64
    # The plan fingerprint covers the pins, so recompute it: this attacks the
    # pins fingerprint specifically rather than tripping check one.
    recorded = _fingerprints(build_dir)
    recorded["plan"] = _recompute(data)["plan"]
    _write_manifest(build_dir, data)
    _write_fingerprints(build_dir, recorded)

    result = runner.invoke(app, ["run", str(build_dir)])
    assert result.exit_code == 1, result.output
    assert "pins fingerprint" in result.output


def test_run_refuses_when_fingerprints_json_alone_is_edited(project, fake_cfng, credentials):
    """The recorded value is a claim about the manifest, not a value to trust."""
    build_dir = _freeze(project)
    recorded = _fingerprints(build_dir)
    recorded["plan"] = "sha256:" + "1" * 64
    _write_fingerprints(build_dir, recorded)

    result = runner.invoke(app, ["run", str(build_dir)])
    assert result.exit_code == 1, result.output
    assert "fingerprint" in result.output


def test_run_refuses_a_fingerprints_file_that_is_internally_inconsistent(project, fake_cfng, credentials):
    """`manifest == sha256(plan + pins)` is free, and it is what catches a lone edit."""
    build_dir = _freeze(project)
    recorded = _fingerprints(build_dir)
    recorded["manifest"] = "sha256:" + "2" * 64
    _write_fingerprints(build_dir, recorded)

    result = runner.invoke(app, ["run", str(build_dir)])
    assert result.exit_code == 1, result.output
    assert "inconsistent" in result.output


def test_run_refuses_when_the_manifest_declares_different_fingerprints(project, fake_cfng, credentials):
    """The manifest's own `fingerprints:` block is excluded from every hash.

    That is exactly why it must never be a source: the ledger used to read the
    hash it certified from this block. Here it is a subject instead — a
    disagreement with fingerprints.json is evidence of an edit.
    """
    build_dir = _freeze(project)
    data = _manifest(build_dir)
    data["fingerprints"]["manifest"] = "sha256:" + "3" * 64
    _write_manifest(build_dir, data)

    result = runner.invoke(app, ["run", str(build_dir)])
    assert result.exit_code == 1, result.output
    assert "disagree" in result.output


def test_run_refuses_a_renamed_build_directory(project, fake_cfng, credentials):
    """A build directory is identified by its hash, so its name is checked too."""
    build_dir = _freeze(project)
    renamed = build_dir.parent / "0123456789ab"
    build_dir.rename(renamed)

    result = runner.invoke(app, ["run", str(renamed)])
    assert result.exit_code == 1, result.output
    assert "0123456789ab" in result.output
    assert not (project / "run_logs").exists()


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        "[]",
        '{"plan": 1, "pins": 2, "manifest": 3}',
        '{"plan": "sha256:x"}',
    ],
)
def test_run_reports_a_malformed_fingerprints_file_instead_of_a_traceback(project, fake_cfng, credentials, content):
    """A truncated or rewritten fingerprints.json used to raise TypeError/JSONDecodeError."""
    build_dir = _freeze(project)
    (build_dir / "fingerprints.json").write_text(content)

    result = runner.invoke(app, ["run", str(build_dir)])
    assert result.exit_code == 1, result.output
    _assert_handled(result)
    assert "fingerprints.json" in result.output


def test_benign_reformatting_of_the_artifact_is_still_accepted(project, fake_cfng, credentials):
    """A checker that refuses everything is as useless as one that accepts everything.

    Canonicalization tolerance is a real property of this design: flow style,
    key order, comments and JSON indentation carry no meaning, so rewriting them
    must not be mistaken for tampering.
    """
    build_dir = _freeze(project)
    data = _manifest(build_dir)
    _write_manifest(build_dir, data, default_flow_style=True, sort_keys=True, width=40)
    manifest_path = build_dir / "manifest.yaml"
    manifest_path.write_text("# reformatted by hand, meaning unchanged\n" + manifest_path.read_text() + "\n\n")
    _write_fingerprints(build_dir, dict(reversed(list(_fingerprints(build_dir).items()))), indent=8)

    result = runner.invoke(app, ["run", str(build_dir)])
    assert result.exit_code == 0, result.output
    assert "success" in result.output


def test_the_ledger_records_the_verified_hash_not_the_manifests_self_declaration(project, fake_cfng, credentials):
    """The audit trail must name what ran: the hash that passed verification."""
    from osiris.evidence.run_index import RunIndex

    build_dir = _freeze(project)
    assert runner.invoke(app, ["run", str(build_dir)]).exit_code == 0

    record = RunIndex(project / ".osiris" / "index" / "runs.jsonl").latest()[0]
    assert record.manifest_hash == _fingerprints(build_dir)["manifest"]
    # And it resolves to the directory that actually ran.
    assert record.manifest_hash.removeprefix("sha256:").startswith(build_dir.name)


def test_the_ledger_hash_survives_a_manifest_with_no_fingerprints_block(project, fake_cfng, credentials):
    """The manifest's `fingerprints:` block is excluded from every hash, so
    deleting it changes nothing that is verified and the artifact still runs.

    What used to happen then was a ledger row whose manifest_hash was the empty
    string, because the CLI read the hash it certified out of that block. The
    ledger's source has to be the value that was verified, not the artifact's
    account of itself.
    """
    from osiris.evidence.run_index import RunIndex

    build_dir = _freeze(project)
    data = _manifest(build_dir)
    del data["fingerprints"]
    _write_manifest(build_dir, data)

    result = runner.invoke(app, ["run", str(build_dir)])
    assert result.exit_code == 0, result.output

    record = RunIndex(project / ".osiris" / "index" / "runs.jsonl").latest()[0]
    assert record.manifest_hash == _fingerprints(build_dir)["manifest"]


def test_a_failure_after_the_run_started_still_leaves_a_ledger_row(project, fake_cfng, credentials):
    """A transport failure on the tool call itself is neither DriftError nor StepError.

    The CLI caught exactly those two, so this shape exited with a traceback and
    wrote nothing to the ledger — contradicting the comment right above the
    handler. The backstop is every exception, not a maintained list of them.
    """
    from osiris.evidence.run_index import RunIndex

    build_dir = _freeze(project)
    fake_cfng["fail_call"] = httpx.ConnectError("connection reset mid-call")

    result = runner.invoke(app, ["run", str(build_dir)])
    assert result.exit_code == 1, result.output
    _assert_handled(result)
    assert "Run failed" in result.output

    record = RunIndex(project / ".osiris" / "index" / "runs.jsonl").latest()[0]
    assert record.status == "failed"
    assert "connection reset mid-call" in (record.error or "")
    # The pins were verified before the call, so the evidence says so.
    events = "".join(path.read_text() for path in (project / "run_logs" / "demo").rglob("events.jsonl"))
    assert "artifact_verified" in events


def test_a_verified_run_is_distinguishable_from_an_unverified_one(project, fake_cfng, credentials):
    """Verification that leaves no trace is indistinguishable from a skipped check."""
    build_dir = _freeze(project)
    assert runner.invoke(app, ["run", str(build_dir)]).exit_code == 0

    events = [
        json.loads(line)
        for path in (project / "run_logs" / "demo").rglob("events.jsonl")
        for line in path.read_text().splitlines()
        if line.strip()
    ]
    verified = [event for event in events if event["event"] == "artifact_verified"]
    assert len(verified) == 1
    recorded = _fingerprints(build_dir)
    assert verified[0]["manifest_fingerprint"] == recorded["manifest"]
    assert verified[0]["plan_fingerprint"] == recorded["plan"]
    assert set(verified[0]["verified"]) == {"plan", "pins", "manifest"}
    assert verified[0]["build_dir"] == str(build_dir)


def test_a_connector_404_is_recorded_and_explained(project, fake_cfng, credentials):
    """`CfngError` from the pin probe used to escape as a traceback with no ledger row."""
    from osiris.evidence.run_index import RunIndex

    build_dir = _freeze(project)
    fake_cfng["fail"] = (404, "connector 'imdb' does not exist")

    result = runner.invoke(app, ["run", str(build_dir)])
    assert result.exit_code == 1, result.output
    _assert_handled(result)
    assert "imdb" in result.output
    assert "re-freeze" in result.output.lower()

    record = RunIndex(project / ".osiris" / "index" / "runs.jsonl").latest()[0]
    assert record.status == "failed"
    assert "imdb" in (record.error or "")
    assert record.manifest_hash == _fingerprints(build_dir)["manifest"]


def test_an_unreachable_cfng_is_recorded_and_explained(project, fake_cfng, credentials):
    """A transport failure is not an HTTP status, and used to be a traceback too."""
    from osiris.evidence.run_index import RunIndex

    build_dir = _freeze(project)
    fake_cfng["fail"] = httpx.ConnectError("connection refused")

    result = runner.invoke(app, ["run", str(build_dir)])
    assert result.exit_code == 1, result.output
    _assert_handled(result)
    assert "CFNG_BASE_URL" in result.output

    assert RunIndex(project / ".osiris" / "index" / "runs.jsonl").latest()[0].status == "failed"


def test_dry_run_reports_an_unreachable_cfng_instead_of_a_traceback(project, fake_cfng, credentials):
    build_dir = _freeze(project)
    fake_cfng["fail"] = httpx.ConnectError("connection refused")

    result = runner.invoke(app, ["run", str(build_dir), "--dry-run"])
    assert result.exit_code == 1, result.output
    _assert_handled(result)
    assert "CFNG_BASE_URL" in result.output
    # Nothing ran, so nothing is claimed to have run.
    assert not (project / ".osiris" / "index" / "runs.jsonl").exists()
    assert "Pins verified" not in result.output


# --- .env loading -----------------------------------------------------------
#
# python-dotenv was declared and never imported, so a valid .env did nothing and
# `osiris doctor` reported the variables unset. A dependency that is shipped but
# not wired is a promise the CLI does not keep.


def test_env_file_supplies_missing_variables(project, monkeypatch):
    monkeypatch.delenv(BASE_URL_ENV, raising=False)
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    (project / ".env").write_text(
        f"{BASE_URL_ENV}=https://from-dotenv.test\n{TOKEN_ENV}=cfng_from_dotenv\n"
    )  # pragma: allowlist secret

    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert f"{BASE_URL_ENV} is set" in result.output
    assert f"{TOKEN_ENV} is set" in result.output


def test_an_exported_variable_beats_the_env_file(project, monkeypatch):
    """Otherwise you cannot point at a different cf-ng without editing the file."""
    (project / ".env").write_text(f"{BASE_URL_ENV}=https://from-dotenv.test\n")
    monkeypatch.setenv(BASE_URL_ENV, "https://exported.test")
    monkeypatch.setenv(TOKEN_ENV, "cfng_x")  # pragma: allowlist secret

    load_env(project)
    assert os.environ[BASE_URL_ENV] == "https://exported.test"


def test_doctor_still_fails_without_an_env_file(project, monkeypatch):
    monkeypatch.delenv(BASE_URL_ENV, raising=False)
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code != 0
    assert TOKEN_ENV in result.output


def test_the_env_file_value_never_reaches_the_console(project, monkeypatch):
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    monkeypatch.setenv(BASE_URL_ENV, "https://x.test")
    (project / ".env").write_text(f"{TOKEN_ENV}=cfng_LiVeT0kenFromDotEnvFile\n")  # pragma: allowlist secret

    result = runner.invoke(app, ["doctor"])
    assert "cfng_LiVeT0kenFromDotEnvFile" not in result.output  # pragma: allowlist secret


def test_run_rejects_an_artifact_moved_under_a_different_plan_name(project, fake_cfng, credentials):
    """Check 5 validated only the leaf, so a verified artifact could be relocated.

    The layout would then say one thing and the manifest another, and the run
    ledger keys on the plan name.
    """
    build_dir = _freeze(project)
    moved = project / "build" / "some-other-plan" / build_dir.name
    moved.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(build_dir, moved)

    result = runner.invoke(app, ["run", str(moved)])
    assert result.exit_code != 0
    assert "some-other-plan" in result.output
    assert "moved" in result.output.lower()


def test_run_accepts_the_artifact_where_freeze_put_it(project, fake_cfng, credentials):
    """The parent check must not reject the honest layout."""
    build_dir = _freeze(project)
    assert runner.invoke(app, ["run", str(build_dir)]).exit_code == 0
