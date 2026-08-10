"""The CLI wires the pieces together and fails with actionable messages."""

import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner
import yaml

from osiris.cli import app

runner = CliRunner()

DRAFT = {
    "metadata": {"name": "demo"},
    "params": {},
    "steps": [{"id": "fetch", "uses": "cfng_call", "with": {"connector": "imdb", "tool": "search"}}],
}
IMDB = [{"name": "search", "inputSchema": {"type": "object"}}]


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
def fake_cfng(monkeypatch):
    """Swap the client factory the CLI looks up, keeping the real client's logic."""

    def handler(request):
        if request.url.path == "/catalog/version":
            return httpx.Response(200, json={"catalog_version": "sha256:cat1"})
        if request.url.path.endswith("/tools"):
            return httpx.Response(200, json={"connector": "imdb", "tools": IMDB})
        return httpx.Response(
            200,
            json={"connector": "imdb", "tool": "search", "result": [{"a": 1}], "_meta": {"server_ms": 1.0}},
        )

    import osiris.cli as cli_module

    original = cli_module.CfngClient

    def patched(*args, **kwargs):
        client = original(*args, **kwargs)
        client._http = httpx.Client(transport=httpx.MockTransport(handler), base_url=client.base_url)
        return client

    monkeypatch.setattr(cli_module, "CfngClient", patched)


def _freeze(project) -> Path:
    """Freeze DRAFT and return the build directory."""
    (project / "draft.json").write_text(json.dumps(DRAFT))
    frozen = runner.invoke(app, ["freeze", "draft.json"])
    assert frozen.exit_code == 0, frozen.output
    return next((project / "build").rglob("manifest.yaml")).parent


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


def test_run_evidence_redacts_the_token(project, fake_cfng, monkeypatch):
    """The token is a session secret, so it can never reach events.jsonl."""
    monkeypatch.setenv("CFNG_BASE_URL", "https://cfng.test")
    monkeypatch.setenv("CFNG_TOKEN", "cfng_secretvalue1234")  # pragma: allowlist secret
    build_dir = _freeze(project)
    assert runner.invoke(app, ["run", str(build_dir)]).exit_code == 0

    events = (project / "run_logs" / "demo").rglob("events.jsonl")
    text = "".join(path.read_text() for path in events)
    assert "run_start" in text
    assert "cfng_secretvalue1234" not in text  # pragma: allowlist secret
