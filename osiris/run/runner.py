"""Sequential plan executor.

Pins are verified before the first tool call. v0.5.4 computed fingerprints and
never checked them; here a mismatch aborts by default.
"""

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from osiris.cfng.client import CfngClient, CfngError
from osiris.cfng.pins import Drift, DriftKind, ToolPin, detect_tool_drift, tool_pin
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

    def _live_tool_pins(self, plan: Plan) -> dict[str, ToolPin]:
        live: dict[str, ToolPin] = {}
        connectors = {
            str(s.with_["connector"]) for s in plan.steps if s.uses == "cfng_call" and s.with_.get("connector")
        }
        for connector in sorted(connectors):
            for manifest in self._client.list_tools(connector):
                live[f"{connector}__{manifest.get('name')}"] = tool_pin(manifest)
        return live

    def _check_pins(self, plan: Plan, session: Session) -> list[str]:
        """Verify pins before the first tool call. Returns warnings; raises on fail policy."""
        warnings: list[str] = []
        fatal: list[Drift] = []

        drifts = detect_tool_drift(plan.pins.tools, self._live_tool_pins(plan))
        if drifts:
            action = plan.policy.on_tool_contract_drift
            if action is DriftAction.FAIL:
                fatal.extend(drifts)
            elif action is DriftAction.WARN:
                warnings.extend(d.diff for d in drifts)

        pinned_catalog = plan.pins.cfng.catalog_version
        if pinned_catalog:
            try:
                actual = self._client.catalog_version()
            except CfngError:
                actual = None
            if actual and actual != pinned_catalog:
                drift = Drift(
                    kind=DriftKind.CATALOG,
                    subject="catalog",
                    expected=pinned_catalog,
                    actual=actual,
                    diff=f"catalog_version changed: {pinned_catalog} -> {actual}",
                )
                action = plan.policy.on_catalog_drift
                if action is DriftAction.FAIL:
                    fatal.append(drift)
                elif action is DriftAction.WARN:
                    warnings.append(drift.diff)

        for message in warnings:
            session.log_event("drift_warning", detail=message)
        if fatal:
            for drift in fatal:
                session.log_event("drift_fatal", detail=drift.diff)
            raise DriftError(fatal)
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
