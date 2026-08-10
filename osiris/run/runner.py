"""Sequential plan executor.

Pins are verified before the first tool call. v0.5.4 computed fingerprints and
never checked them; here a mismatch aborts by default.

Three things can stop a run before any tool is called, all of them evidenced:
a drift the policy rates fatal (DriftError), pins that cannot be verified
because cf-ng did not answer (PinProbeError), and pins that are not worth
verifying because the artifact does not carry them (PinIntegrityError). The
last two exist because "nothing was checked" used to be indistinguishable from
"everything checked out".
"""

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from osiris.cfng.client import CfngClient, CfngError
from osiris.cfng.pins import (
    Drift,
    DriftKind,
    ToolPin,
    detect_pin_key_collisions,
    detect_tool_drift,
    pin_key,
    tool_pin,
)
from osiris.evidence.run_ids import new_run_id
from osiris.evidence.session import Session
from osiris.fsc.paths import Paths
from osiris.plan.model import DriftAction, Plan
from osiris.run.context import RunContext
from osiris.run.steps.assert_step import run_assert
from osiris.run.steps.cfng_call import run_cfng_call
from osiris.run.steps.sql import StepError, run_sql


class DriftError(Exception):
    """Reality diverged from the pins and policy says stop."""

    def __init__(self, drifts: list[Drift]) -> None:
        super().__init__("\n".join(d.diff for d in drifts))
        self.drifts = drifts


# Both new errors subclass DriftError deliberately. They are distinct
# conditions and a caller that cares can branch on the type, but every one of
# them means the same operational thing -- "the pins were not verified, nothing
# was called" -- and `osiris/cli.py` already catches DriftError, records a
# failed row in the ledger, and renders `.drifts`. Subclassing keeps that
# behaviour for free; a sibling exception type would have gone straight to an
# unhandled traceback with nothing in runs.jsonl, which is the defect being
# fixed here (report defect 10), not a new surface to introduce.
class PinProbeError(DriftError):
    """cf-ng could not be asked whether the pins still hold.

    A connector 404 or an unreachable cf-ng fails closed -- no tool is called --
    but previously the CfngError escaped `Runner.execute` uncaught, so the run
    left no evidence at all. "Unknown" is not "unchanged": this aborts.
    """

    def __init__(self, subject: str, detail: str, status: int | None = None) -> None:
        super().__init__(
            [
                Drift(
                    kind=DriftKind.PIN_INTEGRITY,
                    subject=subject,
                    expected="a pin probe response from cf-ng",
                    actual=f"cf-ng error{f' {status}' if status is not None else ''}",
                    diff=f"could not verify pins for {subject}: {detail}",
                )
            ]
        )
        self.status = status
        self.detail = detail


class PinIntegrityError(DriftError):
    """The pins themselves are unusable, so verification is meaningless.

    Empty or partial `pins.tools` on a plan that calls tools, or a pin key that
    names more than one tool. Such an artifact was never frozen properly and an
    unpinned plan must not be indistinguishable from a verified one.
    """


def _raise_on_collisions(pairs: list[tuple[str, str]], origin: str) -> None:
    """Abort if any two distinct tools share a pin key. See FOLLOW-UP(pin-key-format)."""
    collisions = detect_pin_key_collisions(pairs)
    if not collisions:
        return
    raise PinIntegrityError(
        [
            Drift(
                kind=DriftKind.PIN_INTEGRITY,
                subject=collision.key,
                expected="one tool per pin key",
                actual=f"{len(collision.pairs)} tools",
                diff=f"{origin}: {collision.diff}",
            )
            for collision in collisions
        ]
    )


class _PinVerdict:
    """The three fates a detected drift can meet, kept apart on purpose.

    `warned` and `ignored` were previously indistinguishable from "no drift at
    all" by the time the summary event was written, which is how a run with a
    broken contract came to emit the same positive assertion as a clean one.
    They are collected separately so the evidence can name what happened.
    """

    def __init__(self) -> None:
        self.fatal: list[Drift] = []
        self.warned: list[Drift] = []
        self.ignored: list[Drift] = []

    def sort(self, drifts: list[Drift], action: DriftAction) -> None:
        """File each drift under the fate its policy assigns it."""
        if not drifts:
            return
        if action is DriftAction.FAIL:
            self.fatal.extend(drifts)
        elif action is DriftAction.WARN:
            self.warned.extend(drifts)
        else:
            self.ignored.extend(drifts)

    @property
    def suppressed(self) -> list[Drift]:
        """Drift that was found and run anyway -- `warn` and `ignore` alike."""
        return self.warned + self.ignored

    @property
    def warnings(self) -> list[str]:
        return [drift.diff for drift in self.warned]


