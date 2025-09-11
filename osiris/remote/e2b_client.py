"""E2B sandbox client wrapper for remote pipeline execution.

This module provides a thin wrapper around the E2B SDK with a mockable
transport layer for testing without network access.
"""

import contextlib
import os
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol


class SandboxStatus(Enum):
    """Status of sandbox execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class SandboxHandle:
    """Handle for interacting with a sandbox instance."""

    sandbox_id: str
    status: SandboxStatus
    metadata: Dict[str, Any]


@dataclass
class FinalStatus:
    """Final status of sandbox execution."""

    status: SandboxStatus
    exit_code: Optional[int]
    duration_seconds: float
    stdout: Optional[str]
    stderr: Optional[str]


class E2BTransport(Protocol):
    """Transport interface for E2B operations (mockable for testing)."""

    def create_sandbox(
        self, cpu: int, mem_gb: int, env: Dict[str, str], timeout: int
    ) -> SandboxHandle:
        """Create a new sandbox instance."""
        ...

    def upload_file(self, handle: SandboxHandle, local_path: Path, remote_path: str) -> None:
        """Upload a file to the sandbox."""
        ...

    def execute_command(self, handle: SandboxHandle, command: List[str]) -> str:
        """Execute a command in the sandbox and return process ID."""
        ...

    def get_process_status(self, handle: SandboxHandle, process_id: str) -> SandboxStatus:
        """Check status of a running process."""
        ...

    def get_process_output(
        self, handle: SandboxHandle, process_id: str
    ) -> tuple[Optional[str], Optional[str], Optional[int]]:
        """Get stdout, stderr, and exit code of a process."""
        ...

    def download_file(self, handle: SandboxHandle, remote_path: str, local_path: Path) -> None:
        """Download a file from the sandbox."""
        ...

    def list_files(self, handle: SandboxHandle, path: str) -> List[str]:
        """List files in a directory."""
        ...

    def close_sandbox(self, handle: SandboxHandle) -> None:
        """Close and cleanup sandbox resources."""
        ...


class E2BLiveTransport:
    """Live E2B transport using actual E2B SDK."""

    def __init__(self, api_key: str):
        """Initialize with E2B API key."""
        # Set the API key in environment for E2B SDK
        os.environ["E2B_API_KEY"] = api_key
        # Lazy import to avoid requiring e2b-code-interpreter for tests
        self._e2b = None

    def _ensure_e2b(self):
        """Ensure E2B SDK is imported."""
        if self._e2b is None:
            try:
                from e2b_code_interpreter import Sandbox

                self._e2b = Sandbox
            except ImportError as e:
                raise ImportError(
                    "E2B SDK not installed. Run: pip install e2b-code-interpreter"
                ) from e

    def create_sandbox(
        self, cpu: int, mem_gb: int, env: Dict[str, str], timeout: int  # noqa: ARG002
    ) -> SandboxHandle:
        """Create a new E2B sandbox."""
        self._ensure_e2b()

        # Create sandbox with new API using create() class method
        sandbox = self._e2b.create(timeout=timeout, envs=env)

        return SandboxHandle(
            sandbox_id=getattr(sandbox, "id", "unknown"),
            status=SandboxStatus.RUNNING,
            metadata={"sandbox": sandbox, "processes": {}, "env": env, "timeout": timeout},
        )

    def upload_file(self, handle: SandboxHandle, local_path: Path, remote_path: str) -> None:
        """Upload a file to the sandbox."""
        sandbox = handle.metadata["sandbox"]
        with open(local_path, "rb") as f:
            content = f.read()
        # Use files.write method in new API
        sandbox.files.write(remote_path, content)

    def execute_command(self, handle: SandboxHandle, command: List[str]) -> str:
        """Execute a command in the sandbox."""
        sandbox = handle.metadata["sandbox"]
        env = handle.metadata.get("env", {})
        timeout = handle.metadata.get("timeout", 300)

        # Use run_code to execute shell commands in new API
        cmd_str = " ".join(command)
        execution = sandbox.run_code(
            f"import subprocess; subprocess.run('{cmd_str}', shell=True, check=True)",
            envs=env,
            timeout=timeout,
        )

        # Store execution for later retrieval
        process_id = f"exec_{len(handle.metadata['processes'])}"
        handle.metadata["processes"][process_id] = execution
        return process_id

    def get_process_status(self, handle: SandboxHandle, process_id: str) -> SandboxStatus:
        """Check status of a running process."""
        execution = handle.metadata["processes"].get(process_id)
        if not execution:
            return SandboxStatus.FAILED

        # In new API, execution is synchronous, so it's always complete
        if hasattr(execution, "error") and execution.error:
            return SandboxStatus.FAILED
        return SandboxStatus.SUCCESS

    def get_process_output(
        self, handle: SandboxHandle, process_id: str
    ) -> tuple[Optional[str], Optional[str], Optional[int]]:
        """Get stdout, stderr, and exit code of a process."""
        execution = handle.metadata["processes"].get(process_id)
        if not execution:
            return None, None, None

        # Extract output from execution results
        stdout = ""
        stderr = ""
        exit_code = 1 if (hasattr(execution, "error") and execution.error) else 0

        # Concatenate output messages from logs
        if hasattr(execution, "logs"):
            logs = execution.logs
            if hasattr(logs, "stdout") and logs.stdout:
                stdout = "\n".join(logs.stdout)
            if hasattr(logs, "stderr") and logs.stderr:
                stderr = "\n".join(logs.stderr)

        if hasattr(execution, "error") and execution.error:
            stderr = str(execution.error)

        return stdout or None, stderr or None, exit_code

    def download_file(self, handle: SandboxHandle, remote_path: str, local_path: Path) -> None:
        """Download a file from the sandbox."""
        sandbox = handle.metadata["sandbox"]
        # Use files.read method in new API
        try:
            content = sandbox.files.read(remote_path)
            local_path.parent.mkdir(parents=True, exist_ok=True)

            # Handle both bytes and string content
            if isinstance(content, str):
                with open(local_path, "w") as f:
                    f.write(content)
            else:
                with open(local_path, "wb") as f:
                    f.write(content)
        except Exception:  # nosec B110
            # File might not exist, which is OK for artifact downloads
            pass

    def list_files(self, handle: SandboxHandle, path: str) -> List[str]:
        """List files in a directory."""
        sandbox = handle.metadata["sandbox"]
        # Use files.list method in new API
        try:
            result = sandbox.files.list(path)
            # Extract filenames from result
            if isinstance(result, list):
                return [str(item) for item in result]
            else:
                return []
        except Exception:
            return []

    def close_sandbox(self, handle: SandboxHandle) -> None:
        """Close and cleanup sandbox resources."""
        sandbox = handle.metadata.get("sandbox")
        if sandbox:
            with contextlib.suppress(Exception):
                # Use kill method in new API
                sandbox.kill()  # Best effort cleanup


class E2BClient:
    """High-level E2B client for pipeline execution."""

    def __init__(self, transport: Optional[E2BTransport] = None):
        """Initialize E2B client.

        Args:
            transport: Optional transport implementation. If not provided,
                      will use E2BLiveTransport with API key from environment.
        """
        if transport is None:
            api_key = os.environ.get("E2B_API_KEY")
            if not api_key:
                raise ValueError(
                    "E2B_API_KEY environment variable not set. "
                    "Please set it to your E2B API key or pass a custom transport."
                )
            transport = E2BLiveTransport(api_key)
        self.transport = transport

    def create_sandbox(
        self,
        cpu: int = 2,
        mem_gb: int = 4,
        env: Optional[Dict[str, str]] = None,
        timeout: int = 900,
    ) -> SandboxHandle:
        """Create a new sandbox with specified resources.

        Args:
            cpu: Number of CPU cores
            mem_gb: Memory in GB
            env: Environment variables to set in sandbox
            timeout: Timeout in seconds

        Returns:
            SandboxHandle for interacting with the sandbox
        """
        if env is None:
            env = {}
        return self.transport.create_sandbox(cpu, mem_gb, env, timeout)

    def upload_payload(self, handle: SandboxHandle, payload_tgz_path: Path) -> None:
        """Upload and extract payload tarball to sandbox.

        Args:
            handle: Sandbox handle
            payload_tgz_path: Path to payload.tgz file
        """
        # Upload the tarball
        self.transport.upload_file(handle, payload_tgz_path, "/tmp/payload.tgz")  # nosec B108

        # Extract it
        extract_cmd = ["tar", "-xzf", "/tmp/payload.tgz", "-C", "/home/user"]  # nosec B108
        process_id = self.transport.execute_command(handle, extract_cmd)

        # Wait for extraction to complete
        max_wait = 30  # seconds
        start = time.time()
        while time.time() - start < max_wait:
            status = self.transport.get_process_status(handle, process_id)
            if status != SandboxStatus.RUNNING:
                break
            time.sleep(0.5)

        if status != SandboxStatus.SUCCESS:
            raise RuntimeError(f"Failed to extract payload: {status}")

    def start(self, handle: SandboxHandle, command: List[str]) -> str:
        """Start pipeline execution in sandbox.

        Args:
            handle: Sandbox handle
            command: Command to execute (e.g., ["python", "mini_runner.py"])

        Returns:
            Process ID for tracking
        """
        # Change to working directory and execute
        full_command = ["cd", "/home/user", "&&"] + command
        return self.transport.execute_command(handle, full_command)

    def poll_until_complete(
        self,
        handle: SandboxHandle,
        process_id: str,
        timeout_s: int = 900,
        backoff_strategy: str = "exponential",
    ) -> FinalStatus:
        """Poll process until completion or timeout.

        Args:
            handle: Sandbox handle
            process_id: Process ID to monitor
            timeout_s: Maximum time to wait in seconds
            backoff_strategy: Polling strategy ("exponential" or "linear")

        Returns:
            FinalStatus with execution results
        """
        start_time = time.time()
        poll_interval = 1.0  # Initial interval

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout_s:
                return FinalStatus(
                    status=SandboxStatus.TIMEOUT,
                    exit_code=None,
                    duration_seconds=elapsed,
                    stdout=None,
                    stderr=None,
                )

            status = self.transport.get_process_status(handle, process_id)

            if status in [SandboxStatus.SUCCESS, SandboxStatus.FAILED]:
                stdout, stderr, exit_code = self.transport.get_process_output(handle, process_id)
                return FinalStatus(
                    status=status,
                    exit_code=exit_code,
                    duration_seconds=elapsed,
                    stdout=stdout,
                    stderr=stderr,
                )

            time.sleep(poll_interval)

            # Adjust polling interval
            if backoff_strategy == "exponential":
                poll_interval = min(poll_interval * 1.5, 10.0)  # Cap at 10 seconds
            elif backoff_strategy == "linear":
                poll_interval = min(poll_interval + 0.5, 10.0)

    def download_artifacts(self, handle: SandboxHandle, dest_dir: Path) -> None:
        """Download execution artifacts from sandbox.

        Args:
            handle: Sandbox handle
            dest_dir: Local directory to download artifacts to
        """
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Files to download
        artifacts = [
            ("events.jsonl", dest_dir / "events.jsonl"),
            ("metrics.jsonl", dest_dir / "metrics.jsonl"),
            ("osiris.log", dest_dir / "osiris.log"),
        ]

        for remote_path, local_path in artifacts:
            with contextlib.suppress(Exception):
                # Some files might not exist, that's ok
                self.transport.download_file(handle, f"/home/user/{remote_path}", local_path)

        # Download artifacts directory if it exists
        with contextlib.suppress(Exception):
            # Artifacts directory might not exist
            artifact_files = self.transport.list_files(handle, "/home/user/artifacts")
            artifacts_dir = dest_dir / "artifacts"
            artifacts_dir.mkdir(exist_ok=True)

            for file_name in artifact_files:
                self.transport.download_file(
                    handle, f"/home/user/artifacts/{file_name}", artifacts_dir / file_name
                )

    def close(self, handle: SandboxHandle) -> None:
        """Close sandbox and cleanup resources (best effort).

        Args:
            handle: Sandbox handle to close
        """
        with contextlib.suppress(Exception):
            self.transport.close_sandbox(handle)  # Best effort cleanup
