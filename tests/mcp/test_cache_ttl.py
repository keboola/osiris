"""
Test discovery cache TTL behavior.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
import json
import tempfile
from pathlib import Path

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
        test_data = {
            "database": "test",
            "tables": ["users", "orders"]
        }

        # Set cache entry
        discovery_id = await cache.set(
            "conn1", "comp1", 5, test_data, "key1"
        )

        # Get cached entry
        result = await cache.get("conn1", "comp1", 5, "key1")

        assert result is not None
        assert result["database"] == "test"
        assert result["tables"] == ["users", "orders"]

    @pytest.mark.asyncio
    async def test_cache_ttl_expiry(self, cache):
        """Test cache entries expire after TTL."""
        test_data = {"test": "data"}

        # Set with 1 second TTL
        discovery_id = await cache.set(
            "conn1", "comp1", 0, test_data, ttl=timedelta(seconds=1)
        )

        # Should be available immediately
        result = await cache.get("conn1", "comp1", 0)
        assert result is not None

        # Mock time to after expiry
        future_time = datetime.now(timezone.utc) + timedelta(seconds=2)
        with patch('osiris.mcp.cache.datetime') as mock_datetime:
            mock_datetime.now.return_value = future_time

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
        future_time = datetime.now(timezone.utc) + timedelta(seconds=2)
        with patch('osiris.mcp.cache.datetime') as mock_datetime:
            mock_datetime.now.return_value = future_time

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
        discovery_id = await cache.set(
            "conn1", "comp1", 0, test_data
        )

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