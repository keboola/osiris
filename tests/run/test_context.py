"""The run context is the single seam every step depends on."""

from pathlib import Path
import subprocess
import sys

from osiris.evidence.session import Session
from osiris.run.context import RunContext


def _ctx(tmp_path: Path) -> RunContext:
    return RunContext(tmp_path / "run", Session(tmp_path / "ev", "sess_1"))


def test_context_exposes_get_db_connection(tmp_path):
    """The exact method v0.5.4's contexts lacked while every driver called it."""
    with _ctx(tmp_path) as ctx:
        assert callable(ctx.get_db_connection)
        assert ctx.get_db_connection().execute("SELECT 1").fetchone() == (1,)


def test_connection_is_shared_across_calls(tmp_path):
    with _ctx(tmp_path) as ctx:
        ctx.get_db_connection().execute("CREATE TABLE t AS SELECT 1 AS a")
        assert ctx.get_db_connection().execute("SELECT a FROM t").fetchone() == (1,)


def test_data_persists_to_a_file_not_memory(tmp_path):
    """Volumes must not be bounded by RAM."""
    with _ctx(tmp_path) as ctx:
        ctx.get_db_connection().execute("CREATE TABLE t AS SELECT 1 AS a")
        db_path = ctx.db_path
    assert db_path.exists()
    assert db_path.stat().st_size > 0


def test_output_dir_is_created(tmp_path):
    with _ctx(tmp_path) as ctx:
        assert ctx.output_dir.is_dir()


def test_log_metric_reaches_the_session(tmp_path):
    session = Session(tmp_path / "ev", "sess_1")
    with RunContext(tmp_path / "run", session) as ctx:
        ctx.log_metric("rows_read", 7, step="fetch")
    metrics = session.read_metrics()
    assert metrics[0]["name"] == "rows_read"
    assert metrics[0]["value"] == 7
    assert metrics[0]["step"] == "fetch"


def test_close_is_idempotent(tmp_path):
    ctx = _ctx(tmp_path)
    ctx.get_db_connection()
    ctx.close()
    ctx.close()


def test_tables_survive_reopening_the_same_run_dir(tmp_path):
    """The runner reopens the data bus between phases; tables must still be there."""
    session = Session(tmp_path / "ev", "sess_1")
    with RunContext(tmp_path / "run", session) as first:
        first.get_db_connection().execute("CREATE TABLE t AS SELECT 42 AS a")
        db_path = first.db_path

    assert db_path.is_file()

    with RunContext(tmp_path / "run", session) as second:
        assert second.db_path == db_path
        assert second.get_db_connection().execute("SELECT a FROM t").fetchone() == (42,)


def test_two_contexts_in_one_process_share_the_database(tmp_path):
    """DuckDB's instance cache makes a second in-process context a view of the same database.

    No lock error, and no isolation: writes through one connection are immediately
    visible through the other. In-process concurrency is therefore safe but shared —
    the runner still builds exactly one context per run so ownership stays obvious.
    """
    session = Session(tmp_path / "ev", "sess_1")
    first = RunContext(tmp_path / "run", session)
    second = RunContext(tmp_path / "run", session)
    try:
        first.get_db_connection().execute("CREATE TABLE t AS SELECT 1 AS a")
        assert second.get_db_connection().execute("SELECT a FROM t").fetchone() == (1,)
        # Closing one leaves the other fully usable.
        first.close()
        assert second.get_db_connection().execute("SELECT a FROM t").fetchone() == (1,)
    finally:
        first.close()
        second.close()


def test_a_second_process_is_locked_out_and_the_lock_is_released_on_close(tmp_path):
    """Across processes DuckDB takes an exclusive file lock — and close() gives it back.

    This is the constraint on any out-of-process worker: it may not hold the run's
    data bus open while the parent does. There is no lock leak after close().
    """
    probe = (
        "import duckdb,sys\n"
        "try:\n"
        "    c = duckdb.connect(sys.argv[1])\n"
        "    print('OPENED', c.execute('SELECT a FROM t').fetchone()[0])\n"
        "except duckdb.IOException as exc:\n"
        "    print('LOCKED' if 'lock' in str(exc).lower() else 'OTHER')\n"
    )

    def probe_in_another_process(path: Path) -> str:
        return subprocess.run(
            [sys.executable, "-c", probe, str(path)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    session = Session(tmp_path / "ev", "sess_1")
    ctx = RunContext(tmp_path / "run", session)
    ctx.get_db_connection().execute("CREATE TABLE t AS SELECT 1 AS a")

    assert probe_in_another_process(ctx.db_path) == "LOCKED"

    ctx.close()

    assert probe_in_another_process(ctx.db_path) == "OPENED 1"


def test_context_exposes_the_session_secrets(tmp_path):
    """Steps write to disk without going through the session and need the same list."""
    session = Session(tmp_path / "ev", "sess_1", secrets=["cfng_abc123"])  # pragma: allowlist secret
    with RunContext(tmp_path / "run", session) as ctx:
        assert ctx.secrets == ["cfng_abc123"]  # pragma: allowlist secret


def test_context_secrets_cannot_be_mutated_through_the_property(tmp_path):
    """A step holding the list must not be able to empty the session's copy."""
    session = Session(tmp_path / "ev", "sess_1", secrets=["cfng_abc123"])  # pragma: allowlist secret
    with RunContext(tmp_path / "run", session) as ctx:
        ctx.secrets.clear()
        assert ctx.secrets == ["cfng_abc123"]  # pragma: allowlist secret


def test_context_secrets_is_empty_when_the_session_has_none(tmp_path):
    with RunContext(tmp_path / "run", Session(tmp_path / "ev", "sess_1")) as ctx:
        assert ctx.secrets == []
