"""Test E2B full CLI execution in sandbox."""

import os
import tarfile
import tempfile
from pathlib import Path

import pytest

# Skip all tests in this file unless both conditions are met
pytestmark = [
    pytest.mark.skipif(not os.environ.get("E2B_API_KEY"), reason="E2B_API_KEY not set - skipping live tests"),
    pytest.mark.skipif(
        os.environ.get("E2B_LIVE_TESTS") != "1",
        reason="E2B_LIVE_TESTS not set to 1 - skipping live tests",
    ),
]


@pytest.fixture
def simple_manifest():
    """Create a simple test manifest."""
    return {
        "pipeline": {"name": "test-e2b-full-cli", "version": "1.0.0"},
        "steps": [
            {
                "id": "test-step",
                "component": "filesystem.csv.writer",
                "config": {"path": "test_output.csv"},
            }
        ],
        "meta": {"compiler_version": "0.1.0", "created_at": "2025-01-01T00:00:00Z"},
    }


class TestE2BFullCLI:
    """Test full CLI execution in E2B sandbox."""

    def test_full_cli_sandbox_creation(self):
        """Test that we can create a sandbox and get a real ID."""
        from osiris.remote.e2b_client import E2BClient

        client = E2BClient()
        handle = client.create_sandbox(cpu=1, mem_gb=1, timeout=60)

        try:
            # Verify we got a real sandbox ID
            assert handle.sandbox_id is not None
            assert handle.sandbox_id != "unknown"
            assert len(handle.sandbox_id) > 0
            print(f"✓ Created sandbox with ID: {handle.sandbox_id}")

        finally:
            client.close(handle)

    def test_payload_structure(self, simple_manifest):
        """Test that the full payload has the correct structure."""
        from osiris.core.execution_adapter import PreparedRun
        from osiris.remote.e2b_full_pack import build_full_payload

        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / "session"
            session_dir.mkdir()

            # Create a PreparedRun
            prepared = PreparedRun(
                manifest=simple_manifest,
                plan=simple_manifest,
                cfg_index={"cfg/test-step.json": {"path": "test_output.csv"}},
                io_layout={},
                run_params={"verbose": True},
                constraints={},
                metadata={},
            )

            # Build payload
            payload_path = build_full_payload(prepared, session_dir)

            # Verify payload exists
            assert payload_path.exists()
            assert payload_path.suffix == ".tgz"

            # Extract and verify contents
            extract_dir = Path(tmpdir) / "extracted"
            with tarfile.open(payload_path, "r:gz") as tar:
                tar.extractall(extract_dir)

            # Check required files
            assert (extract_dir / "osiris").exists()
            assert (extract_dir / "requirements.txt").exists()
            assert (extract_dir / "run.sh").exists()
            assert (extract_dir / "compiled" / "manifest.yaml").exists()
            assert (extract_dir / "prepared_run.json").exists()

            # Verify run.sh is executable
            run_script = extract_dir / "run.sh"
            assert run_script.stat().st_mode & 0o111  # Check execute permission

            # Verify requirements includes sqlalchemy
            with open(extract_dir / "requirements.txt") as f:
                requirements = f.read()
                assert "sqlalchemy" in requirements

    def test_full_cli_execution_phases(self):
        """Test all execution phases with real E2B sandbox."""
        from osiris.core.execution_adapter import ExecutionContext, PreparedRun
        from osiris.remote.e2b_adapter import E2BAdapter

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ExecutionContext("test_full_cli", Path(tmpdir))

            # Create a simple manifest
            manifest = {
                "pipeline": {"name": "test-phases", "id": "test-123"},
                "steps": [],  # Empty pipeline for phase testing
                "meta": {"compiler_version": "0.1.0"},
            }

            prepared = PreparedRun(
                manifest=manifest,
                plan=manifest,
                cfg_index={},
                io_layout={},
                run_params={
                    "verbose": True,
                    "cpu": 1,
                    "memory_gb": 1,
                    "timeout": 120,
                    "env_vars": {},
                },
                constraints={},
                metadata={},
            )

            adapter = E2BAdapter()

            # Execute and verify phases
            result = adapter.execute(prepared, context)

            # Should succeed even with empty pipeline
            assert result.success is True
            assert result.exit_code == 0

            # Verify remote logs were downloaded
            remote_dir = context.logs_dir / "remote"
            assert remote_dir.exists()

    def test_environment_variable_passing(self):
        """Test that environment variables are passed correctly."""
        from osiris.core.execution_adapter import PreparedRun
        from osiris.remote.e2b_full_pack import get_required_env_vars

        # Create a manifest with MySQL connection
        prepared = PreparedRun(
            manifest={
                "pipeline": {"name": "test-env"},
                "steps": [
                    {
                        "id": "mysql-step",
                        "component": "mysql.extractor",
                        "cfg_path": "cfg/mysql-step.json",
                    }
                ],
            },
            plan={},
            cfg_index={
                "cfg/mysql-step.json": {
                    "host": "${MYSQL_HOST}",
                    "password": "${MYSQL_PASSWORD}",
                }
            },
            io_layout={},
            run_params={},
            constraints={},
            metadata={},
        )

        # Get required env vars
        env_vars = get_required_env_vars(prepared)

        # Should include MySQL env vars
        assert "MYSQL_HOST" in env_vars
        assert "MYSQL_PASSWORD" in env_vars

    def test_error_handling_missing_dependencies(self):
        """Test that missing dependencies are properly reported."""
        from osiris.core.execution_adapter import ExecuteError, ExecutionContext, PreparedRun
        from osiris.remote.e2b_adapter import E2BAdapter

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ExecutionContext("test_error", Path(tmpdir))

            # Create a manifest that requires a missing package
            manifest = {
                "pipeline": {"name": "test-missing-dep"},
                "steps": [
                    {
                        "id": "bad-step",
                        "component": "nonexistent.component",
                        "cfg_path": "cfg/bad-step.json",
                    }
                ],
            }

            prepared = PreparedRun(
                manifest=manifest,
                plan=manifest,
                cfg_index={"cfg/bad-step.json": {}},
                io_layout={},
                run_params={
                    "verbose": True,
                    "cpu": 1,
                    "memory_gb": 1,
                    "timeout": 60,
                    "env_vars": {},
                },
                constraints={},
                metadata={},
            )

            adapter = E2BAdapter()

            # Should raise ExecuteError
            with pytest.raises(ExecuteError) as exc_info:
                adapter.execute(prepared, context)

            # Error should include sandbox ID
            assert "sandbox" in str(exc_info.value).lower()

            # Logs should still be downloaded
            # remote_dir = context.logs_dir / "remote"
            # May or may not exist depending on failure point
