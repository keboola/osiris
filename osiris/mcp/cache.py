"""
Cache management for Osiris MCP server.

Handles TTL-based caching for discovery artifacts.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


class DiscoveryCache:
    """
    Cache for discovery artifacts with TTL support.

    Discovery results are cached for 24 hours by default to avoid
    expensive re-discovery operations.
    """

    def __init__(self, cache_dir: Path | None = None, default_ttl_hours: int = 24):
        """
        Initialize the discovery cache.

        Args:
            cache_dir: Directory for cache storage
            default_ttl_hours: Default TTL in hours
        """
        self.cache_dir = cache_dir or Path.home() / ".osiris_cache" / "mcp" / "discovery"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.default_ttl = timedelta(hours=default_ttl_hours)

        # In-memory cache for fast lookups
        self._memory_cache: dict[str, dict[str, Any]] = {}

    def _generate_cache_key(
        self, connection_id: str, component_id: str, samples: int = 0, idempotency_key: str | None = None
    ) -> str:
        """
        Generate a deterministic cache key.

        Args:
            connection_id: Database connection ID
            component_id: Component ID
            samples: Number of samples requested
            idempotency_key: Optional idempotency key for determinism

        Returns:
            Cache key string
        """
        # Create deterministic key components
        key_parts = [connection_id, component_id, str(samples), idempotency_key or ""]

        # Generate hash for consistent key
        key_string = "|".join(key_parts)
        key_hash = hashlib.sha256(key_string.encode()).hexdigest()[:16]

        return f"disc_{key_hash}"

    async def get(
        self, connection_id: str, component_id: str, samples: int = 0, idempotency_key: str | None = None
    ) -> dict[str, Any] | None:
        """
        Get cached discovery result.

        Args:
            connection_id: Database connection ID
            component_id: Component ID
            samples: Number of samples requested
            idempotency_key: Optional idempotency key

        Returns:
            Cached discovery result or None if not found/expired
        """
        cache_key = self._generate_cache_key(connection_id, component_id, samples, idempotency_key)

        # Check memory cache first
        if cache_key in self._memory_cache:
            entry = self._memory_cache[cache_key]
            if not self._is_expired(entry):
                return entry["data"]
            else:
                # Remove expired entry
                del self._memory_cache[cache_key]

        # Check disk cache
        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    entry = json.load(f)

                if not self._is_expired(entry):
                    # Load into memory cache
                    self._memory_cache[cache_key] = entry
                    return entry["data"]
                else:
                    # Remove expired file
                    cache_file.unlink()
            except (OSError, json.JSONDecodeError):
                # Corrupted cache file, remove it
                cache_file.unlink(missing_ok=True)

        return None

    async def set(
        self,
        connection_id: str,
        component_id: str,
        samples: int,
        data: dict[str, Any],
        idempotency_key: str | None = None,
        ttl: timedelta | None = None,
    ) -> str:
        """
        Cache discovery result.

        Args:
            connection_id: Database connection ID
            component_id: Component ID
            samples: Number of samples included
            data: Discovery data to cache
            idempotency_key: Optional idempotency key
            ttl: Optional custom TTL

        Returns:
            Discovery ID for referencing cached data
        """
        cache_key = self._generate_cache_key(connection_id, component_id, samples, idempotency_key)

        ttl = ttl or self.default_ttl
        expiry_time = datetime.now(UTC) + ttl

        # Create cache entry
        entry = {
            "discovery_id": cache_key,
            "connection_id": connection_id,
            "component_id": component_id,
            "samples": samples,
            "idempotency_key": idempotency_key,
            "data": data,
            "created_at": datetime.now(UTC).isoformat(),
            "expires_at": expiry_time.isoformat(),
            "ttl_seconds": int(ttl.total_seconds()),
        }

        # Save to memory cache
        self._memory_cache[cache_key] = entry

        # Save to disk
        cache_file = self.cache_dir / f"{cache_key}.json"
        with open(cache_file, "w") as f:
            json.dump(entry, f, indent=2)

        return cache_key

    def _is_expired(self, entry: dict[str, Any]) -> bool:
        """Check if a cache entry is expired."""
        expires_at = datetime.fromisoformat(entry["expires_at"])
        return datetime.now(UTC) >= expires_at

    async def clear_expired(self):
        """Remove all expired cache entries."""
        # Clear from memory
        expired_keys = [key for key, entry in self._memory_cache.items() if self._is_expired(entry)]
        for key in expired_keys:
            del self._memory_cache[key]

        # Clear from disk
        for cache_file in self.cache_dir.glob("disc_*.json"):
            try:
                with open(cache_file) as f:
                    entry = json.load(f)
                if self._is_expired(entry):
                    cache_file.unlink()
            except (OSError, json.JSONDecodeError):
                # Remove corrupted files
                cache_file.unlink()

    async def clear_all(self):
        """Clear all cache entries."""
        # Clear memory cache
        self._memory_cache.clear()

        # Clear disk cache
        for cache_file in self.cache_dir.glob("disc_*.json"):
            cache_file.unlink()

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total_entries = len(self._memory_cache)
        expired_entries = sum(1 for entry in self._memory_cache.values() if self._is_expired(entry))

        disk_files = list(self.cache_dir.glob("disc_*.json"))
        disk_size = sum(f.stat().st_size for f in disk_files)

        return {
            "memory_entries": total_entries,
            "expired_entries": expired_entries,
            "disk_files": len(disk_files),
            "disk_size_bytes": disk_size,
            "cache_directory": str(self.cache_dir),
        }

    def get_discovery_uri(self, discovery_id: str, artifact_type: str) -> str:
        """
        Generate URI for a discovery artifact.

        Args:
            discovery_id: Discovery cache ID
            artifact_type: Type of artifact (overview, tables, samples)

        Returns:
            Osiris URI for the artifact
        """
        return f"osiris://mcp/discovery/{discovery_id}/{artifact_type}.json"
