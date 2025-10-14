"""
Test MCP error shape and taxonomy.
"""

import pytest
from osiris.mcp.errors import (
    OsirisError, SchemaError, SemanticError, DiscoveryError,
    LintError, PolicyError, ErrorFamily, OsirisErrorHandler
)


class TestErrorShape:
    """Test error shape compliance with spec."""

    def test_error_shape_basic(self):
        """Test basic error shape has required fields."""
        error = OsirisError(
            ErrorFamily.SCHEMA,
            "Test error message",
            path=["field", "subfield"],
            suggest="Try fixing this"
        )

        error_dict = error.to_dict()

        # Check required fields
        assert "code" in error_dict
        assert "message" in error_dict
        assert "path" in error_dict

        # Check optional field
        assert "suggest" in error_dict

        # Verify format
        assert error_dict["code"].startswith("SCHEMA/")
        assert error_dict["message"] == "Test error message"
        assert error_dict["path"] == ["field", "subfield"]
        assert error_dict["suggest"] == "Try fixing this"

    def test_error_shape_without_suggest(self):
        """Test error shape without suggest field."""
        error = SemanticError(
            "Semantic error",
            path="single_path"
        )

        error_dict = error.to_dict()

        assert "code" in error_dict
        assert "message" in error_dict
        assert "path" in error_dict
        assert "suggest" not in error_dict

        # Path should be converted to list
        assert error_dict["path"] == ["single_path"]

    def test_error_families(self):
        """Test all error families generate correct codes."""
        families = [
            (SchemaError, "SCHEMA"),
            (SemanticError, "SEMANTIC"),
            (DiscoveryError, "DISCOVERY"),
            (LintError, "LINT"),
            (PolicyError, "POLICY")
        ]

        for error_class, family_name in families:
            error = error_class("Test message")
            error_dict = error.to_dict()
            assert error_dict["code"].startswith(f"{family_name}/")

    def test_error_handler_format_error(self):
        """Test error handler formatting."""
        handler = OsirisErrorHandler()
        error = PolicyError(
            "Permission denied",
            path=["resource", "access"],
            suggest="Check permissions"
        )

        formatted = handler.format_error(error)

        assert formatted["success"] is False
        assert "error" in formatted
        assert formatted["error"]["code"].startswith("POLICY/")
        assert formatted["error"]["message"] == "Permission denied"

    def test_error_handler_format_unexpected(self):
        """Test formatting unexpected errors."""
        handler = OsirisErrorHandler()
        formatted = handler.format_unexpected_error("Something went wrong")

        assert formatted["success"] is False
        assert formatted["error"]["code"] == "INTERNAL/UNEXPECTED"
        assert "Something went wrong" in formatted["error"]["message"]
        assert formatted["error"]["suggest"] == "Please report this issue if it persists"

    def test_validation_diagnostics_format(self):
        """Test ADR-0019 compatible diagnostic formatting."""
        handler = OsirisErrorHandler()
        diagnostics = [
            {
                "type": "error",
                "line": 10,
                "column": 5,
                "message": "Missing required field"
            },
            {
                "type": "warning",
                "line": 20,
                "column": 0,
                "message": "Deprecated feature"
            }
        ]

        formatted = handler.format_validation_diagnostics(diagnostics)

        assert len(formatted) == 2

        # Check first diagnostic
        assert formatted[0]["type"] == "error"
        assert formatted[0]["line"] == 10
        assert formatted[0]["column"] == 5
        assert formatted[0]["message"] == "Missing required field"
        assert formatted[0]["id"].startswith("OML001_")  # Error prefix

        # Check second diagnostic
        assert formatted[1]["type"] == "warning"
        assert formatted[1]["id"].startswith("OML002_")  # Warning prefix

    def test_error_code_determinism(self):
        """Test error codes are deterministic."""
        error1 = SchemaError("Same message", path=["path"])
        error2 = SchemaError("Same message", path=["different"])

        # Same message should generate same code suffix
        code1 = error1.to_dict()["code"]
        code2 = error2.to_dict()["code"]

        assert code1.split("/")[1] == code2.split("/")[1]

        # Different message should generate different code
        error3 = SchemaError("Different message")
        code3 = error3.to_dict()["code"]

        assert code1.split("/")[1] != code3.split("/")[1]