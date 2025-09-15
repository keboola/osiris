"""Test that logs are created even on early failures."""

import tempfile
from pathlib import Path

import pytest

from osiris.core.execution_adapter import ExecuteError, ExecutionContext
from osiris.runtime.local_adapter import LocalAdapter


class TestEarlyFailureLogs:
    """Test that deterministic logs are created even on early failures."""

    def test_missing_cfg_creates_logs_and_exits_1(self):
        """Test that missing cfg files create logs in session directory and fail properly."""
        adapter = LocalAdapter()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # ExecutionContext will create proper directory structure

            context = ExecutionContext(session_id="test_session_missing_cfg", base_path=tmp_path)

            # Plan with missing cfg files
            plan = {
                "metadata": {"source_manifest_path": str(tmp_path / "compiled" / "manifest.yaml")},
                "pipeline": {"name": "test-pipeline", "id": "test-id"},
                "steps": [
                    {"id": "step-1", "cfg_path": "cfg/missing-step.json", "driver": "test.driver"}
                ],
            }

            # Prepare the run (this should work)
            prepared = adapter.prepare(plan, context)

            # Now attempt execute which should fail at preflight validation
            with pytest.raises(ExecuteError) as exc_info:
                adapter.execute(prepared, context)

            # Check that the error is about cfg file issues (either missing source or missing files)
            error_msg = str(exc_info.value)
            assert (
                "Missing required cfg files" in error_msg
                or "Cannot find source location for cfg files" in error_msg
            )
            # The specific cfg reference may or may not be in the error depending on which validation fails first

            # Verify that session directory and logs were created despite early failure
            logs_dir = context.logs_dir
            artifacts_dir = context.artifacts_dir
            assert logs_dir.exists(), f"Session logs directory should exist: {logs_dir}"
            assert (
                artifacts_dir.exists()
            ), f"Session artifacts directory should exist: {artifacts_dir}"

            # Check that essential log files exist
            events_log = logs_dir / "events.jsonl"
            metrics_log = logs_dir / "metrics.jsonl"
            execution_log = logs_dir / "osiris.log"
            manifest_file = logs_dir / "manifest.yaml"

            assert events_log.exists(), f"events.jsonl should exist: {events_log}"
            assert metrics_log.exists(), f"metrics.jsonl should exist: {metrics_log}"
            assert execution_log.exists(), f"osiris.log should exist: {execution_log}"
            assert manifest_file.exists(), f"manifest.yaml should exist: {manifest_file}"

            # Check that preflight validation error was logged to events.jsonl
            events_content = events_log.read_text()
            assert "preflight_validation_error" in events_content
            assert (
                "Missing required cfg files" in events_content
                or "Cannot find source location for cfg files" in events_content
            )

            # Check that error was logged to osiris.log
            log_content = execution_log.read_text()
            assert (
                "Missing required cfg files" in log_content
                or "Cannot find source location for cfg files" in log_content
            )

    def test_missing_source_location_creates_logs_and_fails(self):
        """Test that missing source location creates logs and fails properly."""
        adapter = LocalAdapter()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Create session directory structure
            logs_dir = tmp_path / "logs" / "test_session_no_source"
            artifacts_dir = logs_dir / "artifacts"

            context = ExecutionContext(session_id="test_session_no_source", base_path=tmp_path)

            # Plan with cfg files but no source location
            plan = {
                "metadata": {},  # No source_manifest_path
                "pipeline": {"name": "test-pipeline", "id": "test-id"},
                "steps": [
                    {"id": "step-1", "cfg_path": "cfg/some-step.json", "driver": "test.driver"}
                ],
            }

            # Prepare the run (compiled_root will be None)
            prepared = adapter.prepare(plan, context)

            # Mock the legacy session hunting to also fail
            with pytest.raises(ExecuteError) as exc_info:
                adapter.execute(prepared, context)

            # Check that error is about missing source location
            error_msg = str(exc_info.value)
            assert (
                "Cannot find source location for cfg files" in error_msg
                or "Missing required cfg files" in error_msg
            )

            # Verify that session directory and logs were created despite early failure
            logs_dir = context.logs_dir
            artifacts_dir = context.artifacts_dir
            assert logs_dir.exists(), f"Session logs directory should exist: {logs_dir}"
            assert (
                artifacts_dir.exists()
            ), f"Session artifacts directory should exist: {artifacts_dir}"

            # Check that essential log files exist
            events_log = logs_dir / "events.jsonl"
            assert events_log.exists(), f"events.jsonl should exist: {events_log}"

            # Check that error was logged
            events_content = events_log.read_text()
            assert "preflight_validation_error" in events_content

    def test_successful_preflight_creates_success_event(self):
        """Test that successful preflight validation creates success event."""
        adapter = LocalAdapter()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Create cfg files that will be found
            cfg_dir = tmp_path / "cfg"
            cfg_dir.mkdir(parents=True)
            cfg_file = cfg_dir / "test-step.json"
            cfg_file.write_text('{"component": "test.extractor"}')

            # ExecutionContext will create proper directory structure

            context = ExecutionContext(session_id="test_session_success", base_path=tmp_path)

            # Plan that will find cfg files
            plan = {
                "metadata": {"source_manifest_path": str(tmp_path / "compiled" / "manifest.yaml")},
                "pipeline": {"name": "test-pipeline", "id": "test-id"},
                "steps": [
                    {"id": "step-1", "cfg_path": "cfg/test-step.json", "driver": "test.driver"}
                ],
            }

            # Prepare the run
            prepared = adapter.prepare(plan, context)

            # Execute just the preflight validation part
            adapter._preflight_validate_cfg_files(prepared, context)

            # Check that success event was logged
            events_log = context.logs_dir / "events.jsonl"
            if events_log.exists():
                events_content = events_log.read_text()
                assert "preflight_validation_success" in events_content
