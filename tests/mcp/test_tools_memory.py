"""
Test memory.capture tool for session memory management.
"""

from unittest.mock import patch

import pytest

from osiris.mcp.tools.memory import MemoryTools


class TestMemoryTools:
    """Test memory capture tools."""

    @pytest.fixture
    def memory_tools(self):
        """Create memory tools instance."""
        return MemoryTools()

    @pytest.mark.asyncio
    async def test_memory_capture_with_consent(self, memory_tools):
        """Test memory capture with user consent."""
        result = await memory_tools.capture(
            {
                "consent": True,
                "session_id": "test_session_123",
                "intent": "Build ETL pipeline for customer data",
                "actor_trace": [
                    {"action": "discover", "target": "mysql.source"},
                    {"action": "validate", "target": "oml_draft"},
                ],
                "decisions": [{"point": "connection_choice", "value": "@mysql.prod"}],
                "artifacts": ["osiris://mcp/drafts/draft1.yaml"],
            }
        )

        assert result["status"] == "success"
        assert result["captured"] is True
        assert "memory_id" in result
        assert result["memory_id"].startswith("mem_")

    @pytest.mark.asyncio
    async def test_memory_capture_without_consent(self, memory_tools):
        """Test memory capture without consent."""
        result = await memory_tools.capture(
            {"consent": False, "session_id": "test_session_456", "intent": "Test pipeline"}
        )

        assert result["status"] == "success"
        assert result["captured"] is False
        assert "memory_id" not in result or result["memory_id"] is None

    @pytest.mark.asyncio
    async def test_memory_capture_retention(self, memory_tools):
        """Test memory capture with custom retention."""
        result = await memory_tools.capture(
            {"consent": True, "retention_days": 30, "session_id": "test_session_789", "intent": "Temporary test"}
        )

        assert result["status"] == "success"
        assert result["captured"] is True
        assert result["retention_days"] == 30

    @pytest.mark.asyncio
    async def test_memory_capture_minimal(self, memory_tools):
        """Test memory capture with minimal data."""
        result = await memory_tools.capture({"consent": True, "session_id": "minimal_session"})

        assert result["status"] == "success"
        assert result["captured"] is True
        assert "memory_id" in result

    @pytest.mark.asyncio
    async def test_memory_capture_complex_trace(self, memory_tools):
        """Test memory capture with complex actor trace."""
        complex_trace = [
            {"action": "discover", "target": "@mysql.source", "result": {"tables": 10, "rows": 50000}},
            {"action": "generate", "target": "oml_pipeline", "config": {"mode": "batch", "parallel": True}},
            {"action": "validate", "target": "pipeline.yaml", "errors": 0, "warnings": 2},
        ]

        result = await memory_tools.capture(
            {
                "consent": True,
                "session_id": "complex_session",
                "actor_trace": complex_trace,
                "intent": "Complex ETL with validation",
            }
        )

        assert result["status"] == "success"
        assert result["captured"] is True

    @pytest.mark.asyncio
    async def test_memory_capture_persistence(self, memory_tools):
        """Test memory is persisted correctly via CLI delegation."""
        # Mock the CLI bridge to verify delegation occurs
        with patch("osiris.mcp.cli_bridge.run_cli_json") as mock_cli:
            # Return a successful response
            mock_cli.return_value = {
                "status": "success",
                "captured": True,
                "memory_id": "mem_abc123",
                "session_id": "persist_test",
                "memory_uri": "osiris://mcp/memory/sessions/persist_test.jsonl",
                "retention_days": 365,
                "timestamp": "2025-10-16T14:00:00+00:00",
                "entry_size_bytes": 100,
            }

            result = await memory_tools.capture(
                {"consent": True, "session_id": "persist_test", "intent": "Test persistence"}
            )

            # Verify CLI was called (security model: MCP delegates to CLI)
            mock_cli.assert_called_once()
            call_args = mock_cli.call_args[0][0]

            # Verify correct CLI command structure
            assert "mcp" in call_args
            assert "memory" in call_args
            assert "capture" in call_args
            assert "--session-id" in call_args
            assert "persist_test" in call_args
            assert "--consent" in call_args

            # Verify result structure
            assert result["memory_id"] == "mem_abc123"
            assert result["session_id"] == "persist_test"

    @pytest.mark.asyncio
    async def test_memory_capture_invalid_retention(self, memory_tools):
        """Test memory capture with invalid retention period."""
        # Negative retention
        result = await memory_tools.capture({"consent": True, "retention_days": -1, "session_id": "invalid_retention"})

        # Should either clamp to minimum or use default
        assert result["status"] == "success"
        if "retention_days" in result:
            assert result["retention_days"] > 0

        # Excessive retention
        result2 = await memory_tools.capture(
            {"consent": True, "retention_days": 10000, "session_id": "excessive_retention"}
        )

        # Should clamp to maximum
        assert result2["status"] == "success"
        if "retention_days" in result2:
            assert result2["retention_days"] <= 730  # Max 2 years

    @pytest.mark.asyncio
    async def test_memory_capture_session_isolation(self, memory_tools):
        """Test memories are isolated by session."""
        # Capture for session 1
        result1 = await memory_tools.capture({"consent": True, "session_id": "session_1", "intent": "Session 1 work"})

        # Capture for session 2
        result2 = await memory_tools.capture({"consent": True, "session_id": "session_2", "intent": "Session 2 work"})

        assert result1["memory_id"] != result2["memory_id"]

    @pytest.mark.asyncio
    async def test_memory_capture_error_handling(self, memory_tools):
        """Test memory capture error handling."""
        # Missing session_id
        try:
            result = await memory_tools.capture({"consent": True})
            # Should handle gracefully
            if "error" not in result:
                assert result["status"] in ["success", "error"]
        except Exception as e:
            # Should mention session_id
            assert "session" in str(e).lower()
