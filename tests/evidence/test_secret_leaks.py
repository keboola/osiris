"""No credential reaches ANY file under base_path, on either exit path.

The test this replaces (`test_run_evidence_redacts_the_token`) grepped exactly
one file, `events.jsonl` — the one file that was already correct — and stayed
green while the token sat in `runs.jsonl`, in `artifacts/*.ndjson` and inside
`pipeline_data.duckdb`. A leak test that names the file it trusts cannot fail.

So these tests name nothing. They drive the real CLI end to end against a cf-ng
that echoes credentials back — once in a tool result (success path), once in a
403 detail (failure path) — and then byte-grep every file under base_path,
binary ones included. `read_bytes` rather than `read_text` is the whole point:
the DuckDB file is binary, and `read_text` would have raised on it, which is
precisely how a binary leak stays invisible.

They also passed 5/5 through a second leak, for a second reason: they hunted
exactly one value, `$CFNG_TOKEN`, so redaction keyed to that one value looked
total. Every credential Osiris does *not* hold went to disk in the clear beside
it. So the sweep now carries three credentials — the process's own, a foreign
flat-shaped one, and a foreign `cfng_v1.<base64>`-shaped one — and no test may
grep for only the value this process happens to know.
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

# A credential this process has never held and cannot match by value. cf-ng
# injects a `credentials` argument into every tool's inputSchema by design
# (osiris/cfng/client.py), so somebody else's token arriving in a payload is the
# documented case, not an exotic one.
FOREIGN_TOKEN = "cfng_0THER_Ag3ntPastedTokenZZ99"  # pragma: allowlist secret

# The real cf-ng token shape. The `.` is exactly what the old exact-substring
# redaction and the old `cfng_[A-Za-z0-9_\-]{8,}` freeze guard both could not
# see, which is how a token in this form reached a verified manifest at exit 0.
FOREIGN_V1_TOKEN = "cfng_v1.9Xq2vB7tR4mN8pL3wZ6yK1sH0dF5gJ2a"  # pragma: allowlist secret

# Every credential the sweep hunts. A test that greps one of these and calls it
# a guarantee is the failure mode this file exists to prevent.
CREDENTIALS = (TOKEN, FOREIGN_TOKEN, FOREIGN_V1_TOKEN)

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
def cfng_echoes_credentials_in_a_result(monkeypatch):
    """A tool whose result reflects credentials — a config or whoami endpoint.

    Three of them, only one of which this process holds. The other two are what
    the previous version of this fixture could not model, and therefore what the
    previous version of these tests could not catch.
    """

    def call(request):
        return httpx.Response(
            200,
            json={
                "connector": "imdb",
                "tool": "search",
                "result": [
                    {
                        "title": "Dune",
                        "authorization": f"Bearer {TOKEN}",
                        "credentials": {"api_token": FOREIGN_TOKEN},
                        "note": f"connector configured with {FOREIGN_V1_TOKEN}",
                    }
                ],
                "_meta": {"server_ms": 1.0},
            },
        )

    _install_cfng(monkeypatch, call)


@pytest.fixture
def cfng_echoes_credentials_in_a_403(monkeypatch):
    """The canonical leak: a rejection that quotes what was presented.

    The report's exact sentence — the process's own token masked to `***` in the
    same string where two foreign ones sat in the clear.
    """

    def call(request):
        detail = (
            f"token {TOKEN} is not authorized for connector imdb "
            f'(req={{"credentials":{{"api_token":"{FOREIGN_V1_TOKEN}"}}}}); '
            f"presented {FOREIGN_TOKEN}"
        )
        return httpx.Response(403, json={"detail": detail})

    _install_cfng(monkeypatch, call)


def _freeze(project) -> Path:
    (project / "draft.json").write_text(json.dumps(DRAFT))
    frozen = runner.invoke(app, ["freeze", "draft.json"])
    assert frozen.exit_code == 0, frozen.output
    return next((project / "build").rglob("manifest.yaml")).parent


@pytest.mark.parametrize("credential", CREDENTIALS)
def test_the_sweep_finds_a_planted_token(tmp_path, credential):
    """Guard against a vacuous sweep: the helper must actually find things.

    Both cases matter — a dotted directory (where the ledger lives) and a binary
    file with an embedded NUL (where DuckDB puts it). Run for each credential so
    that a shape the helper cannot represent (the `.` in `cfng_v1.…`) fails here
    rather than silently making the real sweeps below unfalsifiable.
    """
    (tmp_path / ".osiris" / "index").mkdir(parents=True)
    (tmp_path / ".osiris" / "index" / "runs.jsonl").write_text(f'{{"error":"{credential}"}}\n')
    (tmp_path / "pipeline_data.duckdb").write_bytes(b"DUCK\x00\x00" + credential.encode() + b"\x00pad")
    (tmp_path / "clean.txt").write_text("nothing here")

    hits = {p.name for p in files_containing(tmp_path, credential)}
    assert hits == {"runs.jsonl", "pipeline_data.duckdb"}


def test_the_sweep_reads_binary_files_without_raising(tmp_path):
    """read_text() on a DuckDB file raises; a sweep that skips it sees nothing."""
    (tmp_path / "binary.duckdb").write_bytes(bytes(range(256)))
    assert files_containing(tmp_path, TOKEN) == []


def _assert_no_credential_under(project: Path) -> None:
    """No credential — ours or anyone else's — anywhere beneath base_path."""
    for credential in CREDENTIALS:
        leaks = files_containing(project, credential)
        assert leaks == [], f"credential on disk in: {[str(p.relative_to(project)) for p in leaks]}"


