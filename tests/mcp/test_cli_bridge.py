"""
Tests for MCP CLI bridge component.

Tests the CLI-first adapter architecture that delegates operations
to CLI subcommands instead of direct secret access.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

from osiris.mcp.cli_bridge import (
    run_cli_json,
    generate_correlation_id,
    track_metrics,
    map_cli_error_to_mcp,
    ensure_base_path,
)
from osiris.mcp.errors import OsirisError, ErrorFamily


class TestGenerateCorrelationId:
    """Test correlation ID generation."""

    def test_generates_valid_uuid(self):
        """Test that correlation IDs are valid UUIDs."""
        corr_id = generate_correlation_id()
        assert isinstance(corr_id, str)
        assert len(corr_id) == 36  # UUID4 format
        assert corr_id.count('-') == 4

    def test_generates_unique_ids(self):
        """Test that each call generates a unique ID."""
        ids = [generate_correlation_id() for _ in range(100)]
        assert len(set(ids)) == 100  # All unique


class TestTrackMetrics:
    """Test metrics tracking."""

    def test_tracks_basic_metrics(self):
        """Test basic metrics calculation."""
        start_time = 1000.0
        with patch('time.time', return_value=1001.5):  # 1.5s elapsed
            metrics = track_metrics(start_time, 100, 200)

        assert metrics["duration_ms"] == 1500.0
        assert metrics["bytes_in"] == 100
        assert metrics["bytes_out"] == 200
        assert "overhead_ms" in metrics

    def test_handles_zero_bytes(self):
        """Test metrics with zero byte counts."""
        start_time = 1000.0
        with patch('time.time', return_value=1000.1):  # 100ms elapsed
            metrics = track_metrics(start_time, 0, 0)

        assert metrics["duration_ms"] == 100.0
        assert metrics["bytes_in"] == 0
        assert metrics["bytes_out"] == 0


class TestMapCliErrorToMcp:
    """Test CLI error mapping to MCP errors."""

    def test_maps_general_error(self):
        """Test mapping of general errors (exit code 1)."""
        error = map_cli_error_to_mcp(
            exit_code=1,
            stderr="Something went wrong",
            cmd=["osiris", "mcp", "connections", "list"]
        )

        assert isinstance(error, OsirisError)
        assert error.family == ErrorFamily.SEMANTIC
        assert "Something went wrong" in str(error)

    def test_maps_schema_error(self):
        """Test mapping of schema errors (exit code 2)."""
        error = map_cli_error_to_mcp(
            exit_code=2,
            stderr="Invalid argument: connection_id",
            cmd=["osiris", "mcp", "connections", "doctor"]
        )

        assert error.family == ErrorFamily.SCHEMA
        assert "Invalid argument" in str(error)

    def test_maps_timeout_error(self):
        """Test mapping of timeout errors (exit code 124)."""
        error = map_cli_error_to_mcp(
            exit_code=124,
            stderr="Command timed out",
            cmd=["osiris", "mcp", "discovery", "run"]
        )

        assert error.family == ErrorFamily.DISCOVERY  # Timeouts map to DISCOVERY
        assert "Command timed out" in str(error)
        assert "timeout" in error.suggest.lower()

    def test_maps_command_not_found(self):
        """Test mapping of command not found (exit code 127)."""
        error = map_cli_error_to_mcp(
            exit_code=127,
            stderr="/bin/sh: osiris: command not found",
            cmd=["osiris", "mcp", "connections", "list"]
        )

        assert error.family == ErrorFamily.SEMANTIC  # Execution errors map to SEMANTIC
        assert "command not found" in str(error)

    def test_maps_interrupted_errors(self):
        """Test mapping of interrupted errors (SIGINT/SIGTERM)."""
        # SIGINT (130)
        error_sigint = map_cli_error_to_mcp(
            exit_code=130,
            stderr="Interrupted",
            cmd=["osiris", "mcp", "discovery", "run"]
        )
        assert error_sigint.family == ErrorFamily.SEMANTIC  # Interrupted errors map to SEMANTIC

        # SIGTERM (143)
        error_sigterm = map_cli_error_to_mcp(
            exit_code=143,
            stderr="Terminated",
            cmd=["osiris", "mcp", "discovery", "run"]
        )
        assert error_sigterm.family == ErrorFamily.SEMANTIC  # Interrupted errors map to SEMANTIC

    def test_includes_path_in_error(self):
        """Test that error includes path."""
        error = map_cli_error_to_mcp(
            exit_code=1,
            stderr="Error message",
            cmd=["osiris", "mcp", "connections", "list"]
        )

        assert error.path == ["cli_bridge", "run_cli_json"]
        assert error.suggest is not None

    def test_handles_long_stderr(self):
        """Test that very long stderr is handled."""
        long_stderr = "Error: " + "x" * 1000

        error = map_cli_error_to_mcp(
            exit_code=1,
            stderr=long_stderr,
            cmd=["osiris", "mcp", "test"]
        )

        # Message should contain the error
        assert "Error:" in str(error)


class TestEnsureBasePath:
    """Test base path resolution."""

    def test_uses_osiris_home_if_set(self):
        """Test that OSIRIS_HOME env var takes precedence."""
        with patch.dict('os.environ', {'OSIRIS_HOME': '/tmp/test_osiris'}):
            with patch('pathlib.Path.exists', return_value=True):
                base_path = ensure_base_path()
                assert str(base_path) == str(Path('/tmp/test_osiris').resolve())

    def test_loads_from_osiris_yaml(self, tmp_path):
        """Test loading base_path from osiris.yaml."""
        # Create temporary osiris.yaml
        config_file = tmp_path / "osiris.yaml"
        config_file.write_text("""
