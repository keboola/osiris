"""
Simplified MCP E2E integration tests - focus on CLI delegation pattern.

Tests the core requirement: All MCP operations delegate to CLI, no env vars in MCP process.
"""

import os
from unittest.mock import patch

import pytest

from osiris.mcp.errors import ErrorFamily, OsirisError
from osiris.mcp.server import OsirisMCPServer


class TestMCPE2ESimple:
    """Simplified E2E tests focusing on CLI delegation."""

    @pytest.fixture
    def mock_cli(self):
        """Mock CLI bridge at the source."""
        with patch("osiris.mcp.cli_bridge.run_cli_json") as mock:
            yield mock

    @pytest.fixture
    def mcp_server(self):
        """Create MCP server instance."""
        with patch("osiris.mcp.server.init_telemetry"):
            server = OsirisMCPServer(server_name="test-server", debug=True)
            return server

    @pytest.mark.asyncio
    async def test_connections_list_delegates_to_cli(self, mock_cli, mcp_server):
        """Test that connections_list delegates to CLI subprocess."""
        mock_cli.return_value = {
            "connections": [],
            "count": 0,
            "status": "success",
            "_meta": {"correlation_id": "test-001", "duration_ms": 10.0},
        }

        result = await mcp_server._handle_connections_list({})

        # Verify CLI was called
        assert mock_cli.called
        assert mock_cli.call_args[0][0] == ["mcp", "connections", "list"]

        # Verify result
        assert result["status"] == "success"
        assert "connections" in result

    @pytest.mark.asyncio
    async def test_discovery_delegates_to_cli(self, mock_cli, mcp_server):
        """Test that discovery delegates to CLI subprocess."""
        # Mock cache to avoid cache hits
        with patch.object(mcp_server.discovery_tools.cache, "get", return_value=None):
            mock_cli.return_value = {
                "discovery_id": "disc_test_123",
                "connection_id": "@mysql.test",
                "component_id": "@mysql/extractor",
                "artifacts": {},
                "summary": {"table_count": 5},
                "status": "success",
                "_meta": {"correlation_id": "test-002", "duration_ms": 500.0},
            }

            result = await mcp_server._handle_discovery_request(
                {
                    "connection_id": "@mysql.test",
                    "component_id": "@mysql/extractor",
                }
            )

            # Verify CLI was called
            assert mock_cli.called
            assert "mcp" in mock_cli.call_args[0][0]
            assert "discovery" in mock_cli.call_args[0][0]

            # Verify result
            assert result["status"] == "success"
            assert result["discovery_id"].startswith("disc_")

    @pytest.mark.asyncio
    async def test_no_env_vars_in_mcp_process(self, mock_cli, mcp_server):
        """Test that MCP process works with no environment variables."""
        with patch.dict(os.environ, {}, clear=True):
            mock_cli.return_value = {
                "connections": [],
                "count": 0,
                "status": "success",
                "_meta": {"correlation_id": "test-003", "duration_ms": 5.0},
            }

            # Should work even with empty environment
            result = await mcp_server._handle_connections_list({})

            assert result["status"] == "success"
            assert mock_cli.called

    @pytest.mark.asyncio
    async def test_cli_error_propagated(self, mock_cli, mcp_server):
        """Test that CLI errors are properly propagated."""
        mock_cli.side_effect = OsirisError(
            ErrorFamily.SCHEMA,
            "connection_id is required",
            path=["connection_id"],
            suggest="Provide connection ID",
        )

        with pytest.raises(OsirisError) as exc_info:
            await mcp_server._handle_connections_doctor({})

        assert exc_info.value.family == ErrorFamily.SCHEMA
        assert "connection_id" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_metrics_included_in_response(self, mock_cli, mcp_server):
        """Test that metrics are included in responses."""
        mock_cli.return_value = {
            "connections": [],
            "count": 0,
            "status": "success",
            "_meta": {
                "correlation_id": "test-004",
                "duration_ms": 12.5,
                "bytes_in": 100,
                "bytes_out": 200,
            },
        }

        result = await mcp_server._handle_connections_list({})

        assert "_meta" in result
        assert "correlation_id" in result["_meta"]
        assert "duration_ms" in result["_meta"]
        assert result["_meta"]["duration_ms"] > 0

    @pytest.mark.asyncio
    async def test_aiop_list_delegates_to_cli(self, mock_cli, mcp_server):
        """Test that AIOP operations delegate to CLI."""
        mock_cli.return_value = {
            "runs": [
                {
                    "run_id": "run_test_001",
                    "pipeline": "test_pipeline",
                    "status": "success",
                }
            ],
            "count": 1,
            "status": "success",
            "_meta": {"correlation_id": "test-005", "duration_ms": 8.5},
        }

        result = await mcp_server._handle_aiop_list({})

        assert mock_cli.called
        assert mock_cli.call_args[0][0] == ["mcp", "aiop", "list"]
        assert result["status"] == "success"
        assert len(result["runs"]) == 1

    @pytest.mark.asyncio
    async def test_memory_capture_delegates_to_cli(self, mock_cli, mcp_server):
        """Test that memory capture delegates to CLI."""
        mock_cli.return_value = {
            "captured": True,
            "session_id": "test_session",
            "memory_uri": "osiris://mcp/memory/sessions/test_session.jsonl",
            "pii_redacted": True,
            "status": "success",
            "_meta": {"correlation_id": "test-006", "duration_ms": 20.0},
        }

        result = await mcp_server._handle_memory_capture(
            {
                "consent": True,
                "session_id": "test_session",
                "intent": "Test capture",
                "actor_trace": [],
                "decisions": [],
                "artifacts": [],
            }
        )

        assert mock_cli.called
        assert result["captured"] is True
        assert result["pii_redacted"] is True