def test_no_credential_anywhere_under_base_path_on_the_success_path(
    project, cfng_echoes_credentials_in_a_result, live_token
):
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

    _assert_no_credential_under(project)


def test_no_credential_anywhere_under_base_path_on_the_failure_path(
    project, cfng_echoes_credentials_in_a_403, live_token
):
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
    # And the sentence that carried all three credentials survived as a sentence,
    # so the sweep below is passing because of redaction and not because the
    # ledger row is empty.
    assert "not authorized" in record.error
    assert "***" in record.error

    _assert_no_credential_under(project)


def test_a_foreign_credential_is_masked_in_the_same_sentence_as_our_own(
    project, cfng_echoes_credentials_in_a_403, live_token
):
    """The defect stated precisely: `***` for the token we hold, plaintext for the rest.

    A whole-tree sweep proves absence; this proves the mechanism, so a
    regression that (say) truncated the ledger error would not read as a pass.
    """
    from osiris.evidence.run_index import RunIndex  # noqa: PLC0415

    build_dir = _freeze(project)
    assert runner.invoke(app, ["run", str(build_dir)]).exit_code != 0

    error = RunIndex(project / ".osiris" / "index" / "runs.jsonl").latest()[0].error or ""
    assert "for connector imdb" in error, error
    assert error.count("***") == 3, error


def test_stdout_never_carries_a_credential_either(project, cfng_echoes_credentials_in_a_403, live_token):
    """`osiris run > nightly.log` is outside the evidence system and persists anyway."""
    build_dir = _freeze(project)
    result = runner.invoke(app, ["run", str(build_dir)])
    assert result.exit_code != 0
    for credential in CREDENTIALS:
        assert credential not in result.output, result.output
    assert "***" in result.output


def test_the_ndjson_artifact_is_still_faithful_apart_from_the_secrets(
    project, cfng_echoes_credentials_in_a_result, live_token
):
    """Redaction is targeted: only the credential runs are rewritten.

    The shape rule matches a span, not a line, so everything around a masked
    token — the ordinary field beside it, and the prose either side of it in the
    same string — has to come through untouched or the evidence is worthless.
    """
    build_dir = _freeze(project)
    assert runner.invoke(app, ["run", str(build_dir)]).exit_code == 0

    artifact = next((project / "run_logs").rglob("fetch.ndjson"))
    row = json.loads(artifact.read_text(encoding="utf-8").splitlines()[0])
    assert row["title"] == "Dune"
    assert row["authorization"] == "Bearer ***"
    assert row["credentials"] == {"api_token": "***"}
    assert row["note"] == "connector configured with ***"
