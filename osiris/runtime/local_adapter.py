"""LocalAdapter for executing pipelines in the current environment.

This adapter wraps the existing local execution logic behind the
ExecutionAdapter contract, ensuring identical behavior while providing
a stable execution boundary.
"""

import time
from pathlib import Path
from typing import Any, Dict

from ..core.error_taxonomy import ErrorContext
from ..core.execution_adapter import (
    CollectedArtifacts,
    CollectError,
    ExecResult,
    ExecuteError,
    ExecutionAdapter,
    ExecutionContext,
    PreparedRun,
    PrepareError,
)
from ..core.runner_v0 import RunnerV0
from ..core.session_logging import log_event, log_metric


class LocalAdapter(ExecutionAdapter):
    """Local execution adapter using current runner implementation.

    This adapter maintains identical behavior to the existing local execution
    while conforming to the ExecutionAdapter contract.
    """

    def __init__(self):
        """Initialize LocalAdapter."""
        self.error_context = ErrorContext(source="local")

    def prepare(self, plan: Dict[str, Any], context: ExecutionContext) -> PreparedRun:
        """Prepare local execution package.

        Args:
            plan: Canonical compiled manifest JSON
            context: Execution context

        Returns:
            PreparedRun with local execution configuration
        """
        try:
            # Extract metadata from plan
            pipeline_info = plan.get("pipeline", {})
            steps = plan.get("steps", [])

            # Build cfg_index from steps
            cfg_index = {}
            for step in steps:
                cfg_path = step.get("cfg_path")
                if cfg_path:
                    # Extract step config (without cfg_path itself)
                    step_config = {k: v for k, v in step.items() if k != "cfg_path"}
                    cfg_index[cfg_path] = step_config

            # Setup I/O layout for local execution
            io_layout = {
                "logs_dir": str(context.logs_dir),
                "artifacts_dir": str(context.artifacts_dir),
                "manifest_path": str(context.logs_dir / "manifest.yaml"),
            }

            # Local execution uses environment resolution - no secret placeholders needed
            # Connection resolution will happen at runtime via existing mechanisms
            resolved_connections = {}

            # Runtime parameters
            run_params = {
                "profile": True,  # Enable profiling metrics by default
                "verbose": False,
                "timeout": None,
            }

            # No special constraints for local execution
            constraints = {
                "max_duration_seconds": None,
                "max_memory_mb": None,
                "max_disk_mb": None,
            }

            # Execution metadata
            metadata = {
                "session_id": context.session_id,
                "created_at": context.started_at.isoformat(),
                "adapter_target": "local",
                "compiler_fingerprint": plan.get("metadata", {}).get("fingerprint"),
                "pipeline_name": pipeline_info.get("name", "unknown"),
                "pipeline_id": pipeline_info.get("id", "unknown"),
            }

            return PreparedRun(
                plan=plan,
                resolved_connections=resolved_connections,
                cfg_index=cfg_index,
                io_layout=io_layout,
                run_params=run_params,
                constraints=constraints,
                metadata=metadata,
            )

        except Exception as e:
            raise PrepareError(f"Failed to prepare local execution: {e}") from e

    def execute(self, prepared: PreparedRun, context: ExecutionContext) -> ExecResult:
        """Execute prepared pipeline locally.

        Args:
            prepared: Prepared execution package
            context: Execution context

        Returns:
            ExecResult with execution status
        """
        try:
            log_event("execute_start", adapter="local", session_id=context.session_id)
            start_time = time.time()

            # Ensure directories exist
            context.logs_dir.mkdir(parents=True, exist_ok=True)
            context.artifacts_dir.mkdir(parents=True, exist_ok=True)

            # Write manifest to expected location
            manifest_path = Path(prepared.io_layout["manifest_path"])
            manifest_path.parent.mkdir(parents=True, exist_ok=True)

            with open(manifest_path, "w") as f:
                import yaml

                yaml.safe_dump(prepared.plan, f, default_flow_style=False)

            # Create runner with existing implementation
            runner = RunnerV0(
                manifest_path=str(manifest_path), output_dir=str(context.artifacts_dir)
            )

            # Execute pipeline
            success = runner.run()

            duration = time.time() - start_time
            log_metric("execution_duration", duration, unit="seconds")

            # Determine exit code
            exit_code = 0 if success else 1

            # Extract step results if available
            step_results = {}
            if hasattr(runner, "results"):
                step_results = runner.results

            # Get error message if failed
            error_message = None
            if not success:
                # Try to extract error from recent events
                recent_events = getattr(runner, "events", [])
                for event in reversed(recent_events):
                    if event.get("type") == "step_error":
                        error_message = event.get("data", {}).get(
                            "error", "Unknown execution error"
                        )
                        break
                if not error_message:
                    error_message = "Pipeline execution failed"

                # Log error with taxonomy
                error_event = self.error_context.handle_error(
                    error_message, step_id=getattr(runner, "last_step_id", None)
                )
                # Don't unpack error_event as it contains an 'event' key
                log_event("execution_error_mapped", error_details=error_event)

            log_event(
                "execute_complete" if success else "execute_error",
                adapter="local",
                success=success,
                duration=duration,
                steps_executed=len(
                    [e for e in getattr(runner, "events", []) if e.get("type") == "step_complete"]
                ),
                error=error_message if not success else None,
            )

            return ExecResult(
                success=success,
                exit_code=exit_code,
                duration_seconds=duration,
                error_message=error_message,
                step_results=step_results,
            )

        except Exception as e:
            duration = time.time() - start_time if "start_time" in locals() else 0
            error_msg = f"Local execution failed: {e}"

            log_event(
                "execute_error",
                adapter="local",
                error=error_msg,
                duration=duration,
            )

            raise ExecuteError(error_msg) from e

    def collect(
        self, prepared: PreparedRun, context: ExecutionContext  # noqa: ARG002
    ) -> CollectedArtifacts:
        """Collect execution artifacts after local run.

        Args:
            prepared: Prepared execution package
            context: Execution context

        Returns:
            CollectedArtifacts with paths to logs and outputs
        """
        try:
            log_event("collect_start", adapter="local", session_id=context.session_id)

            # Locate standard artifact files
            events_log = context.logs_dir / "events.jsonl"
            metrics_log = context.logs_dir / "metrics.jsonl"
            execution_log = context.logs_dir / "osiris.log"
            artifacts_dir = context.artifacts_dir

            # Verify files exist
            collected_files = {}
            if events_log.exists():
                collected_files["events_log"] = events_log
            if metrics_log.exists():
                collected_files["metrics_log"] = metrics_log
            if execution_log.exists():
                collected_files["execution_log"] = execution_log
            if artifacts_dir.exists() and artifacts_dir.is_dir():
                collected_files["artifacts_dir"] = artifacts_dir

            # Collect metadata about artifacts
            metadata = {
                "adapter": "local",
                "session_id": context.session_id,
                "collected_at": time.time(),
                "artifacts_count": (
                    len(list(artifacts_dir.iterdir())) if artifacts_dir.exists() else 0
                ),
            }

            # Add file sizes if files exist
            for file_type, file_path in collected_files.items():
                if file_type != "artifacts_dir" and file_path.exists():
                    metadata[f"{file_type}_size"] = file_path.stat().st_size

            log_event(
                "collect_complete",
                adapter="local",
                artifacts_collected=len(collected_files),
                metadata=metadata,
            )

            return CollectedArtifacts(
                events_log=collected_files.get("events_log"),
                metrics_log=collected_files.get("metrics_log"),
                execution_log=collected_files.get("execution_log"),
                artifacts_dir=collected_files.get("artifacts_dir"),
                metadata=metadata,
            )

        except Exception as e:
            error_msg = f"Failed to collect local artifacts: {e}"
            log_event("collect_error", adapter="local", error=error_msg)
            raise CollectError(error_msg) from e
