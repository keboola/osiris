"""
Test MCP error shape and taxonomy.
"""

import pytest
from osiris.mcp.errors import (
    OsirisError, SchemaError, SemanticError, DiscoveryError,
    LintError, PolicyError, ErrorFamily, OsirisErrorHandler,
    map_cli_error_to_mcp, _redact_secrets_from_message
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


class TestCLIBridgeErrorMapping:
    """Test CLI-bridge error mapping to MCP format."""

    @pytest.mark.parametrize("message,expected_code,expected_family", [
        # Connection errors (SEMANTIC)
        ("Missing environment variable MYSQL_PASSWORD", "E_CONN_SECRET_MISSING", ErrorFamily.SEMANTIC),
        ("Environment variable DB_HOST not set", "E_CONN_SECRET_MISSING", ErrorFamily.SEMANTIC),
        ("Variable ${DATABASE_URL} is not set", "E_CONN_SECRET_MISSING", ErrorFamily.SEMANTIC),
        ("Authentication failed for user root", "E_CONN_AUTH_FAILED", ErrorFamily.SEMANTIC),
        ("Invalid password for database connection", "E_CONN_AUTH_FAILED", ErrorFamily.SEMANTIC),
        ("Auth error: invalid credentials", "E_CONN_AUTH_FAILED", ErrorFamily.SEMANTIC),
        ("Connection refused by host", "E_CONN_REFUSED", ErrorFamily.SEMANTIC),
        ("No such host: mysql.example.com", "E_CONN_DNS", ErrorFamily.SEMANTIC),
        ("DNS resolution failed for database.local", "E_CONN_DNS", ErrorFamily.SEMANTIC),
        ("Name or service not known", "E_CONN_DNS", ErrorFamily.SEMANTIC),
        ("Could not connect to remote host", "E_CONN_UNREACHABLE", ErrorFamily.SEMANTIC),
        ("Network is unreachable", "E_CONN_UNREACHABLE", ErrorFamily.SEMANTIC),
        ("Unreachable host: 10.0.0.1", "E_CONN_UNREACHABLE", ErrorFamily.SEMANTIC),

        # Timeout errors (DISCOVERY)
        ("Connection timeout after 30 seconds", "E_CONN_TIMEOUT", ErrorFamily.DISCOVERY),
        ("Operation timed out", "E_CONN_TIMEOUT", ErrorFamily.DISCOVERY),
        ("Request timeout", "E_CONN_TIMEOUT", ErrorFamily.DISCOVERY),

        # OML/Schema errors (SCHEMA)
        ("OML parse error at line 10", "OML010", ErrorFamily.SCHEMA),
        ("YAML parse error: invalid syntax", "OML010", ErrorFamily.SCHEMA),
        ("Missing required field: steps", "OML002", ErrorFamily.SCHEMA),

        # Policy errors (POLICY)
        ("Consent required for this operation", "POL001", ErrorFamily.POLICY),
        ("Unauthorized access", "POL004", ErrorFamily.POLICY),
        ("Forbidden operation: delete", "POL005", ErrorFamily.POLICY),
        ("Rate limit exceeded", "POL003", ErrorFamily.POLICY),
    ])
    def test_cli_error_mapping_deterministic_codes(self, message, expected_code, expected_family):
        """Test CLI errors map to correct deterministic codes."""
        error = map_cli_error_to_mcp(message)

        assert error.family == expected_family
        assert error.to_dict()["code"] == f"{expected_family.value}/{expected_code}"
        assert error.path == []

    def test_cli_error_from_exception(self):
        """Test mapping from Exception object."""
        exc = ValueError("Authentication failed: bad password")  # pragma: allowlist secret
        error = map_cli_error_to_mcp(exc)

        assert error.family == ErrorFamily.SEMANTIC
        assert "E_CONN_AUTH_FAILED" in error.to_dict()["code"]
        assert "Authentication failed" in error.message

    def test_cli_error_message_normalization(self):
        """Test message normalization (single line, trimmed)."""
        multiline_msg = """
        Connection
        timeout
        after 30 seconds
        """
        error = map_cli_error_to_mcp(multiline_msg)

        assert "\n" not in error.message
        assert error.message == "Connection timeout after 30 seconds"

    def test_cli_error_determinism(self):
        """Test same input produces same error code."""
        msg = "Authentication failed for user admin"
        error1 = map_cli_error_to_mcp(msg)
        error2 = map_cli_error_to_mcp(msg)

        assert error1.to_dict()["code"] == error2.to_dict()["code"]

    def test_cli_error_suggestions(self):
        """Test error suggestions are provided for common issues."""
        test_cases = [
            ("Missing environment variable DB_PASSWORD", "Check environment variables"),  # pragma: allowlist secret
            ("Connection timeout", "Check network connectivity"),
            ("Authentication failed", "Verify credentials"),
            ("Connection refused", "Verify the service is running"),
            ("No such host", "Check hostname spelling"),
            ("Network is unreachable", "Check network connectivity"),
        ]

        for message, expected_suggestion_fragment in test_cases:
            error = map_cli_error_to_mcp(message)
            assert error.suggest is not None
            assert expected_suggestion_fragment.lower() in error.suggest.lower()


class TestSecretRedaction:
    """Test secret redaction in error messages."""

    @pytest.mark.parametrize("input_msg,expected_output", [
        # DSN redaction
        (
            "mysql://root:secret123@localhost/db",  # pragma: allowlist secret
            "mysql://***@localhost/db"
        ),
        (
            "postgresql://user:pass@db.example.com:5432/mydb",  # pragma: allowlist secret
            "postgresql://***@db.example.com:5432/mydb"
        ),
        (
            "https://admin:token@api.example.com/v1",  # pragma: allowlist secret
            "https://***@api.example.com/v1"
        ),

        # Query parameter redaction
        (
            "GET /api?password=secret123&key=abc",  # pragma: allowlist secret
            "GET /api?password=***&key=***"
        ),
        (
            "Connection string: server=host;password=mypass;token=xyz",  # pragma: allowlist secret
            "Connection string: server=host;password=***;token=***"
        ),

        # No redaction needed
        (
            "Connection refused by localhost",
            "Connection refused by localhost"
        ),
        (
            "Timeout after 30 seconds",
            "Timeout after 30 seconds"
        ),
    ])
    def test_secret_redaction(self, input_msg, expected_output):
        """Test secrets are properly redacted from error messages."""
        redacted = _redact_secrets_from_message(input_msg)
        assert redacted == expected_output

    def test_cli_error_redacts_secrets(self):
        """Test map_cli_error_to_mcp redacts secrets from messages."""
        msg_with_secret = "Failed to connect: mysql://root:password123@localhost/db"  # pragma: allowlist secret
        error = map_cli_error_to_mcp(msg_with_secret)

        assert "password123" not in error.message  # pragma: allowlist secret
        assert "***" in error.message
        assert "mysql://***@localhost/db" in error.message