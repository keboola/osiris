# Copyright (c) 2025 Osiris Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Integration tests for discovery cache invalidation (M0.2)."""

import json
import tempfile
from pathlib import Path

import pytest

from osiris.core.discovery import ProgressiveDiscovery
from osiris.core.interfaces import TableInfo


class MockExtractor:
    """Mock extractor for testing."""

    def __init__(self):
        self.get_table_info_calls = 0
        self.list_tables_calls = 0

    async def get_table_info(self, table_name: str) -> TableInfo:
        """Mock get_table_info that counts calls."""
        self.get_table_info_calls += 1
        return TableInfo(
            name=table_name,
            columns=["id", "name", "email"],
            column_types={"id": "int", "name": "varchar", "email": "varchar"},
            primary_keys=["id"],
            row_count=100,
            sample_data=[
                {"id": 1, "name": "Alice", "email": "alice@example.com"},
                {"id": 2, "name": "Bob", "email": "bob@example.com"},
            ],
        )

    async def list_tables(self):
        """Mock list_tables that counts calls."""
        self.list_tables_calls += 1
        return ["users", "orders", "products"]

    async def disconnect(self):
        """Mock disconnect."""
        pass

    async def connect(self):
        """Mock connect."""
        pass

    async def sample_table(self, table_name: str, size: int):
        """Mock sample_table."""
        pass

    async def execute_query(self, query: str):
        """Mock execute_query."""
        pass


