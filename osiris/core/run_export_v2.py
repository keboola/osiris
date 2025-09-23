#!/usr/bin/env python3
# Copyright (c) 2025 Osiris Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""PR2 - Evidence Layer implementation for AIOP."""

import json
import re
from datetime import datetime
from pathlib import Path


def build_evidence_layer(
    events: list[dict], metrics: list[dict], artifacts: list[Path], max_bytes: int = 300_000
) -> dict:
    """Compile evidence with stable IDs.

    Args:
        events: List of event dictionaries from events.jsonl
        metrics: List of metric dictionaries from metrics.jsonl
        artifacts: List of artifact paths
        max_bytes: Maximum size in bytes for evidence layer

    Returns:
        Evidence layer dictionary with timeline, metrics, errors, and artifacts
    """
    # Build timeline from events
    timeline = build_timeline(events, density="medium")

    # Aggregate metrics
    aggregated_metrics = aggregate_metrics(metrics, topk=100)

    # Extract errors from events
    errors = _extract_errors(events)

    # Build artifact list
    artifact_list = _build_artifact_list(artifacts)

    evidence = {
        "timeline": timeline,
        "metrics": aggregated_metrics,
        "errors": errors,
        "artifacts": artifact_list,
    }

    # Apply truncation if needed
    evidence, truncated = apply_truncation(evidence, max_bytes)

    return evidence


def generate_evidence_id(type: str, step_id: str, name: str, ts_ms: int) -> str:
    """Generate canonical evidence ID: ev.<type>.<name>.<step_or_run>.<ts_ms>

    Args:
        type: Event type (will be sanitized)
        step_id: Step identifier (will be sanitized) or None/empty for run-level
        name: Event name (will be sanitized)
        ts_ms: Timestamp in milliseconds since epoch

    Returns:
        Canonical evidence ID string
    """
    # Sanitize components - only [a-z0-9_]
    type = _sanitize_id_component(type)
    name = _sanitize_id_component(name)

    # Use 'run' when step_id is missing or empty
    step_or_run = _sanitize_id_component(step_id) if step_id else "run"

    return f"ev.{type}.{name}.{step_or_run}.{ts_ms}"


def build_timeline(events: list[dict], density: str = "medium") -> list[dict]:
    """Build chronologically sorted timeline.

    Args:
        events: List of event dictionaries
        density: Timeline density level (low/medium/high)

    Returns:
        Chronologically sorted list of timeline events with evidence IDs
    """
    timeline = []

    for event in events:
        # Extract key fields - support both 'type' and 'event' fields
        event_type = event.get("type", "") or event.get("event", "")
        if not event_type:  # Skip events without type
            continue

        step_id = event.get("step_id", "")
        timestamp = event.get("ts", "")

        # Use event type directly if already canonical, otherwise map it
        if event_type in [
            "START",
            "STEP_START",
            "METRICS",
            "STEP_COMPLETE",
            "COMPLETE",
            "ERROR",
            "DEBUG",
            "TRACE",
        ]:
            canonical_type = event_type
        else:
            canonical_type = _get_canonical_event_type(event_type)

        # Generate evidence ID
        ts_ms = _timestamp_to_ms(timestamp)
        evidence_id = generate_evidence_id("event", step_id, event_type.lower(), ts_ms)

        timeline.append(
            {
                "@id": evidence_id,
                "ts": timestamp,
                "type": canonical_type,
                "step_id": step_id if step_id else None,
                "data": _sanitize_event_data(event),
            }
        )

    # Sort chronologically
    timeline.sort(key=lambda x: x["ts"])

    # Apply density filter
    if density == "low":
        # Keep only major events
        major_types = ["START", "COMPLETE", "STEP_START", "STEP_COMPLETE", "ERROR"]
        timeline = [e for e in timeline if e["type"] in major_types]
    elif density == "medium":
        # low + METRICS
        allowed_types = ["START", "COMPLETE", "STEP_START", "STEP_COMPLETE", "ERROR", "METRICS"]
        timeline = [e for e in timeline if e["type"] in allowed_types]
    # high density keeps all events

    return timeline