class RunSummary(BaseModel):
    run_id: str
    status: str
    steps: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class Runner:
    """Executes a frozen plan against cf-ng."""

    def __init__(self, client: CfngClient, paths: Paths) -> None:
        self._client = client
        self._paths = paths

    @staticmethod
    def _log_drifts(session: Session, event: str, drifts: list[Drift]) -> None:
        for drift in drifts:
            session.log_event(event, subject=drift.subject, detail=drift.diff)

    @staticmethod
    def _planned_tool_pairs(plan: Plan) -> list[tuple[str, str]]:
        """Every (connector, tool) the plan intends to call, in step order."""
        pairs: list[tuple[str, str]] = []
        for step in plan.steps:
            if step.uses != "cfng_call":
                continue
            connector = step.with_.get("connector")
            tool = step.with_.get("tool")
            if not connector or not tool:
                # freeze rejects this, so the artifact was hand-built. There is
                # nothing to pin and therefore nothing to verify: fail closed
                # here rather than let earlier steps run and side-effect before
                # the step's own StepError fires.
                raise PinIntegrityError(
                    [
                        Drift(
                            kind=DriftKind.PIN_INTEGRITY,
                            subject=step.id,
                            expected="connector and tool",
                            actual=f"connector={connector!r} tool={tool!r}",
                            diff=f"step '{step.id}': cfng_call without both 'connector' and 'tool' cannot be pinned",
                        )
                    ]
                )
            pairs.append((str(connector), str(tool)))
        return pairs

    @staticmethod
    def _require_pins(plan: Plan, planned: list[tuple[str, str]]) -> None:
        """A plan that calls tools must carry a pin for every one of them.

        Without this an artifact with `pins.tools = {}` is indistinguishable
        from a verified one: `detect_tool_drift` iterates the pinned dict, so
        zero pins means zero comparisons, zero drift, and a clean run. Nothing
        was checked, yet the run reads as checked. Refuse instead.
        """
        if not planned:
            return
        if not plan.pins.tools:
            raise PinIntegrityError(
                [
                    Drift(
                        kind=DriftKind.PIN_INTEGRITY,
                        subject="pins.tools",
                        expected=f"{len(planned)} pinned tool(s)",
                        actual="none",
                        diff=(
                            f"plan calls {len(planned)} cf-ng tool(s) but pins.tools is empty: "
                            "this artifact was never frozen against cf-ng"
                        ),
                    )
                ]
            )
        missing = [pair for pair in planned if pin_key(*pair) not in plan.pins.tools]
        if missing:
            raise PinIntegrityError(
                [
                    Drift(
                        kind=DriftKind.PIN_INTEGRITY,
                        subject=pin_key(connector, tool),
                        expected="a pin captured at freeze",
                        actual="none",
                        diff=f"tool '{tool}' on connector '{connector}' is called by the plan but not pinned",
                    )
                    for connector, tool in missing
                ]
            )

    def _live_tool_pins(self, plan: Plan) -> dict[str, ToolPin]:
        """Pin every tool cf-ng currently advertises for the plan's connectors.

        CfngError is translated rather than propagated: a 404 on a connector or
        an unreachable cf-ng must abort with evidence, not with a traceback.
        """
        live: dict[str, ToolPin] = {}
        live_pairs: list[tuple[str, str]] = []
        connectors = {connector for connector, _ in self._planned_tool_pairs(plan)}
        for connector in sorted(connectors):
            try:
                manifests = self._client.list_tools(connector)
            except CfngError as exc:
                raise PinProbeError(f"connector '{connector}'", exc.detail, exc.status) from exc
            except Exception as exc:  # transport failure: cf-ng unreachable
                raise PinProbeError(f"connector '{connector}'", str(exc)) from exc
            for manifest in manifests:
                name = str(manifest.get("name"))
                live_pairs.append((connector, name))
                live[pin_key(connector, name)] = tool_pin(manifest)
        # The catalog can be ambiguous even when the plan is not: two live tools
        # collapsing onto one key means the pin compared below is not
        # necessarily the pin for the tool that will be called.
        _raise_on_collisions(live_pairs, "cf-ng catalog")
        return live

    def _catalog_drift(self, plan: Plan, session: Session) -> Drift | None:
        """Compare the pinned catalog version against the live one, if pinned."""
        pinned = plan.pins.cfng.catalog_version
        if not pinned:
            return None
        try:
            actual = self._client.catalog_version()
        except CfngError as exc:
            # The catalog probe is a cheap heuristic on top of the tool
            # contracts, not the contract check itself, so a failure here does
            # not abort. It must not be silent either: the previous bare
            # `actual = None` made an unavailable catalog look exactly like an
            # unchanged one.
            session.log_event("catalog_probe_failed", status=exc.status, detail=exc.detail)
            return None
        if not actual or actual == pinned:
            return None
        return Drift(
            kind=DriftKind.CATALOG,
            subject="catalog",
            expected=pinned,
            actual=actual,
            diff=f"catalog_version changed: {pinned} -> {actual}",
        )

    def _check_pins(self, plan: Plan, session: Session) -> list[str]:
        """Verify pins before the first tool call. Returns warnings; raises on fail policy."""
        verdict = _PinVerdict()

        # Everything that can make the verdict untrustworthy happens here, and
        # every one of those aborts leaves an event behind: an abort the ledger
        # never heard about is the failure mode this replaces.
        try:
            planned = self._planned_tool_pairs(plan)
            _raise_on_collisions(planned, "plan")
            self._require_pins(plan, planned)
            live = self._live_tool_pins(plan)
        except PinIntegrityError as exc:
            self._log_drifts(session, "pins_unusable", exc.drifts)
            raise
        except PinProbeError as exc:
            self._log_drifts(session, "pin_probe_failed", exc.drifts)
            raise

        verdict.sort(detect_tool_drift(plan.pins.tools, live), plan.policy.on_tool_contract_drift)
        catalog_drift = self._catalog_drift(plan, session)
        if catalog_drift is not None:
            verdict.sort([catalog_drift], plan.policy.on_catalog_drift)

        warnings = verdict.warnings
        for message in warnings:
            session.log_event("drift_warning", detail=message)
        if verdict.fatal:
            for drift in verdict.fatal:
                session.log_event("drift_fatal", detail=drift.diff)
            raise DriftError(verdict.fatal)

        # Under `ignore` the diff text reached disk nowhere at all: the only
        # record of what moved lived in memory and was discarded. Record it even
        # though the policy says not to stop.
        self._log_drifts(session, "drift_ignored", verdict.ignored)

        suppressed = verdict.suppressed
        # The *event name* is the assertion, and it must not be obtainable by
        # editing a policy field. `policy.on_tool_contract_drift: warn|ignore`
        # switches the abort off; under `ignore` this event used to be
        # byte-identical to a clean run's -- same name, `warnings: 0` -- so the
        # record of a failed verification read exactly like the record of a
        # passed one. A positive integrity assertion must never appear for a run
        # whose integrity check failed. When it failed and the policy suppressed
        # the abort, the record now says so under its own name, and both names
        # carry the drift count and the policy that made the call so neither can
        # be read as the other.
        session.log_event(
            "pins_drift_suppressed" if suppressed else "pins_verified",
            tools_checked=len(plan.pins.tools),
            tool_calls_pinned=len(planned),
            catalog_version=plan.pins.cfng.catalog_version,
            drifts_found=len(suppressed),
            drift_subjects=sorted({d.subject for d in suppressed}),
            warnings=len(warnings),
            on_tool_contract_drift=plan.policy.on_tool_contract_drift.value,
            on_catalog_drift=plan.policy.on_catalog_drift.value,
        )
        return warnings

    def execute(self, plan: Plan, run_dir: Path, session: Session) -> RunSummary:
        run_id = new_run_id()
        session.log_event("run_start", run_id=run_id, plan=plan.metadata.get("name"))

        # Before the first call, not after: a moved contract must cost nothing.
        warnings = self._check_pins(plan, session)

        steps: dict[str, int] = {}
        with RunContext(run_dir, session) as ctx:
            for step in plan.steps:
                session.log_event("step_start", run_id=run_id, step=step.id, uses=step.uses)
                started = datetime.now(UTC)
                try:
                    if step.uses == "cfng_call":
                        result = run_cfng_call(step, ctx, self._client, plan.params)
                    elif step.uses == "sql":
                        result = run_sql(step, ctx, plan.params)
                    elif step.uses == "assert":
                        result = run_assert(step, ctx, plan.params)
                    else:  # pragma: no cover - the model rejects unknown types
                        raise StepError(step.id, f"unknown step type: {step.uses}")
                except StepError as exc:
                    session.log_event("step_error", run_id=run_id, step=step.id, detail=str(exc))
                    session.log_event("run_finish", run_id=run_id, status="failed")
                    raise
                duration_ms = (datetime.now(UTC) - started).total_seconds() * 1000
                steps[step.id] = result["rows"]
                session.log_event(
                    "step_finish", run_id=run_id, step=step.id, rows=result["rows"], duration_ms=round(duration_ms, 1)
                )

        session.log_event("run_finish", run_id=run_id, status="success")
        return RunSummary(run_id=run_id, status="success", steps=steps, warnings=warnings)
