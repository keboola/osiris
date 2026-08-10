"""Pin capture and drift classification.

Not all drift is equal. A changed tool contract breaks a plan; a new connector
in the catalog does not. Each class carries its own policy in the manifest.
"""

from collections.abc import Iterable
from enum import Enum

from pydantic import BaseModel, ConfigDict

from osiris.determinism.canonical import canonical_json
from osiris.determinism.fingerprint import compute_fingerprint

# How a (connector, tool) pair is flattened into a single pins.tools key.
#
# FOLLOW-UP(pin-key-format): this separator is duplicated as an inline f-string
# in `osiris/plan/freeze.py::_capture_tool_pins` and in
# `osiris/relay/server.py`, and it is ambiguous: connector "x" + tool "y__z"
# and connector "x__y" + tool "z" flatten to the same key, so two distinct
# tools can share one pin. The format cannot be changed here alone -- freeze
# writes the key into the artifact and the runner reads it back, so both sides
# must move in the same commit or every already-frozen plan stops verifying.
# Until that unification lands (length-prefixed or tuple-derived keys), the
# collision is *detected* rather than tolerated: see
# `detect_pin_key_collisions`, which the runner calls before it trusts any pin.
PIN_KEY_SEPARATOR = "__"


# `str, Enum` rather than `StrEnum`: the plan pins this shape and downstream
# manifests compare kinds as plain strings. noqa: ruff prefers StrEnum here.
class DriftKind(str, Enum):  # noqa: UP042
    TOOL_CONTRACT = "tool_contract"
    CATALOG = "catalog"
    PROXY_SCOPE = "proxy_scope"
    # Not a divergence between pins and reality but a defect in the pins
    # themselves: absent, ambiguous, or unverifiable. Reported through the same
    # Drift channel so a single evidence shape covers "we cannot trust this".
    PIN_INTEGRITY = "pin_integrity"


class ToolPin(BaseModel):
    """Hashes of a tool's declared contract. Only prose is deliberately excluded.

    `extra="forbid"`, like every model in `osiris/plan/model.py`. This was the
    one model left on pydantic's default `extra="ignore"`, and the gap was not
    cosmetic: `pins.tools.<key>` is inside the artifact and inside the pins
    fingerprint, but an unknown key added there after freeze was *dropped on
    load*, so it never reached any hash and the artifact still passed all five
    integrity checks. 100KB of padding -- and a live `cfng_` credential -- rode
    into a verified manifest that way, while the identical literal offered at
    freeze time was correctly refused. Nothing may enter a pin that the pin does
    not hash.

    `annotations` are hashed alongside the schemas because they are the MCP
    machine-readable safety hints (`readOnlyHint`, `destructiveHint`,
    `idempotentHint`), not prose: flipping `destructiveHint` false -> true turns
    a read into a delete, and a future retry policy will read them. `description`
    and `title` remain excluded -- rewording a tool is not a contract change.
    """

    model_config = ConfigDict(extra="forbid")

    input: str
    output: str | None = None
    annotations: str | None = None


class Drift(BaseModel):
    kind: DriftKind
    subject: str
    expected: str
    actual: str
    diff: str


class PinKeyCollision(BaseModel):
    """Two or more distinct (connector, tool) pairs that flatten to one pin key."""

    key: str
    pairs: list[tuple[str, str]]

    @property
    def diff(self) -> str:
        rendered = ", ".join(f"({c!r}, {t!r})" for c, t in self.pairs)
        return f"pin key {self.key!r} is ambiguous: it names {len(self.pairs)} distinct tools: {rendered}"


def pin_key(connector: str, tool: str) -> str:
    """The pins.tools key for one tool.

    Kept as a named function so the format has one importable definition even
    while `freeze.py` still inlines it -- see FOLLOW-UP(pin-key-format) above.
    """
    return f"{connector}{PIN_KEY_SEPARATOR}{tool}"


def detect_pin_key_collisions(pairs: Iterable[tuple[str, str]]) -> list[PinKeyCollision]:
    """Report (connector, tool) pairs that would share a pin key.

    `detect_tool_drift` cannot do this itself: by the time it sees `dict[str,
    ToolPin]` the colliding pairs have already been collapsed into one entry
    and the evidence of the collision is gone. So the check has to run against
    the pairs, upstream of the flattening -- on the plan's own steps and on the
    live catalog -- which is what the runner does.
    """
    grouped: dict[str, list[tuple[str, str]]] = {}
    for connector, tool in pairs:
        grouped.setdefault(pin_key(connector, tool), []).append((connector, tool))
    collisions: list[PinKeyCollision] = []
    for key, members in sorted(grouped.items()):
        distinct = sorted(set(members))
        if len(distinct) > 1:
            collisions.append(PinKeyCollision(key=key, pairs=distinct))
    return collisions


