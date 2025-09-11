"""End-to-end tests for LocalAdapter using example pipeline."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from osiris.core.execution_adapter import ExecutionContext
from osiris.runtime.local_adapter import LocalAdapter


class TestLocalAdapterE2E:
    """End-to-end tests for LocalAdapter execution."""

    @pytest.fixture
    def example_pipeline_path(self):
        """Path to the example pipeline."""
        return (
            Path(__file__).parent.parent.parent
            / "docs"
            / "examples"
            / "mysql_to_local_csv_all_tables.yaml"
        )

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

    def test_local_adapter_prepare_phase(self, compiled_manifest):
        """Test LocalAdapter prepare phase."""
        adapter = LocalAdapter()

        with tempfile.TemporaryDirectory() as temp_dir:
            context = ExecutionContext("test_session", Path(temp_dir))

            # Test prepare
            prepared = adapter.prepare(compiled_manifest, context)

            # Verify PreparedRun structure
            assert prepared.plan == compiled_manifest
            assert prepared.metadata["session_id"] == "test_session"
            assert prepared.metadata["adapter_target"] == "local"
            assert prepared.metadata["pipeline_name"] == "mysql-to-local-csv-all-tables"

            # Verify cfg_index contains step configurations
            assert "cfg/extract-actors.json" in prepared.cfg_index
            assert "cfg/write-actors-csv.json" in prepared.cfg_index

            # Verify I/O layout
            assert "logs_dir" in prepared.io_layout
            assert "artifacts_dir" in prepared.io_layout
            assert "manifest_path" in prepared.io_layout

            # Verify no secrets in PreparedRun
            prepared_json = json.dumps(
                {
                    "plan": prepared.plan,
                    "resolved_connections": prepared.resolved_connections,
                    "cfg_index": prepared.cfg_index,
                }
            )

            # Should not contain actual password values
            assert "password123" not in prepared_json
            assert "secret" not in prepared_json.lower()

    @patch("osiris.runtime.local_adapter.RunnerV0")
    def test_local_adapter_execute_phase_success(self, mock_runner_class, compiled_manifest):
        """Test LocalAdapter execute phase with successful execution."""
        # Setup mock runner
        mock_runner = MagicMock()
        mock_runner.run.return_value = True
        mock_runner.events = [
            {"type": "step_complete", "data": {"step_id": "extract-actors"}},
            {"type": "step_complete", "data": {"step_id": "write-actors-csv"}},
        ]
        mock_runner.results = {"extract-actors": "success", "write-actors-csv": "success"}
        mock_runner_class.return_value = mock_runner

        adapter = LocalAdapter()

        with tempfile.TemporaryDirectory() as temp_dir:
            context = ExecutionContext("test_session", Path(temp_dir))

            # Prepare and execute
            prepared = adapter.prepare(compiled_manifest, context)
            result = adapter.execute(prepared, context)

            # Verify execution result
            assert result.success is True
            assert result.exit_code == 0
            assert result.duration_seconds > 0
            assert result.error_message is None
            assert result.step_results is not None

            # Verify runner was called correctly
            mock_runner_class.assert_called_once()
            mock_runner.run.assert_called_once()

            # Verify manifest was written
            manifest_path = Path(prepared.io_layout["manifest_path"])
            assert manifest_path.exists()

            with open(manifest_path) as f:
                written_manifest = yaml.safe_load(f)
            assert written_manifest == compiled_manifest

    @patch("osiris.runtime.local_adapter.RunnerV0")
    def test_local_adapter_execute_phase_failure(self, mock_runner_class, compiled_manifest):
        """Test LocalAdapter execute phase with failed execution."""
        # Setup mock runner to fail
        mock_runner = MagicMock()
        mock_runner.run.return_value = False
        mock_runner.events = [
            {"type": "step_start", "data": {"step_id": "extract-actors"}},
            {
                "type": "step_error",
                "data": {"step_id": "extract-actors", "error": "Database connection failed"},
            },
        ]
        mock_runner.results = {"extract-actors": "failed"}
        mock_runner_class.return_value = mock_runner

        adapter = LocalAdapter()

        with tempfile.TemporaryDirectory() as temp_dir:
            context = ExecutionContext("test_session", Path(temp_dir))

            # Prepare and execute
            prepared = adapter.prepare(compiled_manifest, context)
            result = adapter.execute(prepared, context)

            # Verify execution result
            assert result.success is False
            assert result.exit_code == 1
            assert result.duration_seconds > 0
            assert "Database connection failed" in result.error_message
            assert result.step_results is not None

    def test_local_adapter_collect_phase(self, compiled_manifest):
        """Test LocalAdapter collect phase."""
        adapter = LocalAdapter()

        with tempfile.TemporaryDirectory() as temp_dir:
            context = ExecutionContext("test_session", Path(temp_dir))

            # Create mock artifact files
            context.logs_dir.mkdir(parents=True, exist_ok=True)
            context.artifacts_dir.mkdir(parents=True, exist_ok=True)

            events_file = context.logs_dir / "events.jsonl"
            events_file.write_text('{"event": "test"}\n')

            metrics_file = context.logs_dir / "metrics.jsonl"
            metrics_file.write_text('{"metric": "rows_read", "value": 100}\n')

            log_file = context.logs_dir / "osiris.log"
            log_file.write_text("Test log entry\n")

            csv_file = context.artifacts_dir / "actors.csv"
            csv_file.write_text("id,name\n1,John Doe\n")

            # Test prepare and collect
            prepared = adapter.prepare(compiled_manifest, context)
            artifacts = adapter.collect(prepared, context)

            # Verify collected artifacts
            assert artifacts.events_log == events_file
            assert artifacts.metrics_log == metrics_file
            assert artifacts.execution_log == log_file
            assert artifacts.artifacts_dir == context.artifacts_dir

            # Verify metadata
            assert artifacts.metadata["adapter"] == "local"  # pragma: allowlist secret
            assert artifacts.metadata["session_id"] == "test_session"
            assert artifacts.metadata["artifacts_count"] == 1  # CSV file
            assert "events_log_size" in artifacts.metadata

    @patch.dict(os.environ, {"MYSQL_PASSWORD": "test123"}, clear=False)  # pragma: allowlist secret
    @patch("osiris.runtime.local_adapter.RunnerV0")
    def test_local_adapter_full_workflow(self, mock_runner_class, compiled_manifest):
        """Test complete LocalAdapter workflow: prepare -> execute -> collect."""
        # Setup mock runner for successful execution
        mock_runner = MagicMock()
        mock_runner.run.return_value = True
        mock_runner.events = [
            {"type": "step_complete", "data": {"step_id": "extract-actors"}},
            {"type": "step_complete", "data": {"step_id": "write-actors-csv"}},
        ]
        mock_runner.results = {"extract-actors": "success", "write-actors-csv": "success"}
        mock_runner_class.return_value = mock_runner

        adapter = LocalAdapter()

        with tempfile.TemporaryDirectory() as temp_dir:
            context = ExecutionContext("test_session", Path(temp_dir))

            # Phase 1: Prepare
            prepared = adapter.prepare(compiled_manifest, context)
            assert prepared.metadata["adapter_target"] == "local"

            # Phase 2: Execute
            result = adapter.execute(prepared, context)
            assert result.success is True
            assert result.exit_code == 0

            # Create some artifacts for collection
            context.logs_dir.mkdir(parents=True, exist_ok=True)
            events_file = context.logs_dir / "events.jsonl"
            events_file.write_text('{"event": "run_complete"}\n')

            # Phase 3: Collect
            artifacts = adapter.collect(prepared, context)
            assert artifacts.events_log == events_file
            assert artifacts.metadata["adapter"] == "local"

            # Verify no secrets in any outputs
            assert "test123" not in str(prepared.plan)
            assert "test123" not in str(prepared.resolved_connections)
            assert "test123" not in events_file.read_text()

    def test_local_adapter_missing_artifacts(self, compiled_manifest):
        """Test LocalAdapter collect when some artifacts are missing."""
        adapter = LocalAdapter()

        with tempfile.TemporaryDirectory() as temp_dir:
            context = ExecutionContext("test_session", Path(temp_dir))

            # Only create logs directory, no artifact files
            context.logs_dir.mkdir(parents=True, exist_ok=True)

            # Test collect with missing files
            prepared = adapter.prepare(compiled_manifest, context)
            artifacts = adapter.collect(prepared, context)

            # Should handle missing files gracefully
            assert artifacts.events_log is None
            assert artifacts.metrics_log is None
            assert artifacts.execution_log is None
            assert artifacts.artifacts_dir is None or not artifacts.artifacts_dir.exists()

            # Metadata should still be present
            assert artifacts.metadata["adapter"] == "local"
            assert artifacts.metadata["session_id"] == "test_session"
            assert artifacts.metadata["artifacts_count"] == 0


class TestLocalAdapterIntegration:
    """Integration tests that require real pipeline files."""

    def test_example_pipeline_exists(self):
        """Verify the example pipeline file exists and is valid."""
        example_path = (
            Path(__file__).parent.parent.parent
            / "docs"
            / "examples"
            / "mysql_to_local_csv_all_tables.yaml"
        )

        assert example_path.exists(), f"Example pipeline not found at {example_path}"

        # Verify it's valid YAML
        with open(example_path) as f:
            pipeline_data = yaml.safe_load(f)

        # Basic structure validation
        assert "oml_version" in pipeline_data
        assert "name" in pipeline_data
        assert "steps" in pipeline_data
        assert len(pipeline_data["steps"]) > 0

        # Verify it uses the expected connections
        steps_text = str(pipeline_data["steps"])
        assert "@mysql.db_movies" in steps_text

    @pytest.mark.skip(reason="Requires actual MySQL connection - run manually with real DB")
    def test_local_adapter_with_real_example(self):
        """Test LocalAdapter with real example pipeline (manual test only)."""
        # This test requires:
        # 1. MYSQL_PASSWORD environment variable
        # 2. Access to MySQL database with movies schema
        # 3. Proper connection configuration

        example_path = (
            Path(__file__).parent.parent.parent
            / "docs"
            / "examples"
            / "mysql_to_local_csv_all_tables.yaml"
        )

        # This would be a real integration test if MySQL is available
        # For CI/CD, this test is skipped
        assert example_path.exists()
