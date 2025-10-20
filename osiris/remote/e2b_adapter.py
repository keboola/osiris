"""E2BAdapter for executing pipelines in E2B sandboxes.

This adapter provides remote execution via E2B Code Interpreter sandboxes,
implementing the ExecutionAdapter contract while reusing existing E2B
prototype infrastructure.
"""

import contextlib
import json
import logging
import os
from pathlib import Path
import time
from typing import Any

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
from .e2b_full_pack import build_full_payload, get_required_env_vars

logger = logging.getLogger(__name__)


class E2BAdapter(ExecutionAdapter):
    """E2B remote execution adapter.

    This adapter executes pipelines in isolated E2B sandboxes, providing
    the same interface as local execution while ensuring complete isolation
    and reproducible remote execution.
    """

    def __init__(self, e2b_config: dict[str, Any] | None = None):
        """Initialize E2B adapter.

        Args:
            e2b_config: E2B configuration (timeout, cpu, memory, etc.)
        """
        self.e2b_config = e2b_config or {}
        self.client = None
        self.sandbox_handle = None
        self.error_context = ErrorContext(source="remote")

    def prepare(self, plan: dict[str, Any], context: ExecutionContext) -> PreparedRun:
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

            # Build cfg_index by loading actual cfg files for payload building and env detection
            cfg_index = {}
            source_manifest_path = plan.get("metadata", {}).get("source_manifest_path")

            for step in steps:
                cfg_path = step.get("cfg_path")
                if cfg_path:
                    # Load actual cfg file content for connection detection
                    try:
                        cfg_content = self._load_cfg_file(cfg_path, source_manifest_path)
                        if cfg_content:
                            cfg_index[cfg_path] = cfg_content
                        else:
                            # File doesn't exist (e.g., in tests) - use step config
                            cfg_index[cfg_path] = {
                                "id": step.get("id"),
                                "driver": step.get("driver"),
                                "config": step.get("config", {}),
                            }
                    except Exception as e:
                        log_event(
                            "cfg_load_warning",
                            cfg_path=cfg_path,
                            error=str(e),
                            session_id=context.session_id,
                        )
                        # Fallback to step config on error
                        # Include essential fields for contract compliance
                        cfg_index[cfg_path] = {
                            "id": step.get("id"),
                            "driver": step.get("driver"),
                            "config": step.get("config", {}),
                        }

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
            payload_path = build_full_payload(prepared, context.logs_dir)

            # Debug: Show payload info
            import hashlib

            payload_size = payload_path.stat().st_size
            with open(payload_path, "rb") as f:
                payload_sha256 = hashlib.sha256(f.read()).hexdigest()
            print(f"[DEBUG] Payload built: {payload_path}")
            print(f"[DEBUG] Payload size: {payload_size} bytes")
            print(f"[DEBUG] Payload SHA256: {payload_sha256}")

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

            if prepared.run_params.get("verbose"):
                print(
                    f"🔧 Creating E2B sandbox (CPU: {prepared.run_params['cpu']}, Memory: {prepared.run_params['memory_gb']}GB)..."
                )

            self.sandbox_handle = self.client.create_sandbox(
                cpu=prepared.run_params["cpu"],
                mem_gb=prepared.run_params["memory_gb"],
                env=prepared.run_params["env_vars"],
                timeout=prepared.run_params["timeout"],
            )

            # We now have a real sandbox ID
            sandbox_id = self.sandbox_handle.sandbox_id

            if prepared.run_params.get("verbose"):
                print(f"✓ Sandbox created with ID: {sandbox_id}")

            log_event("e2b_payload_upload", session_id=context.session_id, sandbox_id=sandbox_id)
            if prepared.run_params.get("verbose"):
                print(f"📤 Uploading payload to sandbox {sandbox_id}...")

            self.client.upload_payload(self.sandbox_handle, payload_path)

            if prepared.run_params.get("verbose"):
                print("✓ Payload uploaded successfully")

            # Prepare environment variables for sandbox with validation
            required_env_vars = get_required_env_vars(prepared)
            sandbox_env = {}
            missing_vars = []

            for var in required_env_vars:
                value = os.environ.get(var)
                if value:
                    sandbox_env[var] = value
                else:
                    missing_vars.append(var)

            # Fail fast if required environment variables are missing
            if missing_vars:
                error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
                if prepared.run_params.get("verbose"):
                    print(f"❌ {error_msg}")
                raise ExecuteError(error_msg)

            # Add E2B sandbox ID to environment
            sandbox_env["E2B_SANDBOX_ID"] = sandbox_id

            if prepared.run_params.get("verbose"):
                print(f"🔑 Passing {len(sandbox_env)} environment variables to sandbox")
                # Only show variable names, never values
                print(f"   Variables: {', '.join(sorted(sandbox_env.keys()))}")

            # Pass environment variables when creating the process
            # The run.sh script will handle dependency installation
            log_event("e2b_execution_start", session_id=context.session_id, sandbox_id=sandbox_id)
            if prepared.run_params.get("verbose"):
                print(f"🏃 Starting full CLI execution in sandbox {sandbox_id}...")

            # Run the full CLI via run.sh with environment variables
            # We need to pass env vars at process creation time
            self.sandbox_handle.metadata["env"] = sandbox_env
            run_cmd = ["bash", "/home/user/payload/run.sh"]
            process_id = self.client.start(self.sandbox_handle, run_cmd)

            if prepared.run_params.get("verbose"):
                print(f"✓ Execution started (process: {process_id})")

            # Get results immediately (no polling needed for synchronous execution)
            log_event("e2b_execution_fetch", session_id=context.session_id, process_id=process_id)

            if prepared.run_params.get("verbose"):
                print("📊 Retrieving execution results...")

            import time as exec_time

            exec_start = exec_time.time()
            final_status = self.client.poll_until_complete(
                self.sandbox_handle,
                process_id,
                timeout_s=prepared.run_params["timeout"],
            )
            exec_duration = exec_time.time() - exec_start

            # Parse execution phases from stdout for better user feedback
            if prepared.run_params.get("verbose") and final_status.stdout:
                self._parse_and_report_execution_phases(final_status.stdout)

            # Show execution summary in verbose mode
            if prepared.run_params.get("verbose") and final_status.stdout:
                # Show last few lines of output
                output_lines = final_status.stdout.strip().split("\n")
                if len(output_lines) > 5:
                    print("📝 Output (last 5 lines):")
                    for line in output_lines[-5:]:
                        print(f"   {line}")
                else:
                    print("📝 Output:")
                    for line in output_lines:
                        print(f"   {line}")

            # Defer stderr display until after status.json classification

            duration = time.time() - start_time
            log_metric("e2b_execution_duration", duration, unit="seconds")

            # Determine success - must check exit code first (non-zero = failure)
            exit_code = final_status.exit_code or 0

            # E2B SDK sometimes doesn't properly expose exit codes, parse from stderr
            import re

            if exit_code == 0 and final_status.stderr:
                exit_code_match = re.search(r"Command exited with code (\d+)", final_status.stderr)
                if exit_code_match:
                    exit_code = int(exit_code_match.group(1))

            success = final_status.status.value == "success" and exit_code == 0

            # Additional error detection for Python errors
            has_python_error = False
            if final_status.stderr:
                error_indicators = [
                    "Traceback",
                    "Error:",
                    "ModuleNotFoundError",
                    "ImportError",
                    "SyntaxError",
                    "NameError",
                    "TypeError",
                    "ValueError",
                ]
                has_python_error = any(indicator in final_status.stderr for indicator in error_indicators)
                if has_python_error:
                    success = False

            # Print execution result in verbose mode
            if prepared.run_params.get("verbose"):
                if success:
                    print("✓ Remote execution completed successfully")
                else:
                    print("✗ Remote execution failed")
                    if exit_code != 0:
                        print(f"   Exit code: {exit_code}")
                    if has_python_error:
                        print("   Python error detected in output")

            # If failed, map error with taxonomy
            if not success and final_status.stderr:
                error_event = self.error_context.handle_error(final_status.stderr, step_id="e2b_execution")
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

            # Always try to collect remote logs, even on failure
            if prepared.run_params.get("verbose"):
                print(f"📥 Downloading execution artifacts from sandbox {sandbox_id}...")

            # Download logs with error handling
            downloaded_count = 0
            try:
                downloaded_count = self._download_remote_logs(context)
                if prepared.run_params.get("verbose"):
                    if downloaded_count > 0:
                        print(f"✓ Downloaded {downloaded_count} log files")
                    else:
                        print("⚠️  No log files were downloaded")
            except Exception as e:
                if prepared.run_params.get("verbose"):
                    print(f"[DEBUG] Failed to download remote logs: {e}")

            # Parse and validate status.json for four-proof rule
            status_json_path = context.logs_dir / "remote" / "status.json"
            status_data = None
            four_proof_success = False

            if status_json_path.exists():
                try:
                    import json

                    with open(status_json_path) as f:
                        status_data = json.load(f)

                    # Apply enhanced four-proof rule validation with session copy check
                    four_proof_success = (
                        status_data.get("ok", False)
                        and status_data.get("exit_code", -1) == 0
                        and status_data.get("steps_completed", 0) == status_data.get("steps_total", -1)
                        and status_data.get("session_copied", False)
                        and status_data.get("events_jsonl_exists", False)
                    )

                    if prepared.run_params.get("verbose"):
                        steps_info = f"({status_data.get('steps_completed', 0)}/{status_data.get('steps_total', 0)})"

                        if four_proof_success:
                            print(f"✓ Four-proof validation passed {steps_info}")

                            # Report session log download details
                            artifacts_count = status_data.get("artifacts_count", 0)
                            events_size = status_data.get("events_jsonl_size", 0)
                            metrics_size = status_data.get("metrics_jsonl_size", 0)

                            log_parts = []
                            if status_data.get("events_jsonl_exists", False):
                                log_parts.append("events.jsonl")
                            if status_data.get("metrics_jsonl_exists", False):
                                log_parts.append("metrics.jsonl")
                            if status_data.get("osiris_log_exists", False):
                                log_parts.append("osiris.log")

                            log_summary = ", ".join(log_parts)
                            if artifacts_count > 0:
                                log_summary += f", artifacts: {artifacts_count}"

                            print(f"✓ Downloaded session logs ({log_summary})")
                        else:
                            # Detailed failure reporting
                            print(f"✗ Four-proof validation failed {steps_info}")

                            # List specific failures
                            failures = []
                            if status_data.get("exit_code", -1) != 0:
                                failures.append(f"exit_code={status_data.get('exit_code', -1)}")
                            if status_data.get("steps_completed", 0) != status_data.get("steps_total", -1):
                                failures.append("incomplete_steps")
                            if not status_data.get("session_copied", False):
                                failures.append("session_not_copied")
                            if not status_data.get("events_jsonl_exists", False):
                                failures.append("missing_events_jsonl")

                            if failures:
                                print(f"   Failed checks: {', '.join(failures)}")

                            reason = status_data.get("reason", "unknown")
                            if reason:
                                print(f"   Reason: {reason}")

                except Exception as e:
                    if prepared.run_params.get("verbose"):
                        print(f"⚠️  Failed to parse status.json: {e}")
            elif prepared.run_params.get("verbose"):
                print("✗ status.json not found - execution invalid")
                print("❌ Log transfer incomplete - missing status.json")
                success = False

            # Verify log transfer completeness if status indicates success
            if (
                status_data
                and status_data.get("ok", False)
                and not all(
                    [
                        status_data.get("session_copied", False),
                        status_data.get("events_jsonl_exists", False),
                        status_data.get("metrics_jsonl_exists", False),
                        status_data.get("osiris_log_exists", False),
                    ]
                )
            ):
                if prepared.run_params.get("verbose"):
                    print("❌ Log transfer incomplete - session files missing")
                    print("   Hint: Check sandbox execution and session copy logic")
                success = False

            # Override success determination with four-proof rule
            success = four_proof_success

            # Display warnings/errors based on classification
            if prepared.run_params.get("verbose"):
                warnings_count = status_data.get("warnings_count", 0) if status_data else 0
                errors_count = status_data.get("errors_count", 0) if status_data else 0

                # If we have status.json with counts, use those
                if status_data and "warnings_count" in status_data:
                    if success and errors_count == 0 and warnings_count > 0:
                        # Show benign warnings on success
                        print(f"⚠️  Warnings from sandbox ({warnings_count}):")
                        stderr_file = context.logs_dir / "remote" / "stderr.txt"
                        if stderr_file.exists():
                            try:
                                stderr_content = stderr_file.read_text()
                                warning_lines = self._extract_warning_lines(stderr_content)
                                for line in warning_lines[-10:]:  # Last 10 warning lines
                                    print(f"   {line}")
                            except Exception as e:
                                logger.warning(f"Failed to read stderr file for warnings: {e}")
                    elif not success or errors_count > 0:
                        # Show errors on failure
                        if final_status.stderr:
                            print("❌ Errors detected:")
                            error_lines = final_status.stderr.strip().split("\n")[:5]
                            for line in error_lines:
                                print(f"   {line}")
                # Fallback to old behavior if status.json lacks counts
                elif final_status.stderr:
                    if success:
                        # Classify manually for backward compatibility
                        if self._has_real_errors(final_status.stderr):
                            print("❌ Errors detected:")
                            error_lines = final_status.stderr.strip().split("\n")[:5]
                            for line in error_lines:
                                print(f"   {line}")
                        elif self._has_warnings(final_status.stderr):
                            print("⚠️  Warnings from sandbox:")
                            warning_lines = self._extract_warning_lines(final_status.stderr)
                            for line in warning_lines[-10:]:
                                print(f"   {line}")
                    else:
                        # Always show stderr on failure
                        print("❌ Errors detected:")
                        error_lines = final_status.stderr.strip().split("\n")[:5]
                        for line in error_lines:
                            print(f"   {line}")

            # Prepare error message for failed executions
            error_msg = None
            if not success:
                remote_logs_path = context.logs_dir / "remote"
                error_msg = f"Remote execution failed in sandbox {sandbox_id}"

                # Include status.json details if available
                if status_data:
                    error_msg += f"\nStatus: {status_data.get('reason', 'unknown')}"
                    error_msg += (
                        f" (steps: {status_data.get('steps_completed', 0)}/{status_data.get('steps_total', 0)})"
                    )
                    error_msg += f", exit_code: {status_data.get('exit_code', 'unknown')}"
                    error_msg += f", events.jsonl: {'yes' if status_data.get('events_jsonl_exists') else 'no'}"

                # Include last 30 lines of stdout if available
                stdout_file = remote_logs_path / "stdout.txt"
                if stdout_file.exists():
                    try:
                        stdout_content = stdout_file.read_text()
                        stdout_lines = stdout_content.strip().split("\n")
                        if stdout_lines and len(stdout_lines) > 0:
                            error_msg += "\nLast 30 lines of stdout:\n"
                            for line in stdout_lines[-30:]:
                                error_msg += f"  {line}\n"
                    except Exception as e:
                        logger.warning(f"Failed to read stdout.txt for error reporting: {e}")
                        error_msg += f"\n(Could not read stdout.txt: {e})\n"

                # Include last 30 lines of stderr if available
                stderr_file = remote_logs_path / "stderr.txt"
                if stderr_file.exists():
                    try:
                        stderr_content = stderr_file.read_text()
                        stderr_lines = stderr_content.strip().split("\n")
                        if stderr_lines and len(stderr_lines) > 0:
                            error_msg += "\nLast 30 lines of stderr:\n"
                            for line in stderr_lines[-30:]:
                                error_msg += f"  {line}\n"
                    except Exception as e:
                        logger.warning(f"Failed to read stderr.txt for error reporting: {e}")
                        error_msg += f"\n(Could not read stderr.txt: {e})\n"
                elif final_status.stderr:
                    # Fallback to process stderr if file not available
                    stderr_lines = final_status.stderr.strip().split("\n")
                    if len(stderr_lines) <= 5:
                        error_msg += f"\nProcess stderr: {final_status.stderr.strip()}"
                    else:
                        error_msg += "\nLast 5 lines of process stderr:\n"
                        for line in stderr_lines[-5:]:
                            error_msg += f"  {line}\n"

                error_msg += f"\nCheck logs at: {remote_logs_path}/"

            return ExecResult(
                success=success,
                exit_code=exit_code,
                duration_seconds=duration,
                error_message=error_msg,
                step_results={
                    "process_id": process_id,
                    "final_status": final_status.status.value,
                    "stdout": final_status.stdout,
                    "stderr": final_status.stderr,
                    "sandbox_id": (
                        self.sandbox_handle.sandbox_id if hasattr(self.sandbox_handle, "sandbox_id") else None
                    ),
                },
            )

        except Exception as e:
            duration = time.time() - start_time if "start_time" in locals() else 0
            error_msg = f"E2B execution failed: {e}"

            # Map error with taxonomy
            error_event = self.error_context.handle_error(error_msg, exception=e, step_id="e2b_execution")

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

    def _format_error_message(self, final_status: Any, context: ExecutionContext) -> str:
        """Format comprehensive error message with stderr excerpt.

        Args:
            final_status: Final execution status
            context: Execution context

        Returns:
            Formatted error message
        """
        base_msg = final_status.stderr or "Remote execution failed"

        # Try to add sandbox ID if available
        sandbox_id = "unknown"
        if hasattr(self.sandbox_handle, "sandbox_id"):
            sandbox_id = self.sandbox_handle.sandbox_id

        msg_parts = [f"Sandbox {sandbox_id}: {base_msg}"]

        # Add last lines of remote stderr if available
        remote_stderr = context.logs_dir / "remote" / "stderr.txt"
        if remote_stderr.exists():
            try:
                with open(remote_stderr) as f:
                    lines = f.readlines()
                    if lines:
                        msg_parts.append("\nLast stderr lines:")
                        for line in lines[-10:]:
                            msg_parts.append(f"  {line.rstrip()}")
            except Exception as e:
                logger.warning(f"Failed to read remote stderr for error formatting: {e}")

        return "\n".join(msg_parts)

    def _download_remote_logs(self, context: ExecutionContext) -> int:
        """Download remote logs from sandbox including full session directory.

        Args:
            context: Execution context

        Returns:
            Number of files downloaded
        """
        if not self.client or not self.sandbox_handle:
            return 0

        # Create remote logs directory
        remote_logs_dir = context.logs_dir / "remote"
        remote_logs_dir.mkdir(parents=True, exist_ok=True)

        # Files to download from sandbox remote directory
        # The run.sh script creates logs in ./remote (relative to /home/user/payload)
        remote_base_path = "/home/user/payload/remote"
        downloaded_count = 0

        # First, download base files: stdout.txt, stderr.txt, diag.txt, and status.json
        base_files = ["stdout.txt", "stderr.txt", "diag.txt", "status.json"]

        for file_name in base_files:
            remote_path = f"{remote_base_path}/{file_name}"
            try:
                content = self.client.download_file(self.sandbox_handle, remote_path)
                if content:
                    (remote_logs_dir / file_name).write_bytes(content)
                    downloaded_count += 1
            except Exception as e:
                # Don't silently pass - log the failure!
                logger.warning(f"Failed to download E2B artifact {file_name}: {e}")
                log_event(
                    "e2b_artifact_download_failed",
                    file_name=file_name,
                    error=str(e),
                    remote_path=remote_path,
                )

        # Download entire session directory recursively
        session_remote_path = f"{remote_base_path}/session"
        session_local_dir = remote_logs_dir / "session"

        def download_directory_recursive(remote_dir: str, local_dir: Path) -> int:
            """Recursively download directory contents."""
            count = 0
            local_dir.mkdir(parents=True, exist_ok=True)

            try:
                # List files in remote directory
                items = self.client.transport.list_files(self.sandbox_handle, remote_dir)

                for item in items or []:
                    # Handle both string names and EntryInfo objects
                    item_str = str(item)

                    # Check if it looks like an EntryInfo string representation
                    if item_str.startswith("EntryInfo("):
                        # Parse the name from the string representation
                        import re

                        name_match = re.search(r"name='([^']+)'", item_str)
                        if name_match:
                            item_name = name_match.group(1)
                            is_dir = "type=<FileType.DIR:" in item_str or "type='dir'" in item_str
                        else:
                            # Fallback
                            item_name = item_str
                            is_dir = False
                    elif hasattr(item, "name"):
                        # It's an actual EntryInfo object
                        item_name = item.name
                        is_dir = hasattr(item, "type") and "dir" in str(item.type).lower()
                    else:
                        # It's a plain string
                        item_name = item_str
                        is_dir = False  # Will detect below

                    remote_item_path = f"{remote_dir}/{item_name}"
                    local_item_path = local_dir / item_name

                    # Determine if it's a file or directory
                    if is_dir:
                        # We know it's a directory, recurse
                        count += download_directory_recursive(remote_item_path, local_item_path)
                    else:
                        # Try to download as a file first
                        try:
                            content = self.client.download_file(self.sandbox_handle, remote_item_path)
                            if content:
                                local_item_path.write_bytes(content)
                                count += 1
                            else:
                                # Empty content might mean it's a directory
                                try:
                                    sub_items = self.client.transport.list_files(self.sandbox_handle, remote_item_path)
                                    if sub_items is not None:
                                        # It's a directory, recurse
                                        count += download_directory_recursive(remote_item_path, local_item_path)
                                except Exception as e:
                                    # Log but continue - item might not exist or be inaccessible
                                    logger.debug(f"Unable to check if {item_name} is directory: {e}")
                        except Exception as e:
                            # If download fails, try as directory
                            logger.debug(f"Download failed for {item_name}, attempting directory listing: {e}")
                            try:
                                sub_items = self.client.transport.list_files(self.sandbox_handle, remote_item_path)
                                if sub_items is not None:
                                    # It's a directory, recurse
                                    count += download_directory_recursive(remote_item_path, local_item_path)
                            except Exception as e:
                                # Log but don't fail - best effort artifact collection
                                logger.warning(f"Failed to download directory item {item_name}: {e}")
                                continue  # nosec B112 - best effort artifact collection
            except Exception as e:
                # Log directory listing failures
                logger.warning(f"Failed to list directory {remote_dir}: {e}")

            return count

        # Download session directory
        session_count = download_directory_recursive(session_remote_path, session_local_dir)
        downloaded_count += session_count

        # Also download artifacts directory if separate (legacy)
        artifacts_remote_path = f"{remote_base_path}/artifacts"
        artifacts_local_dir = remote_logs_dir / "artifacts"

        artifacts_count = download_directory_recursive(artifacts_remote_path, artifacts_local_dir)
        downloaded_count += artifacts_count

        return downloaded_count

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

    def _extract_connection_descriptors(self, plan: dict[str, Any]) -> dict[str, dict[str, Any]]:  # noqa: ARG002
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

    def _tag_remote_artifacts(self, remote_dir: Path, session_id: str):  # noqa: ARG002
        """Tag remote artifacts with source metadata."""
        # Add source:"remote" to events and metrics files
        for log_file in ["events.jsonl", "metrics.jsonl"]:
            log_path = remote_dir / log_file
            if log_path.exists():
                self._tag_jsonl_file(log_path, {"source": "remote"})

    def _tag_jsonl_file(self, file_path: Path, tags: dict[str, Any]):
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

        except Exception as e:
            # Best effort - don't fail collection if tagging fails
            logger.debug(f"Failed to tag JSONL file {file_path}: {e}")  # nosec B110

    def _extract_connections_from_steps(
        self, plan: dict[str, Any], cfg_index: dict[str, Any]  # noqa: ARG002
    ) -> dict[str, dict[str, Any]]:
        """Extract connection references from step configurations.

        This is a fallback when connections aren't in manifest metadata.
        It builds connection descriptors from step configs that reference connections.

        Args:
            plan: The manifest plan
            cfg_index: Map of cfg_path to step config (contains actual cfg file content)
        """

        connections = {}

        # The cfg_index contains the actual cfg file content loaded during prepare
        # Look for connection references in each cfg file
        for _cfg_path, step_config in cfg_index.items():
            connection_ref = step_config.get("connection")

            if connection_ref and connection_ref.startswith("@"):
                # Parse connection reference like @mysql.db_movies
                if "." in connection_ref[1:]:
                    family, alias = connection_ref[1:].split(".", 1)
                else:
                    # Infer family from component name
                    component = step_config.get("component", "")
                    family = component.split(".")[0] if "." in component else "unknown"
                    alias = connection_ref[1:]

                # Get connection descriptor directly from config file without resolution
                # This avoids requiring environment variables to be set during prepare phase
                try:
                    conn_descriptor = self._get_connection_descriptor_raw(family, alias)
                    if conn_descriptor:
                        connections[connection_ref] = conn_descriptor
                except Exception as e:
                    log_event(
                        "connection_resolution_skipped",
                        connection=connection_ref,
                        reason=str(e),
                    )

        return connections

    def _load_cfg_file(self, cfg_path: str, source_manifest_path: str | None) -> dict[str, Any] | None:
        """Load cfg file content using manifest-relative resolution.

        Args:
            cfg_path: Relative cfg path like "cfg/extract-actors.json"
            source_manifest_path: Path to source manifest for resolution

        Returns:
            Dict with cfg file content, or None if not found
        """
        import json

        # Try manifest-relative resolution first (most common case)
        if source_manifest_path:
            manifest_parent = Path(source_manifest_path).parent
            cfg_file_path = manifest_parent / cfg_path
            if cfg_file_path.exists():
                try:
                    with open(cfg_file_path) as f:
                        return json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to load cfg file {cfg_file_path}: {e}")

        # Fallback: try current working directory
        cfg_file_path = Path(cfg_path)
        if cfg_file_path.exists():
            try:
                with open(cfg_file_path) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cfg file {cfg_file_path}: {e}")

        # No fallback - source_manifest_path must be provided
        return None

    def _get_connection_descriptor_raw(self, family: str, alias: str) -> dict[str, Any] | None:
        """Get connection descriptor directly from config file without environment resolution.

        Args:
            family: Connection family (e.g., 'mysql', 'supabase')
            alias: Connection alias (e.g., 'db_movies', 'main')

        Returns:
            Dict with connection descriptor as-is from config file, or None if not found
        """

        # Try to find osiris_connections.yaml file
        connections_file = None
        search_paths = [
            Path("osiris_connections.yaml"),
            Path("testing_env/osiris_connections.yaml"),
            Path("../osiris_connections.yaml"),
        ]

        for path in search_paths:
            if path.exists():
                connections_file = path
                break

        if not connections_file:
            return None

        try:
            with open(connections_file) as f:
                data = yaml.safe_load(f)

            connections = data.get("connections", {})
            family_connections = connections.get(family, {})
            connection_config = family_connections.get(alias, {})

            return connection_config if connection_config else None

        except Exception as e:
            logger.warning(f"Failed to load connection descriptor for {family}.{alias}: {e}")
            return None

    def _parse_and_report_execution_phases(self, stdout: str) -> None:
        """Parse stdout to report execution phases with clear status."""
        lines = stdout.split("\n")

        # Look for key phase indicators
        deps_drivers_ok = False
        pipeline_started = False

        for line in lines:
            # Check for deps+drivers sanity success
            if "✓ deps+drivers sanity" in line:
                deps_drivers_ok = True
                print("✓ deps+drivers sanity")

            # Check for pipeline execution start
            if "🚀 Executing pipeline with" in line:
                pipeline_started = True

        # Report phase failures
        if not deps_drivers_ok:
            if "❌ Driver sanity check failed" in stdout:
                print("❌ deps+drivers sanity failed - driver registry issues")
            elif "❌ Dependency installation failed" in stdout:
                print("❌ deps+drivers sanity failed - dependency installation issues")
            elif "❌ Virtual environment creation failed" in stdout:
                print("❌ deps+drivers sanity failed - virtual environment issues")
            else:
                print("⚠️  deps+drivers sanity status unclear")

        if deps_drivers_ok and not pipeline_started:
            print("⚠️  Pipeline execution did not start despite successful sanity checks")

    def _has_real_errors(self, stderr_content: str) -> bool:
        """Check if stderr contains real errors (not just warnings)."""
        import re

        error_patterns = [
            r"Traceback \(most recent call last\):",
            r"\b(?:AssertionError|TypeError|ValueError|KeyError|ImportError|ModuleNotFoundError|ConnectionError|TimeoutError)\b",
            r"\bException\b",
            r"\berror\b(?!.*RuntimeWarning)(?!.*DeprecationWarning)",
        ]

        warning_allowlist = [
            r"RuntimeWarning",
            r"DeprecationWarning",
            r"WARNING: Running pip as the .root. user",
            r"^WARNING: ",
        ]

        lines = stderr_content.strip().split("\n") if stderr_content.strip() else []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Skip if it matches warning allowlist
            is_warning = any(re.search(pattern, line, re.IGNORECASE) for pattern in warning_allowlist)
            if is_warning:
                continue

            # Check if it matches error patterns
            is_error = any(re.search(pattern, line, re.IGNORECASE) for pattern in error_patterns)
            if is_error:
                return True

        return False

    def _has_warnings(self, stderr_content: str) -> bool:
        """Check if stderr contains warnings."""
        import re

        warning_patterns = [
            r"RuntimeWarning",
            r"DeprecationWarning",
            r"WARNING: Running pip as the .root. user",
            r"^WARNING: ",
        ]

        lines = stderr_content.strip().split("\n") if stderr_content.strip() else []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check if it matches warning patterns
            is_warning = any(re.search(pattern, line, re.IGNORECASE) for pattern in warning_patterns)
            if is_warning:
                return True

        return False

    def _extract_warning_lines(self, stderr_content: str) -> list:
        """Extract warning lines from stderr."""
        import re

        warning_patterns = [
            r"RuntimeWarning",
            r"DeprecationWarning",
            r"WARNING: Running pip as the .root. user",
            r"^WARNING: ",
        ]

        lines = stderr_content.strip().split("\n") if stderr_content.strip() else []
        warning_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check if it matches warning patterns
            is_warning = any(re.search(pattern, line, re.IGNORECASE) for pattern in warning_patterns)
            if is_warning:
                warning_lines.append(line)

        return warning_lines
