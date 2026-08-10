"""The frozen artifact's schema."""

from enum import Enum
import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from osiris.cfng.pins import ToolPin
from osiris.determinism.canonical import canonical_json

STEP_TYPES = frozenset({"cfng_call", "sql", "assert"})

# Fields that change on every freeze and therefore must never reach the hash.
EPHEMERAL_METADATA_KEYS = frozenset({"generated_at"})

# Shown instead of an empty path when the offending value is the plan itself.
ROOT_PATH = "<plan>"

# Why each rejected type is rejected, keyed by type name so that naming a type
# costs no import. The repair differs per type -- a set needs an order chosen by
# the author, a Decimal needs a representation chosen by the author -- so a
# single blanket message would tell nobody what to do next.
_REPAIR_HINTS = {
    "set": "a set has no order, so two processes serialize it differently; use a list in the order you mean",
    "frozenset": "a frozenset has no order, so two processes serialize it differently; use a list in the order you mean",
    "tuple": "a tuple is indistinguishable from a list once written; use a list",
    "bytes": "bytes have no JSON form; encode them as a string yourself",
    "bytearray": "a bytearray has no JSON form; encode it as a string yourself",
    "Decimal": "a Decimal is written as either a float or a string and the choice is not yours here; "
    "use whichever one you mean",
    "datetime": "a datetime is written in whatever format the serializer picks; use an explicit ISO-8601 string",
    "date": "a date is written in whatever format the serializer picks; use an explicit ISO-8601 string",
    "time": "a time is written in whatever format the serializer picks; use an explicit ISO-8601 string",
    "complex": "a complex number has no JSON form",
}
_GENERIC_HINT = (
    "only JSON values may enter a plan: string, integer, finite float, boolean, null, list, and object with string keys"
)


class NonJsonValue(ValueError):
    """A plan carries a value JSON cannot represent, so its hash would not be a fact.

    Every guarantee downstream -- the manifest hash, the build directory name,
    the ledger row -- assumes the plan has exactly one serialization. A value
    that does not is refused at the door rather than coerced into one of its
    several.
    """

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"{path}: {reason}")
        self.path = path
        self.reason = reason


def _non_finite_name(value: float) -> str:
    if math.isnan(value):
        return "NaN"
    return "Infinity" if value > 0 else "-Infinity"


def reject_non_json_values(value: Any, path: str = "") -> None:
    """Raise `NonJsonValue` unless `value` is built only from what JSON represents exactly.

    Run this on the *raw* draft, before pydantic sees it. Pydantic's coercion is
    precisely what this check exists to prevent: `mode="json"` flattens a `set`
    into a list in whatever order this process's `PYTHONHASHSEED` produced, and
    rewrites `NaN`/`Infinity` as `null`. In both cases the artifact and its hash
    end up naming a plan nobody wrote -- silently, and differently per process.

    `path` names the offending value the way the author wrote it, so the message
    reads `params.tags` and `steps[0].with.token` rather than "somewhere".
    """
    if value is None or isinstance(value, str | bool):
        return
    if isinstance(value, int):  # bool is a subclass of int and returned above.
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise NonJsonValue(
                path or ROOT_PATH,
                f"{_non_finite_name(value)} is not a JSON value and is silently rewritten to null; "
                "use a real number, or null if that is what you mean",
            )
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            reject_non_json_values(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise NonJsonValue(
                    path or ROOT_PATH,
                    f"object key {key!r} is a {type(key).__name__}, not a string; "
                    "a non-string key is coerced to one and then collides with the real string key",
                )
            reject_non_json_values(item, f"{path}.{key}" if path else key)
        return

    type_name = type(value).__name__
    raise NonJsonValue(
        path or ROOT_PATH,
        f"{type_name} is not a JSON type; {_REPAIR_HINTS.get(type_name, _GENERIC_HINT)}",
    )


class DriftAction(str, Enum):  # noqa: UP042 - StrEnum changes str()/f-string rendering of members
    FAIL = "fail"
    WARN = "warn"
    IGNORE = "ignore"


# `extra="forbid"` throughout, on every model in this file. Under the previous
# `extra="ignore"` a draft carrying `retries: 5` froze to the same hash as one
# without it: the field was dropped on the way in, the manifest never mentioned
# it, and the author was told nothing. A hash that cannot distinguish two drafts
# the author considers different is not naming the plan's meaning. Verified safe
# for the freeze -> manifest.yaml -> `Plan(**yaml.safe_load(...))` round trip:
# `model_dump(by_alias=True)` emits exactly the declared fields, `with` included.
# `Pins.tools` holds `ToolPin` from `osiris/cfng/pins.py`, which is sealed the
# same way -- it was the last model on `extra="ignore"` and therefore the last
# place an unhashed payload could ride inside a verified artifact.
class Policy(BaseModel):
    """What to do when reality diverges from the pins."""

    model_config = ConfigDict(extra="forbid")

    on_tool_contract_drift: DriftAction = DriftAction.FAIL
    on_catalog_drift: DriftAction = DriftAction.WARN
    on_proxy_scope_drift: DriftAction = DriftAction.WARN


class CfngPins(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proxy: str | None = None
    catalog_version: str | None = None


class Pins(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cfng: CfngPins = Field(default_factory=CfngPins)
    tools: dict[str, ToolPin] = Field(default_factory=dict)


class Step(BaseModel):
    """One executable step. `uses` is an open field by design, not a closed enum."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: str
    uses: str
    with_: dict[str, Any] = Field(default_factory=dict, alias="with")


class Plan(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    # apiVersion/kind are wire field names in the Kubernetes convention, not snake_case by oversight.
    apiVersion: str = "osiris/v1"
    kind: str = "Plan"
    metadata: dict[str, Any] = Field(default_factory=dict)
    pins: Pins = Field(default_factory=Pins)
    policy: Policy = Field(default_factory=Policy)
    params: dict[str, Any] = Field(default_factory=dict)
    steps: list[Step] = Field(default_factory=list)
    fingerprints: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _reject_non_json_input(cls, data: Any) -> Any:
        """Refuse a non-JSON value before pydantic coerces the evidence away.

        `freeze()` runs the same check on its draft so that the failure arrives
        as a `FreezeError` with an unwrapped message. This one covers the other
        door: `Plan(**yaml.safe_load(manifest.yaml))`, where a hand-edited
        `!!set` tag materializes a real set and would otherwise re-hash
        differently in every process that loads it.

        `mode="before"` is deliberate -- by the time field coercion has run, a
        tuple is already a list and an int key is already a string.
        """
        if isinstance(data, dict):
            reject_non_json_values(data)
        return data

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
