"""E2BAdapter for executing pipelines in E2B sandboxes.

This adapter provides remote execution via E2B Code Interpreter sandboxes,
implementing the ExecutionAdapter contract while reusing existing E2B
prototype infrastructure.
"""

import contextlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

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
from ..core.session_logging import log_event, log_metric
from .e2b_client import E2BClient
from .e2b_pack import PayloadBuilder, RunConfig


class E2BAdapter(ExecutionAdapter):
    """E2B remote execution adapter.

    This adapter executes pipelines in isolated E2B sandboxes, providing
    the same interface as local execution while ensuring complete isolation
    and reproducible remote execution.
    """

    def __init__(self, e2b_config: Optional[Dict[str, Any]] = None):
        """Initialize E2B adapter.

        Args:
            e2b_config: E2B configuration (timeout, cpu, memory, etc.)
        """
        self.e2b_config = e2b_config or {}
        self.client = None
        self.sandbox_handle = None
        self.error_context = ErrorContext(source="remote")

    def prepare(self, plan: Dict[str, Any], context: ExecutionContext) -> PreparedRun:
        """Prepare E2B execution package.

        Args:
            plan: Canonical compiled manifest JSON
            context: Execution context

        Returns:
            PreparedRun configured for E2B execution
        """
        try:
            log_event("e2b_prepare_start", session_id=context.session_id)

            # Extract metadata from plan
            pipeline_info = plan.get("pipeline", {})
            steps = plan.get("steps", [])

            # Build cfg_index from steps for payload building
            cfg_index = {}
            for step in steps:
                cfg_path = step.get("cfg_path")
                if cfg_path:
                    # Extract step config (without cfg_path itself)
                    step_config = {k: v for k, v in step.items() if k != "cfg_path"}
                    cfg_index[cfg_path] = step_config

            # Setup I/O layout for remote execution
            remote_logs_dir = context.logs_dir / "remote"
            io_layout = {
                "remote_logs_dir": str(remote_logs_dir),
                "local_artifacts_dir": str(context.artifacts_dir),
                "remote_work_dir": "/home/user",
                "remote_artifacts_dir": "/home/user/artifacts",
            }

            # For E2B, resolved_connections will contain secret placeholders
            # that get resolved via environment injection
            resolved_connections = self._extract_connection_descriptors(plan)

            # If no connections in manifest metadata, extract from step configs
            if not resolved_connections:
                resolved_connections = self._extract_connections_from_steps(plan, cfg_index)

            # E2B runtime parameters
            run_params = {
                "timeout": self.e2b_config.get("timeout", 900),
                "cpu": self.e2b_config.get("cpu", 2),
                "memory_gb": self.e2b_config.get("memory", 4),
                "env_vars": self.e2b_config.get("env", {}),
                "verbose": self.e2b_config.get("verbose", False),
            }

            # E2B execution constraints
            constraints = {
                "max_duration_seconds": run_params["timeout"],
                "max_memory_mb": run_params["memory_gb"] * 1024,
                "max_disk_mb": 10 * 1024,  # 10GB disk limit
            }

            # Execution metadata
            metadata = {
                "session_id": context.session_id,
                "created_at": context.started_at.isoformat(),
                "adapter_target": "e2b",
                "compiler_fingerprint": plan.get("metadata", {}).get("fingerprint"),
                "pipeline_name": pipeline_info.get("name", "unknown"),
                "pipeline_id": pipeline_info.get("id", "unknown"),
                "e2b_config": {
                    "timeout": run_params["timeout"],
                    "cpu": run_params["cpu"],
                    "memory_gb": run_params["memory_gb"],
                },
            }

            log_event(
                "e2b_prepare_complete",
                session_id=context.session_id,
                cfg_files=len(cfg_index),
                constraints=constraints,
            )

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
            log_event("e2b_prepare_error", session_id=context.session_id, error=str(e))
            raise PrepareError(f"Failed to prepare E2B execution: {e}") from e

    def execute(self, prepared: PreparedRun, context: ExecutionContext) -> ExecResult:
        """Execute prepared pipeline in E2B sandbox.

        Args:
            prepared: Prepared execution package
            context: Execution context

        Returns:
            ExecResult with remote execution status
        """
        try:
            log_event("e2b_execute_start", session_id=context.session_id)
            start_time = time.time()

            # Build and upload payload using existing infrastructure
            if prepared.run_params.get("verbose"):
                print("🔨 Building E2B payload...")

            log_event("e2b_payload_build", session_id=context.session_id)
            payload_path = self._build_payload(prepared, context)

            log_event(
                "e2b_payload_built",
                session_id=context.session_id,
                payload_path=str(payload_path),
                manifest_steps=len(prepared.plan.get("steps", [])),
            )

            if prepared.run_params.get("verbose"):
                print(f"✓ Payload built ({len(prepared.plan.get('steps', []))} steps)")

            # Create E2B client
            api_key = os.environ.get("E2B_API_KEY")
            if not api_key:
                raise ExecuteError("E2B_API_KEY environment variable not set")

            self.client = E2BClient()

            # Create sandbox
            if prepared.run_params.get("verbose"):
                print("🚀 Creating E2B sandbox...")

            log_event("e2b_sandbox_create", session_id=context.session_id)
            self.sandbox_handle = self.client.create_sandbox(
                cpu=prepared.run_params["cpu"],
                mem_gb=prepared.run_params["memory_gb"],
                env=prepared.run_params["env_vars"],
                timeout=prepared.run_params["timeout"],
            )

            if prepared.run_params.get("verbose"):
                print(
                    f"✓ Sandbox created (CPU: {prepared.run_params['cpu']}, Memory: {prepared.run_params['memory_gb']}GB)"
                )

            log_event("e2b_payload_upload", session_id=context.session_id)
            if prepared.run_params.get("verbose"):
                print("📤 Uploading payload to sandbox...")
            self.client.upload_payload(self.sandbox_handle, payload_path)
            if prepared.run_params.get("verbose"):
                print("✓ Payload uploaded")

            # Start execution in sandbox
            log_event("e2b_execution_start", session_id=context.session_id)
            if prepared.run_params.get("verbose"):
                print("🏃 Starting pipeline execution in sandbox...")

            command = ["python", "mini_runner.py"]
            process_id = self.client.start(self.sandbox_handle, command)

            # Poll for completion
            log_event("e2b_execution_poll", session_id=context.session_id, process_id=process_id)

            if prepared.run_params.get("verbose"):
                print("⏳ Waiting for remote execution to complete...")
                # For now, we show a simple waiting message
                # In the future, we could poll for intermediate results

            final_status = self.client.poll_until_complete(
                self.sandbox_handle,
                process_id,
                timeout_s=prepared.run_params["timeout"],
            )

            if prepared.run_params.get("verbose"):
                if final_status.status.value == "success":
                    print("✓ Remote execution completed successfully")
                else:
                    print("✗ Remote execution failed")

            duration = time.time() - start_time
            log_metric("e2b_execution_duration", duration, unit="seconds")

            # Determine success
            success = final_status.status.value == "success"
            exit_code = final_status.exit_code or (0 if success else 1)

            # If failed, map error with taxonomy
            if not success and final_status.stderr:
                error_event = self.error_context.handle_error(
                    final_status.stderr, step_id="e2b_execution"
                )
                # Don't unpack error_event as it contains an 'event' key
                log_event("e2b_error_mapped", error_details=error_event)

            log_event(
                "e2b_execute_complete" if success else "e2b_execute_error",
                session_id=context.session_id,
                success=success,
                exit_code=exit_code,
                duration=duration,
                stdout=final_status.stdout,
                stderr=final_status.stderr,
            )

            return ExecResult(
                success=success,
                exit_code=exit_code,
                duration_seconds=duration,
                error_message=final_status.stderr if not success else None,
                step_results={
                    "process_id": process_id,
                    "final_status": final_status.status.value,
                    "stdout": final_status.stdout,
                    "stderr": final_status.stderr,
                },
            )

        except Exception as e:
            duration = time.time() - start_time if "start_time" in locals() else 0
            error_msg = f"E2B execution failed: {e}"

            # Map error with taxonomy
            error_event = self.error_context.handle_error(
                error_msg, exception=e, step_id="e2b_execution"
            )

            log_event(
                "e2b_execute_error",
                session_id=context.session_id,
                error=error_msg,
                duration=duration,
                error_details=error_event,
            )

            raise ExecuteError(error_msg) from e

        finally:
            # Clean up sandbox (best effort)
            if self.client and self.sandbox_handle:
                with contextlib.suppress(Exception):
                    self.client.close(self.sandbox_handle)

    def collect(self, prepared: PreparedRun, context: ExecutionContext) -> CollectedArtifacts:
        """Collect execution artifacts from E2B sandbox.

        Args:
            prepared: Prepared execution package
            context: Execution context

        Returns:
            CollectedArtifacts with paths to remote logs and outputs
        """
        try:
            log_event("e2b_collect_start", session_id=context.session_id)

            if not self.client or not self.sandbox_handle:
                raise CollectError("No active E2B session to collect from")

            # Create remote logs directory
            remote_logs_dir = Path(prepared.io_layout["remote_logs_dir"])
            remote_logs_dir.mkdir(parents=True, exist_ok=True)

            # Download artifacts from sandbox
            log_event("e2b_artifacts_download", session_id=context.session_id)
            self.client.download_artifacts(self.sandbox_handle, remote_logs_dir)

            # Tag downloaded files with remote source
            self._tag_remote_artifacts(remote_logs_dir, context.session_id)

            # Locate collected files
            events_log = remote_logs_dir / "events.jsonl"
            metrics_log = remote_logs_dir / "metrics.jsonl"
            execution_log = remote_logs_dir / "osiris.log"
            artifacts_dir = remote_logs_dir / "artifacts"

            # Collect metadata
            metadata = {
                "adapter": "e2b",
                "session_id": context.session_id,
                "collected_at": time.time(),
                "source": "remote",
                "sandbox_id": self.sandbox_handle.sandbox_id,
            }

            # Add file sizes if files exist
            collected_files = {}
            for name, path in [
                ("events_log", events_log),
                ("metrics_log", metrics_log),
                ("execution_log", execution_log),
                ("artifacts_dir", artifacts_dir),
            ]:
                if path.exists():
                    collected_files[name] = path
                    if path.is_file():
                        metadata[f"{name}_size"] = path.stat().st_size
                    elif path.is_dir():
                        metadata[f"{name}_count"] = len(list(path.iterdir()))

            log_event(
                "e2b_collect_complete",
                session_id=context.session_id,
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
            error_msg = f"Failed to collect E2B artifacts: {e}"
            log_event("e2b_collect_error", session_id=context.session_id, error=error_msg)
            raise CollectError(error_msg) from e

    def _extract_connection_descriptors(
        self, plan: Dict[str, Any]  # noqa: ARG002
    ) -> Dict[str, Dict[str, Any]]:
        """Extract connection descriptors with secret placeholders.

        This extracts connection references from the manifest and prepares them
        for injection into the PreparedRun. The actual resolution happens at
        compile time and the resolved connections (with placeholders) are
        stored in the manifest.
        """
        # Extract resolved connections from the manifest metadata
        # These are prepared during compilation with secret placeholders
        resolved_connections = {}

        # Check if manifest has resolved_connections in metadata
        metadata = plan.get("metadata", {})
        if "resolved_connections" in metadata:
            resolved_connections = metadata["resolved_connections"]

        # Also check for connections in pipeline metadata (older format)
        pipeline_meta = plan.get("pipeline", {}).get("metadata", {})
        if "connections" in pipeline_meta:
            resolved_connections.update(pipeline_meta["connections"])

        return resolved_connections

    def _build_payload(self, prepared: PreparedRun, context: ExecutionContext) -> Path:
        """Build E2B execution payload using existing infrastructure."""
        # Create temporary manifest file with resolved connections in metadata
        manifest_with_connections = prepared.plan.copy()
        if prepared.resolved_connections:
            if "metadata" not in manifest_with_connections:
                manifest_with_connections["metadata"] = {}
            manifest_with_connections["metadata"][
                "resolved_connections"
            ] = prepared.resolved_connections

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.safe_dump(manifest_with_connections, f, default_flow_style=False)
            temp_manifest = Path(f.name)

        try:
            # Find the source cfg directory from the original manifest
            source_cfg_dir = None
            if "metadata" in prepared.plan and "source_manifest_path" in prepared.plan["metadata"]:
                source_manifest = Path(prepared.plan["metadata"]["source_manifest_path"])
                if source_manifest.exists():
                    # cfg files are in compiled/cfg relative to manifest
                    source_cfg_dir = source_manifest.parent / "cfg"

            # If we couldn't find it from metadata, try to find the latest compile dir
            if not source_cfg_dir or not source_cfg_dir.exists():
                base_logs = context.base_path / "logs"
                if base_logs.exists():
                    compile_dirs = sorted(
                        [d for d in base_logs.iterdir() if d.name.startswith("compile_")],
                        key=lambda x: x.name,
                        reverse=True,
                    )
                    if compile_dirs:
                        source_cfg_dir = compile_dirs[0] / "compiled" / "cfg"

            # Create payload builder using existing infrastructure
            build_dir = context.logs_dir / "e2b_build"
            build_dir.mkdir(parents=True, exist_ok=True)

            builder = PayloadBuilder(context.logs_dir, build_dir)
            run_config = RunConfig()

            # Build payload with source cfg directory
            payload_path = builder.build(
                temp_manifest,
                run_config,
                source_cfg_dir=(
                    source_cfg_dir if source_cfg_dir and source_cfg_dir.exists() else None
                ),
            )

            log_event(
                "e2b_payload_built",
                session_id=context.session_id,
                payload_path=str(payload_path),
                manifest_steps=len(prepared.plan.get("steps", [])),
            )

            return payload_path

        finally:
            # Clean up temporary manifest
            if temp_manifest.exists():
                temp_manifest.unlink()

    def _tag_remote_artifacts(self, remote_dir: Path, session_id: str):  # noqa: ARG002
        """Tag remote artifacts with source metadata."""
        # Add source:"remote" to events and metrics files
        for log_file in ["events.jsonl", "metrics.jsonl"]:
            log_path = remote_dir / log_file
            if log_path.exists():
                self._tag_jsonl_file(log_path, {"source": "remote"})

    def _tag_jsonl_file(self, file_path: Path, tags: Dict[str, Any]):
        """Add tags to each line in a JSONL file."""
        try:
            lines = []
            with open(file_path) as f:
                for line in f:
                    if line.strip():
                        try:
                            data = json.loads(line)
                            data.update(tags)
                            lines.append(json.dumps(data) + "\n")
                        except json.JSONDecodeError:
                            lines.append(line)  # Keep malformed lines as-is

            # Write back with tags
            with open(file_path, "w") as f:
                f.writelines(lines)

        except Exception:
            # Best effort - don't fail collection if tagging fails
            pass  # nosec B110

    def _extract_connections_from_steps(
        self, plan: Dict[str, Any], cfg_index: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """Extract connection references from step configurations.

        This is a fallback when connections aren't in manifest metadata.
        It builds connection descriptors from step configs that reference connections.

        Args:
            plan: The manifest plan
            cfg_index: Map of cfg_path to step config
        """
        from ..core.config import resolve_connection

        connections = {}
        steps = plan.get("steps", [])

        for step in steps:
            # Check step config for connection reference
            cfg_path = step.get("cfg_path")
            if cfg_path and cfg_path in cfg_index:
                step_config = cfg_index[cfg_path]
                connection_ref = step_config.get("connection")

                if connection_ref and connection_ref.startswith("@"):
                    # Parse connection reference
                    if "." in connection_ref[1:]:
                        family, alias = connection_ref[1:].split(".", 1)
                    else:
                        # Infer family from component name
                        component = step.get("component", "")
                        family = component.split(".")[0] if "." in component else "unknown"
                        alias = connection_ref[1:]

                    # Resolve connection to get descriptor with placeholders
                    # Note: This will have actual values, we need to convert to placeholders
                    try:
                        resolved = resolve_connection(family, alias)
                        # Replace actual secrets with placeholders
                        placeholder_conn = {}
                        for key, value in resolved.items():
                            if key in ["password", "key", "token", "secret", "service_role_key"]:
                                # Convert to placeholder based on common patterns
                                if family == "mysql" and key == "password":
                                    placeholder_conn[key] = "${MYSQL_PASSWORD}"
                                elif family == "supabase" and key == "service_role_key":
                                    placeholder_conn[key] = "${SUPABASE_SERVICE_ROLE_KEY}"
                                else:
                                    # Generic placeholder
                                    placeholder_conn[key] = f"${{{family.upper()}_{key.upper()}}}"
                            else:
                                placeholder_conn[key] = value

                        connections[connection_ref] = placeholder_conn
                    except Exception as e:
                        log_event(
                            "connection_resolution_skipped",
                            connection=connection_ref,
                            reason=str(e),
                        )

        return connections
