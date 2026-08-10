"""Pin capture and drift classification.

Not all drift is equal. A changed tool contract breaks a plan; a new connector
in the catalog does not. Each class carries its own policy in the manifest.
"""

from enum import Enum

from pydantic import BaseModel

from osiris.determinism.canonical import canonical_json
from osiris.determinism.fingerprint import compute_fingerprint


# `str, Enum` rather than `StrEnum`: the plan pins this shape and downstream
# manifests compare kinds as plain strings. noqa: ruff prefers StrEnum here.
class DriftKind(str, Enum):  # noqa: UP042
    TOOL_CONTRACT = "tool_contract"
    CATALOG = "catalog"
    PROXY_SCOPE = "proxy_scope"


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


def tool_pin(manifest: dict[str, object]) -> ToolPin:
    """Pin a tool from its REST manifest, hashing only inputSchema and outputSchema."""
    input_schema = manifest.get("inputSchema") or {}
    output_schema = manifest.get("outputSchema")
    return ToolPin(
        input=compute_fingerprint(canonical_json(input_schema)),
        output=compute_fingerprint(canonical_json(output_schema)) if output_schema is not None else None,
    )


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
        elif want.output is not None and have.output != want.output:
            drifts.append(
                Drift(
                    kind=DriftKind.TOOL_CONTRACT,
                    subject=name,
                    expected=want.output,
                    actual=have.output or "",
                    diff=f"{name}: outputSchema changed since freeze",
                )
            )
    return drifts
