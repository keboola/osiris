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

"""Cache fingerprinting for M0 implementation.

This module implements SHA-256 fingerprinting for component specs and input options
to eliminate stale discovery reuse when configurations change.
"""

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any


@dataclass
class CacheFingerprint:
    """Cache fingerprint containing all hash components."""

    component_type: str
    component_version: str
    connection_ref: str
    options_fp: str
    spec_fp: str

    @property
    def cache_key(self) -> str:
        """Generate cache key from fingerprint components."""
        parts = [
            self.component_type,
            self.component_version,
            self.connection_ref,
            self.options_fp,
            self.spec_fp,
        ]
        return ":".join(parts)


@dataclass
class CacheEntry:
    """Cache entry with fingerprint metadata and TTL."""

    key: str
    created_at: str
    ttl_seconds: int
    fingerprint: CacheFingerprint
    payload: dict[str, Any]

    @property
    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        import time

        created_timestamp = datetime.fromisoformat(self.created_at.replace("Z", "+00:00")).timestamp()
        age = time.time() - created_timestamp
        return age > self.ttl_seconds


def canonical_json(obj: Any) -> str:
    """Convert object to canonical JSON string with stable ordering.

    Args:
        obj: Object to serialize

    Returns:
        Canonical JSON string with sorted keys and no whitespace
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def sha256_hex(s: str) -> str:
    """Generate SHA-256 hash of string.

    Args:
        s: String to hash

    Returns:
        Hexadecimal SHA-256 hash
    """
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def input_options_fingerprint(options: dict[str, Any]) -> str:
    """Generate fingerprint for input options.

    Args:
        options: Input options dictionary

    Returns:
        SHA-256 fingerprint of canonicalized options
    """
    return sha256_hex(canonical_json(options))


def spec_fingerprint(spec_schema: dict[str, Any]) -> str:
    """Generate fingerprint for component spec schema.

    Args:
        spec_schema: Component specification schema

    Returns:
        SHA-256 fingerprint of canonicalized spec schema
    """
    return sha256_hex(canonical_json(spec_schema))


def create_cache_fingerprint(
    component_type: str,
    component_version: str,
    connection_ref: str,
    options: dict[str, Any],
    spec_schema: dict[str, Any],
) -> CacheFingerprint:
    """Create complete cache fingerprint from components.

    Args:
        component_type: Type of component (e.g., "mysql.table")
        component_version: Version of component spec
        connection_ref: Connection reference (e.g., "@mysql")
        options: Input options dictionary
        spec_schema: Component specification schema

    Returns:
        Complete CacheFingerprint object
    """
    options_fp = input_options_fingerprint(options)
    spec_fp = spec_fingerprint(spec_schema)

    return CacheFingerprint(
        component_type=component_type,
        component_version=component_version,
        connection_ref=connection_ref,
        options_fp=options_fp,
        spec_fp=spec_fp,
    )


def create_cache_entry(fingerprint: CacheFingerprint, payload: dict[str, Any], ttl_seconds: int = 3600) -> CacheEntry:
    """Create cache entry with fingerprint and payload.

    Args:
        fingerprint: Cache fingerprint
        payload: Data to cache
        ttl_seconds: Time-to-live in seconds (default 1 hour)

    Returns:
        Complete CacheEntry object
    """
    return CacheEntry(
        key=fingerprint.cache_key,
        created_at=datetime.utcnow().isoformat() + "Z",
        ttl_seconds=ttl_seconds,
        fingerprint=fingerprint,
        payload=payload,
    )


def fingerprints_match(fp1: CacheFingerprint, fp2: CacheFingerprint) -> bool:
    """Check if two fingerprints match exactly.

    Args:
        fp1: First fingerprint
        fp2: Second fingerprint

    Returns:
        True if all fingerprint components match
    """
    return (
        fp1.component_type == fp2.component_type
        and fp1.component_version == fp2.component_version
        and fp1.connection_ref == fp2.connection_ref
        and fp1.options_fp == fp2.options_fp
        and fp1.spec_fp == fp2.spec_fp
    )


def should_invalidate_cache(cached_entry: CacheEntry | None, current_fingerprint: CacheFingerprint) -> bool:
    """Determine if cache should be invalidated.

    Args:
        cached_entry: Existing cache entry (if any)
        current_fingerprint: Current request fingerprint

    Returns:
        True if cache should be invalidated
    """
    # No cache entry exists
    if cached_entry is None:
        return True

    # Cache has expired
    if cached_entry.is_expired:
        return True

    # Fingerprints don't match
    return not fingerprints_match(cached_entry.fingerprint, current_fingerprint)