def aggregate_metrics(metrics: list[dict], topk: int = 100) -> dict:
    """Aggregate and prioritize metrics.

    Args:
        metrics: List of metric dictionaries
        topk: Maximum number of step metrics to return

    Returns:
        Dictionary with total_rows, total_duration_ms, and steps
    """
    # Track totals and per-step metrics
    total_rows = 0
    total_duration_ms = 0
    step_metrics = {}

    for metric in metrics:
        step_id = metric.get("step_id", "")

        # Handle direct field access (not nested under "metric")
        rows_read = metric.get("rows_read", 0) if "rows_read" in metric else 0
        rows_written = metric.get("rows_written", 0) if "rows_written" in metric else 0
        rows_out = metric.get("rows_out", 0) if "rows_out" in metric else 0
        duration_ms = metric.get("duration_ms", 0) if "duration_ms" in metric else 0

        # Also handle nested under "metric" field for compatibility
        name = metric.get("metric", "")
        value = metric.get("value", 0)

        if name == "rows_read":
            rows_read = value
        elif name == "rows_written":
            rows_written = value
        elif name == "rows_out":
            rows_out = value
        elif name == "duration_ms":
            duration_ms = value

        # Aggregate totals
        if isinstance(rows_read, (int, float)) and rows_read > 0:
            total_rows += rows_read
        if isinstance(rows_written, (int, float)) and rows_written > 0:
            total_rows += rows_written
        if isinstance(rows_out, (int, float)) and rows_out > 0:
            total_rows += rows_out
        if isinstance(duration_ms, (int, float)) and duration_ms > 0:
            total_duration_ms += duration_ms

        # Aggregate per-step metrics
        if step_id:
            if step_id not in step_metrics:
                step_metrics[step_id] = {
                    "rows_read": None,
                    "rows_written": None,
                    "rows_out": None,
                    "duration_ms": None,
                }

            # Update step metrics - sum if already present
            if rows_read > 0:
                if step_metrics[step_id]["rows_read"] is None:
                    step_metrics[step_id]["rows_read"] = rows_read
                else:
                    step_metrics[step_id]["rows_read"] += rows_read
            if rows_written > 0:
                if step_metrics[step_id]["rows_written"] is None:
                    step_metrics[step_id]["rows_written"] = rows_written
                else:
                    step_metrics[step_id]["rows_written"] += rows_written
            if rows_out > 0:
                if step_metrics[step_id]["rows_out"] is None:
                    step_metrics[step_id]["rows_out"] = rows_out
                else:
                    step_metrics[step_id]["rows_out"] += rows_out
            if duration_ms > 0:
                if step_metrics[step_id]["duration_ms"] is None:
                    step_metrics[step_id]["duration_ms"] = duration_ms
                else:
                    step_metrics[step_id]["duration_ms"] += duration_ms

    # Sort steps by duration desc, then rows desc, then step_id asc
    sorted_steps = sorted(
        step_metrics.items(),
        key=lambda x: (
            -(x[1]["duration_ms"] or 0),
            -((x[1]["rows_read"] or 0) + (x[1]["rows_written"] or 0) + (x[1]["rows_out"] or 0)),
            x[0],
        ),
    )

    # Apply topk limit to steps
    limited_steps = dict(sorted_steps[:topk])

    return {
        "total_rows": total_rows if total_rows > 0 else 0,
        "total_duration_ms": total_duration_ms if total_duration_ms > 0 else 0,
        "steps": limited_steps,
    }


def canonicalize_json(data: dict) -> str:
    """Produce deterministic JSON with sorted keys.

    Args:
        data: Dictionary to serialize

    Returns:
        Deterministic JSON string with sorted keys
    """
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False, separators=(",", ": "))


