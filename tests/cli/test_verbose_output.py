"""Tests for verbose output in local and E2B execution."""

import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from osiris.core.execution_adapter import ExecutionContext
from osiris.remote.e2b_adapter import E2BAdapter
from osiris.runtime.local_adapter import LocalAdapter


class TestLocalVerboseOutput:
    """Test verbose output for local execution."""

    def test_local_verbose_prints_step_progress(self):
        """Test that --verbose prints step.start/finish summaries for local execution."""
        adapter = LocalAdapter(verbose=True)

        # Create a test manifest
        manifest = {
            "pipeline": {"id": "test-pipeline", "name": "test"},
            "steps": [
                {"id": "step1", "driver": "test.driver"},
                {"id": "step2", "driver": "test.driver"},
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            context = ExecutionContext("test_session", Path(temp_dir))

            # Prepare
            prepared = adapter.prepare(manifest, context)

            # Mock the runner to simulate execution
            with patch("osiris.runtime.local_adapter.RunnerV0") as mock_runner_class:
                mock_runner = MagicMock()
                mock_runner.run.return_value = True
                mock_runner.events = [
                    {"type": "step_start", "data": {"step_id": "step1"}},
                    {"type": "step_complete", "data": {"step_id": "step1", "rows_read": 100}},
                    {"type": "step_start", "data": {"step_id": "step2"}},
                    {"type": "step_complete", "data": {"step_id": "step2", "rows_written": 100}},
                ]
                mock_runner_class.return_value = mock_runner

                # Capture stdout
                with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                    # Execute
                    result = adapter.execute(prepared, context)

                    # Get printed output
                    output = mock_stdout.getvalue()

                    # Verify verbose output
                    assert "🚀 Executing pipeline with 2 steps" in output
                    assert "step1: Starting..." in output
                    assert "step1: Complete (read 100 rows)" in output
                    assert "step2: Starting..." in output
                    assert "step2: Complete (wrote 100 rows)" in output
                    assert "Pipeline completed" in output

                    # Verify success
                    assert result.success

    def test_local_no_verbose_silent(self):
        """Test that without --verbose, local execution is silent."""
        adapter = LocalAdapter(verbose=False)

        manifest = {
            "pipeline": {"id": "test-pipeline", "name": "test"},
            "steps": [{"id": "step1", "driver": "test.driver"}],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            context = ExecutionContext("test_session", Path(temp_dir))

            prepared = adapter.prepare(manifest, context)

            with patch("osiris.runtime.local_adapter.RunnerV0") as mock_runner_class:
                mock_runner = MagicMock()
                mock_runner.run.return_value = True
                mock_runner.events = [
                    {"type": "step_complete", "data": {"step_id": "step1"}},
                ]
                mock_runner_class.return_value = mock_runner

                with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                    result = adapter.execute(prepared, context)
                    output = mock_stdout.getvalue()

                    # Should be silent
                    assert output == ""
                    assert result.success


class TestE2BVerboseOutput:
    """Test verbose output for E2B execution."""

    def test_e2b_verbose_prints_phases(self):
        """Test that E2B --verbose prints phase progress messages."""
        e2b_config = {
            "timeout": 300,
            "cpu": 2,
            "memory": 4,
            "verbose": True,
        }

        adapter = E2BAdapter(e2b_config)

        manifest = {
            "pipeline": {"id": "test-pipeline", "name": "test"},
            "steps": [
                {"id": "step1", "driver": "test.driver", "cfg_path": "cfg/step1.json"},
            ],
            "metadata": {"source_manifest_path": "/tmp/test/manifest.yaml"},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            context = ExecutionContext("test_session", Path(temp_dir))

            # Prepare
            prepared = adapter.prepare(manifest, context)

            # Mock E2B client
            with patch("osiris.remote.e2b_adapter.E2BClient") as mock_client_class:
                mock_client = MagicMock()
                mock_handle = MagicMock()
                mock_handle.sandbox_id = "test-sandbox"

                mock_client.create_sandbox.return_value = mock_handle
                mock_client.start.return_value = "process-123"

                mock_status = MagicMock()
                mock_status.status.value = "success"
                mock_status.exit_code = 0
                mock_status.stdout = "Success"
                mock_status.stderr = None
                mock_client.poll_until_complete.return_value = mock_status

                mock_client_class.return_value = mock_client

                # Mock payload builder
                with patch("osiris.remote.e2b_adapter.PayloadBuilder") as mock_builder_class:
                    mock_builder = MagicMock()
                    mock_builder.build.return_value = Path(temp_dir) / "payload.tgz"
                    mock_builder_class.return_value = mock_builder

                    # Create dummy payload
                    (Path(temp_dir) / "payload.tgz").touch()

                    # Capture stdout and mock E2B_API_KEY
                    with patch("sys.stdout", new_callable=StringIO) as mock_stdout, patch.dict(
                        "os.environ", {"E2B_API_KEY": "test-key"}  # pragma: allowlist secret
                    ):
                        # Execute
                        result = adapter.execute(prepared, context)

                        output = mock_stdout.getvalue()

                        # Verify verbose output shows phases
                        assert "🔨 Building E2B payload..." in output
                        assert "✓ Payload built" in output
                        assert "🚀 Creating E2B sandbox..." in output
                        assert "✓ Sandbox created" in output
                        assert "📤 Uploading payload to sandbox..." in output
                        assert "✓ Payload uploaded" in output
                        assert "🏃 Starting pipeline execution in sandbox..." in output
                        assert "⏳ Waiting for remote execution" in output
                        assert "✓ Remote execution completed successfully" in output

                        assert result.success

    def test_e2b_no_verbose_silent(self):
        """Test that without verbose, E2B execution is silent."""
        e2b_config = {
            "timeout": 300,
            "cpu": 2,
            "memory": 4,
            "verbose": False,
        }

        adapter = E2BAdapter(e2b_config)

        manifest = {
            "pipeline": {"id": "test-pipeline", "name": "test"},
            "steps": [{"id": "step1", "driver": "test.driver"}],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            context = ExecutionContext("test_session", Path(temp_dir))

            prepared = adapter.prepare(manifest, context)

            with patch("osiris.remote.e2b_adapter.E2BClient") as mock_client_class:
                mock_client = MagicMock()
                mock_handle = MagicMock()
                mock_handle.sandbox_id = "test-sandbox"

                mock_client.create_sandbox.return_value = mock_handle
                mock_client.start.return_value = "process-123"

                mock_status = MagicMock()
                mock_status.status.value = "success"
                mock_status.exit_code = 0
                mock_status.stdout = "Success"
                mock_status.stderr = None
                mock_client.poll_until_complete.return_value = mock_status

                mock_client_class.return_value = mock_client

                with patch("osiris.remote.e2b_adapter.PayloadBuilder") as mock_builder_class:
                    mock_builder = MagicMock()
                    mock_builder.build.return_value = Path(temp_dir) / "payload.tgz"
                    mock_builder_class.return_value = mock_builder

                    (Path(temp_dir) / "payload.tgz").touch()

                    with patch("sys.stdout", new_callable=StringIO) as mock_stdout, patch.dict(
                        "os.environ", {"E2B_API_KEY": "test-key"}  # pragma: allowlist secret
                    ):
                        result = adapter.execute(prepared, context)
                        output = mock_stdout.getvalue()

                        # Should be silent
                        assert output == ""
                        assert result.success
