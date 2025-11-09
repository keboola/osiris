"""
Test MCP discovery tools.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from osiris.mcp.cache import DiscoveryCache
from osiris.mcp.errors import OsirisError
from osiris.mcp.tools.discovery import DiscoveryTools


class TestDiscoveryTools:
    """Test discovery.request tool."""

    @pytest.fixture
    def discovery_tools(self):
        """Create DiscoveryTools instance with mocked cache."""
        cache = MagicMock(spec=DiscoveryCache)
        return DiscoveryTools(cache)

    @pytest.mark.asyncio
    async def test_discovery_request_cache_hit(self, discovery_tools):
        """Test discovery with cache hit."""
        cached_data = {
            "discovery_id": "disc_abc123",
            "timestamp": datetime.now(UTC).isoformat(),
            "database": "test_db",
            "tables": ["users", "orders"],
            "summary": {"tables_count": 2, "total_rows": 1000},
        }

        discovery_tools.cache.get = AsyncMock(return_value=cached_data)

        result = await discovery_tools.request(
            {
                "connection": "@mysql.default",
                "component": "mysql.extractor",
                "samples": 5,
                "idempotency_key": "test_key",
            }
        )

        assert result["status"] == "success"
        assert result["cached"] is True
        assert result["discovery_id"] == "disc_abc123"
        assert "artifacts" in result

        # Verify cache was checked
        discovery_tools.cache.get.assert_called_once_with("@mysql.default", "mysql.extractor", 5, "test_key")

    @pytest.mark.asyncio
    async def test_discovery_request_cache_miss(self, discovery_tools):
        """Test discovery with cache miss via CLI delegation."""
        discovery_tools.cache.get = AsyncMock(return_value=None)
        discovery_tools.cache.set = AsyncMock(return_value="disc_new123")
        discovery_tools.cache.get_discovery_uri = MagicMock(
            side_effect=lambda disc_id, artifact: f"osiris://mcp/discovery/{disc_id}/{artifact}.json"
        )

        # Mock CLI delegation response
        mock_cli_result = {
            "discovery_id": "disc_cli123",
            "status": "success",
            "summary": {
                "connection": "@mysql.default",
                "database_type": "mysql",
                "total_tables": 5,
                "tables_discovered": ["users", "orders"],
            },
            "_meta": {"correlation_id": "test-789", "duration_ms": 500},
        }

        with patch("osiris.mcp.cli_bridge.run_cli_json", return_value=mock_cli_result):
            result = await discovery_tools.request(
                {"connection": "@mysql.default", "component": "mysql.extractor", "samples": 0}
            )

            assert result["status"] == "success"
            assert "discovery_id" in result
            assert "summary" in result

    @pytest.mark.asyncio
    async def test_discovery_request_missing_connection_id(self, discovery_tools):
        """Test discovery request without connection."""
        with pytest.raises(OsirisError) as exc_info:
            await discovery_tools.request({"component": "mysql.extractor"})

        assert exc_info.value.family.value == "SCHEMA"
        assert "connection is required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_discovery_request_missing_component_id(self, discovery_tools):
        """Test discovery request without component."""
        with pytest.raises(OsirisError) as exc_info:
            await discovery_tools.request({"connection": "@mysql.default"})

        assert exc_info.value.family.value == "SCHEMA"
        assert "component is required" in str(exc_info.value)

    # Note: _perform_discovery is now in CLI subcommands (discovery_cmds.py),
    # not in the MCP tool. The MCP tool delegates to CLI.

    def test_get_artifact_uris(self, discovery_tools):
        """Test getting artifact URIs for discovery results."""
        discovery_tools.cache.get_discovery_uri = MagicMock(
            side_effect=lambda disc_id, artifact: f"osiris://mcp/discovery/{disc_id}/{artifact}.json"
        )

        uris = discovery_tools._get_artifact_uris("disc_123")

        assert uris["overview"] == "osiris://mcp/discovery/disc_123/overview.json"
        assert uris["tables"] == "osiris://mcp/discovery/disc_123/tables.json"
        assert uris["samples"] == "osiris://mcp/discovery/disc_123/samples.json"

    @pytest.mark.asyncio
    async def test_discovery_request_filesystem_component(self, discovery_tools):
        """Test discovery with filesystem component and connection."""
        discovery_tools.cache.get = AsyncMock(return_value=None)
        discovery_tools.cache.set = AsyncMock(return_value="disc_fs123")
        discovery_tools.cache.get_discovery_uri = MagicMock(
            side_effect=lambda disc_id, artifact: f"osiris://mcp/discovery/{disc_id}/{artifact}.json"
        )

        # Mock CLI delegation response for filesystem discovery
        mock_cli_result = {
            "discovery_id": "disc_fs123",
            "status": "success",
            "summary": {
                "connection": "@filesystem.local",
                "component": "filesystem_csv_extractor",
                "total_files": 5,
                "files_discovered": ["file1.csv", "file2.csv", "file3.csv"],
                "base_dir": "/path/to/data",
            },
            "_meta": {"correlation_id": "test-fs-456", "duration_ms": 150},
        }

        with patch("osiris.mcp.cli_bridge.run_cli_json", return_value=mock_cli_result):
            result = await discovery_tools.request(
                {"connection": "@filesystem.local", "component": "filesystem_csv_extractor", "samples": 0}
            )

            assert result["status"] == "success"
            assert result["discovery_id"] == "disc_fs123"
            assert "summary" in result
            assert result["summary"]["total_files"] == 5
            assert "files_discovered" in result["summary"]
