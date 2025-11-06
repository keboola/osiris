"""
CLI Bridge for MCP tools - CLI-first adapter architecture.

This module provides the bridge between MCP tools and CLI subcommands,
ensuring that all operations requiring secrets are delegated to CLI,
which has proper environment access.

Security Model:
- MCP tools NEVER access secrets directly
- All operations requiring secrets are delegated via run_cli_json()
- CLI inherits os.environ and has access to connection resolution
- Errors are mapped to MCP-compatible format
"""

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
import uuid

from osiris.mcp.errors import ErrorFamily, OsirisError

logger = logging.getLogger(__name__)


def derive_correlation_id(request_id: str | None = None) -> str:
    """
    Derive correlation ID deterministically from request_id if available.

    When request_id is provided (from MCP protocol), this generates a deterministic
    correlation ID using SHA-256 hash. This ensures the same request_id always produces
    the same correlation ID, enabling reproducible metrics for testing and auditing.

    When request_id is None, generates a random correlation ID for non-request contexts.

    Args:
        request_id: Optional request ID from MCP protocol

    Returns:
        Correlation ID (deterministic if request_id provided, else random)
        Format: "mcp_<12-char-hex>"
    """
    if request_id is not None:
        # Deterministic: SHA-256 hash of request_id (supports empty string)
        hash_digest = hashlib.sha256(request_id.encode()).hexdigest()[:12]
        return f"mcp_{hash_digest}"
    else:
        # Random for non-request contexts
        return f"mcp_{uuid.uuid4().hex[:12]}"


def generate_correlation_id() -> str:
    """
    Generate a correlation ID for tracking CLI operations.

    DEPRECATED: Use derive_correlation_id() instead for deterministic IDs.

    Returns:
        Unique correlation ID (UUID4 format)
    """
    return str(uuid.uuid4())


def track_metrics(start_time: float, bytes_in: int, bytes_out: int) -> dict[str, Any]:
    """
    Track metrics for CLI operation.

    Args:
        start_time: Operation start time (from time.time())
        bytes_in: Input payload size in bytes
        bytes_out: Output payload size in bytes

    Returns:
        Metrics dictionary
    """
    duration_ms = (time.time() - start_time) * 1000
    return {
        "duration_ms": round(duration_ms, 2),
        "bytes_in": bytes_in,
        "bytes_out": bytes_out,
        "overhead_ms": round(duration_ms - (bytes_out / 1_000_000), 2),  # Rough estimate
    }


def map_cli_error_to_mcp(exit_code: int, stderr: str, cmd: list[str]) -> OsirisError:
    """
    Map CLI error to MCP-compatible OsirisError.

    Args:
        exit_code: CLI process exit code
        stderr: Standard error output
        cmd: Command that was executed

    Returns:
        OsirisError with appropriate family and message
    """
    # Map common exit codes to error families
    # Only use families that exist: SCHEMA, SEMANTIC, DISCOVERY, LINT, POLICY
    error_family_map = {
        1: ErrorFamily.SEMANTIC,  # General error
        2: ErrorFamily.SCHEMA,  # Argument/validation error
        3: ErrorFamily.DISCOVERY,  # Discovery operation failed
        4: ErrorFamily.POLICY,  # Policy/validation error
        5: ErrorFamily.SEMANTIC,  # Execution error
        124: ErrorFamily.DISCOVERY,  # Timeout (use DISCOVERY for timeouts)
        127: ErrorFamily.SEMANTIC,  # Command not found
        130: ErrorFamily.SEMANTIC,  # SIGINT
        137: ErrorFamily.SEMANTIC,  # SIGKILL
        143: ErrorFamily.SEMANTIC,  # SIGTERM
    }

    family = error_family_map.get(exit_code, ErrorFamily.SEMANTIC)

    # Extract error message from stderr
    error_lines = stderr.strip().split("\n")
    error_message = error_lines[-1] if error_lines else "CLI command failed"

    # Build suggestion based on error
    suggest = f"CLI command failed with exit code {exit_code}. Check logs for details."
    if exit_code == 124:
        suggest = "Operation timed out. Consider increasing timeout or checking for blocking operations."
    elif exit_code == 127:
        suggest = "CLI command not found. Ensure Osiris is properly installed."
    elif "connection" in error_message.lower():
        suggest = "Check connection configuration in osiris_connections.yaml"
    elif "permission" in error_message.lower():
        suggest = "Check file permissions and ensure proper access rights"

    # Note: OsirisError doesn't support context parameter
    # We include relevant info in the message instead
    f"{error_message} (exit code: {exit_code}, command: {' '.join(cmd[:3])}...)"

    return OsirisError(
        family=family,
        message=error_message,  # Keep message clean, don't include context
        path=["cli_bridge", "run_cli_json"],
        suggest=suggest,
    )


