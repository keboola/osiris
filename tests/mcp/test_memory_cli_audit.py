"""
Tests for MCP memory CLI - stdout/stderr separation, metrics, and resolver.

These tests ensure:
1. JSON output goes to stdout only (no logs)
2. INFO/WARN logs go to stderr when --json is used
3. Memory URI is resolvable via ResourceResolver
4. All responses include correlation_id, duration_ms, bytes_in, bytes_out
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Find osiris.py once at module level
_REPO_ROOT = Path(__file__).parent.parent.parent
_OSIRIS_PY = _REPO_ROOT / "osiris.py"
assert _OSIRIS_PY.exists(), f"osiris.py not found at {_OSIRIS_PY}"


class TestMemoryStdoutStderr:
    """Test stdout/stderr separation for memory capture."""

    def test_json_output_is_clean_on_stdout(self, tmp_path):
        """Test that --json output goes only to stdout (no logs mixed in)."""
        # Create temporary config
        config_file = tmp_path / "osiris.yaml"
        config_file.write_text(
            f"""
filesystem:
  base_path: "{tmp_path}"
  mcp_logs_dir: ".osiris/mcp/logs"
"""
        )

        # Run memory capture with --json
        result = subprocess.run(
            [
                sys.executable,
                str(_OSIRIS_PY),
                "mcp",
                "memory",
                "capture",
                "--session-id",
                "stdout_test",
                "--text",
                "test message",
                "--consent",
                "--json",
            ],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )

        # Stdout should be valid JSON (no INFO/WARN logs)
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Parse stdout as JSON (will fail if logs are mixed in)
        try:
            output = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            pytest.fail(f"Stdout is not valid JSON: {result.stdout}\nError: {e}")

        # Verify it's the expected structure
        assert output["status"] == "success"
        assert output["captured"] is True
        assert "memory_uri" in output

    def test_info_logs_go_to_stderr(self, tmp_path):
        """Test that INFO logs go to stderr when --json is used."""
        config_file = tmp_path / "osiris.yaml"
        config_file.write_text(
            f"""
filesystem:
  base_path: "{tmp_path}"
  mcp_logs_dir: ".osiris/mcp/logs"
"""
        )

        result = subprocess.run(
            [
                sys.executable,
                str(_OSIRIS_PY),
                "mcp",
                "memory",
                "capture",
                "--session-id",
                "stderr_test",
                "--text",
                "test",
                "--consent",
                "--json",
            ],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )

        # INFO logs should be on stderr
        assert "INFO" in result.stderr or result.stderr == "", "Expected INFO logs on stderr or no logs"

        # Stdout should be pure JSON
        assert result.stdout.strip().startswith("{"), "Stdout should start with JSON object"
        assert result.stdout.strip().endswith("}"), "Stdout should end with JSON object"


class TestMemoryMetrics:
    """Test that memory responses include required metrics."""

    def test_cli_output_includes_all_fields(self, tmp_path):
        """Test that CLI output includes status, captured, memory_uri, etc."""
        config_file = tmp_path / "osiris.yaml"
        config_file.write_text(
            f"""
filesystem:
  base_path: "{tmp_path}"
  mcp_logs_dir: ".osiris/mcp/logs"
