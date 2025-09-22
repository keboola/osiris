"""ProxyWorker - Runs inside E2B sandbox and executes pipeline steps.

This worker receives commands via stdin, executes drivers directly,
and streams results back via stdout.
"""

import json
import logging
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import core components
from osiris.core.driver import DriverRegistry
from osiris.core.execution_adapter import ExecutionContext
from osiris.remote.rpc_protocol import (
    CleanupCommand,
    CleanupResponse,
    ErrorMessage,
    EventMessage,
    ExecStepCommand,
    ExecStepResponse,
    MetricMessage,
    PingCommand,
    PingResponse,
    PrepareCommand,
    PrepareResponse,
    parse_command,
)


class ProxyWorker:
    """Worker that executes pipeline steps inside E2B sandbox."""

    def __init__(self):
        """Initialize the proxy worker."""
        self.session_id = None
        self.session_dir = None
        self.manifest = None
        self.driver_registry = None
        self.execution_context = None
        self.session_context = None
        self.step_count = 0
        self.total_rows = 0
        self.step_outputs = {}  # Cache outputs for downstream steps
        self.step_rows = {}  # Track rows per step for cleanup aggregation
        self.step_drivers = {}  # Track driver type per step

        # Set up stderr logging for debugging
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            stream=sys.stderr,
        )
        self.logger = logging.getLogger(__name__)

        # Log Python path for debugging
        self.logger.info(f"Python path: {sys.path}")
        self.logger.info(f"Working directory: {Path.cwd()}")

    def run(self):
        """Main loop - read commands from stdin and execute."""
        self.logger.info("ProxyWorker starting...")

        while True:
            try:
                # Read line from stdin
                line = sys.stdin.readline()
                if not line:
                    self.logger.info("No more input, exiting")
                    break

                # Parse and handle command
                try:
                    data = json.loads(line.strip())
                    command = parse_command(data)
                    self.logger.debug(f"Received command: {command.cmd}")

                    # Handle command and send response
                    response = self.handle_command(command)
                    if response:
                        self.send_response(response)

                except json.JSONDecodeError as e:
                    self.send_error(f"Invalid JSON: {e}")
                except ValueError as e:
                    self.send_error(f"Invalid command: {e}")
                except Exception as e:
                    self.send_error(f"Command failed: {e}", include_traceback=True)

            except KeyboardInterrupt:
                self.logger.info("Interrupted, exiting")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error: {e}", exc_info=True)
                self.send_error(f"Worker error: {e}", include_traceback=True)

    def handle_command(self, command) -> Optional[Any]:
        """Process a command and return response."""
        if isinstance(command, PrepareCommand):
            return self.handle_prepare(command)
        elif isinstance(command, ExecStepCommand):
            return self.handle_exec_step(command)
        elif isinstance(command, CleanupCommand):
            return self.handle_cleanup(command)
        elif isinstance(command, PingCommand):
            return self.handle_ping(command)
        else:
            raise ValueError(f"Unknown command type: {type(command)}")

    def handle_prepare(self, cmd: PrepareCommand) -> PrepareResponse:
        """Initialize session and load drivers."""
        self.session_id = cmd.session_id
        self.manifest = cmd.manifest
        self.allow_install_deps = getattr(cmd, "install_deps", False)
        self.execution_start = time.time()  # Track start time for status.json

        # Use the mounted session directory directly (no nested run_id)
        # E2B mounts host session dir to /home/user/session/<session_id>
        self.session_dir = Path(f"/home/user/session/{self.session_id}")
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # Write events and metrics directly to session root
        self.events_file = self.session_dir / "events.jsonl"
        self.metrics_file = self.session_dir / "metrics.jsonl"

        # Note: We don't use SessionContext here to avoid nested directories
        # Instead we'll write events/metrics directly
        self.session_context = None

        # Initialize execution context
        self.execution_context = ExecutionContext(
            session_id=self.session_id, base_path=self.session_dir
        )

        # Run dependency preflight check
        required_deps = self._get_required_dependencies()
        if required_deps:
            preflight_result = self._preflight_dependencies(required_deps)

            # Send dependency check event
            self.send_event(
                "dependency_check",
                missing=preflight_result["missing"],
                present=preflight_result["present"],
            )

            # If missing dependencies found
            if preflight_result["missing"]:
                if self.allow_install_deps:
                    # Install missing dependencies
                    self.logger.info(
                        f"Installing missing dependencies: {preflight_result['missing']}"
                    )
                    install_success = self._install_dependencies(preflight_result["missing"])

                    if install_success:
                        # Re-check after installation
                        post_install_check = self._preflight_dependencies(required_deps)
                        self.send_event(
                            "dependency_installed",
                            now_present=post_install_check["present"],
                            still_missing=post_install_check["missing"],
                        )

                        if post_install_check["missing"]:
                            error_msg = f"Failed to install some dependencies: {post_install_check['missing']}"
                            self.logger.error(error_msg)
                            raise ValueError(error_msg)
                    else:
                        error_msg = "Failed to install dependencies"
                        self.logger.error(error_msg)
                        raise ValueError(error_msg)
                else:
                    # Fail with clear error message
                    error_msg = (
                        f"Missing required dependencies: {', '.join(preflight_result['missing'])}\n"
                        "To enable auto-install, use --e2b-install-deps or set OSIRIS_E2B_INSTALL_DEPS=1"
                    )
                    self.logger.error(error_msg)
                    raise ValueError(error_msg)

        # Initialize and register drivers explicitly
        self.driver_registry = DriverRegistry()
        self._register_drivers()

        # Get list of loaded drivers
        drivers_loaded = self.list_registered_drivers()

        # Emit run_start event with pipeline_id (before session_initialized)
        pipeline_id = None
        if self.manifest and "pipeline" in self.manifest:
            pipeline_id = self.manifest["pipeline"].get("id", "unknown")

        self.send_event(
            "run_start",
            pipeline_id=pipeline_id,
            manifest_path=f"session/{self.session_id}/manifest.json",
            profile=self.manifest.get("pipeline", {})
            .get("fingerprints", {})
            .get("profile", "default"),
        )

        # Send initialization event
        self.send_event(
            "session_initialized", session_id=self.session_id, drivers_loaded=drivers_loaded
        )

        # Send metrics
        steps_count = len(self.manifest.get("steps", []))
        self.send_metric("steps_total", steps_count)

        self.logger.info(f"Session {self.session_id} prepared with {len(drivers_loaded)} drivers")

        return PrepareResponse(
            session_id=self.session_id,
            session_dir=str(self.session_dir),
            drivers_loaded=drivers_loaded,
        )

    def handle_exec_step(self, cmd: ExecStepCommand) -> ExecStepResponse:
        """Execute a pipeline step using the appropriate driver."""
        step_id = cmd.step_id
        driver_name = cmd.driver

        # Load config from file if cfg_path is provided (file-only contract)
        if hasattr(cmd, "cfg_path") and cmd.cfg_path:
            cfg_file = self.session_dir / cmd.cfg_path
            if not cfg_file.exists():
                raise FileNotFoundError(f"Config file not found: {cfg_file}")

            # Read the raw bytes for SHA256 calculation
            import hashlib

            cfg_bytes = cfg_file.read_bytes()
            config = json.loads(cfg_bytes)

            # Calculate SHA256 from the actual file bytes read
            sha256 = hashlib.sha256(cfg_bytes).hexdigest()

            # Extract top-level keys (sorted)
            config_keys = sorted(config.keys())

            # Emit cfg_opened event with path, sha256, and keys
            self.send_event("cfg_opened", path=cmd.cfg_path, sha256=sha256, keys=config_keys)

            self.logger.info(
                f"Loaded config from {cmd.cfg_path} (sha256: {sha256[:8]}..., keys: {config_keys})"
            )
        else:
            # Fallback to inline config if provided (for backward compatibility)
            config = cmd.config if hasattr(cmd, "config") else {}

        # Resolve symbolic inputs from cached step outputs
        resolved_inputs = {}
        if hasattr(cmd, "inputs") and cmd.inputs:
            resolved_inputs = self._resolve_inputs(cmd.inputs)

        # Send start event
        self.send_event("step_start", step_id=step_id, driver=driver_name)

        start_time = time.time()

        try:
            # Create step artifacts directory (matching LocalAdapter behavior)
            artifacts_base = self.session_dir / "artifacts"
            step_artifacts_dir = artifacts_base / step_id
            step_artifacts_dir.mkdir(parents=True, exist_ok=True)
            self.logger.debug(
                f"Created artifacts directory for step {step_id}: {step_artifacts_dir}"
            )

            # Emit event for artifacts directory creation
            self.send_event(
                "artifacts_dir_created", step_id=step_id, relative_path=f"artifacts/{step_id}"
            )

            # Clean config for driver (strip meta keys) and save cleaned_config.json
            clean_config = config.copy()
            meta_keys_removed = []

            if "component" in clean_config:
                del clean_config["component"]
                meta_keys_removed.append("component")

            if "connection" in clean_config:
                del clean_config["connection"]
                meta_keys_removed.append("connection")

            # Emit event for config meta stripping if we removed any keys
            if meta_keys_removed:
                self.send_event(
                    "config_meta_stripped", step_id=step_id, keys_removed=meta_keys_removed
                )

            # Emit connection resolution events if we have a resolved connection
            # (for parity with local runs, even though resolution happened on host)
            if "resolved_connection" in clean_config:
                # Extract family and alias from the config (passed from E2B transparent proxy)
                family = config.get("_connection_family", None)
                alias = config.get("_connection_alias", None)

                # Try to infer family from driver name if not provided
                if not family:
                    if driver_name.startswith("mysql."):
                        family = "mysql"
                    elif driver_name.startswith("supabase."):
                        family = "supabase"
                    elif driver_name.startswith("postgres."):
                        family = "postgres"
                    elif "resolved_connection" in clean_config:
                        resolved = clean_config["resolved_connection"]
                        if "url" in resolved:
                            url = resolved.get("url", "")
                            if "mysql" in url:
                                family = "mysql"
                            elif "postgres" in url or "supabase" in url:
                                family = "supabase"

                    # Final fallback - infer from driver
                    if not family:
                        family = driver_name.split(".")[0] if "." in driver_name else "unknown"

                # Only emit events if we have at least the family
                if family and family != "unknown":
                    # Use actual alias or omit if not available (don't use "unknown")
                    event_data = {"step_id": step_id, "family": family}
                    if alias and alias != "unknown":
                        event_data["alias"] = alias

                    self.send_event("connection_resolve_start", **event_data)
                    self.send_event("connection_resolve_complete", **event_data, ok=True)

                    # Add metadata to resolved_connection for tracking
                    clean_config["resolved_connection"]["_family"] = family
                    if alias and alias != "unknown":
                        clean_config["resolved_connection"]["_alias"] = alias

            # Save cleaned config as artifact (with masked secrets)
            cleaned_config_path = step_artifacts_dir / "cleaned_config.json"
            artifact_config = clean_config.copy()
            if "resolved_connection" in artifact_config:
                # Mask sensitive fields in resolved connection
                conn = artifact_config["resolved_connection"].copy()
                for key in ["password", "key", "token", "secret"]:
                    if key in conn:
                        conn[key] = "***MASKED***"
                artifact_config["resolved_connection"] = conn

            with open(cleaned_config_path, "w") as f:
                json.dump(artifact_config, f, indent=2)

            self.logger.debug(f"Created artifact: {cleaned_config_path}")
            self.send_event(
                "artifact_created",
                step_id=step_id,
                artifact_type="cleaned_config",
                path=str(cleaned_config_path.relative_to(self.session_dir)),
            )

            # Get driver from registry
            driver = self.driver_registry.get(driver_name)
            if not driver:
                raise ValueError(f"Driver not found: {driver_name}")

            # Create a simple context object with artifacts directory and metrics support
            class SimpleContext:
                def __init__(self, artifacts_dir, worker):
                    self.artifacts_dir = artifacts_dir
                    self.worker = worker

                def log_metric(self, name, value, **tags):
                    """Forward metrics to worker for emission."""
                    self.worker.send_metric(name, value, tags=tags)

            ctx = SimpleContext(step_artifacts_dir, self)

            # Remove metadata fields that were added for tracking before passing to driver
            driver_config = clean_config.copy()
            driver_config.pop("_connection_family", None)
            driver_config.pop("_connection_alias", None)

            # Execute driver
            self.logger.info(f"Executing step {step_id} with driver {driver_name}")
            result = driver.run(
                step_id=step_id,
                config=driver_config,  # Use cleaned config without metadata
                inputs=resolved_inputs,
                ctx=ctx,
            )

            # Cache outputs for downstream steps by step_id
            # IMPORTANT: Keep DataFrames in memory but DO NOT serialize them
            if result and isinstance(result, dict):
                self.step_outputs[step_id] = result

            # Extract metrics from result (if any)
            # Extractors return {"df": DataFrame} and we count rows as rows_processed
            # Writers emit rows_written via ctx.log_metric during execution
            rows_processed = 0
            if result:
                # Check for explicit rows_processed key
                if "rows_processed" in result:
                    rows_processed = result["rows_processed"]
                # For extractors, count DataFrame rows
                elif "df" in result:
                    try:
                        import pandas as pd

                        if isinstance(result["df"], pd.DataFrame):
                            rows_processed = len(result["df"])
                            # Emit rows_read for extractors specifically (ONLY with step tag)
                            if driver_name.endswith(".extractor"):
                                self.send_metric(
                                    "rows_read", rows_processed, tags={"step": step_id}
                                )
                                # DO NOT emit untagged rows_read metric
                    except Exception:
                        pass

            # Track driver type and rows for this step
            self.step_drivers[step_id] = driver_name

            # For writer steps, get actual written count
            rows_written = 0
            if driver_name.endswith(".writer"):
                # Try to get actual written count from driver result or input DataFrame
                if rows_processed > 0:
                    rows_written = rows_processed
                elif resolved_inputs and "df" in resolved_inputs:
                    try:
                        import pandas as pd

                        if isinstance(resolved_inputs["df"], pd.DataFrame):
                            rows_written = len(resolved_inputs["df"])
                    except Exception:
                        pass
                # Track rows for this writer step
                self.step_rows[step_id] = rows_written
                # Writers contribute to total_rows
                self.total_rows += rows_written
            else:
                # Track rows for extractor/transform steps
                self.step_rows[step_id] = rows_processed
                # Non-writers don't contribute to total_rows anymore
                # self.total_rows += rows_processed  # REMOVED

            # Update step counter
            self.step_count += 1

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Send metrics
            self.send_metric("steps_completed", self.step_count)
            if rows_processed > 0:
                self.send_metric("rows_processed", rows_processed, tags={"step": step_id})
            self.send_metric("step_duration_ms", duration_ms, tags={"step": step_id})

            # Send completion event with correct row count
            # Writers report actual written count, extractors report extracted count
            completion_rows = rows_written if driver_name.endswith(".writer") else rows_processed
            self.send_event(
                "step_complete",
                step_id=step_id,
                rows_processed=completion_rows,
                duration_ms=duration_ms,
            )

            self.logger.info(
                f"Step {step_id} completed: {rows_processed} rows in {duration_ms:.2f}ms"
            )

            # CRITICAL: Return response WITHOUT DataFrames - only JSON-serializable data
            # For RPC response, writers should report actual written count
            rpc_rows = rows_written if driver_name.endswith(".writer") else rows_processed
            return ExecStepResponse(
                step_id=step_id,
                rows_processed=rpc_rows,  # Writers report written count in RPC response
                outputs={},  # Empty dict instead of the full result containing DataFrames
                duration_ms=duration_ms,
            )

        except Exception as e:
            # Send error event with enhanced error info
            self.send_event(
                "step_failed",
                step_id=step_id,
                driver=driver_name,
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
            )

            self.logger.error(f"Step {step_id} failed: {e}", exc_info=True)

            # Return error response with enhanced info
            return ExecStepResponse(
                step_id=step_id,
                rows_processed=0,
                outputs={},
                duration_ms=(time.time() - start_time) * 1000,
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
            )

    def handle_cleanup(self, cmd: CleanupCommand) -> CleanupResponse:
        """Cleanup session resources and write final status."""
        self.send_event("cleanup_start")

        # Calculate correct total_rows based on writer-only aggregation
        sum_rows_written = 0
        sum_rows_read = 0

        if hasattr(self, "step_drivers") and hasattr(self, "step_rows"):
            for step_id, driver_name in self.step_drivers.items():
                rows = self.step_rows.get(step_id, 0)
                if driver_name.endswith(".writer"):
                    sum_rows_written += rows
                elif driver_name.endswith(".extractor"):
                    sum_rows_read += rows

        # Use writers-only sum if available, else fall back to extractors
        final_total_rows = sum_rows_written if sum_rows_written > 0 else sum_rows_read

        try:
            # Ensure metrics.jsonl exists even if empty
            if hasattr(self, "metrics_file") and self.metrics_file:
                if not self.metrics_file.exists():
                    # Touch the file with an initial event
                    try:
                        with open(self.metrics_file, "w") as f:
                            initial_metric = {
                                "name": "session_initialized",
                                "value": 1,
                                "timestamp": time.time(),
                            }
                            f.write(json.dumps(initial_metric) + "\n")
                    except Exception as e:
                        self.logger.warning(f"Failed to create metrics file: {e}")
        finally:
            # ALWAYS write status.json, even on failure
            self._write_final_status()

            # Clear cached outputs
            self.step_outputs.clear()

        self.send_event(
            "cleanup_complete", steps_executed=self.step_count, total_rows=final_total_rows
        )

        self.logger.info(
            f"Session {self.session_id} cleaned up - total_rows={final_total_rows} (writers={sum_rows_written}, extractors={sum_rows_read})"
        )

        return CleanupResponse(
            session_id=self.session_id, steps_executed=self.step_count, total_rows=final_total_rows
        )

    def handle_ping(self, cmd: PingCommand) -> PingResponse:
        """Handle ping command for health check."""
        return PingResponse(timestamp=time.time(), echo=cmd.data)

    def send_response(self, response):
        """Send a response to the host."""
        msg = response.model_dump(exclude_none=True)
        print(json.dumps(msg), flush=True)

    def send_event(self, event_name: str, **kwargs):
        """Send an event to the host and write to events file."""
        msg = EventMessage(name=event_name, timestamp=time.time(), data=kwargs)
        event_data = msg.model_dump()

        # Send to stdout for real-time monitoring
        print(json.dumps(event_data), flush=True)

        # Also write to events.jsonl if file is set up
        if hasattr(self, "events_file") and self.events_file:
            try:
                with open(self.events_file, "a") as f:
                    f.write(json.dumps(event_data) + "\n")
            except Exception as e:
                self.logger.warning(f"Failed to write event to file: {e}")

    def send_metric(self, metric_name: str, value: Any, tags: Optional[Dict[str, str]] = None):
        """Send a metric to the host and write to metrics file."""
        msg = MetricMessage(name=metric_name, value=value, timestamp=time.time(), tags=tags)
        metric_data = msg.model_dump(exclude_none=True)

        # Send to stdout for real-time monitoring
        print(json.dumps(metric_data), flush=True)

        # Also write to metrics.jsonl if file is set up
        if hasattr(self, "metrics_file") and self.metrics_file:
            try:
                with open(self.metrics_file, "a") as f:
                    f.write(json.dumps(metric_data) + "\n")
            except Exception as e:
                self.logger.warning(f"Failed to write metric to file: {e}")

    def send_error(self, error_msg: str, include_traceback: bool = False):
        """Send an error to the host."""
        context = {}
        if include_traceback:
            context["traceback"] = traceback.format_exc()

        msg = ErrorMessage(
            error=error_msg, timestamp=time.time(), context=context if context else None
        )
        print(json.dumps(msg.model_dump(exclude_none=True)), flush=True)

    def _register_drivers(self):
        """Register known drivers explicitly for M1f."""
        # Import and register MySQL extractor
        try:
            from osiris.drivers.mysql_extractor_driver import MySQLExtractorDriver

            self.driver_registry.register("mysql.extractor", lambda: MySQLExtractorDriver())
            self.logger.info("Registered driver: mysql.extractor")
            self.send_event("driver_registered", driver="mysql.extractor", status="success")
        except ImportError as e:
            self.logger.warning(f"Failed to import MySQLExtractorDriver: {e}")
            self.send_event("driver_registration_failed", driver="mysql.extractor", error=str(e))

        # Import and register filesystem CSV writer
        try:
            from osiris.drivers.filesystem_csv_writer_driver import FilesystemCsvWriterDriver

            self.driver_registry.register(
                "filesystem.csv_writer", lambda: FilesystemCsvWriterDriver()
            )
            self.logger.info("Registered driver: filesystem.csv_writer")
            self.send_event("driver_registered", driver="filesystem.csv_writer", status="success")
        except ImportError as e:
            self.logger.warning(f"Failed to import FilesystemCsvWriterDriver: {e}")
            self.send_event(
                "driver_registration_failed", driver="filesystem.csv_writer", error=str(e)
            )

        # Import and register Supabase writer if available
        try:
            from osiris.drivers.supabase_writer_driver import SupabaseWriterDriver

            self.driver_registry.register("supabase.writer", lambda: SupabaseWriterDriver())
            self.logger.info("Registered driver: supabase.writer")
            self.send_event("driver_registered", driver="supabase.writer", status="success")
        except ImportError as e:
            # Check if supabase is actually needed in the plan
            steps = self.manifest.get("steps", []) if hasattr(self, "manifest") else []
            needs_supabase = any(step.get("driver") == "supabase.writer" for step in steps)

            if needs_supabase:
                error_msg = (
                    f"Supabase driver unavailable: {e}. "
                    f"Try: --e2b-install-deps or include supabase deps in your image."
                )
                self.logger.error(error_msg)
                self.send_event(
                    "driver_registration_failed", driver="supabase.writer", error=str(e)
                )

                # If we need supabase and auto-install is enabled, try to install
                if hasattr(self, "allow_install_deps") and self.allow_install_deps:
                    self.logger.info("Attempting to install supabase package...")
                    if self._install_dependencies(["supabase"]):
                        # Retry registration
                        try:
                            from osiris.drivers.supabase_writer_driver import SupabaseWriterDriver

                            self.driver_registry.register(
                                "supabase.writer", lambda: SupabaseWriterDriver()
                            )
                            self.logger.info("Registered driver: supabase.writer (after install)")
                            self.send_event(
                                "driver_registered",
                                driver="supabase.writer",
                                status="success_after_install",
                            )
                        except ImportError as e2:
                            self.logger.error(
                                f"Still unable to register supabase.writer after install: {e2}"
                            )
                            # Will fail later when trying to execute a step that needs it
                    else:
                        self.logger.error("Failed to install supabase dependencies")
            else:
                # Supabase not needed for this pipeline
                self.logger.debug(f"Supabase writer not available (not needed): {e}")

        # Log all registered drivers for diagnostics
        registered = self.list_registered_drivers()
        self.logger.info(f"Drivers registered: {registered}")
        self.send_event("drivers_registered", drivers=registered)

    def list_registered_drivers(self) -> list:
        """Get list of registered driver names."""
        return sorted(self.driver_registry._drivers.keys())

    def _get_required_dependencies(self) -> Dict[str, List[str]]:
        """Get required dependencies based on drivers used in the plan.

        Returns:
            Dict mapping driver name to list of required modules
        """
        # Map of driver to required modules
        driver_deps = {
            "mysql.extractor": ["sqlalchemy", "pandas", "pymysql"],
            "filesystem.csv_writer": ["pandas"],
            "supabase.writer": ["supabase", "pandas"],
        }

        # Find which drivers are used in the plan
        required = {}
        for step in self.manifest.get("steps", []):
            driver = step.get("driver", step.get("type"))
            if driver in driver_deps:
                required[driver] = driver_deps[driver]

        return required

    def _preflight_dependencies(self, required_deps: Dict[str, List[str]]) -> Dict[str, List[str]]:
        """Check if required modules are importable.

        Args:
            required_deps: Dict of driver name to list of required modules

        Returns:
            Dict with 'missing' and 'present' lists
        """
        missing = []
        present = []

        # Get unique list of all required modules
        all_modules = set()
        for modules in required_deps.values():
            all_modules.update(modules)

        # Try importing each module
        for module_name in all_modules:
            try:
                __import__(module_name)
                present.append(module_name)
                self.logger.debug(f"Module {module_name} is available")
            except ImportError:
                missing.append(module_name)
                self.logger.debug(f"Module {module_name} is missing")

        return {"missing": missing, "present": present}

    def _resolve_inputs(self, inputs_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve symbolic input references to actual values.

        Args:
            inputs_spec: Input specification with symbolic references
                        e.g., {"df": {"from_step": "extract-actors", "key": "df"}}

        Returns:
            Resolved inputs with actual values from cached outputs
        """
        resolved = {}

        for input_key, ref in inputs_spec.items():
            if isinstance(ref, dict) and "from_step" in ref:
                from_step = ref["from_step"]
                from_key = ref.get("key", "df")  # Default to "df" if not specified

                # Look up the output from the referenced step
                if from_step in self.step_outputs:
                    step_output = self.step_outputs[from_step]
                    if isinstance(step_output, dict) and from_key in step_output:
                        resolved[input_key] = step_output[from_key]
                        self.logger.debug(
                            f"Resolved input '{input_key}' from step '{from_step}', key '{from_key}'"
                        )
                    else:
                        self.logger.warning(
                            f"Key '{from_key}' not found in outputs from step '{from_step}'"
                        )
                else:
                    self.logger.warning(f"No outputs cached for step '{from_step}'")
            else:
                # Not a symbolic reference, use as-is
                resolved[input_key] = ref

        return resolved

    def _write_final_status(self):
        """Write final status.json with execution summary matching local contract."""
        if not hasattr(self, "session_dir") or not self.session_dir:
            return

        status_file = self.session_dir / "status.json"

        # Determine success based on steps completed vs total
        steps_total = len(self.manifest.get("steps", [])) if self.manifest else 0
        success = self.step_count == steps_total

        # Build status matching local contract
        import os

        sandbox_id = os.environ.get("E2B_SANDBOX_ID", "e2b")  # Get from env or default to "e2b"

        status = {
            "sandbox_id": sandbox_id,
            "exit_code": 0 if success else 1,
            "steps_completed": self.step_count,
            "steps_total": steps_total,
            "ok": success,
            "session_path": str(self.session_dir),
            "session_copied": True,  # E2B copies to host
            "events_jsonl_exists": (
                (self.session_dir / "events.jsonl").exists() if self.session_dir else False
            ),
            "reason": "" if success else f"Completed {self.step_count}/{steps_total} steps",
        }

        try:
            with open(status_file, "w") as f:
                json.dump(status, f, indent=2)
            self.logger.info(f"Written status.json to {status_file}")
        except Exception as e:
            self.logger.error(f"Failed to write status.json: {e}")
            # Try to at least write a minimal status
            try:
                minimal_status = {
                    "sandbox_id": sandbox_id,  # Use the same sandbox_id from above
                    "exit_code": 1,
                    "steps_completed": self.step_count,
                    "steps_total": 0,
                    "ok": False,
                    "reason": f"Failed to write status: {e}",
                }
                with open(status_file, "w") as f:
                    json.dump(minimal_status, f)
            except:
                pass  # Give up if we can't write at all

    def _install_dependencies(self, missing_modules: List[str]) -> bool:
        """Install missing dependencies in the sandbox.

        Args:
            missing_modules: List of module names to install

        Returns:
            True if installation succeeded
        """
        import subprocess
        import sys

        try:
            # Check if we have a requirements file
            requirements_file = self.session_dir / "requirements_e2b.txt"

            if requirements_file.exists():
                # Install from requirements file
                self.logger.info(f"Installing from {requirements_file}")
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", str(requirements_file)],
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout
                )
            else:
                # Install specific modules
                self.logger.info(f"Installing modules: {missing_modules}")
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install"] + missing_modules,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout
                )

            if result.returncode == 0:
                self.logger.info("Dependency installation completed successfully")
                # Log installed versions
                for line in result.stdout.split("\n"):
                    if "Successfully installed" in line:
                        self.logger.info(f"Installed: {line}")
                return True
            else:
                self.logger.error(f"Dependency installation failed: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            self.logger.error("Dependency installation timed out after 5 minutes")
            return False
        except Exception as e:
            self.logger.error(f"Error installing dependencies: {e}")
            return False

    def _resolve_inputs(self, inputs_spec: dict) -> dict:
        """Resolve symbolic input references to actual Python objects.

        Args:
            inputs_spec: Dictionary with symbolic references like:
                {"df": {"from_step": "extract-actors", "key": "df"}}

        Returns:
            Dictionary with resolved Python objects from step_outputs cache
        """
        resolved = {}

        for input_key, ref in inputs_spec.items():
            if isinstance(ref, dict) and "from_step" in ref:
                from_step = ref["from_step"]
                from_key = ref.get("key", "df")  # Default to "df" if not specified

                # Look up the cached output from the referenced step
                if from_step in self.step_outputs:
                    step_output = self.step_outputs[from_step]
                    if from_key in step_output:
                        resolved[input_key] = step_output[from_key]
                        self.logger.debug(f"Resolved input {input_key} from {from_step}.{from_key}")
                    else:
                        available_keys = list(step_output.keys())
                        error_msg = (
                            f"Input key '{from_key}' not found in outputs from step '{from_step}'. "
                            f"Available keys: {available_keys}"
                        )
                        self.logger.error(error_msg)
                        self.send_event(
                            "input_resolution_failed",
                            input_key=input_key,
                            from_step=from_step,
                            requested_key=from_key,
                            available_keys=available_keys,
                        )
                        raise KeyError(error_msg)
                else:
                    available_steps = list(self.step_outputs.keys())
                    error_msg = (
                        f"Step '{from_step}' not found in cached outputs. "
                        f"Available steps: {available_steps}"
                    )
                    self.logger.error(error_msg)
                    self.send_event(
                        "input_resolution_failed",
                        input_key=input_key,
                        from_step=from_step,
                        available_steps=available_steps,
                    )
                    raise KeyError(error_msg)

        # Log successful input resolution for observability
        if resolved:
            from_steps = list(
                set(
                    ref.get("from_step", "unknown")
                    for ref in inputs_spec.values()
                    if isinstance(ref, dict)
                )
            )
            resolved_keys = list(resolved.keys())

            self.send_event("inputs_resolved", keys=resolved_keys, from_steps=from_steps)
            self.logger.debug(f"Resolved {len(resolved)} inputs from {from_steps}")

        return resolved


if __name__ == "__main__":
    worker = ProxyWorker()
    worker.run()