version: '2.0'
filesystem:
  base_path: "/srv/osiris/test"
""")

        with patch.dict('os.environ', clear=True):  # No OSIRIS_HOME
            with patch('pathlib.Path.cwd', return_value=tmp_path):
                base_path = ensure_base_path()
                # Should resolve the path from config
                assert "osiris" in str(base_path).lower() or str(base_path) == str(tmp_path)

    def test_falls_back_to_cwd(self):
        """Test fallback to current working directory."""
        with patch.dict('os.environ', clear=True):  # No OSIRIS_HOME
            with patch('pathlib.Path.exists', return_value=False):  # No osiris.yaml
                base_path = ensure_base_path()
                assert base_path == Path.cwd().resolve()

    def test_warns_on_invalid_osiris_home(self, caplog):
        """Test warning when OSIRIS_HOME points to non-existent path."""
        with patch.dict('os.environ', {'OSIRIS_HOME': '/nonexistent/path'}):
            with patch('pathlib.Path.exists', side_effect=lambda: False):
                ensure_base_path()
                # Should log a warning but not fail
                assert any("does not exist" in record.message for record in caplog.records)


@pytest.mark.asyncio
class TestRunCliJson:
    """Test the main CLI bridge function."""

    async def test_successful_command(self):
        """Test successful CLI command execution."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "connections": [],
            "count": 0,
            "status": "success"
        })
        mock_result.stderr = ""

        with patch('subprocess.run', return_value=mock_result):
            with patch('osiris.mcp.cli_bridge.ensure_base_path', return_value=Path('/tmp/test')):
                result = await run_cli_json(["mcp", "connections", "list"])

        assert result["status"] == "success"
        assert result["count"] == 0
        assert "_meta" in result
        assert "correlation_id" in result["_meta"]
        assert "duration_ms" in result["_meta"]

    async def test_adds_json_flag(self):
        """Test that --json flag is automatically added."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"status": "success"})
        mock_result.stderr = ""

        with patch('subprocess.run', return_value=mock_result) as mock_run:
            with patch('osiris.mcp.cli_bridge.ensure_base_path', return_value=Path('/tmp/test')):
                await run_cli_json(["mcp", "connections", "list"])

        # Check that subprocess.run was called with --json
        call_args = mock_run.call_args
        assert "--json" in call_args[0][0]  # First positional arg (cmd list)

    async def test_handles_cli_error(self):
        """Test handling of CLI errors."""
        mock_result = Mock()
        mock_result.returncode = 2
        mock_result.stdout = ""
        mock_result.stderr = "Error: connection_id is required"

        with patch('subprocess.run', return_value=mock_result):
            with patch('osiris.mcp.cli_bridge.ensure_base_path', return_value=Path('/tmp/test')):
                with pytest.raises(OsirisError) as exc_info:
                    await run_cli_json(["mcp", "connections", "doctor"])

        # Exit code 2 maps to SCHEMA errors
        assert exc_info.value.family == ErrorFamily.SCHEMA
        assert "connection_id is required" in str(exc_info.value)

    async def test_handles_timeout(self):
        """Test timeout handling."""
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired(['osiris'], 30)):
            with patch('osiris.mcp.cli_bridge.ensure_base_path', return_value=Path('/tmp/test')):
                with pytest.raises(OsirisError) as exc_info:
                    await run_cli_json(["mcp", "discovery", "run"], timeout_s=30.0)

        assert exc_info.value.family == ErrorFamily.DISCOVERY  # Timeouts map to DISCOVERY
        assert "timed out" in str(exc_info.value).lower()

    async def test_handles_invalid_json(self):
        """Test handling of invalid JSON response."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "This is not JSON"
        mock_result.stderr = ""

        with patch('subprocess.run', return_value=mock_result):
            with patch('osiris.mcp.cli_bridge.ensure_base_path', return_value=Path('/tmp/test')):
                with pytest.raises(OsirisError) as exc_info:
                    await run_cli_json(["mcp", "connections", "list"])

        assert exc_info.value.family == ErrorFamily.SEMANTIC
        assert "json" in str(exc_info.value).lower()

    async def test_handles_command_not_found(self):
        """Test handling when osiris.py is not found."""
        with patch('subprocess.run', side_effect=FileNotFoundError("osiris.py not found")):
            with patch('osiris.mcp.cli_bridge.ensure_base_path', return_value=Path('/tmp/test')):
                with pytest.raises(OsirisError) as exc_info:
                    await run_cli_json(["mcp", "connections", "list"])

        assert exc_info.value.family == ErrorFamily.SEMANTIC  # Execution errors map to SEMANTIC
        assert "not found" in str(exc_info.value).lower()

    async def test_passes_environment(self):
        """Test that environment variables are passed to subprocess."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"status": "success"})
        mock_result.stderr = ""

        with patch('subprocess.run', return_value=mock_result) as mock_run:
            with patch('osiris.mcp.cli_bridge.ensure_base_path', return_value=Path('/tmp/test')):
                with patch.dict('os.environ', {'MYSQL_PASSWORD': 'test123'}):  # pragma: allowlist secret
                    await run_cli_json(["mcp", "connections", "list"])

        # Check that environment was passed
        call_kwargs = mock_run.call_args[1]
        assert 'env' in call_kwargs
        # Environment should be a copy of os.environ
        assert isinstance(call_kwargs['env'], dict)

    async def test_custom_correlation_id(self):
        """Test using a custom correlation ID."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"status": "success"})
        mock_result.stderr = ""

        custom_id = "test-correlation-123"

        with patch('subprocess.run', return_value=mock_result):
            with patch('osiris.mcp.cli_bridge.ensure_base_path', return_value=Path('/tmp/test')):
                result = await run_cli_json(
                    ["mcp", "connections", "list"],
                    correlation_id=custom_id
                )

        assert result["_meta"]["correlation_id"] == custom_id

    async def test_custom_timeout(self):
        """Test using a custom timeout."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"status": "success"})
        mock_result.stderr = ""

        with patch('subprocess.run', return_value=mock_result) as mock_run:
            with patch('osiris.mcp.cli_bridge.ensure_base_path', return_value=Path('/tmp/test')):
                await run_cli_json(["mcp", "connections", "list"], timeout_s=60.0)

        # Check timeout was passed
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs['timeout'] == 60.0

    async def test_includes_metrics_in_response(self):
        """Test that response includes execution metrics."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"status": "success"})
        mock_result.stderr = ""

        with patch('subprocess.run', return_value=mock_result):
            with patch('osiris.mcp.cli_bridge.ensure_base_path', return_value=Path('/tmp/test')):
                result = await run_cli_json(["mcp", "connections", "list"])

        meta = result["_meta"]
        assert "duration_ms" in meta
        assert "bytes_in" in meta
        assert "bytes_out" in meta
        assert "cli_command" in meta
        assert meta["cli_command"] == "mcp connections list"
