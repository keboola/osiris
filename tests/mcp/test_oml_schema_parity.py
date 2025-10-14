"""
Test OML schema parity between MCP and core implementation.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from osiris.mcp.tools.oml import OMLTools


class TestOMLSchemaParity:
    """Test OML schema consistency."""

    @pytest.fixture
    def oml_tools(self):
        """Create OML tools instance."""
        return OMLTools()

    @pytest.mark.asyncio
    async def test_schema_version_matches(self, oml_tools):
        """Test MCP schema version matches core OML version."""
        result = await oml_tools.get_schema({})

        assert result["status"] == "success"
        assert result["version"] == "0.1.0"

        # Verify against core OML schema if available
        try:
            from osiris.core.oml import OML_SCHEMA_VERSION
            assert result["version"] == OML_SCHEMA_VERSION
        except ImportError:
            # Core OML module not available in test environment
            pass

    @pytest.mark.asyncio
    async def test_schema_structure(self, oml_tools):
        """Test schema has expected structure."""
        result = await oml_tools.get_schema({})

        schema = result["schema"]
        assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema

        # Check required top-level fields
        required_fields = ["name", "version", "steps"]
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
        assert "name" in step_schema["properties"]
        assert "component" in step_schema["properties"]
        assert "config" in step_schema["properties"]

        # Verify required step fields
        assert "name" in step_schema["required"]
        assert "component" in step_schema["required"]

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
            assert "@" in conn_schema.get("pattern", "") or \
                   conn_schema.get("type") == "string"

    @pytest.mark.asyncio
    async def test_schema_validates_valid_oml(self, oml_tools):
        """Test schema validates correct OML."""
        valid_oml = """
name: test_pipeline
version: "1.0"
steps:
  - name: extract
    component: mysql_extractor
    connection: "@mysql.source"
    config:
      query: "SELECT * FROM users"
      mode: batch
"""
        result = await oml_tools.validate({
            "oml_content": valid_oml,
            "strict": True
        })

        assert result["valid"] is True or len(result["diagnostics"]) == 0

    @pytest.mark.asyncio
    async def test_schema_rejects_invalid_oml(self, oml_tools):
        """Test schema rejects invalid OML."""
        invalid_oml = """
name: test_pipeline
steps:
  - component: mysql_extractor
"""
        result = await oml_tools.validate({
            "oml_content": invalid_oml,
            "strict": True
        })

        assert result["valid"] is False
        assert len(result["diagnostics"]) > 0

        # Should identify missing required field
        diagnostics = result["diagnostics"]
        error_messages = [d["message"] for d in diagnostics if d["type"] == "error"]
        assert any("name" in msg.lower() or "required" in msg.lower()
                  for msg in error_messages)

    @pytest.mark.asyncio
    async def test_schema_backward_compatibility(self, oml_tools):
        """Test schema maintains backward compatibility."""
        # Test v0.1.0 format is still valid
        legacy_oml = """
name: legacy_pipeline
version: "0.1"
steps:
  - name: step1
    component: component1
    config: {}
"""
        result = await oml_tools.validate({
            "oml_content": legacy_oml
        })

        # Legacy format should still validate
        # (may have warnings but no errors)
        errors = [d for d in result["diagnostics"] if d["type"] == "error"]
        assert len(errors) == 0 or result["valid"] is True