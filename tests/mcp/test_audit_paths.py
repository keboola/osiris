"""Tests for audit logging path configuration and secret redaction."""

import json
import tempfile
from pathlib import Path

import pytest

from osiris.mcp.audit import AuditLogger
from osiris.mcp.config import MCPFilesystemConfig


def test_audit_requires_log_dir():
    """Test that AuditLogger requires explicit log_dir (no Path.home() fallback)."""
    with pytest.raises(ValueError, match="log_dir is required"):
        AuditLogger(log_dir=None)


@pytest.mark.asyncio
async def test_audit_uses_config_path(tmp_path):
    """Test that audit logs write to config-driven path."""
    # Create audit directory from config
    audit_dir = tmp_path / ".osiris" / "mcp" / "logs" / "audit"

    # Initialize audit logger with config path
    logger = AuditLogger(log_dir=audit_dir)

    # Verify directory was created
    assert audit_dir.exists()
    assert audit_dir.is_dir()

    # Write an event to create the file
    await logger.log_tool_call(tool="test", params_bytes=10)

    # Verify log file path
    assert logger.log_file.exists()
    assert logger.log_file.parent == audit_dir


@pytest.mark.asyncio
async def test_audit_tool_call(tmp_path):
    """Test audit logging for tool calls."""
    audit_dir = tmp_path / "audit"
    logger = AuditLogger(log_dir=audit_dir)

    # Log tool call
    correlation_id = await logger.log_tool_call(
        tool="test_tool",
        params_bytes=100,
    )

    # Verify event written
    with open(logger.log_file) as f:
        event = json.loads(f.read().strip())

    assert event["event"] == "tool_call"
    assert event["tool"] == "test_tool"
    assert event["correlation_id"] == correlation_id
    assert event["bytes_in"] == 100


@pytest.mark.asyncio
async def test_audit_tool_result(tmp_path):
    """Test audit logging for tool results."""
    audit_dir = tmp_path / "audit"
    logger = AuditLogger(log_dir=audit_dir)

    # Log tool result
    await logger.log_tool_result(
        tool="test_tool",
        duration_ms=150,
        result_bytes=500,
        correlation_id="test_123",
    )

    # Verify event written
    with open(logger.log_file) as f:
        event = json.loads(f.read().strip())

    assert event["event"] == "tool_result"
    assert event["tool"] == "test_tool"
    assert event["duration_ms"] == 150
    assert event["bytes_out"] == 500
    assert event["correlation_id"] == "test_123"


@pytest.mark.asyncio
async def test_audit_tool_error(tmp_path):
    """Test audit logging for tool errors."""
    audit_dir = tmp_path / "audit"
    logger = AuditLogger(log_dir=audit_dir)

    # Log tool error
    await logger.log_tool_error(
        tool="test_tool",
        duration_ms=50,
        error_code="VALIDATION_ERROR",
        correlation_id="test_456",
    )

    # Verify event written
    with open(logger.log_file) as f:
        event = json.loads(f.read().strip())

    assert event["event"] == "tool_error"
    assert event["tool"] == "test_tool"
    assert event["error_code"] == "VALIDATION_ERROR"
    assert event["correlation_id"] == "test_456"


@pytest.mark.asyncio
async def test_audit_resource_access(tmp_path):
    """Test audit logging for resource access."""
    audit_dir = tmp_path / "audit"
    logger = AuditLogger(log_dir=audit_dir)

    # Log resource access
    await logger.log_resource_access(
        resource_uri="osiris://mcp/discovery/disc_123/overview.json",
        operation="read",
        success=True,
    )

    # Verify event written
    with open(logger.log_file) as f:
        event = json.loads(f.read().strip())

    assert event["event"] == "resource_access"
    assert event["resource_uri"] == "osiris://mcp/discovery/disc_123/overview.json"
    assert event["operation"] == "read"
    assert event["status"] == "ok"


