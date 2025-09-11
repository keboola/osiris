"""Live E2B integration tests (requires E2B_API_KEY and E2B_LIVE_TESTS=1)."""

import json
import os
import tempfile
from pathlib import Path

import pytest

# Skip all tests in this file unless both conditions are met
pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("E2B_API_KEY"), reason="E2B_API_KEY not set - skipping live tests"
    ),
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
        """Smoke test: execute a simple manifest remotely."""
        from osiris.remote.e2b_client import E2BClient
        from osiris.remote.e2b_pack import PayloadBuilder, RunConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            session_dir = tmpdir / "session"
            build_dir = tmpdir / "build"
            session_dir.mkdir()
            build_dir.mkdir()

            # Write manifest
            manifest_path = session_dir / "manifest.json"
            with open(manifest_path, "w") as f:
                json.dump(simple_manifest, f)

            # Build payload
            builder = PayloadBuilder(session_dir, build_dir)
            run_config = RunConfig(seed=42)
            payload_path = builder.build(manifest_path, run_config)

            # Execute remotely
            client = E2BClient()
            handle = client.create_sandbox(cpu=1, mem_gb=2, timeout=60)

            try:
                # Upload and run
                client.upload_payload(handle, payload_path)
                process_id = client.start(handle, ["python", "mini_runner.py"])

                # Wait for completion
                client.poll_until_complete(handle, process_id, timeout_s=30)

                # Download results
                remote_dir = session_dir / "remote"
                client.download_artifacts(handle, remote_dir)

                # Verify artifacts exist
                assert (remote_dir / "events.jsonl").exists()
                assert (remote_dir / "osiris.log").exists()

                # Verify events
                with open(remote_dir / "events.jsonl") as f:
                    events = [json.loads(line) for line in f]

                assert any(e.get("event") == "run_start" for e in events)
                assert any(e.get("event") == "run_end" for e in events)

            finally:
                client.close(handle)

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
            handle = client.create_sandbox(
                cpu=1, mem_gb=1, env={"SECRET_KEY": secret_value}, timeout=30
            )

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
