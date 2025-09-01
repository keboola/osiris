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

"""Tests for cache fingerprinting system (M0.1)."""

from datetime import datetime, timedelta

from osiris.core.cache_fingerprint import (
    CacheEntry,
    CacheFingerprint,
    canonical_json,
    create_cache_entry,
    create_cache_fingerprint,
    fingerprints_match,
    input_options_fingerprint,
    sha256_hex,
    should_invalidate_cache,
    spec_fingerprint,
)


class TestCanonicalization:
    """Test canonical JSON serialization."""

    def test_canonical_json_stable_ordering(self):
        """Test that canonical JSON produces stable ordering."""
        obj1 = {"b": 2, "a": 1, "c": {"z": 3, "y": 4}}
        obj2 = {"c": {"y": 4, "z": 3}, "a": 1, "b": 2}

        result1 = canonical_json(obj1)
        result2 = canonical_json(obj2)

        assert result1 == result2
        assert result1 == '{"a":1,"b":2,"c":{"y":4,"z":3}}'

    def test_canonical_json_no_whitespace(self):
        """Test that canonical JSON has no whitespace."""
        obj = {"key": "value", "number": 42}
        result = canonical_json(obj)

        assert " " not in result
        assert "\n" not in result
        assert "\t" not in result

    def test_sha256_hex(self):
        """Test SHA-256 hash generation."""
        test_string = "hello world"
        result = sha256_hex(test_string)

        # Known SHA-256 of "hello world"
        expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        assert result == expected
        assert len(result) == 64  # SHA-256 is 64 hex chars


class TestFingerprints:
    """Test fingerprint generation."""

    def test_input_options_fingerprint(self):
        """Test input options fingerprinting."""
        options1 = {"table": "users", "schema": "public", "columns": ["id", "name"]}
        options2 = {"columns": ["id", "name"], "schema": "public", "table": "users"}

        fp1 = input_options_fingerprint(options1)
        fp2 = input_options_fingerprint(options2)

        # Should be identical due to canonical ordering
        assert fp1 == fp2
        assert len(fp1) == 64  # SHA-256 length

    def test_spec_fingerprint(self):
        """Test spec schema fingerprinting."""
        spec1 = {
            "type": "object",
            "required": ["connection", "table"],
            "properties": {"connection": {"type": "string"}, "table": {"type": "string"}},
        }
        spec2 = {
            "properties": {"table": {"type": "string"}, "connection": {"type": "string"}},
            "required": ["connection", "table"],
            "type": "object",
        }

        fp1 = spec_fingerprint(spec1)
        fp2 = spec_fingerprint(spec2)

        assert fp1 == fp2
        assert len(fp1) == 64

    def test_create_cache_fingerprint(self):
        """Test complete fingerprint creation."""
        options = {"table": "users", "schema": "public"}
        spec_schema = {"type": "object", "required": ["table"]}

        fingerprint = create_cache_fingerprint(
            component_type="mysql.table",
            component_version="0.1.0",
            connection_ref="@mysql",
            options=options,
            spec_schema=spec_schema,
        )

        assert isinstance(fingerprint, CacheFingerprint)
        assert fingerprint.component_type == "mysql.table"
        assert fingerprint.component_version == "0.1.0"
        assert fingerprint.connection_ref == "@mysql"
        assert len(fingerprint.options_fp) == 64
        assert len(fingerprint.spec_fp) == 64

    def test_fingerprint_cache_key(self):
        """Test cache key generation from fingerprint."""
        fingerprint = CacheFingerprint(
            component_type="mysql.table",
            component_version="0.1.0",
            connection_ref="@mysql",
            options_fp="abc123",
            spec_fp="def456",
        )

        expected = "mysql.table:0.1.0:@mysql:abc123:def456"
        assert fingerprint.cache_key == expected

    def test_fingerprints_match(self):
        """Test fingerprint matching."""
        fp1 = CacheFingerprint("mysql.table", "0.1.0", "@mysql", "abc123", "def456")
        fp2 = CacheFingerprint("mysql.table", "0.1.0", "@mysql", "abc123", "def456")
        fp3 = CacheFingerprint("mysql.table", "0.1.0", "@mysql", "different", "def456")

        assert fingerprints_match(fp1, fp2)
        assert not fingerprints_match(fp1, fp3)


class TestCacheEntry:
    """Test cache entry operations."""

    def test_create_cache_entry(self):
        """Test cache entry creation."""
        fingerprint = CacheFingerprint("mysql.table", "0.1.0", "@mysql", "abc123", "def456")
        payload = {"name": "users", "columns": ["id", "name"]}

        entry = create_cache_entry(fingerprint, payload, ttl_seconds=1800)

        assert isinstance(entry, CacheEntry)
        assert entry.key == fingerprint.cache_key
        assert entry.ttl_seconds == 1800
        assert entry.payload == payload
        assert entry.fingerprint == fingerprint

        # Check timestamp format
        assert entry.created_at.endswith("Z")
        datetime.fromisoformat(entry.created_at.replace("Z", "+00:00"))  # Should not raise

    def test_cache_entry_expiry(self):
        """Test cache entry expiry logic."""
        fingerprint = CacheFingerprint("mysql.table", "0.1.0", "@mysql", "abc123", "def456")
        payload = {"test": "data"}

        # Create entry that expires in 1 second
        entry = create_cache_entry(fingerprint, payload, ttl_seconds=1)

        # Should not be expired initially
        assert not entry.is_expired

        # Manually set creation time to 2 seconds ago
        past_time = (datetime.utcnow() - timedelta(seconds=2)).isoformat() + "Z"
        entry.created_at = past_time

        # Should now be expired
        assert entry.is_expired


