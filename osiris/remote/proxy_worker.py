"""ProxyWorker - Runs inside E2B sandbox and executes pipeline steps.

This worker receives commands via stdin, executes drivers directly,
and streams results back via stdout.
"""

from collections.abc import Iterable, Mapping
import copy
import hashlib
import importlib
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - optional for older runtimes
    tomllib = None  # type: ignore[assignment]

# Import core components
from osiris.components.registry import ComponentRegistry
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


class _E2BLogSanitizer:
    """Sanitize log payloads to prevent secret leakage."""

    _AUTH_JSON_RE = re.compile(r'(?i)(["\']Authorization["\']\s*:\s*["\'])(Bearer\s+[^"\']+)(["\'])')
    _AUTH_PLAIN_RE = re.compile(r"(?i)(Authorization\s*[:=]\s*)(Bearer\s+[A-Za-z0-9\-._~+/=]+)")
    _APIKEY_JSON_RE = re.compile(r'(?i)(["\'](?:x-)?api[-_]?key["\']\s*:\s*["\'])([^"\']+)(["\'])')
    _APIKEY_PLAIN_RE = re.compile(r'(?i)((?:x-)?api[-_]?key\s*[:=]\s*)([^\s"\']+)')
    _JWT_TOKEN_RE = re.compile(r"eyJhbGciOi[A-Za-z0-9_\-\.]*")
    _PG_DSN_RE = re.compile(r"(postgres(?:ql)?://[^:/?#]+:)([^@]+)(@)")

    _SENSITIVE_HEADER_TOKENS = {
        "authorization",
        "proxyauthorization",
        "apikey",
        "xapikey",
        "xsupabaseapikey",
    }

    def sanitize_text(self, text: str) -> str:
        if not text:
            return text

        text = self._AUTH_JSON_RE.sub(lambda m: f"{m.group(1)}**REDACTED**{m.group(3)}", text)
        text = self._AUTH_PLAIN_RE.sub(lambda m: f"{m.group(1)}**REDACTED**", text)
        text = self._APIKEY_JSON_RE.sub(lambda m: f"{m.group(1)}**REDACTED**{m.group(3)}", text)
        text = self._APIKEY_PLAIN_RE.sub(lambda m: f"{m.group(1)}**REDACTED**", text)
        text = self._PG_DSN_RE.sub(lambda m: f"{m.group(1)}***{m.group(3)}", text)
        text = self._JWT_TOKEN_RE.sub("**REDACTED**", text)
        return text

    def sanitize_structure(self, value: Any, *, key_hint: str | None = None) -> Any:
        if isinstance(value, dict):
            return {k: self.sanitize_structure(v, key_hint=self._canonical_key(k)) for k, v in value.items()}
        if isinstance(value, list):
            return [self.sanitize_structure(item, key_hint=key_hint) for item in value]
        if isinstance(value, tuple):
            if len(value) == 2:
                return (
                    value[0],
                    self.sanitize_structure(value[1], key_hint=self._canonical_key(value[0])),
                )
            return tuple(self.sanitize_structure(item, key_hint=key_hint) for item in value)
        if isinstance(value, bytes):
            decoded = value.decode("utf-8", errors="replace")
            return self.sanitize_text(decoded)
        if isinstance(value, str):
            if key_hint and self._is_sensitive_header_key(key_hint):
                return "**REDACTED**"
            if key_hint == "pg_dsn":
                return self._sanitize_pg_dsn(value)
            return self.sanitize_text(value)
        return value

    def _sanitize_pg_dsn(self, value: str) -> str:
        return self._PG_DSN_RE.sub(lambda m: f"{m.group(1)}***{m.group(3)}", value)

    @staticmethod
    def _canonical_key(key: Any) -> str:
        text = key.decode("utf-8", errors="replace") if isinstance(key, bytes) else str(key)
        return text.strip(" '\"").lower()

    def _is_sensitive_header_key(self, key: str) -> bool:
        token = key.lstrip(":").replace("-", "").replace("_", "")
        return token in self._SENSITIVE_HEADER_TOKENS


