"""The run index is append-only, redacted, and survives concurrent writers."""

from osiris.evidence.run_index import RunIndex, RunRecord
from osiris.evidence.session import REDACTED

TOKEN = "cfng_LiVeT0ken_ledger"  # pragma: allowlist secret


def _rec(run_id: str, status: str = "success", error: str | None = None) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        plan_name="demo",
        manifest_hash="a71f3c9",
        started_at="2026-08-10T14:05:09Z",
        finished_at="2026-08-10T14:05:12Z",
        status=status,
        error=error,
    )


def test_append_then_read(tmp_path):
    idx = RunIndex(tmp_path / "runs.jsonl")
    idx.append(_rec("run_1"))
    idx.append(_rec("run_2", status="failed"))
    records = idx.read_all()
    assert [r.run_id for r in records] == ["run_1", "run_2"]
    assert records[1].status == "failed"


def test_creates_parent_directory(tmp_path):
    idx = RunIndex(tmp_path / "deep" / "nested" / "runs.jsonl")
    idx.append(_rec("run_1"))
    assert idx.read_all()[0].run_id == "run_1"


def test_read_all_on_missing_file_is_empty(tmp_path):
    assert RunIndex(tmp_path / "absent.jsonl").read_all() == []


def test_latest_returns_most_recent_first(tmp_path):
    idx = RunIndex(tmp_path / "runs.jsonl")
    for i in range(5):
        idx.append(_rec(f"run_{i}"))
    assert [r.run_id for r in idx.latest(2)] == ["run_4", "run_3"]


def test_concurrent_appends_do_not_interleave(tmp_path):
    """Every line must remain valid JSON under concurrent writers."""
    from concurrent.futures import ThreadPoolExecutor
    import json

    path = tmp_path / "runs.jsonl"
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: RunIndex(path).append(_rec(f"run_{i}")), range(64)))

    lines = path.read_text().splitlines()
    assert len(lines) == 64
    for line in lines:
        json.loads(line)


def test_corrupt_line_is_skipped_not_fatal(tmp_path):
    path = tmp_path / "runs.jsonl"
    idx = RunIndex(path)
    idx.append(_rec("run_1"))
    with path.open("a") as fh:
        fh.write("{not json\n")
    idx.append(_rec("run_2"))
    assert [r.run_id for r in idx.read_all()] == ["run_1", "run_2"]


def test_declared_secrets_are_redacted_in_the_error_field(tmp_path, monkeypatch):
    """`error` carries a cf-ng message, and a 403 echoes the presented credential."""
    monkeypatch.delenv("CFNG_TOKEN", raising=False)
    path = tmp_path / "runs.jsonl"
    idx = RunIndex(path, secrets=[TOKEN])
    idx.append(_rec("run_1", status="failed", error=f"invalid token {TOKEN} (status 403)"))

    assert TOKEN.encode() not in path.read_bytes()
    assert REDACTED in (idx.read_all()[0].error or "")


def test_the_ledger_redacts_without_being_told(tmp_path, monkeypatch):
    """`RunIndex(path)` is the CLI's call shape; omitting secrets must not mean
    writing in the clear, so the credential this process holds is redacted too."""
    monkeypatch.setenv("CFNG_TOKEN", TOKEN)
    path = tmp_path / "runs.jsonl"
    RunIndex(path).append(_rec("run_1", status="failed", error=f"cf-ng 403: bad token {TOKEN}"))
    assert TOKEN.encode() not in path.read_bytes()


def test_the_credential_is_resolved_at_append_time(tmp_path, monkeypatch):
    """The ledger outlives the moment it was opened; a later credential still counts."""
    monkeypatch.delenv("CFNG_TOKEN", raising=False)
    path = tmp_path / "runs.jsonl"
    idx = RunIndex(path)
    monkeypatch.setenv("CFNG_TOKEN", TOKEN)
    idx.append(_rec("run_1", status="failed", error=f"cf-ng 403: {TOKEN}"))
    assert TOKEN.encode() not in path.read_bytes()


def test_an_explicit_empty_secret_list_disables_redaction(tmp_path, monkeypatch):
    """Explicit beats ambient: a caller that says 'no secrets' is obeyed."""
    monkeypatch.setenv("CFNG_TOKEN", TOKEN)
    path = tmp_path / "runs.jsonl"
    RunIndex(path, secrets=[]).append(_rec("run_1", status="failed", error=TOKEN))
    assert TOKEN.encode() in path.read_bytes()


def test_redaction_leaves_the_rest_of_the_record_intact(tmp_path):
    path = tmp_path / "runs.jsonl"
    idx = RunIndex(path, secrets=[TOKEN])
    idx.append(_rec("run_1", status="failed", error=f"boom {TOKEN}"))
    record = idx.read_all()[0]
    assert record.run_id == "run_1"
    assert record.plan_name == "demo"
    assert record.manifest_hash == "a71f3c9"
    assert record.status == "failed"
    assert record.error == f"boom {REDACTED}"
