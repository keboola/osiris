"""Shared fixtures for E2B tests."""

import contextlib
import inspect
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Import real E2B components
from osiris.core.execution_adapter import ExecutionContext
from osiris.remote.e2b_adapter import E2BAdapter
from osiris.remote.e2b_client import (
    E2BClient,
    FinalStatus,
    SandboxHandle,
    SandboxStatus,
)


def make_execution_context(tmpdir: Path, **extras) -> ExecutionContext:
    """
    Backward/forward-compatible factory for ExecutionContext.
    Do NOT blindly pass logs_dir or unknown kwargs; inspect signature first.
    After construction, set optional attributes if present.
    """
    sig = inspect.signature(ExecutionContext)
    kwargs = {}

    # Check if base_path is a parameter (newer versions)
    # base_path should be the parent directory, not logs itself
    if "base_path" in sig.parameters:
        kwargs["base_path"] = tmpdir

    base_candidates = {
        "session_id": extras.get("session_id", "test-session-123"),
        "work_dir": tmpdir,  # newer variants
        "workdir": tmpdir,  # older variants
        "project_root": tmpdir,
        "logs_dir": tmpdir / "logs",  # Try this too
        # DO NOT pass logs_dir here if base_path is used
    }

    for name, value in base_candidates.items():
        if name in sig.parameters and name not in kwargs:
            kwargs[name] = value

    for k, v in extras.items():
        if k in sig.parameters and k not in kwargs:
            kwargs[k] = v

    ctx = ExecutionContext(**kwargs)

    # Post-set optional attributes if object supports them
    # logs_dir is a read-only property, so we can't set it
    # It's derived from base_path

    return ctx


def _merge_env():
    """Merge environment from both os.environ and .env file."""
    env = os.environ.copy()

    # Try to load .env file
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    # Only set if not already in environment
                    if key not in env:
                        env[key] = value.strip('"').strip("'")

    return env


@pytest.fixture(scope="session")
def e2b_env():
    """Provide E2B environment configuration, skip if not available."""
    env = _merge_env()
    api_key = env.get("E2B_API_KEY")

    # Don't skip if no API key - let tests handle it
    return {"E2B_API_KEY": api_key} if api_key else {}


def _create_test_e2b_adapter(use_real=False, api_key=None):
    """Create E2B adapter for testing.

    Args:
        use_real: If True, use real E2B adapter with mocked transport.
                 If False, return fully mocked adapter.
        api_key: Optional API key for real tests.

    Returns:
        E2BAdapter instance (possibly with mocked transport)
    """
    if use_real:
        # Create real adapter with test config
        adapter = E2BAdapter(
            {
                "timeout": 300,
                "cpu": 2,
                "memory": 4,
                "verbose": True,
                "env": {"TEST_MODE": "true"},
            }
        )

        # If no API key, mock the client to avoid real API calls
        if not api_key:
            mock_client = MagicMock(spec=E2BClient)
            mock_handle = SandboxHandle(
                sandbox_id="test-sandbox-123", status=SandboxStatus.RUNNING, metadata={}
            )
            mock_client.create_sandbox.return_value = mock_handle
            mock_client.upload_payload.return_value = None
            mock_client.start.return_value = "process-123"
            mock_client.poll_until_complete.return_value = FinalStatus(
                status=SandboxStatus.SUCCESS,
                exit_code=0,
                duration_seconds=1.5,
                stdout="Pipeline executed successfully",
                stderr=None,
            )
            mock_client.download_file.return_value = b'{"ok": true}'
            mock_client.transport.list_files.return_value = []
            adapter.client = mock_client

        return adapter
    else:
        # Return a fully mocked adapter
        mock_adapter = MagicMock()
        mock_adapter.prepare.return_value = MagicMock(
            plan={},
            metadata={"adapter_target": "e2b"},
            io_layout={"remote_logs_dir": "/tmp/logs"},
            run_params={"timeout": 300},
            constraints={},
            cfg_index={},
        )
        mock_adapter.execute.return_value = MagicMock(
            success=True, exit_code=0, duration_seconds=1.5, error_message=None
        )
        mock_adapter.collect.return_value = MagicMock(
            events_log=None,
            metrics_log=None,
            execution_log=None,
            artifacts_dir=None,
            metadata={"adapter": "e2b"},
        )
        return mock_adapter


