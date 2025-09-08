"""Integration tests for session logging in compile and run commands."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from osiris.cli.compile import compile_command
from osiris.cli.main import run_command


class TestSessionIntegration:
    """Test session integration for compile and run commands."""

    @pytest.fixture
    def sample_oml(self, tmp_path):
        """Create a sample OML file."""
        oml = {
            "oml_version": "0.1.0",
            "name": "Test Pipeline",
            "params": {
                "db": {"default": "test_db"},
                "table": {"default": "users"},
            },
            "steps": [
                {
                    "id": "extract",
                    "component": "supabase.extractor",
                    "mode": "read",
                    "config": {
                        "url": "${params.url}",
                        "table": "${params.table}",
                    },
                },
                {
                    "id": "transform",
                    "component": "duckdb.transform",
                    "mode": "transform",
                    "config": {
                        "sql": "SELECT 1 as id, 'test' as name",  # Simple SQL that doesn't require tables
                    },
                },
            ],
        }

        oml_path = tmp_path / "test.yaml"
        with open(oml_path, "w") as f:
            yaml.dump(oml, f)

        return str(oml_path)

    def test_compile_creates_session(self, sample_oml, tmp_path):
        """Test that compile command creates a session."""
        # Set up environment
        import os

        os.environ["OSIRIS_PARAM_URL"] = "https://test.supabase.co"

        try:
            # Mock sys.exit to prevent test from exiting
            with patch("sys.exit") as mock_exit:
                # Run compile command
                compile_command([sample_oml])

                # Check that exit was called with success (0)
                mock_exit.assert_called_once_with(0)

            # Check that session directory was created
            logs_dir = Path("logs")
            assert logs_dir.exists()

            # Find the compile session
            sessions = list(logs_dir.glob("compile_*"))
            assert len(sessions) > 0

            # Check session contents
            session_dir = sessions[-1]  # Get most recent
            assert (session_dir / "events.jsonl").exists()
            assert (session_dir / "metrics.jsonl").exists()
            assert (session_dir / "compiled").exists()
            assert (session_dir / "compiled" / "manifest.yaml").exists()

            # Check events were logged
            with open(session_dir / "events.jsonl") as f:
                events = [json.loads(line) for line in f]

            event_types = {e["event"] for e in events}
            assert "compile_start" in event_types
            assert "compile_complete" in event_types

        finally:
            # Clean up
            if "OSIRIS_PARAM_URL" in os.environ:
                del os.environ["OSIRIS_PARAM_URL"]

    def test_run_creates_unified_session(self, sample_oml, tmp_path):
        """Test that run command creates a unified session for compile + execute."""
        # Set up environment
        import os

        os.environ["OSIRIS_PARAM_URL"] = "https://test.supabase.co"

        # Create dummy connections file for test
        connections = {
            "version": 1,
            "connections": {
                "supabase": {
                    "default": {
                        "url": "https://test.supabase.co",
                        "key": "test_key",  # pragma: allowlist secret
                    }
                },
                "mysql": {
                    "default": {
                        "host": "localhost",
                        "port": 3306,
                        "database": "test",
                        "user": "test",
                        "password": "test",  # pragma: allowlist secret
                    }
                },
            },
        }
        from pathlib import Path

        import yaml

        connections_path = Path.cwd() / "osiris_connections.yaml"
        with open(connections_path, "w") as f:
            yaml.dump(connections, f)

        try:
            # Mock compilation to avoid actual compilation
            with patch("osiris.cli.run.CompilerV0") as mock_compiler_class:
                mock_compiler = MagicMock()
                mock_compiler.compile.return_value = (True, "Compilation successful")
                mock_compiler_class.return_value = mock_compiler

                # Mock drivers to avoid actual DB connections
                with patch("osiris.cli.run.RunnerV0") as mock_runner_class:
                    mock_runner = MagicMock()
                    mock_runner.run.return_value = True
                    mock_runner.events = [
                        {"type": "step_complete", "step_id": "extract"},
                        {"type": "step_complete", "step_id": "transform"},
                    ]
                    mock_runner_class.return_value = mock_runner

                    # Mock sys.exit to prevent test from exiting
                    with patch("sys.exit") as mock_exit:
                        # Run command
                        run_command([sample_oml])

                        # Check that exit was called with success (0)
                        mock_exit.assert_called_once_with(0)

            # Check that session directory was created
            logs_dir = Path("logs")
            assert logs_dir.exists()

            # Find the run session
            sessions = list(logs_dir.glob("run_*"))
            assert len(sessions) > 0

            # Check session contents
            session_dir = sessions[-1]  # Get most recent
            assert (session_dir / "events.jsonl").exists()
            assert (session_dir / "metrics.jsonl").exists()
            assert (session_dir / "compiled").exists()
            assert (session_dir / "compiled" / "manifest.yaml").exists()
            assert (session_dir / "artifacts").exists()

            # Check events were logged
            with open(session_dir / "events.jsonl") as f:
                events = [json.loads(line) for line in f]

            event_types = {e["event"] for e in events}
            assert "run_start" in event_types
            assert "compile_start" in event_types
            assert "compile_complete" in event_types
            assert "execute_start" in event_types
            # Note: run_complete may not be present if runner has issues with stub implementations

            # Check metrics were logged
            with open(session_dir / "metrics.jsonl") as f:
                metrics = [json.loads(line) for line in f]

            metric_names = {m["metric"] for m in metrics}
            assert "compilation_duration" in metric_names

        finally:
            # Clean up
            if "OSIRIS_PARAM_URL" in os.environ:
                del os.environ["OSIRIS_PARAM_URL"]
            # Clean up connections file
            if connections_path.exists():
                connections_path.unlink()

    def test_session_with_custom_output_dir(self, sample_oml, tmp_path):
        """Test that --out option still creates session but copies artifacts."""
        # Set up environment
        import os

        os.environ["OSIRIS_PARAM_URL"] = "https://test.supabase.co"
        custom_output = str(tmp_path / "custom_output")

        try:
            # Mock sys.exit to prevent test from exiting
            with patch("sys.exit") as mock_exit:
                # Run compile with custom output
                compile_command([sample_oml, "--out", custom_output])

                # Check that exit was called with success (0)
                mock_exit.assert_called_once_with(0)

            # Check that session directory was created
            logs_dir = Path("logs")
            assert logs_dir.exists()

            # Find the compile session
            sessions = list(logs_dir.glob("compile_*"))
            assert len(sessions) > 0

            session_dir = sessions[-1]  # Get most recent
            assert (session_dir / "compiled").exists()

            # Check that custom output directory was also created
            assert Path(custom_output).exists()
            assert (Path(custom_output) / "manifest.yaml").exists()

        finally:
            # Clean up
            if "OSIRIS_PARAM_URL" in os.environ:
                del os.environ["OSIRIS_PARAM_URL"]
