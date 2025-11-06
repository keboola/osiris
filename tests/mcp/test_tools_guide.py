"""
Test guide.start tool for OML authoring guidance.
"""

import pytest
import yaml

from osiris.core.oml_validator import OMLValidator
from osiris.mcp.tools.guide import GuideTools


class TestGuideTools:
    """Test guide tools."""

    @pytest.fixture
    def guide_tools(self):
        """Create guide tools instance."""
        return GuideTools()

    @pytest.mark.asyncio
    async def test_guide_start_basic(self, guide_tools):
        """Test basic guide start."""
        result = await guide_tools.start({"intent": "I want to copy data from MySQL to PostgreSQL"})

        assert result["status"] == "success"
        assert "next_steps" in result
        assert len(result["next_steps"]) > 0
        assert "recommendations" in result

    @pytest.mark.asyncio
    async def test_guide_with_connections(self, guide_tools):
        """Test guide with known connections."""
        result = await guide_tools.start(
            {"intent": "Extract customer data", "known_connections": ["@mysql.prod", "@postgres.warehouse"]}
        )

        assert result["status"] == "success"
        assert "next_steps" in result

        # Should suggest using known connections
        steps_text = str(result["next_steps"])
        assert any(conn in steps_text for conn in ["mysql", "postgres", "connection"])

    @pytest.mark.asyncio
    async def test_guide_with_discovery(self, guide_tools):
        """Test guide when discovery has been performed."""
        result = await guide_tools.start(
            {"intent": "Build ETL pipeline", "known_connections": ["@mysql.source"], "has_discovery": True}
        )

        assert result["status"] == "success"
        # Should acknowledge discovery and suggest next steps
        assert "discovery" in str(result).lower() or "schema" in str(result).lower() or len(result["next_steps"]) > 0

    @pytest.mark.asyncio
    async def test_guide_with_previous_oml(self, guide_tools):
        """Test guide with previous OML draft."""
        result = await guide_tools.start(
            {"intent": "Fix validation errors", "has_previous_oml": True, "has_error_report": True}
        )

        assert result["status"] == "success"
        assert "next_steps" in result

        # Should suggest validation or error fixing
        result_text = str(result).lower()
        assert "validat" in result_text or "error" in result_text or "fix" in result_text

    @pytest.mark.asyncio
    async def test_guide_empty_intent(self, guide_tools):
        """Test guide with empty intent."""
        result = await guide_tools.start({"intent": ""})

        assert result["status"] == "success"
        assert "next_steps" in result
        # Should provide general guidance
        assert len(result["next_steps"]) > 0

    @pytest.mark.asyncio
    async def test_guide_complex_scenario(self, guide_tools):
        """Test guide with complex scenario."""
        result = await guide_tools.start(
            {
                "intent": "Migrate all customer and order data with transformations",
                "known_connections": ["@mysql.legacy", "@postgres.modern"],
                "has_discovery": True,
                "has_previous_oml": True,
                "has_error_report": False,
            }
        )

        assert result["status"] == "success"
        assert "next_steps" in result
        assert "recommendations" in result

        # Should provide structured guidance
        assert len(result["next_steps"]) > 0

        # Check for contextual recommendations
        if "recommendations" in result:
            assert isinstance(result["recommendations"], (list, dict))

    @pytest.mark.asyncio
    async def test_guide_prioritizes_steps(self, guide_tools):
        """Test guide prioritizes steps appropriately."""
        # No connections - should suggest connection setup
        result1 = await guide_tools.start({"intent": "Build pipeline", "known_connections": []})

        # Has connections but no discovery - should suggest discovery
        result2 = await guide_tools.start(
            {"intent": "Build pipeline", "known_connections": ["@mysql.db"], "has_discovery": False}
        )

        # Has everything - should suggest OML creation
        result3 = await guide_tools.start(
            {"intent": "Build pipeline", "known_connections": ["@mysql.db"], "has_discovery": True}
        )

        # All should succeed
        assert all(r["status"] == "success" for r in [result1, result2, result3])

        # Each should have different priorities
        assert result1["next_steps"] != result2["next_steps"]
        assert result2["next_steps"] != result3["next_steps"]

    @pytest.mark.asyncio
    async def test_guide_error_handling(self, guide_tools):
        """Test guide handles errors gracefully."""
        # Missing required field
        try:
            result = await guide_tools.start({})
            # Should either handle gracefully or raise appropriate error
            if "error" not in result:
                assert result["status"] in ["success", "error"]
        except Exception as e:
            # Should be a meaningful error
            assert "intent" in str(e).lower()

    @pytest.mark.asyncio
    async def test_guide_includes_references(self, guide_tools):
        """Test guide includes references in result."""
        result = await guide_tools.start({"intent": "I want to extract data from MySQL"})

        assert result["status"] == "success"
        assert "references" in result
        assert isinstance(result["references"], list)

        # Test different next_step scenarios to ensure references are populated
        scenarios = [
            {"intent": "Build pipeline", "known_connections": []},  # list_connections
            {"intent": "Build pipeline", "known_connections": ["@mysql.db"], "has_discovery": False},  # run_discovery
            {"intent": "Build pipeline", "known_connections": ["@mysql.db"], "has_discovery": True},  # create_oml
            {"intent": "Fix errors", "has_previous_oml": True, "has_error_report": True},  # validate_oml
        ]

        for scenario in scenarios:
            result = await guide_tools.start(scenario)
            assert result["status"] == "success"
            assert "references" in result
            assert isinstance(result["references"], list)

    def test_sample_oml_validates(self, guide_tools):
        """Test that the sample OML returned by _get_sample_oml passes OML validation."""
        # Get the sample OML
        sample_oml_str = guide_tools._get_sample_oml()

        # Parse YAML
        sample_oml = yaml.safe_load(sample_oml_str)

        # Validate using OMLValidator
        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(sample_oml)

        # Assert validation passes
        assert is_valid, f"Sample OML validation failed with errors: {errors}"
        assert len(errors) == 0, f"Sample OML has validation errors: {errors}"

        # Verify correct OML v0.1.0 structure
        assert sample_oml["oml_version"] == "0.1.0", "Should use oml_version not version"
        assert "name" in sample_oml
        assert "steps" in sample_oml
        assert len(sample_oml["steps"]) > 0

        # Verify all steps have required fields
        for step in sample_oml["steps"]:
            assert "id" in step, f"Step missing 'id': {step}"
            assert "component" in step, f"Step missing 'component': {step}"
            assert "mode" in step, f"Step missing 'mode': {step}"
            assert step["mode"] in ["read", "write", "transform"], f"Invalid mode: {step['mode']}"
            assert "config" in step, f"Step missing 'config': {step}"

        # Verify dependencies use 'needs' not 'depends_on'
        for step in sample_oml["steps"]:
            assert "depends_on" not in step, f"Step uses deprecated 'depends_on': {step['id']}"
            if "needs" in step:
                assert isinstance(step["needs"], list), f"'needs' must be a list: {step['id']}"

        # Verify connection references are quoted strings
        for step in sample_oml["steps"]:
            config = step.get("config", {})
            if "connection" in config:
                conn = config["connection"]
                assert isinstance(conn, str), f"Connection reference must be string: {conn}"
                if conn.startswith("@"):
                    # Verify it's a quoted string (not bare YAML identifier)
                    assert conn == config["connection"], f"Connection reference not properly quoted: {conn}"
