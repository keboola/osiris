"""
Unified ID generation for Osiris.

This module provides a single source of truth for generating stable,
deterministic identifiers used across the system.

Design Principles:
- Deterministic: Same inputs → same ID
- Stable: IDs don't change across versions
- Collision-resistant: SHA-256 provides sufficient entropy
- Consistent: All modules use these functions
"""

import hashlib


def generate_discovery_id(connection_id: str, component_id: str, samples: int) -> str:
    """
    Generate deterministic discovery ID.

    This ID identifies the DISCOVERY RESULT itself, not individual requests.
    Multiple requests with the same logical parameters should produce the
    same discovery_id to enable artifact reuse.

    Args:
        connection_id: Connection reference (e.g., "@mysql.main")
        component_id: Component identifier (e.g., "mysql.extractor")
        samples: Number of sample rows requested

    Returns:
        Discovery ID in format: disc_<16-hex-chars>

    Example:
        >>> generate_discovery_id("@mysql.main", "mysql.extractor", 10)
        'disc_a1b2c3d4e5f6g7h8'

    Note:
        The idempotency_key parameter is NOT included in discovery_id.
        - discovery_id identifies the DISCOVERY RESULT (deterministic based on inputs)
        - idempotency_key is for REQUEST deduplication (MCP cache layer only)

        This separation prevents file overwrites when different idempotency_keys
        are used for the same logical discovery.
    """
    key_parts = [connection_id, component_id, str(samples)]
    key_string = "|".join(key_parts)
    key_hash = hashlib.sha256(key_string.encode()).hexdigest()[:16]
    return f"disc_{key_hash}"


def generate_cache_key(connection_id: str, component_id: str, samples: int, idempotency_key: str | None = None) -> str:
    """
    Generate MCP cache key for request deduplication.

    This key is used for MCP-level caching to ensure the same request
    (including idempotency_key) always returns the same cached response.

    The cache key INCLUDES idempotency_key to distinguish different requests
    that happen to query the same discovery result.

    Args:
        connection_id: Connection reference (e.g., "@mysql.main")
        component_id: Component identifier (e.g., "mysql.extractor")
        samples: Number of sample rows requested
        idempotency_key: Optional idempotency key for request deduplication

    Returns:
        Cache key in format: cache_<16-hex-chars>

    Example:
        >>> generate_cache_key("@mysql.main", "mysql.extractor", 10, "abc123")
        'cache_a1b2c3d4e5f6g7h8'
        >>> generate_cache_key("@mysql.main", "mysql.extractor", 10, "def456")
        'cache_x9y8z7w6v5u4t3s2'  # Different key!

    Note:
        The cache key is distinct from discovery_id:
        - cache_key: For MCP request-level caching (includes idempotency_key)
        - discovery_id: For artifact identification (excludes idempotency_key)

        Multiple cache entries can point to the same discovery_id.
    """
    key_parts = [connection_id, component_id, str(samples), idempotency_key or ""]
    key_string = "|".join(key_parts)
    key_hash = hashlib.sha256(key_string.encode()).hexdigest()[:16]
    return f"cache_{key_hash}"
