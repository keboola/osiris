"""Gated E2B smoke tests for remote execution."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from osiris.remote.e2b_adapter import E2BAdapter


class TestE2BSmoke:
    """Smoke tests for E2B remote execution (gated by environment variables)."""

    @pytest.fixture
    def example_pipeline_path(self):
        """Path to the example pipeline."""
        return Path(__file__).parent.parent.parent / "docs" / "examples" / "mysql_to_local_csv_all_tables.yaml"

    @pytest.fixture
    def compiled_manifest(self):
        """Mock compiled manifest for testing."""
        return {
            "pipeline": {
                "id": "test-pipeline",
                "name": "mysql-to-local-csv-all-tables",
            },
            "steps": [
                {
                    "id": "extract-actors",
                    "component": "mysql.extractor",
                    "mode": "extract",
                    "cfg_path": "cfg/extract-actors.json",
                    "needs": [],
                },
                {
                    "id": "write-actors-csv",
                    "component": "filesystem.csv_writer",
                    "mode": "write",
                    "cfg_path": "cfg/write-actors-csv.json",
                    "needs": ["extract-actors"],
                },
            ],
            "metadata": {
                "fingerprint": "test-123",
                "compiled_at": "2025-01-01T00:00:00Z",
            },
        }

    @pytest.fixture
    def e2b_config(self):
        """E2B configuration for testing."""
        return {
            "timeout": 300,
            "cpu": 2,
            "memory": 4,
            "env": {
                "MYSQL_PASSWORD": os.environ.get("MYSQL_PASSWORD", "test123"),
            },
            "verbose": True,
        }

    @pytest.mark.e2b_smoke
    def test_e2b_environment_check(self):
        """Test that checks E2B environment setup."""
        api_key = os.environ.get("E2B_API_KEY")
        live_tests = os.environ.get("E2B_LIVE_TESTS")

        if not api_key:
            pytest.skip("E2B_API_KEY not set - skipping E2B tests")

        if not live_tests:
            pytest.skip("E2B_LIVE_TESTS not enabled - skipping live E2B tests")

        # If we get here, environment is properly configured
        assert api_key is not None
        assert live_tests is not None

    @pytest.mark.e2b_smoke
    @pytest.mark.e2b_live
    @pytest.mark.skipif(not os.getenv("E2B_API_KEY"), reason="E2B_API_KEY not set")
    @pytest.mark.skipif(not os.getenv("E2B_LIVE_TESTS"), reason="E2B_LIVE_TESTS not enabled")
    def test_e2b_adapter_prepare_phase(self, compiled_manifest, e2b_config, execution_context):
        """Test E2B adapter prepare phase (live test)."""
        adapter = E2BAdapter(e2b_config)
        context = execution_context

        # Test prepare
        prepared = adapter.prepare(compiled_manifest, context)

        # Verify PreparedRun structure
        assert prepared.plan == compiled_manifest
        assert prepared.metadata["session_id"] == "test-session-123"
        assert prepared.metadata["adapter_target"] == "e2b"
        assert prepared.metadata["pipeline_name"] == "mysql-to-local-csv-all-tables"

        # Verify E2B-specific configuration
        assert prepared.run_params["timeout"] == 300
        assert prepared.run_params["cpu"] == 2
        assert prepared.run_params["memory_gb"] == 4

        # Verify I/O layout for remote execution
        assert "remote_logs_dir" in prepared.io_layout
        assert "remote_work_dir" in prepared.io_layout
        assert prepared.io_layout["remote_work_dir"] == "/home/user"

        # Verify constraints
        assert prepared.constraints["max_duration_seconds"] == 300
        assert prepared.constraints["max_memory_mb"] == 4096

        # Verify cfg_index was built from steps
        assert isinstance(prepared.cfg_index, dict)
        assert "cfg/extract-actors.json" in prepared.cfg_index
        assert "cfg/write-actors-csv.json" in prepared.cfg_index

        # Verify cfg_index content
        extract_cfg = prepared.cfg_index["cfg/extract-actors.json"]
        assert extract_cfg["id"] == "extract-actors"
        assert extract_cfg["component"] == "mysql.extractor"

        write_cfg = prepared.cfg_index["cfg/write-actors-csv.json"]
        assert write_cfg["id"] == "write-actors-csv"
        assert write_cfg["component"] == "filesystem.csv_writer"

    @pytest.mark.e2b_smoke
    @pytest.mark.skipif(not os.getenv("E2B_API_KEY"), reason="E2B_API_KEY not set")
    @pytest.mark.skipif(not os.getenv("E2B_LIVE_TESTS"), reason="E2B_LIVE_TESTS not enabled")
    @patch("osiris.remote.e2b_adapter.E2BClient")
    def test_e2b_adapter_mock_execution(self, mock_client_class, compiled_manifest, e2b_config, execution_context):
        """Test E2B adapter execution with mocked client (safer for CI)."""
        # Setup mock E2B client
        mock_client = MagicMock()
        mock_handle = MagicMock()
        mock_handle.sandbox_id = "test-sandbox-123"

        mock_client.create_sandbox.return_value = mock_handle
        mock_client.start.return_value = "process-123"

        # Mock successful execution
        mock_final_status = MagicMock()
        mock_final_status.status.value = "success"
        mock_final_status.exit_code = 0
        mock_final_status.stdout = "Pipeline completed successfully"
        mock_final_status.stderr = None
        mock_client.poll_until_complete.return_value = mock_final_status

        mock_client_class.return_value = mock_client

        adapter = E2BAdapter(e2b_config)
        context = execution_context

        # Prepare
        prepared = adapter.prepare(compiled_manifest, context)

        # Execute
        result = adapter.execute(prepared, context)

        # Verify execution result
        assert result.success is True
        assert result.exit_code == 0
        assert result.duration_seconds > 0
        assert result.error_message is None

        # Verify E2B client calls
        mock_client.create_sandbox.assert_called_once_with(cpu=2, mem_gb=4, env=e2b_config["env"], timeout=300)
        mock_client.upload_payload.assert_called_once()
        mock_client.start.assert_called_once()
        mock_client.poll_until_complete.assert_called_once()

    @pytest.mark.e2b_smoke
    @pytest.mark.skipif(not os.getenv("E2B_API_KEY"), reason="E2B_API_KEY not set")
    @pytest.mark.skipif(not os.getenv("E2B_LIVE_TESTS"), reason="E2B_LIVE_TESTS not enabled")
    @patch("osiris.remote.e2b_adapter.E2BClient")
    def test_e2b_adapter_collect_artifacts(self, mock_client_class, compiled_manifest, e2b_config, execution_context):
        """Test E2B adapter artifact collection."""
        # Setup mock E2B client
        mock_client = MagicMock()
        mock_handle = MagicMock()
        mock_handle.sandbox_id = "test-sandbox-123"

        mock_client.create_sandbox.return_value = mock_handle
        mock_client.start.return_value = "process-123"

        # Mock successful execution
        mock_final_status = MagicMock()
        mock_final_status.status.value = "success"
        mock_final_status.exit_code = 0
        mock_final_status.stdout = "Pipeline completed"
        mock_final_status.stderr = None
        mock_client.poll_until_complete.return_value = mock_final_status

        mock_client_class.return_value = mock_client

        adapter = E2BAdapter(e2b_config)
        context = execution_context

        # Prepare and execute
        prepared = adapter.prepare(compiled_manifest, context)
        _ = adapter.execute(prepared, context)

        # Create mock remote artifacts for collection
        remote_logs_dir = Path(prepared.io_layout["remote_logs_dir"])
        remote_logs_dir.mkdir(parents=True, exist_ok=True)

        # Simulate downloaded artifacts
        events_file = remote_logs_dir / "events.jsonl"
        events_file.write_text('{"event": "run_complete", "source": "remote"}\n')

        metrics_file = remote_logs_dir / "metrics.jsonl"
        metrics_file.write_text('{"metric": "rows_read", "value": 100, "source": "remote"}\n')

        log_file = remote_logs_dir / "osiris.log"
        log_file.write_text("Remote execution log\n")

        artifacts_dir = remote_logs_dir / "artifacts"
        artifacts_dir.mkdir()
        csv_file = artifacts_dir / "actors.csv"
        csv_file.write_text("id,name\n1,Remote Actor\n")

        # Test collect
        artifacts = adapter.collect(prepared, context)

        # Verify collected artifacts
        assert artifacts.events_log == events_file
        assert artifacts.metrics_log == metrics_file
        assert artifacts.execution_log == log_file
        assert artifacts.artifacts_dir == artifacts_dir

        # Verify E2B-specific metadata
        assert artifacts.metadata["adapter"] == "e2b"
        assert artifacts.metadata["source"] == "remote"
        assert artifacts.metadata["sandbox_id"] == "test-sandbox-123"

        # Verify download was called
        mock_client.download_artifacts.assert_called_once()

    @pytest.mark.e2b_smoke
    def test_e2b_adapter_without_api_key(self, compiled_manifest, e2b_config, execution_context):
        """Test E2B adapter behavior when API key is missing."""
        adapter = E2BAdapter(e2b_config)
        context = execution_context

        # Prepare should work
        prepared = adapter.prepare(compiled_manifest, context)
        assert prepared.metadata["adapter_target"] == "e2b"

        # Execute should fail without API key
        with patch.dict(os.environ, {}, clear=True), pytest.raises(Exception, match="E2B_API_KEY"):
            adapter.execute(prepared, context)

    @pytest.mark.e2b_smoke
    @pytest.mark.skipif(not os.getenv("E2B_API_KEY"), reason="E2B_API_KEY not set")
    @pytest.mark.skipif(not os.getenv("E2B_LIVE_TESTS"), reason="E2B_LIVE_TESTS not enabled")
    def test_e2b_example_pipeline_compatibility(self, example_pipeline_path):
        """Test that example pipeline is compatible with E2B execution."""
        # Verify example pipeline exists
        assert example_pipeline_path.exists()

        # Load and verify structure
        with open(example_pipeline_path) as f:
            pipeline_data = yaml.safe_load(f)

        # Basic validation for E2B compatibility
        assert "oml_version" in pipeline_data
        assert "steps" in pipeline_data

        # Check for MySQL connection usage (will need secrets in E2B)
        steps_text = str(pipeline_data)
        assert "@mysql.db_movies" in steps_text

        # Verify filesystem outputs (should work in E2B)
        filesystem_steps = [step for step in pipeline_data["steps"] if step.get("component") == "filesystem.csv_writer"]
        assert len(filesystem_steps) > 0

        # All filesystem paths should be relative for E2B compatibility
        for step in filesystem_steps:
            path = step.get("config", {}).get("path", "")
            assert not path.startswith("/"), f"Absolute path not E2B compatible: {path}"


class TestE2BAdapterConfiguration:
    """Test E2B adapter configuration and setup."""

    @pytest.mark.e2b_smoke
    def test_e2b_config_defaults(self):
        """Test E2B adapter with default configuration."""
        adapter = E2BAdapter()

        # Should handle empty config gracefully
        assert adapter.e2b_config == {}

    @pytest.mark.e2b_smoke
    def test_e2b_config_custom(self):
        """Test E2B adapter with custom configuration."""
        custom_config = {
            "timeout": 600,
            "cpu": 4,
            "memory": 8,
            "env": {"CUSTOM_VAR": "value"},
        }

        adapter = E2BAdapter(custom_config)
        assert adapter.e2b_config == custom_config

    @pytest.mark.e2b_smoke
    def test_e2b_instructions_for_manual_testing(self):
        """Instructions for running E2B tests manually."""
        instructions = """
        To run E2B smoke tests manually:

        1. Set up E2B account and get API key
        2. Export environment variables:
           export E2B_API_KEY="your-api-key"  # pragma: allowlist secret
           export E2B_LIVE_TESTS=1
           export MYSQL_PASSWORD="your-mysql-password"  # pragma: allowlist secret

        3. Run tests:
           pytest tests/e2b/test_e2b_smoke.py -v

        4. For testing with real example:
           cd testing_env && source .env
           export E2B_LIVE_TESTS=1
           python ../osiris.py run ../docs/examples/mysql_to_local_csv_all_tables.yaml --e2b
        """

        # This test just documents the process
        assert "E2B_API_KEY" in instructions
        assert "E2B_LIVE_TESTS" in instructions