class _E2BRedactionFilter(logging.Filter):
    """Logging filter that sanitizes records before emission."""

    def __init__(self, sanitizer: _E2BLogSanitizer):
        super().__init__(name="e2b_redaction")
        self._sanitizer = sanitizer

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        sanitized = self._sanitizer.sanitize_text(message)
        if sanitized != message:
            record.msg = sanitized
            record.args = ()
        return True


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
        self.step_io: dict[str, dict[str, Any]] = {}
        self.component_specs: dict[str, dict[str, Any]] = {}
        self.component_secret_paths: dict[str, list[list[str]]] = {}
        self.driver_summary = None
        self.artifacts_root: Path | None = None
        self.component_registry: ComponentRegistry | None = None

        # Set up stderr logging for debugging
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            stream=sys.stderr,
        )
        self.logger = logging.getLogger(__name__)
        self._log_sanitizer = _E2BLogSanitizer()
        self.enable_redaction = self._should_enable_redaction()
        if self.enable_redaction:
            self._install_log_redaction()

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

    def handle_command(self, command) -> Any | None:
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

    @staticmethod
    def _should_enable_redaction() -> bool:
        value = os.getenv("E2B_LOG_REDACT", "1")
        return value.strip().lower() not in {"0", "false", "off", "no"}

    def _install_log_redaction(self) -> None:
        root_logger = logging.getLogger()
        if not any(isinstance(f, _E2BRedactionFilter) for f in root_logger.filters):
            root_logger.addFilter(_E2BRedactionFilter(self._log_sanitizer))

        for handler in root_logger.handlers:
            if not any(isinstance(f, _E2BRedactionFilter) for f in handler.filters):
                handler.addFilter(_E2BRedactionFilter(self._log_sanitizer))

        for logger_name in ("httpx", "httpcore", "httpcore.http11", "httpcore.h11", "httpcore.h2", "httpcore.hpack"):
            logging.getLogger(logger_name).setLevel(logging.INFO)

    def handle_prepare(self, cmd: PrepareCommand) -> PrepareResponse:  # noqa: PLR0915
        """Initialize session and load drivers."""
        self.session_id = cmd.session_id
        self.manifest = cmd.manifest or {}
        self.allow_install_deps = bool(getattr(cmd, "install_deps", False))
        self.execution_start = time.time()

        # Use the mounted session directory directly (no nested run_id)
        self.session_dir = Path(f"/home/user/session/{self.session_id}")
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # Prepare artifact layout and logging endpoints
        self.artifacts_root = self.session_dir / "artifacts"
        self.artifacts_root.mkdir(parents=True, exist_ok=True)
        self.events_file = self.session_dir / "events.jsonl"
        self.metrics_file = self.session_dir / "metrics.jsonl"
        self.session_context = None  # Avoid nested directories in sandbox
        self.execution_context = ExecutionContext(session_id=self.session_id, base_path=self.session_dir)

        # Load component specifications once per session
        self.component_registry = ComponentRegistry()
        self.component_specs = self.component_registry.load_specs()
        self.component_secret_paths = self._build_secret_index(self.component_specs)

        # Register drivers using ComponentRegistry as the single source of truth
        self.driver_registry = DriverRegistry()
        allowlist = self._env_set("OSIRIS_E2B_DRIVER_ALLOWLIST")
        denylist = self._env_set("OSIRIS_E2B_DRIVER_DENYLIST")
        mode_filter = self._mode_filter()

        self.driver_summary = self.driver_registry.populate_from_component_specs(
            self.component_specs,
            modes=mode_filter,
            allow=allowlist,
            deny=denylist,
            verify_import=False,
            strict=False,
            on_success=lambda component, driver: self.logger.debug(f"Registered driver {component} -> {driver}"),
        )

        for component_name, reason in self.driver_summary.skipped.items():
            self.logger.debug(f"Component {component_name} skipped during driver registration: {reason}")

        for component_name, error_msg in self.driver_summary.errors.items():
            self.logger.error(f"Driver registration issue for {component_name}: {error_msg}")
            self.send_event("driver_registration_failed", driver=component_name, error=error_msg)

        required_modules, required_packages = self._collect_runtime_requirements(self.driver_summary.registered.keys())

        missing_modules, present_modules = self._check_runtime_dependencies(required_modules)
        self.send_event(
            "dependency_check",
            required=sorted(required_modules),
            present=present_modules,
            missing=missing_modules,
        )

        if missing_modules:
            if self.allow_install_deps:
                install_details = self._install_requirements(required_packages)
                missing_modules, present_modules = self._check_runtime_dependencies(required_modules)
                self.send_event(
                    "dependency_install_complete",
                    still_missing=missing_modules,
                    now_present=present_modules,
                    installed=install_details.get("installed", []),
                    log_path=install_details.get("log_relpath"),
                )

                if missing_modules:
                    error_msg = (
                        "Missing required dependencies after installation: " f"{', '.join(sorted(missing_modules))}"
                    )
                    self.logger.error(error_msg)
                    raise ValueError(error_msg)
            else:
                error_msg = (
                    "Missing required dependencies: "
                    f"{', '.join(sorted(missing_modules))}. "
                    "Enable auto-install with --e2b-install-deps or set OSIRIS_E2B_INSTALL_DEPS=1"
                )
                self.logger.error(error_msg)
                raise ValueError(error_msg)

        # Verify that drivers import successfully now that dependencies are satisfied
        import_results = self.driver_registry.validate_imports()
        degraded = {name: str(exc) for name, exc in import_results.items() if exc}
        if degraded:
            for driver_name, error_msg in degraded.items():
                self.send_event("driver_registration_failed", driver=driver_name, error=error_msg)
            error_msg = "Drivers failed to import: " + ", ".join(sorted(degraded))
            self.logger.error(error_msg)
            raise ValueError(error_msg)

        drivers_loaded = self.list_registered_drivers()
        for driver_name in drivers_loaded:
            impl_path = self.driver_summary.registered.get(driver_name, "")
            self.send_event(
                "driver_registered",
                driver=driver_name,
                implementation=impl_path,
                status="success",
            )

            if driver_name == "supabase.writer":
                self._emit_driver_file_verification(
                    driver_name=driver_name,
                    sandbox_path=Path("/home/user/osiris/drivers/supabase_writer_driver.py"),
                )

        self.driver_summary.compute_fingerprint()
        self.send_event(
            "drivers_registered",
            drivers=drivers_loaded,
            fingerprint=self.driver_summary.fingerprint,
        )

        # Emit run_start event with pipeline_id (before session_initialized)
        pipeline_id = None
        if self.manifest and "pipeline" in self.manifest:
            pipeline_id = self.manifest["pipeline"].get("id", "unknown")

        self.send_event(
            "run_start",
            pipeline_id=pipeline_id,
            manifest_path=f"session/{self.session_id}/manifest.json",
            profile=self.manifest.get("pipeline", {}).get("fingerprints", {}).get("profile", "default"),
        )

        # Send initialization event and baseline metrics
        self.send_event("session_initialized", session_id=self.session_id, drivers_loaded=drivers_loaded)

        steps_count = len(self.manifest.get("steps", []))
        self.send_metric("steps_total", steps_count)

        self.logger.info(
            f"Session {self.session_id} prepared with {len(drivers_loaded)} drivers (fingerprint {self.driver_summary.fingerprint})"
        )

        return PrepareResponse(
            session_id=self.session_id,
            session_dir=str(self.session_dir),
            drivers_loaded=drivers_loaded,
        )

    def handle_exec_step(self, cmd: ExecStepCommand) -> ExecStepResponse:  # noqa: PLR0915
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

            self.logger.info(f"Loaded config from {cmd.cfg_path} (sha256: {sha256[:8]}..., keys: {config_keys})")
        else:
            # Fallback to inline config if provided (for backward compatibility)
            config = cmd.config if hasattr(cmd, "config") else {}

        component_name = config.get("component") or driver_name

        # Resolve symbolic inputs from cached step outputs
        resolved_inputs, rows_in = self._resolve_inputs(getattr(cmd, "inputs", {}) or {}, step_id)
        if rows_in:
            self.send_metric("rows_in", rows_in, tags={"step": step_id})

        # Send start event
        self.send_event("step_start", step_id=step_id, driver=driver_name)

        start_time = time.time()

        try:
            # Create step artifacts directory (matching LocalAdapter behavior)
            artifacts_base = self.session_dir / "artifacts"
            step_artifacts_dir = artifacts_base / step_id
            step_artifacts_dir.mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"Created artifacts directory for step {step_id}: {step_artifacts_dir}")

            # Emit event for artifacts directory creation
            self.send_event("artifacts_dir_created", step_id=step_id, relative_path=f"artifacts/{step_id}")

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
                self.send_event("config_meta_stripped", step_id=step_id, keys_removed=meta_keys_removed)

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
                    clean_config.setdefault("resolved_connection", {})["_family"] = family
                    if alias and alias != "unknown":
                        clean_config["resolved_connection"]["_alias"] = alias

            # Save cleaned config as artifact (with masked secrets)
            cleaned_config_path = step_artifacts_dir / "cleaned_config.json"
            artifact_config = self._mask_config_for_artifact(component_name, clean_config)

            with open(cleaned_config_path, "w", encoding="utf-8") as f:
                json.dump(artifact_config, f, indent=2)

            self.logger.debug(f"Created artifact: {cleaned_config_path}")
            self._emit_artifact_event(cleaned_config_path, artifact_type="cleaned_config", step_id=step_id)

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

            cached_output: dict[str, Any] = {}
            force_spill = os.getenv("E2B_FORCE_SPILL", "").strip().lower() in {"1", "true", "yes"}

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

                        df_value = result["df"]
                        if isinstance(df_value, pd.DataFrame):
                            rows_processed = len(df_value)
                            if force_spill:
                                parquet_path = step_artifacts_dir / "output.parquet"
                                df_value.to_parquet(parquet_path)
                                self._emit_artifact_event(parquet_path, artifact_type="parquet", step_id=step_id)

                                schema_path = step_artifacts_dir / "schema.json"
                                try:
                                    schema = {column: str(dtype) for column, dtype in df_value.dtypes.items()}
                                    schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
                                    cached_output["schema_path"] = schema_path
                                    self._emit_artifact_event(schema_path, artifact_type="schema", step_id=step_id)
                                except Exception as exc:  # pragma: no cover - best effort
                                    self.logger.debug(f"Failed to write schema for {step_id}: {exc}")

                                cached_output["df_path"] = parquet_path
                                cached_output["spilled"] = True
                                # Drop the in-memory DataFrame reference
                                result["df"] = None
                            else:
                                cached_output["df"] = df_value
                                cached_output["spilled"] = False

                            if driver_name.endswith(".extractor"):
                                self.send_metric("rows_read", rows_processed, tags={"step": step_id})
                    except Exception as exc:
                        self.logger.error(f"Failed to cache DataFrame for step {step_id}: {exc}")

                # Copy non-DataFrame keys from result to cached_output
                if isinstance(result, dict):
                    for k, v in result.items():
                        if k != "df":  # Skip df as it's already saved to parquet
                            cached_output[k] = v

            # Track driver type and rows for this step
            self.step_drivers[step_id] = driver_name

            rows_out = rows_processed
            if driver_name.endswith(".writer"):
                df_input = resolved_inputs.get("df")
                if not rows_out and df_input is not None:
                    try:
                        import pandas as pd

                        if isinstance(df_input, pd.DataFrame):
                            rows_out = len(df_input)
                    except Exception:
                        pass
                self.step_rows[step_id] = rows_out
                self.total_rows += rows_out
                if rows_in and rows_out == 0:
                    raise ValueError(f"Writer step {step_id} produced zero rows but had {rows_in} input rows")
            else:
                self.step_rows[step_id] = rows_processed

            # Update step counter
            self.step_count += 1

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Send metrics
            self.send_metric("steps_completed", self.step_count)
            if rows_processed > 0:
                self.send_metric("rows_processed", rows_processed, tags={"step": step_id})
                self.send_metric("rows_out", rows_processed, tags={"step": step_id})
            self.send_metric("step_duration_ms", duration_ms, tags={"step": step_id})

            self.step_outputs[step_id] = cached_output
            artifact_paths = [str(cleaned_config_path.relative_to(self.session_dir))]
            if cached_output.get("df_path"):
                artifact_paths.append(str(cached_output["df_path"].relative_to(self.session_dir)))
            self.step_io[step_id] = {
                "driver": driver_name,
                "rows_in": rows_in,
                "rows_out": rows_out,
                "duration_ms": duration_ms,
                "status": "succeeded",
                "artifacts": artifact_paths,
            }

            # Send completion event with correct row count
            completion_rows = rows_out if driver_name.endswith(".writer") else rows_processed
            self.send_event(
                "step_complete",
                step_id=step_id,
                rows_processed=completion_rows,
                duration_ms=duration_ms,
            )

            self.logger.info(f"Step {step_id} completed: {rows_processed} rows in {duration_ms:.2f}ms")

            # CRITICAL: Return response WITHOUT DataFrames - only JSON-serializable data
            # For RPC response, writers should report actual written count
            rpc_rows = rows_out if driver_name.endswith(".writer") else rows_processed
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

            self.step_io[step_id] = {
                "driver": driver_name,
                "rows_in": rows_in,
                "rows_out": 0,
                "duration_ms": (time.time() - start_time) * 1000,
                "status": "failed",
                "error": str(e),
            }

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

            if self.step_io:
                try:
                    self._write_run_card()
                except Exception as card_error:  # pragma: no cover - best effort
                    self.logger.warning(f"Failed to write run card: {card_error}")
        finally:
            # ALWAYS write status.json, even on failure
            self._write_final_status()

            # Clear cached outputs
            self.step_outputs.clear()
            self.step_io.clear()

        self.send_event("cleanup_complete", steps_executed=self.step_count, total_rows=final_total_rows)

        self.logger.info(
            f"Session {self.session_id} cleaned up - total_rows={final_total_rows} (writers={sum_rows_written}, extractors={sum_rows_read})"
        )

        return CleanupResponse(session_id=self.session_id, steps_executed=self.step_count, total_rows=final_total_rows)

    def handle_ping(self, cmd: PingCommand) -> PingResponse:
        """Handle ping command for health check."""
        return PingResponse(timestamp=time.time(), echo=cmd.data)

    def send_response(self, response):
        """Send a response to the host."""
        msg = response.model_dump(exclude_none=True)
        if getattr(self, "enable_redaction", False):
            msg = self._log_sanitizer.sanitize_structure(msg)
        print(json.dumps(msg), flush=True)

    def send_event(self, event_name: str, **kwargs):
        """Send an event to the host and write to events file."""
        msg = EventMessage(name=event_name, timestamp=time.time(), data=kwargs)
        event_data = msg.model_dump()
        if getattr(self, "enable_redaction", False):
            event_data = self._log_sanitizer.sanitize_structure(event_data)

        # Send to stdout for real-time monitoring
        print(json.dumps(event_data), flush=True)

        # Also write to events.jsonl if file is set up
        if hasattr(self, "events_file") and self.events_file:
            try:
                with open(self.events_file, "a") as f:
                    f.write(json.dumps(event_data) + "\n")
            except Exception as e:
                self.logger.warning(f"Failed to write event to file: {e}")

    def send_metric(self, metric_name: str, value: Any, tags: dict[str, str] | None = None):
        """Send a metric to the host and write to metrics file."""
        msg = MetricMessage(name=metric_name, value=value, timestamp=time.time(), tags=tags)
        metric_data = msg.model_dump(exclude_none=True)
        if getattr(self, "enable_redaction", False):
            metric_data = self._log_sanitizer.sanitize_structure(metric_data)

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

        if getattr(self, "enable_redaction", False):
            error_msg = self._log_sanitizer.sanitize_text(error_msg)
            context = self._log_sanitizer.sanitize_structure(context)

        msg = ErrorMessage(error=error_msg, timestamp=time.time(), context=context if context else None)
        print(json.dumps(msg.model_dump(exclude_none=True)), flush=True)

    def _register_drivers(self):  # noqa: PLR0915
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

            self.driver_registry.register("filesystem.csv_writer", lambda: FilesystemCsvWriterDriver())
            self.logger.info("Registered driver: filesystem.csv_writer")
            self.send_event("driver_registered", driver="filesystem.csv_writer", status="success")
        except ImportError as e:
            self.logger.warning(f"Failed to import FilesystemCsvWriterDriver: {e}")
            self.send_event("driver_registration_failed", driver="filesystem.csv_writer", error=str(e))

        # Import and register GraphQL extractor
        try:
            from osiris.drivers.graphql_extractor_driver import GraphQLExtractorDriver

            self.driver_registry.register("graphql.extractor", lambda: GraphQLExtractorDriver())
            self.logger.info("Registered driver: graphql.extractor")
            self.send_event("driver_registered", driver="graphql.extractor", status="success")
        except ImportError as e:
            self.logger.warning(f"Failed to import GraphQLExtractorDriver: {e}")
            self.send_event("driver_registration_failed", driver="graphql.extractor", error=str(e))

        # Import and register Supabase writer if available
        try:
            from osiris.drivers.supabase_writer_driver import SupabaseWriterDriver

            self.driver_registry.register("supabase.writer", lambda: SupabaseWriterDriver())
            self.logger.info("Registered driver: supabase.writer")
            self.send_event("driver_registered", driver="supabase.writer", status="success")
            self._emit_driver_file_verification(
                driver_name="supabase.writer",
                sandbox_path=Path("/home/user/osiris/drivers/supabase_writer_driver.py"),
            )
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
                self.send_event("driver_registration_failed", driver="supabase.writer", error=str(e))

                # If we need supabase and auto-install is enabled, try to install
                if hasattr(self, "allow_install_deps") and self.allow_install_deps:
                    self.logger.info("Attempting to install supabase package...")
                    if self._install_dependencies(["supabase"]):
                        # Retry registration
                        try:
                            from osiris.drivers.supabase_writer_driver import SupabaseWriterDriver

                            self.driver_registry.register("supabase.writer", lambda: SupabaseWriterDriver())
                            self.logger.info("Registered driver: supabase.writer (after install)")
                            self.send_event(
                                "driver_registered",
                                driver="supabase.writer",
                                status="success_after_install",
                            )
                            self._emit_driver_file_verification(
                                driver_name="supabase.writer",
                                sandbox_path=Path("/home/user/osiris/drivers/supabase_writer_driver.py"),
                            )
                        except ImportError as e2:
                            self.logger.error(f"Still unable to register supabase.writer after install: {e2}")
                            # Will fail later when trying to execute a step that needs it
                    else:
                        self.logger.error("Failed to install supabase dependencies")
            else:
                # Supabase not needed for this pipeline
                self.logger.debug(f"Supabase writer not available (not needed): {e}")

        # Import and register DuckDB processor
        try:
            from osiris.drivers.duckdb_processor_driver import DuckDBProcessorDriver

            self.driver_registry.register("duckdb.processor", lambda: DuckDBProcessorDriver())
            self.logger.info("Registered driver: duckdb.processor")
            self.send_event("driver_registered", driver="duckdb.processor", status="success")
        except ImportError as e:
            # Check if DuckDB is needed in the plan
            steps = self.manifest.get("steps", []) if hasattr(self, "manifest") else []
            needs_duckdb = any(step.get("driver") == "duckdb.processor" for step in steps)

            if needs_duckdb:
                self.logger.warning(f"DuckDB driver needed but unavailable: {e}")

                # If auto-install is enabled, try to install duckdb
                if hasattr(self, "allow_install_deps") and self.allow_install_deps:
                    self.logger.info("Attempting to install duckdb package...")
                    if self._install_dependencies(["duckdb"]):
                        # Retry registration after install
                        try:
                            from osiris.drivers.duckdb_processor_driver import DuckDBProcessorDriver

                            self.driver_registry.register("duckdb.processor", lambda: DuckDBProcessorDriver())
                            self.logger.info("Registered driver: duckdb.processor (after install)")
                            self.send_event(
                                "driver_registered",
                                driver="duckdb.processor",
                                status="success_after_install",
                            )
                        except ImportError as e2:
                            self.logger.error(f"Still unable to register duckdb.processor after install: {e2}")
                            self.send_event(
                                "driver_registration_failed",
                                driver="duckdb.processor",
                                error=str(e2),
                            )
                    else:
                        self.logger.error("Failed to install duckdb package")
                        self.send_event("driver_registration_failed", driver="duckdb.processor", error=str(e))
                else:
                    self.send_event("driver_registration_failed", driver="duckdb.processor", error=str(e))
            else:
                self.logger.debug(f"DuckDB processor not available (not needed): {e}")

        # Log all registered drivers for diagnostics
        registered = self.list_registered_drivers()
        self.logger.info(f"Drivers registered: {registered}")
        self.send_event("drivers_registered", drivers=registered)

    def list_registered_drivers(self) -> list:
        """Get list of registered driver names."""
        return sorted(self.driver_registry._drivers.keys())

    def _emit_driver_file_verification(self, *, driver_name: str, sandbox_path: Path) -> None:
        """Emit an event with SHA256 + size for a driver file inside the sandbox."""

        if os.getenv("E2B_DRIVER_VERIFY", "1").strip().lower() in {"0", "false", "off", "no"}:
            self.logger.debug("driver_file_verified: verification disabled via E2B_DRIVER_VERIFY")
            return

        file_path = sandbox_path
        try:
            file_path = sandbox_path.resolve()
        except FileNotFoundError:
            file_path = sandbox_path

        if not file_path.exists():
            self.logger.warning(f"Driver file missing for verification: {sandbox_path}")
            self.send_event(
                "driver_file_verified",
                driver=driver_name,
                path=str(sandbox_path),
                error="not_found",
            )
            return

        sha256 = hashlib.sha256()
        size_bytes = 0
        try:
            with open(file_path, "rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    if not chunk:
                        break
                    sha256.update(chunk)
                    size_bytes += len(chunk)
        except OSError as exc:
            self.logger.error(f"Failed to hash driver file {sandbox_path}: {exc}")
            self.send_event(
                "driver_file_verified",
                driver=driver_name,
                path=str(sandbox_path),
                error="not_found",
            )
            return

        sha_hex = sha256.hexdigest()
        self.logger.debug(
            "driver_file_verified: emitting",
            extra={"path": str(file_path), "size": size_bytes, "sha": sha_hex[:12]},
        )

        self.send_event(
            "driver_file_verified",
            driver=driver_name,
            path=str(sandbox_path),
            sha256=sha_hex,
            size_bytes=size_bytes,
        )

    def _env_set(self, env_var: str) -> set[str]:
        raw = os.environ.get(env_var, "")
        return {value.strip() for value in raw.split(",") if value.strip()}

    def _mode_filter(self) -> set[str]:
        return {"extract", "transform", "write", "read"}

    def _collect_runtime_requirements(self, components: Iterable[str]) -> tuple[set[str], set[str]]:
        modules: set[str] = set()
        packages: set[str] = set()

        for component in components:
            spec = self.component_specs.get(component, {}) if hasattr(self, "component_specs") else {}
            runtime_cfg = (spec.get("x-runtime", {}) or {}).get("requirements", {}) or {}
            for module_name in runtime_cfg.get("imports", []) or []:
                modules.add(module_name)
            for package_name in runtime_cfg.get("packages", []) or []:
                packages.add(package_name)

        return modules, packages

    def _check_runtime_dependencies(self, modules: Iterable[str]) -> tuple[list[str], list[str]]:
        missing: list[str] = []
        present: list[str] = []

        for module_name in sorted({m for m in modules if m}):
            try:
                importlib.import_module(module_name)
            except ImportError:
                missing.append(module_name)
                self.logger.debug(f"Module {module_name} is missing")
            else:
                present.append(module_name)
                self.logger.debug(f"Module {module_name} is available")

        return missing, present

    def _install_requirements(self, packages: Iterable[str]) -> dict[str, Any]:
        artifacts_base = self.artifacts_root or (self.session_dir / "artifacts")
        system_dir = artifacts_base / "_system"
        system_dir.mkdir(parents=True, exist_ok=True)
        log_path = system_dir / "pip_install.log"

        commands: list[list[str]] = []
        lock_file = self.session_dir / "requirements.lock"
        uv_lock = self.session_dir / "uv.lock"
        requirements_file = self.session_dir / "requirements_e2b.txt"

        if lock_file.exists():
            commands.append([sys.executable, "-m", "pip", "install", "-r", str(lock_file)])
        elif uv_lock.exists():
            lock_packages = self._packages_from_uv_lock(uv_lock)
            if lock_packages:
                commands.append([sys.executable, "-m", "pip", "install", *lock_packages])

        if requirements_file.exists():
            commands.append([sys.executable, "-m", "pip", "install", "-r", str(requirements_file)])

        fallback_packages = sorted({pkg for pkg in packages if pkg})
        if fallback_packages and not requirements_file.exists():
            commands.append([sys.executable, "-m", "pip", "install", *fallback_packages])

        installed: list[str] = []

        if not commands:
            with open(log_path, "w", encoding="utf-8") as log_file:
                message = "No requirements files provided; skipping pip install\n"
                log_file.write(message)
            self._emit_artifact_event(log_path, artifact_type="pip_log")
            return {
                "installed": installed,
                "log_path": log_path,
                "log_relpath": str(log_path.relative_to(self.session_dir)),
            }

        with open(log_path, "w", encoding="utf-8") as log_file:
            for command in commands:
                log_file.write("$ " + " ".join(command) + "\n")
                log_file.flush()
                self.logger.info("Running %s", " ".join(command))
                result = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    cwd=str(self.session_dir),
                )
                if result.stdout:
                    log_file.write(result.stdout)
                if result.stderr:
                    log_file.write(result.stderr)
                log_file.flush()

                if result.returncode != 0:
                    raise ValueError(f"pip command failed ({' '.join(command)}), see {log_path.name} for details")

                for line in result.stdout.splitlines():
                    if line.lower().startswith("successfully installed"):
                        installed.extend(part.strip() for part in line.split("installed", 1)[1].split())

        self._emit_artifact_event(log_path, artifact_type="pip_log")

        return {
            "installed": installed,
            "log_path": log_path,
            "log_relpath": str(log_path.relative_to(self.session_dir)),
        }

    def _packages_from_uv_lock(self, lock_path: Path) -> list[str]:
        if not tomllib:
            self.logger.debug("tomllib not available; skipping uv.lock parsing")
            return []

        try:
            data = tomllib.loads(lock_path.read_text(encoding="utf-8"))
            packages: list[str] = []
            for entry in data.get("package", []):
                name = entry.get("name")
                version = entry.get("version")
                if name and version:
                    packages.append(f"{name}=={version}")
            return packages
        except Exception as exc:  # pragma: no cover - best effort parsing
            self.logger.warning(f"Failed to parse {lock_path}: {exc}")
            return []

    def _build_secret_index(self, specs: Mapping[str, dict[str, Any]]) -> dict[str, list[list[str]]]:
        secret_index: dict[str, list[list[str]]] = {}
        for component, spec in specs.items():
            pointers: list[list[str]] = []
            for field in ("secrets", "x-secret"):
                for pointer in spec.get(field, []) or []:
                    path = self._pointer_to_path(pointer)
                    if path:
                        pointers.append(path)
            if pointers:
                secret_index[component] = pointers
        return secret_index

    @staticmethod
    def _pointer_to_path(pointer: str) -> list[str]:
        if not pointer:
            return []
        trimmed = pointer[1:] if pointer.startswith("/") else pointer
        if not trimmed:
            return []
        parts: list[str] = []
        for raw_segment in trimmed.split("/"):
            segment = raw_segment.replace("~1", "/").replace("~0", "~")
            if segment:
                parts.append(segment)
        return parts

    def _mask_config_for_artifact(self, component_name: str, config: dict[str, Any]) -> dict[str, Any]:
        redacted = copy.deepcopy(config)
        for path in self.component_secret_paths.get(component_name, []):
            self._mask_path(redacted, path)
        return redacted

    def _mask_path(self, data: Any, path: list[str]) -> None:
        if not path:
            return
        current = data
        for segment in path[:-1]:
            if isinstance(current, dict):
                if segment not in current:
                    return
                current = current[segment]
            elif isinstance(current, list):
                try:
                    idx = int(segment)
                except ValueError:
                    return
                if idx < 0 or idx >= len(current):
                    return
                current = current[idx]
            else:
                return

        last = path[-1]
        if isinstance(current, dict) and last in current:
            current[last] = "***MASKED***"
        elif isinstance(current, list):
            try:
                idx = int(last)
            except ValueError:
                return
            if 0 <= idx < len(current):
                current[idx] = "***MASKED***"

    def _emit_artifact_event(self, path: Path, *, artifact_type: str, step_id: str | None = None) -> None:
        try:
            rel_path = path.relative_to(self.session_dir)
        except ValueError:
            rel_path = path

        payload = {
            "artifact_type": artifact_type,
            "path": str(rel_path),
        }
        if step_id:
            payload["step_id"] = step_id
        self.send_event("artifact_created", **payload)

    def _resolve_inputs(self, inputs_spec: dict[str, Any], step_id: str) -> tuple[dict[str, Any], int]:
        if not inputs_spec:
            return {}, 0

        resolved: dict[str, Any] = {}
        rows_total = 0

        for input_key, ref in inputs_spec.items():
            if isinstance(ref, dict) and "from_step" in ref:
                from_step = ref["from_step"]
                from_key = ref.get("key", "df")
                step_output = self.step_outputs.get(from_step)

                if not step_output:
                    self.logger.warning(f"No outputs cached for step '{from_step}'")
                    continue

                if from_key == "df" and isinstance(step_output, dict) and step_output.get("df_path"):
                    df_path = step_output["df_path"]
                    try:
                        import pandas as pd

                        df = pd.read_parquet(df_path)
                        resolved[input_key] = df
                        rows = len(df)
                        rows_total += rows
                        self.send_event(
                            "inputs_resolved",
                            step_id=step_id,
                            from_step=from_step,
                            key=from_key,
                            rows=rows,
                            artifact=str(Path(df_path).relative_to(self.session_dir)),
                            from_memory=False,
                            from_spill=True,
                        )
                    except Exception as exc:
                        self.logger.error(f"Failed to load input DataFrame {df_path}: {exc}")
                elif isinstance(step_output, dict) and from_key in step_output:
                    value = step_output[from_key]
                    resolved[input_key] = value
                    self.logger.debug(f"Resolved input '{input_key}' from step '{from_step}', key '{from_key}'")
                    if from_key == "df":
                        try:
                            import pandas as pd

                            if isinstance(value, pd.DataFrame):
                                rows = len(value)
                                rows_total += rows
                                self.send_event(
                                    "inputs_resolved",
                                    step_id=step_id,
                                    from_step=from_step,
                                    key=from_key,
                                    rows=rows,
                                    from_memory=True,
                                    from_spill=False,
                                )
                        except Exception as exc:  # pragma: no cover - telemetry best effort
                            self.logger.debug(f"Failed to emit inputs_resolved for {from_step}: {exc}")
                else:
                    available_keys = list(step_output.keys()) if isinstance(step_output, dict) else []
                    self.logger.warning(
                        f"Key '{from_key}' not found in outputs from step '{from_step}' (available: {available_keys})"
                    )
            else:
                resolved[input_key] = ref

        return resolved, rows_total

    def _write_run_card(self) -> Path | None:
        if not self.step_io:
            return None

        artifacts_base = self.artifacts_root or (self.session_dir / "artifacts")
        system_dir = artifacts_base / "_system"
        system_dir.mkdir(parents=True, exist_ok=True)
        run_card_path = system_dir / "run_card.json"

        run_card = {
            "session_id": self.session_id,
            "steps": [],
        }

        for step_id, info in self.step_io.items():
            entry = {"step_id": step_id}
            for key, value in info.items():
                entry[key] = value
            run_card["steps"].append(entry)

        with open(run_card_path, "w", encoding="utf-8") as f:
            json.dump(run_card, f, indent=2)

        self._emit_artifact_event(run_card_path, artifact_type="run_card")
        self.logger.debug(f"Run card written to {run_card_path}")
        return run_card_path

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
            "events_jsonl_exists": ((self.session_dir / "events.jsonl").exists() if self.session_dir else False),
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
            except Exception:
                pass  # Give up if we can't write at all


if __name__ == "__main__":
    worker = ProxyWorker()
    worker.run()
