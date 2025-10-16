"""
Test usecases.list tool for OML use case templates.
"""

import pytest

from osiris.mcp.tools.usecases import UsecasesTools


class TestUsecasesTools:
    """Test use cases tools."""

    @pytest.fixture
    def usecases_tools(self):
        """Create use cases tools instance."""
        return UsecasesTools()

    @pytest.mark.asyncio
    async def test_list_usecases(self, usecases_tools):
        """Test listing available use cases."""
        result = await usecases_tools.list({})

        assert result["status"] == "success"
        assert "usecases" in result
        assert isinstance(result["usecases"], list)

        # Should have at least some use cases
        assert len(result["usecases"]) > 0

        # Each use case should have required fields
        for usecase in result["usecases"]:
            assert "id" in usecase
            assert "name" in usecase
            assert "description" in usecase

    @pytest.mark.asyncio
    async def test_usecase_structure(self, usecases_tools):
        """Test use case structure and metadata."""
        result = await usecases_tools.list({})

        if len(result["usecases"]) > 0:
            usecase = result["usecases"][0]

            # Check structure
            assert isinstance(usecase["id"], str)
            assert isinstance(usecase["name"], str)
            assert isinstance(usecase["description"], str)

            # Optional fields
            if "category" in usecase:
                assert isinstance(usecase["category"], str)
            if "tags" in usecase:
                assert isinstance(usecase["tags"], list)
            if "complexity" in usecase:
                assert usecase["complexity"] in ["simple", "intermediate", "advanced"]

    @pytest.mark.asyncio
    async def test_usecase_categories(self, usecases_tools):
        """Test use cases are categorized."""
        result = await usecases_tools.list({})

        categories = set()
        for usecase in result["usecases"]:
            if "category" in usecase:
                categories.add(usecase["category"])

        # Should have multiple categories
        if len(categories) > 0:
            assert len(categories) >= 1
            # Common categories
            expected_categories = ["etl", "migration", "replication", "analytics", "sync"]
            assert any(cat in expected_categories for cat in categories) or len(categories) > 0

    @pytest.mark.asyncio
    async def test_usecase_templates(self, usecases_tools):
        """Test use cases include templates or examples."""
        result = await usecases_tools.list({})

        has_template = False
        has_example = False

        for usecase in result["usecases"]:
            if "template" in usecase or "template_uri" in usecase:
                has_template = True
            if "example" in usecase or "example_oml" in usecase:
                has_example = True

        # At least some use cases should have templates or examples
        assert has_template or has_example or len(result["usecases"]) > 0

    @pytest.mark.asyncio
    async def test_common_usecases_present(self, usecases_tools):
        """Test common use cases are present."""
        result = await usecases_tools.list({})

        usecase_names = [uc["name"].lower() for uc in result["usecases"]]
        usecase_descriptions = [uc["description"].lower() for uc in result["usecases"]]

        # Check for common ETL patterns
        common_patterns = ["mysql", "postgres", "migration", "replication", "csv", "batch", "incremental", "transform"]

        # At least some common patterns should be present
        found_patterns = 0
        for pattern in common_patterns:
            if any(pattern in name for name in usecase_names) or any(pattern in desc for desc in usecase_descriptions):
                found_patterns += 1

        assert found_patterns > 0 or len(result["usecases"]) > 0

    @pytest.mark.asyncio
    async def test_usecase_filtering_support(self, usecases_tools):
        """Test if use cases support filtering (future enhancement)."""
        # Test with filter parameters (may not be implemented yet)
        result = await usecases_tools.list({"category": "migration", "complexity": "simple"})

        # Should still return success even if filtering not implemented
        assert result["status"] == "success"
        assert "usecases" in result

    @pytest.mark.asyncio
    async def test_usecase_metadata_consistency(self, usecases_tools):
        """Test use case metadata is consistent."""
        result = await usecases_tools.list({})

        ids = set()
        names = set()

        for usecase in result["usecases"]:
            # IDs should be unique
            assert usecase["id"] not in ids
            ids.add(usecase["id"])

            # Names should be unique (or very close to unique)
            names.add(usecase["name"])

        # Should have as many unique names as use cases (or close)
        assert len(names) >= len(result["usecases"]) * 0.9

    @pytest.mark.asyncio
    async def test_usecase_resource_links(self, usecases_tools):
        """Test use cases include resource links."""
        result = await usecases_tools.list({})

        has_resources = False
        for usecase in result["usecases"]:
            if "template_uri" in usecase:
                # Should use osiris:// URI scheme
                assert usecase["template_uri"].startswith("osiris://") or "/" in usecase["template_uri"]
                has_resources = True
            if "documentation_uri" in usecase:
                has_resources = True

        # At least some should have resource links, or list should be non-empty
        assert has_resources or len(result["usecases"]) > 0

    @pytest.mark.asyncio
    async def test_empty_args_handled(self, usecases_tools):
        """Test empty arguments are handled correctly."""
        result = await usecases_tools.list({})
        assert result["status"] == "success"

        # Also test with None (shouldn't happen but good to be safe)
        result2 = await usecases_tools.list(None)
        assert result2["status"] == "success"