@pytest.fixture
def e2b_sandbox(e2b_env):
    """E2B sandbox adapter for testing.

    Returns real E2B adapter with mocked transport unless E2B_LIVE_TESTS is set.
    """
    # Check if we should use real E2B
    use_live = os.getenv("E2B_LIVE_TESTS") == "1"
    api_key = e2b_env.get("E2B_API_KEY") if use_live else None

    # Create adapter (real or mocked based on environment)
    adapter = _create_test_e2b_adapter(use_real=True, api_key=api_key)

    # Track created sandboxes for cleanup
    created_handles = []

    if use_live and api_key:
        # For live tests, track real sandbox handles
        original_execute = adapter.execute

        def tracked_execute(prepared, context):
            result = original_execute(prepared, context)
            if adapter.sandbox_handle:
                created_handles.append(adapter.sandbox_handle)
            return result

        adapter.execute = tracked_execute

    try:
        yield adapter
    finally:
        # Cleanup any created sandboxes
        if use_live and adapter.client:
            for handle in created_handles:
                with contextlib.suppress(Exception):
                    adapter.client.close(handle)


@pytest.fixture
def execution_context():
    """Create execution context for E2B tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        context = make_execution_context(Path(tmpdir))
        # logs_dir and artifacts_dir are properties, just ensure directories exist
        if hasattr(context, "logs_dir"):
            context.logs_dir.mkdir(parents=True, exist_ok=True)
        if hasattr(context, "artifacts_dir"):
            context.artifacts_dir.mkdir(parents=True, exist_ok=True)
        yield context


@pytest.fixture
def small_pipeline():
    """Small test pipeline for E2B execution.

    Returns a compiled manifest ready for execution.
    """
    return {
        "pipeline": {
            "id": "test-pipeline-123",
            "name": "test-pipeline",
        },
        "steps": [
            {
                "id": "generate_test_data",
                "component": "duckdb.processor",
                "driver": "duckdb_processor",
                "mode": "transform",
                "config": {"query": "SELECT 1 as id, 'test' as name"},
                "needs": [],
                "cfg_path": "cfg/generate_test_data.json",
            },
            {
                "id": "write_output",
                "component": "filesystem.csv_writer",
                "driver": "filesystem_csv_writer",
                "mode": "write",
                "config": {"path": "output.csv"},
                "needs": ["generate_test_data"],
                "cfg_path": "cfg/write_output.json",
            },
        ],
        "metadata": {
            "fingerprint": "test-fingerprint-123",
            "compiled_at": "2025-01-01T00:00:00Z",
            "source_manifest_path": "test.yaml",
        },
    }


@pytest.fixture
def resource_intensive_pipeline():
    """Pipeline requiring specific CPU/memory resources.

    Returns a compiled manifest for resource-intensive execution.
    """
    return {
        "pipeline": {
            "id": "resource-test-123",
            "name": "resource-test-pipeline",
        },
        "steps": [
            {
                "id": "heavy_processing",
                "component": "duckdb.processor",
                "driver": "duckdb_processor",
                "mode": "transform",
                "config": {
                    "query": """
                        WITH RECURSIVE numbers(n) AS (
                            SELECT 1
                            UNION ALL
                            SELECT n + 1 FROM numbers WHERE n < 1000000
                        )
                        SELECT COUNT(*) as total FROM numbers
                    """
                },
                "needs": [],
                "cfg_path": "cfg/heavy_processing.json",
            }
        ],
        "metadata": {
            "fingerprint": "resource-test-fingerprint",
            "compiled_at": "2025-01-01T00:00:00Z",
            "source_manifest_path": "resource-test.yaml",
        },
    }


@pytest.fixture
def timeout_prone_pipeline():
    """Pipeline that will timeout/abort to test error handling."""
    return {
        "pipeline": {
            "id": "timeout-test-123",
            "name": "timeout-test-pipeline",
        },
        "steps": [
            {
                "id": "slow_processing",
                "component": "python.script",
                "driver": "python_script",
                "mode": "transform",
                "config": {
                    "script": """
import time
# Simulate very slow processing
time.sleep(3600)  # Sleep for 1 hour - will timeout
print("This should never print")
                    """
                },
                "needs": [],
                "cfg_path": "cfg/slow_processing.json",
            }
        ],
        "metadata": {
            "fingerprint": "timeout-test-fingerprint",
            "compiled_at": "2025-01-01T00:00:00Z",
            "source_manifest_path": "timeout-test.yaml",
        },
    }
