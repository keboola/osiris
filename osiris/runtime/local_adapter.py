"""LocalAdapter for executing pipelines in the current environment.

This adapter wraps the existing local execution logic behind the
ExecutionAdapter contract, ensuring identical behavior while providing
a stable execution boundary.
"""

import shutil
import time
from pathlib import Path
from typing import Any, Dict, Set

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

    def __init__(self, verbose: bool = False):
        """Initialize LocalAdapter.

        Args:
            verbose: If True, print step progress to stdout
        """
        self.error_context = ErrorContext(source="local")
        self.verbose = verbose

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

            # Build cfg_index from steps and collect cfg paths
            cfg_index = {}
            cfg_paths: Set[str] = set()
            for step in steps:
                cfg_path = step.get("cfg_path")
                if cfg_path:
                    cfg_paths.add(cfg_path)
                    # Extract step config (without cfg_path itself)
                    step_config = {k: v for k, v in step.items() if k != "cfg_path"}
                    cfg_index[cfg_path] = step_config

            # Store cfg paths for materialization during execute
            self._cfg_paths_to_materialize = cfg_paths
            self._source_manifest_path = plan.get("metadata", {}).get("source_manifest_path")

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

            # Materialize cfg files from source to run session
            self._materialize_cfg_files(prepared, context, manifest_path)

            # Create runner with existing implementation
            runner = RunnerV0(
                manifest_path=str(manifest_path), output_dir=str(context.artifacts_dir)
            )

            # If verbose, print starting message
            if self.verbose:
                print(f"🚀 Executing pipeline with {len(prepared.plan.get('steps', []))} steps")

            # Execute pipeline
            success = runner.run()

            duration = time.time() - start_time

            # If verbose, print step results summary
            if self.verbose:
                # Extract step events from runner
                step_events = [
                    e
                    for e in runner.events
                    if e.get("type") in ["step_start", "step_complete", "step_error"]
                ]
                for event in step_events:
                    event_type = event.get("type")
                    event_data = event.get("data", {})
                    step_id = event_data.get("step_id", "unknown")

                    if event_type == "step_start":
                        print(f"  ▶ {step_id}: Starting...")
                    elif event_type == "step_complete":
                        rows_read = event_data.get("rows_read", 0)
                        rows_written = event_data.get("rows_written", 0)
                        if rows_read > 0:
                            print(f"  ✓ {step_id}: Complete (read {rows_read} rows)")
                        elif rows_written > 0:
                            print(f"  ✓ {step_id}: Complete (wrote {rows_written} rows)")
                        else:
                            print(f"  ✓ {step_id}: Complete")
                    elif event_type == "step_error":
                        error = event_data.get("error", "Unknown error")
                        print(f"  ✗ {step_id}: Failed - {error}")

                print(f"Pipeline {'completed' if success else 'failed'} in {duration:.2f}s")
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

    def _materialize_cfg_files(
        self, prepared: PreparedRun, context: ExecutionContext, manifest_path: Path
    ) -> None:
        """Materialize cfg files from source to run session.

        Args:
            prepared: Prepared execution details
            context: Execution context
            manifest_path: Path where manifest was written
        """
        # Get cfg paths from prepared run
        cfg_paths = getattr(self, "_cfg_paths_to_materialize", set())
        if not cfg_paths:
            return

        # Determine source location
        # Try to find compiled cfg location from context or environment
        source_base = None

        # Option 1: Check if we have source_manifest_path in metadata
        if self._source_manifest_path:
            source_base = Path(self._source_manifest_path).parent
        # Option 2: Check for --last-compile pattern
        elif "last_compile_dir" in prepared.metadata:
            source_base = Path(prepared.metadata["last_compile_dir"]) / "compiled"
        # Option 3: Look for most recent compile session
        else:
            # Find most recent compile session
            logs_parent = context.logs_dir.parent
            compile_dirs = sorted(
                [d for d in logs_parent.glob("compile_*") if d.is_dir()],
                key=lambda x: x.stat().st_mtime,
                reverse=True,
            )
            if compile_dirs:
                source_base = compile_dirs[0] / "compiled"

        if not source_base or not source_base.exists():
            raise PrepareError(
                "Cannot find source location for cfg files. "
                "Expected compiled manifest directory but found none. "
                "Ensure compilation was successful before running."
            )

        # Create cfg directory in run session
        run_cfg_dir = manifest_path.parent / "cfg"
        run_cfg_dir.mkdir(parents=True, exist_ok=True)

        # Copy each cfg file
        missing_cfgs = []
        for cfg_path in sorted(cfg_paths):
            source_cfg = source_base / cfg_path
            if not source_cfg.exists():
                missing_cfgs.append(str(cfg_path))
                continue

            # Preserve relative structure
            dest_cfg = run_cfg_dir / Path(cfg_path).name

            # Read, potentially transform, and write
            # For now, just copy as-is (no secrets should be in cfg files per ADR-0020)
            shutil.copy2(source_cfg, dest_cfg)

            log_event(
                "cfg_materialized",
                cfg_path=cfg_path,
                source=str(source_cfg),
                destination=str(dest_cfg),
            )

        if missing_cfgs:
            raise PrepareError(
                f"Missing configuration files required by manifest:\n"
                f"{chr(10).join('  - ' + cfg for cfg in missing_cfgs)}\n\n"
                f"The adapter's prepare() phase materializes cfg files into the run session. "
                f"Ensure the source cfg exists at compile location or fix the manifest. "
                f"Searched in: {source_base}/cfg/\n"
                f"See docs/milestones/m1e-e2b-runner.md (PreparedRun cfg_index)."
            )
