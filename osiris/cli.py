"""Osiris command line interface.

Every command follows the same precondition order: configuration, then
credentials, then arguments. Setup problems are reported before argument
problems because a missing `osiris.yaml` or an unset token breaks every
invocation, whatever path was typed, and a run that would fail on a missing
credential should never touch the filesystem first.
"""

from datetime import UTC, datetime
import json
import os
from pathlib import Path

from rich.console import Console
import typer
import yaml

from osiris.cfng.client import CfngClient
from osiris.determinism.fingerprint import FingerprintMismatch, require_fingerprint
from osiris.evidence.run_ids import new_run_id
from osiris.evidence.run_index import RunIndex, RunRecord
from osiris.evidence.session import Session
from osiris.fsc.config import CONFIG_FILENAME, FilesystemConfig
from osiris.fsc.paths import Paths
from osiris.plan.freeze import FreezeError
from osiris.plan.freeze import freeze as freeze_plan
from osiris.plan.model import Plan
from osiris.run.runner import DriftError, Runner
from osiris.run.steps.sql import StepError

BASE_URL_ENV = "CFNG_BASE_URL"
TOKEN_ENV = "CFNG_TOKEN"  # nosec B105 - the name of a variable, never its value
STACK_ENV = "CFNG_STACK"

MANIFEST_FILENAME = "manifest.yaml"
FINGERPRINTS_FILENAME = "fingerprints.json"

# How much of the manifest hash to show a human. Long enough to identify a
# build directory, short enough to read back over a phone call.
HASH_DISPLAY_CHARS = 12

# Exit codes. 1 means Osiris ran and the answer was no; 2 means it never got
# far enough to have an answer.
EXIT_FAILED = 1
EXIT_PRECONDITION = 2

app = typer.Typer(help="Turn an agent's conversation with a third-party system into a replayable artifact.")

# soft_wrap keeps a message on one line regardless of terminal width, so a long
# path in an error is never folded mid-token when the output is piped or logged.
console = Console(soft_wrap=True)

# `osiris serve` speaks JSON-RPC on stdout. Anything human-readable it emits has
# to go to stderr or it corrupts the MCP framing.
err_console = Console(stderr=True, soft_wrap=True)


def _fail(message: str, code: int) -> typer.Exit:
    """Print an error and return the exception to raise. Returning keeps `raise ... from exc` available."""
    console.print(f"[red]{message}[/red]")
    return typer.Exit(code=code)


def _require_env(*names: str) -> dict[str, str]:
    """Return the named variables, or abort naming *every* missing one.

    Reporting only the first missing variable makes the user re-run to discover
    the second, so all of them are collected before anything is printed.
    """
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        console.print(f"[red]Missing required environment variable(s): {', '.join(missing)}.[/red]")
        console.print("[dim]Export them, or put them in the shell that launches Osiris.[/dim]")
        raise typer.Exit(code=EXIT_PRECONDITION)
    return {name: os.environ[name] for name in names}


def _client() -> CfngClient:
    """Build the cf-ng client.

    `CfngClient` is resolved through this module's namespace at call time, which
    is what lets a test swap `osiris.cli.CfngClient` for a transport-mocked
    factory. Importing it inside this function would defeat that.
    """
    env = _require_env(BASE_URL_ENV, TOKEN_ENV)
    return CfngClient(
        base_url=env[BASE_URL_ENV],
        token=env[TOKEN_ENV],
        stack=os.environ.get(STACK_ENV),
    )


def _load_config() -> FilesystemConfig:
    """Load osiris.yaml, turning its exceptions into an actionable message."""
    try:
        return FilesystemConfig.load()
    except (FileNotFoundError, ValueError) as exc:
        raise _fail(str(exc), EXIT_PRECONDITION) from exc


