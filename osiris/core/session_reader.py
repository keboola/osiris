"""Session reader for aggregating and analyzing session logs.

This module provides functionality to read session data from the ./logs directory,
aggregate metrics, compute summaries, and handle redaction of sensitive information.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


@dataclass
class SessionSummary:
    """Aggregated summary of a session."""

    session_id: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_ms: int = 0
    status: str = "unknown"
    labels: List[str] = field(default_factory=list)

    # Aggregated metrics
    steps_total: int = 0
    steps_ok: int = 0
    steps_failed: int = 0
    rows_in: int = 0
    rows_out: int = 0
    tables: List[str] = field(default_factory=list)
    warnings: int = 0
    errors: int = 0

    # Pipeline metadata
    pipeline_name: Optional[str] = None
    oml_version: Optional[str] = None
    adapter_type: str = "Local"  # Default to Local, set to E2B for remote runs

    # Artifacts metadata
    artifacts_count: int = 0
    steps_with_artifacts: List[str] = field(default_factory=list)

    # Diagnostic hints
    double_count_hint: bool = False  # Indicates potential double counting (non-blocking)

    # Computed fields
    @property
    def success_rate(self) -> float:
        """Calculate success rate of steps."""
        if self.steps_total == 0:
            return 0.0
        return self.steps_ok / self.steps_total


class SessionReader:
    """Reads and aggregates session data from logs directory."""

    # Whitelist of fields that can be exposed without redaction
    WHITELIST_FIELDS = {
        "session_id",
        "started_at",
        "finished_at",
        "duration_ms",
        "status",
        "labels",
        "pipeline_name",
        "oml_version",
        "event",
        "level",
        "step_id",
        "rows_read",
        "rows_written",
        "tables",
        "mode",
        "component_type",
    }

    # Patterns for sensitive data that should be redacted
    SENSITIVE_PATTERNS = [
        # Database connection strings with user:password format
        (re.compile(r"mysql://[^:]+:[^@]+@"), "mysql://***@"),
        (re.compile(r"postgresql://[^:]+:[^@]+@"), "postgresql://***@"),
        (re.compile(r"postgres://[^:]+:[^@]+@"), "postgres://***@"),
        # JSON password fields
        (re.compile(r'"password"\s*:\s*"[^"]*"'), '"password": "***"'),
        (re.compile(r'"api_key"\s*:\s*"[^"]*"'), '"api_key": "***"'),
        (re.compile(r'"service_role_key"\s*:\s*"[^"]*"'), '"service_role_key": "***"'),
        # Bearer tokens
        (re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+"), "Bearer ***"),
    ]

    def __init__(self, logs_dir: str = "./logs"):
        """Initialize SessionReader with logs directory path.

        Args:
            logs_dir: Path to the logs directory (default: ./logs)
        """
        self.logs_dir = Path(logs_dir)

    def list_sessions(self, limit: Optional[int] = None) -> List[SessionSummary]:
        """List all sessions, ordered by newest first.

        Args:
            limit: Maximum number of sessions to return

        Returns:
            List of SessionSummary objects, newest first
        """
        if not self.logs_dir.exists():
            return []

        sessions = []

        # Find all session directories
        for session_dir in self.logs_dir.iterdir():
            if not session_dir.is_dir():
                continue
            if session_dir.name.startswith(".") or session_dir.name.startswith("@"):
                continue  # Skip hidden and special directories

            summary = self.read_session(session_dir.name)
            if summary:
                sessions.append(summary)

        # Sort by started_at (newest first), with deterministic fallback
        sessions.sort(key=lambda s: (s.started_at or "", s.session_id), reverse=True)

        if limit:
            sessions = sessions[:limit]

        return sessions

    def read_session(self, session_id: str) -> Optional[SessionSummary]:
        """Read and aggregate data for a single session.

        Args:
            session_id: The session ID to read

        Returns:
            SessionSummary object or None if session not found
        """
        session_path = self.logs_dir / session_id
        if not session_path.exists():
            return None

        summary = SessionSummary(session_id=session_id)

        # Read metadata.json if it exists
        metadata_path = session_path / "metadata.json"
        if metadata_path.exists():
            self._read_metadata(metadata_path, summary)

        # Read events.jsonl for step metrics
        events_path = session_path / "events.jsonl"
        if events_path.exists():
            self._read_events(events_path, summary)

        # Read metrics.jsonl for additional metrics
        metrics_path = session_path / "metrics.jsonl"
        if metrics_path.exists():
            self._read_metrics(metrics_path, summary)

        # Read artifacts directory
        artifacts_path = session_path / "artifacts"
        if artifacts_path.exists():
            self._read_artifacts(artifacts_path, summary)

        # Check for remote execution data
        remote_path = session_path / "remote"
        if remote_path.exists():
            self._merge_remote_data(remote_path, summary)

        # Check for E2B execution via commands.jsonl (RPC commands)
        commands_path = session_path / "commands.jsonl"
        if commands_path.exists() and summary.adapter_type != "E2B":
            try:
                with open(commands_path) as f:
                    for line in f:
                        try:
                            cmd = json.loads(line.strip())
                            if cmd.get("cmd") in ["prepare", "exec_step", "cleanup", "ping"]:
                                summary.adapter_type = "E2B"
                                break
                        except json.JSONDecodeError:
                            continue
            except OSError:
                pass

        return summary

    def get_last_session(self) -> Optional[SessionSummary]:
        """Get the most recent session.

        Returns:
            SessionSummary of the most recent session or None
        """
        sessions = self.list_sessions(limit=1)
        return sessions[0] if sessions else None

    def _read_metadata(self, path: Path, summary: SessionSummary) -> None:
        """Read and parse metadata.json file."""
        try:
            with open(path) as f:
                metadata = json.load(f)

            # Extract safe fields
            summary.started_at = metadata.get("started_at")
            summary.finished_at = metadata.get("finished_at")
            summary.duration_ms = metadata.get("duration_ms", 0)
            summary.status = metadata.get("status", "unknown")
            summary.labels = metadata.get("labels", [])
            summary.pipeline_name = metadata.get("pipeline_name")
            summary.rows_in = metadata.get("rows_in", 0)
            summary.rows_out = metadata.get("rows_out", 0)

        except (OSError, json.JSONDecodeError):
            pass  # Ignore invalid metadata files

    def _read_events(self, path: Path, summary: SessionSummary) -> None:
        """Read and aggregate events.jsonl file."""
        steps_seen: Set[str] = set()
        tables_seen: Set[str] = set()
        rows_by_step: Dict[str, int] = {}  # Track rows per step to avoid duplicates
        cleanup_total_rows = None  # Track cleanup_complete.total_rows if present

        try:
            with open(path) as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())
                        event_type = event.get("event")

                        # Track session timing
                        if event_type == "run_start":
                            summary.started_at = event.get("ts")
                            summary.status = "running"
                            # Extract pipeline name from run_start event
                            if "pipeline_id" in event:
                                summary.pipeline_name = event["pipeline_id"]

                        elif event_type == "run_end":
                            summary.finished_at = event.get("ts", event.get("end_time"))
                            # Extract duration from event if available
                            if "duration_seconds" in event:
                                summary.duration_ms = int(event["duration_seconds"] * 1000)
                            # Determine final status
                            if summary.errors > 0 or summary.steps_failed > 0:
                                summary.status = "failed"
                            else:
                                summary.status = "success"

                        # Track compile sessions
                        elif event_type == "compile_start":
                            summary.started_at = event.get("ts")
                            summary.status = "running"
                            summary.pipeline_name = (
                                event.get("pipeline", "").split("/")[-1].replace(".yaml", "")
                            )

                        elif event_type == "compile_complete":
                            summary.finished_at = event.get("ts")
                            if "duration" in event:
                                summary.duration_ms = int(event["duration"] * 1000)
                            summary.status = "success"

                        # Track connection sessions
                        elif event_type == "connections_list" or event_type == "connections_doctor":
                            if not summary.started_at:
                                summary.started_at = event.get("ts")
                            summary.finished_at = event.get("ts")
                            summary.status = "success"

                        # Track steps
                        elif event_type == "step_start":
                            step_id = event.get("step_id")
                            if step_id and step_id not in steps_seen:
                                steps_seen.add(step_id)
                                summary.steps_total += 1

                        elif event_type == "step_complete":
                            summary.steps_ok += 1
                            # Track rows_processed from step_complete for writers
                            step_id = event.get("step_id", "")
                            if "rows_processed" in event and step_id:
                                rows_by_step[step_id] = event["rows_processed"]

                        elif event_type == "step_error":
                            summary.steps_failed += 1
                            summary.errors += 1

                        # Check for cleanup_complete total_rows (preferred source for E2B)
                        elif event_type == "cleanup_complete" and "total_rows" in event:
                            cleanup_total_rows = event["total_rows"]

                        # Track data flow (only count if step_id present to avoid duplicates)
                        # Handle both direct rows_read field and metric-style with value field
                        if event_type == "rows_read" or "rows_read" in event:
                            if "step_id" in event:
                                step_id = event["step_id"]
                                # Get row count from either 'value' field (metric style) or 'rows_read' field
                                row_count = event.get("value", event.get("rows_read", 0))
                                if step_id not in rows_by_step and row_count > 0:
                                    rows_by_step[step_id] = row_count
                                    summary.rows_in += row_count

                        if "rows_written" in event:
                            summary.rows_out += event["rows_written"]

                        # Track tables
                        if "table" in event:
                            tables_seen.add(event["table"])

                        # Track warnings/errors
                        level = event.get("level", "").lower()
                        if level == "warning":
                            summary.warnings += 1
                        elif level == "error":
                            summary.errors += 1

                        # Extract pipeline metadata from OML events
                        if event_type == "oml_validated":
                            summary.oml_version = event.get("oml_version")
                            if "pipeline" in event:
                                summary.pipeline_name = event["pipeline"].get("name")

                    except (json.JSONDecodeError, KeyError):
                        continue  # Skip invalid events

            # Use cleanup_complete total_rows if available (most accurate for E2B)
            if cleanup_total_rows is not None:
                summary.rows_out = cleanup_total_rows

                # Diagnostic: check for potential double counting
                # If cleanup_total equals sum of all step rows and we have writer steps
                if rows_by_step:
                    total_all_steps = sum(rows_by_step.values())
                    # Check if any steps look like writers (simple heuristic)
                    has_writers = any("write" in step_id.lower() for step_id in rows_by_step.keys())
                    if has_writers and cleanup_total_rows == total_all_steps and total_all_steps > 0:
                        # Potential double count detected (cleanup should be writers-only)
                        summary.double_count_hint = True

            # Otherwise, if we have no rows_out but have step data, sum it
            elif summary.rows_out == 0 and rows_by_step:
                # For E2B sessions where writers don't emit rows_written,
                # use the sum of extractor rows as the total
                summary.rows_out = sum(rows_by_step.values())

            summary.tables = sorted(tables_seen)  # Deterministic ordering

        except OSError:
            pass  # Ignore if file can't be read

    def _read_metrics(self, path: Path, summary: SessionSummary) -> None:
        """Read and aggregate metrics.jsonl file."""
        rows_by_step: Dict[str, int] = {}  # Track to avoid duplicates

        try:
            with open(path) as f:
                for line in f:
                    try:
                        metric = json.loads(line.strip())

                        # Handle rows_read metrics with step_id (ignore untagged)
                        if metric.get("metric") == "rows_read" and "step_id" in metric:
                            step_id = metric["step_id"]
                            value = metric.get("value", 0)
                            if step_id not in rows_by_step and value > 0:
                                rows_by_step[step_id] = value
                                summary.rows_in += value

                        # Handle rows_written metrics
                        elif metric.get("metric") == "rows_written":
                            value = metric.get("value", 0)
                            if value > 0:
                                summary.rows_out += value

                        # Aggregate any additional metrics not in events
                        elif "total_rows" in metric:
                            # Use max in case of multiple reports
                            summary.rows_out = max(summary.rows_out, metric["total_rows"])

                    except (json.JSONDecodeError, KeyError):
                        continue

        except OSError:
            pass

    def _read_artifacts(self, path: Path, summary: SessionSummary) -> None:
        """Read artifacts directory for additional metadata."""
        # Count artifacts and track which steps have them
        if not hasattr(summary, "artifacts_count"):
            summary.artifacts_count = 0
        if not hasattr(summary, "steps_with_artifacts"):
            summary.steps_with_artifacts = []

        # Count artifacts per step
        try:
            for step_dir in path.iterdir():
                if step_dir.is_dir():
                    # Count files in this step's directory
                    artifact_files = list(step_dir.glob("*"))
                    if artifact_files:
                        summary.artifacts_count += len([f for f in artifact_files if f.is_file()])
                        if step_dir.name not in summary.steps_with_artifacts:
                            summary.steps_with_artifacts.append(step_dir.name)
        except OSError:
            pass

        # Check for generated OML file (legacy, at artifacts root)
        oml_files = list(path.glob("*.yaml")) + list(path.glob("*.yml"))
        if oml_files:
            # Try to extract pipeline name from OML
            try:
                with open(oml_files[0]) as f:
                    content = f.read()
                    # Simple extraction without full YAML parsing
                    if "name:" in content:
                        lines = content.split("\n")
                        for line in lines:
                            if line.strip().startswith("name:"):
                                name = line.split(":", 1)[1].strip().strip("\"'")
                                if name:
                                    summary.pipeline_name = name
                                break
            except OSError:
                pass

    def redact_text(self, text: str) -> str:
        """Redact sensitive information from text.

        Args:
            text: Text that may contain sensitive information

        Returns:
            Text with sensitive patterns redacted
        """
        for pattern, replacement in self.SENSITIVE_PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    def _merge_remote_data(self, remote_path: Path, summary: SessionSummary) -> None:
        """Merge remote execution data into session summary.

        Args:
            remote_path: Path to remote/ directory
            summary: SessionSummary to update
        """
        # Mark that this was a remote execution (E2B)
        summary.adapter_type = "E2B"
        if not hasattr(summary, "execution_mode"):
            summary.execution_mode = "remote"

        # Look for remote session data (new location: remote/session/)
        session_path = remote_path / "session"
        if session_path.exists():
            # Read remote session events
            remote_events = session_path / "events.jsonl"
            if remote_events.exists():
                try:
                    with open(remote_events) as f:
                        for line in f:
                            try:
                                event = json.loads(line.strip())
                                event_type = event.get("event")

                                # Extract pipeline info from run_start
                                if event_type == "run_start" and "pipeline_id" in event:
                                    summary.pipeline_name = event["pipeline_id"]

                                # Update step counts from remote execution
                                if event_type == "step_complete":
                                    summary.steps_ok += 1
                                elif event_type == "step_error":
                                    summary.steps_failed += 1
                                    summary.errors += 1

                                # Track remote data flow
                                if "rows_read" in event:
                                    summary.rows_in += event["rows_read"]
                                if "rows_written" in event:
                                    summary.rows_out += event["rows_written"]

                            except (json.JSONDecodeError, KeyError):
                                continue
                except OSError:
                    pass

            # Read remote session metrics
            remote_metrics = session_path / "metrics.jsonl"
            if remote_metrics.exists():
                try:
                    with open(remote_metrics) as f:
                        for line in f:
                            try:
                                metric = json.loads(line.strip())
                                if metric.get("metric") == "rows_written":
                                    summary.rows_out += metric.get("value", 0)
                                elif metric.get("metric") == "rows_read":
                                    summary.rows_in += metric.get("value", 0)
                                elif "total_rows" in metric:
                                    summary.rows_out = max(summary.rows_out, metric["total_rows"])
                            except (json.JSONDecodeError, KeyError):
                                continue
                except OSError:
                    pass

            # Read remote session artifacts
            remote_artifacts = session_path / "artifacts"
            if remote_artifacts.exists():
                self._read_artifacts(remote_artifacts, summary)

        # Also check legacy location (remote/events.jsonl) for backward compatibility
        else:
            remote_events = remote_path / "events.jsonl"
            if remote_events.exists():
                try:
                    with open(remote_events) as f:
                        for line in f:
                            try:
                                event = json.loads(line.strip())
                                event_type = event.get("event")

                                # Update step counts from remote execution
                                if event_type == "step_complete":
                                    summary.steps_ok += 1
                                elif event_type == "step_error":
                                    summary.steps_failed += 1
                                    summary.errors += 1

                                # Track remote data flow
                                if "rows_read" in event:
                                    summary.rows_in += event["rows_read"]
                                if "rows_written" in event:
                                    summary.rows_out += event["rows_written"]

                            except (json.JSONDecodeError, KeyError):
                                continue
                except OSError:
                    pass

    def filter_safe_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Filter dictionary to only include whitelisted fields.

        Args:
            data: Dictionary that may contain sensitive fields

        Returns:
            Dictionary with only safe fields
        """
        return {k: v for k, v in data.items() if k in self.WHITELIST_FIELDS}