@pytest.mark.asyncio
async def test_audit_secret_redaction(tmp_path):
    """Test that audit logs redact secrets using spec-aware helper."""
    audit_dir = tmp_path / "audit"
    logger = AuditLogger(log_dir=audit_dir)

    # Create arguments with secrets
    sensitive_args = {
        "connection_id": "@mysql.main",
        "username": "admin",
        "password": "secret123",  # pragma: allowlist secret
        "api_key": "key_abc123",  # pragma: allowlist secret
        "host": "localhost",
    }

    # Sanitize arguments
    sanitized = logger._sanitize_arguments(sensitive_args)

    # Verify redaction
    assert sanitized["connection_id"] == "@mysql.main"  # Not a secret
    assert sanitized["username"] == "admin"  # Not a secret
    assert sanitized["password"] == "***MASKED***"  # Should be masked
    assert sanitized["api_key"] == "***MASKED***"  # Should be masked
    assert sanitized["host"] == "localhost"  # Not a secret


@pytest.mark.asyncio
async def test_audit_with_filesystem_config(tmp_path):
    """Test audit logging integration with MCPFilesystemConfig."""
    # Create osiris.yaml
    config_file = tmp_path / "osiris.yaml"
    config_file.write_text(f"""
filesystem:
  base_path: "{tmp_path}"
  mcp_logs_dir: ".osiris/mcp/logs"
""")

    # Load config
    fs_config = MCPFilesystemConfig.from_config(str(config_file))

    # Verify audit dir is derived from config
    audit_dir = fs_config.mcp_logs_dir / "audit"
    assert audit_dir == tmp_path / ".osiris" / "mcp" / "logs" / "audit"

    # Initialize audit logger
    logger = AuditLogger(log_dir=audit_dir)

    # Log event
    await logger.log_tool_call(tool="test_tool", params_bytes=100)

    # Verify event written to config path
    assert logger.log_file.exists()
    assert str(logger.log_file).startswith(str(tmp_path))


@pytest.mark.asyncio
async def test_audit_session_summary(tmp_path):
    """Test audit session summary."""
    audit_dir = tmp_path / "audit"
    logger = AuditLogger(log_dir=audit_dir)

    # Log some tool calls
    for i in range(5):
        await logger.log_tool_call(tool=f"tool_{i}", params_bytes=100 + i * 10)

    # Get session summary
    summary = logger.get_session_summary()

    assert summary["tool_calls"] == 5
    assert summary["session_id"].startswith("mcp_")
    assert str(audit_dir) in summary["audit_file"]


@pytest.mark.asyncio
async def test_audit_correlation_id_generation(tmp_path):
    """Test correlation ID generation."""
    audit_dir = tmp_path / "audit"
    logger = AuditLogger(log_dir=audit_dir)

    # Log multiple tool calls
    correlation_ids = []
    for i in range(3):
        corr_id = await logger.log_tool_call(tool=f"tool_{i}", params_bytes=100)
        correlation_ids.append(corr_id)

    # Verify unique correlation IDs
    assert len(set(correlation_ids)) == 3

    # Verify correlation IDs follow pattern
    for corr_id in correlation_ids:
        assert corr_id.startswith("mcp_")


@pytest.mark.asyncio
async def test_audit_legacy_api_compatibility(tmp_path):
    """Test backward compatibility with old test API."""
    audit_dir = tmp_path / "audit"
    logger = AuditLogger(log_dir=audit_dir)

    # Use old test API (tool_name, arguments)
    correlation_id = await logger.log_tool_call(
        tool_name="legacy_tool",
        arguments={"param": "value"},
    )

    # Verify event written with both new and old fields
    with open(logger.log_file) as f:
        event = json.loads(f.read().strip())

    assert event["tool"] == "legacy_tool"
    assert event["tool_name"] == "legacy_tool"  # Test expects this
    assert event["arguments"] == {"param": "value"}  # Test expects this
    assert event["correlation_id"] == correlation_id