def _load_plan(build_dir: Path) -> Plan:
    """Read a frozen manifest and check it against the fingerprints beside it.

    v0.5.4 computed fingerprints and never verified them. Reading a manifest
    without checking the `fingerprints.json` sitting next to it would repeat
    exactly that, so an edited artifact stops the run here rather than executing
    something nobody froze.
    """
    manifest_path = build_dir / MANIFEST_FILENAME
    if not manifest_path.exists():
        raise _fail(
            f"No {MANIFEST_FILENAME} in {build_dir}. Point 'osiris run' at a directory produced by 'osiris freeze'.",
            EXIT_PRECONDITION,
        )

    try:
        plan = Plan(**(yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}))
    except Exception as exc:  # yaml errors and pydantic ValidationError alike
        raise _fail(f"{manifest_path} is not a readable plan: {exc}", EXIT_PRECONDITION) from exc

    fingerprints_path = build_dir / FINGERPRINTS_FILENAME
    if not fingerprints_path.exists():
        raise _fail(
            f"No {FINGERPRINTS_FILENAME} beside {MANIFEST_FILENAME} in {build_dir} — "
            "the artifact is incomplete and cannot be verified. Freeze it again.",
            EXIT_PRECONDITION,
        )
    recorded = json.loads(fingerprints_path.read_text(encoding="utf-8"))
    try:
        require_fingerprint(plan.canonical_without_fingerprints(), recorded["plan"])
    except (FingerprintMismatch, KeyError) as exc:
        raise _fail(
            f"{manifest_path} does not match its recorded fingerprint — the artifact was edited after freezing.",
            EXIT_FAILED,
        ) from exc
    return plan


def _session_for(directory: Path, secrets: list[str]) -> Session:
    """Open a session at exactly `directory`.

    `Paths` owns the layout and `Session` appends its own id to whatever parent
    it is given, so the resolved directory is split rather than recomputed. That
    keeps one source of truth for where evidence lands.
    """
    return Session(directory.parent, directory.name, secrets=secrets)


