"""ExecutionAdapter contract for stable execution boundary.

This module defines the core contract for pipeline execution adapters,
ensuring remote runs never drift from local execution. The adapter pattern
provides a stable boundary between compilation and execution phases.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class PreparedRun:
    """Deterministic execution package with no embedded secrets.

    This structure contains everything needed for execution except
    for actual secret values, which are injected at runtime via
    environment variables.
    """

    # Canonical compiled manifest as JSON dict
    plan: dict[str, Any]

    # Connection descriptors with secret placeholders only
    # Format: {"@mysql.db_movies": {"type": "mysql", "host": "localhost", "password": "${MYSQL_PASSWORD}"}}
    resolved_connections: dict[str, dict[str, Any]]

    # Map of cfg/*.json paths to normalized step configurations
    # Format: {"cfg/step1.json": {"query": "SELECT * FROM table1", "connection": "@mysql.db_movies"}}
    cfg_index: dict[str, dict[str, Any]]

    # Relative paths for logs and artifacts layout
    io_layout: dict[str, str]

    # Runtime parameters
    run_params: dict[str, Any]

    # Execution limits and policies
    constraints: dict[str, Any]

    # Execution metadata
    metadata: dict[str, Any]

    # Source directory for compiled assets (manifest, cfg files)
    # Used for manifest-relative cfg resolution
    compiled_root: str | None = None


@dataclass
class ExecResult:
    """Result of pipeline execution."""

    # Success/failure status
    success: bool

    # Exit code (0 = success, >0 = error)
    exit_code: int

    # Execution duration in seconds
    duration_seconds: float

    # Error message if failed
    error_message: str | None = None

    # Step-level results
    step_results: dict[str, Any] | None = None


@dataclass
class CollectedArtifacts:
    """Artifacts collected after execution."""

    # Paths to collected files
    events_log: Path | None = None
    metrics_log: Path | None = None
    execution_log: Path | None = None
    artifacts_dir: Path | None = None

    # Artifact metadata
    metadata: dict[str, Any] | None = None


class ExecutionContext:
    """Context for execution operations."""

    def __init__(self, session_id: str, base_path: Path):
        self.session_id = session_id
        self.base_path = base_path
        self.started_at = datetime.utcnow()

    @property
    def logs_dir(self) -> Path:
        """Directory for execution logs."""
        # If base_path is already a session directory, use it directly
        # Patterns: "run_*", "compile_*" (legacy), or "*_run-*" (FilesystemContract)
        base_name = self.base_path.name
        if (
            base_name.startswith("run_")
            or base_name.startswith("compile_")
            or "_run-" in base_name  # FilesystemContract pattern
            or "run_logs" in str(self.base_path)  # Inside run_logs/ hierarchy
        ):
            return self.base_path
        # Otherwise, create session subdirectory (legacy compatibility)
        return self.base_path / "logs" / self.session_id

    @property
    def artifacts_dir(self) -> Path:
        """Directory for execution artifacts."""
        # Artifacts go in base_path/artifacts (no session segment)
        return self.base_path / "artifacts"


class ExecutionAdapter(ABC):
    """Abstract base class for pipeline execution adapters.

    This contract ensures that local and remote execution produce
    identical results and maintain the same event/metrics schema.
    """

    @abstractmethod
    def prepare(self, plan: dict[str, Any], context: ExecutionContext) -> PreparedRun:
        """Prepare execution package from compiled manifest.

        Args:
            plan: Canonical compiled manifest JSON
            context: Execution context with session info

        Returns:
            PreparedRun with deterministic execution package

        Note:
            Must not embed any secret values in the PreparedRun.
            Secrets are injected at runtime via environment variables.
        """

    @abstractmethod
    def execute(self, prepared: PreparedRun, context: ExecutionContext) -> ExecResult:
        """Execute prepared pipeline.

        Args:
            prepared: Prepared execution package
            context: Execution context

        Returns:
            ExecResult with execution status and metrics
        """

    @abstractmethod
    def collect(self, prepared: PreparedRun, context: ExecutionContext) -> CollectedArtifacts:
        """Collect execution artifacts after run.

        Args:
            prepared: Prepared execution package
            context: Execution context

        Returns:
            CollectedArtifacts with paths to logs and outputs
        """


class ExecutionAdapterError(Exception):
    """Base exception for execution adapter errors."""

    pass


class PrepareError(ExecutionAdapterError):
    """Error during execution preparation."""

    pass


class ExecuteError(ExecutionAdapterError):
    """Error during pipeline execution."""

    pass


class CollectError(ExecutionAdapterError):
    """Error during artifact collection."""

    pass
