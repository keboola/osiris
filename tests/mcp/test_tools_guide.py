"""
Test guide.start tool for OML authoring guidance.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

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
        result = await guide_tools.start({
            "intent": "I want to copy data from MySQL to PostgreSQL"
        })

        assert result["status"] == "success"
        assert "next_steps" in result
        assert len(result["next_steps"]) > 0
        assert "recommendations" in result

    @pytest.mark.asyncio
    async def test_guide_with_connections(self, guide_tools):
        """Test guide with known connections."""
        result = await guide_tools.start({
            "intent": "Extract customer data",
            "known_connections": ["@mysql.prod", "@postgres.warehouse"]
        })

        assert result["status"] == "success"
        assert "next_steps" in result

        # Should suggest using known connections
        steps_text = str(result["next_steps"])
        assert any(conn in steps_text for conn in ["mysql", "postgres", "connection"])

    @pytest.mark.asyncio
    async def test_guide_with_discovery(self, guide_tools):
        """Test guide when discovery has been performed."""
        result = await guide_tools.start({
            "intent": "Build ETL pipeline",
            "known_connections": ["@mysql.source"],
            "has_discovery": True
        })

        assert result["status"] == "success"
        # Should acknowledge discovery and suggest next steps
        assert "discovery" in str(result).lower() or \
               "schema" in str(result).lower() or \
               len(result["next_steps"]) > 0

    @pytest.mark.asyncio
    async def test_guide_with_previous_oml(self, guide_tools):
        """Test guide with previous OML draft."""
        result = await guide_tools.start({
            "intent": "Fix validation errors",
            "has_previous_oml": True,
            "has_error_report": True
        })

        assert result["status"] == "success"
        assert "next_steps" in result

        # Should suggest validation or error fixing
        result_text = str(result).lower()
        assert "validat" in result_text or "error" in result_text or \
               "fix" in result_text

    @pytest.mark.asyncio
    async def test_guide_empty_intent(self, guide_tools):
        """Test guide with empty intent."""
        result = await guide_tools.start({
            "intent": ""
        })

        assert result["status"] == "success"
        assert "next_steps" in result
        # Should provide general guidance
        assert len(result["next_steps"]) > 0

    @pytest.mark.asyncio
    async def test_guide_complex_scenario(self, guide_tools):
        """Test guide with complex scenario."""
        result = await guide_tools.start({
            "intent": "Migrate all customer and order data with transformations",
            "known_connections": ["@mysql.legacy", "@postgres.modern"],
            "has_discovery": True,
            "has_previous_oml": True,
            "has_error_report": False
        })

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
        result1 = await guide_tools.start({
            "intent": "Build pipeline",
            "known_connections": []
        })

        # Has connections but no discovery - should suggest discovery
        result2 = await guide_tools.start({
            "intent": "Build pipeline",
            "known_connections": ["@mysql.db"],
            "has_discovery": False
        })

        # Has everything - should suggest OML creation
        result3 = await guide_tools.start({
            "intent": "Build pipeline",
            "known_connections": ["@mysql.db"],
            "has_discovery": True
        })

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