"""Pin capture and drift classification.

Not all drift is equal. A changed tool contract breaks a plan; a new connector
in the catalog does not. Each class carries its own policy in the manifest.
"""

from collections.abc import Iterable
from enum import Enum

from pydantic import BaseModel

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
    """Hashes of a tool's declared contract. Prose fields are deliberately excluded."""

    input: str
    output: str | None = None


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


def tool_pin(manifest: dict[str, object]) -> ToolPin:
    """Pin a tool from its REST manifest, hashing only inputSchema and outputSchema."""
    input_schema = manifest.get("inputSchema") or {}
    output_schema = manifest.get("outputSchema")
    return ToolPin(
        input=compute_fingerprint(canonical_json(input_schema)),
        output=compute_fingerprint(canonical_json(output_schema)) if output_schema is not None else None,
    )


def _output_diff(name: str, want: str | None, have: str | None) -> str:
    """Describe an outputSchema change in the direction it actually happened."""
    if want is None:
        return f"{name}: outputSchema added since freeze (the pin recorded none)"
    if have is None:
        return f"{name}: outputSchema removed since freeze"
    return f"{name}: outputSchema changed since freeze"


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
                    diff=_output_diff(name, want.output, have.output),
                )
            )
    return drifts
