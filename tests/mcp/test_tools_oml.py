"""
Test MCP OML tools (schema.get, validate, save).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from osiris.mcp.errors import OsirisError
from osiris.mcp.tools.oml import OMLTools


class TestOMLTools:
    """Test OML tools."""

    @pytest.fixture
    def oml_tools(self):
        """Create OMLTools instance."""
        resolver = MagicMock()
        return OMLTools(resolver)

    @pytest.mark.asyncio
    async def test_oml_schema_get(self, oml_tools):
        """Test getting OML schema."""
        result = await oml_tools.schema_get({})

        assert result["status"] == "success"
        assert result["version"] == "0.1.0"
        assert result["schema_uri"] == "osiris://mcp/schemas/oml/v0.1.0.json"
        assert "schema" in result

        schema = result["schema"]
        assert schema["type"] == "object"
        assert schema["required"] == ["oml_version", "name", "steps"]
        assert "properties" in schema

    @pytest.mark.asyncio
    async def test_validate_oml_valid(self, oml_tools):
        """Test validating valid OML content."""
        valid_oml = """
oml_version: "0.1.0"
name: test_pipeline
steps:
  - id: extract
    component: mysql.extractor
    mode: read
    config:
      connection: @mysql.default
      query: SELECT * FROM users
"""
        result = await oml_tools.validate({"oml_content": valid_oml, "strict": True})

        assert result["status"] == "success"
        assert result["valid"] is True
        assert "diagnostics" in result
        assert result["summary"]["errors"] == 0

    @pytest.mark.asyncio
    async def test_validate_oml_invalid_yaml(self, oml_tools):
        """Test validating invalid YAML."""
        invalid_yaml = """
version: 0.1.0
name: test
  bad_indent
"""
        result = await oml_tools.validate({"oml_content": invalid_yaml})

        assert result["status"] == "success"
        assert result["valid"] is False
        assert len(result["diagnostics"]) > 0
        assert result["diagnostics"][0]["type"] == "error"
        assert "YAML parse error" in result["diagnostics"][0]["message"]

    @pytest.mark.asyncio
    async def test_validate_oml_missing_required_fields(self, oml_tools):
        """Test validating OML missing required fields."""
        incomplete_oml = """
name: test_pipeline
"""
        result = await oml_tools.validate({"oml_content": incomplete_oml})

        assert result["valid"] is False
        assert any("Missing required" in d["message"] and "oml_version" in d["message"] for d in result["diagnostics"])
        assert any("Missing required" in d["message"] and "steps" in d["message"] for d in result["diagnostics"])

    @pytest.mark.asyncio
    async def test_validate_oml_no_content(self, oml_tools):
        """Test validation without OML content."""
        with pytest.raises(OsirisError) as exc_info:
            await oml_tools.validate({})

        assert exc_info.value.family.value == "SCHEMA"
        assert "oml_content is required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_save_oml_success(self, oml_tools):
        """Test saving OML draft."""
        oml_tools.resolver.write_resource = AsyncMock(return_value=True)

        result = await oml_tools.save(
            {"oml_content": "version: 0.1.0\nname: test", "session_id": "test_session", "filename": "test.yaml"}
        )

        assert result["status"] == "success"
        assert result["saved"] is True
        assert result["filename"] == "test.yaml"
        assert result["session_id"] == "test_session"
        assert result["uri"] == "osiris://mcp/drafts/oml/test.yaml"

        # Verify write was called
        oml_tools.resolver.write_resource.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_oml_auto_filename(self, oml_tools):
        """Test saving OML with auto-generated filename."""
        oml_tools.resolver.write_resource = AsyncMock(return_value=True)

        with patch("osiris.mcp.tools.oml.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "20251014_120000"

            result = await oml_tools.save({"oml_content": "version: 0.1.0", "session_id": "sess123"})

            assert result["saved"] is True
            assert result["filename"] == "sess123_20251014_120000.yaml"
            assert "sess123" in result["uri"]

    @pytest.mark.asyncio
    async def test_save_oml_missing_content(self, oml_tools):
        """Test saving without OML content."""
        with pytest.raises(OsirisError) as exc_info:
            await oml_tools.save({"session_id": "test"})

        assert exc_info.value.family.value == "SCHEMA"
        assert "oml_content is required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_save_oml_missing_session_id(self, oml_tools):
        """Test saving without session_id."""
        with pytest.raises(OsirisError) as exc_info:
            await oml_tools.save({"oml_content": "test"})

        assert exc_info.value.family.value == "SCHEMA"
        assert "session_id is required" in str(exc_info.value)
