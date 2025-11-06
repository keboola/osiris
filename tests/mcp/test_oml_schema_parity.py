"""
Test OML schema parity between MCP and core implementation.
"""

import pytest

from osiris.mcp.tools.oml import OMLTools


class TestOMLSchemaParity:
    """Test OML schema consistency."""

    @pytest.fixture
    def oml_tools(self):
        """Create OML tools instance."""
        return OMLTools()

    @pytest.mark.asyncio
    async def test_schema_version_matches(self, oml_tools):
        """Test MCP schema version matches core OML version.

        Verifies both top-level version AND schema.version are present and match.
        This ensures jq '.version' and jq '.schema.version' both work.
        """
        result = await oml_tools.get_schema({})

        assert result["status"] == "success"

        # Test top-level version field (for jq '.version')
        assert result["version"] == "0.1.0"

        # Test nested schema.version field (for jq '.schema.version')
        assert result["schema"]["version"] == "0.1.0"

        # Verify both versions match
        assert result["version"] == result["schema"]["version"]

        # Verify against core OML schema if available
        try:
            from osiris.core.oml import OML_SCHEMA_VERSION

            assert result["version"] == OML_SCHEMA_VERSION
            assert result["schema"]["version"] == OML_SCHEMA_VERSION
        except ImportError:
            # Core OML module not available in test environment
            pass

    @pytest.mark.asyncio
    async def test_schema_structure(self, oml_tools):
        """Test schema has expected structure."""
        result = await oml_tools.get_schema({})

        schema = result["schema"]
        assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
        assert schema["version"] == "0.1.0"  # Schema version field
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema

        # Check required top-level fields
        required_fields = ["name", "oml_version", "steps"]
        for field in required_fields:
            assert field in schema["required"]

    @pytest.mark.asyncio
    async def test_schema_step_structure(self, oml_tools):
        """Test step schema structure."""
        result = await oml_tools.get_schema({})

        schema = result["schema"]
        step_schema = schema["properties"]["steps"]["items"]

        # Verify step properties
        assert step_schema["type"] == "object"
        assert "properties" in step_schema
        assert "id" in step_schema["properties"]
        assert "component" in step_schema["properties"]
        assert "mode" in step_schema["properties"]
        assert "config" in step_schema["properties"]

        # Verify required step fields
        assert "id" in step_schema["required"]
        assert "component" in step_schema["required"]
        assert "mode" in step_schema["required"]

    @pytest.mark.asyncio
    async def test_schema_connection_references(self, oml_tools):
        """Test schema supports connection references."""
        result = await oml_tools.get_schema({})

        schema = result["schema"]
        step_schema = schema["properties"]["steps"]["items"]

        # Connection should allow @ references
        conn_schema = step_schema["properties"].get("connection", {})
        if "pattern" in conn_schema:
            # Should allow @family.alias format
            assert "@" in conn_schema.get("pattern", "") or conn_schema.get("type") == "string"

    @pytest.mark.asyncio
    async def test_schema_validates_valid_oml(self, oml_tools):
        """Test schema validates correct OML."""
        valid_oml = """
name: test_pipeline
oml_version: "0.1.0"
steps:
  - id: extract
    component: mysql_extractor
    mode: read
    connection: "@mysql.source"
    config:
      query: "SELECT * FROM users"
"""
        result = await oml_tools.validate({"oml_content": valid_oml, "strict": True})

        assert result["valid"] is True or len(result["diagnostics"]) == 0

    @pytest.mark.asyncio
    async def test_schema_rejects_invalid_oml(self, oml_tools):
        """Test schema rejects invalid OML."""
        invalid_oml = """
name: test_pipeline
steps:
  - component: mysql_extractor
"""
        result = await oml_tools.validate({"oml_content": invalid_oml, "strict": True})

        assert result["valid"] is False
        assert len(result["diagnostics"]) > 0

        # Should identify missing required field
        diagnostics = result["diagnostics"]
        error_messages = [d["message"] for d in diagnostics if d["type"] == "error"]
        assert any("name" in msg.lower() or "required" in msg.lower() for msg in error_messages)

    @pytest.mark.asyncio
    async def test_schema_backward_compatibility(self, oml_tools):
        """Test schema maintains backward compatibility."""
        # Test v0.1.0 format is still valid
        legacy_oml = """
name: legacy_pipeline
oml_version: "0.1.0"
steps:
  - id: step1
    component: component1
    mode: read
    config: {}
"""
        result = await oml_tools.validate({"oml_content": legacy_oml})

        # Legacy format should still validate
        # (may have warnings but no errors)
        errors = [d for d in result["diagnostics"] if d["type"] == "error"]
        assert len(errors) == 0 or result["valid"] is True
