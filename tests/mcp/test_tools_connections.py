"""
Test MCP connections tools.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from osiris.mcp.tools.connections import ConnectionsTools
from osiris.mcp.errors import OsirisError


class TestConnectionsTools:
    """Test connections.list and connections.doctor tools."""

    @pytest.fixture
    def connections_tools(self):
        """Create ConnectionsTools instance."""
        return ConnectionsTools()

    @pytest.mark.asyncio
    async def test_connections_list(self, connections_tools):
        """Test listing connections."""
        # Mock load_connections_yaml
        mock_connections = {
            "mysql": {
                "default": {
                    "host": "localhost",
                    "port": 3306,
                    "database": "test",
                    "username": "user",
                    "password": "${MYSQL_PASSWORD}"
                }
            },
            "supabase": {
                "prod": {
                    "url": "${SUPABASE_URL}",
                    "key": "${SUPABASE_KEY}"
                }
            }
        }

        with patch('osiris.mcp.tools.connections.load_connections_yaml',
                  return_value=mock_connections):
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
        """Test successful connection diagnosis."""
        mock_connections = {
            "mysql": {
                "default": {
                    "host": "localhost",
                    "database": "test",
                    "username": "user",
                    "password": "secret"  # pragma: allowlist secret
                }
            }
        }

        with patch('osiris.mcp.tools.connections.load_connections_yaml',
                  return_value=mock_connections):
            with patch('osiris.mcp.tools.connections.parse_connection_ref',
                      return_value=("mysql", "default")):
                with patch('osiris.mcp.tools.connections.resolve_connection',
                          return_value={
                              "host": "localhost",
                              "database": "test",
                              "username": "user",
                              "password": "secret"  # pragma: allowlist secret
                          }):
                    result = await connections_tools.doctor({
                        "connection_id": "@mysql.default"
                    })

                    assert result["status"] == "success"
                    assert result["health"] == "healthy"
                    assert result["family"] == "mysql"
                    assert result["alias"] == "default"
                    assert len(result["diagnostics"]) > 0

                    # Check for passed diagnostics
                    config_check = next(
                        d for d in result["diagnostics"]
                        if d["check"] == "config_exists"
                    )
                    assert config_check["status"] == "passed"

    @pytest.mark.asyncio
    async def test_connections_doctor_missing_connection(self, connections_tools):
        """Test diagnosis of missing connection."""
        mock_connections = {"mysql": {}}

        with patch('osiris.mcp.tools.connections.load_connections_yaml',
                  return_value=mock_connections):
            with patch('osiris.mcp.tools.connections.parse_connection_ref',
                      return_value=("mysql", "nonexistent")):
                result = await connections_tools.doctor({
                    "connection_id": "@mysql.nonexistent"
                })

                assert result["status"] == "success"
                assert result["health"] == "unhealthy"
                assert any(
                    d["check"] == "alias_exists" and d["status"] == "failed"
                    for d in result["diagnostics"]
                )

    @pytest.mark.asyncio
    async def test_connections_doctor_no_connection_id(self, connections_tools):
        """Test doctor without connection_id raises error."""
        with pytest.raises(OsirisError) as exc_info:
            await connections_tools.doctor({})

        assert exc_info.value.family.value == "SCHEMA"
        assert "connection_id is required" in str(exc_info.value)

    def test_sanitize_config(self, connections_tools):
        """Test configuration sanitization."""
        config = {
            "host": "localhost",
            "username": "user",
            "password": "secret123",  # pragma: allowlist secret
            "api_key": "key123",  # pragma: allowlist secret
            "database": "test",
            "nested": {
                "secret": "nested_secret",  # pragma: allowlist secret
                "public": "value"
            }
        }

        sanitized = connections_tools._sanitize_config(config)

        assert sanitized["host"] == "localhost"
        assert sanitized["username"] == "user"
        assert sanitized["password"] == "***"
        assert sanitized["api_key"] == "***"
        assert sanitized["database"] == "test"
        assert sanitized["nested"]["secret"] == "***"
        assert sanitized["nested"]["public"] == "value"

    def test_get_required_fields(self, connections_tools):
        """Test getting required fields for connection families."""
        assert connections_tools._get_required_fields("mysql") == [
            "host", "database", "username", "password"
        ]
        assert connections_tools._get_required_fields("supabase") == [
            "url", "key"
        ]
        assert connections_tools._get_required_fields("unknown") == []