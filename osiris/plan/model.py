"""The frozen artifact's schema."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from osiris.cfng.pins import ToolPin
from osiris.determinism.canonical import canonical_json

STEP_TYPES = frozenset({"cfng_call", "sql", "assert"})

# Fields that change on every freeze and therefore must never reach the hash.
EPHEMERAL_METADATA_KEYS = frozenset({"generated_at"})


class DriftAction(str, Enum):  # noqa: UP042 - StrEnum changes str()/f-string rendering of members
    FAIL = "fail"
    WARN = "warn"
    IGNORE = "ignore"


class Policy(BaseModel):
    """What to do when reality diverges from the pins."""

    on_tool_contract_drift: DriftAction = DriftAction.FAIL
    on_catalog_drift: DriftAction = DriftAction.WARN
    on_proxy_scope_drift: DriftAction = DriftAction.WARN


class CfngPins(BaseModel):
    proxy: str | None = None
    catalog_version: str | None = None


class Pins(BaseModel):
    cfng: CfngPins = Field(default_factory=CfngPins)
    tools: dict[str, ToolPin] = Field(default_factory=dict)


class Step(BaseModel):
    """One executable step. `uses` is an open field by design, not a closed enum."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    uses: str
    with_: dict[str, Any] = Field(default_factory=dict, alias="with")


class Plan(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # apiVersion/kind are wire field names in the Kubernetes convention, not snake_case by oversight.
    apiVersion: str = "osiris/v1"
    kind: str = "Plan"
    metadata: dict[str, Any] = Field(default_factory=dict)
    pins: Pins = Field(default_factory=Pins)
    policy: Policy = Field(default_factory=Policy)
    params: dict[str, Any] = Field(default_factory=dict)
    steps: list[Step] = Field(default_factory=list)
    fingerprints: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_steps(self) -> "Plan":
        if not self.steps:
            raise ValueError("a plan must have at least one step")
        seen: set[str] = set()
        for step in self.steps:
            if step.id in seen:
                raise ValueError(f"duplicate step id: {step.id}")
            seen.add(step.id)
            if step.uses not in STEP_TYPES:
                raise ValueError(f"unknown step type: {step.uses} (known: {sorted(STEP_TYPES)})")
        return self

    def canonical_without_fingerprints(self) -> str:
        """Canonical form used for hashing: fingerprints and generated_at excluded.

        `mode="json"` collapses every value to a JSON primitive -- enum members
        become their string values, nested models become plain dicts -- so the
        result depends only on the plan's content, never on Python object
        identity or field declaration order. `by_alias=True` emits the wire name
        `with` rather than the Python attribute `with_`, which is what the
        manifest on disk carries, so the hash covers exactly what is written.
        """
        data = self.model_dump(by_alias=True, mode="json")
        data.pop("fingerprints", None)
        metadata = {k: v for k, v in (data.get("metadata") or {}).items() if k not in EPHEMERAL_METADATA_KEYS}
        data["metadata"] = metadata
        return canonical_json(data)
