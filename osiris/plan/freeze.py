"""Compile a draft plan into a fingerprinted, pinned artifact."""

from collections.abc import Iterator
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any

from pydantic import BaseModel, ConfigDict

from osiris.cfng.client import CfngClient, CfngError
from osiris.cfng.pins import ToolPin, tool_pin
from osiris.determinism.canonical import canonical_yaml
from osiris.determinism.fingerprint import compute_fingerprint
from osiris.fsc.paths import Paths
from osiris.plan.model import ROOT_PATH, NonJsonValue, Plan, reject_non_json_values

# A value that looks like a live credential rather than a reference to one.
_SECRET_SHAPED = re.compile(r"(cfng_[A-Za-z0-9_\-]{8,}|sk-[A-Za-z0-9]{16,}|xox[baprs]-[A-Za-z0-9\-]{10,})")
_ENV_REFERENCE = re.compile(r"^\$\{[A-Z_][A-Z0-9_]*\}$")

# Length of the manifest hash prefix that names the build directory.
BUILD_DIR_HASH_PREFIX = 12


class FreezeError(Exception):
    """The draft plan cannot be frozen."""


class FrozenPlan(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    plan: Plan
    manifest_hash: str
    build_dir: Path


def _walk_strings(value: Any, path: str = "") -> Iterator[tuple[str, str]]:
    """Yield `(location, text)` for every string in `value`, object keys included.

    Keys carry text just as values do: `{"cfng_live...": true}` writes the
    credential into the manifest exactly as surely as `{"token": "cfng_live..."}`
    does, and a walker that recurses only into `.values()` sees neither the key
    nor anything nested under it.
    """
    if isinstance(value, str):
        yield path or ROOT_PATH, value
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                yield f"{path or ROOT_PATH} (object key)", key
            yield from _walk_strings(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_strings(item, f"{path}[{index}]")


def _reject_secrets(plan: Plan) -> None:
    """Fail the compile when anything in the artifact carries a live-looking credential.

    The whole plan is walked, not just `steps`: `params` and `metadata` are
    written into the same `manifest.yaml` and are just as readable there, so a
    guard that looks only at step arguments protects the artifact nowhere it
    matters. Object keys are walked for the same reason.

    An `${ENV_VAR}` reference is the sanctioned way to name a secret without
    embedding it, so it is skipped before the shape check runs.

    The message names the location and never the text. Echoing the offending
    value would print the credential to the terminal and, through the CLI's
    error path, back onto disk -- reproducing the leak this guard exists to stop.
    """
    for location, text in _walk_strings(plan.model_dump(by_alias=True, mode="json")):
        if _ENV_REFERENCE.match(text):
            continue
        if _SECRET_SHAPED.search(text):
            raise FreezeError(
                f"{location}: a literal secret must never enter an artifact. "
                f"Use an environment reference such as ${{CFNG_TOKEN}} instead."
            )


def _capture_tool_pins(plan: Plan, client: CfngClient) -> dict[str, ToolPin]:
    """Pin every cf-ng tool the plan calls, from the canonical REST manifest."""
    pins: dict[str, ToolPin] = {}
    for step in plan.steps:
        if step.uses != "cfng_call":
            continue
        connector = step.with_.get("connector")
        tool = step.with_.get("tool")
        if not connector or not tool:
            raise FreezeError(f"step '{step.id}': cfng_call requires both 'connector' and 'tool'")
        try:
            manifests = client.list_tools(str(connector))
        except CfngError as exc:
            raise FreezeError(f"step '{step.id}': {exc.detail}") from exc
        match = next((m for m in manifests if m.get("name") == tool), None)
        if match is None:
            available = ", ".join(sorted(str(m.get("name")) for m in manifests)) or "none"
            raise FreezeError(
                f"step '{step.id}': connector '{connector}' has no tool '{tool}' (available: {available})"
            )
        pins[f"{connector}__{tool}"] = tool_pin(match)
    return pins


def freeze(draft: dict[str, Any], client: CfngClient, paths: Paths) -> FrozenPlan:
    """Validate a draft against live cf-ng, pin it, fingerprint it, and write build/."""
    # First, before a single cf-ng call and long before anything is hashed: a
    # value JSON cannot represent has no single serialization, so the manifest
    # hash below would name whichever one this process happened to produce.
    # Checked on the raw draft rather than on the validated Plan because
    # pydantic's coercion is what destroys the evidence -- by then a tuple is a
    # list, an int key is a string, and a NaN is a null.
    try:
        reject_non_json_values(draft)
    except NonJsonValue as exc:
        raise FreezeError(str(exc)) from exc

    try:
        plan = Plan(**draft)
    except Exception as exc:  # pydantic ValidationError and friends
        raise FreezeError(str(exc)) from exc

    _reject_secrets(plan)

    plan.pins.tools = _capture_tool_pins(plan, client)
    try:
        plan.pins.cfng.catalog_version = client.catalog_version()
    except CfngError as exc:
        raise FreezeError(f"could not read catalog version: {exc.detail}") from exc

    plan.metadata.setdefault("name", "plan")
    # Recorded for humans reading the manifest; excluded from every hash below.
    plan.metadata["generated_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    canonical = plan.canonical_without_fingerprints()
    plan_fp = compute_fingerprint(canonical)
    pins_fp = compute_fingerprint(canonical_yaml(plan.pins.model_dump(mode="json")))
    plan.fingerprints = {"plan": plan_fp, "pins": pins_fp, "manifest": compute_fingerprint(plan_fp + pins_fp)}

    manifest_hash = plan.fingerprints["manifest"].removeprefix("sha256:")
    build_dir = paths.build_dir(str(plan.metadata["name"]), manifest_hash[:BUILD_DIR_HASH_PREFIX])
    build_dir.mkdir(parents=True, exist_ok=True)

    (build_dir / "manifest.yaml").write_text(
        canonical_yaml(plan.model_dump(by_alias=True, mode="json")), encoding="utf-8"
    )
    (build_dir / "fingerprints.json").write_text(
        json.dumps(plan.fingerprints, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    return FrozenPlan(plan=plan, manifest_hash=manifest_hash, build_dir=build_dir)