@pytest.mark.asyncio
async def test_full_workflow_sequence():
    """
    Test a realistic workflow sequence: connections → discovery → validation.

    This test verifies:
    1. Multiple operations in sequence
    2. Data flows correctly
    3. All CLI calls succeed
    4. No env vars needed in MCP process
    """
    with patch("osiris.mcp.cli_bridge.run_cli_json") as mock_cli, \
         patch("osiris.mcp.server.init_telemetry"):
        # Setup responses
        responses = [
            # Step 1: List connections
            # CLI response format (no envelope - MCP server will wrap)
            {
                "connections": [
                    {
                        "family": "mysql",
                        "alias": "source",
                        "reference": "@mysql.source",
                        "config": {"host": "localhost"},
                    }
                ],
                "count": 1,
                "_meta": {"correlation_id": "wf-001", "duration_ms": 10.0, "bytes_in": 0, "bytes_out": 100},
            },
            # Step 2: Discovery (CLI response format)
            {
                "discovery_id": "disc_wf_test",
                "connection_id": "@mysql.source",
                "component_id": "@mysql/extractor",
                "artifacts": {
                    "overview": "osiris://mcp/discovery/disc_wf_test/overview.json",
                },
                "summary": {"table_count": 3},
                "_meta": {"correlation_id": "wf-002", "duration_ms": 450.0, "bytes_in": 50, "bytes_out": 200},
            },
        ]

        mock_cli.side_effect = responses

        # Create server
        server = OsirisMCPServer(server_name="workflow-test", debug=True)

        # Clear environment to verify no env var access
        with patch.dict(os.environ, {}, clear=True):
            # Step 1: List connections
            result1 = await server._handle_connections_list({})
            # MCP server wraps CLI response in envelope
            assert result1["status"] == "success"
            assert result1["result"]["count"] == 1

            # Step 2: Discovery
            result2 = await server._handle_discovery_request(
                {
                    "connection_id": "@mysql.source",
                    "component_id": "@mysql/extractor",
                }
            )
            assert result2["status"] == "success"
            assert result2["result"]["discovery_id"].startswith("disc_")

            # Verify all CLI calls made
            assert mock_cli.call_count == 2
