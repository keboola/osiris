"""E2B sandbox client wrapper for remote pipeline execution.

This module provides a thin wrapper around the E2B SDK with a mockable
transport layer for testing without network access.
"""

import contextlib
from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import time
from typing import Any, Protocol


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
    metadata: dict[str, Any]


@dataclass
class FinalStatus:
    """Final status of sandbox execution."""

    status: SandboxStatus
    exit_code: int | None
    duration_seconds: float
    stdout: str | None
    stderr: str | None


class E2BTransport(Protocol):
    """Transport interface for E2B operations (mockable for testing)."""

    def create_sandbox(self, cpu: int, mem_gb: int, env: dict[str, str], timeout: int) -> SandboxHandle:
        """Create a new sandbox instance."""
        ...

    def upload_file(self, handle: SandboxHandle, local_path: Path, remote_path: str) -> None:
        """Upload a file to the sandbox."""
        ...

    def execute_command(self, handle: SandboxHandle, command: list[str]) -> str:
        """Execute a command in the sandbox and return process ID."""
        ...

    def get_process_status(self, handle: SandboxHandle, process_id: str) -> SandboxStatus:
        """Check status of a running process."""
        ...

    def get_process_output(self, handle: SandboxHandle, process_id: str) -> tuple[str | None, str | None, int | None]:
        """Get stdout, stderr, and exit code of a process."""
        ...

    def download_file(self, handle: SandboxHandle, remote_path: str, local_path: Path | None = None) -> bytes | None:
        """Download a file from the sandbox."""
        ...

    def list_files(self, handle: SandboxHandle, path: str) -> list[str]:
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
                raise ImportError("E2B SDK not installed. Run: pip install e2b-code-interpreter") from e

    def create_sandbox(self, cpu: int, mem_gb: int, env: dict[str, str], timeout: int) -> SandboxHandle:  # noqa: ARG002
        """Create a new E2B sandbox."""
        self._ensure_e2b()

        # Create sandbox using the class method
        # Note: E2B SDK uses .create() for synchronous creation
        sandbox = self._e2b.create(
            timeout=timeout,  # Sandbox lifetime timeout
            envs=env if env else None,  # Environment variables
        )

        # Try multiple approaches to get sandbox ID
        # Fallback chain: .id → .session_id → .sandbox_id → raise error
        sandbox_id = None
        for attr in ["id", "session_id", "sandbox_id"]:
            if hasattr(sandbox, attr):
                sandbox_id = getattr(sandbox, attr)
                if sandbox_id and sandbox_id != "unknown":
                    break

        if not sandbox_id or sandbox_id == "unknown":
            # No valid sandbox ID found - this is a critical error
            from osiris.core.execution_adapter import ExecuteError

            raise ExecuteError(
                "Failed to retrieve sandbox ID from E2B SDK. " "Checked attributes: id, session_id, sandbox_id"
            )

        return SandboxHandle(
            sandbox_id=sandbox_id,
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

    def execute_command(self, handle: SandboxHandle, command: list[str]) -> str:
        """Execute a command in the sandbox.

        For E2B, we execute everything as Python code using run_code().
        Shell commands are not directly supported - they must be wrapped in Python.
        """
        sandbox = handle.metadata["sandbox"]
        timeout = handle.metadata.get("timeout", 300)

        # Determine the type of command and create appropriate Python code
        if len(command) >= 2 and command[0] == "python":
            if command[1] == "-c":
                # Direct Python code execution
                code = command[2] if len(command) > 2 else ""
            elif command[1] == "-u" and len(command) > 2:
                # Running a Python script with unbuffered output
                # Read the script and execute it
                script_path = command[2]
                # Convert relative paths to absolute within /home/user/payload
                if not script_path.startswith("/"):
                    script_path = f"/home/user/payload/{script_path}"

                code = f"""
# Execute Python script: {script_path}
import sys
import os

# Change to payload directory for relative imports
os.chdir('/home/user/payload')
sys.path.insert(0, '/home/user/payload')

# Read and execute the script
with open('{script_path}', 'r') as f:
    script_content = f.read()

# Execute in global namespace to preserve state
exec(script_content, globals())
"""
            else:
                # Generic Python invocation - read and execute
                script_name = command[1] if len(command) > 1 else "script.py"
                code = f"""
# Execute Python script
import sys
import os
os.chdir('/home/user/payload')
sys.path.insert(0, '/home/user/payload')

with open('{script_name}', 'r') as f:
    exec(f.read(), globals())
"""
        else:
            # For any other command, we need to wrap it in Python subprocess
            # This includes shell commands, tar extraction, etc.
            import json

            if len(command) == 3 and command[0] in ["sh", "bash"] and command[1] == "-c":
                # Shell command with -c flag
                cmd_str = command[2]
            else:
                # Regular command - join parts
                cmd_str = " ".join(json.dumps(arg) if " " in arg else arg for arg in command)

            # Escape the command string for Python
            escaped_cmd = json.dumps(cmd_str)

            # Get environment variables from handle metadata if available
            env_vars = handle.metadata.get("env", {})
            env_setup = ""
            if env_vars:
                import json as json_module

                for key, value in env_vars.items():
                    env_setup += f"os.environ[{json_module.dumps(key)}] = {json_module.dumps(value)}\n"

            code = f"""
# Execute shell command via subprocess
import subprocess
import sys
import os

# Set working directory
os.chdir('/home/user/payload')

# Set environment variables
{env_setup}

# Run the command with updated environment
result = subprocess.run({escaped_cmd}, shell=True, capture_output=True, text=True, env=os.environ.copy())

# Output results
if result.stdout:
    print(result.stdout, end='')
if result.stderr:
    print(result.stderr, end='', file=sys.stderr)

# Store return code in a variable (don't exit, as that would kill the sandbox)
_exit_code = result.returncode
if _exit_code != 0:
    print(f"\\nCommand exited with code {{_exit_code}}", file=sys.stderr)
"""

        # Execute the code using run_code
        # Note: run_code is synchronous in the sync SDK
        execution = sandbox.run_code(code, timeout=timeout)

        # Store execution for later retrieval
        process_id = f"exec_{len(handle.metadata['processes'])}"
        handle.metadata["processes"][process_id] = execution
        return process_id

    def get_process_status(self, handle: SandboxHandle, process_id: str) -> SandboxStatus:
        """Check status of a running process.

        Since run_code is synchronous, execution is always complete.
        We determine success/failure based on the execution results.
        """
        execution = handle.metadata["processes"].get(process_id)
        if not execution:
            return SandboxStatus.FAILED

        # E2B SDK returns Execution object with .error property
        # If error is present and not None, execution failed
        if hasattr(execution, "error") and execution.error:
            return SandboxStatus.FAILED

        # Check if we stored an exit code in the execution
        # This happens when we run subprocess commands
        if hasattr(execution, "results") and execution.results:
            # Check if the last result contains _exit_code variable
            for result in execution.results:
                if hasattr(result, "data") and isinstance(result.data, dict) and result.data.get("_exit_code", 0) != 0:
                    return SandboxStatus.FAILED

        return SandboxStatus.SUCCESS

    def get_process_output(self, handle: SandboxHandle, process_id: str) -> tuple[str | None, str | None, int | None]:
        """Get stdout, stderr, and exit code of a process.

        Maps E2B Execution object properties to our expected output format.
        """
        execution = handle.metadata["processes"].get(process_id)
        if not execution:
            return None, None, None

        stdout = ""
        stderr = ""
        exit_code = 0

        # According to E2B docs, Execution has these properties:
        # - .text: The text output
        # - .logs: Contains stdout and stderr arrays
        # - .error: Error if execution failed
        # - .results: Array of execution results

        # Extract text output (primary output)
        if hasattr(execution, "text") and execution.text:
            stdout = execution.text

        # Extract logs (stdout/stderr)
        if hasattr(execution, "logs") and execution.logs:
            logs = execution.logs
            # Logs object has .stdout and .stderr arrays
            if hasattr(logs, "stdout") and logs.stdout:
                # If we already have text, append logs
                log_stdout = "\n".join(str(line) for line in logs.stdout)
                if stdout and log_stdout and log_stdout not in stdout:
                    stdout = stdout + "\n" + log_stdout
                elif not stdout:
                    stdout = log_stdout

            if hasattr(logs, "stderr") and logs.stderr:
                stderr = "\n".join(str(line) for line in logs.stderr)

        # Check for errors
        if hasattr(execution, "error") and execution.error:
            # Error present means failure
            stderr = stderr + "\n" + str(execution.error) if stderr else str(execution.error)
            exit_code = 1

        # Try to extract exit code from results if we ran a subprocess
        if hasattr(execution, "results") and execution.results:
            for result in execution.results:
                if hasattr(result, "data") and isinstance(result.data, dict):
                    stored_exit_code = result.data.get("_exit_code")
                    if stored_exit_code is not None:
                        exit_code = stored_exit_code

        return stdout or None, stderr or None, exit_code

    def download_file(self, handle: SandboxHandle, remote_path: str, local_path: Path | None = None) -> bytes | None:
        """Download a file from the sandbox.

        Args:
            handle: Sandbox handle
            remote_path: Path in sandbox
            local_path: Optional local path to save to

        Returns:
            File contents as bytes if local_path is None, otherwise None
        """
        sandbox = handle.metadata["sandbox"]
        # Use files.read method in new API
        try:
            content = sandbox.files.read(remote_path)

            # If local_path is provided, save to file
            if local_path:
                local_path.parent.mkdir(parents=True, exist_ok=True)
                # Handle both bytes and string content
                if isinstance(content, str):
                    with open(local_path, "w") as f:
                        f.write(content)
                else:
                    with open(local_path, "wb") as f:
                        f.write(content)
                return None
            # Return content as bytes
            elif isinstance(content, str):
                return content.encode("utf-8")
            else:
                return content
        except Exception:  # nosec B110
            # File might not exist, which is OK for artifact downloads
            return None

    def list_files(self, handle: SandboxHandle, path: str) -> list[str]:
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

    def __init__(self, transport: E2BTransport | None = None):
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
        env: dict[str, str] | None = None,
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

        # Use a single Python code cell to extract the payload
        # This avoids context restarts
        extract_code = """
import os
import subprocess
import sys

# Create directory
os.makedirs('/home/user/payload', exist_ok=True)

# Extract tarball
result = subprocess.run(['tar', '-xzf', '/tmp/payload.tgz', '-C', '/home/user/payload'],
                       capture_output=True, text=True)
if result.returncode != 0:
    print(f"Extract failed: {result.stderr}", file=sys.stderr)
    sys.exit(1)
"""

        # Execute extraction code
        process_id = self.transport.execute_command(handle, ["python", "-c", extract_code])

        # Get extraction results immediately (synchronous)
        status = self.transport.get_process_status(handle, process_id)

        if status != SandboxStatus.SUCCESS:
            stdout, stderr, exit_code = self.transport.get_process_output(handle, process_id)
            raise RuntimeError(f"Failed to extract payload: {stderr or 'Unknown error'}")

    def start(self, handle: SandboxHandle, command: list[str]) -> str:
        """Start pipeline execution in sandbox.

        Args:
            handle: Sandbox handle
            command: Command to execute (e.g., ["python", "mini_runner.py"])

        Returns:
            Process ID for tracking
        """
        # If command is already a shell command, use it directly
        if command[0] in ["sh", "bash"]:
            return self.transport.execute_command(handle, command)

        # Otherwise, wrap it in a shell command to change directory
        shell_command = ["sh", "-c", f"cd /home/user/payload && {' '.join(command)}"]
        return self.transport.execute_command(handle, shell_command)

    def poll_until_complete(
        self,
        handle: SandboxHandle,
        process_id: str,
        timeout_s: int = 900,  # noqa: ARG002
        backoff_strategy: str = "exponential",  # noqa: ARG002
    ) -> FinalStatus:
        """Get execution results immediately (no polling needed).

        Since E2B's run_code is synchronous, the execution is already complete
        when execute_command returns. This method now just retrieves the results.

        Args:
            handle: Sandbox handle
            process_id: Process ID to monitor
            timeout_s: Maximum time to wait in seconds (unused for sync execution)
            backoff_strategy: Polling strategy (unused for sync execution)

        Returns:
            FinalStatus with execution results
        """
        start_time = time.time()

        # Since run_code is synchronous, execution is already complete
        # Just retrieve the status and output
        status = self.transport.get_process_status(handle, process_id)
        stdout, stderr, exit_code = self.transport.get_process_output(handle, process_id)

        # Calculate actual duration (should be near-instant for retrieval)
        duration = time.time() - start_time

        return FinalStatus(
            status=status,
            exit_code=exit_code,
            duration_seconds=duration,
            stdout=stdout,
            stderr=stderr,
        )

    def download_file(self, handle: SandboxHandle, remote_path: str) -> bytes | None:
        """Download a single file from sandbox.

        Args:
            handle: Sandbox handle
            remote_path: Path in sandbox to download

        Returns:
            File contents as bytes, or None if file doesn't exist
        """
        try:
            # Call transport with None for local_path to get bytes back
            return self.transport.download_file(handle, remote_path, None)
        except Exception:
            return None

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
                self.transport.download_file(handle, f"/home/user/artifacts/{file_name}", artifacts_dir / file_name)

    def close(self, handle: SandboxHandle) -> None:
        """Close sandbox and cleanup resources (best effort).

        Args:
            handle: Sandbox handle to close
        """
        with contextlib.suppress(Exception):
            self.transport.close_sandbox(handle)  # Best effort cleanup
