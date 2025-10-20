"""E2B Transparent Proxy Adapter - Host-side implementation.

This adapter creates an E2B sandbox, uploads the ProxyWorker,
and orchestrates execution via JSON-RPC protocol.
"""

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
import time
from typing import Any

try:
    from e2b_code_interpreter import AsyncSandbox
except ImportError:
    # For testing without E2B SDK
    AsyncSandbox = None

import contextlib
from datetime import UTC

from osiris.core.execution_adapter import (
    CollectedArtifacts,
    CollectError,
    ExecResult,
    ExecuteError,
    ExecutionAdapter,
    ExecutionContext,
    PreparedRun,
    PrepareError,
)
from osiris.remote.rpc_protocol import EventMessage, MetricMessage

# Get the ProxyWorker code path
PROXY_WORKER_PATH = Path(__file__).parent / "proxy_worker.py"


class E2BTransparentProxy(ExecutionAdapter):
    """Transparent proxy adapter for E2B execution.

    This adapter:
    1. Creates an E2B sandbox with the host session mounted
    2. Uploads and starts ProxyWorker in background
    3. Sends commands and receives streaming responses via JSON-RPC
    4. Ensures identical session structure to local execution
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize the E2B transparent proxy.

        Args:
            config: Optional configuration with:
                - api_key: E2B API key (defaults to E2B_API_KEY env var)
                - timeout: Sandbox timeout in seconds (default: 900)
                - cpu: Number of CPUs (default: 2)
                - mem_gb: Memory in GB (default: 4)
        """
        self.config = config or {}

        self.api_key = self.config.get("api_key") or os.environ.get("E2B_API_KEY")
        if not self.api_key:
            raise ExecuteError("E2B_API_KEY not found in config or environment")

        self.timeout = self.config.get("timeout", 900)
        self.cpu = self.config.get("cpu", 2)
        self.mem_gb = self.config.get("mem_gb", 4)
        self.verbose = self.config.get("verbose", False)

        self.sandbox = None
        self.sandbox_id = None  # Will be set after sandbox creation
        self.session_id = None
        self.session_context = None
        self.batch_responses = []
        self.execution_complete = False

        for logger_name in ("httpx", "httpcore", "httpcore.http11", "httpcore.h11", "httpcore.h2", "httpcore.hpack"):
            logging.getLogger(logger_name).setLevel(logging.INFO)

    def prepare(self, plan: dict[str, Any], context: ExecutionContext) -> PreparedRun:
        """Prepare execution package from compiled manifest.

        Args:
            plan: Canonical compiled manifest JSON
            context: Execution context with session info

        Returns:
            PreparedRun with deterministic execution package
        """
        try:
            # Extract components from the plan
            resolved_connections = {}
            cfg_index = {}

            # Process steps to extract connections and configs
            # Load actual configs from compiled cfg directory
            # For --last-compile, configs are in compile session, not run session
            # We need to find the compiled directory based on the plan
            import json

            # Try to determine the compiled directory
            # Check if we have a source manifest path
            source_manifest = plan.get("metadata", {}).get("source_manifest_path")
            if source_manifest:
                # Source manifest is at build/pipelines/[{profile}/]{slug}/{hash}/manifest.yaml
                # So configs are at build/pipelines/[{profile}/]{slug}/{hash}/cfg/
                manifest_path = Path(source_manifest)
                compiled_root = manifest_path.parent  # This is the build artifact directory
            else:
                # Fallback: assume configs are in base_path/cfg
                compiled_root = context.base_path

            compiled_cfg_dir = compiled_root / "cfg"
            logging.info(f"Loading configs from compiled directory: {compiled_cfg_dir}")

            for step in plan.get("steps", []):
                step_id = step.get("id")

                # Load config from compiled cfg file
                cfg_file = compiled_cfg_dir / f"{step_id}.json"
                if cfg_file.exists():
                    logging.debug(f"Loading config for {step_id} from {cfg_file}")
                    with open(cfg_file) as f:
                        config = json.load(f)
                    logging.debug(f"Loaded config for {step_id}: {config}")
                else:
                    # Fallback to config from plan if file doesn't exist
                    logging.warning(f"Config file not found: {cfg_file}, using plan config")
                    config = step.get("config", {})

                # Store config in cfg_index
                cfg_path = f"cfg/{step_id}.json"
                cfg_index[cfg_path] = config

                # Extract connection if present
                if "connection" in config:
                    conn_ref = config["connection"]
                    if conn_ref.startswith("@"):
                        # This is a connection reference
                        # The actual resolution happens at runtime
                        resolved_connections[conn_ref] = {
                            "ref": conn_ref,
                            "resolved": False,  # Will be resolved during execution
                        }

            # Define IO layout
            io_layout = {
                "logs": f"logs/{context.session_id}",
                "artifacts": f"logs/{context.session_id}/artifacts",
                "events": f"logs/{context.session_id}/events.jsonl",
                "metrics": f"logs/{context.session_id}/metrics.jsonl",
            }

            # Runtime parameters
            run_params = {
                "session_id": context.session_id,
                "started_at": context.started_at.isoformat(),
                "adapter": "e2b_transparent_proxy",
                "verbose": self.verbose,
            }

            # Execution constraints
            constraints = {
                "timeout_seconds": self.timeout,
                "max_memory_gb": self.mem_gb,
                "cpu_count": self.cpu,
            }

            # Metadata
            metadata = {
                "pipeline_name": plan.get("pipeline", {}).get("name", "unknown"),
                "step_count": len(plan.get("steps", [])),
                "adapter_version": "1.0.0",
            }

            return PreparedRun(
                plan=plan,
                resolved_connections=resolved_connections,
                cfg_index=cfg_index,
                io_layout=io_layout,
                run_params=run_params,
                constraints=constraints,
                metadata=metadata,
                compiled_root=str(context.base_path),
            )

        except Exception as e:
            raise PrepareError(f"Failed to prepare execution: {e}") from e

    def execute(self, prepared: PreparedRun, context: ExecutionContext) -> ExecResult:
        """Execute prepared pipeline in E2B sandbox.

        Since E2B requires async operations, we run the async execution
        in a new event loop if not already in one.

        Args:
            prepared: Prepared execution package
            context: Execution context

        Returns:
            ExecResult with execution status and metrics
        """
        start_time = time.time()

        try:
            # Check if we're already in an event loop
            try:
                asyncio.get_running_loop()
                # We're in an async context, can't use asyncio.run
                # This is a limitation - E2B requires async
                raise ExecuteError(
                    "E2BTransparentProxy requires async execution. "
                    "Please use the async execution path or run in a separate thread."
                )
            except RuntimeError:
                # No event loop, we can create one
                result = asyncio.run(self._execute_async(prepared, context))

            duration = time.time() - start_time

            return ExecResult(
                success=result.get("status") == "success",
                exit_code=0 if result.get("status") == "success" else 1,
                duration_seconds=duration,
                error_message=result.get("error"),
                step_results=result.get("step_results"),
            )

        except Exception as e:
            duration = time.time() - start_time
            return ExecResult(
                success=False,
                exit_code=1,
                duration_seconds=duration,
                error_message=str(e),
            )

    async def _execute_async(self, prepared: PreparedRun, context: ExecutionContext) -> dict[str, Any]:  # noqa: PLR0915
        """Async execution implementation using batch file communication."""
        sandbox_start_time = time.time()
        self.session_id = context.session_id
        self.context = context  # Store context for use in other methods
        self.prepared_plan = prepared.plan  # Store plan for status.json fallback
        # Don't use SessionContext to avoid nested directories
        # E2B writes directly to the mounted session directory
        self.session_context = None

        # Track any step failures for proper exit code
        self.had_errors = False

        # Store verbose and raw_stdout flags for use in output handlers
        self.verbose = prepared.run_params.get("verbose", False)
        self.raw_stdout = self.config.raw_stdout if hasattr(self.config, "raw_stdout") else False

        verbose = self.verbose

        logging.info(f"Starting E2B transparent proxy execution for session {self.session_id}")
        if verbose:
            print("🚀 Starting E2B Transparent Proxy...")

        try:
            # Create sandbox
            if verbose:
                print(f"📦 Creating E2B sandbox (CPU: {self.cpu}, Memory: {self.mem_gb}GB)...")
            await self._create_sandbox(context)

            # Upload ProxyWorker and dependencies
            if verbose:
                print("📤 Uploading ProxyWorker to sandbox...")
            await self._upload_worker()

            # Materialize execution files with resolved configs
            if verbose:
                print("📝 Materializing configs and manifest...")
            await self._materialize_execution_files(prepared, context)

            # Generate and upload commands file
            if verbose:
                print("📝 Generating batch commands file...")
            await self._generate_commands_file(prepared.plan, context)

            # Save commands.jsonl to host for debugging
            commands_host_file = context.logs_dir / "commands.jsonl"
            with open(commands_host_file, "w") as f:
                f.write(self.commands_content)
            logging.debug(f"Saved commands.jsonl to {commands_host_file}")

            # Log E2B overhead (sandbox creation time)
            sandbox_ready_time = time.time()
            e2b_overhead_ms = (sandbox_ready_time - sandbox_start_time) * 1000
            from osiris.core.session_logging import log_metric

            log_metric("e2b_overhead_ms", e2b_overhead_ms)

            # Execute batch commands and stream results
            if verbose:
                print("🔄 Executing batch commands and streaming results...")
            results = await self._execute_batch_commands(verbose)

            # Check if we had any errors during execution
            if self.had_errors:
                results["status"] = "failed"
                if verbose:
                    print("❌ E2B execution completed with errors")
            elif verbose:
                print("✅ E2B execution completed successfully")

            return results

        except Exception as e:
            logging.error(f"E2B execution failed: {e}", exc_info=True)
            self.had_errors = True
            return {
                "status": "failed",
                "error": str(e),
            }

        finally:
            # Download artifacts from sandbox to host before closing
            if hasattr(self, "sandbox") and self.sandbox and hasattr(self, "context") and self.context:
                try:
                    await self._download_artifacts(self.context)
                except Exception as e:
                    logging.error(f"Failed to download artifacts: {e}")

            # Try to fetch status.json from sandbox
            status_fetched = False
            if hasattr(self, "sandbox") and self.sandbox:
                status_fetched = await self._fetch_status_from_sandbox()

            if not status_fetched:
                # CONTRACT VIOLATION: Worker didn't write status.json
                logging.warning("status_contract_violation: Worker failed to write status.json")

                # Create fallback status with last stderr
                if hasattr(self, "context") and self.context:
                    last_stderr = self._get_last_stderr_lines(20)
                    self._write_fallback_status(self.context, last_stderr)

            await self._close_sandbox()

    def collect(self, prepared: PreparedRun, context: ExecutionContext) -> CollectedArtifacts:
        """Collect execution artifacts after run.

        Since artifacts are written directly to the host session directory
        via the transparent proxy, we just need to verify they exist.

        Args:
            prepared: Prepared execution package
            context: Execution context

        Returns:
            CollectedArtifacts with paths to logs and outputs
        """
        try:
            logs_dir = context.logs_dir

            # Check for expected artifacts
            events_log = logs_dir / "events.jsonl"
            metrics_log = logs_dir / "metrics.jsonl"
            execution_log = logs_dir / "osiris.log"
            artifacts_dir = logs_dir / "artifacts"

            # Build metadata
            metadata = {
                "session_id": context.session_id,
                "adapter": "e2b_transparent_proxy",
                "collected_at": time.time(),
            }

            # Add file sizes if they exist
            if events_log.exists():
                metadata["events_size"] = events_log.stat().st_size
            if metrics_log.exists():
                metadata["metrics_size"] = metrics_log.stat().st_size
            if execution_log.exists():
                metadata["log_size"] = execution_log.stat().st_size
            if artifacts_dir.exists():
                artifact_files = list(artifacts_dir.glob("*"))
                metadata["artifact_count"] = len(artifact_files)

            return CollectedArtifacts(
                events_log=events_log if events_log.exists() else None,
                metrics_log=metrics_log if metrics_log.exists() else None,
                execution_log=execution_log if execution_log.exists() else None,
                artifacts_dir=artifacts_dir if artifacts_dir.exists() else None,
                metadata=metadata,
            )

        except Exception as e:
            raise CollectError(f"Failed to collect artifacts: {e}") from e

    # === Async implementation methods ===

    def _prepare_env_vars(self) -> dict[str, str]:
        """Prepare environment variables to pass to the sandbox.

        Passes through OSIRIS_* and AWS_* variables, plus common secrets.
        """
        import os

        env_vars = {}

        # Pass through OSIRIS_* variables
        for key, value in os.environ.items():
            if key.startswith("OSIRIS_"):
                env_vars[key] = value
                logging.debug(f"Passing through env var: {key}")

        # Pass through AWS_* variables for cloud access
        for key, value in os.environ.items():
            if key.startswith("AWS_"):
                env_vars[key] = value
                logging.debug(f"Passing through env var: {key}")

        # Pass through common database/API credentials
        common_secrets = [
            "MYSQL_PASSWORD",
            "POSTGRES_PASSWORD",
            "SUPABASE_URL",
            "SUPABASE_SERVICE_ROLE_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "GEMINI_API_KEY",
        ]

        for key in common_secrets:
            if key in os.environ:
                env_vars[key] = os.environ[key]
                logging.debug(f"Passing through secret: {key[:10]}...")

        # Note: E2B_SANDBOX_ID will be set after sandbox creation
        # since we don't know the ID until the sandbox is created

        return env_vars

    async def _create_sandbox(self, context: ExecutionContext):
        """Create E2B sandbox with session directory mounted."""
        logging.info("Creating E2B sandbox...")

        if not AsyncSandbox:
            raise ExecuteError("E2B SDK not installed. Run: pip install e2b-code-interpreter")

        # Prepare environment variables
        env_vars = self._prepare_env_vars()

        # Create sandbox with async API
        self.sandbox = await AsyncSandbox.create(api_key=self.api_key, timeout=self.timeout, envs=env_vars)

        # Extract sandbox ID from the sandbox object
        self.sandbox_id = getattr(self.sandbox, "sandbox_id", "unknown")

        # Pass sandbox ID to environment for worker
        await self.sandbox.commands.run(f"export E2B_SANDBOX_ID={self.sandbox_id}")

        # Create session directory in sandbox (use home directory)
        await self.sandbox.commands.run(f"mkdir -p /home/user/session/{self.session_id}")

        logging.info(f"Sandbox created: {self.sandbox_id}")

    async def _upload_worker(self):  # noqa: PLR0915
        """Upload ProxyWorker script and dependencies to sandbox."""
        logging.info("Uploading ProxyWorker to sandbox...")

        # Read ProxyWorker code
        with open(PROXY_WORKER_PATH) as f:
            worker_code = f.read()

        # Create osiris directory structure in sandbox
        await self.sandbox.commands.run(
            "mkdir -p /home/user/osiris/core /home/user/osiris/remote /home/user/osiris/drivers"
        )

        # Upload RPC protocol
        rpc_protocol_path = Path(__file__).parent / "rpc_protocol.py"
        with open(rpc_protocol_path) as f:
            rpc_content = f.read()
            await self.sandbox.files.write("/home/user/rpc_protocol.py", rpc_content)
            await self.sandbox.files.write("/home/user/osiris/remote/rpc_protocol.py", rpc_content)

        # Upload the unbuffered proxy_worker_runner
        runner_path = Path(__file__).parent / "proxy_worker_runner.py"
        if runner_path.exists():
            with open(runner_path) as f:
                await self.sandbox.files.write("/home/user/proxy_worker_runner.py", f.read())

        # Upload required core modules
        osiris_root = Path(__file__).parent.parent  # osiris/ directory

        # Upload driver registry and related core modules
        core_modules = [
            "core/driver.py",
            "core/execution_adapter.py",
            "core/session_logging.py",
            "core/redaction.py",
            "components/__init__.py",
            "components/registry.py",
            "components/error_mapper.py",
            "components/utils.py",
        ]

        # Also upload connector modules that drivers might need
        connector_modules = [
            "connectors/mysql/mysql_extractor_driver.py",
            "connectors/mysql/mysql_writer_driver.py",
            "connectors/supabase/client.py",
            "connectors/supabase/writer.py",
            "connectors/supabase/extractor.py",
            "connectors/supabase/__init__.py",
        ]

        for module_path in core_modules:
            full_path = osiris_root / module_path
            if full_path.exists():
                with open(full_path) as f:
                    await self.sandbox.files.write(f"/home/user/osiris/{module_path}", f.read())

        # Upload connector modules
        await self.sandbox.commands.run(
            "mkdir -p /home/user/osiris/connectors/mysql /home/user/osiris/connectors/supabase"
        )
        for module_path in connector_modules:
            full_path = osiris_root / module_path
            if full_path.exists():
                with open(full_path) as f:
                    await self.sandbox.files.write(f"/home/user/osiris/{module_path}", f.read())

        # Upload __init__.py files to make it a proper package
        init_content = "# Osiris package\n"
        await self.sandbox.files.write("/home/user/osiris/__init__.py", init_content)
        await self.sandbox.files.write("/home/user/osiris/core/__init__.py", init_content)
        await self.sandbox.files.write("/home/user/osiris/remote/__init__.py", init_content)
        await self.sandbox.files.write("/home/user/osiris/drivers/__init__.py", init_content)
        await self.sandbox.files.write("/home/user/osiris/connectors/__init__.py", init_content)
        await self.sandbox.files.write("/home/user/osiris/connectors/mysql/__init__.py", init_content)
        await self.sandbox.files.write("/home/user/osiris/connectors/supabase/__init__.py", init_content)
        await self.sandbox.files.write("/home/user/osiris/components/__init__.py", init_content)

        # Upload all driver modules
        drivers_dir = osiris_root / "drivers"
        if drivers_dir.exists():
            for driver_file in drivers_dir.glob("*.py"):
                if driver_file.name != "__init__.py":
                    with open(driver_file) as f:
                        await self.sandbox.files.write(f"/home/user/osiris/drivers/{driver_file.name}", f.read())

        # Patch worker script to use local imports for RPC protocol only
        # Driver registration is now handled properly in the source
        patched_worker_code = worker_code.replace("from osiris.remote.rpc_protocol import", "from rpc_protocol import")

        # Upload worker script
        await self.sandbox.files.write("/home/user/proxy_worker.py", patched_worker_code)

        # Upload component specs
        components_dir = osiris_root.parent / "components"
        if components_dir.exists():
            # Create components directory structure
            await self.sandbox.commands.run("mkdir -p /home/user/components")

            # Upload each component spec
            for comp_dir in components_dir.iterdir():
                if comp_dir.is_dir() and not comp_dir.name.startswith("."):
                    comp_name = comp_dir.name
                    spec_file = comp_dir / "spec.yaml"
                    if spec_file.exists():
                        await self.sandbox.commands.run(f"mkdir -p /home/user/components/{comp_name}")
                        with open(spec_file) as f:
                            await self.sandbox.files.write(f"/home/user/components/{comp_name}/spec.yaml", f.read())
                        logging.debug(f"Uploaded component spec: {comp_name}")

            # Upload spec.schema.json if it exists
            schema_file = components_dir / "spec.schema.json"
            if schema_file.exists():
                with open(schema_file) as f:
                    await self.sandbox.files.write("/home/user/components/spec.schema.json", f.read())
                logging.debug("Uploaded component spec schema")

            logging.info("Component specs uploaded successfully")

        # Upload requirements.txt if auto-install is enabled
        if self.config.get("install_deps", False):
            requirements_path = Path(__file__).parent.parent.parent / "requirements.txt"
            if requirements_path.exists():
                with open(requirements_path) as f:
                    requirements_content = f.read()
                # Upload as requirements_e2b.txt to the session directory
                await self.sandbox.files.write(
                    f"/home/user/session/{self.session_id}/requirements_e2b.txt",
                    requirements_content,
                )
                logging.info("Requirements.txt uploaded for dependency installation")
            else:
                logging.warning(f"Requirements.txt not found at {requirements_path}")

        logging.info("ProxyWorker uploaded successfully")

    def _handle_event(self, event: EventMessage):
        """Handle event from worker."""
        # Log event to session
        if self.session_context:
            self.session_context.log_event(event.name, **event.data)

    def _handle_metric(self, metric: MetricMessage):
        """Handle metric from worker."""
        # Log metric to session
        if self.session_context:
            self.session_context.log_metric(metric.name, metric.value)

    # Removed duplicate _forward_event_to_host - using the one at line 1006 instead

    async def _show_heartbeat(self):
        """Show heartbeat with file sizes and line counts."""
        try:
            # Check files in mounted session directory
            result = await self.sandbox.commands.run(
                f"wc -l /home/user/session/{self.session_id}/events.jsonl "
                f"/home/user/session/{self.session_id}/metrics.jsonl 2>/dev/null || echo '0 0'"
            )

            if result.stdout:
                lines = result.stdout.strip().split("\n")
                events_lines = 0
                metrics_lines = 0

                for line in lines:
                    if "events.jsonl" in line:
                        events_lines = int(line.strip().split()[0])
                    elif "metrics.jsonl" in line:
                        metrics_lines = int(line.strip().split()[0])

                # Check artifacts size
                size_result = await self.sandbox.commands.run(
                    f"du -sm /home/user/session/{self.session_id}/artifacts 2>/dev/null || echo '0'"
                )
                artifacts_size = 0
                if size_result.stdout:
                    parts = size_result.stdout.strip().split()
                    if parts:
                        with contextlib.suppress(ValueError, IndexError):
                            artifacts_size = float(parts[0])

                print(
                    f"[E2B] heartbeat: events={events_lines}, metrics={metrics_lines}, artifacts_size_mb={artifacts_size:.1f}"
                )

        except Exception as e:
            logging.debug(f"Error showing heartbeat: {e}")

    async def _download_artifacts(self, context: ExecutionContext):  # noqa: PLR0915
        """Download artifacts from sandbox to host.

        Args:
            context: Execution context with session info
        """
        if not self.sandbox:
            logging.debug("No sandbox available for artifact download")
            return

        artifacts_start_time = time.time()
        sandbox_artifacts_dir = f"/home/user/session/{context.session_id}/artifacts"
        host_artifacts_dir = context.logs_dir / "artifacts"

        download_data = os.environ.get("E2B_DOWNLOAD_DATA_ARTIFACTS", "0") == "1"
        max_mb_default = 5
        try:
            max_mb = float(os.environ.get("E2B_ARTIFACT_MAX_MB", max_mb_default))
        except (TypeError, ValueError):
            max_mb = max_mb_default
        max_bytes = max_mb * 1024 * 1024

        try:
            # Check if artifacts directory exists in sandbox
            result = await self.sandbox.commands.run(
                f"test -d {sandbox_artifacts_dir} && echo 'exists' || echo 'missing'"
            )

            if not result.stdout or "missing" in result.stdout:
                logging.info("No artifacts directory in sandbox to download")
                return

            # List all artifact files
            logging.info(f"Downloading artifacts from {sandbox_artifacts_dir}")
            list_result = await self.sandbox.commands.run(
                f"find {sandbox_artifacts_dir} -type f -printf '%P\\n' 2>/dev/null | sort"
            )

            if not list_result.stdout:
                logging.info("Artifacts directory exists but is empty")
                return

            files = [f.strip() for f in list_result.stdout.strip().split("\n") if f.strip()]

            if not files:
                logging.info("No artifact files found to download")
                return

            # Download each file
            downloaded_count = 0
            total_bytes = 0

            def should_download(rel_path: str, size: int) -> bool:
                if rel_path.startswith("_system/"):
                    return True
                if rel_path.endswith("run_card.json"):
                    return True
                if rel_path.endswith("cleaned_config.json"):
                    return True

                if size > max_bytes and not download_data:
                    logging.debug(
                        "Skipping artifact %s due to size %.2f MB > limit %.2f MB",
                        rel_path,
                        size / (1024 * 1024),
                        max_mb,
                    )
                    return False

                lower_path = rel_path.lower()
                if not download_data and (
                    lower_path.endswith("output.pkl")
                    or lower_path.endswith("output.parquet")
                    or lower_path.endswith(".feather")
                ):
                    logging.debug("Skipping data artifact %s (data downloads disabled)", rel_path)
                    return False

                if lower_path.endswith((".txt", ".json", ".sql")):
                    return True

                return download_data

            for relative_path in files:
                sandbox_file_path = f"{sandbox_artifacts_dir}/{relative_path}"
                host_file_path = host_artifacts_dir / relative_path

                try:
                    stat_result = await self.sandbox.commands.run(f"stat -c %s {sandbox_file_path}")
                    file_size = 0
                    if stat_result.stdout:
                        try:
                            file_size = int(stat_result.stdout.strip())
                        except ValueError:
                            file_size = 0

                    if not should_download(relative_path, file_size):
                        logging.debug("Skipping artifact: %s", relative_path)
                        continue

                    host_file_path.parent.mkdir(parents=True, exist_ok=True)

                    content = await self.sandbox.files.read(sandbox_file_path)

                    if isinstance(content, str):
                        host_file_path.write_text(content, encoding="utf-8")
                        written_bytes = len(content.encode("utf-8"))
                    elif isinstance(content, bytes):
                        host_file_path.write_bytes(content)
                        written_bytes = len(content)
                    else:
                        content_str = str(content)
                        host_file_path.write_text(content_str, encoding="utf-8")
                        written_bytes = len(content_str.encode("utf-8"))

                    total_bytes += written_bytes
                    downloaded_count += 1

                    logging.debug(f"Downloaded artifact: {relative_path} ({file_size} bytes)")

                except Exception as e:
                    logging.warning(f"Failed to download artifact {relative_path}: {e}")
                    continue

            # Log summary
            total_mb = total_bytes / (1024 * 1024)
            logging.info(f"Artifacts copied: {downloaded_count} files, {total_bytes} bytes ({total_mb:.2f} MB)")

            # Emit metrics
            from osiris.core.session_logging import log_metric

            log_metric("artifacts_bytes_total", total_bytes, unit="bytes")
            log_metric("artifacts_files_total", downloaded_count, unit="files")

            # Log artifact copy time
            artifacts_copy_ms = (time.time() - artifacts_start_time) * 1000
            log_metric("artifacts_copy_ms", artifacts_copy_ms)

        except Exception as e:
            logging.error(f"Error downloading artifacts: {e}")
            raise

    async def _close_sandbox(self):
        """Close sandbox and cleanup resources."""
        if self.sandbox:
            try:
                logging.info("Closing E2B sandbox...")
                await self.sandbox.kill()
            except Exception as e:
                logging.warning(f"Error closing sandbox: {e}")

    def _prepare_env_vars(self) -> dict[str, str]:
        """Prepare environment variables for sandbox."""
        env_vars = {}

        # Pass through important environment variables
        for key, value in os.environ.items():
            # Pass secrets and config vars
            if any(pattern in key for pattern in ["_KEY", "_PASSWORD", "_TOKEN", "MYSQL_", "SUPABASE_"]):
                env_vars[key] = value
                # Log masked for security
                masked = "***" if value else "(empty)"
                logging.debug(f"Setting env var {key}={masked}")

        return env_vars

    async def _materialize_execution_files(self, prepared, context: ExecutionContext):
        """Materialize manifest and configs as execution source of truth."""
        import hashlib

        import yaml

        from osiris.core.config import parse_connection_ref, resolve_connection

        # 1. Create cfg directory
        cfg_dir = context.logs_dir / "cfg"
        cfg_dir.mkdir(exist_ok=True)

        # 2. Write each config from cfg_index with CONNECTION RESOLUTION (matching LocalAdapter)
        logging.info(f"Writing {len(prepared.cfg_index)} configs to {cfg_dir} with connection resolution")

        for cfg_path, step_config in prepared.cfg_index.items():
            # Extract step_id from cfg path (e.g., "cfg/extract-actors.json" -> "extract-actors")
            step_id = cfg_path.replace("cfg/", "").replace(".json", "")

            # Make a copy to avoid modifying original
            resolved_config = step_config.copy()

            # CRITICAL: Resolve connection references on the host (same as LocalAdapter does)
            # This is the same logic from runner_v0.py _resolve_step_connection
            if "connection" in resolved_config:
                conn_ref = resolved_config["connection"]

                # Only resolve if it's a reference (starts with @)
                if isinstance(conn_ref, str) and conn_ref.startswith("@"):
                    try:
                        # Parse the connection reference
                        family, alias = parse_connection_ref(conn_ref)

                        # Resolve the connection using the EXACT SAME function as LocalAdapter
                        resolved_connection = resolve_connection(family, alias)

                        # Replace the reference with the resolved connection
                        resolved_config["resolved_connection"] = resolved_connection
                        # Add connection metadata for proxy worker to use in events
                        resolved_config["_connection_family"] = family
                        resolved_config["_connection_alias"] = alias if alias else "default"
                        # Remove the reference string
                        del resolved_config["connection"]

                        logging.debug(f"Resolved connection for {step_id}: {family}.{alias or '(default)'}")
                    except Exception as e:
                        logging.error(f"Failed to resolve connection for {step_id}: {e}")
                        raise

            logging.debug(f"Writing resolved config for {step_id}")

            # Write resolved config to host
            cfg_file = cfg_dir / f"{step_id}.json"
            with open(cfg_file, "w") as f:
                json.dump(resolved_config, f, indent=2)

            # Calculate SHA256 from the actual file bytes written to disk
            sha256 = hashlib.sha256(cfg_file.read_bytes()).hexdigest()

            # Log materialization event
            if hasattr(self, "context") and self.context:
                self._forward_event_to_host(
                    {
                        "name": "cfg_materialized",
                        "data": {
                            "path": f"cfg/{step_id}.json",
                            "size_bytes": cfg_file.stat().st_size,
                            "sha256": sha256,
                        },
                    }
                )

            # Upload the EXACT SAME resolved config to sandbox
            await self.sandbox.files.write(
                f"/home/user/session/{self.session_id}/cfg/{step_id}.json", cfg_file.read_text()
            )

            # Log upload confirmation to debug.log
            logging.debug(f"Uploaded cfg/{step_id}.json - size: {cfg_file.stat().st_size} bytes, sha256: {sha256}")

        # 3. Write manifest.yaml
        manifest_path = context.logs_dir / "manifest.yaml"
        with open(manifest_path, "w") as f:
            yaml.dump(prepared.plan, f, default_flow_style=False)

        manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

        # Log manifest materialization
        if hasattr(self, "context") and self.context:
            self._forward_event_to_host(
                {
                    "name": "manifest_materialized",
                    "data": {
                        "path": "manifest.yaml",
                        "size": manifest_path.stat().st_size,
                        "sha256": manifest_sha256,
                    },
                }
            )

        # Upload manifest to sandbox
        await self.sandbox.files.write(f"/home/user/session/{self.session_id}/manifest.yaml", manifest_path.read_text())

        logging.info(f"Materialized {len(prepared.plan.get('steps', []))} configs with host-side connection resolution")

    async def _generate_commands_file(self, manifest_data: dict[str, Any], context: ExecutionContext):
        """Generate commands.jsonl file with file-only contract."""
        commands = []

        # 1. Ping command to test communication
        commands.append({"cmd": "ping", "data": "init"})

        # 2. Prepare session command
        commands.append(
            {
                "cmd": "prepare",
                "session_id": self.session_id,
                "manifest": manifest_data,
                "log_level": self.config.get("log_level", "INFO"),
                "install_deps": self.config.get("install_deps", False),
            }
        )

        # 3. Build step dependency graph for inputs
        for i, step in enumerate(manifest_data.get("steps", [])):
            step_id = step["id"]
            driver = step.get("driver", step.get("type"))  # Handle both formats

            # Determine inputs based on needs dependencies
            inputs = {}
            needs = step.get("needs", [])

            if needs:
                # This step needs inputs from upstream steps
                # For simplicity, take the first dependency and assume it provides a DataFrame
                from_step = needs[0]
                inputs = {"df": {"from_step": from_step, "key": "df"}}

            # Legacy fallback for writer pattern (kept for backward compatibility)
            elif "writer" in driver or "csv_writer" in driver:
                # Writers need DataFrame from previous extractor
                for prev_step in reversed(manifest_data.get("steps", [])[:i]):
                    if "extractor" in prev_step.get("driver", ""):
                        # Found the upstream extractor
                        inputs = {"df": {"from_step": prev_step.get("id"), "key": "df"}}
                        break

            # Build exec_step command with file-only contract
            commands.append(
                {
                    "cmd": "exec_step",
                    "step_id": step_id,
                    "driver": driver,
                    "cfg_path": f"cfg/{step_id}.json",  # File reference only
                    "inputs": inputs if inputs else None,
                }
            )

        # 4. Cleanup command
        commands.append({"cmd": "cleanup"})

        # Generate commands.jsonl content
        commands_content = ""
        for cmd in commands:
            commands_content += json.dumps(cmd) + "\n"

        # Store for later use in _execute_batch_commands
        self.commands_content = commands_content

        # Upload commands file to sandbox session directory
        session_commands_file = f"/home/user/session/{self.session_id}/commands.jsonl"
        await self.sandbox.files.write(session_commands_file, commands_content)

        # Also keep legacy location for compatibility
        await self.sandbox.files.write("/home/user/commands.jsonl", commands_content)

        logging.info(f"Generated commands.jsonl with {len(commands)} commands using file-only contract")

    async def _execute_batch_commands(self, verbose: bool = False) -> dict[str, Any]:
        """Execute batch commands with unbuffered output and progress watchdog."""

        # Generate commands.jsonl in session directory
        session_commands_file = f"/home/user/session/{self.session_id}/commands.jsonl"
        await self.sandbox.commands.run(f"mkdir -p /home/user/session/{self.session_id}")

        # Write commands file to session directory (use stored content)
        await self.sandbox.files.write(session_commands_file, self.commands_content)

        # Execute the unbuffered runner with PYTHONUNBUFFERED=1
        # Pass session ID as argument so runner knows where to find commands
        await self.sandbox.commands.run(
            f"cd /home/user && PYTHONUNBUFFERED=1 python -u proxy_worker_runner.py {self.session_id}",
            background=True,
            on_stdout=self._handle_batch_output,
            on_stderr=self._handle_batch_error,
        )

        # Reset response collection and watchdog
        self.batch_responses.clear()
        self.execution_complete = False
        last_output_time = time.time()
        watchdog_interval = 30  # seconds without output before warning

        # Wait for execution with progress watchdog and heartbeat
        timeout_seconds = self.timeout
        start_time = time.time()
        last_heartbeat = time.time()
        heartbeat_interval = 2.0  # seconds

        while not self.execution_complete and (time.time() - start_time) < timeout_seconds:
            await asyncio.sleep(0.5)

            # Check if we've had output recently
            if hasattr(self, "_last_output_time"):
                last_output_time = self._last_output_time

            # Heartbeat: show progress every ~2 seconds
            if self.verbose and (time.time() - last_heartbeat) > heartbeat_interval:
                last_heartbeat = time.time()
                await self._show_heartbeat()

            # Watchdog: warn if no output for too long
            time_since_output = time.time() - last_output_time
            if time_since_output > watchdog_interval:
                if verbose:
                    print(
                        f"⚠️  No output for {int(time_since_output)} seconds - execution may be stuck (last heartbeat: {int(time.time() - last_heartbeat)}s ago)"
                    )
                logging.warning(f"No output from E2B for {int(time_since_output)} seconds")
                # Reset watchdog to avoid spamming
                last_output_time = time.time()

        if not self.execution_complete:
            # Check if worker completed but we missed the signal
            check_result = await self.sandbox.commands.run(
                "cat /home/user/session/*/worker_complete 2>/dev/null || echo 'NOT_COMPLETE'"
            )
            if check_result.stdout and "worker_complete" in check_result.stdout:
                logging.info("Worker completed but signal was missed, collecting results")
            else:
                raise ExecuteError(f"Batch execution timed out after {timeout_seconds} seconds")

        # Parse final results from responses
        return self._parse_batch_results()

    async def _handle_batch_output(self, data: str):  # noqa: PLR0915
        """Handle stdout from batch runner with verbose passthrough."""
        # Update watchdog timer
        self._last_output_time = time.time()

        # Import masking for sensitive data
        from osiris.core.secrets_masking import mask_sensitive_string

        for line in data.split("\n"):
            if line.strip():
                # Mask sensitive data before any output
                masked_line = mask_sensitive_string(line)

                # Verbose passthrough with [E2B] prefix
                if self.verbose:
                    print(f"[E2B] {masked_line}")

                # Always log raw output if e2b-raw-stdout is enabled
                if self.raw_stdout:
                    logging.debug(f"[E2B-RAW] {masked_line}")

                try:
                    response_data = json.loads(line)

                    # Handle special output from proxy_worker_runner
                    msg_type = response_data.get("type")

                    if msg_type == "worker_started":
                        logging.info(f"ProxyWorker started in session {response_data.get('session')}")
                    elif msg_type == "worker_init":
                        logging.info("ProxyWorker initializing...")
                    elif msg_type == "commands_start":
                        logging.info(f"Processing commands from {response_data.get('file')}")
                    elif msg_type == "rpc_ack":
                        logging.debug(f"Command acknowledged: {response_data.get('id')}")
                    elif msg_type == "rpc_exec":
                        cmd = response_data.get("cmd")
                        logging.debug(f"Executing command: {cmd}")
                        # Special handling for exec_step to show progress
                        if cmd == "exec_step" and self.verbose:
                            # Will be handled when we get the actual exec_step command data
                            pass
                    elif msg_type == "rpc_done":
                        logging.debug(f"Command completed: {response_data.get('cmd')}")
                    elif msg_type == "rpc_response":
                        # This is a response from ProxyWorker
                        self.batch_responses.append(response_data)

                        # Check for exec_step errors to track failures
                        if response_data.get("cmd") == "exec_step":
                            if response_data.get("error") or response_data.get("status") == "failed":
                                self.had_errors = True
                                logging.error(
                                    f"Step {response_data.get('step_id')} failed: {response_data.get('error')}"
                                )

                        # Handle exec_step responses for verbose output
                        if response_data.get("cmd") == "exec_step" and self.verbose:
                            step_id = response_data.get("step_id")
                            if response_data.get("status") == "complete":
                                duration = response_data.get("duration_ms", 0)
                                rows = response_data.get("rows_processed", 0)
                                print(f"  ✓ {step_id}: Complete (duration_ms={duration}, rows={rows})")
                            elif response_data.get("error"):
                                print(f"  ✗ {step_id}: Failed - {response_data.get('error')}")

                    elif msg_type == "worker_complete":
                        logging.info(f"Worker completed: {response_data.get('commands_processed')} commands")
                        self.execution_complete = True
                    elif msg_type in {"error", "fatal"}:
                        logging.error(
                            f"Worker error ({msg_type}): {response_data.get('reason')} - {response_data.get('error')}"
                        )
                    elif msg_type == "interrupted":
                        logging.warning(f"Worker interrupted: {response_data.get('reason')}")

                    # Also handle regular event/metric messages
                    elif "event" in response_data or response_data.get("type") == "event":
                        # Forward event to host events.jsonl
                        self._forward_event_to_host(
                            {
                                "name": response_data.get("name", response_data.get("event")),
                                "data": response_data.get("data", {}),
                                "timestamp": response_data.get("timestamp"),
                            }
                        )

                        # Track step_failed events
                        event_name = response_data.get("name", response_data.get("event"))
                        if event_name == "step_failed":
                            self.had_errors = True
                            error_msg = response_data.get("data", {}).get("error", "Unknown error")
                            logging.error(f"Step failed event: {error_msg}")

                        # Special handling for step events in verbose mode
                        if event_name == "step_start" and self.verbose:
                            step_id = response_data.get("data", {}).get("step_id")
                            print(f"  ▶ {step_id}: Starting...")
                        elif event_name == "step_complete" and self.verbose:
                            step_id = response_data.get("data", {}).get("step_id")
                            duration = response_data.get("data", {}).get("duration", 0)
                            rows = response_data.get("data", {}).get("rows_processed", 0)
                            print(f"  ✓ {step_id}: Complete (duration={duration:.2f}s, rows={rows})")
                        elif event_name == "step_failed" and self.verbose:
                            step_id = response_data.get("data", {}).get("step_id")
                            error = response_data.get("data", {}).get("error", "Unknown error")
                            print(f"  ✗ {step_id}: Failed - {error}")

                    elif response_data.get("type") == "metric":
                        # Forward metric to host metrics.jsonl
                        self._forward_metric_to_host(response_data)
                    else:
                        # Regular command response
                        self.batch_responses.append(response_data)

                        # Check if this is the cleanup response (final command)
                        if response_data.get("cmd") == "cleanup":
                            self.execution_complete = True

                except json.JSONDecodeError:
                    logging.warning(f"Invalid JSON from batch runner: {line}")
                except Exception as e:
                    logging.error(f"Error handling batch output: {e}")

    async def _handle_batch_error(self, data: str):
        """Handle stderr from batch runner (debug logs)."""
        for line in data.split("\n"):
            if line.strip():
                logging.debug(f"[Batch Runner] {line}")

    def _parse_batch_results(self) -> dict[str, Any]:
        """Parse batch responses into final execution results."""
        step_results = []
        total_rows = 0
        steps_executed = 0

        for response in self.batch_responses:
            if response.get("cmd") == "exec_step" and response.get("status") == "complete":
                rows = response.get("rows_processed", 0)
                total_rows += rows
                steps_executed += 1

                step_results.append(
                    {
                        "step_id": response.get("step_id"),
                        "rows_processed": rows,
                        "duration_ms": response.get("duration_ms", 0),
                    }
                )
            elif response.get("cmd") == "cleanup":
                # Use cleanup response for final counts if available
                if "steps_executed" in response:
                    steps_executed = response["steps_executed"]
                if "total_rows" in response:
                    total_rows = response["total_rows"]

        return {
            "status": "success",
            "steps_executed": steps_executed,
            "total_rows": total_rows,
            "step_results": step_results,
        }

    def _forward_event_to_host(self, event_data: dict[str, Any]):
        """Forward ProxyWorker event with 1:1 parity to local schema."""
        from datetime import datetime

        # Normalize timestamp to ISO format (same as local)
        if "timestamp" in event_data and event_data["timestamp"]:
            ts = datetime.fromtimestamp(event_data["timestamp"], tz=UTC).isoformat()
        else:
            ts = datetime.now(UTC).isoformat()

        # Build event matching LocalAdapter schema exactly
        event_name = event_data.get("name", event_data.get("event"))
        event_payload = dict(event_data.get("data") or {})

        if event_name == "driver_file_verified":
            event_payload = self._augment_driver_file_event(event_payload)

        event_dict = {
            "ts": ts,
            "session": self.session_id,
            "event": event_name,
            **event_payload,
        }

        # Write to host events.jsonl
        if hasattr(self, "context") and self.context:
            events_file = self.context.logs_dir / "events.jsonl"
            try:
                with open(events_file, "a") as f:
                    f.write(json.dumps(event_dict) + "\n")
            except Exception as e:
                logging.warning(f"Failed to forward event to host: {e}")

    def _augment_driver_file_event(self, event_data: dict[str, Any]) -> dict[str, Any]:
        """Enrich driver_file_verified events with host-side verification results."""

        remote_path = event_data.get("path")
        if not remote_path:
            return {**event_data, "host_error": "missing_path", "match": False, "sha256_match": False}

        repo_root = Path(__file__).resolve().parents[2]
        relative_path = remote_path
        sandbox_prefix = "/home/user/"
        if remote_path.startswith(sandbox_prefix):
            relative_path = remote_path[len(sandbox_prefix) :]
        else:
            relative_path = remote_path.lstrip("/")

        local_path = repo_root / relative_path

        with contextlib.suppress(FileNotFoundError):
            local_path = local_path.resolve()

        if not local_path.exists():
            logging.warning(f"Host driver file missing for verification: {local_path}")
            return {
                **event_data,
                "host_error": "missing",
                "host_path": str(local_path),
                "match": False,
                "sha256_match": False,
            }

        try:
            size_bytes = local_path.stat().st_size
            sha256 = hashlib.sha256()
            with open(local_path, "rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    if not chunk:
                        break
                    sha256.update(chunk)

            host_sha = sha256.hexdigest()
        except OSError as exc:
            logging.warning(f"Failed to hash host driver file {local_path}: {exc}")
            return {
                **event_data,
                "host_error": str(exc),
                "host_path": str(local_path),
                "match": False,
                "sha256_match": False,
            }

        remote_sha = event_data.get("sha256")
        match = bool(remote_sha) and remote_sha == host_sha
        if not match:
            logging.error(
                "Driver file SHA mismatch for %s: sandbox=%s host=%s",
                remote_path,
                remote_sha,
                host_sha,
            )

        return {
            **event_data,
            "host_path": str(local_path),
            "host_sha256": host_sha,
            "host_size_bytes": size_bytes,
            "match": match,
            "sha256_match": match,
        }

    def _forward_metric_to_host(self, metric_data: dict[str, Any]):
        """Forward ProxyWorker metric to host metrics.jsonl."""
        from osiris.core.session_logging import log_metric

        # Extract metric details
        metric_name = metric_data.get("name")
        value = metric_data.get("value")
        tags = metric_data.get("tags", {})
        unit = metric_data.get("unit")

        # Use the session logging system to write the metric
        # This ensures consistent format with local runs
        if metric_name and value is not None:
            kwargs = {}
            if tags and isinstance(tags, dict):
                # For metrics with step tags
                if "step" in tags:
                    kwargs["step_id"] = tags["step"]
                else:
                    # Pass other tags as-is
                    for k, v in tags.items():
                        kwargs[k] = v
            if unit:
                kwargs["unit"] = unit

            log_metric(metric_name, value, **kwargs)

    async def _fetch_status_from_sandbox(self) -> bool:
        """Attempt to fetch status.json from sandbox."""
        try:
            # Try to read status.json from sandbox
            status_path = f"/home/user/session/{self.session_id}/status.json"
            content = await self.sandbox.files.read(status_path)

            if content:
                # Write to host
                status_file = self.context.logs_dir / "status.json"
                with open(status_file, "w") as f:
                    f.write(content)
                return True
        except Exception as e:
            logging.warning(f"Could not fetch status.json from sandbox: {e}")

        return False

    def _write_fallback_status(self, context: ExecutionContext, last_stderr: str = ""):
        """Write fallback status.json when worker fails to provide one."""
        # Determine exit code and ok status based on tracked errors
        had_errors = getattr(self, "had_errors", True)  # Default to error if not tracked

        status = {
            "sandbox_id": self.sandbox_id if hasattr(self, "sandbox_id") else "unknown",
            "exit_code": 1 if had_errors else 0,
            "steps_completed": 0,
            "steps_total": (len(self.prepared_plan.get("steps", [])) if hasattr(self, "prepared_plan") else 0),
            "ok": not had_errors,
            "session_path": f"/home/user/session/{self.session_id}",
            "session_copied": False,
            "events_jsonl_exists": (context.logs_dir / "events.jsonl").exists(),
            "reason": ("Worker failed to write status.json" if had_errors else "Completed but status not written"),
            "last_stderr": last_stderr,
        }

        status_file = context.logs_dir / "status.json"
        with open(status_file, "w") as f:
            json.dump(status, f, indent=2)

    def _get_last_stderr_lines(self, n: int = 20) -> str:
        """Get last N lines of debug.log for error context."""
        try:
            debug_log = self.context.logs_dir / "debug.log"
            if debug_log.exists():
                lines = debug_log.read_text().split("\n")
                return "\n".join(lines[-n:])
        except Exception:
            pass
        return ""