# Why an annotations drift is worth an operator's attention, appended to the
# diff so the evidence explains itself without a lookup.
_ANNOTATIONS_NOTE = " (readOnlyHint/destructiveHint/idempotentHint are safety semantics)"


def _optional_fingerprint(value: object) -> str | None:
    """Fingerprint a manifest field that may legitimately be absent.

    `None` means "the manifest declared nothing here" and is preserved as such,
    so `detect_tool_drift` can report the appearance or disappearance of the
    field in the direction it happened rather than as an opaque hash change.
    """
    return compute_fingerprint(canonical_json(value)) if value is not None else None


def tool_pin(manifest: dict[str, object]) -> ToolPin:
    """Pin a tool from its REST manifest: inputSchema, outputSchema, annotations.

    NOTE(pin-value-change): adding `annotations` and tightening the inputSchema
    fingerprint below both change the value of every pin. Artifacts frozen
    before this commit will fail verification and must be re-frozen. That is
    intended at this stage -- nothing is in production, and a pin that never
    covered the tool's safety hints was not worth preserving.

    `manifest.get("inputSchema") or {}` used to collapse four distinct
    declarations into one fingerprint: absent, `{}`, `null` and `false`. In JSON
    Schema `{}` accepts anything and `false` accepts nothing -- opposite
    meanings, and the pin could not tell them apart, so a tool whose input
    contract was inverted after freeze verified clean. `outputSchema` already
    used the strict `is not None` form; both halves now agree that "no schema"
    is a value to be hashed rather than a synonym for the empty object.
    """
    return ToolPin(
        input=compute_fingerprint(canonical_json(manifest.get("inputSchema"))),
        output=_optional_fingerprint(manifest.get("outputSchema")),
        annotations=_optional_fingerprint(manifest.get("annotations")),
    )


def _optional_diff(name: str, field: str, want: str | None, have: str | None, note: str = "") -> str:
    """Describe a change to an optional manifest field in the direction it happened."""
    if want is None:
        return f"{name}: {field} added since freeze (the pin recorded none){note}"
    if have is None:
        return f"{name}: {field} removed since freeze{note}"
    return f"{name}: {field} changed since freeze{note}"


def detect_tool_drift(pinned: dict[str, ToolPin], live: dict[str, ToolPin]) -> list[Drift]:
    """Compare pinned tools against live ones. Extra live tools are not drift."""
    drifts: list[Drift] = []
    for name, want in sorted(pinned.items()):
        have = live.get(name)
        if have is None:
            drifts.append(
                Drift(
                    kind=DriftKind.TOOL_CONTRACT,
                    subject=name,
                    expected=want.input,
                    actual="",
                    diff=f"tool {name} is missing from cf-ng",
                )
            )
            continue
        if have.input != want.input:
            drifts.append(
                Drift(
                    kind=DriftKind.TOOL_CONTRACT,
                    subject=name,
                    expected=want.input,
                    actual=have.input,
                    diff=f"{name}: inputSchema changed since freeze",
                )
            )
        # Symmetric on purpose. The former guard was `want.output is not None`,
        # which made a pin recording `output: null` incapable of ever drifting:
        # *removing* an outputSchema aborted the run while *adding* one -- an
        # equally large change to the contract the plan was built against --
        # went entirely unreported. `None` is a value here, not "unknown", so
        # both directions are compared the same way. Reported alongside an
        # input drift rather than instead of it (`if`, not `elif`): when both
        # halves of a contract moved, the evidence should say so.
        if have.output != want.output:
            drifts.append(
                Drift(
                    kind=DriftKind.TOOL_CONTRACT,
                    subject=name,
                    expected=want.output or "",
                    actual=have.output or "",
                    diff=_optional_diff(name, "outputSchema", want.output, have.output),
                )
            )
        # Same symmetry, and for a sharper reason: under the default fail policy
        # a tool could flip `destructiveHint` false -> true after freeze and the
        # run proceeded, because nothing in the pin covered it. A plan approved
        # against a read-only tool must not silently execute against a
        # destructive one.
        if have.annotations != want.annotations:
            drifts.append(
                Drift(
                    kind=DriftKind.TOOL_CONTRACT,
                    subject=name,
                    expected=want.annotations or "",
                    actual=have.annotations or "",
                    diff=_optional_diff(name, "annotations", want.annotations, have.annotations, _ANNOTATIONS_NOTE),
                )
            )
    return drifts
