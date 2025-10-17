"""
Test discovery cache TTL behavior.
"""

import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from osiris.mcp.cache import DiscoveryCache


class TestCacheTTL:
    """Test cache TTL expiry behavior."""

    @pytest.fixture
    def temp_cache_dir(self):
        """Create temporary cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def cache(self, temp_cache_dir):
        """Create cache with temporary directory."""
        return DiscoveryCache(cache_dir=temp_cache_dir, default_ttl_hours=1)

    @pytest.mark.asyncio
    async def test_cache_set_and_get(self, cache):
        """Test basic cache set and get."""
        test_data = {"database": "test", "tables": ["users", "orders"]}

        # Set cache entry
        discovery_id = await cache.set("conn1", "comp1", 5, test_data, "key1")

        # Get cached entry (returns full entry including TTL metadata)
        result = await cache.get("conn1", "comp1", 5, "key1")

        assert result is not None
        assert result["data"]["database"] == "test"
        assert result["data"]["tables"] == ["users", "orders"]
        # Verify TTL metadata is present (CACHE-002 fix)
        assert "expires_at" in result
        assert "ttl_seconds" in result
        assert "discovery_id" in result

    @pytest.mark.asyncio
    async def test_cache_ttl_expiry(self, cache):
        """Test cache entries expire after TTL."""
        test_data = {"test": "data"}

        # Set with 1 second TTL
        discovery_id = await cache.set("conn1", "comp1", 0, test_data, ttl=timedelta(seconds=1))

        # Should be available immediately
        result = await cache.get("conn1", "comp1", 0)
        assert result is not None

        # Mock time to after expiry
        future_time = datetime.now(UTC) + timedelta(seconds=2)

        # Patch datetime.now to return future time
        with patch("osiris.mcp.cache.datetime") as mock_datetime:
            # Configure mock to handle both datetime.now(timezone.utc) and datetime.fromisoformat
            mock_datetime.now = lambda tz=None: future_time
            mock_datetime.fromisoformat = datetime.fromisoformat

            # Should be expired
            result = await cache.get("conn1", "comp1", 0)
            assert result is None

    @pytest.mark.asyncio
    async def test_cache_clear_expired(self, cache):
        """Test clearing expired entries."""
        # Create entries with different TTLs
        await cache.set("conn1", "comp1", 0, {"data": 1}, ttl=timedelta(seconds=1))
        await cache.set("conn2", "comp2", 0, {"data": 2}, ttl=timedelta(hours=24))

        # Mock time to expire first entry
        future_time = datetime.now(UTC) + timedelta(seconds=2)
        with patch("osiris.mcp.cache.datetime") as mock_datetime:
            # Configure mock to handle both datetime.now(timezone.utc) and datetime.fromisoformat
            mock_datetime.now = lambda tz=None: future_time
            mock_datetime.fromisoformat = datetime.fromisoformat

            # Clear expired entries
            await cache.clear_expired()

            # First should be gone
            result1 = await cache.get("conn1", "comp1", 0)
            assert result1 is None

            # Second should still exist
            result2 = await cache.get("conn2", "comp2", 0)
            assert result2 is not None

    @pytest.mark.asyncio
    async def test_cache_deterministic_keys(self, cache):
        """Test cache key generation is deterministic."""
        # Same parameters should generate same key
        key1 = cache._generate_cache_key("conn", "comp", 5, "idempotency")
        key2 = cache._generate_cache_key("conn", "comp", 5, "idempotency")
        assert key1 == key2

        # Different parameters should generate different keys
        key3 = cache._generate_cache_key("conn", "comp", 10, "idempotency")
        assert key1 != key3

        key4 = cache._generate_cache_key("conn", "comp", 5, "different")
        assert key1 != key4

    @pytest.mark.asyncio
    async def test_cache_persistence(self, cache, temp_cache_dir):
        """Test cache persists to disk."""
        test_data = {"persistent": "data"}

        # Set cache entry
        discovery_id = await cache.set("conn1", "comp1", 0, test_data)

        # Check file exists
        cache_file = temp_cache_dir / f"{discovery_id}.json"
        assert cache_file.exists()

        # Load file and verify content
        with open(cache_file) as f:
            stored = json.load(f)

        assert stored["discovery_id"] == discovery_id
        assert stored["data"]["persistent"] == "data"
        assert stored["connection_id"] == "conn1"
        assert stored["component_id"] == "comp1"

    @pytest.mark.asyncio
    async def test_cache_clear_all(self, cache):
        """Test clearing all cache entries."""
        # Create multiple entries
        await cache.set("conn1", "comp1", 0, {"data": 1})
        await cache.set("conn2", "comp2", 0, {"data": 2})
        await cache.set("conn3", "comp3", 0, {"data": 3})

        # Verify entries exist
        assert await cache.get("conn1", "comp1", 0) is not None
        assert await cache.get("conn2", "comp2", 0) is not None

        # Clear all
        await cache.clear_all()

        # Verify all are gone
        assert await cache.get("conn1", "comp1", 0) is None
        assert await cache.get("conn2", "comp2", 0) is None
        assert await cache.get("conn3", "comp3", 0) is None

    def test_cache_stats(self, cache):
        """Test cache statistics."""
        stats = cache.get_cache_stats()

        assert "memory_entries" in stats
        assert "expired_entries" in stats
        assert "disk_files" in stats
        assert "disk_size_bytes" in stats
        assert "cache_directory" in stats

    def test_discovery_uri_generation(self, cache):
        """Test discovery artifact URI generation."""
        uri = cache.get_discovery_uri("disc_123", "overview")
        assert uri == "osiris://mcp/discovery/disc_123/overview.json"

        uri = cache.get_discovery_uri("disc_456", "tables")
        assert uri == "osiris://mcp/discovery/disc_456/tables.json"

    @pytest.mark.asyncio
    async def test_cache_invalidate_connection(self, cache):
        """Test cache invalidation by connection ID."""
        # Create cache entries for multiple connections
        await cache.set("mysql.default", "extractor", 5, {"data": "mysql"})
        await cache.set("mysql.default", "extractor", 10, {"data": "mysql2"})
        await cache.set("supabase.main", "writer", 0, {"data": "supabase"})

        # Verify entries exist
        assert await cache.get("mysql.default", "extractor", 5) is not None
        assert await cache.get("mysql.default", "extractor", 10) is not None
        assert await cache.get("supabase.main", "writer", 0) is not None

        # Invalidate mysql.default connection
        count = await cache.invalidate_connection("mysql.default")

        # Should have invalidated 2 entries
        assert count == 2

        # MySQL entries should be gone
        assert await cache.get("mysql.default", "extractor", 5) is None
        assert await cache.get("mysql.default", "extractor", 10) is None

        # Supabase entry should still exist
        assert await cache.get("supabase.main", "writer", 0) is not None

    @pytest.mark.asyncio
    async def test_cache_uses_config_path(self, temp_cache_dir):
        """Test cache uses config-driven path from MCPFilesystemConfig."""
        # Create cache without passing cache_dir (should load from config)
        cache_with_config = DiscoveryCache()

        # Cache dir should be set from config, not Path.home()
        assert cache_with_config.cache_dir is not None
        assert "Path.home()" not in str(cache_with_config.cache_dir)

        # Test with explicit cache_dir
        cache_explicit = DiscoveryCache(cache_dir=temp_cache_dir)
        assert cache_explicit.cache_dir == temp_cache_dir

    @pytest.mark.asyncio
    async def test_cache_invalidate_connection_disk_persistence(self, cache, temp_cache_dir):
        """Test cache invalidation removes files from disk."""
        # Create cache entries that persist to disk
        discovery_id_1 = await cache.set("mysql.test", "extractor", 5, {"data": "test1"})
        discovery_id_2 = await cache.set("mysql.test", "extractor", 10, {"data": "test2"})
        discovery_id_3 = await cache.set("postgres.main", "writer", 0, {"data": "pg"})

        # Verify files exist on disk
        assert (temp_cache_dir / f"{discovery_id_1}.json").exists()
        assert (temp_cache_dir / f"{discovery_id_2}.json").exists()
        assert (temp_cache_dir / f"{discovery_id_3}.json").exists()

        # Invalidate mysql.test connection
        count = await cache.invalidate_connection("mysql.test")
        assert count == 2

        # MySQL cache files should be deleted
        assert not (temp_cache_dir / f"{discovery_id_1}.json").exists()
        assert not (temp_cache_dir / f"{discovery_id_2}.json").exists()

        # Postgres cache file should still exist
        assert (temp_cache_dir / f"{discovery_id_3}.json").exists()

    @pytest.mark.asyncio
    async def test_cache_invalidate_nonexistent_connection(self, cache):
        """Test invalidating a connection that doesn't exist returns 0."""
        # Create some cache entries
        await cache.set("mysql.default", "extractor", 5, {"data": "test"})

        # Invalidate non-existent connection
        count = await cache.invalidate_connection("nonexistent.connection")

        # Should return 0
        assert count == 0

        # Original entry should still exist
        assert await cache.get("mysql.default", "extractor", 5) is not None
