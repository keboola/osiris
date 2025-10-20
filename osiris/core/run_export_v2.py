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

import builtins
from collections.abc import Generator
import contextlib
import copy
from datetime import datetime
from functools import lru_cache
import gzip
import io
import json
from pathlib import Path
import re


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

    # Aggregate metrics (pass events to look for cleanup_complete)
    aggregated_metrics = aggregate_metrics(metrics, topk=100, events=events)

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


def aggregate_metrics(metrics: list[dict], topk: int = 100, events: list[dict] = None) -> dict:
    """Aggregate and prioritize metrics.

    Args:
        metrics: List of metric dictionaries
        topk: Maximum number of step metrics to return
        events: Optional list of event dictionaries (for calculating durations)

    Returns:
        Dictionary with total_rows, total_duration_ms, steps, and rows_source.
        If events provided, also includes durations.wall_ms and durations.active_ms
    """
    # Track totals and per-step metrics
    total_rows = 0
    total_duration_ms = 0
    active_duration_ms = 0
    step_metrics = {}
    rows_source = "calculated"  # Track how we determined total_rows

    # Calculate total wall time from RUN_START/RUN_COMPLETE events
    run_start_time = None
    run_complete_time = None
    step_timings = {}  # Track STEP_START/COMPLETE pairs
    cleanup_total_rows = None  # Initialize here

    # Process events for timing information
    if events:
        for event in events:
            event_type = event.get("event_type") or event.get("event", "")
            timestamp = event.get("timestamp", "")

            # Track RUN_START/RUN_COMPLETE for wall time
            if event_type == "RUN_START":
                if timestamp:
                    with contextlib.suppress(builtins.BaseException):
                        run_start_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            elif event_type == "RUN_COMPLETE":
                if timestamp:
                    with contextlib.suppress(builtins.BaseException):
                        run_complete_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

            # Track STEP_START/STEP_COMPLETE for active duration
            elif event_type == "STEP_START":
                step_id = event.get("step_id", "")
                if step_id and timestamp:
                    with contextlib.suppress(builtins.BaseException):
                        step_timings[step_id] = {"start": datetime.fromisoformat(timestamp.replace("Z", "+00:00"))}
            elif event_type == "STEP_COMPLETE":
                step_id = event.get("step_id", "")
                if step_id and timestamp and step_id in step_timings:
                    try:
                        end_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                        if "start" in step_timings[step_id]:
                            duration = (end_time - step_timings[step_id]["start"]).total_seconds() * 1000
                            step_timings[step_id]["duration_ms"] = int(duration)
                    except Exception:
                        pass

            # Check for cleanup_complete event (highest authority for rows)
            if event.get("event") == "cleanup_complete" and "total_rows" in event:
                cleanup_total_rows = event["total_rows"]
                rows_source = "cleanup_complete"

    # Calculate wall time if we have both start and complete
    if run_start_time and run_complete_time:
        total_duration_ms = int((run_complete_time - run_start_time).total_seconds() * 1000)

    # Track the last write operation's rows for total_rows
    last_writer_rows = 0
    export_step_rows = 0

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

        # Track export step and last writer for total_rows calculation
        # Use the export step if present, otherwise the last writer
        if step_id and "export" in step_id.lower() and rows_written > 0:
            export_step_rows = rows_written
        elif rows_written > 0:
            last_writer_rows = rows_written
        if isinstance(duration_ms, int | float) and duration_ms > 0:
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

    # Merge duration data from events if not in metrics
    for step_id, timing_data in step_timings.items():
        if "duration_ms" in timing_data:
            if step_id not in step_metrics:
                step_metrics[step_id] = {
                    "rows_read": None,
                    "rows_written": None,
                    "rows_out": None,
                    "duration_ms": timing_data["duration_ms"],
                }
            elif step_metrics[step_id].get("duration_ms") is None:
                # Use event-based duration if no metric duration
                step_metrics[step_id]["duration_ms"] = timing_data["duration_ms"]

    # Calculate active duration as sum of all step durations
    active_duration_ms = 0
    for step_data in step_metrics.values():
        if step_data.get("duration_ms"):
            active_duration_ms += step_data["duration_ms"]

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

    # Determine total_rows using deterministic rule:
    # 1. Use cleanup_complete.total_rows if available (highest authority)
    # 2. Otherwise use export step if present
    # 3. Otherwise use last writer's rows
    # 4. Otherwise sum all terminal writers (if no single last writer)
    if cleanup_total_rows is not None:
        total_rows = cleanup_total_rows
        rows_source = "cleanup_complete"
    elif export_step_rows > 0:
        total_rows = export_step_rows
        rows_source = "export_step"
    elif last_writer_rows > 0:
        total_rows = last_writer_rows
        rows_source = "last_writer"
    else:
        # Sum rows_written from all steps (fallback)
        total_rows = sum(
            step.get("rows_written", 0)
            for step in step_metrics.values()
            if isinstance(step.get("rows_written"), int | float)
        )
        rows_source = "sum_writers"

    return {
        "total_rows": total_rows if total_rows > 0 else 0,
        "total_duration_ms": total_duration_ms if total_duration_ms > 0 else 0,
        "active_duration_ms": active_duration_ms if active_duration_ms > 0 else 0,
        "steps": limited_steps,
        "rows_source": rows_source,  # Track how we determined total_rows
    }


def canonicalize_json(data: dict) -> str:
    """Produce deterministic JSON with sorted keys.

    Args:
        data: Dictionary to serialize

    Returns:
        Deterministic JSON string with sorted keys
    """
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False, separators=(",", ": "))


def stream_json_chunks(data: dict, chunk_size: int = 8192) -> Generator[str, None, None]:
    """Stream JSON output in chunks to reduce memory usage.

    Args:
        data: Dictionary to serialize
        chunk_size: Size of each chunk in bytes

    Yields:
        JSON string chunks
    """
    # Use StringIO to simulate streaming
    buffer = io.StringIO()
    json.dump(data, buffer, indent=2, sort_keys=True, ensure_ascii=False, separators=(",", ": "))
    buffer.seek(0)

    while True:
        chunk = buffer.read(chunk_size)
        if not chunk:
            break
        yield chunk