def apply_truncation(data: dict, max_bytes: int) -> tuple[dict, bool]:
    """Truncate with object-level markers if exceeds size limit.

    Args:
        data: Data dictionary to truncate
        max_bytes: Maximum size in bytes

    Returns:
        Tuple of (truncated_data, was_truncated)
    """
    json_str = json.dumps(data)
    current_size = len(json_str.encode("utf-8"))

    if current_size <= max_bytes:
        return data, False

    was_truncated = False

    # Truncate timeline first (usually largest)
    if "timeline" in data and len(data["timeline"]) > 200:
        # Keep first 100 and last 100
        original_count = len(data["timeline"])
        data["timeline"] = data["timeline"][:100] + data["timeline"][-100:]

        # Add truncation markers to timeline
        data["timeline"] = {
            "items": data["timeline"],
            "truncated": True,
            "dropped_events": original_count - 200,
            "annex_ref": None,
        }
        was_truncated = True

    # Check size again
    json_str = json.dumps(data)
    current_size = len(json_str.encode("utf-8"))

    # Truncate metrics if still too large
    if (
        current_size > max_bytes
        and "metrics" in data
        and "steps" in data["metrics"]
        and len(data["metrics"]["steps"]) > 20
    ):
        original_step_count = len(data["metrics"]["steps"])
        # Keep only first 20 steps (already sorted by priority)
        step_items = list(data["metrics"]["steps"].items())[:20]
        data["metrics"]["steps"] = dict(step_items)

        # Add truncation markers to metrics
        data["metrics"]["truncated"] = True
        data["metrics"]["dropped_series"] = original_step_count - 20
        was_truncated = True

    # Add optional summary flag
    if was_truncated:
        data["truncated"] = True

    return data, was_truncated


# Internal helper functions (not part of PR2 public API)


def _sanitize_id_component(text: str) -> str:
    """Sanitize text for use in evidence IDs.

    Converts to lowercase and replaces non-alphanumeric with underscore.
    Only allows [a-z0-9_]. Collapses multiple underscores.
    """
    # Convert to lowercase and replace anything not a-z0-9 with underscore
    sanitized = re.sub(r"[^a-z0-9]+", "_", text.lower())
    # Remove leading/trailing underscores
    sanitized = sanitized.strip("_")
    return sanitized if sanitized else "unknown"


def _timestamp_to_ms(timestamp: str) -> int:
    """Convert ISO timestamp to milliseconds since epoch."""
    try:
        # Handle both with and without timezone
        if "Z" in timestamp:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        elif "+" in timestamp or timestamp.count("-") > 2:
            dt = datetime.fromisoformat(timestamp)
        else:
            # Assume UTC if no timezone
            dt = datetime.fromisoformat(timestamp + "+00:00")
        return int(dt.timestamp() * 1000)
    except (ValueError, AttributeError, TypeError):
        return 0


def _sanitize_event_data(event: dict) -> dict:
    """Remove sensitive and redundant fields from event data."""
    sensitive_fields = ["password", "token", "key", "secret", "credential"]
    redundant_fields = ["ts", "session", "event"]

    sanitized = {}
    for key, value in event.items():
        # Skip sensitive fields
        if any(s in key.lower() for s in sensitive_fields):
            continue
        # Skip redundant fields
        if key in redundant_fields:
            continue
        sanitized[key] = value

    return sanitized


def _extract_errors(events: list[dict]) -> list[dict]:
    """Extract error events from event list."""
    errors = []

    for event in events:
        if "error" in event.get("event", "").lower() or event.get("level") == "ERROR":
            ts_ms = _timestamp_to_ms(event.get("ts", ""))
            step_id = event.get("step_id", "")
            evidence_id = generate_evidence_id("event", step_id, "error", ts_ms)

            errors.append(
                {
                    "@id": evidence_id,
                    "step_id": step_id if step_id else None,
                    "message": event.get("error", event.get("msg", "Unknown error")),
                    "severity": "error",
                    "ts": event.get("ts", ""),
                }
            )

    return errors


