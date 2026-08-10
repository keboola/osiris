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
from typing import Any, NamedTuple

import httpx
from rich.console import Console
import typer
import yaml

from osiris.cfng.client import CfngClient, CfngError
from osiris.determinism.canonical import canonical_yaml
from osiris.determinism.fingerprint import FingerprintMismatch, require_fingerprint
from osiris.evidence.run_ids import new_run_id
from osiris.evidence.run_index import RunIndex, RunRecord
from osiris.evidence.session import Session, redact
from osiris.fsc.config import CONFIG_FILENAME, FilesystemConfig
from osiris.fsc.paths import Paths, slugify
from osiris.plan.freeze import BUILD_DIR_HASH_PREFIX, FreezeError
from osiris.plan.freeze import freeze as freeze_plan
from osiris.plan.model import Plan
from osiris.run.runner import DriftError, Runner
from osiris.run.steps.sql import StepError

BASE_URL_ENV = "CFNG_BASE_URL"
TOKEN_ENV = "CFNG_TOKEN"  # nosec B105 - the name of a variable, never its value
STACK_ENV = "CFNG_STACK"

MANIFEST_FILENAME = "manifest.yaml"
FINGERPRINTS_FILENAME = "fingerprints.json"

# Every fingerprint a complete artifact carries, and every fingerprint that is
# checked before a run. Writing a value and never reading it is the v0.5.4 habit
# this rebuild exists to end, so there is no such thing here as a fingerprint
# that is merely recorded.
REQUIRED_FINGERPRINTS = ("plan", "pins", "manifest")

# What to do about an artifact that failed verification. Repeated on every
# integrity error because "it does not verify" without a next step reads as a
# tool malfunction rather than a refusal.
TAMPER_HINT = (
    "Re-freeze the draft, or restore the directory from wherever the artifact was published. "
    "Osiris will not execute a build it cannot account for."
)

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


def _safe(text: str) -> str:
    """Redact the live token out of anything bound for the console.

    stdout is outside the evidence system: `osiris run > nightly.log` persists
    whatever was printed, so a cf-ng error that echoes the credential it was
    presented with would leak past a redaction seam that guards only
    events.jsonl. Every printed exception goes through here.
    """
    return str(redact(text, [os.environ.get(TOKEN_ENV, "")]))


def _fail(message: str, code: int) -> typer.Exit:
    """Print an error and return the exception to raise. Returning keeps `raise ... from exc` available."""
    console.print(f"[red]{_safe(message)}[/red]")
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


class VerifiedArtifact(NamedTuple):
    """A build directory that passed every integrity check, plus the values that passed it.

    The fingerprints travel with the plan because everything downstream — the
    ledger row, the evidence event — must quote the value that was *verified*,
    not the one the artifact declares about itself.
    """

    plan: Plan
    build_dir: Path
    plan_fp: str
    pins_fp: str
    manifest_fp: str