"""
        )

        result = subprocess.run(
            [
                sys.executable,
                str(_OSIRIS_PY),
                "mcp",
                "memory",
                "capture",
                "--session-id",
                "metrics_test",
                "--text",
                "test",
                "--consent",
                "--json",
            ],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )

        output = json.loads(result.stdout)

        # Check all required fields
        required_fields = [
            "status",
            "captured",
            "memory_id",
            "session_id",
            "memory_uri",
            "retention_days",
            "timestamp",
            "entry_size_bytes",
            "file_path",
        ]

        for field in required_fields:
            assert field in output, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_mcp_tool_includes_metrics(self):
        """Test that MCP tool wrapper adds correlation_id, duration_ms, bytes_in, bytes_out."""
        from osiris.mcp.tools.memory import MemoryTools

        # Create memory tool with audit logger
        class MockAuditLogger:
            def make_correlation_id(self):
                return "mcp_test_123"

        tools = MemoryTools(audit_logger=MockAuditLogger())

        # Call capture (with consent)
        result = await tools.capture(
            {
                "session_id": "test_metrics",
                "consent": True,
                "text": "test",
            }
        )

        # Verify metrics are present in _meta
        assert "_meta" in result, "Missing _meta"
        assert "correlation_id" in result["_meta"], "Missing correlation_id"
        assert "duration_ms" in result["_meta"], "Missing duration_ms"
        assert "bytes_in" in result["_meta"], "Missing bytes_in"
        assert "bytes_out" in result["_meta"], "Missing bytes_out"

        # Verify types
        assert isinstance(result["_meta"]["correlation_id"], str)
        assert isinstance(result["_meta"]["duration_ms"], (int, float))
        assert isinstance(result["_meta"]["bytes_in"], int)
        assert isinstance(result["_meta"]["bytes_out"], int)


class TestMemoryURIResolver:
    """Test that memory URIs are resolvable via ResourceResolver."""

    def test_uri_resolves_to_correct_file(self, tmp_path):
        """Test that memory_uri can be resolved to actual file path."""
        from osiris.mcp.config import MCPFilesystemConfig, MCPConfig
        from osiris.mcp.resolver import ResourceResolver

        # Create config with tmp_path
        fs_config = MCPFilesystemConfig()
        fs_config.base_path = tmp_path
        fs_config.mcp_logs_dir = tmp_path / ".osiris/mcp/logs"

        config = MCPConfig(fs_config=fs_config)
        resolver = ResourceResolver(config=config)

        # Create a test memory file
        memory_uri = "osiris://mcp/memory/sessions/test_session.jsonl"

        # Resolve URI to physical path
        physical_path = resolver._get_physical_path(memory_uri)

        # Verify path structure
        expected_path = tmp_path / ".osiris/mcp/logs/memory/sessions/test_session.jsonl"
        assert physical_path == expected_path

    def test_uri_roundtrip(self, tmp_path):
        """Test that we can write via CLI and read via resolver."""
        config_file = tmp_path / "osiris.yaml"
        config_file.write_text(
            f"""
filesystem:
  base_path: "{tmp_path}"
  mcp_logs_dir: ".osiris/mcp/logs"
"""
        )

        # Write via CLI
        result = subprocess.run(
            [
                sys.executable,
                str(_OSIRIS_PY),
                "mcp",
                "memory",
                "capture",
                "--session-id",
                "roundtrip_test",
                "--text",
                "resolver test data",
                "--consent",
                "--json",
            ],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )

        output = json.loads(result.stdout)
        memory_uri = output["memory_uri"]

        # Resolve URI
        from osiris.mcp.config import MCPFilesystemConfig, MCPConfig
        from osiris.mcp.resolver import ResourceResolver

        fs_config = MCPFilesystemConfig()
        fs_config.base_path = tmp_path
        fs_config.mcp_logs_dir = tmp_path / ".osiris/mcp/logs"

        config = MCPConfig(fs_config=fs_config)
        resolver = ResourceResolver(config=config)

        physical_path = resolver._get_physical_path(memory_uri)

        # Verify file exists and is readable
        assert physical_path.exists(), f"File not found: {physical_path}"

        # Read file content
        with open(physical_path) as f:
            line = f.readline()
            entry = json.loads(line)

        # Verify data (should be redacted)
        assert "events" in entry
        assert entry["session_id"] == "roundtrip_test"


class TestMemoryTextFlag:
    """Test the --text convenience flag."""

    def test_text_flag_creates_simple_note(self, tmp_path):
        """Test that --text creates a simple note entry."""
        config_file = tmp_path / "osiris.yaml"
        config_file.write_text(
            f"""
filesystem:
  base_path: "{tmp_path}"
  mcp_logs_dir: ".osiris/mcp/logs"
"""
        )

        result = subprocess.run(
            [
                sys.executable,
                str(_OSIRIS_PY),
                "mcp",
                "memory",
                "capture",
                "--session-id",
                "text_test",
                "--text",
                "Quick manual test note",
                "--consent",
                "--json",
            ],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )

        output = json.loads(result.stdout)
        assert output["captured"] is True

        # Read the file
        file_path = Path(output["file_path"])
        with open(file_path) as f:
            entry = json.loads(f.readline())

        # Verify structure
        assert "events" in entry
        assert len(entry["events"]) == 1
        assert entry["events"][0]["note"] == "Quick manual test note"
        assert entry["events"][0]["type"] == "manual_entry"

    def test_text_help_shows_flag(self):
        """Test that --help shows the --text flag."""
        result = subprocess.run(
            [sys.executable, str(_OSIRIS_PY), "mcp", "memory", "capture", "--help"],
            capture_output=True,
            text=True,
        )

        # Help should mention --text
        assert "--text" in result.stdout, "Help should show --text flag"
        assert "Simple text note" in result.stdout or "manual testing" in result.stdout
