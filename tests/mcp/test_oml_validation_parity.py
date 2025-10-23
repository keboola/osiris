"""
Test OML validation parity between MCP and CLI.

This test ensures that the MCP server and CLI validator return identical validation
results for the same OML content. This is critical for consistent user experience
regardless of whether validation happens via Claude Desktop or command-line.
"""

import pytest
import yaml  # noqa: PLC0415

from osiris.core.oml_validator import OMLValidator
from osiris.mcp.tools.oml import OMLTools


class TestOMLValidationParity:
    """Test that MCP and CLI validation agree on all cases."""

    @pytest.fixture
    def mcp_tools(self):
        """Create OMLTools instance for MCP testing."""
        return OMLTools()

    @pytest.fixture
    def cli_validator(self):
        """Create OMLValidator instance for CLI testing."""
        return OMLValidator()

    @pytest.mark.asyncio
    async def test_valid_pipeline_parity(self, mcp_tools, cli_validator):
        """Both MCP and CLI should accept valid OML v0.1.0 pipelines."""
        valid_oml = """
oml_version: "0.1.0"
name: test-pipeline
steps:
  - id: extract
    component: mysql.extractor
    mode: read
    config:
      connection: "@mysql.default"
      query: SELECT * FROM users
  - id: write
    component: filesystem.csv_writer
    mode: write
    needs: [extract]
    config:
      path: /tmp/output.csv
"""
        # Test via MCP
        mcp_result = await mcp_tools.validate({"oml_content": valid_oml, "strict": True})

        # Test via CLI
        oml_data = yaml.safe_load(valid_oml)
        is_valid, errors, warnings = cli_validator.validate(oml_data)

        # Both should agree on validity
        assert mcp_result["valid"] is True, f"MCP validation failed: {mcp_result.get('diagnostics')}"
        assert is_valid is True, f"CLI validation failed: {errors}"

        # Both should have zero errors
        assert mcp_result["summary"]["errors"] == 0
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_missing_oml_version_parity(self, mcp_tools, cli_validator):
        """Both should reject pipelines missing oml_version."""
        invalid_oml = """
name: test-pipeline
steps:
  - id: extract
    component: mysql.extractor
    mode: read
    config:
      connection: "@mysql.default"
      query: SELECT * FROM users
"""
        # Test via MCP
        mcp_result = await mcp_tools.validate({"oml_content": invalid_oml, "strict": True})

        # Test via CLI
        oml_data = yaml.safe_load(invalid_oml)
        is_valid, errors, warnings = cli_validator.validate(oml_data)

        # Both should reject
        assert mcp_result["valid"] is False
        assert is_valid is False

        # Both should report missing oml_version
        mcp_errors = [d for d in mcp_result["diagnostics"] if d["type"] == "error"]
        assert any("oml_version" in d.get("message", "") or "version" in d.get("message", "") for d in mcp_errors)
        assert any(e["type"] == "missing_required_key" and "oml_version" in e["message"] for e in errors)

    @pytest.mark.asyncio
    async def test_missing_mode_in_step_parity(self, mcp_tools, cli_validator):
        """Both should reject steps missing required 'mode' field."""
        invalid_oml = """
oml_version: "0.1.0"
name: test-pipeline
steps:
  - id: extract
    component: mysql.extractor
    config:
      connection: "@mysql.default"
      query: SELECT * FROM users
"""
        # Test via MCP
        mcp_result = await mcp_tools.validate({"oml_content": invalid_oml, "strict": True})

        # Test via CLI
        oml_data = yaml.safe_load(invalid_oml)
        is_valid, errors, warnings = cli_validator.validate(oml_data)

        # Both should reject
        assert mcp_result["valid"] is False
        assert is_valid is False

        # Both should report missing mode
        mcp_errors = [d for d in mcp_result["diagnostics"] if d["type"] == "error"]
        assert any("mode" in d.get("message", "") for d in mcp_errors)
        assert any(e["type"] == "missing_step_field" and "mode" in e["message"] for e in errors)

    @pytest.mark.asyncio
    async def test_forbidden_version_key_parity(self, mcp_tools, cli_validator):
        """Both should reject pipelines using 'version' instead of 'oml_version'."""
        invalid_oml = """
version: "0.1.0"
name: test-pipeline
steps:
  - id: extract
    component: mysql.extractor
    mode: read
    config:
      connection: "@mysql.default"
      query: SELECT * FROM users
"""
        # Test via MCP
        mcp_result = await mcp_tools.validate({"oml_content": invalid_oml, "strict": True})

        # Test via CLI
        oml_data = yaml.safe_load(invalid_oml)
        is_valid, errors, warnings = cli_validator.validate(oml_data)

        # Both should reject
        assert mcp_result["valid"] is False
        assert is_valid is False

        # Both should report the version/oml_version issues
        mcp_errors = [d for d in mcp_result["diagnostics"] if d["type"] == "error"]
        # MCP should catch missing oml_version
        assert any("version" in d.get("message", "").lower() for d in mcp_errors)

        # CLI should catch both forbidden 'version' and missing 'oml_version'
        assert any(e["type"] == "forbidden_key" and "version" in e["message"] for e in errors)
        assert any(e["type"] == "missing_required_key" and "oml_version" in e["message"] for e in errors)

    @pytest.mark.asyncio
    async def test_user_reported_pipeline_parity(self, mcp_tools, cli_validator):
        """Test the actual pipeline from user's Claude Desktop session that triggered the bug report.

        This pipeline has two critical errors:
        1. Uses 'version' instead of 'oml_version'
        2. Missing 'mode' field in step
        """
        user_pipeline = """
version: "0.1.0"
name: "top_movies_by_reviews"
steps:
  - id: extract_movies
    component: "mysql.extractor"
    config:
      connection: "@mysql.db_movies"
      table: "movies"
"""
        # Test via MCP
        mcp_result = await mcp_tools.validate({"oml_content": user_pipeline, "strict": True})

        # Test via CLI
        oml_data = yaml.safe_load(user_pipeline)
        is_valid, errors, warnings = cli_validator.validate(oml_data)

        # Both MUST reject this invalid pipeline
        assert mcp_result["valid"] is False, "MCP should reject pipeline with version/mode errors"
        assert is_valid is False, "CLI should reject pipeline with version/mode errors"

        # Both should have multiple errors
        mcp_error_count = mcp_result["summary"]["errors"]
        cli_error_count = len(errors)

        assert mcp_error_count > 0, "MCP should report errors"
        assert cli_error_count > 0, "CLI should report errors"

        # Extract error types from MCP
        mcp_errors = [d for d in mcp_result["diagnostics"] if d["type"] == "error"]
        mcp_error_messages = [d.get("message", "") for d in mcp_errors]

        # Both should detect version-related issues
        mcp_has_version_error = any("version" in msg.lower() for msg in mcp_error_messages)
        cli_has_version_error = any(
            (e["type"] == "forbidden_key" and "version" in e["message"])
            or (e["type"] == "missing_required_key" and "oml_version" in e["message"])
            for e in errors
        )

        assert mcp_has_version_error, f"MCP should detect version error. Errors: {mcp_error_messages}"
        assert cli_has_version_error, f"CLI should detect version error. Errors: {errors}"

        # Both should detect missing mode
        mcp_has_mode_error = any("mode" in msg for msg in mcp_error_messages)
        cli_has_mode_error = any(e["type"] == "missing_step_field" and "mode" in e["message"] for e in errors)

        assert mcp_has_mode_error, f"MCP should detect missing mode. Errors: {mcp_error_messages}"
        assert cli_has_mode_error, f"CLI should detect missing mode. Errors: {errors}"

    @pytest.mark.asyncio
    async def test_invalid_mode_value_parity(self, mcp_tools, cli_validator):
        """Both should reject steps with invalid mode values."""
        invalid_oml = """
oml_version: "0.1.0"
name: test-pipeline
steps:
  - id: extract
    component: mysql.extractor
    mode: invalid_mode
    config:
      connection: "@mysql.default"
      query: SELECT * FROM users
"""
        # Test via MCP
        mcp_result = await mcp_tools.validate({"oml_content": invalid_oml, "strict": True})

        # Test via CLI
        oml_data = yaml.safe_load(invalid_oml)
        is_valid, errors, warnings = cli_validator.validate(oml_data)

        # Both should reject
        assert mcp_result["valid"] is False
        assert is_valid is False

        # Both should report invalid mode
        mcp_errors = [d for d in mcp_result["diagnostics"] if d["type"] == "error"]
        assert any("mode" in d.get("message", "") and "invalid" in d.get("message", "").lower() for d in mcp_errors)
        assert any(e["type"] == "invalid_mode" for e in errors)

    @pytest.mark.asyncio
    async def test_duplicate_step_ids_parity(self, mcp_tools, cli_validator):
        """Both should reject pipelines with duplicate step IDs."""
        invalid_oml = """
oml_version: "0.1.0"
name: test-pipeline
steps:
  - id: step1
    component: mysql.extractor
    mode: read
    config:
      connection: "@mysql.default"
      query: SELECT * FROM users
  - id: step1
    component: filesystem.csv_writer
    mode: write
    config:
      path: /tmp/output.csv
"""
        # Test via MCP
        mcp_result = await mcp_tools.validate({"oml_content": invalid_oml, "strict": True})

        # Test via CLI
        oml_data = yaml.safe_load(invalid_oml)
        is_valid, errors, warnings = cli_validator.validate(oml_data)

        # Both should reject
        assert mcp_result["valid"] is False
        assert is_valid is False

        # Both should report duplicate ID
        mcp_errors = [d for d in mcp_result["diagnostics"] if d["type"] == "error"]
        assert any("duplicate" in d.get("message", "").lower() and "step1" in d.get("message", "") for d in mcp_errors)
        assert any(e["type"] == "duplicate_id" for e in errors)

    @pytest.mark.asyncio
    async def test_empty_steps_parity(self, mcp_tools, cli_validator):
        """Both should reject pipelines with no steps."""
        invalid_oml = """
oml_version: "0.1.0"
name: test-pipeline
steps: []
"""
        # Test via MCP
        mcp_result = await mcp_tools.validate({"oml_content": invalid_oml, "strict": True})

        # Test via CLI
        oml_data = yaml.safe_load(invalid_oml)
        is_valid, errors, warnings = cli_validator.validate(oml_data)

        # Both should reject (empty steps is an error)
        assert mcp_result["valid"] is False
        assert is_valid is False

        # Both should report empty/no steps
        mcp_diagnostics = mcp_result["diagnostics"]
        # MCP might report as warning or error
        assert any("step" in d.get("message", "").lower() for d in mcp_diagnostics)
        assert any(e["type"] == "empty_steps" for e in errors)

    @pytest.mark.asyncio
    async def test_invalid_connection_ref_parity(self, mcp_tools, cli_validator):
        """Both should reject invalid connection reference format."""
        invalid_oml = """
oml_version: "0.1.0"
name: test-pipeline
steps:
  - id: extract
    component: mysql.extractor
    mode: read
    config:
      connection: "@invalid"
      query: SELECT * FROM users
"""
        # Test via MCP
        mcp_result = await mcp_tools.validate({"oml_content": invalid_oml, "strict": True})

        # Test via CLI
        oml_data = yaml.safe_load(invalid_oml)
        is_valid, errors, warnings = cli_validator.validate(oml_data)

        # Both should reject
        assert mcp_result["valid"] is False
        assert is_valid is False

        # Both should report connection reference error
        mcp_errors = [d for d in mcp_result["diagnostics"] if d["type"] == "error"]
        assert any("connection" in d.get("message", "").lower() for d in mcp_errors)
        assert any(e["type"] == "invalid_connection_ref" for e in errors)

    @pytest.mark.asyncio
    async def test_yaml_parse_error_parity(self, mcp_tools, cli_validator):
        """Both should handle YAML parse errors gracefully."""
        # Invalid YAML with mismatched indentation that breaks YAML parser
        invalid_yaml = """
oml_version: "0.1.0"
name: test
steps:
  - id: test
    component: mysql
      bad_indent: value
"""
        # Test via MCP - it should handle YAML errors
        mcp_result = await mcp_tools.validate({"oml_content": invalid_yaml, "strict": True})

        # The CLI validator expects valid YAML (dict), so we test with pytest.raises
        with pytest.raises(yaml.YAMLError):
            yaml.safe_load(invalid_yaml)

        # MCP should handle YAML errors and return diagnostic
        assert mcp_result["valid"] is False
        assert any("YAML" in d.get("message", "") or "parse" in d.get("message", "") for d in mcp_result["diagnostics"])