class TestCacheInvalidation:
    """Test cache invalidation logic."""

    def test_should_invalidate_no_cache(self):
        """Test invalidation when no cache exists."""
        fingerprint = CacheFingerprint("mysql.table", "0.1.0", "@mysql", "abc123", "def456")

        assert should_invalidate_cache(None, fingerprint)

    def test_should_invalidate_expired_cache(self):
        """Test invalidation when cache is expired."""
        fingerprint = CacheFingerprint("mysql.table", "0.1.0", "@mysql", "abc123", "def456")
        payload = {"test": "data"}

        # Create expired entry
        entry = create_cache_entry(fingerprint, payload, ttl_seconds=1)
        past_time = (datetime.utcnow() - timedelta(seconds=2)).isoformat() + "Z"
        entry.created_at = past_time

        assert should_invalidate_cache(entry, fingerprint)

    def test_should_invalidate_fingerprint_mismatch(self):
        """Test invalidation when fingerprints don't match."""
        fingerprint1 = CacheFingerprint("mysql.table", "0.1.0", "@mysql", "abc123", "def456")
        fingerprint2 = CacheFingerprint("mysql.table", "0.1.0", "@mysql", "different", "def456")

        entry = create_cache_entry(fingerprint1, {"test": "data"})

        assert should_invalidate_cache(entry, fingerprint2)

    def test_should_not_invalidate_valid_cache(self):
        """Test that valid cache with matching fingerprint is not invalidated."""
        fingerprint = CacheFingerprint("mysql.table", "0.1.0", "@mysql", "abc123", "def456")
        entry = create_cache_entry(fingerprint, {"test": "data"}, ttl_seconds=3600)

        assert not should_invalidate_cache(entry, fingerprint)

    def test_different_component_types_invalidate(self):
        """Test that different component types cause invalidation."""
        fingerprint1 = CacheFingerprint("mysql.table", "0.1.0", "@mysql", "abc123", "def456")
        fingerprint2 = CacheFingerprint("supabase.table", "0.1.0", "@mysql", "abc123", "def456")

        entry = create_cache_entry(fingerprint1, {"test": "data"})

        assert should_invalidate_cache(entry, fingerprint2)

    def test_different_versions_invalidate(self):
        """Test that different component versions cause invalidation."""
        fingerprint1 = CacheFingerprint("mysql.table", "0.1.0", "@mysql", "abc123", "def456")
        fingerprint2 = CacheFingerprint("mysql.table", "0.2.0", "@mysql", "abc123", "def456")

        entry = create_cache_entry(fingerprint1, {"test": "data"})

        assert should_invalidate_cache(entry, fingerprint2)

    def test_different_connections_invalidate(self):
        """Test that different connections cause invalidation."""
        fingerprint1 = CacheFingerprint("mysql.table", "0.1.0", "@mysql", "abc123", "def456")
        fingerprint2 = CacheFingerprint("mysql.table", "0.1.0", "@mysql2", "abc123", "def456")

        entry = create_cache_entry(fingerprint1, {"test": "data"})

        assert should_invalidate_cache(entry, fingerprint2)

    def test_options_change_invalidates(self):
        """Test that changing input options invalidates cache."""
        options1 = {"table": "users", "schema": "public"}
        options2 = {"table": "users", "schema": "private"}
        spec_schema = {"type": "object"}

        fingerprint1 = create_cache_fingerprint(
            "mysql.table", "0.1.0", "@mysql", options1, spec_schema
        )
        fingerprint2 = create_cache_fingerprint(
            "mysql.table", "0.1.0", "@mysql", options2, spec_schema
        )

        entry = create_cache_entry(fingerprint1, {"test": "data"})

        assert should_invalidate_cache(entry, fingerprint2)

    def test_spec_change_invalidates(self):
        """Test that changing spec schema invalidates cache."""
        options = {"table": "users"}
        spec1 = {"type": "object", "required": ["table"]}
        spec2 = {"type": "object", "required": ["table", "schema"]}

        fingerprint1 = create_cache_fingerprint("mysql.table", "0.1.0", "@mysql", options, spec1)
        fingerprint2 = create_cache_fingerprint("mysql.table", "0.1.0", "@mysql", options, spec2)

        entry = create_cache_entry(fingerprint1, {"test": "data"})

        assert should_invalidate_cache(entry, fingerprint2)
