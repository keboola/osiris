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

        try:
            with open(path) as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())
                        event_type = event.get("event")

                        # Track steps
                        if event_type == "step_start":
                            step_id = event.get("step_id")
                            if step_id and step_id not in steps_seen:
                                steps_seen.add(step_id)
                                summary.steps_total += 1

                        elif event_type == "step_complete":
                            summary.steps_ok += 1

                        elif event_type == "step_error":
                            summary.steps_failed += 1
                            summary.errors += 1

                        # Track data flow
                        if "rows_read" in event:
                            summary.rows_in += event["rows_read"]
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

            summary.tables = sorted(tables_seen)  # Deterministic ordering

        except OSError:
            pass  # Ignore if file can't be read

    def _read_metrics(self, path: Path, summary: SessionSummary) -> None:
        """Read and aggregate metrics.jsonl file."""
        try:
            with open(path) as f:
                for line in f:
                    try:
                        metric = json.loads(line.strip())

                        # Aggregate any additional metrics not in events
                        if "total_rows" in metric:
                            # Use max in case of multiple reports
                            summary.rows_out = max(summary.rows_out, metric["total_rows"])

                    except (json.JSONDecodeError, KeyError):
                        continue

        except OSError:
            pass

    def _read_artifacts(self, path: Path, summary: SessionSummary) -> None:
        """Read artifacts directory for additional metadata."""
        # Check for generated OML file
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

    def filter_safe_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Filter dictionary to only include whitelisted fields.

        Args:
            data: Dictionary that may contain sensitive fields

        Returns:
            Dictionary with only safe fields
        """
        return {k: v for k, v in data.items() if k in self.WHITELIST_FIELDS}