@app.command()
def init() -> None:
    """Create osiris.yaml in the current directory with an absolute base_path."""
    root = Path.cwd()
    config_path = root / CONFIG_FILENAME
    if config_path.exists():
        console.print(f"[yellow]{CONFIG_FILENAME} already exists — leaving it untouched.[/yellow]")
        raise typer.Exit(code=0)
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": "0.6",
                "filesystem": {
                    # Absolute on purpose: every later command resolves paths
                    # from here, so the project must not move when the cwd does.
                    "base_path": str(root),
                    "build_dir": "build",
                    "run_logs_dir": "run_logs",
                    "sessions_dir": ".osiris/sessions",
                    "index_dir": ".osiris/index",
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    console.print(f"[green]Wrote {config_path}[/green]")


@app.command()
def serve() -> None:
    """Run the recording MCP relay over stdio."""
    config = _load_config()
    paths = Paths(config)
    # Credentials are checked before the MCP machinery is imported, let alone
    # started: a relay that cannot reach cf-ng has nothing to relay, and stdio
    # has no place to report it once the protocol handshake has begun.
    token = _require_env(BASE_URL_ENV, TOKEN_ENV)[TOKEN_ENV]
    client = _client()

    import asyncio  # noqa: PLC0415

    from osiris.relay.server import Relay, serve_stdio  # noqa: PLC0415

    session_id = new_run_id().replace("run_", "sess_")
    session = _session_for(paths.session_dir(session_id), secrets=[token])
    err_console.print(f"[green]Relaying to {client.base_url}[/green] session={session.session_id}")
    asyncio.run(serve_stdio(Relay(client, session)))


@app.command()
def freeze(draft: Path) -> None:
    """Freeze a draft plan into build/<hash>/."""
    paths = Paths(_load_config())
    try:
        payload = json.loads(Path(draft).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"Could not read draft {draft}: {exc}", EXIT_PRECONDITION) from exc
    if not isinstance(payload, dict):
        raise _fail(f"Draft {draft} must be a JSON object, got {type(payload).__name__}.", EXIT_PRECONDITION)

    with _client() as client:
        try:
            frozen = freeze_plan(payload, client, paths)
        except FreezeError as exc:
            raise _fail(f"Freeze failed: {exc}", EXIT_FAILED) from exc

    console.print(f"[green]Frozen[/green] {frozen.plan.metadata['name']} -> {frozen.build_dir}")
    console.print(f"  manifest hash: {frozen.manifest_hash[:HASH_DISPLAY_CHARS]}")


@app.command()
def run(
    build_dir: Path,
    dry_run: bool = typer.Option(False, "--dry-run", help="Verify pins, execute nothing."),
) -> None:
    """Run a frozen plan."""
    config = _load_config()
    paths = Paths(config)
    token = _require_env(BASE_URL_ENV, TOKEN_ENV)[TOKEN_ENV]
    plan = _load_plan(Path(build_dir))

    name = str(plan.metadata.get("name", "plan"))
    manifest_hash = str(plan.fingerprints.get("manifest", ""))
    # This id names the invocation: it is the ledger's key and the evidence
    # directory's name, so a row in runs.jsonl resolves to a directory on disk.
    # `Runner.execute` mints a second id internally and stamps it on every
    # event; the two are correlatable because both appear in events.jsonl.
    run_id = new_run_id()
    log_dir = paths.run_log_dir(name, run_id)
    session = _session_for(log_dir, secrets=[token])

    with _client() as client:
        runner_ = Runner(client, paths)
        if dry_run:
            # TODO(runner): replace with a public Runner.verify_pins(). Reaching
            # into a private method is the only way to check pins without
            # executing, which is a gap in Runner's surface, not a CLI need.
            try:
                warnings = runner_._check_pins(plan, session)  # noqa: SLF001
            except DriftError as exc:
                console.print("[red]Pin verification failed:[/red]")
                for drift in exc.drifts:
                    console.print(f"  {drift.diff}")
                raise typer.Exit(code=EXIT_FAILED) from exc
            for warning in warnings:
                console.print(f"[yellow]warning:[/yellow] {warning}")
            console.print("[green]Pins verified. Nothing executed (--dry-run).[/green]")
            raise typer.Exit(code=0)

        index = RunIndex(paths.run_index_path())
        started_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            summary = runner_.execute(plan, session.directory / "work", session)
        except (DriftError, StepError) as exc:
            # A failed run is recorded too: a ledger that only holds successes
            # cannot answer "what happened last night".
            index.append(
                RunRecord(
                    run_id=run_id,
                    plan_name=name,
                    manifest_hash=manifest_hash,
                    started_at=started_at,
                    finished_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    status="failed",
                    error=str(exc),
                )
            )
            if isinstance(exc, DriftError):
                console.print("[red]Tool contract drift — aborting before first call.[/red]")
                for drift in exc.drifts:
                    console.print(f"  {drift.diff}")
                console.print(f"[dim]-> osiris replan {manifest_hash[:19]}[/dim]")
            else:
                console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=EXIT_FAILED) from exc

    for warning in summary.warnings:
        console.print(f"[yellow]warning:[/yellow] {warning}")
    index.append(
        RunRecord(
            run_id=run_id,
            plan_name=name,
            manifest_hash=manifest_hash,
            started_at=started_at,
            finished_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            status=summary.status,
        )
    )
    console.print(f"[green]{summary.status}[/green] {run_id}")
    for step_id, rows in summary.steps.items():
        console.print(f"  {step_id}: {rows} rows")
    console.print(f"[dim]evidence: {log_dir}[/dim]")


@app.command()
def doctor() -> None:
    """Report configuration and credential state."""
    ok = True
    try:
        config = FilesystemConfig.load()
        console.print(f"[green]ok[/green] {CONFIG_FILENAME} base_path={config.base_path}")
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]fail[/red] {CONFIG_FILENAME}: {exc}")
        raise typer.Exit(code=EXIT_FAILED) from exc

    for var in (BASE_URL_ENV, TOKEN_ENV):
        if os.environ.get(var):
            # The value is never printed: doctor reports presence, not secrets.
            console.print(f"[green]ok[/green] {var} is set")
        else:
            console.print(f"[red]fail[/red] {var} is not set")
            ok = False

    index_path = Paths(config).run_index_path()
    console.print(f"[green]ok[/green] run index at {index_path}" if index_path.exists() else "[dim]no runs yet[/dim]")

    if not ok:
        raise typer.Exit(code=EXIT_FAILED)


if __name__ == "__main__":  # pragma: no cover
    app()
