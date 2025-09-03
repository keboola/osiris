"""Tests for components list JSON output."""

import json
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from osiris.cli.components_cmd import list_components
from osiris.components.registry import ComponentRegistry


class TestComponentsListJSON:
    """Test suite for components list JSON output."""

    def test_list_components_json_output(self):
        """Test that list_components outputs valid JSON when --json is used."""
        # Create mock registry with test components
        mock_registry = MagicMock(spec=ComponentRegistry)
        mock_registry.list_components.return_value = [
            {
                "name": "mysql.extractor",
                "version": "1.0.0",
                "modes": ["extract", "discover"],
                "description": "Extract data from MySQL databases...",
            },
            {
                "name": "mysql.writer",
                "version": "1.0.0",
                "modes": ["write", "discover"],
                "description": "Write data to MySQL databases...",
            },
        ]

        # Capture stdout
        captured_output = StringIO()

        with patch("osiris.cli.components_cmd.get_registry", return_value=mock_registry), patch(
            "sys.stdout", captured_output
        ):
            list_components(mode="all", as_json=True)

        # Parse the output as JSON
        output = captured_output.getvalue()
        assert output.strip() != ""  # Should have output

        try:
            data = json.loads(output)
        except json.JSONDecodeError as e:
            pytest.fail(f"Output is not valid JSON: {e}\nOutput: {output}")

        # Verify structure
        assert isinstance(data, list)
        assert len(data) == 2

        # Check first component
        assert data[0]["name"] == "mysql.extractor"
        assert data[0]["version"] == "1.0.0"
        assert data[0]["modes"] == ["extract", "discover"]
        assert "..." not in data[0]["description"]  # Ellipsis should be removed

        # Check second component
        assert data[1]["name"] == "mysql.writer"
        assert data[1]["modes"] == ["write", "discover"]

    def test_list_components_json_empty(self):
        """Test that empty component list outputs empty JSON array."""
        mock_registry = MagicMock(spec=ComponentRegistry)
        mock_registry.list_components.return_value = []

        captured_output = StringIO()

        with patch("osiris.cli.components_cmd.get_registry", return_value=mock_registry), patch(
            "sys.stdout", captured_output
        ):
            list_components(mode="all", as_json=True)

        output = captured_output.getvalue()
        data = json.loads(output)

        assert data == []

    def test_list_components_json_with_mode_filter(self):
        """Test JSON output with mode filtering."""
        mock_registry = MagicMock(spec=ComponentRegistry)

        # Registry should be called with the mode filter
        mock_registry.list_components.return_value = [
            {
                "name": "mysql.writer",
                "version": "1.0.0",
                "modes": ["write", "discover"],
                "description": "Write data to MySQL",
            }
        ]

        captured_output = StringIO()

        with patch("osiris.cli.components_cmd.get_registry", return_value=mock_registry), patch(
            "sys.stdout", captured_output
        ):
            list_components(mode="write", as_json=True)

        # Verify the registry was called with correct mode
        mock_registry.list_components.assert_called_once_with(mode="write")

        # Verify output
        data = json.loads(captured_output.getvalue())
        assert len(data) == 1
        assert data[0]["name"] == "mysql.writer"

    def test_list_components_no_json_has_table(self):
        """Test that without --json flag, output is not JSON (has Rich table)."""
        mock_registry = MagicMock(spec=ComponentRegistry)
        mock_registry.list_components.return_value = [
            {
                "name": "test.component",
                "version": "1.0.0",
                "modes": ["test"],
                "description": "Test component",
            }
        ]

        with patch("osiris.cli.components_cmd.get_registry", return_value=mock_registry), patch(
            "osiris.cli.components_cmd.console.print"
        ) as mock_print:
            list_components(mode="all", as_json=False)

        # Should have called console.print with a Table object
        mock_print.assert_called()
        # The argument should be a Table (we can't import it directly due to Rich internals)
        assert mock_print.call_args[0][0].__class__.__name__ == "Table"

    def test_list_components_json_format_validation(self):
        """Test that JSON output conforms to expected schema."""
        mock_registry = MagicMock(spec=ComponentRegistry)
        mock_registry.list_components.return_value = [
            {
                "name": "supabase.extractor",
                "version": "2.0.1",
                "modes": ["extract", "discover", "analyze"],
                "description": "Extract data from Supabase PostgreSQL databases with advanced features...",
                "title": "Supabase Extractor",
                "capabilities": {"discover": True, "streaming": False},
            }
        ]

        captured_output = StringIO()

        with patch("osiris.cli.components_cmd.get_registry", return_value=mock_registry), patch(
            "sys.stdout", captured_output
        ):
            list_components(mode="all", as_json=True)

        data = json.loads(captured_output.getvalue())

        # Validate structure
        assert len(data) == 1
        component = data[0]

        # Required fields should be present
        assert "name" in component
        assert "version" in component
        assert "modes" in component
        assert "description" in component

        # Types should be correct
        assert isinstance(component["name"], str)
        assert isinstance(component["version"], str)
        assert isinstance(component["modes"], list)
        assert isinstance(component["description"], str)

        # Modes should be list of strings
        for mode in component["modes"]:
            assert isinstance(mode, str)

        # Description should not have ellipsis
        assert not component["description"].endswith("...")

    def test_list_components_json_indentation(self):
        """Test that JSON output is properly indented for readability."""
        mock_registry = MagicMock(spec=ComponentRegistry)
        mock_registry.list_components.return_value = [
            {
                "name": "test.component",
                "version": "1.0.0",
                "modes": ["test"],
                "description": "Test",
            }
        ]

        captured_output = StringIO()

        with patch("osiris.cli.components_cmd.get_registry", return_value=mock_registry), patch(
            "sys.stdout", captured_output
        ):
            list_components(mode="all", as_json=True)

        output = captured_output.getvalue()

        # Check for indentation (should have newlines and spaces)
        assert "\n" in output
        assert "  " in output  # Should have indentation

        # Verify it's still valid JSON
        json.loads(output)
