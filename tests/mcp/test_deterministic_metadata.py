"""
Tests for deterministic metadata features:
- Canonical tool ID mapping
- Deterministic correlation ID derivation from request_id
"""

from osiris.mcp.cli_bridge import derive_correlation_id
from osiris.mcp.server import CANONICAL_TOOL_IDS, canonical_tool_id


class TestCanonicalToolIds:
    """Test canonical tool ID mapping."""

    def test_all_primary_tools_map_to_themselves(self):
        """Primary tool names should map to themselves."""
        primary_tools = [
            "connections_list",
            "connections_doctor",
            "components_list",
            "discovery_request",
            "usecases_list",
            "oml_schema_get",
            "oml_validate",
            "oml_save",
            "guide_start",
            "memory_capture",
            "aiop_list",
            "aiop_show",
        ]

        for tool in primary_tools:
            assert canonical_tool_id(tool) == tool, f"{tool} should map to itself"

    def test_dot_notation_aliases_map_to_primary(self):
        """Dot notation aliases should map to primary names."""
        test_cases = [
            ("connections.list", "connections_list"),
            ("connections.doctor", "connections_doctor"),
            ("components.list", "components_list"),
            ("discovery.request", "discovery_request"),
            ("usecases.list", "usecases_list"),
            ("oml.schema.get", "oml_schema_get"),
            ("oml.validate", "oml_validate"),
            ("oml.save", "oml_save"),
            ("guide.start", "guide_start"),
            ("memory.capture", "memory_capture"),
            ("aiop.list", "aiop_list"),
            ("aiop.show", "aiop_show"),
        ]

        for alias, expected in test_cases:
            assert canonical_tool_id(alias) == expected, f"{alias} should map to {expected}"

    def test_osiris_prefix_aliases_map_to_primary(self):
        """Osiris-prefixed aliases should map to primary names."""
        test_cases = [
            ("osiris.connections.list", "connections_list"),
            ("osiris.connections.doctor", "connections_doctor"),
            ("osiris.components.list", "components_list"),
            ("osiris.discovery.request", "discovery_request"),
            ("osiris.usecases.list", "usecases_list"),
            ("osiris.oml.schema.get", "oml_schema_get"),
            ("osiris.oml.validate", "oml_validate"),
            ("osiris.oml.save", "oml_save"),
            ("osiris.guide_start", "guide_start"),
            ("osiris.guide.start", "guide_start"),
            ("osiris.memory.capture", "memory_capture"),
            ("osiris.aiop.list", "aiop_list"),
            ("osiris.aiop.show", "aiop_show"),
        ]

        for alias, expected in test_cases:
            assert canonical_tool_id(alias) == expected, f"{alias} should map to {expected}"

    def test_legacy_aliases_map_to_primary(self):
        """Legacy aliases should map to primary names."""
        test_cases = [
            ("osiris.introspect_sources", "discovery_request"),
            ("osiris.validate_oml", "oml_validate"),
            ("osiris.save_oml", "oml_save"),
        ]

        for alias, expected in test_cases:
            assert canonical_tool_id(alias) == expected, f"{alias} should map to {expected}"

    def test_unknown_tool_returns_as_is(self):
        """Unknown tool names should be returned unchanged."""
        unknown_tools = ["unknown_tool", "foo.bar", "osiris.unknown"]

        for tool in unknown_tools:
            assert canonical_tool_id(tool) == tool, f"{tool} should return unchanged"

    def test_canonical_ids_count(self):
        """Should have expected number of aliases and canonical tools."""
        # We should have exactly 40 total aliases (all variations)
        assert len(CANONICAL_TOOL_IDS) == 40, "Should have 40 total aliases"

        # We should have exactly 12 unique canonical tools
        unique_canonical = set(CANONICAL_TOOL_IDS.values())
        assert len(unique_canonical) == 12, "Should have 12 unique canonical tools"

    def test_all_aliases_covered(self):
        """All aliases in mapping should return expected canonical name."""
        for alias, expected_canonical in CANONICAL_TOOL_IDS.items():
            result = canonical_tool_id(alias)
            assert result == expected_canonical, f"{alias} should map to {expected_canonical}, got {result}"