def _build_artifact_list(artifacts: list[Path]) -> list[dict]:
    """Build list of artifact metadata."""
    import hashlib

    artifact_list = []

    for artifact_path in artifacts:
        if artifact_path.exists() and artifact_path.is_file():
            # Calculate content hash
            sha256_hash = hashlib.sha256()
            with open(artifact_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)

            artifact_list.append(
                {
                    "@id": f"artifact.{artifact_path.stem}.{sha256_hash.hexdigest()[:8]}",
                    "path": str(artifact_path),
                    "size_bytes": artifact_path.stat().st_size,
                    "content_hash": f"sha256:{sha256_hash.hexdigest()}",
                }
            )

    return artifact_list


def _get_canonical_event_type(event_type: str) -> str:
    """Map event types to canonical types."""
    event_lower = event_type.lower()

    if "start" in event_lower:
        if "step" in event_lower:
            return "STEP_START"
        return "START"
    elif "complete" in event_lower or "end" in event_lower:
        if "step" in event_lower:
            return "STEP_COMPLETE"
        return "COMPLETE"
    elif "error" in event_lower:
        return "ERROR"
    elif "metric" in event_lower:
        return "METRICS"
    elif "debug" in event_lower:
        return "DEBUG"
    elif "trace" in event_lower:
        return "TRACE"
    else:
        # Default mapping for known types
        return event_type.upper()


# ============================================================================
# PR3 - Semantic/Ontology Layer
# ============================================================================


def build_semantic_layer(
    manifest: dict, oml_spec: dict, component_registry: dict, schema_mode: str = "summary"
) -> dict:
    """Build JSON-LD semantic representation (deterministic).

    Args:
        manifest: Compiled manifest dictionary
        oml_spec: OML specification dictionary
        component_registry: Component registry with schemas and capabilities
        schema_mode: "summary" or "detailed" for component schema inclusion

    Returns:
        Semantic layer dictionary with @type, components, DAG, etc.
    """
    # Extract DAG structure
    dag = extract_dag_structure(manifest)

    # Build component ontology
    components = build_component_ontology(component_registry, mode=schema_mode)

    # Create semantic layer dictionary
    semantic = {}

    # Add pipeline URI if we have manifest hash
    if "manifest_hash" in manifest:
        manifest_hash = manifest["manifest_hash"]
        semantic["@id"] = f"osiris://pipeline/@{manifest_hash}"

    semantic["@type"] = "SemanticLayer"
    semantic["components"] = components
    semantic["dag"] = dag
    semantic["oml_version"] = oml_spec.get("oml_version", "0.1.0")

    # Return with sorted keys for determinism
    return dict(sorted(semantic.items()))


def extract_dag_structure(manifest: dict) -> dict:
    """Return {'nodes': [...], 'edges': [{'from': 'stepA','to':'stepB','relation': 'produces'|...}], 'counts': {...}}

    Args:
        manifest: Compiled manifest with steps

    Returns:
        DAG structure with nodes, edges, and counts
    """
    steps = manifest.get("steps", [])

    # Extract nodes (step IDs)
    nodes = []
    step_outputs = {}  # Map output names to step IDs

    for step in steps:
        step_id = step.get("id", "")
        if step_id:
            nodes.append(step_id)
            # Track outputs from this step
            for output in step.get("outputs", []):
                step_outputs[output] = step_id

    # Build edges based on input/output dependencies AND depends_on
    edges = []
    for step in steps:
        step_id = step.get("id", "")
        if not step_id:
            continue

        # Check inputs to determine dependencies (produces relation)
        for input_name in step.get("inputs", []):
            if input_name in step_outputs:
                from_step = step_outputs[input_name]
                edges.append({"from": from_step, "to": step_id, "relation": "produces"})

        # Check explicit depends_on field (depends_on relation)
        for dep_step in step.get("depends_on", []):
            edges.append({"from": dep_step, "to": step_id, "relation": "depends_on"})

    # Sort for determinism
    edges.sort(key=lambda e: (e["from"], e["to"], e["relation"]))

    return {"nodes": nodes, "edges": edges, "counts": {"nodes": len(nodes), "edges": len(edges)}}