def apply_truncation(data: dict, max_bytes: int) -> tuple[dict, bool]:
    """If canonicalized JSON exceeds max_bytes, drop to object-level markers.

    Evidence timeline: { "items": [...], "truncated": true, "dropped_events": N }
    Evidence metrics:  { ... , "truncated": true, "aggregates_only": true, "dropped_series": N }
    Evidence artifacts: { "files": [...], "truncated": true, "content_omitted": true }

    Keep strategy: first_K + last_K for events, aggregates for metrics, refs for artifacts.
    Deterministic outcome; never break JSON-LD shape.

    Args:
        data: Data dictionary to truncate
        max_bytes: Maximum size in bytes

    Returns:
        Tuple of (truncated_data, was_truncated)
    """
    # Check initial size
    json_str = canonicalize_json(data)
    current_size = len(json_str.encode("utf-8"))

    if current_size <= max_bytes:
        return data, False

    # Make a copy to modify
    result = copy.deepcopy(data)
    was_truncated = False

    # Determine how aggressive truncation should be
    ratio = current_size / max_bytes
    if ratio > 10:
        keep_count = 5
    elif ratio > 5:
        keep_count = 10
    elif ratio > 2:
        keep_count = 20
    elif ratio > 1.5:
        keep_count = 50
    else:
        keep_count = 100

    # Handle evidence.timeline specifically
    if "evidence" in result and "timeline" in result["evidence"]:
        timeline = result["evidence"]["timeline"]

        # If timeline is a list
        if isinstance(timeline, list) and len(timeline) > keep_count * 2:
            original_count = len(timeline)
            # Keep first K and last K events
            kept_events = timeline[:keep_count] + timeline[-keep_count:]

            # Convert to object form with marker
            result["evidence"]["timeline"] = {
                "items": kept_events,
                "truncated": True,
                "dropped_events": original_count - len(kept_events),
            }
            was_truncated = True

    # Check size after timeline truncation
    json_str = canonicalize_json(result)
    current_size = len(json_str.encode("utf-8"))

    if current_size <= max_bytes:
        return result, was_truncated

    # Handle evidence.metrics
    if "evidence" in result and "metrics" in result["evidence"]:
        metrics = result["evidence"]["metrics"]

        # Drop detailed step metrics if present
        if "steps" in metrics and len(metrics["steps"]) > 10:
            original_step_count = len(metrics["steps"])
            # Keep only top 10 steps (they're already sorted by priority)
            step_items = list(metrics["steps"].items())[:10]
            metrics["steps"] = dict(step_items)
            metrics["truncated"] = True
            metrics["aggregates_only"] = True
            metrics["dropped_series"] = original_step_count - 10
            was_truncated = True

        # Recheck size after initial metrics truncation
        json_str = canonicalize_json(result)
        current_size = len(json_str.encode("utf-8"))

        # If still too large, remove steps entirely
        if current_size > max_bytes and "steps" in metrics:
            dropped_count = len(metrics.get("steps", {}))
            del metrics["steps"]
            metrics["truncated"] = True
            metrics["aggregates_only"] = True
            metrics["dropped_series"] = dropped_count
            was_truncated = True

    # Check size after metrics truncation
    json_str = canonicalize_json(result)
    current_size = len(json_str.encode("utf-8"))

    if current_size <= max_bytes:
        return result, was_truncated

    # Handle evidence.artifacts
    if "evidence" in result and "artifacts" in result["evidence"]:
        artifacts = result["evidence"]["artifacts"]

        # Convert to truncated form if it's a list
        if isinstance(artifacts, list) and len(artifacts) > 10:
            kept_artifacts = artifacts[:10]
            result["evidence"]["artifacts"] = {
                "files": kept_artifacts,
                "truncated": True,
                "content_omitted": True,
            }
            was_truncated = True

    # Final size check - if still too large, apply more aggressive truncation
    json_str = canonicalize_json(result)
    current_size = len(json_str.encode("utf-8"))

    while current_size > max_bytes:
        # More aggressive truncation for timeline
        if "evidence" in result and "timeline" in result["evidence"]:
            timeline = result["evidence"]["timeline"]

            # First convert list to object if not already done
            if isinstance(timeline, list):
                # Convert to object form with aggressive truncation
                original_count = len(timeline)
                # Keep very few items when over limit
                kept_items = timeline[:5] + timeline[-5:] if len(timeline) > 10 else timeline
                result["evidence"]["timeline"] = {
                    "items": kept_items,
                    "truncated": True,
                    "dropped_events": original_count - len(kept_items),
                }
                was_truncated = True
                timeline = result["evidence"]["timeline"]

            if isinstance(timeline, dict) and "items" in timeline:
                items = timeline["items"]
                if len(items) > 10:
                    # Progressively reduce items
                    timeline["items"] = items[:5] + items[-5:]
                    timeline["dropped_events"] = timeline.get("dropped_events", 0) + (len(items) - 10)
                    was_truncated = True
                elif len(items) > 2:
                    # Keep just first and last
                    timeline["items"] = [items[0], items[-1]]
                    timeline["dropped_events"] = timeline.get("dropped_events", 0) + (len(items) - 2)
                    was_truncated = True
                else:
                    # Remove all items
                    timeline["items"] = []
                    timeline["dropped_events"] = timeline.get("dropped_events", 0) + len(items)
                    timeline["all_dropped"] = True
                    was_truncated = True

        # Handle artifacts - convert to object form if needed
        if "evidence" in result and "artifacts" in result["evidence"]:
            artifacts = result["evidence"]["artifacts"]

            # Convert list to object if still a list
            if isinstance(artifacts, list) or isinstance(artifacts, dict) and artifacts.get("files"):
                result["evidence"]["artifacts"] = {
                    "files": [],
                    "truncated": True,
                    "content_omitted": True,
                    "all_dropped": True,
                }
                was_truncated = True

        # Remove errors if present and still too large
        if "evidence" in result and "errors" in result["evidence"] and result["evidence"]["errors"]:
            result["evidence"]["errors"] = []
            was_truncated = True

        # Recheck size
        json_str = canonicalize_json(result)
        new_size = len(json_str.encode("utf-8"))

        # If we didn't make progress, break to avoid infinite loop
        if new_size >= current_size:
            break
        current_size = new_size

    return result, was_truncated


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
    # Try to get manifest hash from the correct location
    manifest_hash = None
    if "manifest_hash" in manifest:
        manifest_hash = manifest["manifest_hash"]
    elif manifest.get("meta", {}).get("manifest_hash"):
        from osiris.core.fs_paths import normalize_manifest_hash

        manifest_hash = normalize_manifest_hash(manifest["meta"]["manifest_hash"])

    if manifest_hash:
        semantic["@id"] = f"osiris://pipeline/@{manifest_hash}"

    semantic["@type"] = "SemanticLayer"

    # Add pipeline name from manifest
    if "name" in manifest:
        semantic["pipeline_name"] = manifest["name"]
    else:
        # Check if pipeline is a dict with id field
        pipeline_data = manifest.get("pipeline")
        if isinstance(pipeline_data, dict) and "id" in pipeline_data:
            semantic["pipeline_name"] = pipeline_data["id"]

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

    # Build edges based on input/output dependencies, depends_on, and needs
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

        # Check needs field (needs relation) - common in OML
        for need_step in step.get("needs", []):
            edges.append({"from": need_step, "to": step_id, "relation": "needs"})

    # Sort for determinism
    edges.sort(key=lambda e: (e["from"], e["to"], e["relation"]))

    return {"nodes": nodes, "edges": edges, "counts": {"nodes": len(nodes), "edges": len(edges)}}


@lru_cache(maxsize=32)
def build_component_ontology_cached(components_str: str, mode: str = "summary") -> dict:
    """Cached version of build_component_ontology using JSON string key.

    Args:
        components_str: JSON string of component definitions
        mode: "summary" or "detailed"

    Returns:
        Component ontology dictionary
    """
    components = json.loads(components_str)
    return _build_component_ontology_impl(components, mode)


def build_component_ontology(components: dict, mode: str = "summary") -> dict:
    """Map components to ontology (types, capabilities, optional schema snippets based on mode).

    Args:
        components: Dictionary of component definitions
        mode: "summary" or "detailed"

    Returns:
        Component ontology dictionary
    """
    # Use cached version for performance
    components_str = json.dumps(components, sort_keys=True)
    return build_component_ontology_cached(components_str, mode)