@pytest.fixture
def temp_cache_dir():
    """Create a temporary cache directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_extractor():
    """Create a mock extractor."""
    return MockExtractor()


@pytest.fixture
def discovery(mock_extractor, temp_cache_dir):
    """Create a ProgressiveDiscovery instance with mocked dependencies."""
    discovery = ProgressiveDiscovery(
        extractor=mock_extractor,
        cache_dir=temp_cache_dir,
        component_type="mysql.table",
        component_version="0.1.0",
        connection_ref="@mysql",
    )

    # Set a basic spec schema for fingerprinting
    spec_schema = {
        "type": "object",
        "required": ["connection", "table"],
        "properties": {
            "connection": {"type": "string"},
            "table": {"type": "string"},
            "schema": {"type": "string"},
        },
    }
    discovery.set_spec_schema(spec_schema)

    return discovery


class TestCacheInvalidationIntegration:
    """Integration tests for cache invalidation scenarios."""

    @pytest.mark.asyncio
    async def test_cache_hit_on_identical_request(self, discovery, mock_extractor):
        """Test that identical requests hit the cache."""
        options = {"table": "users", "schema": "public"}

        # First request - should call extractor
        result1 = await discovery.get_table_info("users", options)
        assert mock_extractor.get_table_info_calls == 1
        assert result1.name == "users"

        # Second identical request - should use cache
        result2 = await discovery.get_table_info("users", options)
        assert mock_extractor.get_table_info_calls == 1  # No additional call
        assert result2.name == "users"

    @pytest.mark.asyncio
    async def test_cache_invalidation_on_options_change(self, discovery, mock_extractor):
        """Test that changing options invalidates cache."""
        options1 = {"table": "users", "schema": "public"}
        options2 = {"table": "users", "schema": "private"}

        # First request
        result1 = await discovery.get_table_info("users", options1)
        assert mock_extractor.get_table_info_calls == 1

        # Second request with different options - should invalidate cache
        result2 = await discovery.get_table_info("users", options2)
        assert mock_extractor.get_table_info_calls == 2  # Cache miss, new call

    @pytest.mark.asyncio
    async def test_cache_invalidation_on_spec_change(self, discovery, mock_extractor):
        """Test that changing spec schema invalidates cache."""
        options = {"table": "users", "schema": "public"}

        # First request
        result1 = await discovery.get_table_info("users", options)
        assert mock_extractor.get_table_info_calls == 1

        # Change spec schema
        new_spec_schema = {
            "type": "object",
            "required": ["connection", "table", "schema"],  # Added schema as required
            "properties": {
                "connection": {"type": "string"},
                "table": {"type": "string"},
                "schema": {"type": "string"},
            },
        }
        discovery.set_spec_schema(new_spec_schema)

        # Second request with same options but different spec - should invalidate
        result2 = await discovery.get_table_info("users", options)
        assert mock_extractor.get_table_info_calls == 2  # Cache miss due to spec change

    @pytest.mark.asyncio
    async def test_cache_invalidation_on_component_version_change(self, discovery, mock_extractor):
        """Test that changing component version invalidates cache."""
        options = {"table": "users", "schema": "public"}

        # First request
        result1 = await discovery.get_table_info("users", options)
        assert mock_extractor.get_table_info_calls == 1

        # Create new discovery with different version
        discovery2 = ProgressiveDiscovery(
            extractor=mock_extractor,
            cache_dir=discovery.cache_dir,
            component_type="mysql.table",
            component_version="0.2.0",  # Different version
            connection_ref="@mysql",
        )
        discovery2.set_spec_schema(discovery.spec_schema)

        # Second request with same options but different version - should invalidate
        result2 = await discovery2.get_table_info("users", options)
        assert mock_extractor.get_table_info_calls == 2  # Cache miss due to version change

    @pytest.mark.asyncio
    async def test_cache_invalidation_on_connection_change(self, discovery, mock_extractor):
        """Test that changing connection reference invalidates cache."""
        options = {"table": "users", "schema": "public"}

        # First request
        result1 = await discovery.get_table_info("users", options)
        assert mock_extractor.get_table_info_calls == 1

        # Create new discovery with different connection ref
        discovery2 = ProgressiveDiscovery(
            extractor=mock_extractor,
            cache_dir=discovery.cache_dir,
            component_type="mysql.table",
            component_version="0.1.0",
            connection_ref="@mysql2",  # Different connection
        )
        discovery2.set_spec_schema(discovery.spec_schema)

        # Second request with same options but different connection - should invalidate
        result2 = await discovery2.get_table_info("users", options)
        assert mock_extractor.get_table_info_calls == 2  # Cache miss due to connection change

    @pytest.mark.asyncio
    async def test_multiple_tables_independent_caching(self, discovery, mock_extractor):
        """Test that different tables are cached independently."""
        options = {"schema": "public"}

        # Request info for different tables
        result1 = await discovery.get_table_info("users", options)
        assert mock_extractor.get_table_info_calls == 1

        result2 = await discovery.get_table_info("orders", options)
        assert mock_extractor.get_table_info_calls == 2

        # Re-request first table - should use cache
        result3 = await discovery.get_table_info("users", options)
        assert mock_extractor.get_table_info_calls == 2  # No additional call

        # Re-request second table - should use cache
        result4 = await discovery.get_table_info("orders", options)
        assert mock_extractor.get_table_info_calls == 2  # No additional call

    @pytest.mark.asyncio
    async def test_cache_persistence_across_instances(self, mock_extractor, temp_cache_dir):
        """Test that cache persists across discovery instances."""
        spec_schema = {
            "type": "object",
            "required": ["connection", "table"],
            "properties": {"connection": {"type": "string"}, "table": {"type": "string"}},
        }

        # First discovery instance
        discovery1 = ProgressiveDiscovery(
            extractor=mock_extractor,
            cache_dir=temp_cache_dir,
            component_type="mysql.table",
            component_version="0.1.0",
            connection_ref="@mysql",
        )
        discovery1.set_spec_schema(spec_schema)

        options = {"table": "users"}
        result1 = await discovery1.get_table_info("users", options)
        assert mock_extractor.get_table_info_calls == 1

        # Second discovery instance with same configuration
        discovery2 = ProgressiveDiscovery(
            extractor=mock_extractor,
            cache_dir=temp_cache_dir,
            component_type="mysql.table",
            component_version="0.1.0",
            connection_ref="@mysql",
        )
        discovery2.set_spec_schema(spec_schema)

        # Should use cached result
        result2 = await discovery2.get_table_info("users", options)
        assert mock_extractor.get_table_info_calls == 1  # No additional call

    @pytest.mark.asyncio
    async def test_cache_file_structure_with_fingerprint(self, discovery, temp_cache_dir):
        """Test that cache files contain fingerprint metadata."""
        options = {"table": "users", "schema": "public"}

        # Make request to create cache file
        await discovery.get_table_info("users", options)

        # Check cache file exists and has correct structure
        cache_file = Path(temp_cache_dir) / "table_users.json"
        assert cache_file.exists()

        with open(cache_file) as f:
            cache_data = json.load(f)

        # Check new fingerprint format
        required_fields = ["key", "created_at", "ttl_seconds", "fingerprint", "payload"]
        for field in required_fields:
            assert field in cache_data

        # Check fingerprint structure
        fingerprint = cache_data["fingerprint"]
        assert fingerprint["component_type"] == "mysql.table"
        assert fingerprint["component_version"] == "0.1.0"
        assert fingerprint["connection_ref"] == "@mysql"
        assert len(fingerprint["options_fp"]) == 64  # SHA-256 length
        assert len(fingerprint["spec_fp"]) == 64

        # Check payload contains table info
        payload = cache_data["payload"]
        assert payload["name"] == "users"
        assert "columns" in payload
        assert "sample_data" in payload

    @pytest.mark.asyncio
    async def test_cache_ttl_expiry(self, discovery, mock_extractor):
        """Test cache expiry based on TTL."""
        options = {"table": "users", "schema": "public"}

        # Set very short TTL for testing
        discovery.cache_ttl = 1  # 1 second

        # First request
        result1 = await discovery.get_table_info("users", options)
        assert mock_extractor.get_table_info_calls == 1

        # Immediately after - should use cache
        result2 = await discovery.get_table_info("users", options)
        assert mock_extractor.get_table_info_calls == 1

        # Wait for expiry (in real test, would sleep, but for unit test we can mock time)
        import time

        time.sleep(1.1)

        # After expiry - should make new call
        result3 = await discovery.get_table_info("users", options)
        assert mock_extractor.get_table_info_calls == 2

    @pytest.mark.asyncio
    async def test_backward_compatibility_with_legacy_cache(
        self, discovery, mock_extractor, temp_cache_dir
    ):
        """Test that legacy cache format is handled gracefully."""
        # Create a legacy cache file (without fingerprint)
        legacy_cache_data = {
            "name": "users",
            "columns": ["id", "name"],
            "column_types": {"id": "int", "name": "varchar"},
            "primary_keys": ["id"],
            "row_count": 50,
            "sample_data": [{"id": 1, "name": "test"}],
        }

        cache_file = Path(temp_cache_dir) / "table_users.json"
        with open(cache_file, "w") as f:
            json.dump(legacy_cache_data, f)

        options = {"table": "users", "schema": "public"}

        # Request should not use legacy cache (no fingerprint validation)
        # and should create new fingerprinted cache
        result = await discovery.get_table_info("users", options)
        assert mock_extractor.get_table_info_calls == 1

        # Check that new fingerprinted cache was created
        with open(cache_file) as f:
            new_cache_data = json.load(f)
        assert "fingerprint" in new_cache_data

    @pytest.mark.asyncio
    async def test_complex_options_fingerprinting(self, discovery, mock_extractor):
        """Test fingerprinting with complex nested options."""
        options1 = {
            "table": "users",
            "schema": "public",
            "columns": ["id", "name", "email"],
            "filters": ["status = 'active'", "created_at > '2024-01-01'"],
            "sort": {"column": "id", "direction": "asc"},
        }

        options2 = {
            "sort": {"direction": "asc", "column": "id"},  # Same content, different key order
            "schema": "public",
            "table": "users",
            "columns": ["id", "name", "email"],  # Same content, same order
            "filters": [
                "status = 'active'",
                "created_at > '2024-01-01'",
            ],  # Same content, same order
        }

        # First request
        result1 = await discovery.get_table_info("users", options1)
        assert mock_extractor.get_table_info_calls == 1

        # Second request with same content and same array ordering - should use cache
        result2 = await discovery.get_table_info("users", options2)
        assert (
            mock_extractor.get_table_info_calls == 1
        )  # Should use cache due to canonical ordering

        # Third request with different array ordering - should NOT use cache (different semantics)
        options3 = {
            "table": "users",
            "schema": "public",
            "columns": ["email", "name", "id"],  # Different order - may affect SQL SELECT
            "filters": [
                "created_at > '2024-01-01'",
                "status = 'active'",
            ],  # Different order - may affect query plan
            "sort": {"column": "id", "direction": "asc"},
        }

        result3 = await discovery.get_table_info("users", options3)
        assert (
            mock_extractor.get_table_info_calls == 2
        )  # Cache miss due to different array ordering


class TestErrorHandling:
    """Test error handling in cache invalidation scenarios."""

    @pytest.mark.asyncio
    async def test_corrupted_cache_file_handling(self, discovery, mock_extractor, temp_cache_dir):
        """Test handling of corrupted cache files."""
        # Create corrupted cache file
        cache_file = Path(temp_cache_dir) / "table_users.json"
        with open(cache_file, "w") as f:
            f.write("invalid json content {")

        options = {"table": "users", "schema": "public"}

        # Should handle corrupted cache gracefully and make fresh request
        result = await discovery.get_table_info("users", options)
        assert mock_extractor.get_table_info_calls == 1
        assert result.name == "users"

        # Should create new valid cache file
        with open(cache_file) as f:
            cache_data = json.load(f)
        assert "fingerprint" in cache_data

    @pytest.mark.asyncio
    async def test_permission_denied_cache_dir(self, mock_extractor):
        """Test handling when cache directory is not writable."""
        # Use a non-existent parent directory that can't be created
        invalid_cache_dir = "/nonexistent/readonly/cache"

        discovery = ProgressiveDiscovery(
            extractor=mock_extractor,
            cache_dir=invalid_cache_dir,
            component_type="mysql.table",
            component_version="0.1.0",
            connection_ref="@mysql",
        )

        # Should work without caching
        result = await discovery.get_table_info("users", {"table": "users"})
        assert result.name == "users"
        # Can't easily test cache creation failure without mocking, but at least ensure it doesn't crash
