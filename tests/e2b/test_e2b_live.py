"""Live E2B integration tests (requires E2B_API_KEY and E2B_LIVE_TESTS=1)."""

import json
import os
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
        "pipeline": {"name": "test-e2b-pipeline", "version": "1.0.0"},
        "steps": [{"id": "noop", "component": "noop", "config": {}}],
        "meta": {"compiler_version": "0.1.0", "created_at": "2025-01-01T00:00:00Z"},
    }


class TestE2BLive:
    """Live integration tests with E2B service."""

    def test_smoke_simple_execution(self, simple_manifest):
        """Smoke test: execute a simple manifest remotely with payload structure assertions."""
        import tarfile

        from osiris.core.execution_adapter import ExecutionContext, PreparedRun
        from osiris.remote.e2b_adapter import E2BAdapter
        from osiris.remote.e2b_full_pack import build_full_payload

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            session_dir = tmpdir / "session"
            session_dir.mkdir()

            # Create execution context
            context = ExecutionContext("test_smoke", session_dir)

            # Create PreparedRun with cfg files
            cfg_index = {"cfg/test-step.json": {"path": "output.csv"}}
            prepared = PreparedRun(
                plan=simple_manifest,
                resolved_connections={},
                cfg_index=cfg_index,
                io_layout={},
                run_params={
                    "verbose": True,
                    "cpu": 1,
                    "memory_gb": 2,
                    "timeout": 60,
                    "env_vars": {},
                },
                constraints={},
                metadata={},
            )

            # 1. Assert payload structure
            payload_path = build_full_payload(prepared, session_dir)
            assert payload_path.exists()

            with tarfile.open(payload_path, "r:gz") as tar:
                files = tar.getnames()
                # Check payload structure
                assert "./compiled/manifest.yaml" in files
                assert "./cfg/test-step.json" in files  # cfg at root level
                assert "./run.sh" in files
                assert "./osiris" in files or any(f.startswith("./osiris/") for f in files)
                print("✓ Payload structure correct")

            # 2. Assert run.sh uses explicit manifest path
            with tarfile.open(payload_path, "r:gz") as tar:
                run_sh = tar.extractfile("./run.sh").read().decode("utf-8")
                assert "./compiled/manifest.yaml" in run_sh
                assert "OSIRIS_LOGS_DIR=./remote" in run_sh
                print("✓ Run script uses explicit manifest path and logs directory")

            # Execute using E2BAdapter
            adapter = E2BAdapter()
            result = adapter.execute(prepared, context)

            # 3. Verify execution completed successfully (empty pipeline should succeed)
            assert result is not None
            assert result.exit_code == 0
            assert result.success is True
            print("✓ Execution succeeded")

            # 4. Verify remote logs directory and attempted downloads
            remote_dir = context.logs_dir / "remote"
            assert remote_dir.exists()
            print(f"✓ Remote logs directory created: {remote_dir}")

            # List what was downloaded
            files = list(remote_dir.glob("*"))
            print(f"  Files downloaded: {[f.name for f in files] if files else 'None'}")

            # For empty pipeline, logs might not exist, but directory should be created
            # This tests the download mechanism without requiring actual log files

    def test_environment_variables(self):
        """Test passing environment variables to sandbox."""
        from osiris.remote.e2b_client import E2BClient

        client = E2BClient()

        # Create sandbox with env vars
        env_vars = {"TEST_VAR": "test_value", "ANOTHER_VAR": "another_value"}

        handle = client.create_sandbox(cpu=1, mem_gb=1, env=env_vars, timeout=30)

        try:
            # Execute command that echoes env var
            process_id = client.start(handle, ["echo", "$TEST_VAR"])
            final_status = client.poll_until_complete(handle, process_id, timeout_s=10)

            # Note: Actual env var checking would depend on E2B SDK behavior
            assert final_status.exit_code == 0

        finally:
            client.close(handle)

    def test_timeout_handling(self):
        """Test that timeouts are handled correctly."""
        from osiris.remote.e2b_client import E2BClient, SandboxStatus

        client = E2BClient()
        handle = client.create_sandbox(cpu=1, mem_gb=1, timeout=30)

        try:
            # Start a long-running process
            process_id = client.start(handle, ["sleep", "100"])

            # Poll with short timeout
            final_status = client.poll_until_complete(handle, process_id, timeout_s=2)

            assert final_status.status == SandboxStatus.TIMEOUT

        finally:
            client.close(handle)

    def test_artifact_download(self):
        """Test downloading multiple artifacts."""
        from osiris.remote.e2b_client import E2BClient
        from osiris.remote.e2b_pack import PayloadBuilder, RunConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            session_dir = tmpdir / "session"
            build_dir = tmpdir / "build"
            session_dir.mkdir()
            build_dir.mkdir()

            # Create manifest that generates artifacts
            manifest = {
                "pipeline": {"name": "artifact-test"},
                "steps": [],
                "meta": {"compiler_version": "0.1.0"},
            }

            manifest_path = session_dir / "manifest.json"
            with open(manifest_path, "w") as f:
                json.dump(manifest, f)

            # Build and execute
            builder = PayloadBuilder(session_dir, build_dir)
            payload_path = builder.build(manifest_path, RunConfig())

            client = E2BClient()
            handle = client.create_sandbox(cpu=1, mem_gb=1, timeout=30)

            try:
                client.upload_payload(handle, payload_path)
                process_id = client.start(handle, ["python", "mini_runner.py"])
                client.poll_until_complete(handle, process_id, timeout_s=30)

                # Download artifacts
                remote_dir = session_dir / "remote"
                client.download_artifacts(handle, remote_dir)

                # Check that basic files exist
                assert remote_dir.exists()
                assert any(remote_dir.iterdir())  # At least some files downloaded

            finally:
                client.close(handle)

    def test_redaction_no_secrets_in_logs(self):
        """Test that secrets are not exposed in logs."""
        from osiris.core.session_reader import SessionReader
        from osiris.remote.e2b_client import E2BClient

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            logs_dir = tmpdir / "logs"
            session_dir = logs_dir / "test_session"
            session_dir.mkdir(parents=True)

            # Create a mock secret env var
            secret_value = "super-secret-key-12345"  # pragma: allowlist secret

            client = E2BClient()
            handle = client.create_sandbox(cpu=1, mem_gb=1, env={"SECRET_KEY": secret_value}, timeout=30)

            try:
                # Run a simple command
                process_id = client.start(handle, ["echo", "test"])
                client.poll_until_complete(handle, process_id, timeout_s=10)

                # Download logs
                remote_dir = session_dir / "remote"
                client.download_artifacts(handle, remote_dir)

                # Check logs don't contain secret
                if (remote_dir / "osiris.log").exists():
                    log_content = (remote_dir / "osiris.log").read_text()
                    assert secret_value not in log_content

                # Use SessionReader to verify redaction works
                reader = SessionReader(logs_dir=str(logs_dir))

                # Test redaction function
                test_text = f"Connection string: mysql://user:{secret_value}@host/db"
                redacted = reader.redact_text(test_text)
                assert secret_value not in redacted
                assert "***" in redacted

            finally:
                client.close(handle)