def _build_component_ontology_impl(components: dict, mode: str = "summary") -> dict:
    """Implementation of component ontology building.

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
    # Try to get manifest hash from meta.manifest_hash (canonical source)
    manifest_hash = manifest.get("manifest_hash", "unknown")
    if manifest_hash == "unknown" and manifest:
        # Extract from meta.manifest_hash and normalize
        from osiris.core.fs_paths import normalize_manifest_hash

        manifest_hash = manifest.get("meta", {}).get("manifest_hash", "unknown")
        if manifest_hash != "unknown":
            manifest_hash = normalize_manifest_hash(manifest_hash)
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


# ============================================================================
# PR4 - Narrative Layer and Markdown Run-card
# ============================================================================


def format_duration(ms: int | None) -> str:
    """Format milliseconds as human-readable duration.

    Args:
        ms: Duration in milliseconds

    Returns:
        Human-readable duration string (e.g., "5m 23s")
    """
    if ms is None or ms < 0:
        return "0s"

    seconds = ms // 1000
    if seconds == 0:
        return "0s"

    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")

    return " ".join(parts)


def discover_intent(
    manifest: dict,
    repo_readme: str | None = None,
    commits: list[dict] | None = None,
    chat_logs: list[dict] | None = None,
    config: dict | None = None,
) -> tuple[str, bool, list[dict]]:
    """Discover pipeline intent from multiple sources with provenance tracking.

    Args:
        manifest: Pipeline manifest (highest trust)
        repo_readme: README.md content from repo root (medium trust)
        commits: List of commit messages (medium trust)
        chat_logs: Session chat logs if enabled (low trust)
        config: AIOP configuration for redaction settings

    Returns:
        Tuple of (intent_summary, intent_known, intent_provenance)
        intent_provenance contains exactly one item - the winning source
    """
    intent_summary = ""
    intent_known = False
    winning_source = None

    # Helper to create provenance entry with excerpt
    def make_provenance(source: str, value: str, trust: str, location: str = None) -> dict:
        excerpt = value[:160] if len(value) > 160 else value
        prov = {"source": source, "trust": trust, "excerpt": excerpt}
        if location:
            prov["location"] = location
        return prov

    # 1. Check manifest.metadata.intent (highest trust) - if found, stop here
    if manifest and manifest.get("metadata", {}).get("intent"):
        intent_text = manifest["metadata"]["intent"].strip()
        if intent_text:
            intent_summary = intent_text
            intent_known = True
            winning_source = make_provenance("manifest", intent_text, "high", "manifest.metadata.intent")
            return intent_summary, intent_known, [winning_source]

    # 2. Check pipeline description (high trust) - if found, stop here
    if manifest and manifest.get("description"):
        description = manifest["description"].strip()
        if description:
            intent_summary = description
            intent_known = True
            winning_source = make_provenance("manifest_description", description, "high", "manifest.description")
            return intent_summary, intent_known, [winning_source]

    # 3. Check README.md for intent line (medium trust) - take first match
    if repo_readme and not intent_known:
        import re

        intent_pattern = re.compile(r"^(intent|purpose|objective|goal):\s*(.+)", re.IGNORECASE | re.MULTILINE)
        matches = intent_pattern.findall(repo_readme)
        if matches:
            intent_text = matches[0][1].strip()
            if intent_text:
                intent_summary = intent_text
                intent_known = True
                winning_source = make_provenance("readme", intent_text, "medium", "README.md")
                return intent_summary, intent_known, [winning_source]

    # 4. Check commit messages for intent lines (medium trust) - take first match
    if commits and not intent_known:
        import re

        for commit in commits:
            message = commit.get("message", "")
            intent_pattern = re.compile(r"^intent:\s*(.+)", re.IGNORECASE | re.MULTILINE)
            matches = intent_pattern.findall(message)
            if matches:
                intent_text = matches[0].strip()
                if intent_text:
                    intent_summary = intent_text
                    intent_known = True
                    winning_source = make_provenance("commit_message", intent_text, "medium", "git commit")
                    return intent_summary, intent_known, [winning_source]

    # 5. Check chat logs if enabled (low trust) - take first match
    if chat_logs and config and config.get("narrative", {}).get("session_chat", {}).get("enabled") and not intent_known:
        mode = config.get("narrative", {}).get("session_chat", {}).get("mode", "masked")
        for log_entry in chat_logs:
            if log_entry.get("role") == "user":
                content = log_entry.get("content", "")
                if mode == "masked":
                    content = redact_secrets({"content": content}).get("content", "")

                if "want to" in content.lower() or "need to" in content.lower() or "pipeline" in content.lower():
                    sentences = content.split(".")
                    if sentences:
                        potential_intent = sentences[0].strip()
                        if potential_intent and len(potential_intent) < 200:
                            intent_summary = potential_intent
                            intent_known = True
                            winning_source = make_provenance("chat_log", potential_intent, "low", "session chat")
                            return intent_summary, intent_known, [winning_source]

    # Fallback to generated summary if no intent found
    if not intent_known:
        intent_summary = generate_intent_summary(manifest)
        winning_source = make_provenance("inferred", intent_summary, "low")
        return intent_summary, intent_known, [winning_source]

    # Should not reach here, but ensure we always return something
    return intent_summary, intent_known, [winning_source] if winning_source else []


def generate_intent_summary(manifest: dict) -> str:
    """Extract pipeline intent from manifest.

    Args:
        manifest: Pipeline manifest

    Returns:
        Brief summary of pipeline intent/purpose
    """
    # Try to get description first
    if "description" in manifest and manifest["description"]:
        return manifest["description"].strip()

    # Try to infer from steps
    steps = manifest.get("steps", [])
    if steps:
        # Look at step IDs or types to determine operations
        has_extract = False
        has_transform = False
        has_export = False

        for step in steps:
            step_id = step.get("id", "").lower()
            step_type = step.get("type", "").lower()
            step_component = step.get("component", "").lower()

            # Check all fields for operation keywords
            combined = f"{step_id} {step_type} {step_component}"

            if "extract" in combined or "read" in combined or "fetch" in combined:
                has_extract = True
            if "transform" in combined or "process" in combined or "aggregate" in combined:
                has_transform = True
            if "export" in combined or "write" in combined or "load" in combined or "save" in combined:
                has_export = True

        # Build intent based on detected operations
        operations = []
        if has_extract:
            operations.append("Extract")
        if has_transform:
            operations.append("transform")
        if has_export:
            operations.append("export")

        if operations:
            # Format: "Extract and export data" or "Extract, transform and export data"
            if len(operations) == 1:
                intent = f"{operations[0]} data"
            elif len(operations) == 2:
                intent = f"{operations[0]} and {operations[1]} data"
            else:
                intent = f"{operations[0]}, {' and '.join(operations[1:])} data"

            # Add pipeline name if present
            pipeline_name = manifest.get("pipeline") or manifest.get("name")
            if pipeline_name:
                intent += f" with pipeline {pipeline_name}"
            else:
                intent += " with an unnamed pipeline"

            return intent

    # Default fallback
    pipeline_name = manifest.get("pipeline") or manifest.get("name")
    if pipeline_name:
        return f"Execute pipeline {pipeline_name}"
    else:
        return "Execute an unnamed pipeline"


def _collect_evidence_ids(evidence_refs: dict) -> list[str]:
    """Collect and sanitize evidence IDs from evidence_refs.

    Args:
        evidence_refs: Dictionary containing evidence references

    Returns:
        List of unique, sanitized evidence IDs
    """
    collected_ids = []
    secret_patterns = {"password", "token", "api_key", "key", "secret", "credential"}

    # Priority order for known keys (lowercase for case-insensitive matching)
    priority_keys = [
        "rows_metric_id",
        "timeline_id",
        "timeline_ids",
        "evidence_id",
        "evidence_ids",
        "metrics",
        "events",
    ]

    # Create lowercase map of actual keys for case-insensitive matching
    key_map = {k.lower(): k for k in evidence_refs}

    # First check priority keys with case-insensitive matching
    for priority_key in priority_keys:
        # Find actual key that matches (case-insensitive)
        actual_key = None
        for lower_key, original_key in key_map.items():
            if lower_key == priority_key.lower():
                actual_key = original_key
                break

        if actual_key:
            value = evidence_refs[actual_key]
            if isinstance(value, str):
                value = [value]
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        item = item.strip()
                        if (
                            item
                            and (item.startswith("ev.") or item.startswith("osiris://"))
                            and not any(secret in item.lower() for secret in secret_patterns)
                        ):
                            collected_ids.append(item)

    # Then check any key ending with _id or _ids (case-insensitive)
    for key, value in evidence_refs.items():
        key_lower = key.lower()
        # Skip if already processed as priority key
        is_priority = any(key_lower == pk.lower() for pk in priority_keys)
        if not is_priority and (key_lower.endswith("_id") or key_lower.endswith("_ids")):
            if isinstance(value, str):
                value = [value]
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        item = item.strip()
                        if (
                            item
                            and (item.startswith("ev.") or item.startswith("osiris://"))
                            and not any(secret in item.lower() for secret in secret_patterns)
                        ):
                            collected_ids.append(item)

    # Deduplicate while preserving order
    seen = set()
    unique_ids = []
    for id_val in collected_ids:
        if id_val not in seen:
            seen.add(id_val)
            unique_ids.append(id_val)
            if len(unique_ids) >= 3:  # Limit to 3 citations
                break

    return unique_ids


def build_narrative_layer(
    manifest: dict,
    run_summary: dict,
    evidence_refs: dict,
    config: dict | None = None,
    repo_readme: str | None = None,
    commits: list[dict] | None = None,
    chat_logs: list[dict] | None = None,
) -> dict:
    """Generate natural language narrative (3-5 paragraphs) with intent discovery.

    Args:
        manifest: Pipeline manifest
        run_summary: Run execution summary with status, duration, etc.
        evidence_refs: Dictionary of evidence references (metrics, events, etc.)
        config: AIOP configuration for narrative settings
        repo_readme: README content for intent discovery
        commits: Commit messages for intent discovery
        chat_logs: Session chat logs if enabled

    Returns:
        Dictionary with paragraphs list, intent summary, and provenance
    """
    # Discover intent from multiple sources
    intent_summary, intent_known, intent_provenance = discover_intent(manifest, repo_readme, commits, chat_logs, config)

    # Extract key information - use "name" field for pipeline name
    pipeline_name = manifest.get("name", manifest.get("pipeline", "unnamed pipeline"))
    status = run_summary.get("status", "unknown")
    duration_ms = run_summary.get("duration_ms")
    duration_str = format_duration(duration_ms) if duration_ms else "unknown duration"
    total_rows = run_summary.get("total_rows", 0)
    started_at = run_summary.get("started_at", "")
    completed_at = run_summary.get("completed_at", "")

    # Collect evidence IDs for citation
    evidence_ids = _collect_evidence_ids(evidence_refs)

    # Build narrative paragraphs
    paragraphs = []

    # Paragraph 1: Context and Intent
    context_para = f"The pipeline execution for {pipeline_name} was initiated"
    if started_at:
        context_para += f" at {started_at}"
    context_para += f". {intent_summary}."
    paragraphs.append(context_para)

    # Paragraph 2: Execution details
    exec_para = "The pipeline executed"
    steps = manifest.get("steps", [])
    if steps:
        exec_para += f" {len(steps)} steps"
        step_names = [s.get("id", "unnamed") for s in steps[:3]]  # First 3 steps
        if step_names:
            exec_para += f" including {', '.join(step_names)}"
            if len(steps) > 3:
                exec_para += f" and {len(steps) - 3} more"
    exec_para += f". The execution took {duration_str} to complete."
    if total_rows > 0:
        exec_para += f" During execution, {total_rows:,} rows were processed."
    # Include evidence citations if available
    if evidence_ids:
        citations = ", ".join(f"[{id_val}]" for id_val in evidence_ids)
        exec_para += f" Supporting evidence: {citations}."
    paragraphs.append(exec_para)

    # Paragraph 3: Outcome
    if status == "success":
        outcome_para = "The pipeline completed successfully"
        if completed_at:
            outcome_para += f" at {completed_at}"
        outcome_para += ". All configured steps executed without errors"
        if total_rows > 0:
            outcome_para += ", successfully processing the entire dataset"
        outcome_para += "."
    elif status == "failure":
        outcome_para = "The pipeline execution failed"
        if completed_at:
            outcome_para += f" at {completed_at}"
        outcome_para += ". The execution encountered errors that prevented successful completion."
    else:
        outcome_para = f"The pipeline execution ended with status: {status}."

    paragraphs.append(outcome_para)

    # Paragraph 4: Summary (if we have enough detail)
    if len(steps) > 1 and (evidence_ids or total_rows > 0):
        summary_para = "In summary, the pipeline "
        if status == "success":
            summary_para += "successfully "
        summary_para += "executed its configured data processing workflow"
        if total_rows > 0:
            summary_para += f", handling {total_rows:,} records"
        summary_para += f" in {duration_str}."
        paragraphs.append(summary_para)

    narrative = "\n\n".join(paragraphs)

    # Return both formats for compatibility with intent discovery fields
    return {
        "narrative": narrative,
        "paragraphs": paragraphs,
        "intent_summary": intent_summary,
        "intent_known": intent_known,
        "intent_provenance": intent_provenance,
    }


# ============================================================================
# PR5 - Parity, Redaction, Truncation & CLI
# ============================================================================


def redact_secrets(data: dict) -> dict:
    """Recursively redact secret fields in-place (returns sanitized copy).

    Denylist substrings (case-insensitive): password, token, api_key, key,
    secret, credential, authorization, private_key.
    Also sanitize connection strings (mask creds), and lists/dicts deeply.
    Deterministic traversal; preserve structure; replace values with '[REDACTED]'.

    Args:
        data: Dictionary to redact secrets from

    Returns:
        Sanitized copy with secrets redacted
    """
    # Denylist of secret field names (case-insensitive)
    # These are checked for exact matches or as suffixes (e.g., "user_password")
    secret_patterns = {
        "password",
        "token",
        "api_key",
        "secret",
        "authorization",
        "private_key",
        "auth_token",
        "access_token",
        "refresh_token",
        "bearer_token",
    }

    def _is_secret_field(field_name: str) -> bool:
        """Check if field name contains secret patterns."""
        field_lower = field_name.lower()

        # Special handling for "key" - only match if it's part of a compound word
        if field_lower == "key":
            return False  # Plain 'key' is not a secret

        # Special negative cases - field names that should NOT be treated as secrets
        # even though they contain secret patterns
        safe_fields = {
            "no_password",
            "without_password",
            "skip_password",
            "ignore_password",
            "has_password",
            "use_password",
            "password_required",
            "password_field",
            "password_column",
        }
        if field_lower in safe_fields:
            return False

        # Check for exact matches or if pattern is in the field name
        for pattern in secret_patterns:
            if pattern in field_lower:
                # Special case: 'secret' should match 'secret_key' but not 'secrets'
                if pattern == "secret" and field_lower == "secrets":
                    continue
                return True

        # Also check for common suffixes with underscore or camelCase
        if field_lower.endswith("_key") or field_lower.endswith("_secret"):
            return True
        return "Key" in field_name and (
            field_name.endswith("Key") or "ApiKey" in field_name or "SecretKey" in field_name
        )

    def _redact_connection_string(value: str) -> str:
        """Redact credentials from connection strings and query parameters."""
        import re

        # Store original for fallback
        # Handle DSN format: scheme://user:pass@host/db?params  # pragma: allowlist secret
        if "://" in value and "@" in value:
            # Use regex to mask user:pass part
            # Handle both user:pass and :pass (no username) formats
            value = re.sub(r"(://)([^:/@]+:[^@]+|:[^@]+)(@)", r"\1***\3", value)

        # Handle query parameters (even in URLs without @)
        if "?" in value or "&" in value:
            # Mask sensitive query parameters
            sensitive_params = [
                "key",
                "token",
                "password",
                "secret",
                "api_key",
                "apikey",
                "auth",
                "access_token",
            ]
            for param in sensitive_params:
                # Handle both & and ? delimiters - mask the value part
                # Use word boundary to avoid partial matches
                value = re.sub(rf"([?&]{param}=)[^&\s]+", r"\1***", value, flags=re.IGNORECASE)

        return value

    def _redact_value(value):
        """Recursively redact a value."""
        if isinstance(value, dict):
            return _redact_dict(value)
        elif isinstance(value, list):
            return [_redact_value(item) for item in value]
        elif isinstance(value, str):
            # Check if it looks like a connection string or URL with sensitive params
            if "://" in value:
                return _redact_connection_string(value)
            return value
        else:
            return value

    def _redact_dict(d: dict) -> dict:
        """Recursively redact dictionary."""
        result = {}
        for key, value in sorted(d.items()):  # Deterministic traversal
            if _is_secret_field(key):
                # Check if the value is a URL/connection string
                if isinstance(value, str) and ("://" in value or "?" in value):
                    # Apply connection string redaction instead of full redaction
                    result[key] = _redact_connection_string(value)
                else:
                    # Redact the entire value
                    result[key] = "[REDACTED]"
            else:
                # Recursively process the value
                result[key] = _redact_value(value)
        return result

    # Make a deep copy and handle different input types
    data_copy = copy.deepcopy(data)

    if isinstance(data_copy, dict):
        return _redact_dict(data_copy)
    elif isinstance(data_copy, list):
        return [_redact_value(item) for item in data_copy]
    else:
        return data_copy


def export_annex_shards(
    events: list[dict],
    metrics: list[dict],
    errors: list[dict],
    annex_dir: Path,
    compress: str = "none",
) -> dict:
    """Write NDJSON shards (events.ndjson, metrics.ndjson, errors.ndjson) into annex_dir.

    If compress == 'gzip', write .ndjson.gz (only for Annex, never for Core).
    Return manifest: { "files": [{"name": "…", "path": "…", "count": N, "size_bytes": M}], "compress": "none|gzip" }.

    Args:
        events: List of event dictionaries
        metrics: List of metric dictionaries
        errors: List of error dictionaries
        annex_dir: Directory to write shards to
        compress: Compression mode ('none' or 'gzip')

    Returns:
        Manifest dictionary with file information
    """
    # Ensure annex directory exists
    annex_dir.mkdir(parents=True, exist_ok=True)

    manifest = {"files": [], "compress": compress}

    # Define shards to export
    shards = [("events", events), ("metrics", metrics), ("errors", errors)]

    for shard_name, shard_data in shards:
        # Determine filename based on compression
        if compress == "gzip":
            filename = f"{shard_name}.ndjson.gz"
            file_path = annex_dir / filename

            # Write gzipped NDJSON
            with gzip.open(file_path, "wt", encoding="utf-8") as f:
                for item in shard_data:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
        else:
            filename = f"{shard_name}.ndjson"
            file_path = annex_dir / filename

            # Write plain NDJSON
            with open(file_path, "w", encoding="utf-8") as f:
                for item in shard_data:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")

        # Get file size
        size_bytes = file_path.stat().st_size if file_path.exists() else 0

        # Add to manifest
        manifest["files"].append(
            {
                "name": filename,
                "path": str(file_path),
                "count": len(shard_data),
                "size_bytes": size_bytes,
            }
        )

    return manifest


def generate_markdown_runcard(aiop: dict) -> str:
    """Generate Markdown run-card from AIOP.

    Args:
        aiop: AIOP dictionary with evidence, metrics, etc.

    Returns:
        Markdown-formatted run card
    """
    # Guard against empty or None input
    if not aiop:
        return "## Unknown Pipeline ⚠️\n\n*No data available*\n"

    lines = []

    # Extract pipeline name from correct location
    pipeline_data = aiop.get("pipeline", {})
    pipeline_name = pipeline_data.get("name") if isinstance(pipeline_data, dict) else None

    # Fallback to pipeline_name at root level (for backward compatibility)
    if not pipeline_name:
        pipeline_name = aiop.get("pipeline_name")

    # Fallback to pipeline URI if available
    if not pipeline_name and "@id" in aiop:
        pipeline_uri = aiop["@id"]
        if "pipeline/" in pipeline_uri:
            # Try to extract name from URI
            pipeline_name = pipeline_uri.split("/")[-1].split("@")[0] if "@" in pipeline_uri else "Pipeline"

    # Final fallback - ensure never empty
    if not pipeline_name:
        pipeline_name = "Unknown Pipeline"

    # Extract status from run section - ensure never None
    run_data = aiop.get("run", {})
    status = run_data.get("status") if isinstance(run_data, dict) else aiop.get("status", "unknown")

    # Ensure status is never None or empty
    if not status:
        status = "unknown"

    # Map status to icon
    if status in ["completed", "success"]:
        status_icon = "✅"
    elif status in ["failed", "failure"]:
        status_icon = "❌"
    else:
        status_icon = "⚠️"

    lines.append(f"## {pipeline_name} {status_icon}")
    lines.append("")

    # Intent section (if available)
    narrative = aiop.get("narrative", {})
    if narrative:
        # Check both old and new structures
        intent_known = narrative.get("intent_known", False)
        intent_summary = narrative.get("intent_summary", "")

        # Also check nested structure
        if not intent_summary and "intent" in narrative:
            intent_data = narrative["intent"]
            if isinstance(intent_data, dict):
                intent_known = intent_data.get("known", False)
                intent_summary = intent_data.get("summary", "")

        if intent_known and intent_summary:
            lines.append(f"*Intent:* {intent_summary}")
            lines.append("")

    # Evidence links
    session_id = run_data.get("session_id", "")
    if session_id:
        lines.append("**Evidence:**")
        lines.append(f"- Session: `{session_id}`")

        # Add AIOP path if available
        metadata = aiop.get("metadata", {})
        if metadata:
            # Try to extract core_path from somewhere
            lines.append(f"- AIOP: `logs/aiop/run_{session_id[-13:]}/aiop.json`")
        lines.append("")

    # Summary info
    duration_ms = run_data.get("duration_ms") if isinstance(run_data, dict) else aiop.get("duration_ms", 0)
    duration = format_duration(duration_ms)
    lines.append(f"**Status:** {status}")
    lines.append(f"**Duration:** {duration}")

    # Metrics summary
    evidence = aiop.get("evidence", {})
    metrics = evidence.get("metrics", {})
    total_rows = metrics.get("total_rows")
    if total_rows:
        lines.append(f"**Total Rows:** {total_rows:,}")

    # Delta analysis with improved formatting
    metadata = aiop.get("metadata", {})
    delta = metadata.get("delta", {})
    if delta and not delta.get("first_run", False):
        lines.append("")
        lines.append("### 📊 Since last run")
        lines.append("")

        # Create a comparison table
        lines.append("| Metric | Previous | Current | Change |")
        lines.append("|--------|----------|---------|--------|")

        # Row delta
        if "rows" in delta:
            row_delta = delta["rows"]
            prev = row_delta.get("previous", 0)
            curr = row_delta.get("current", 0)
            change = row_delta.get("change", 0)
            change_percent = row_delta.get("change_percent", 0)

            if change > 0:
                change_str = f"📈 +{change:,} (+{change_percent:.1f}%)"
            elif change < 0:
                change_str = f"📉 {change:,} ({change_percent:.1f}%)"
            else:
                change_str = "➡️ No change"

            lines.append(f"| **Rows** | {prev:,} | {curr:,} | {change_str} |")

        # Duration delta
        if "duration_ms" in delta:
            dur_delta = delta["duration_ms"]
            prev_ms = dur_delta.get("previous", 0)
            curr_ms = dur_delta.get("current", 0)
            change_ms = dur_delta.get("change", 0)
            change_percent = dur_delta.get("change_percent", 0)

            prev_str = format_duration(prev_ms) if prev_ms else "0s"
            curr_str = format_duration(curr_ms) if curr_ms else "0s"

            # Duration: faster is better (green down arrow)
            if change_ms < 0:
                change_str = f"🟢 -{format_duration(abs(change_ms))} ({change_percent:.1f}%)"
            elif change_ms > 0:
                change_str = f"🔴 +{format_duration(change_ms)} (+{change_percent:.1f}%)"
            else:
                change_str = "➡️ No change"

            lines.append(f"| **Duration** | {prev_str} | {curr_str} | {change_str} |")

        # Error delta
        if "errors_count" in delta:
            err_delta = delta["errors_count"]
            prev = err_delta.get("previous", 0)
            curr = err_delta.get("current", 0)
            change = err_delta.get("change", 0)

            if change < 0:
                change_str = f"✅ {change:+d}"
            elif change > 0:
                change_str = f"❗ {change:+d}"
            else:
                change_str = "➡️ No change"

            lines.append(f"| **Errors** | {prev} | {curr} | {change_str} |")

        lines.append("")
    elif delta and delta.get("first_run", False):
        lines.append("")
        lines.append("*First run with this configuration*")

    lines.append("")

    # Step metrics with improved tabular layout
    steps = metrics.get("steps", {})
    if steps and isinstance(steps, dict):
        lines.append("### Step Metrics")
        lines.append("")

        # Create a table for better readability
        lines.append("| Step | Rows Read | Rows Written | Duration |")
        lines.append("|------|-----------|--------------|----------|")

        for step_name, step_metrics in steps.items():
            rows_read = step_metrics.get("rows_read")
            rows_written = step_metrics.get("rows_written")
            duration = step_metrics.get("duration_ms")

            # Format values
            read_str = f"{rows_read:,}" if rows_read is not None else "–"
            write_str = f"{rows_written:,}" if rows_written is not None else "–"

            if duration is None:
                dur_str = "–"
            elif duration == 0:
                dur_str = "0s"
            else:
                dur_str = format_duration(duration)

            # Check for errors
            if step_metrics.get("error"):
                dur_str = f"❌ {step_metrics['error']}"

            lines.append(f"| {step_name} | {read_str} | {write_str} | {dur_str} |")

        lines.append("")

    # Errors if any
    errors = evidence.get("errors", [])
    if errors:
        lines.append("### Errors")
        lines.append("")
        for error in errors:
            error_id = error.get("@id", "")
            message = error.get("message", "Unknown error")
            if error_id:
                lines.append(f"- [{error_id}] {message}")
            else:
                lines.append(f"- {message}")
        lines.append("")

    # Narrative summary (if available)
    narrative = aiop.get("narrative", {})
    if narrative and "summary" in narrative:
        lines.append("### Summary")
        lines.append("")
        lines.append(narrative["summary"])
        lines.append("")

    # Add index file links
    lines.append("---")
    lines.append("")
    lines.append("### 📁 Index Files")
    lines.append("")

    # Extract manifest hash if available
    manifest_hash = None
    if pipeline_data and isinstance(pipeline_data, dict):
        manifest_hash = pipeline_data.get("manifest_hash")
    if not manifest_hash and metadata:
        # Try to get from delta source
        delta_info = metadata.get("delta", {})
        if isinstance(delta_info, dict) and "manifest_hash" in delta_info:
            manifest_hash = delta_info["manifest_hash"]

    lines.append("- **All runs:** `logs/aiop/index/runs.jsonl`")
    if manifest_hash:
        lines.append(f"- **This pipeline:** `logs/aiop/index/by_pipeline/{manifest_hash}.jsonl`")
    lines.append("- **Latest run:** `logs/aiop/latest` (symlink)")
    lines.append("")

    return "\n".join(lines)


def calculate_delta(current_run: dict, manifest_hash: str, current_session_id: str = None) -> dict:
    """Compare against previous run for same manifest_hash using index.

    On first run: return {"first_run": true}.
    Otherwise include 'rows', 'duration', and 'errors' changes.

    Args:
        current_run: Current run data with metrics
        manifest_hash: Hash of the manifest for comparison
        current_session_id: Current session ID to exclude from previous runs

    Returns:
        Delta dictionary with first_run flag or change metrics
    """
    # Check if we have metrics in current run
    if not current_run or "metrics" not in current_run:
        return {"first_run": True, "delta_source": "no_metrics"}

    metrics = current_run.get("metrics", {})
    total_rows = metrics.get("rows_total") or metrics.get("total_rows", 0)
    duration_ms = metrics.get("total_duration_ms", 0)
    errors_count = len(current_run.get("errors", []))

    # Look up previous run by manifest hash in index
    previous_run = _find_previous_run_by_manifest(manifest_hash, current_session_id)

    if not previous_run:
        return {"first_run": True, "delta_source": "by_pipeline_index"}

    # Calculate deltas
    delta = {"first_run": False, "delta_source": "by_pipeline_index"}

    # Get previous metrics (from index record)
    previous_rows = previous_run.get("total_rows", 0)
    previous_duration_ms = previous_run.get("duration_ms", 0)
    previous_errors = previous_run.get("errors_count", 0)

    # Calculate row delta
    if total_rows > 0 or previous_rows > 0:
        change = total_rows - previous_rows
        if previous_rows > 0:
            change_percent = round((change / previous_rows) * 100, 2)
        else:
            change_percent = 100.0 if total_rows > 0 else 0.0

        delta["rows"] = {
            "previous": previous_rows,
            "current": total_rows,
            "change": change,
            "change_percent": change_percent,
        }

    # Calculate duration delta
    if duration_ms > 0 or previous_duration_ms > 0:
        change = duration_ms - previous_duration_ms
        if previous_duration_ms > 0:
            change_percent = round((change / previous_duration_ms) * 100, 2)
        else:
            change_percent = 100.0 if duration_ms > 0 else 0.0

        delta["duration_ms"] = {
            "previous": previous_duration_ms,
            "current": duration_ms,
            "change": change,
            "change_percent": change_percent,
        }

    # Calculate errors delta
    if errors_count > 0 or previous_errors > 0:
        change = errors_count - previous_errors
        delta["errors_count"] = {
            "previous": previous_errors,
            "current": errors_count,
            "change": change,
        }

    return delta


def _load_chat_logs(session_id: str, config: dict) -> list[dict] | None:
    """Load chat logs from session if enabled in config.

    Args:
        session_id: Session ID to load chat logs from
        config: AIOP configuration

    Returns:
        List of chat log entries or None if disabled/not found
    """
    # Check if chat logs are enabled
    if not config.get("narrative", {}).get("session_chat", {}).get("enabled", False):
        return None

    # Look for chat logs in session artifacts
    chat_log_path = Path(f"logs/{session_id}/artifacts/chat_log.json")
    if not chat_log_path.exists():
        # Try alternative location
        chat_log_path = Path(f"logs/{session_id}/chat_log.json")
        if not chat_log_path.exists():
            return None

    try:
        with open(chat_log_path) as f:
            chat_logs = json.load(f)

        # Apply redaction based on mode
        mode = config.get("narrative", {}).get("session_chat", {}).get("mode", "masked")
        max_chars = config.get("narrative", {}).get("session_chat", {}).get("max_chars", 10000)

        if mode == "masked":
            # Apply PII redaction to each log entry
            redacted_logs = []
            total_chars = 0
            for entry in chat_logs:
                if total_chars >= max_chars:
                    break
                redacted_entry = redact_secrets(entry)
                content_len = len(str(redacted_entry.get("content", "")))
                if total_chars + content_len > max_chars:
                    # Truncate the content
                    remaining = max_chars - total_chars
                    redacted_entry["content"] = redacted_entry.get("content", "")[:remaining] + "..."
                    redacted_logs.append(redacted_entry)
                    break
                redacted_logs.append(redacted_entry)
                total_chars += content_len
            return redacted_logs
        elif mode == "off":
            return None
        else:  # quotes mode or other
            # Return with truncation only
            truncated_logs = []
            total_chars = 0
            for entry in chat_logs:
                if total_chars >= max_chars:
                    break
                content_len = len(str(entry.get("content", "")))
                if total_chars + content_len > max_chars:
                    # Truncate the content
                    remaining = max_chars - total_chars
                    entry_copy = entry.copy()
                    entry_copy["content"] = entry.get("content", "")[:remaining] + "..."
                    truncated_logs.append(entry_copy)
                    break
                truncated_logs.append(entry)
                total_chars += content_len
            return truncated_logs
    except Exception:
        return None


def _build_llm_primer() -> dict:
    """Build LLM primer with glossary and about section.

    Returns:
        Dictionary with about and glossary fields
    """
    # Keep about to <= 280 chars and glossary to <= 8 terms
    return {
        "about": (
            "AIOP (AI Operation Package) is a structured JSON-LD format for capturing pipeline "
            "execution data. It has four layers: Evidence (metrics/events), Semantic (DAG/components), "
            "Narrative (descriptions), and Metadata (config/deltas) for AI analysis."
        ),
        "glossary": {
            "run": "Single pipeline execution",
            "step": "Individual operation (extract/transform/write)",
            "manifest_hash": "Unique pipeline configuration ID",
            "delta": "Comparison between runs",
            "annex": "External storage for large data",
            "truncated": "Data reduced to meet size limits",
            "rows_source": "Method for determining row count",
            "active_duration": "Time actively processing data",
        },
    }


def _build_controls(session_id: str) -> dict:
    """Build controls section with actionable examples.

    Args:
        session_id: Current session ID

    Returns:
        Dictionary with examples list (max 3 items)
    """
    return {
        "examples": [
            {
                "title": "Export AIOP",
                "command": f"osiris logs aiop --session {session_id}",
                "notes": "Export this run for analysis",
            },
            {
                "title": "Rerun Pipeline",
                "command": "osiris run --last-compile",
                "notes": "Execute the last compiled manifest",
            },
            {
                "title": "Export with Annex",
                "command": f"osiris logs aiop --session {session_id} --policy annex",
                "notes": "Use for large runs exceeding size limits",
            },
        ]
    }


def _find_previous_run_by_manifest(
    manifest_hash: str, current_session_id: str = None, config: dict = None
) -> dict | None:
    """Find the most recent previous run with the same manifest hash.

    Args:
        manifest_hash: Hash of the manifest to look up
        current_session_id: Current session ID to exclude from results
        config: Optional AIOP config (from resolve_aiop_config)

    Returns:
        Previous run record or None if not found
    """
    if not manifest_hash or manifest_hash == "unknown":
        return None

    # Use config or load default
    if config is None:
        from osiris.core.config import resolve_aiop_config

        config, _ = resolve_aiop_config()

    # Get by_pipeline directory from config (matches where writes go)
    by_pipeline_dir = config.get("index", {}).get("by_pipeline_dir", "aiop/index/by_pipeline")
    index_path = Path(by_pipeline_dir) / f"{manifest_hash}.jsonl"

    # Try legacy location as fallback for backward compatibility
    if not index_path.exists():
        legacy_path = Path("logs/aiop/index/by_pipeline") / f"{manifest_hash}.jsonl"
        if legacy_path.exists():
            index_path = legacy_path

    if not index_path.exists():
        return None

    # Read all runs for this pipeline, get the most recent completed one
    runs = []
    try:
        with open(index_path) as f:
            for line in f:
                if line.strip():
                    run_data = json.loads(line)
                    # Skip the current run
                    if current_session_id and run_data.get("session_id") == current_session_id:
                        continue
                    # Only consider completed runs
                    if run_data.get("status") in ["completed", "success"]:
                        runs.append(run_data)
    except Exception:
        return None

    if not runs:
        return None

    # Sort by started_at timestamp (most recent first), fallback to ended_at
    runs.sort(key=lambda r: r.get("started_at") or r.get("ended_at", ""), reverse=True)

    # Return the most recent run (excluding current)
    return runs[0]


def build_aiop(
    session_data: dict,
    manifest: dict,
    events: list[dict],
    metrics: list[dict],
    artifacts: list,
    config: dict,
    show_progress: bool = False,
    config_sources: dict = None,
) -> dict:
    """Compose full AIOP Core package.

    - run, pipeline, narrative (PR4), semantic (PR3), evidence (PR2)
    - metadata: { "aiop_format": "1.0", "truncated": bool, "size_bytes": int, "size_hints": {…} }
    - compute delta and include in evidence or metadata per milestone
    - ensure canonicalization & determinism before size check
    - apply redact_secrets to all inputs prior to serialization
    - enforce size with apply_truncation; if truncated, set metadata.truncated=true
    - return the final dict (Core) and optionally annex manifest info if used.

    Args:
        session_data: Session information (session_id, started_at, etc.)
        manifest: Pipeline manifest
        events: List of event dictionaries
        metrics: List of metric dictionaries
        artifacts: List of artifact paths or dicts
        config: Configuration dictionary with max_core_bytes, timeline_density, etc.
        show_progress: Whether to show progress indicators

    Returns:
        Complete AIOP Core package dictionary
    """
    # Import Rich locally to avoid circular imports
    if show_progress:
        try:
            from rich.console import Console
            from rich.progress import Progress, SpinnerColumn, TextColumn

            console = Console(stderr=True)
            progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            )
        except ImportError:
            show_progress = False

    # Create progress context manager
    if show_progress:
        with progress:
            task_id = progress.add_task("Redacting secrets...", total=None)
            # Redact secrets from all inputs first
            session_data = redact_secrets(session_data)
            manifest = redact_secrets(manifest)
            events = [redact_secrets(event) for event in events]
            metrics = [redact_secrets(metric) for metric in metrics]
            progress.update(task_id, description="Secrets redacted")
    else:
        # Redact secrets from all inputs first
        session_data = redact_secrets(session_data)
        manifest = redact_secrets(manifest)
        events = [redact_secrets(event) for event in events]
        metrics = [redact_secrets(metric) for metric in metrics]

    # Convert artifact paths to Path objects if needed
    artifact_paths = []
    for artifact in artifacts:
        if isinstance(artifact, dict):
            # Extract path from dict
            path_str = artifact.get("path")
            if path_str:
                artifact_paths.append(Path(path_str))
        elif isinstance(artifact, str):
            artifact_paths.append(Path(artifact))
        elif isinstance(artifact, Path):
            artifact_paths.append(artifact)

    # Build layers
    max_bytes = config.get("max_core_bytes", 300 * 1024)
    timeline_density = config.get("timeline_density", "medium")
    metrics_topk = config.get("metrics_topk", 10)
    schema_mode = config.get("schema_mode", "summary")

    # Build layers with progress tracking
    if show_progress:
        with progress:
            # Build evidence layer (PR2)
            task_id = progress.add_task("Building evidence layer...", total=None)
            timeline = build_timeline(events, density=timeline_density)
            aggregated_metrics = aggregate_metrics(metrics, topk=metrics_topk, events=events)
            errors = _extract_errors(events)
            artifact_list = _build_artifact_list(artifact_paths)

            evidence = {
                "timeline": timeline,
                "metrics": aggregated_metrics,
                "errors": errors,
                "artifacts": artifact_list,
            }
            progress.update(task_id, description="Evidence layer complete")

            # Build semantic layer (PR3)
            progress.update(task_id, description="Building semantic layer...")
            # Create a minimal component registry if not provided
            component_registry = {}
            for step in manifest.get("steps", []):
                comp_name = step.get("component", "")
                if comp_name and comp_name not in component_registry:
                    component_registry[comp_name] = {
                        "version": "1.0",
                        "capabilities": ["extract", "transform", "write"],
                    }

            semantic = build_semantic_layer(
                manifest=manifest,
                oml_spec={"oml_version": manifest.get("oml_version", "0.1.0")},
                component_registry=component_registry,
                schema_mode=schema_mode,
            )
            progress.update(task_id, description="Semantic layer complete")

            # Build run summary
            progress.update(task_id, description="Building run summary...")
            run_summary = {
                "session_id": session_data.get("session_id"),
                "status": session_data.get("status", "unknown"),
                "started_at": session_data.get("started_at"),
                "completed_at": session_data.get("completed_at"),
                "duration_ms": aggregated_metrics.get("total_duration_ms", 0),
                "total_rows": aggregated_metrics.get("total_rows", 0),
                "environment": session_data.get("environment", "unknown"),
            }

            # Calculate delta
            # Extract manifest hash from the correct location
            manifest_hash = manifest.get("manifest_hash", "")
            if not manifest_hash and manifest:
                # Try meta.manifest_hash (canonical source)
                from osiris.core.fs_paths import normalize_manifest_hash

                manifest_hash = manifest.get("meta", {}).get("manifest_hash", "")
                if manifest_hash:
                    manifest_hash = normalize_manifest_hash(manifest_hash)
            # Load session_id before delta calculation
            session_id = session_data.get("session_id")

            delta = calculate_delta({"metrics": aggregated_metrics, "errors": errors}, manifest_hash, session_id)

            # Load chat logs if enabled
            chat_logs = _load_chat_logs(session_id, config) if session_id else None

            # Build narrative layer (PR4)
            progress.update(task_id, description="Building narrative layer...")
            evidence_refs = {
                "timeline_ids": [e.get("@id") for e in timeline[:3] if "@id" in e],
                "metrics": aggregated_metrics,
            }
            narrative = build_narrative_layer(manifest, run_summary, evidence_refs, config=config, chat_logs=chat_logs)
            progress.update(task_id, description="Narrative layer complete")
    else:
        # Build evidence layer (PR2)
        timeline = build_timeline(events, density=timeline_density)
        aggregated_metrics = aggregate_metrics(metrics, topk=metrics_topk, events=events)
        errors = _extract_errors(events)
        artifact_list = _build_artifact_list(artifact_paths)

        evidence = {
            "timeline": timeline,
            "metrics": aggregated_metrics,
            "errors": errors,
            "artifacts": artifact_list,
        }

        # Build semantic layer (PR3)
        # Create a minimal component registry if not provided
        component_registry = {}
        for step in manifest.get("steps", []):
            comp_name = step.get("component", "")
            if comp_name and comp_name not in component_registry:
                component_registry[comp_name] = {
                    "version": "1.0",
                    "capabilities": ["extract", "transform", "write"],
                }

        semantic = build_semantic_layer(
            manifest=manifest,
            oml_spec={"oml_version": manifest.get("oml_version", "0.1.0")},
            component_registry=component_registry,
            schema_mode=schema_mode,
        )

        # Build run summary
        # Calculate duration from timestamps
        duration_ms = 0
        started_at = session_data.get("started_at")
        completed_at = session_data.get("completed_at")
        if started_at and completed_at:
            try:
                from datetime import datetime

                if isinstance(started_at, str):
                    start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                else:
                    start_dt = started_at
                if isinstance(completed_at, str):
                    end_dt = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
                else:
                    end_dt = completed_at
                duration_ms = int((end_dt - start_dt).total_seconds() * 1000)
            except Exception:
                duration_ms = aggregated_metrics.get("total_duration_ms", 0)

        run_summary = {
            "session_id": session_data.get("session_id"),
            "status": session_data.get("status", "unknown"),
            "started_at": session_data.get("started_at"),
            "completed_at": session_data.get("completed_at"),
            "duration_ms": duration_ms,
            "total_rows": aggregated_metrics.get("total_rows", 0),
            "environment": session_data.get("environment", "unknown"),
        }

        # Calculate delta
        # Extract manifest hash from the correct location
        manifest_hash = manifest.get("manifest_hash", "")
        if not manifest_hash and manifest:
            # Try meta.manifest_hash (canonical source)
            from osiris.core.fs_paths import normalize_manifest_hash

            manifest_hash = manifest.get("meta", {}).get("manifest_hash", "")
            if manifest_hash:
                manifest_hash = normalize_manifest_hash(manifest_hash)
        # Load session_id before delta calculation
        session_id = session_data.get("session_id")
        delta = calculate_delta({"metrics": aggregated_metrics, "errors": errors}, manifest_hash, session_id)

        # Load chat logs if enabled
        chat_logs = _load_chat_logs(session_id, config) if session_id else None

        # Build narrative layer (PR4)
        evidence_refs = {
            "timeline_ids": [e.get("@id") for e in timeline[:3] if "@id" in e],
            "metrics": aggregated_metrics,
        }
        narrative = build_narrative_layer(manifest, run_summary, evidence_refs, config=config, chat_logs=chat_logs)

    # Compose AIOP
    aiop = {
        "@context": "https://osiris.io/schemas/aiop/v1",
        "@id": (f"osiris://pipeline/@{manifest_hash}" if manifest_hash else "osiris://pipeline/unknown"),
        "run": run_summary,
        "pipeline": {"name": manifest.get("name", "unnamed"), "manifest_hash": manifest_hash},
        "evidence": evidence,
        "semantic": semantic,
        "narrative": narrative,
        "metadata": {
            "aiop_format": "1.0",
            "truncated": False,
            "delta": delta,
            "config_effective": _build_config_effective(config, config_sources),
            "compute": {
                "rows_source": aggregated_metrics.get("rows_source", "unknown"),
                "total_rows": aggregated_metrics.get("total_rows", 0),
            },
            "size_hints": {
                "timeline_events": len(timeline),
                "metrics_steps": len(aggregated_metrics.get("steps", {})),
                "artifacts": len(artifact_list),
                "max_core_bytes": config.get("max_core_bytes", 300000),
                "metrics_topk": config.get("metrics_topk", 100),
                "policy": config.get("policy", "core"),
                "schema_mode": config.get("schema_mode", "summary"),
                "timeline_density": config.get("timeline_density", "medium"),
            },
        },
    }

    # Add LLM affordances
    aiop["metadata"]["llm_primer"] = _build_llm_primer()
    aiop["controls"] = _build_controls(session_id)

    # Apply truncation if needed
    truncated_aiop, was_truncated = apply_truncation(aiop, max_bytes)

    if was_truncated:
        truncated_aiop["metadata"]["truncated"] = True

    # Calculate final size
    final_json = canonicalize_json(truncated_aiop)
    truncated_aiop["metadata"]["size_bytes"] = len(final_json.encode("utf-8"))

    return truncated_aiop


def _build_config_effective(config: dict, config_sources: dict = None) -> dict:
    """Build config_effective with source annotations.

    Args:
        config: Effective configuration dictionary
        config_sources: Map of config key to source ("DEFAULT", "YAML", "ENV", "CLI")

    Returns:
        Config with source annotations
    """
    if not config_sources:
        # If no sources provided, just return config values
        return config

    # Build annotated config
    result = {}
    for key, value in config.items():
        if isinstance(value, dict):
            # Handle nested config
            nested_result = {}
            for nested_key, nested_value in value.items():
                full_key = f"{key}.{nested_key}"
                source = config_sources.get(full_key, "DEFAULT")
                nested_result[nested_key] = {"value": nested_value, "source": source}
            result[key] = nested_result
        else:
            # Handle top-level config
            source = config_sources.get(key, "DEFAULT")
            result[key] = {"value": value, "source": source}

    return result
