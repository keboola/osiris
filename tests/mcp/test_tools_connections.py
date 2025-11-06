"""
Test MCP connections tools.
"""

from unittest.mock import patch

import pytest

from osiris.mcp.errors import OsirisError
from osiris.mcp.tools.connections import ConnectionsTools


class TestConnectionsTools:
    """Test connections.list and connections.doctor tools."""

    @pytest.fixture
    def connections_tools(self):
        """Create ConnectionsTools instance."""
        return ConnectionsTools()

    @pytest.mark.asyncio
    async def test_connections_list(self, connections_tools):
        """Test listing connections via CLI delegation."""
        # Mock CLI delegation response
        mock_result = {
            "connections": [
                {
                    "family": "mysql",
                    "alias": "default",
                    "reference": "@mysql.default",
                    "config": {
                        "host": "localhost",
                        "port": 3306,
                        "database": "test",
                        "username": "user",
                        "password": "${MYSQL_PASSWORD}",
                    },
                },
                {
                    "family": "supabase",
                    "alias": "prod",
                    "reference": "@supabase.prod",
                    "config": {"url": "${SUPABASE_URL}", "key": "${SUPABASE_KEY}"},
                },
            ],
            "count": 2,
            "status": "success",
            "_meta": {"correlation_id": "test-123", "duration_ms": 10},
        }

        with patch("osiris.mcp.cli_bridge.run_cli_json", return_value=mock_result):
            result = await connections_tools.list({})

            assert result["status"] == "success"
            assert "connections" in result
            assert result["count"] == 2

            # Check connection format
            connections = result["connections"]
            assert len(connections) == 2

            # Find MySQL connection
            mysql_conn = next(c for c in connections if c["family"] == "mysql")
            assert mysql_conn["alias"] == "default"
            assert mysql_conn["reference"] == "@mysql.default"
            assert "config" in mysql_conn

            # Password should be shown as env var, not redacted
            assert mysql_conn["config"]["password"] == "${MYSQL_PASSWORD}"

    @pytest.mark.asyncio
    async def test_connections_doctor_success(self, connections_tools):
        """Test successful connection diagnosis via CLI delegation."""
        mock_result = {
            "connection": "@mysql.default",
            "family": "mysql",
            "alias": "default",
            "health": "healthy",
            "diagnostics": [
                {"check": "config_exists", "status": "passed", "message": "Connection configuration found"},
                {"check": "resolution", "status": "passed", "message": "Connection resolved successfully"},
            ],
            "status": "success",
            "_meta": {"correlation_id": "test-456", "duration_ms": 15},
        }

        with patch("osiris.mcp.cli_bridge.run_cli_json", return_value=mock_result):
            result = await connections_tools.doctor({"connection": "@mysql.default"})

            assert result["status"] == "success"
            assert result["health"] == "healthy"
            assert result["family"] == "mysql"
            assert result["alias"] == "default"
            assert len(result["diagnostics"]) > 0

            # Check for passed diagnostics
            config_check = next(d for d in result["diagnostics"] if d["check"] == "config_exists")
            assert config_check["status"] == "passed"

    @pytest.mark.asyncio
    async def test_connections_doctor_missing_connection(self, connections_tools):
        """Test diagnosis of missing connection via CLI delegation."""
        mock_result = {
            "connection": "@mysql.nonexistent",
            "family": "mysql",
            "alias": "nonexistent",
            "health": "unhealthy",
            "diagnostics": [
                {
                    "check": "alias_exists",
                    "status": "failed",
                    "message": "Connection alias 'nonexistent' not found in family 'mysql'",
                    "severity": "error",
                }
            ],
            "status": "success",
            "_meta": {"correlation_id": "test-789", "duration_ms": 5},
        }

        with patch("osiris.mcp.cli_bridge.run_cli_json", return_value=mock_result):
            result = await connections_tools.doctor({"connection": "@mysql.nonexistent"})

            assert result["status"] == "success"
            assert result["health"] == "unhealthy"
            assert any(d["check"] == "alias_exists" and d["status"] == "failed" for d in result["diagnostics"])

    @pytest.mark.asyncio
    async def test_connections_doctor_no_connection_id(self, connections_tools):
        """Test doctor without connection raises error."""
        with pytest.raises(OsirisError) as exc_info:
            await connections_tools.doctor({})

        assert exc_info.value.family.value == "SCHEMA"
        assert "connection is required" in str(exc_info.value)

    # Note: _sanitize_config and _get_required_fields are now in CLI subcommands
    # (connections_cmds.py), not in the MCP tool. The MCP tool delegates to CLI.
