"""E2B Simple Adapter - PyPI-based execution (ADR-0041).

This adapter installs osiris-pipeline from PyPI in an E2B sandbox
and runs the same `osiris run` command as local execution.

Benefits:
- ~100 lines vs ~1500 lines (ProxyWorker)
- Same code path as local execution
- Secrets via environment variables (not config files)
- TGZ artifact bundling (single download)
"""

import asyncio
import contextlib
import json
import logging
import os
from pathlib import Path
import tarfile
import tempfile
import time
from typing import Any

try:
    from e2b_code_interpreter import AsyncSandbox
except ImportError:
    AsyncSandbox = None

from osiris.core.execution_adapter import (
    CollectedArtifacts,
    ExecResult,
    ExecuteError,
    ExecutionAdapter,
    ExecutionContext,
    PreparedRun,
)

logger = logging.getLogger(__name__)


class E2BSimpleAdapter(ExecutionAdapter):
    """Simple E2B adapter using PyPI-based execution.

    Instead of uploading ProxyWorker and using RPC, this adapter:
    1. Creates E2B sandbox
    2. Installs osiris-pipeline from PyPI
    3. Uploads manifest.yaml
    4. Sets secrets as environment variables
    5. Runs `osiris run --stream-events manifest.yaml`
    6. Downloads artifacts as TGZ bundle
    """

    # Osiris package version to install (None = latest)
    OSIRIS_VERSION: str | None = None

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize the E2B simple adapter.

        Args:
            config: Configuration with:
                - api_key: E2B API key (defaults to E2B_API_KEY env var)
                - timeout: Sandbox timeout in seconds (default: 900)
                - cpu: Number of CPUs (default: 2)
                - memory: Memory in GB (default: 4)
                - osiris_version: Specific osiris-pipeline version to install
                - env: Additional environment variables
                - verbose: Enable verbose output
        """
        self.config = config or {}

        self.api_key = self.config.get("api_key") or os.environ.get("E2B_API_KEY")
        if not self.api_key:
            raise ExecuteError("E2B_API_KEY not found in config or environment")

        self.timeout = self.config.get("timeout", 900)
        self.cpu = self.config.get("cpu", 2)
        self.memory = self.config.get("memory", 4)
        self.verbose = self.config.get("verbose", False)
        self.osiris_version = self.config.get("osiris_version", self.OSIRIS_VERSION)
        self.extra_env = self.config.get("env", {})

        self.sandbox = None
        self._events: list[dict] = []
        self._metrics: list[dict] = []

    def _get_required_env_vars(self) -> set[str]:
        """Scan osiris_connections.yaml for ${VAR} references."""
        from osiris.core.config import load_connections_yaml  # noqa: PLC0415

        try:
            connections = load_connections_yaml(substitute_env=False)
        except Exception:
            logger.debug("No osiris_connections.yaml found; skipping env var scan")
            return set()

        env_vars: set[str] = set()
        self._scan_for_env_refs(connections, env_vars)
        return env_vars

    @staticmethod
    def _scan_for_env_refs(data, env_vars: set[str]) -> None:
        """Recursively extract ${VAR_NAME} references from data structure."""
        import re  # noqa: PLC0415

        pattern = re.compile(r"\$\{([^}]+)\}")

        if isinstance(data, str):
            for match in pattern.finditer(data):
                env_vars.add(match.group(1))
        elif isinstance(data, dict):
            for value in data.values():
                E2BSimpleAdapter._scan_for_env_refs(value, env_vars)
        elif isinstance(data, list):
            for item in data:
                E2BSimpleAdapter._scan_for_env_refs(item, env_vars)

    def prepare(self, plan: dict[str, Any], context: ExecutionContext) -> PreparedRun:
        """Prepare execution package from compiled manifest.

        For PyPI-based execution, we just need to package the manifest
        and identify which secrets need to be passed as env vars.
        """
        # Find source manifest path
        source_manifest = plan.get("metadata", {}).get("source_manifest_path")
        if source_manifest:
            compiled_root = str(Path(source_manifest).parent)
        else:
            compiled_root = str(context.base_path)

        # Extract connection refs that need env vars
        resolved_connections = {}
        for step in plan.get("steps", []):
            config = step.get("config", {})
            if "connection" in config:
                conn_ref = config["connection"]
                if conn_ref.startswith("@"):
                    resolved_connections[conn_ref] = {"ref": conn_ref}

        return PreparedRun(
            plan=plan,
            resolved_connections=resolved_connections,
            cfg_index={},  # Not needed - configs are in compiled_root
            io_layout={"session": f"/home/user/session/{context.session_id}"},
            run_params={},
            constraints={"timeout": self.timeout},
            metadata={"adapter": "e2b_simple"},
            compiled_root=compiled_root,
        )

    def execute(self, prepared: PreparedRun, context: ExecutionContext) -> ExecResult:
        """Execute pipeline in E2B sandbox using PyPI-installed osiris."""
        return asyncio.get_event_loop().run_until_complete(self._async_execute(prepared, context))

    async def _async_execute(self, prepared: PreparedRun, context: ExecutionContext) -> ExecResult:
        """Async implementation of execute."""
        start_time = time.time()

        try:
            # Create sandbox
            logger.info("Creating E2B sandbox...")
            self.sandbox = await AsyncSandbox.create(
                api_key=self.api_key,
                timeout=self.timeout,
            )
            logger.info(f"Sandbox created: {self.sandbox.sandbox_id}")

            # Install osiris-pipeline from PyPI
            package = "osiris-pipeline"
            if self.osiris_version:
                package = f"osiris-pipeline=={self.osiris_version}"

            logger.info(f"Installing {package}...")
            result = await self.sandbox.commands.run(
                f"pip install {package}",
                timeout=300,
            )
            if result.exit_code != 0:
                raise ExecuteError(f"Failed to install osiris-pipeline: {result.stderr}")

            # Create session directory
            session_dir = f"/home/user/session/{context.session_id}"
            await self.sandbox.commands.run(f"mkdir -p {session_dir}")

            # Upload manifest and cfg directory
            compiled_root = Path(prepared.compiled_root)
            manifest_path = compiled_root / "manifest.yaml"

            if manifest_path.exists():
                await self.sandbox.files.write(
                    f"{session_dir}/manifest.yaml",
                    manifest_path.read_text(),
                )

            # Upload cfg directory if exists
            cfg_dir = compiled_root / "cfg"
            if cfg_dir.exists():
                await self.sandbox.commands.run(f"mkdir -p {session_dir}/cfg")
                for cfg_file in cfg_dir.glob("*.json"):
                    await self.sandbox.files.write(
                        f"{session_dir}/cfg/{cfg_file.name}",
                        cfg_file.read_text(),
                    )

            # Build environment variables
            env_vars = {
                "OSIRIS_BASE_PATH": session_dir,
                **self.extra_env,
            }

            # Inject only env vars referenced by osiris_connections.yaml
            required_env_vars = self._get_required_env_vars()
            for var_name in required_env_vars:
                value = os.environ.get(var_name)
                if value:
                    env_vars[var_name] = value

            # Set environment variables
            env_str = " ".join(f'{k}="{v}"' for k, v in env_vars.items())

            # Run osiris with --stream-events
            cmd = f"{env_str} osiris run --stream-events {session_dir}/manifest.yaml"
            logger.info("Running: osiris run --stream-events ...")

            result = await self.sandbox.commands.run(
                cmd,
                timeout=self.timeout,
                on_stdout=self._handle_stdout,
                on_stderr=self._handle_stderr if self.verbose else None,
            )

            duration = time.time() - start_time

            if result.exit_code == 0:
                return ExecResult(
                    success=True,
                    exit_code=0,
                    duration_seconds=duration,
                    step_results={"events": self._events, "metrics": self._metrics},
                )
            else:
                return ExecResult(
                    success=False,
                    exit_code=result.exit_code,
                    duration_seconds=duration,
                    error_message=result.stderr or "Pipeline execution failed",
                )

        except Exception as e:
            duration = time.time() - start_time
            logger.exception("E2B execution failed")
            return ExecResult(
                success=False,
                exit_code=1,
                duration_seconds=duration,
                error_message=str(e),
            )

    def _handle_stdout(self, line: str) -> None:
        """Handle stdout line from sandbox - parse JSON Lines events."""
        line = line.strip()
        if not line:
            return

        try:
            data = json.loads(line)
            msg_type = data.get("type")

            if msg_type == "event":
                self._events.append(data)
                if self.verbose:
                    logger.info(f"[event] {data.get('event')}")

            elif msg_type == "metric":
                self._metrics.append(data)
                if self.verbose:
                    logger.info(f"[metric] {data.get('metric')}={data.get('value')}")

        except json.JSONDecodeError:
            # Non-JSON output - log if verbose
            if self.verbose:
                logger.debug(f"[stdout] {line}")

    def _handle_stderr(self, line: str) -> None:
        """Handle stderr line from sandbox."""
        line = line.strip()
        if line:
            logger.warning(f"[stderr] {line}")

    def collect(self, prepared: PreparedRun, context: ExecutionContext) -> CollectedArtifacts:
        """Collect artifacts from E2B sandbox as TGZ bundle."""
        return asyncio.get_event_loop().run_until_complete(self._async_collect(prepared, context))

    async def _async_collect(self, prepared: PreparedRun, context: ExecutionContext) -> CollectedArtifacts:
        """Async implementation of collect."""
        if not self.sandbox:
            return CollectedArtifacts()

        try:
            session_dir = f"/home/user/session/{context.session_id}"

            # Create TGZ bundle in sandbox
            tgz_path = f"/tmp/artifacts_{context.session_id}.tgz"
            await self.sandbox.commands.run(
                f"tar -czf {tgz_path} -C {session_dir} .",
                timeout=60,
            )

            # Download TGZ
            tgz_content = await self.sandbox.files.read(tgz_path)

            # Extract to local artifacts directory
            artifacts_dir = context.base_path / "artifacts"
            artifacts_dir.mkdir(parents=True, exist_ok=True)

            with tempfile.NamedTemporaryFile(suffix=".tgz", delete=False) as f:
                f.write(tgz_content)
                temp_tgz = f.name

            with tarfile.open(temp_tgz, "r:gz") as tar:
                tar.extractall(path=artifacts_dir)

            os.unlink(temp_tgz)

            # Find log files
            events_log = artifacts_dir / "events.jsonl"
            metrics_log = artifacts_dir / "metrics.jsonl"

            return CollectedArtifacts(
                events_log=events_log if events_log.exists() else None,
                metrics_log=metrics_log if metrics_log.exists() else None,
                artifacts_dir=artifacts_dir,
            )

        except Exception:
            logger.exception("Failed to collect artifacts")
            return CollectedArtifacts()

        finally:
            # Close sandbox
            if self.sandbox:
                with contextlib.suppress(Exception):
                    await self.sandbox.kill()
                self.sandbox = None