class TestDeterministicCorrelationId:
    """Test deterministic correlation ID derivation."""

    def test_same_request_id_produces_same_correlation_id(self):
        """Same request_id should always produce same correlation_id."""
        request_id = "test-request-123"

        corr_1 = derive_correlation_id(request_id)
        corr_2 = derive_correlation_id(request_id)
        corr_3 = derive_correlation_id(request_id)

        assert corr_1 == corr_2 == corr_3, "Same request_id should produce same correlation_id"

    def test_different_request_ids_produce_different_correlation_ids(self):
        """Different request_ids should produce different correlation_ids."""
        request_id_1 = "test-request-123"
        request_id_2 = "test-request-456"

        corr_1 = derive_correlation_id(request_id_1)
        corr_2 = derive_correlation_id(request_id_2)

        assert corr_1 != corr_2, "Different request_ids should produce different correlation_ids"

    def test_correlation_id_format(self):
        """Correlation ID should have mcp_ prefix and 12 hex chars."""
        request_id = "test-request-abc"
        corr_id = derive_correlation_id(request_id)

        assert corr_id.startswith("mcp_"), "Should have mcp_ prefix"
        assert len(corr_id) == 16, "Should be 16 chars total (mcp_ + 12 hex)"

        # Check that part after mcp_ is valid hex
        hex_part = corr_id[4:]
        assert len(hex_part) == 12, "Should have 12 hex chars after prefix"
        assert all(c in "0123456789abcdef" for c in hex_part), "Should be valid hex chars"

    def test_none_request_id_produces_random(self):
        """None request_id should produce random correlation_id."""
        corr_1 = derive_correlation_id(None)
        corr_2 = derive_correlation_id(None)

        # Should be different (random generation)
        assert corr_1 != corr_2, "Random correlation_ids should be different"

        # Should still have correct format
        assert corr_1.startswith("mcp_"), "Random ID should have mcp_ prefix"
        assert len(corr_1) == 16, "Random ID should be 16 chars total"

    def test_empty_string_request_id_uses_deterministic_hash(self):
        """Empty string request_id should use deterministic hash."""
        corr_1 = derive_correlation_id("")
        corr_2 = derive_correlation_id("")

        # Empty string should hash deterministically
        assert corr_1 == corr_2, "Empty string should hash deterministically"

    def test_special_characters_in_request_id(self):
        """Request IDs with special characters should work."""
        request_ids = [
            "req-with-dashes",
            "req_with_underscores",
            "req/with/slashes",
            "req.with.dots",
            "req@with@at",
            "req:with:colons",
        ]

        for request_id in request_ids:
            corr_id = derive_correlation_id(request_id)
            assert corr_id.startswith("mcp_"), f"Should work with {request_id}"
            assert len(corr_id) == 16, f"Should have correct length for {request_id}"

    def test_unicode_request_id(self):
        """Request IDs with unicode characters should work."""
        request_id = "test-request-🚀-unicode"
        corr_1 = derive_correlation_id(request_id)
        corr_2 = derive_correlation_id(request_id)

        assert corr_1 == corr_2, "Unicode request_id should hash deterministically"


class TestMetadataIntegration:
    """Test integration of canonical IDs and deterministic correlation IDs."""

    def test_metadata_example(self):
        """Show complete metadata example with both features."""
        # Simulate MCP request
        request_id = "mcp-req-abc123"
        tool_name = "osiris.connections.list"  # Client uses legacy name

        # Server processing
        correlation_id = derive_correlation_id(request_id)
        canonical_tool = canonical_tool_id(tool_name)

        # Metadata that would be returned
        metadata = {
            "correlation_id": correlation_id,
            "tool": canonical_tool,
            "duration_ms": 125,
            "bytes_in": 45,
            "bytes_out": 1234,
        }

        # Verify determinism
        correlation_id_2 = derive_correlation_id(request_id)
        assert metadata["correlation_id"] == correlation_id_2, "Correlation ID should be deterministic"

        # Verify canonical mapping
        assert metadata["tool"] == "connections_list", "Tool should be canonical name"

    def test_all_tools_have_consistent_metadata(self):
        """All tools should produce consistent metadata structure."""
        all_aliases = list(CANONICAL_TOOL_IDS.keys())

        for alias in all_aliases:
            canonical_tool = canonical_tool_id(alias)
            request_id = f"test-{alias}"
            correlation_id = derive_correlation_id(request_id)

            # Metadata structure should be consistent
            assert isinstance(canonical_tool, str), f"{alias} should map to string"
            assert isinstance(correlation_id, str), f"{alias} should have string correlation_id"
            assert correlation_id.startswith("mcp_"), f"{alias} correlation_id should have mcp_ prefix"
