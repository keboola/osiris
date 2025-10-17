"""Tests for telemetry path configuration and secret redaction."""

import json
import tempfile
from pathlib import Path

import pytest

from osiris.mcp.config import MCPFilesystemConfig
from osiris.mcp.telemetry import TelemetryEmitter, init_telemetry


def test_telemetry_requires_output_dir():
    """Test that TelemetryEmitter requires explicit output_dir (no Path.home() fallback)."""
    with pytest.raises(ValueError, match="output_dir is required"):
        TelemetryEmitter(enabled=True, output_dir=None)


def test_init_telemetry_requires_output_dir():
    """Test that init_telemetry requires explicit output_dir."""
    with pytest.raises(ValueError, match="output_dir is required"):
        init_telemetry(enabled=True, output_dir=None)


def test_telemetry_uses_config_path(tmp_path):
    """Test that telemetry writes to config-driven path."""
    # Create telemetry directory from config
    telemetry_dir = tmp_path / ".osiris" / "mcp" / "logs" / "telemetry"

    # Initialize telemetry with config path
    emitter = TelemetryEmitter(enabled=True, output_dir=telemetry_dir)

    # Verify directory was created
    assert telemetry_dir.exists()
    assert telemetry_dir.is_dir()

    # Emit a test event
    emitter.emit_tool_call(
        tool="test_tool",
        status="ok",
        duration_ms=100,
        bytes_in=50,
        bytes_out=200,
    )

    # Verify event was written to correct path
    telemetry_file = emitter.telemetry_file
    assert telemetry_file.exists()
    assert telemetry_file.parent == telemetry_dir

    # Verify event content
    with open(telemetry_file) as f:
        event = json.loads(f.read().strip())
        assert event["event"] == "tool_call"
        assert event["tool"] == "test_tool"
        assert event["status"] == "ok"


def test_telemetry_payload_truncation(tmp_path):
    """Test that large payloads are truncated to 2-4 KB."""
    telemetry_dir = tmp_path / "telemetry"
    emitter = TelemetryEmitter(enabled=True, output_dir=telemetry_dir)

    # Create large payload (10 KB)
    large_payload = {"data": "x" * 10000}

    # Truncate it
    truncated = emitter._truncate_payload(large_payload)

    # Verify truncation
    assert "[TRUNCATED:" in truncated
    assert len(truncated.encode("utf-8")) <= 4096  # MAX_PAYLOAD_PREVIEW_BYTES


def test_telemetry_payload_small_not_truncated(tmp_path):
    """Test that small payloads are not truncated."""
    telemetry_dir = tmp_path / "telemetry"
    emitter = TelemetryEmitter(enabled=True, output_dir=telemetry_dir)

    # Create small payload (100 bytes)
    small_payload = {"data": "small"}

    # Truncate it
    result = emitter._truncate_payload(small_payload)

    # Verify no truncation
    assert "[TRUNCATED:" not in result
    assert json.loads(result) == small_payload


def test_telemetry_secret_redaction(tmp_path):
    """Test that telemetry redacts secrets using spec-aware helper."""
    telemetry_dir = tmp_path / "telemetry"
    emitter = TelemetryEmitter(enabled=True, output_dir=telemetry_dir)

    # Create data with secrets
    sensitive_data = {
        "username": "admin",
        "password": "secret123",  # pragma: allowlist secret
        "api_key": "key_abc123",  # pragma: allowlist secret
        "host": "localhost",
    }

    # Redact secrets
    redacted = emitter._redact_secrets(sensitive_data)

    # Verify redaction
    assert redacted["username"] == "admin"  # Not a secret
    assert redacted["password"] == "***MASKED***"  # Should be masked
    assert redacted["api_key"] == "***MASKED***"  # Should be masked
    assert redacted["host"] == "localhost"  # Not a secret


def test_telemetry_with_filesystem_config(tmp_path):
    """Test telemetry integration with MCPFilesystemConfig."""
    # Create osiris.yaml
    config_file = tmp_path / "osiris.yaml"
    config_file.write_text(f"""
filesystem:
  base_path: "{tmp_path}"
  mcp_logs_dir: ".osiris/mcp/logs"
""")

    # Load config
    fs_config = MCPFilesystemConfig.from_config(str(config_file))

    # Verify telemetry dir is derived from config
    telemetry_dir = fs_config.mcp_logs_dir / "telemetry"
    assert telemetry_dir == tmp_path / ".osiris" / "mcp" / "logs" / "telemetry"

    # Initialize telemetry
    emitter = TelemetryEmitter(enabled=True, output_dir=telemetry_dir)

    # Emit event
    emitter.emit_server_start(version="0.5.0", protocol_version="0.5")

    # Verify event written to config path
    assert emitter.telemetry_file.exists()
    assert str(emitter.telemetry_file).startswith(str(tmp_path))


def test_telemetry_disabled(tmp_path):
    """Test that telemetry can be disabled."""
    telemetry_dir = tmp_path / "telemetry"

    # Initialize with enabled=False
    emitter = TelemetryEmitter(enabled=False, output_dir=telemetry_dir)

    # Emit event (should be no-op)
    emitter.emit_tool_call(
        tool="test_tool",
        status="ok",
        duration_ms=100,
        bytes_in=50,
        bytes_out=200,
    )

    # Verify no file created (disabled)
    assert not telemetry_dir.exists()


def test_telemetry_server_lifecycle(tmp_path):
    """Test server start/stop events."""
    telemetry_dir = tmp_path / "telemetry"
    emitter = TelemetryEmitter(enabled=True, output_dir=telemetry_dir)

    # Emit start
    emitter.emit_server_start(version="0.5.0", protocol_version="0.5")

    # Emit some tool calls
    for i in range(3):
        emitter.emit_tool_call(
            tool=f"tool_{i}",
            status="ok",
            duration_ms=100 + i * 10,
            bytes_in=50 + i * 5,
            bytes_out=200 + i * 20,
        )

    # Emit stop
    emitter.emit_server_stop(reason="shutdown")

    # Verify events
    with open(emitter.telemetry_file) as f:
        events = [json.loads(line) for line in f]

    assert len(events) == 5  # start + 3 tool calls + stop
    assert events[0]["event"] == "server_start"
    assert events[-1]["event"] == "server_stop"
    assert events[-1]["metrics"]["tool_calls"] == 3
