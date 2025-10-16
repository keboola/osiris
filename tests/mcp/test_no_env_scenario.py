"""
Test MCP server operation without environment variables.

This test verifies that the MCP server can operate via CLI delegation
without requiring any environment variables or secrets in the MCP process.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from osiris.mcp.tools.connections import ConnectionsTools
from osiris.mcp.tools.discovery import DiscoveryTools


class TestNoEnvScenario:
    """Test MCP tools work without environment variables."""

    @pytest.mark.asyncio
    async def test_connections_list_no_env(self):
        """Test connections list works without env vars via CLI delegation."""
        # Clear all Osiris-related environment variables
        env_backup = os.environ.copy()
        try:
            # Remove all potential environment variables
            for key in list(os.environ.keys()):
                if key.startswith("OSIRIS_") or key.startswith("MYSQL_") or key.startswith("SUPABASE_"):
                    del os.environ[key]

            # Mock the CLI delegation
            mock_result = {
                "connections": [
                    {
                        "family": "mysql",
                        "alias": "default",
                        "reference": "@mysql.default",
                        "config": {"host": "localhost", "database": "test"},
                    }
                ],
                "count": 1,
                "status": "success",
                "_meta": {"correlation_id": "test-123", "duration_ms": 10},
            }

            with patch("osiris.mcp.tools.connections.run_cli_json", return_value=mock_result) as mock_cli:
                tools = ConnectionsTools()
                result = await tools.list({})

                # Verify CLI was called (not direct config access)
                mock_cli.assert_called_once()
                assert mock_cli.call_args[0][0] == ["mcp", "connections", "list"]

                # Verify result
                assert result["status"] == "success"
                assert result["count"] == 1

        finally:
            # Restore environment
            os.environ.clear()
            os.environ.update(env_backup)

    @pytest.mark.asyncio
    async def test_connections_doctor_no_env(self):
        """Test connections doctor works without env vars via CLI delegation."""
        env_backup = os.environ.copy()
        try:
            # Clear environment
            for key in list(os.environ.keys()):
                if key.startswith("OSIRIS_") or key.startswith("MYSQL_") or key.startswith("SUPABASE_"):
                    del os.environ[key]

            # Mock CLI result
            mock_result = {
                "connection_id": "@mysql.default",
                "family": "mysql",
                "alias": "default",
                "health": "healthy",
                "diagnostics": [{"check": "config_exists", "status": "passed", "message": "Found"}],
                "status": "success",
                "_meta": {"correlation_id": "test-456", "duration_ms": 15},
            }

            with patch("osiris.mcp.tools.connections.run_cli_json", return_value=mock_result) as mock_cli:
                tools = ConnectionsTools()
                result = await tools.doctor({"connection_id": "@mysql.default"})

                # Verify CLI was called
                mock_cli.assert_called_once()
                call_args = mock_cli.call_args[0][0]
                assert call_args[0:3] == ["mcp", "connections", "doctor"]
                assert "@mysql.default" in call_args

                # Verify result
                assert result["status"] == "success"
                assert result["health"] == "healthy"

        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    @pytest.mark.asyncio
    async def test_discovery_request_no_env(self):
        """Test discovery works without env vars via CLI delegation."""
        env_backup = os.environ.copy()
        try:
            # Clear environment
            for key in list(os.environ.keys()):
                if key.startswith("OSIRIS_") or key.startswith("MYSQL_") or key.startswith("SUPABASE_"):
                    del os.environ[key]

            # Mock CLI result
            mock_result = {
                "discovery_id": "disc_12345",
                "status": "success",
                "summary": {"connection_id": "@mysql.default", "database_type": "mysql", "total_tables": 5},
                "_meta": {"correlation_id": "test-789", "duration_ms": 500},
            }

            with patch("osiris.mcp.tools.discovery.run_cli_json", return_value=mock_result) as mock_cli:
                tools = DiscoveryTools()
                result = await tools.request(
                    {"connection_id": "@mysql.default", "component_id": "mysql.extractor", "samples": 10}
                )

                # Verify CLI was called
                mock_cli.assert_called_once()
                call_args = mock_cli.call_args[0][0]
                assert call_args[0:3] == ["mcp", "discovery", "run"]
                assert "--connection-id" in call_args
                assert "--component-id" in call_args
                assert "--samples" in call_args

                # Verify result
                assert result["status"] == "success"
                assert result["discovery_id"] == "disc_12345"

        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_no_direct_import_of_resolve_connection(self):
        """Verify that MCP tools don't import resolve_connection."""
        # This test verifies at runtime that the refactored tools don't use forbidden imports
        tools_module_path = Path(__file__).parent.parent.parent / "osiris" / "mcp" / "tools"

        # Check connections.py
        connections_file = tools_module_path / "connections.py"
        with open(connections_file) as f:
            content = f.read()

        # Should NOT contain direct imports of resolve_connection
        assert "from osiris.core.config import resolve_connection" not in content
        assert "from osiris.core.config import load_connections_yaml" not in content

        # SHOULD contain CLI bridge import
        assert "from osiris.mcp.cli_bridge import run_cli_json" in content

        # Check discovery.py
        discovery_file = tools_module_path / "discovery.py"
        with open(discovery_file) as f:
            content = f.read()

        # Should NOT contain direct imports of resolve_connection
        assert "from osiris.core.config import resolve_connection" not in content
        assert "from osiris.core.config import parse_connection_ref" not in content

        # SHOULD contain CLI bridge import
        assert "from osiris.mcp.cli_bridge import run_cli_json" in content

    def test_mcp_config_loads_from_yaml_not_env(self, tmp_path):
        """Test that MCPFilesystemConfig prefers osiris.yaml over environment."""
        from osiris.mcp.config import MCPFilesystemConfig

        # Create a test config file
        config_file = tmp_path / "osiris.yaml"
        config_file.write_text(
            """
version: '2.0'
filesystem:
  base_path: "/test/base/path"
  mcp_logs_dir: ".osiris/mcp/logs"
"""
        )

        # Set environment variable (should be ignored in favor of config)
        env_backup = os.environ.copy()
        try:
            os.environ["OSIRIS_HOME"] = "/wrong/path"

            # Load config
            fs_config = MCPFilesystemConfig.from_config(str(config_file))

            # Should use config file, not environment
            assert str(fs_config.base_path) == "/test/base/path"
            assert fs_config.mcp_logs_dir == Path("/test/base/path") / ".osiris/mcp/logs"

        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_mcp_config_warns_on_env_fallback(self, caplog, tmp_path):
        """Test that MCPFilesystemConfig warns when falling back to environment."""
        from osiris.mcp.config import MCPFilesystemConfig

        # No config file exists
        nonexistent_config = tmp_path / "nonexistent.yaml"

        env_backup = os.environ.copy()
        try:
            os.environ["OSIRIS_HOME"] = str(tmp_path)

            # Load config (will fall back to env)
            fs_config = MCPFilesystemConfig.from_config(str(nonexistent_config))

            # Should have used environment and logged warning
            assert str(fs_config.base_path) == str(tmp_path)
            # Check for warning in logs (caplog captures logging)
            assert any("environment" in record.message.lower() for record in caplog.records)

        finally:
            os.environ.clear()
            os.environ.update(env_backup)