def build_component_ontology(components: dict, mode: str = "summary") -> dict:
    """Map components to ontology (types, capabilities, optional schema snippets based on mode).

    Args:
        components: Dictionary of component definitions
        mode: "summary" or "detailed"

    Returns:
        Component ontology dictionary
    """
    ontology = {}

    # Secret field names to exclude
    secret_fields = {"password", "token", "api_key", "secret", "credential", "key"}

    for comp_name, comp_def in components.items():
        comp_ont = {"@id": f"osiris://component/{comp_name}"}

        # Add version if present
        if "version" in comp_def:
            comp_ont["version"] = comp_def["version"]

        # Add capabilities
        if "capabilities" in comp_def:
            comp_ont["capabilities"] = comp_def["capabilities"]

        # In detailed mode, include schema snippet (without secrets)
        if mode == "detailed" and "schema" in comp_def:
            schema = comp_def["schema"].copy()

            # Filter out secret properties
            if "properties" in schema:
                filtered_props = {}
                for prop_name, prop_def in schema.get("properties", {}).items():
                    # Skip if name matches secret patterns or marked as secret
                    if (
                        prop_name.lower() not in secret_fields
                        and not prop_def.get("secret", False)
                        and not any(secret in prop_name.lower() for secret in secret_fields)
                    ):
                        filtered_props[prop_name] = prop_def

                if filtered_props:
                    schema["properties"] = filtered_props
                else:
                    schema.pop("properties", None)

            comp_ont["schema"] = schema

        ontology[comp_name] = comp_ont

    # Sort for determinism
    return dict(sorted(ontology.items()))


def generate_graph_hints(manifest: dict, run_data: dict | None = None) -> dict:  # noqa: ARG001
    """Prepare GraphRAG-friendly triples: {'triples': [{'s':'osiris://...','p':'osiris:depends_on','o':'osiris://...'}, ...], 'counts': {...}}

    Args:
        manifest: Compiled manifest
        run_data: Optional run data with session_id, status, etc.

    Returns:
        Graph hints dictionary with triples and counts
    """
    triples = []

    # Generate pipeline URI (using correct format)
    manifest_hash = manifest.get("manifest_hash", "unknown")
    pipeline_uri = f"osiris://pipeline/@{manifest_hash}"

    steps = manifest.get("steps", [])
    step_outputs = {}  # Map output names to step IDs (not URIs)

    # First pass: track outputs
    for step in steps:
        step_id = step.get("id", "")
        if step_id:
            # Track what this step produces
            for output in step.get("outputs", []):
                step_outputs[output] = step_id

    # Second pass: create triples for dependencies
    for step in steps:
        step_id = step.get("id", "")
        if not step_id:
            continue

        step_uri = f"{pipeline_uri}/step/{step_id}"

        # Create triples for inputs (produces and consumes relationships)
        for input_name in step.get("inputs", []):
            if input_name in step_outputs:
                producer_id = step_outputs[input_name]
                producer_uri = f"{pipeline_uri}/step/{producer_id}"

                # Producer produces data that this step consumes
                triples.append({"s": producer_uri, "p": "osiris:produces", "o": step_uri})

                # This step consumes from producer
                triples.append({"s": step_uri, "p": "osiris:consumes", "o": producer_uri})

        # Create triples for explicit depends_on relationships
        for dep_step_id in step.get("depends_on", []):
            dep_step_uri = f"{pipeline_uri}/step/{dep_step_id}"

            # This step depends on dep_step
            triples.append({"s": step_uri, "p": "osiris:depends_on", "o": dep_step_uri})

        # Create produces relationships for outputs
        for _ in step.get("outputs", []):
            # Step produces data (using step URI as both subject and object for now)
            # This could be refined to use data URIs in the future
            triples.append({"s": step_uri, "p": "osiris:produces", "o": step_uri})

    # Sort for determinism
    triples.sort(key=lambda t: (t["s"], t["p"], t["o"]))

    return {"triples": triples, "counts": {"triple_count": len(triples)}}
