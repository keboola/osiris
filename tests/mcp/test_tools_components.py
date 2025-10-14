"""
Test MCP components tools.
"""

import pytest
from unittest.mock import patch, MagicMock

from osiris.mcp.tools.components import ComponentsTools


class TestComponentsTools:
    """Test components.list tool."""

    @pytest.fixture
    def components_tools(self):
        """Create ComponentsTools instance."""
        return ComponentsTools()

    @pytest.mark.asyncio
    async def test_components_list(self, components_tools):
        """Test listing components."""
        # Mock component specs
        mock_specs = {
            "mysql.extractor": {
                "name": "mysql.extractor",
                "version": "1.0.0",
                "description": "Extract data from MySQL",
                "tags": ["database", "sql", "extractor"],
                "capabilities": {
                    "modes": ["read"],
                    "features": ["batch"]
                },
                "config_schema": {
                    "type": "object",
                    "required": ["connection", "query"],
                    "properties": {
                        "connection": {"type": "string"},
                        "query": {"type": "string"},
                        "timeout": {"type": "integer", "default": 30}
                    }
                },
                "examples": [
                    {
                        "description": "Extract all users",
                        "config": {
                            "connection": "@mysql.default",
                            "query": "SELECT * FROM users"
                        }
                    }
                ]
            },
            "supabase.writer": {
                "name": "supabase.writer",
                "version": "1.0.0",
                "description": "Write data to Supabase",
                "tags": ["database", "postgresql", "writer"],
                "capabilities": {
                    "modes": ["write"],
                    "features": ["batch", "upsert"]
                },
                "config_schema": {
                    "type": "object",
                    "required": ["connection", "table"],
                    "properties": {
                        "connection": {"type": "string"},
                        "table": {"type": "string"},
                        "mode": {"type": "string", "default": "append"}
                    }
                }
            },
            "duckdb.processor": {
                "name": "duckdb.processor",
                "version": "1.0.0",
                "description": "Process data with DuckDB",
                "tags": ["sql", "processor", "transform"],
                "capabilities": {
                    "modes": ["transform"],
                    "features": ["sql", "analytics"]
                },
                "config_schema": {
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string"}
                    }
                }
            }
        }

        mock_registry = MagicMock()
        mock_registry.load_specs.return_value = mock_specs

        with patch.object(components_tools, '_get_registry',
                         return_value=mock_registry):
            result = await components_tools.list({})

            assert result["status"] == "success"
            assert result["total_count"] == 3
            assert "components" in result

            components = result["components"]
            assert "extractors" in components
            assert "writers" in components
            assert "processors" in components

            # Check component categorization
            assert len(components["extractors"]) == 1
            assert len(components["writers"]) == 1
            assert len(components["processors"]) == 1

            # Verify extractor details
            extractor = components["extractors"][0]
            assert extractor["name"] == "mysql.extractor"
            assert extractor["version"] == "1.0.0"
            assert extractor["description"] == "Extract data from MySQL"
            assert extractor["tags"] == ["database", "sql", "extractor"]
            assert extractor["required_fields"] == ["connection", "query"]
            assert extractor["optional_fields"] == ["timeout"]
            assert len(extractor["examples"]) == 1

    @pytest.mark.asyncio
    async def test_components_list_empty(self, components_tools):
        """Test listing components when registry is empty."""
        mock_registry = MagicMock()
        mock_registry.load_specs.return_value = {}

        with patch.object(components_tools, '_get_registry',
                         return_value=mock_registry):
            result = await components_tools.list({})

            assert result["status"] == "success"
            assert result["total_count"] == 0
            assert result["components"]["extractors"] == []
            assert result["components"]["writers"] == []
            assert result["components"]["processors"] == []
            assert result["components"]["other"] == []

    @pytest.mark.asyncio
    async def test_components_list_with_other_category(self, components_tools):
        """Test components that don't fit standard categories."""
        mock_specs = {
            "custom.component": {
                "name": "custom.component",
                "version": "1.0.0",
                "description": "Custom component",
                "tags": ["custom"],
                "capabilities": {},
                "config_schema": {
                    "type": "object",
                    "properties": {}
                }
            }
        }

        mock_registry = MagicMock()
        mock_registry.load_specs.return_value = mock_specs

        with patch.object(components_tools, '_get_registry',
                         return_value=mock_registry):
            result = await components_tools.list({})

            assert result["total_count"] == 1
            assert len(result["components"]["other"]) == 1
            assert result["components"]["other"][0]["name"] == "custom.component"