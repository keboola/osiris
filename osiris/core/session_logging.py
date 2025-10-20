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

"""Session-scoped logging and artifacts management.

This module implements per-session logging directories with structured events,
metrics, and artifact collection for better debugging and audit capabilities.
"""

from contextlib import suppress
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import sys
import tempfile
import time
from typing import Any
import uuid

from .redaction import create_redactor


class SessionContext:
    """Manages session-scoped logging and artifact collection."""

    def __init__(
        self,
        session_id: str | None = None,
        base_logs_dir: Path | None = None,
        allowed_events: list[str] | None = None,
        privacy_level: str | None = None,
        fs_contract=None,
        pipeline_slug: str | None = None,
        profile: str | None = None,
        run_id: str | None = None,
        run_ts: datetime | None = None,
        manifest_short: str | None = None,
    ):
        """Initialize session context.

        Args:
            session_id: Unique session identifier. Generated if None.
            base_logs_dir: Base directory for logs (only used if fs_contract not provided).
            allowed_events: List of event types to log. Use ["*"] or None for all events.
            privacy_level: Privacy level for redaction (standard or strict). Uses env var if None.
            fs_contract: Optional FilesystemContract for path resolution.
            pipeline_slug: Pipeline identifier (used with fs_contract).
            profile: Profile name (used with fs_contract).
            run_id: Run identifier (used with fs_contract).
            run_ts: Run timestamp (used with fs_contract).
            manifest_short: Short manifest hash (used with fs_contract).
        """
        self.session_id = session_id or self._generate_session_id()
        self.start_time = datetime.now(UTC)
        self.redactor = create_redactor(privacy_level)
        self.fs_contract = fs_contract

        # Event filtering: None or ["*"] means log all events
        self.allowed_events = allowed_events or ["*"]

        # Set up paths based on whether we have a filesystem contract
        if fs_contract and pipeline_slug and run_id and manifest_short:
            # Use filesystem contract paths
            paths = fs_contract.run_log_paths(
                pipeline_slug=pipeline_slug,
                run_id=run_id,
                run_ts=run_ts or self.start_time,
                manifest_short=manifest_short,
                profile=profile,
            )
            self.session_dir = paths["base"]
            self.osiris_log = paths["osiris_log"]
            self.debug_log = paths["debug_log"]
            self.events_log = paths["events"]
            self.metrics_log = paths["metrics"]
            self.artifacts_dir = paths["artifacts"]

            # These don't have specific paths in contract, put in session dir
            self.manifest_file = self.session_dir / "manifest.json"
            self.config_file = self.session_dir / "cfg.json"
            self.fingerprints_file = self.session_dir / "fingerprints.json"
        else:
            # Legacy path mode - DEPRECATED, will be removed
            self.base_logs_dir = base_logs_dir or Path("run_logs")  # Changed default from logs to run_logs
            self.session_dir = self.base_logs_dir / self.session_id

            # File paths
            self.osiris_log = self.session_dir / "osiris.log"
            self.debug_log = self.session_dir / "debug.log"
            self.events_log = self.session_dir / "events.jsonl"
            self.metrics_log = self.session_dir / "metrics.jsonl"
            self.manifest_file = self.session_dir / "manifest.json"
            self.config_file = self.session_dir / "cfg.json"
            self.fingerprints_file = self.session_dir / "fingerprints.json"
            self.artifacts_dir = self.session_dir / "artifacts"

        # Logging handlers
        self._handlers: list[logging.Handler] = []
        self._fallback_temp_dir: Path | None = None

        # Initialize session directory
        self._setup_session_directory()

        # Log session start
        self.log_event(
            "run_start",
            session_id=self.session_id,
            session_dir=str(self.session_dir),
            fallback_used=self._fallback_temp_dir is not None,
        )

    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        # Use timestamp + short uuid for readability
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_uuid = str(uuid.uuid4())[:8]
        return f"{timestamp}_{short_uuid}"

    def _setup_session_directory(self) -> None:
        """Create session directory and handle permission errors gracefully."""
        try:
            self.session_dir.mkdir(parents=True, exist_ok=True)
            self.artifacts_dir.mkdir(exist_ok=True)
        except (OSError, PermissionError):
            # Fallback to temp directory with warning
            self._fallback_temp_dir = Path(tempfile.mkdtemp(prefix=f"osiris-session-{self.session_id}-"))
            self.session_dir = self._fallback_temp_dir
            self.artifacts_dir = self.session_dir / "artifacts"
            with suppress(OSError, PermissionError):
                self.artifacts_dir.mkdir(exist_ok=True)

            # Update all file paths to use temp directory
            self.osiris_log = self.session_dir / "osiris.log"
            self.debug_log = self.session_dir / "debug.log"
            self.events_log = self.session_dir / "events.jsonl"
            self.metrics_log = self.session_dir / "metrics.jsonl"
            self.manifest_file = self.session_dir / "manifest.json"
            self.config_file = self.session_dir / "cfg.json"
            self.fingerprints_file = self.session_dir / "fingerprints.json"

            # Log warning about fallback (to stderr since logging may not be configured yet)
            import sys

            print(
                f"WARNING: Could not create logs directory {self.base_logs_dir / self.session_id}, "
                f"using temporary directory: {self.session_dir}",
                file=sys.stderr,
            )

            # Emit structured event about the fallback
            self.log_event(
                "cache_error",
                error="permission_denied",
                original_path=str(self.base_logs_dir / self.session_id),
                fallback_path=str(self.session_dir),
            )

    def setup_logging(self, level: int = logging.INFO, enable_debug: bool = False) -> None:
        """Set up logging handlers for the session.

        Args:
            level: Logging level for main log file
            enable_debug: Whether to create separate debug log file
        """
        # Clear any existing handlers
        self.cleanup_logging()

        # Set root logger level to ensure messages propagate
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG if enable_debug else level)

        # Main session log (INFO/WARN/ERROR)
        try:
            main_handler = logging.FileHandler(self.osiris_log)
            main_handler.setLevel(level)

            # Create a secure formatter that masks sensitive data
            class SecureFormatter(logging.Formatter):
                def format(self, record):
                    # Format the message normally first
                    msg = super().format(record)
                    # Then mask any sensitive information in the entire message
                    # Use legacy string masking for log files (not structured data)
                    from .secrets_masking import mask_sensitive_string

                    return mask_sensitive_string(msg)

            main_formatter = SecureFormatter(
                "%(asctime)s - %(name)s - [%(session_id)s] - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            main_handler.setFormatter(main_formatter)
            self._handlers.append(main_handler)

            # Add session_id to all log records
            class SessionFilter(logging.Filter):
                def __init__(self, session_id: str):
                    self.session_id = session_id

                def filter(self, record):
                    record.session_id = self.session_id
                    return True

            session_filter = SessionFilter(self.session_id)
            main_handler.addFilter(session_filter)

            # Add to root logger
            logging.getLogger().addHandler(main_handler)

        except (OSError, PermissionError) as e:
            print(f"WARNING: Could not create main log handler: {e}", file=sys.stderr)

        # Optional debug log (DEBUG only)
        if enable_debug:
            try:
                debug_handler = logging.FileHandler(self.debug_log)
                debug_handler.setLevel(logging.DEBUG)
                debug_formatter = SecureFormatter(
                    "%(asctime)s - %(name)s - [%(session_id)s] - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
                debug_handler.setFormatter(debug_formatter)
                debug_handler.addFilter(SessionFilter(self.session_id))
                self._handlers.append(debug_handler)

                # Add to root logger
                logging.getLogger().addHandler(debug_handler)

            except (OSError, PermissionError) as e:
                print(f"WARNING: Could not create debug log handler: {e}", file=sys.stderr)

    def cleanup_logging(self) -> None:
        """Remove all session-specific logging handlers."""
        root_logger = logging.getLogger()
        for handler in self._handlers:
            # Flush before closing to ensure all data is written
            handler.flush()
            root_logger.removeHandler(handler)
            handler.close()
        self._handlers.clear()

    def log_event(self, event_name: str, **kwargs) -> None:
        """Log a structured event to events.jsonl.

        Args:
            event_name: Event type (cache_hit, cache_miss, run_start, etc.)
            **kwargs: Additional event data
        """
        # Event filtering: skip if not in allowed events (unless wildcard "*" is used)
        if "*" not in self.allowed_events and event_name not in self.allowed_events:
            return
        try:
            event_data = {
                "ts": datetime.now(UTC).isoformat(),
                "session": self.session_id,
                "event": event_name,
                **kwargs,
            }

            # Redact sensitive data using new redactor
            event_data = self.redactor.redact_dict(event_data)

            # Convert non-serializable objects to strings
            def make_serializable(obj):
                if isinstance(obj, dict):
                    return {k: make_serializable(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [make_serializable(item) for item in obj]
                elif isinstance(obj, str | int | float | bool) or obj is None:
                    return obj
                else:
                    return str(obj)

            event_data = make_serializable(event_data)

            # Write to events.jsonl
            with open(self.events_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(event_data, separators=(",", ":")) + "\n")
                f.flush()  # Ensure data is written immediately

        except (OSError, PermissionError) as e:
            # Fallback to stderr if we can't write events
            print(f"WARNING: Could not write event {event_name}: {e}", file=sys.stderr)
        except (TypeError, ValueError) as e:
            # JSON serialization error
            print(f"WARNING: Could not serialize event {event_name}: {e}", file=sys.stderr)

    def log_metric(self, metric: str, value: Any, **kwargs) -> None:
        """Log a metric to metrics.jsonl.

        Args:
            metric: Metric name (duration_ms, row_count, etc.)
            value: Metric value
            **kwargs: Additional metric metadata
        """
        try:
            metric_data = {
                "ts": datetime.now(UTC).isoformat(),
                "session": self.session_id,
                "metric": metric,
                "value": value,
                **kwargs,
            }

            # Redact sensitive data using new redactor
            metric_data = self.redactor.redact_dict(metric_data)

            # Convert non-serializable objects to strings
            def make_serializable(obj):
                if isinstance(obj, dict):
                    return {k: make_serializable(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [make_serializable(item) for item in obj]
                elif isinstance(obj, str | int | float | bool) or obj is None:
                    return obj
                else:
                    return str(obj)

            metric_data = make_serializable(metric_data)

            # Write to metrics.jsonl
            with open(self.metrics_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(metric_data, separators=(",", ":")) + "\n")
                f.flush()  # Ensure data is written immediately

        except (OSError, PermissionError) as e:
            # Fallback to stderr if we can't write metrics
            print(f"WARNING: Could not write metric {metric}: {e}", file=sys.stderr)
        except (TypeError, ValueError) as e:
            # JSON serialization error
            print(f"WARNING: Could not serialize metric {metric}: {e}", file=sys.stderr)

    def save_config(self, config: dict[str, Any]) -> None:
        """Save configuration to cfg.json (with secrets masked).

        Args:
            config: Configuration dictionary to save
        """
        try:
            masked_config = self.redactor.redact_dict(config)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(masked_config, f, indent=2)
        except (OSError, PermissionError) as e:
            print(f"WARNING: Could not save config: {e}", file=sys.stderr)

    def save_manifest(self, manifest: dict[str, Any]) -> None:
        """Save run manifest to manifest.json (with secrets masked).

        Args:
            manifest: Run manifest dictionary to save
        """
        try:
            masked_manifest = self.redactor.redact_dict(manifest)
            with open(self.manifest_file, "w", encoding="utf-8") as f:
                json.dump(masked_manifest, f, indent=2)
        except (OSError, PermissionError) as e:
            print(f"WARNING: Could not save manifest: {e}", file=sys.stderr)

    def save_fingerprints(self, fingerprints: dict[str, Any]) -> None:
        """Save fingerprint data to fingerprints.json.

        Args:
            fingerprints: Fingerprint data dictionary
        """
        try:
            with open(self.fingerprints_file, "w", encoding="utf-8") as f:
                json.dump(fingerprints, f, indent=2)
        except (OSError, PermissionError) as e:
            print(f"WARNING: Could not save fingerprints: {e}", file=sys.stderr)

    def save_artifact(self, name: str, content: Any, content_type: str = "text") -> Path | None:
        """Save an artifact to the artifacts directory.

        Args:
            name: Artifact name (will be used as filename)
            content: Artifact content
            content_type: Content type ("text", "json", "binary")

        Returns:
            Path to saved artifact, or None if failed
        """
        try:
            artifact_path = self.artifacts_dir / name

            if content_type == "json":
                masked_content = self.redactor.redact_dict(content) if isinstance(content, dict) else content
                with open(artifact_path, "w", encoding="utf-8") as f:
                    json.dump(masked_content, f, indent=2)
            elif content_type == "text":
                with open(artifact_path, "w", encoding="utf-8") as f:
                    f.write(str(content))
            elif content_type == "binary":
                with open(artifact_path, "wb") as f:
                    f.write(content)
            else:
                raise ValueError(f"Unknown content_type: {content_type}")

            return artifact_path

        except (OSError, PermissionError) as e:
            print(f"WARNING: Could not save artifact {name}: {e}", file=sys.stderr)
            return None

    def close(self) -> None:
        """Close the session and log session end."""
        end_time = datetime.now(UTC)
        duration_seconds = (end_time - self.start_time).total_seconds()

        self.log_event("run_end", duration_seconds=duration_seconds, end_time=end_time.isoformat())

        self.log_metric("session_duration_seconds", duration_seconds)

        # Clean up logging handlers
        self.cleanup_logging()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if exc_type:
            self.log_event("run_error", error_type=exc_type.__name__, error_message=str(exc_val))
        self.close()


# Global session context (thread-local would be better for multi-threading)
_current_session: SessionContext | None = None


def get_current_session() -> SessionContext | None:
    """Get the current active session context."""
    return _current_session


def set_current_session(session: SessionContext | None) -> None:
    """Set the current active session context."""
    global _current_session
    _current_session = session


def clear_current_session() -> None:
    """Clear the current session context."""
    global _current_session
    _current_session = None


def log_event(event_name: str, **kwargs) -> None:
    """Log an event to the current session (if active)."""
    if _current_session:
        _current_session.log_event(event_name, **kwargs)


def log_metric(metric: str, value: Any, **kwargs) -> None:
    """Log a metric to the current session (if active)."""
    if _current_session:
        _current_session.log_metric(metric, value, **kwargs)


def create_ephemeral_session(command: str = "unknown") -> SessionContext:
    """Create an ephemeral session for CLI commands that don't normally have sessions.

    Args:
        command: Command name for session identification

    Returns:
        New session context
    """
    session_id = f"ephemeral_{command}_{int(time.time())}"
    return SessionContext(session_id=session_id)
