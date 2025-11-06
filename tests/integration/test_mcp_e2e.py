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

        # Verify result envelope structure: {status, result, _meta}
        assert result["status"] == "success"
        assert "result" in result
        # Extract connections from nested result
        result_data = result.get("result", result)
        assert "connections" in result_data

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
                    "connection": "@mysql.test",
                    "component": "@mysql/extractor",
                }
            )

            # Verify CLI was called
            assert mock_cli.called
            assert "mcp" in mock_cli.call_args[0][0]
            assert "discovery" in mock_cli.call_args[0][0]

            # Verify result envelope structure
            assert result["status"] == "success"
            assert "result" in result
            # Extract discovery_id from nested result
            result_data = result.get("result", result)
            assert result_data["discovery_id"].startswith("disc_")

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
            "connection is required",
            path=["connection"],
            suggest="Provide connection ID",
        )

        # Handlers catch OsirisError and return error envelope (don't raise)
        result = await mcp_server._handle_connections_doctor({})

        # Verify error envelope structure
        assert result["status"] == "error"
        # Error should have code and message
        error = result["error"]
        assert error["code"] in ["SCHEMA", "schema"]
        assert "connection" in error["message"]

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

        # Verify envelope includes _meta at top level
        assert "_meta" in result
        meta = result["_meta"]
        assert "correlation_id" in meta
        assert "duration_ms" in meta
        # CLI returns metrics, server may add more
        assert meta["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_aiop_list_delegates_to_cli(self, mock_cli, mcp_server):
        """Test that AIOP operations delegate to CLI."""
        # AIOP tool expects CLI to return {"data": [...]} and extracts it
        mock_cli.return_value = {
            "data": [
                {
                    "run_id": "run_test_001",
                    "pipeline": "test_pipeline",
                    "status": "success",
                }
            ],
            "status": "success",
            "_meta": {"correlation_id": "test-005", "duration_ms": 8.5},
        }

        result = await mcp_server._handle_aiop_list({})

        assert mock_cli.called
        assert mock_cli.call_args[0][0] == ["mcp", "aiop", "list"]
        # Verify result envelope
        assert result["status"] == "success"
        assert "result" in result
        # Extract runs from nested result
        result_data = result.get("result", result)
        assert "runs" in result_data
        assert len(result_data["runs"]) == 1

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
        # Verify result envelope
        assert result["status"] == "success"
        assert "result" in result
        # Extract fields from nested result
        result_data = result.get("result", result)
        assert result_data["captured"] is True
        assert result_data["pii_redacted"] is True


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
    with patch("osiris.mcp.cli_bridge.run_cli_json") as mock_cli, patch("osiris.mcp.server.init_telemetry"):
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
            # MCP server wraps CLI response in envelope: {status, result, _meta}
            assert result1["status"] == "success"
            assert "result" in result1
            # Extract count from nested result
            result1_data = result1.get("result", result1)
            assert result1_data["count"] == 1

            # Step 2: Discovery
            result2 = await server._handle_discovery_request(
                {
                    "connection": "@mysql.source",
                    "component": "@mysql/extractor",
                }
            )
            assert result2["status"] == "success"
            assert "result" in result2
            # Extract discovery_id from nested result
            result2_data = result2.get("result", result2)
            assert result2_data["discovery_id"].startswith("disc_")

            # Verify all CLI calls made
            assert mock_cli.call_count == 2