class TestCLIDelegationIntegrity:
    """Test that CLI delegation maintains data integrity."""

    @pytest.mark.asyncio
    async def test_cli_delegation_preserves_metadata(self):
        """Test that CLI delegation preserves _meta fields."""
        mock_result = {
            "connections": [],
            "count": 0,
            "status": "success",
            "_meta": {
                "correlation_id": "test-correlation",
                "duration_ms": 42.5,
                "bytes_in": 100,
                "bytes_out": 200,
                "cli_command": "mcp connections list",
            },
        }

        with patch("osiris.mcp.tools.connections.run_cli_json", return_value=mock_result):
            tools = ConnectionsTools()
            result = await tools.list({})

            # Verify metadata is preserved
            assert "_meta" in result
            # Note: run_cli_json may add its own metadata, so just verify it exists
            assert "correlation_id" in result["_meta"]
            assert "duration_ms" in result["_meta"]

    @pytest.mark.asyncio
    async def test_cli_delegation_handles_errors_correctly(self):
        """Test that CLI errors are properly propagated."""
        from osiris.mcp.errors import ErrorFamily, OsirisError

        # Simulate CLI error
        error = OsirisError(
            ErrorFamily.SEMANTIC,  # CLI errors map to SEMANTIC by default
            "connection_id is required",
            path=["connection_id"],
            suggest="Provide a valid connection ID",
        )

        with patch("osiris.mcp.tools.connections.run_cli_json", side_effect=error):
            tools = ConnectionsTools()

            with pytest.raises(OsirisError) as exc_info:
                await tools.doctor({"connection_id": "@invalid"})

            # Error should be propagated as-is
            assert exc_info.value.family == ErrorFamily.SEMANTIC
            assert "connection_id is required" in str(exc_info.value)