def _read_fingerprints(build_dir: Path) -> dict[str, str]:
    """Read fingerprints.json, refusing anything that is not three strings.

    A malformed file used to escape as a raw `TypeError`/`JSONDecodeError`
    traceback. It is treated as an integrity failure rather than a crash: the
    difference between "this file is corrupt" and "someone truncated it" is not
    one the CLI can make, and both mean the same thing — do not run.
    """
    fingerprints_path = build_dir / FINGERPRINTS_FILENAME
    if not fingerprints_path.exists():
        raise _fail(
            f"No {FINGERPRINTS_FILENAME} beside {MANIFEST_FILENAME} in {build_dir} — "
            "the artifact is incomplete and cannot be verified. Freeze it again.",
            EXIT_PRECONDITION,
        )
    try:
        recorded: Any = json.loads(fingerprints_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _fail(f"{fingerprints_path} is not readable JSON: {exc}. {TAMPER_HINT}", EXIT_FAILED) from exc

    if not isinstance(recorded, dict):
        raise _fail(
            f"{fingerprints_path} must map a name to a fingerprint, got {type(recorded).__name__}. {TAMPER_HINT}",
            EXIT_FAILED,
        )
    missing = [key for key in REQUIRED_FINGERPRINTS if not isinstance(recorded.get(key), str)]
    if missing:
        raise _fail(
            f"{fingerprints_path} has no usable {', '.join(missing)} fingerprint. "
            f"An artifact is verified against all of {', '.join(REQUIRED_FINGERPRINTS)}. {TAMPER_HINT}",
            EXIT_FAILED,
        )
    return {key: str(recorded[key]) for key in REQUIRED_FINGERPRINTS}


def _load_plan(build_dir: Path) -> VerifiedArtifact:
    """Read a frozen manifest and verify it, completely, before anything executes.

    v0.5.4 computed fingerprints and never verified them. Checking only the
    plan's fingerprint would be the same failure one layer up: an attacker who
    has read this file recomputes that one value with the repo's own public API
    and the tampered artifact runs. So all three recorded fingerprints are
    checked, *and* the relation freeze established between them —
    `manifest == sha256(plan + pins)` — which no single recomputation can
    satisfy on its own, *and* the directory name, which freeze derives from the
    manifest hash and an attacker must therefore also rename.

    None of this is keyed, so it is not a signature: someone who rewrites every
    file and renames the directory produces a coherent artifact. What it does
    buy is that no *partial* edit survives, and that the run ledger can quote a
    hash that was checked rather than one that was merely typed.
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

    recorded = _read_fingerprints(build_dir)

    # 1. The plan's meaning, canonicalized. Tolerant of reformatting by
    #    construction, which is the point: only a semantic edit moves it.
    try:
        require_fingerprint(plan.canonical_without_fingerprints(), recorded["plan"])
    except FingerprintMismatch as exc:
        raise _fail(
            f"{manifest_path} does not match its recorded plan fingerprint — "
            f"the artifact was edited after freezing. {TAMPER_HINT}",
            EXIT_FAILED,
        ) from exc

    # 2. The pins, hashed exactly as freeze hashed them. Pins live inside the
    #    plan, so check 1 already covers a naive edit; this catches the edit
    #    that came with a recomputed plan fingerprint.
    try:
        require_fingerprint(canonical_yaml(plan.pins.model_dump(mode="json")), recorded["pins"])
    except FingerprintMismatch as exc:
        raise _fail(
            f"{manifest_path} does not match its recorded pins fingerprint — "
            f"the pinned tool contracts were edited after freezing. {TAMPER_HINT}",
            EXIT_FAILED,
        ) from exc

    # 3. The relation between them, which freeze established and nothing read.
    #    Recomputing one fingerprint breaks it; recomputing all three
    #    consistently breaks the directory name in check 5 instead.
    try:
        require_fingerprint(recorded["plan"] + recorded["pins"], recorded["manifest"])
    except FingerprintMismatch as exc:
        raise _fail(
            f"{build_dir / FINGERPRINTS_FILENAME} is internally inconsistent: its manifest fingerprint is not "
            f"the hash of its plan and pins fingerprints. One of the three was recomputed by hand. {TAMPER_HINT}",
            EXIT_FAILED,
        ) from exc

    # 4. The manifest's own `fingerprints:` block. It is excluded from every
    #    hash — which is exactly why it must never be trusted as a source and
    #    is compared here as a subject.
    declared = {key: plan.fingerprints[key] for key in REQUIRED_FINGERPRINTS if key in plan.fingerprints}
    if any(recorded[key] != value for key, value in declared.items()):
        raise _fail(
            f"The fingerprints declared inside {manifest_path} disagree with {FINGERPRINTS_FILENAME}. "
            f"That block is excluded from every hash, so it is evidence of a hand edit, never a source of truth. "
            f"{TAMPER_HINT}",
            EXIT_FAILED,
        )

    # 5. The directory name, which freeze derives from the verified hash.
    expected_name = slugify(recorded["manifest"].removeprefix("sha256:")[:BUILD_DIR_HASH_PREFIX])
    actual_name = build_dir.resolve().name
    if actual_name != expected_name:
        raise _fail(
            f"{build_dir} is named '{actual_name}' but its verified manifest fingerprint names '{expected_name}'. "
            f"A build directory is identified by its hash, so this one is a copy, a rename, or a rewrite. "
            f"{TAMPER_HINT}",
            EXIT_FAILED,
        )

    return VerifiedArtifact(
        plan=plan,
        build_dir=build_dir,
        plan_fp=recorded["plan"],
        pins_fp=recorded["pins"],
        manifest_fp=recorded["manifest"],
    )


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


def _abort_hint(exc: Exception) -> str:
    """A next action for an abort that is not a plan-level failure.

    These used to be raw tracebacks: a connector 404 or an unreachable cf-ng
    escaped the two exception types the CLI knew about, so the user got a stack
    and the ledger got nothing.
    """
    # `status` rather than a type check: cf-ng errors reach here either raw or
    # wrapped by the pin probe, and both carry the code that explains them.
    status = getattr(exc, "status", None)
    if isinstance(status, int):
        if status in (401, 403):
            return (
                f"cf-ng rejected the credential ({status}). Check {TOKEN_ENV}, "
                f"and {STACK_ENV} if it is a Keboola master token."
            )
        if status == 404:
            return (
                "cf-ng has no such connector or tool. Re-freeze the plan against the catalog "
                "you are running it against."
            )
        return f"cf-ng answered {status}. Retry if that is transient, otherwise re-freeze against this catalog."
    if hasattr(exc, "status") or isinstance(exc, CfngError | httpx.HTTPError):
        return (
            f"cf-ng at {os.environ.get(BASE_URL_ENV, '?')} could not be reached. Check {BASE_URL_ENV} and the network."
        )
    if isinstance(exc, DriftError):
        return "Re-freeze the plan: an artifact whose pins are absent or ambiguous cannot be verified."
    return "The run ledger records this failure. Fix the cause and re-run the same build directory."


def _unverifiable(exc: DriftError) -> bool:
    """True when the pins were not *checked*, as opposed to a contract having moved.

    A probe that failed and a schema that changed are both DriftError, and the
    advice differs. The distinction is read off the drift kind rather than the
    exception class: `DriftKind` is a str enum, so this compares as a plain
    string and the CLI does not have to import the taxonomy to render a hint.
    """
    return bool(exc.drifts) and all(drift.kind == "pin_integrity" for drift in exc.drifts)


def _render_run_failure(exc: Exception, manifest_hash: str) -> None:
    """Print an abort in terms the user can act on, never echoing a secret."""
    if isinstance(exc, DriftError):
        unverifiable = _unverifiable(exc)
        console.print(
            "[red]Pins could not be verified — nothing was called.[/red]"
            if unverifiable
            else "[red]Tool contract drift — aborting before first call.[/red]"
        )
        for drift in exc.drifts:
            console.print(f"  {_safe(drift.diff)}")
        console.print(
            f"[dim]{_safe(_abort_hint(exc))}[/dim]"
            if unverifiable
            else f"[dim]-> osiris replan {manifest_hash[:19]}[/dim]"
        )
    elif isinstance(exc, StepError):
        console.print(f"[red]{_safe(str(exc))}[/red]")
    else:
        console.print(f"[red]Run failed: {_safe(str(exc))}[/red]")
        console.print(f"[dim]{_safe(_abort_hint(exc))}[/dim]")


@app.command()
def run(
    build_dir: Path,
    dry_run: bool = typer.Option(False, "--dry-run", help="Verify pins, execute nothing."),
) -> None:
    """Run a frozen plan."""
    config = _load_config()
    paths = Paths(config)
    token = _require_env(BASE_URL_ENV, TOKEN_ENV)[TOKEN_ENV]
    artifact = _load_plan(Path(build_dir))
    plan = artifact.plan

    name = str(plan.metadata.get("name", "plan"))
    # From the fingerprint that was *verified*, never from the manifest's own
    # `fingerprints:` block: that block is excluded from every hash, so a ledger
    # quoting it certifies whatever an editor typed there rather than what ran.
    manifest_hash = artifact.manifest_fp
    # This id names the invocation: it is the ledger's key and the evidence
    # directory's name, so a row in runs.jsonl resolves to a directory on disk.
    # `Runner.execute` mints a second id internally and stamps it on every
    # event; the two are correlatable because both appear in events.jsonl.
    run_id = new_run_id()
    log_dir = paths.run_log_dir(name, run_id)
    session = _session_for(log_dir, secrets=[token])
    # Evidence that verification happened, not merely that a run did. Without
    # it, a run whose integrity was checked is indistinguishable in the record
    # from one where the check was skipped or removed.
    session.log_event(
        "artifact_verified",
        run_id=run_id,
        build_dir=str(artifact.build_dir),
        verified=list(REQUIRED_FINGERPRINTS),
        plan_fingerprint=artifact.plan_fp,
        pins_fingerprint=artifact.pins_fp,
        manifest_fingerprint=artifact.manifest_fp,
    )

    with _client() as client:
        runner_ = Runner(client, paths)
        if dry_run:
            # Prefer a public Runner.verify_pins() when Runner grows one.
            # Reaching into the private method is the only way to check pins
            # without executing, which is a gap in Runner's surface, not a CLI
            # need.
            verify_pins = getattr(runner_, "verify_pins", None) or runner_._check_pins  # noqa: SLF001
            try:
                warnings = verify_pins(plan, session)
            except DriftError as exc:
                console.print("[red]Pin verification failed:[/red]")
                for drift in exc.drifts:
                    console.print(f"  {_safe(drift.diff)}")
                if _unverifiable(exc):
                    console.print(f"[dim]{_safe(_abort_hint(exc))}[/dim]")
                raise typer.Exit(code=EXIT_FAILED) from exc
            except Exception as exc:
                console.print(f"[red]Pin verification could not complete: {_safe(str(exc))}[/red]")
                console.print(f"[dim]{_safe(_abort_hint(exc))}[/dim]")
                raise typer.Exit(code=EXIT_FAILED) from exc
            for warning in warnings:
                console.print(f"[yellow]warning:[/yellow] {_safe(warning)}")
            console.print("[green]Pins verified. Nothing executed (--dry-run).[/green]")
            raise typer.Exit(code=0)

        index = RunIndex(paths.run_index_path())
        started_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            summary = runner_.execute(plan, session.directory / "work", session)
        except Exception as exc:
            # Deliberately every exception, not the two the runner is known to
            # raise: a connector 404, an unreachable cf-ng or a pin probe that
            # grows a new error type must still leave a ledger row. "A failed
            # run is recorded too" is not a claim that can hold for a
            # hand-maintained list of exception types.
            index.append(
                RunRecord(
                    run_id=run_id,
                    plan_name=name,
                    manifest_hash=manifest_hash,
                    started_at=started_at,
                    finished_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    status="failed",
                    # cf-ng error details can quote the credential they were
                    # presented with, and the ledger is not session-scoped.
                    error=_safe(str(exc)),
                )
            )
            _render_run_failure(exc, manifest_hash)
            raise typer.Exit(code=EXIT_FAILED) from exc

    for warning in summary.warnings:
        console.print(f"[yellow]warning:[/yellow] {_safe(warning)}")
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
        console.print(f"[red]fail[/red] {CONFIG_FILENAME}: {_safe(str(exc))}")
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
