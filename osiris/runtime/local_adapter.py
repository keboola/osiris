"""LocalAdapter for executing pipelines in the current environment.

This adapter wraps the existing local execution logic behind the
ExecutionAdapter contract, ensuring identical behavior while providing
a stable execution boundary.
"""

import json
from pathlib import Path
import shutil
import time
from typing import Any

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

    def prepare(self, plan: dict[str, Any], context: ExecutionContext) -> PreparedRun:
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
            cfg_paths: set[str] = set()
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

            # Determine compiled_root for manifest-relative cfg resolution
            compiled_root = None
            if self._source_manifest_path:
                # For --manifest execution, compiled_root is the manifest's parent directory
                manifest_path = Path(self._source_manifest_path).resolve()
                compiled_root = str(manifest_path.parent)

            # Setup I/O layout for local execution
            io_layout = {
                "logs_dir": str(context.logs_dir),
                "artifacts_dir": str(context.artifacts_dir),
                "manifest_path": str(context.logs_dir / "manifest.yaml"),
            }

            # Extract connection descriptors from cfg files for env var detection
            resolved_connections = self._extract_connection_descriptors(cfg_index)

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
                compiled_root=compiled_root,
            )

        except Exception as e:
            raise PrepareError(f"Failed to prepare local execution: {e}") from e

    def execute(self, prepared: PreparedRun, context: ExecutionContext) -> ExecResult:  # noqa: PLR0915
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

            # Run preflight validation for cfg files
            self._preflight_validate_cfg_files(prepared, context)

            # Materialize cfg files from source to run session
            self._materialize_cfg_files(prepared, context, manifest_path)

            # Track step metadata for totals calculation
            step_rows = {}  # step_id -> rows count
            step_driver_names = {}  # step_id -> driver name

            # Set up verbose event streaming if enabled
            original_log_event = None
            original_log_metric = None
            if self.verbose:
                print(f"🚀 Executing pipeline with {len(prepared.plan.get('steps', []))} steps")
                print(f"📁 Artifacts base: {context.artifacts_dir}")

                # Monkey-patch session logging to intercept events in real-time
                from .. import core

                original_log_event = core.session_logging.log_event
                original_log_metric = core.session_logging.log_metric

                def verbose_log_event(event_name: str, **kwargs):
                    # Call original function first
                    original_log_event(event_name, **kwargs)

                    # Stream to stdout immediately with [local] prefix
                    if event_name == "step_start":
                        step_id = kwargs.get("step_id", "unknown")
                        driver = kwargs.get("driver", "")
                        print(f"[local]   ▶ {step_id}: Starting... (driver: {driver})", flush=True)
                        # Track driver for classification
                        if step_id != "unknown" and driver:
                            step_driver_names[step_id] = driver
                    elif event_name == "step_complete":
                        step_id = kwargs.get("step_id", "unknown")
                        duration = kwargs.get("duration", 0)
                        # Check for rows in kwargs (from step_complete event)
                        rows = (
                            kwargs.get("rows_read", 0)
                            or kwargs.get("rows_written", 0)
                            or kwargs.get("rows_processed", 0)
                        )
                        if rows > 0:
                            print(
                                f"[local]   ✓ {step_id}: Complete (duration: {duration:.2f}s, rows: {rows})",
                                flush=True,
                            )
                            # Track rows for totals
                            if step_id != "unknown":
                                step_rows[step_id] = rows
                        else:
                            print(
                                f"[local]   ✓ {step_id}: Complete (duration: {duration:.2f}s)",
                                flush=True,
                            )
                    elif event_name == "step_error":
                        step_id = kwargs.get("step_id", "unknown")
                        error = kwargs.get("error", "Unknown error")
                        print(f"[local]   ✗ {step_id}: Failed - {error}", flush=True)
                    elif event_name == "connection_resolve_start":
                        step_id = kwargs.get("step_id", "unknown")
                        family = kwargs.get("family", "unknown")
                        alias = kwargs.get("alias", "default")
                        print(
                            f"[local]   🔌 {step_id}: Resolving {family} connection ({alias})",
                            flush=True,
                        )
                    elif event_name == "run_start":
                        pipeline_id = kwargs.get("pipeline_id", "unknown")
                        print(f"[local]   🎯 Pipeline: {pipeline_id}", flush=True)

                def verbose_log_metric(metric: str, value, **kwargs):
                    # Call original function first
                    original_log_metric(metric, value, **kwargs)

                    # Stream metrics to stdout
                    if metric == "rows_read":
                        step_id = kwargs.get("step_id") or kwargs.get("step", "unknown")
                        print(f"[local]   📊 {step_id}: Read {value} rows", flush=True)
                        # Track read rows for extractors
                        if step_id != "unknown" and step_id not in step_rows:
                            step_rows[step_id] = value
                    elif metric == "rows_written":
                        step_id = kwargs.get("step_id") or kwargs.get("step", "unknown")
                        print(f"[local]   📊 {step_id}: Wrote {value} rows", flush=True)
                        # Track written rows (overwrites read if present)
                        if step_id != "unknown":
                            step_rows[step_id] = value
                            # Mark as writer
                            if step_id not in step_driver_names:
                                step_driver_names[step_id] = f"{step_id}.writer"
                    elif metric == "rows_processed":
                        step_id = kwargs.get("step_id") or kwargs.get("step", "unknown")
                        print(f"[local]   📊 {step_id}: Processed {value} rows", flush=True)

                # Apply monkey-patch
                core.session_logging.log_event = verbose_log_event
                core.session_logging.log_metric = verbose_log_metric

            # Create runner with existing implementation
            runner = RunnerV0(manifest_path=str(manifest_path), output_dir=str(context.artifacts_dir))

            try:
                # Execute pipeline
                success = runner.run()

                # Also collect rows from runner events for any we missed
                if hasattr(runner, "events"):
                    for event in runner.events:
                        if event.get("type") == "step_complete":
                            step_id = event.get("data", {}).get("step_id")
                            driver = event.get("data", {}).get("driver", "")
                            if step_id and driver and step_id not in step_driver_names:
                                step_driver_names[step_id] = driver
                            # Get rows from event data if not already tracked
                            if step_id and step_id not in step_rows:
                                rows = (
                                    event.get("data", {}).get("rows_written", 0)
                                    or event.get("data", {}).get("rows_read", 0)
                                    or event.get("data", {}).get("rows_processed", 0)
                                )
                                if rows > 0:
                                    step_rows[step_id] = rows

            finally:
                # Restore original functions if we patched them
                if original_log_event:
                    from .. import core

                    core.session_logging.log_event = original_log_event
                if original_log_metric:
                    core.session_logging.log_metric = original_log_metric

            duration = time.time() - start_time

            # Also read from metrics.jsonl for any rows_written we missed
            metrics_file = context.logs_dir / "metrics.jsonl"
            if metrics_file.exists():
                try:
                    with open(metrics_file) as f:
                        for line in f:
                            try:
                                metric = json.loads(line.strip())
                                if metric.get("metric") == "rows_written":
                                    step_id = metric.get("step_id") or metric.get("step")
                                    value = metric.get("value", 0)
                                    if value > 0 and step_id:
                                        step_rows[step_id] = value
                                        # Infer it's a writer if we have rows_written metric
                                        if step_id not in step_driver_names:
                                            step_driver_names[step_id] = f"{step_id}.writer"
                            except json.JSONDecodeError:
                                continue
                except OSError:
                    pass

            # Calculate totals like E2B does: writers if any, else extractors
            sum_rows_written = 0
            sum_rows_read = 0

            for step_id, rows in step_rows.items():
                driver_name = step_driver_names.get(step_id, "")
                if ".writer" in driver_name or "write" in step_id.lower() or "load" in step_id.lower():
                    sum_rows_written += rows
                elif ".extractor" in driver_name or "extract" in step_id.lower() or "read" in step_id.lower():
                    sum_rows_read += rows
                else:
                    # Ambiguous step - for now count as extractor
                    sum_rows_read += rows

            final_total_rows = sum_rows_written if sum_rows_written > 0 else sum_rows_read

            # Emit cleanup_complete event with total_rows (matching E2B)
            log_event(
                "cleanup_complete",
                steps_executed=len(prepared.plan.get("steps", [])),
                total_rows=final_total_rows,
            )

            if self.verbose:
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
                        error_message = event.get("data", {}).get("error", "Unknown execution error")
                        break
                if not error_message:
                    error_message = "Pipeline execution failed"

                # Log error with taxonomy
                error_event = self.error_context.handle_error(
                    error_message, step_id=getattr(runner, "last_step_id", None)
                )
                # Don't unpack error_event as it contains an 'event' key
                log_event("execution_error_mapped", error_details=error_event)

            # Generate status.json for parity with E2B execution
            steps_total = len(prepared.plan.get("steps", []))
            steps_completed = len([e for e in getattr(runner, "events", []) if e.get("type") == "step_complete"])

            # Check if events.jsonl exists in session logs
            events_jsonl_exists = False
            try:
                import glob

                session_patterns = [
                    str(context.logs_dir / "run_*" / "events.jsonl"),
                    str(Path(".") / "logs" / "run_*" / "events.jsonl"),
                ]
                for pattern in session_patterns:
                    if glob.glob(pattern):
                        events_jsonl_exists = True
                        break
            except Exception:  # nosec B110
                pass

            # Generate status.json with four-proof rule
            status_ok = success and exit_code == 0 and steps_completed == steps_total and events_jsonl_exists

            status_reason = ""
            if not status_ok:
                if not success or exit_code != 0:
                    status_reason = "execution_failed"
                elif steps_completed != steps_total:
                    status_reason = "incomplete_steps"
                elif not events_jsonl_exists:
                    status_reason = "missing_events_jsonl"
                else:
                    status_reason = "unknown"

            status_data = {
                "sandbox_id": "local",
                "exit_code": exit_code,
                "steps_completed": steps_completed,
                "steps_total": steps_total,
                "ok": status_ok,
                "session_path": "local",
                "session_copied": True,
                "events_jsonl_exists": events_jsonl_exists,
                "reason": status_reason,
            }

            # Write status.json to logs directory for consistency
            status_file = context.logs_dir / "status.json"
            try:
                with open(status_file, "w") as f:
                    json.dump(status_data, f, indent=2)
            except Exception:  # nosec B110
                pass

            log_event(
                "execute_complete" if success else "execute_error",
                adapter="local",
                success=success,
                duration=duration,
                steps_executed=steps_completed,
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

    def collect(self, prepared: PreparedRun, context: ExecutionContext) -> CollectedArtifacts:  # noqa: ARG002
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
                "artifacts_count": (len(list(artifacts_dir.iterdir())) if artifacts_dir.exists() else 0),
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

    def _preflight_validate_cfg_files(self, prepared: PreparedRun, context: ExecutionContext) -> None:
        """Validate that all required cfg files exist before execution.

        Args:
            prepared: Prepared execution details
            context: Execution context

        Raises:
            ExecuteError: If any required cfg files are missing
        """
        import logging
        import os

        # Get cfg paths from prepared run
        cfg_paths = getattr(self, "_cfg_paths_to_materialize", set())
        if not cfg_paths:
            return

        run_cfg_dir = context.logs_dir / "cfg"

        # If cfg files are already materialized alongside the prepared manifest,
        # treat this as success. This enables self-contained runs where callers
        # copy compiled assets directly into the session directory.
        if run_cfg_dir.exists():
            missing_in_run = [cfg_path for cfg_path in cfg_paths if not (run_cfg_dir / Path(cfg_path).name).exists()]
            if not missing_in_run:
                log_event(
                    "preflight_validation_success",
                    adapter="local",
                    cfg_files_count=len(cfg_paths),
                    source_base=str(run_cfg_dir),
                    session_id=context.session_id,
                )
                return

        # Determine source location using same logic as _materialize_cfg_files
        source_base = None

        # For --manifest execution: use cleaner resolution without legacy session hunting
        if prepared.compiled_root:
            # Option 1: Use PreparedRun.compiled_root (set from --manifest)
            source_base = Path(prepared.compiled_root)
        else:
            # Option 2: OSIRIS_COMPILED_ROOT environment variable
            compiled_root_env = os.environ.get("OSIRIS_COMPILED_ROOT")
            if compiled_root_env:
                potential_base = Path(compiled_root_env)
                if potential_base.exists():
                    source_base = potential_base

        # Option 3: Fallback to legacy session hunting (for --last-compile compatibility)
        if not source_base:
            # Check if we have source_manifest_path in metadata
            if self._source_manifest_path:
                source_base = Path(self._source_manifest_path).parent
            # Check for --last-compile pattern
            elif "last_compile_dir" in prepared.metadata:
                source_base = Path(prepared.metadata["last_compile_dir"]) / "compiled"
            # Look for most recent compile session
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
            error_msg = "Cannot find source location for cfg files during preflight validation"

            # Log to both osiris.log and events.jsonl
            logger = logging.getLogger("osiris.runtime.local_adapter")
            logger.error(error_msg)
            log_event(
                "preflight_validation_error",
                adapter="local",
                error=error_msg,
                session_id=context.session_id,
            )

            raise ExecuteError(error_msg)

        # Check each cfg file exists
        missing_cfgs = []
        for cfg_path in sorted(cfg_paths):
            source_cfg_found = False

            # Try same resolution order as _materialize_cfg_files
            if (
                (
                    (source_base / cfg_path).exists()
                    or (source_base / "compiled" / cfg_path).exists()
                    or (source_base / Path(cfg_path).name).exists()
                    or (source_base / "cfg" / Path(cfg_path).name).exists()
                )
                or run_cfg_dir.exists()
                and (run_cfg_dir / Path(cfg_path).name).exists()
            ):
                source_cfg_found = True

            if not source_cfg_found:
                missing_cfgs.append(str(cfg_path))

        if missing_cfgs:
            error_msg = (
                f"Preflight validation failed: Missing required cfg files:\\n"
                f"{chr(10).join('  - ' + cfg for cfg in missing_cfgs)}\\n\\n"
                f"Source directory: {source_base}"
            )

            # Log to both osiris.log and events.jsonl
            logger = logging.getLogger("osiris.runtime.local_adapter")
            logger.error(error_msg)
            log_event(
                "preflight_validation_error",
                adapter="local",
                error=error_msg,
                missing_cfgs=missing_cfgs,
                source_base=str(source_base),
                session_id=context.session_id,
            )

            raise ExecuteError(error_msg)

        # Log successful validation
        log_event(
            "preflight_validation_success",
            adapter="local",
            cfg_files_count=len(cfg_paths),
            source_base=str(source_base),
            session_id=context.session_id,
        )

    def _extract_connection_descriptors(self, cfg_index: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Extract connection descriptors from cfg files.

        Args:
            cfg_index: Map of cfg paths to configurations

        Returns:
            Map of connection IDs to connection configurations with env var placeholders
        """
        import yaml

        connection_refs = set()

        # Find all connection references in cfg files
        for _cfg_path, config in cfg_index.items():
            connection = config.get("connection")
            if connection and connection.startswith("@"):
                connection_refs.add(connection)

        if not connection_refs:
            return {}

        # Load connection configurations
        try:
            connections_file = Path("osiris_connections.yaml")
            if not connections_file.exists():
                # Try in current directory or parent directories
                for parent in [Path("."), Path("..")]:
                    candidate = parent / "osiris_connections.yaml"
                    if candidate.exists():
                        connections_file = candidate
                        break

            if not connections_file.exists():
                log_event(
                    "connection_config_not_found",
                    adapter="local",
                    message="osiris_connections.yaml not found, env var detection may be incomplete",
                )
                return {}

            with open(connections_file) as f:
                connections_config = yaml.safe_load(f)

            resolved_connections = {}

            # Resolve each connection reference
            for connection_ref in connection_refs:
                # Parse @family.alias format
                if not connection_ref.startswith("@"):
                    continue

                parts = connection_ref[1:].split(".", 1)  # Remove @ prefix and split
                if len(parts) != 2:
                    continue

                family, alias = parts
                connection_config = connections_config.get("connections", {}).get(family, {}).get(alias)

                if connection_config:
                    # Store with the full reference as key
                    resolved_connections[connection_ref] = connection_config.copy()

            return resolved_connections

        except Exception as e:
            log_event("connection_resolution_error", adapter="local", error=str(e))
            return {}

    def _materialize_cfg_files(self, prepared: PreparedRun, context: ExecutionContext, manifest_path: Path) -> None:
        """Materialize cfg files from source to run session.

        Args:
            prepared: Prepared execution details
            context: Execution context
            manifest_path: Path where manifest was written
        """
        import os

        # Get cfg paths from prepared run
        cfg_paths = getattr(self, "_cfg_paths_to_materialize", set())
        if not cfg_paths:
            return

        run_cfg_dir = manifest_path.parent / "cfg"

        # Determine source location with clean manifest-relative resolution
        source_base = None
        pre_materialized_base = None

        # Tests and some compilers may pre-materialize cfg files and pass the
        # directory via PreparedRun metadata. Prefer that when present so we do
        # not fail just because the compiled manifest tree is absent.
        metadata_cfg_dir = (
            prepared.metadata.get("materialized_cfg_dir") if isinstance(prepared.metadata, dict) else None
        )
        if not metadata_cfg_dir:
            metadata_cfg_dir = (
                prepared.plan.get("metadata", {}).get("materialized_cfg_dir")
                if isinstance(prepared.plan, dict)
                else None
            )
        if metadata_cfg_dir:
            candidate = Path(metadata_cfg_dir).expanduser()
            if candidate.exists():
                pre_materialized_base = candidate

        # For --manifest execution: use cleaner resolution without legacy session hunting
        if prepared.compiled_root:
            # Option 1: Use PreparedRun.compiled_root (set from --manifest)
            source_base = Path(prepared.compiled_root)
        else:
            # Option 2: OSIRIS_COMPILED_ROOT environment variable
            compiled_root_env = os.environ.get("OSIRIS_COMPILED_ROOT")
            if compiled_root_env:
                potential_base = Path(compiled_root_env)
                if potential_base.exists():
                    source_base = potential_base

        # Option 3: Fallback to legacy session hunting (for --last-compile compatibility)
        if not source_base:
            # Check if we have source_manifest_path in metadata
            if self._source_manifest_path:
                source_base = Path(self._source_manifest_path).parent
            # Check for --last-compile pattern
            elif "last_compile_dir" in prepared.metadata:
                source_base = Path(prepared.metadata["last_compile_dir"]) / "compiled"
            # Look for most recent compile session
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

        # Option 4: pre-materialized cfg directory supplied in metadata
        if not source_base and pre_materialized_base:
            source_base = pre_materialized_base
            log_event(
                "cfg_pre_materialized_used",
                adapter="local",
                path=str(source_base),
                session_id=context.session_id,
            )

        if not source_base or not source_base.exists():
            # Allow callers (tests, prepared manifests) to pre-provide cfg files directly
            # in the run directory. If every required cfg already exists, skip copying.
            existing_ok = True
            if not run_cfg_dir.exists():
                existing_ok = False
            else:
                for cfg_path in sorted(cfg_paths):
                    if not (run_cfg_dir / Path(cfg_path).name).exists():
                        existing_ok = False
                        break

            if existing_ok:
                log_event(
                    "cfg_pre_materialized_used",
                    adapter="local",
                    path=str(run_cfg_dir),
                    session_id=context.session_id,
                    source="run_dir",
                )
                return

            raise PrepareError(
                "Cannot find source location for cfg files. "
                "Expected compiled manifest directory but found none. "
                "Ensure compilation was successful before running."
            )

        # Create cfg directory in run session
        run_cfg_dir.mkdir(parents=True, exist_ok=True)

        # Copy each cfg file using clean resolution order
        missing_cfgs = []
        for cfg_path in sorted(cfg_paths):
            source_cfg = None

            # Try resolution order as specified:
            # 1. compiled_root / rel_path
            if (source_base / cfg_path).exists():
                source_cfg = source_base / cfg_path
            # 2. Legacy fallback patterns for compatibility
            elif (source_base / "compiled" / cfg_path).exists():
                source_cfg = source_base / "compiled" / cfg_path
            # 2b. Direct file inside supplied directory (pre-materialized cfg dir)
            elif (source_base / Path(cfg_path).name).exists():
                source_cfg = source_base / Path(cfg_path).name
            # 3. Direct cfg directory (for some legacy structures)
            elif (source_base / "cfg" / Path(cfg_path).name).exists():
                source_cfg = source_base / "cfg" / Path(cfg_path).name

            if not source_cfg:
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
