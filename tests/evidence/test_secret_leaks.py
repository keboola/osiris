"""No credential reaches ANY file under base_path, on either exit path.

The test this replaces (`test_run_evidence_redacts_the_token`) grepped exactly
one file, `events.jsonl` — the one file that was already correct — and stayed
green while the token sat in `runs.jsonl`, in `artifacts/*.ndjson` and inside
`pipeline_data.duckdb`. A leak test that names the file it trusts cannot fail.

So these tests name nothing. They drive the real CLI end to end against a cf-ng
that echoes the presented credential back — once in a tool result (success
path), once in a 403 detail (failure path) — and then byte-grep every file under
base_path, binary ones included. `read_bytes` rather than `read_text` is the
whole point: the DuckDB file is binary, and `read_text` would have raised on it,
which is precisely how a binary leak stays invisible.
"""

import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from osiris.cli import app

runner = CliRunner()

# Shaped like a real cf-ng token: long enough that a substring hit is not chance.
TOKEN = "cfng_LiVeT0kenAbCdEf0123456789"  # pragma: allowlist secret

DRAFT = {
    "metadata": {"name": "demo"},
    "params": {},
    "steps": [{"id": "fetch", "uses": "cfng_call", "with": {"connector": "imdb", "tool": "search"}}],
}
IMDB = [{"name": "search", "inputSchema": {"type": "object"}}]


def files_containing(root: Path, needle: str) -> list[Path]:
    """Every file under `root` whose raw bytes contain `needle`.

    Walks the complete tree — dotted directories included, since `.osiris/`
    holds the run ledger — and compares bytes, so a binary file (DuckDB) is
    searched exactly like a text one instead of being skipped as undecodable.
    """
    probe = needle.encode("utf-8")
    hits: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink() and probe in path.read_bytes():
            hits.append(path)
    return hits


def _tree(root: Path) -> list[str]:
    """Relative paths of every file under root — reported when a sweep fails."""
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init"]).exit_code == 0
    return tmp_path


@pytest.fixture
def live_token(monkeypatch):
    monkeypatch.setenv("CFNG_BASE_URL", "https://cfng.test")
    monkeypatch.setenv("CFNG_TOKEN", TOKEN)
    return TOKEN


def _install_cfng(monkeypatch, call_response):
    """Point the CLI's client factory at a cf-ng whose /tools/call is scripted."""

    def handler(request):
        if request.url.path == "/catalog/version":
            return httpx.Response(200, json={"catalog_version": "sha256:cat1"})
        if request.url.path.endswith("/tools"):
            return httpx.Response(200, json={"connector": "imdb", "tools": IMDB})
        return call_response(request)

    import osiris.cli as cli_module

    original = cli_module.CfngClient

    def patched(*args, **kwargs):
        client = original(*args, **kwargs)
        client._http = httpx.Client(transport=httpx.MockTransport(handler), base_url=client.base_url)
        return client

    monkeypatch.setattr(cli_module, "CfngClient", patched)


@pytest.fixture
def cfng_echoes_the_token_in_a_result(monkeypatch):
    """A tool whose result reflects the credential — a config or whoami endpoint."""

    def call(request):
        return httpx.Response(
            200,
            json={
                "connector": "imdb",
                "tool": "search",
                "result": [{"title": "Dune", "authorization": f"Bearer {TOKEN}"}],
                "_meta": {"server_ms": 1.0},
            },
        )

    _install_cfng(monkeypatch, call)


@pytest.fixture
def cfng_echoes_the_token_in_a_403(monkeypatch):
    """The canonical leak: a rejection that quotes what was presented."""

    def call(request):
        return httpx.Response(403, json={"detail": f"token {TOKEN} is not authorized for connector imdb"})

    _install_cfng(monkeypatch, call)


def _freeze(project) -> Path:
    (project / "draft.json").write_text(json.dumps(DRAFT))
    frozen = runner.invoke(app, ["freeze", "draft.json"])
    assert frozen.exit_code == 0, frozen.output
    return next((project / "build").rglob("manifest.yaml")).parent


def test_the_sweep_finds_a_planted_token(tmp_path):
    """Guard against a vacuous sweep: the helper must actually find things.

    Both cases matter — a dotted directory (where the ledger lives) and a binary
    file with an embedded NUL (where DuckDB puts it).
    """
    (tmp_path / ".osiris" / "index").mkdir(parents=True)
    (tmp_path / ".osiris" / "index" / "runs.jsonl").write_text(f'{{"error":"{TOKEN}"}}\n')
    (tmp_path / "pipeline_data.duckdb").write_bytes(b"DUCK\x00\x00" + TOKEN.encode() + b"\x00pad")
    (tmp_path / "clean.txt").write_text("nothing here")

    hits = {p.name for p in files_containing(tmp_path, TOKEN)}
    assert hits == {"runs.jsonl", "pipeline_data.duckdb"}


def test_the_sweep_reads_binary_files_without_raising(tmp_path):
    """read_text() on a DuckDB file raises; a sweep that skips it sees nothing."""
    (tmp_path / "binary.duckdb").write_bytes(bytes(range(256)))
    assert files_containing(tmp_path, TOKEN) == []


def test_no_token_anywhere_under_base_path_on_the_success_path(project, cfng_echoes_the_token_in_a_result, live_token):
    build_dir = _freeze(project)
    result = runner.invoke(app, ["run", str(build_dir)])
    assert result.exit_code == 0, result.output

    # The sweep is only meaningful if the run wrote the files it is meant to
    # search. Assert each leak site from the report exists before greping.
    written = _tree(project)
    assert any(name.endswith("pipeline_data.duckdb") for name in written), written
    assert any(name.endswith("fetch.ndjson") for name in written), written
    assert any(name.endswith("events.jsonl") for name in written), written
    assert any(name.endswith("runs.jsonl") for name in written), written

    leaks = files_containing(project, TOKEN)
    assert leaks == [], f"token on disk in: {[str(p.relative_to(project)) for p in leaks]}"


def test_no_token_anywhere_under_base_path_on_the_failure_path(project, cfng_echoes_the_token_in_a_403, live_token):
    from osiris.evidence.run_index import RunIndex  # noqa: PLC0415

    build_dir = _freeze(project)
    result = runner.invoke(app, ["run", str(build_dir)])
    assert result.exit_code != 0

    # The failure must have been recorded, or there is nothing to leak into.
    ledger = project / ".osiris" / "index" / "runs.jsonl"
    assert ledger.exists(), _tree(project)
    record = RunIndex(ledger).latest()[0]
    assert record.status == "failed"
    assert record.error, "the ledger recorded a failure with no detail"

    leaks = files_containing(project, TOKEN)
    assert leaks == [], f"token on disk in: {[str(p.relative_to(project)) for p in leaks]}"


def test_the_ndjson_artifact_is_still_faithful_apart_from_the_secret(
    project, cfng_echoes_the_token_in_a_result, live_token
):
    """Redaction is targeted: only the credential substring is rewritten."""
    build_dir = _freeze(project)
    assert runner.invoke(app, ["run", str(build_dir)]).exit_code == 0

    artifact = next((project / "run_logs").rglob("fetch.ndjson"))
    row = json.loads(artifact.read_text(encoding="utf-8").splitlines()[0])
    assert row["title"] == "Dune"
    assert row["authorization"] == "Bearer ***"
