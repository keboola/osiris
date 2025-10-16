"""
Test audit event logging for MCP server.
"""

import json
from datetime import UTC
from unittest.mock import patch

import pytest

from osiris.mcp.audit import AuditLogger


class TestAuditEvents:
    """Test audit event logging."""

    @pytest.fixture
    def audit_logger(self, tmp_path):
        """Create an audit logger instance."""
        return AuditLogger(log_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_audit_log_tool_call(self, audit_logger, tmp_path):
        """Test logging a tool call."""
        # Log a tool call
        correlation_id = await audit_logger.log_tool_call(tool_name="connections.list", arguments={"test": "value"})

        # Verify correlation ID was generated
        assert correlation_id is not None
        assert correlation_id.startswith("mcp_")

        # Verify log file was created
        log_files = list(tmp_path.glob("mcp_audit_*.jsonl"))
        assert len(log_files) == 1

        # Read and verify log entry
        with open(log_files[0]) as f:
            lines = f.readlines()
            assert len(lines) == 1

            entry = json.loads(lines[0])
            assert entry["event_type"] == "tool_call_started"
            assert entry["tool_name"] == "connections.list"
            assert entry["arguments"] == {"test": "value"}
            assert entry["correlation_id"] == correlation_id

    @pytest.mark.asyncio
    async def test_audit_log_tool_result(self, audit_logger, tmp_path):
        """Test logging a tool result."""
        # Log a tool call first
        correlation_id = await audit_logger.log_tool_call(tool_name="oml.validate", arguments={"oml_content": "test"})

        # Log the result
        await audit_logger.log_tool_result(correlation_id=correlation_id, result={"valid": True}, duration_ms=123.45)

        # Read and verify both entries
        log_files = list(tmp_path.glob("mcp_audit_*.jsonl"))
        with open(log_files[0]) as f:
            lines = f.readlines()
            assert len(lines) == 2

            # Verify result entry
            result_entry = json.loads(lines[1])
            assert result_entry["event_type"] == "tool_call_completed"
            assert result_entry["correlation_id"] == correlation_id
            assert result_entry["duration_ms"] == 123.45
            assert "result" in result_entry

    @pytest.mark.asyncio
    async def test_audit_log_tool_error(self, audit_logger, tmp_path):
        """Test logging a tool error."""
        correlation_id = await audit_logger.log_tool_call(
            tool_name="discovery.request", arguments={"connection_id": "test"}
        )

        # Log an error
        await audit_logger.log_tool_error(correlation_id=correlation_id, error="Connection not found", duration_ms=50.0)

        # Verify error entry
        log_files = list(tmp_path.glob("mcp_audit_*.jsonl"))
        with open(log_files[0]) as f:
            lines = f.readlines()
            result_entry = json.loads(lines[1])
            assert result_entry["event_type"] == "tool_call_failed"
            assert result_entry["error"] == "Connection not found"

    @pytest.mark.asyncio
    async def test_audit_session_tracking(self, audit_logger):
        """Test session ID is consistent across calls."""
        session_id = audit_logger.session_id

        # Multiple tool calls should have same session ID
        id1 = await audit_logger.log_tool_call("tool1", {})
        id2 = await audit_logger.log_tool_call("tool2", {})

        assert audit_logger.session_id == session_id
        assert id1 != id2  # Different correlation IDs

    def test_audit_daily_rotation(self):
        """Test audit logs rotate daily."""
        from datetime import datetime

        # Create logger with specific date
        with patch("osiris.mcp.audit.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2024, 1, 1, tzinfo=UTC)
            audit1 = AuditLogger()
            assert "20240101" in str(audit1.log_file)

            # Next day
            mock_datetime.now.return_value = datetime(2024, 1, 2, tzinfo=UTC)
            audit2 = AuditLogger()
            assert "20240102" in str(audit2.log_file)