def ensure_base_path() -> Path:
    """
    Get base_path from osiris.yaml configuration.

    Resolution order:
    1. OSIRIS_HOME environment variable (if set)
    2. base_path from osiris.yaml
    3. Current working directory

    Returns:
        Resolved absolute base path

    Raises:
        OsirisError: If base_path cannot be determined
    """
    # Check OSIRIS_HOME environment variable first
    osiris_home = os.environ.get("OSIRIS_HOME", "").strip()
    if osiris_home:
        base_path = Path(osiris_home).resolve()
        if base_path.exists():
            return base_path
        else:
            logger.warning(f"OSIRIS_HOME set but path does not exist: {base_path}")

    # Try to load from osiris.yaml
    try:
        import yaml  # noqa: PLC0415  # Lazy import for performance

        # Look for osiris.yaml in current directory or OSIRIS_HOME
        config_paths = [
            Path.cwd() / "osiris.yaml",
            Path.cwd() / ".osiris.yaml",
        ]

        if osiris_home:
            config_paths.insert(0, Path(osiris_home) / "osiris.yaml")

        for config_path in config_paths:
            if config_path.exists():
                with open(config_path) as f:
                    config = yaml.safe_load(f)

                if config and "filesystem" in config:
                    base_path_str = config["filesystem"].get("base_path", "")
                    if base_path_str:
                        return Path(base_path_str).resolve()

                # If base_path is empty in config, use config file's directory
                return config_path.parent.resolve()

    except Exception as e:
        logger.warning(f"Failed to load osiris.yaml: {e}")

    # Fallback to current working directory
    return Path.cwd().resolve()


async def run_cli_json(
    args: list[str],
    timeout_s: float = 30.0,
    correlation_id: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """
    Execute Osiris CLI command and return parsed JSON result.

    This is the core CLI bridge function that delegates operations to the
    Osiris CLI, which has proper environment and secret access.

    Args:
        args: Command arguments (e.g., ["mcp", "connections", "list"])
        timeout_s: Command timeout in seconds (default: 30.0)
        correlation_id: Pre-computed correlation ID (if already derived at MCP layer)
        request_id: Request ID for deterministic correlation (if correlation_id not provided)

    Returns:
        Parsed JSON response from CLI

    Raises:
        OsirisError: If command fails or returns invalid JSON
    """
    # Use provided correlation_id, or derive from request_id, or generate random
    if correlation_id is None:
        correlation_id = derive_correlation_id(request_id)

    start_time = time.time()

    # Build full command: python osiris.py <args> --json
    # We need to find the osiris.py entry point
    base_path = ensure_base_path()

    # Find python executable (prefer current venv)
    python_exe = sys.executable

    # Find osiris.py or use module invocation
    osiris_py = base_path / "osiris.py"
    if osiris_py.exists():
        cmd = [python_exe, str(osiris_py)] + args + ["--json"]
    else:
        # Fallback to module invocation
        cmd = [python_exe, "-m", "osiris.cli.main"] + args + ["--json"]

    logger.debug(f"CLI bridge executing: {' '.join(cmd)}")
    logger.debug(f"Working directory: {base_path}")
    logger.debug(f"Correlation ID: {correlation_id}")

    try:
        # Execute command with timeout in thread pool (non-blocking to event loop)
        # This prevents the async event loop from freezing and enables parallelization
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=str(base_path),
            env=os.environ.copy(),  # Inherit environment (secrets available here)
        )

        # Track metrics
        bytes_in = len(json.dumps(args).encode())
        bytes_out = len(result.stdout.encode())
        metrics = track_metrics(start_time, bytes_in, bytes_out)

        logger.debug(f"CLI command completed: {metrics}")

        # Check for errors
        if result.returncode != 0:
            logger.error(f"CLI command failed with exit code {result.returncode}")
            logger.error(f"STDERR: {result.stderr}")
            error = map_cli_error_to_mcp(result.returncode, result.stderr, cmd)
            raise error

        # Parse JSON response
        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse CLI JSON output: {e}")
            logger.error(f"STDOUT: {result.stdout[:500]}")
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"CLI returned invalid JSON: {str(e)}",
                path=["cli_bridge", "json_parse"],
                suggest="Check CLI output format. Ensure --json flag is working correctly.",
            ) from e

        # Add metadata to response
        # Handle both dict and non-dict responses (some commands return arrays)
        if isinstance(response, dict):
            response["_meta"] = {
                "correlation_id": correlation_id,
                "duration_ms": metrics["duration_ms"],
                "bytes_in": metrics["bytes_in"],
                "bytes_out": metrics["bytes_out"],
                "cli_command": " ".join(args),
            }
            return response
        else:
            # For non-dict responses (e.g., arrays), wrap in a dict with metadata
            return {
                "data": response,
                "_meta": {
                    "correlation_id": correlation_id,
                    "duration_ms": metrics["duration_ms"],
                    "bytes_in": metrics["bytes_in"],
                    "bytes_out": metrics["bytes_out"],
                    "cli_command": " ".join(args),
                },
            }

    except OsirisError:
        # Re-raise OsirisError as-is (already properly formatted)
        raise

    except subprocess.TimeoutExpired as e:
        logger.error(f"CLI command timed out after {timeout_s}s")
        raise OsirisError(
            ErrorFamily.DISCOVERY,  # Use DISCOVERY for timeouts
            f"CLI command timed out after {timeout_s}s",
            path=["cli_bridge", "timeout"],
            suggest=f"Increase timeout (current: {timeout_s}s) or investigate blocking operations.",
        ) from e

    except FileNotFoundError as e:
        logger.error(f"CLI command not found: {e}")
        raise OsirisError(
            ErrorFamily.SEMANTIC,  # Use SEMANTIC for execution errors
            "Osiris CLI not found",
            path=["cli_bridge", "command_not_found"],
            suggest="Ensure osiris.py exists in repository root or Osiris is properly installed.",
        ) from e

    except Exception as e:
        logger.error(f"Unexpected error in CLI bridge: {e}")
        raise OsirisError(
            ErrorFamily.SEMANTIC,  # Use SEMANTIC for unexpected errors
            f"CLI bridge error: {str(e)}",
            path=["cli_bridge", "unexpected"],
            suggest="Check logs for details. This may indicate a system-level issue.",
        ) from e
