"""
Error taxonomy for Osiris MCP server.

Provides structured error handling with consistent format across all tools.
"""

from enum import Enum
import re
from typing import Any

# Deterministic error code mappings
ERROR_CODES = {
    # Schema errors (SCHEMA/*) - exact matches have priority
    "missing required field: name": "OML001",
    "missing required field: steps": "OML002",
    "missing required field: version": "OML003",
    "missing required field": "OML004",
    "invalid type": "OML005",
    "invalid format": "OML006",
    "unknown property": "OML007",
    "yaml parse error": "OML010",
    "oml parse error": "OML010",
    "intent is required": "OML020",
    # Semantic errors (SEMANTIC/*)
    "unknown tool": "SEM001",
    "invalid connection": "SEM002",
    "invalid component": "SEM003",
    "circular dependency": "SEM004",
    "duplicate name": "SEM005",
    # Discovery errors (DISCOVERY/*)
    "connection not found": "DISC001",
    "source unreachable": "DISC002",
    "permission denied": "DISC003",
    "invalid schema": "DISC005",
    # Lint errors (LINT/*)
    "naming convention": "LINT001",
    "deprecated feature": "LINT002",
    "performance warning": "LINT003",
    # Policy errors (POLICY/*)
    "consent required": "POL001",
    "payload too large": "POL002",
    "rate limit exceeded": "POL003",
    "unauthorized": "POL004",
    "forbidden operation": "POL005",
    # Connection/CLI-bridge errors (SEMANTIC/E_CONN_*)
    # Longer patterns first for priority matching
    "missing environment variable": "E_CONN_SECRET_MISSING",
    "environment variable": "E_CONN_SECRET_MISSING",
    "not set": "E_CONN_SECRET_MISSING",
    "authentication failed": "E_CONN_AUTH_FAILED",
    "invalid password": "E_CONN_AUTH_FAILED",
    "invalid credentials": "E_CONN_AUTH_FAILED",
    "connection refused": "E_CONN_REFUSED",
    "dns resolution failed": "E_CONN_DNS",
    "no such host": "E_CONN_DNS",
    "name or service not known": "E_CONN_DNS",
    "could not connect": "E_CONN_UNREACHABLE",
    "network is unreachable": "E_CONN_UNREACHABLE",
    "unreachable host": "E_CONN_UNREACHABLE",
    "connection timeout": "E_CONN_TIMEOUT",
    "request timeout": "E_CONN_TIMEOUT",
    "timed out": "E_CONN_TIMEOUT",
    "timeout": "E_CONN_TIMEOUT",  # Generic timeout pattern (must come last after specific ones)
}


class ErrorFamily(Enum):
    """Error family classification."""

    SCHEMA = "SCHEMA"  # Schema validation errors
    SEMANTIC = "SEMANTIC"  # Semantic/logic errors
    DISCOVERY = "DISCOVERY"  # Discovery-related errors
    LINT = "LINT"  # Linting/style errors
    POLICY = "POLICY"  # Policy/permission errors


class OsirisError(Exception):
    """Base exception for Osiris MCP errors."""

    def __init__(
        self,
        family: ErrorFamily,
        message: str,
        path: str | list[str] | None = None,
        suggest: str | None = None,
    ):
        """
        Initialize an Osiris error.

        Args:
            family: Error family classification
            message: Human-readable error message
            path: Path to the error location (e.g., field path)
            suggest: Optional suggestion for fixing the error
        """
        self.family = family
        self.message = message
        self.path = path if isinstance(path, list) else [path] if path else []
        self.suggest = suggest
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary format."""
        result = {"code": f"{self.family.value}/{self._generate_code()}", "message": self.message, "path": self.path}
        if self.suggest:
            result["suggest"] = self.suggest
        return result

    def _generate_code(self) -> str:
        """Generate specific error code based on message."""
        message_lower = self.message.lower()

        # Check for exact matches first (longer patterns before shorter)
        sorted_patterns = sorted(ERROR_CODES.items(), key=lambda x: -len(x[0]))
        for pattern, code in sorted_patterns:
            if pattern in message_lower:
                return code

        # Generate unique code for unknown errors using hash
        import hashlib  # noqa: PLC0415  # Lazy import for performance

        msg_hash = hashlib.sha256(self.message.encode()).hexdigest()[:3].upper()

        # Family-specific prefixes for unknown errors
        family_prefixes = {
            ErrorFamily.SCHEMA: "OML",
            ErrorFamily.SEMANTIC: "SEM",
            ErrorFamily.DISCOVERY: "DISC",
            ErrorFamily.LINT: "LINT",
            ErrorFamily.POLICY: "POL",
        }

        prefix = family_prefixes.get(self.family, "ERR")
        # Ensure different messages get different codes
        return f"{prefix}{msg_hash}"


class SchemaError(OsirisError):
    """Schema validation error."""

    def __init__(self, message: str, path: str | list[str] | None = None, suggest: str | None = None):
        super().__init__(ErrorFamily.SCHEMA, message, path, suggest)


class SemanticError(OsirisError):
    """Semantic/logic error."""

    def __init__(self, message: str, path: str | list[str] | None = None, suggest: str | None = None):
        super().__init__(ErrorFamily.SEMANTIC, message, path, suggest)


class DiscoveryError(OsirisError):
    """Discovery-related error."""

    def __init__(self, message: str, path: str | list[str] | None = None, suggest: str | None = None):
        super().__init__(ErrorFamily.DISCOVERY, message, path, suggest)


class LintError(OsirisError):
    """Linting/style error."""

    def __init__(self, message: str, path: str | list[str] | None = None, suggest: str | None = None):
        super().__init__(ErrorFamily.LINT, message, path, suggest)


class PolicyError(OsirisError):
    """Policy/permission error."""

    def __init__(self, message: str, path: str | list[str] | None = None, suggest: str | None = None):
        super().__init__(ErrorFamily.POLICY, message, path, suggest)


class OsirisErrorHandler:
    """Handler for formatting and managing errors."""

    def format_error(self, error: OsirisError) -> dict[str, Any]:
        """Format an OsirisError for response."""
        return {"error": error.to_dict(), "success": False}

    def format_unexpected_error(self, message: str) -> dict[str, Any]:
        """Format an unexpected error."""
        return {
            "error": {
                "code": "INTERNAL/UNEXPECTED",
                "message": f"An unexpected error occurred: {message}",
                "path": [],
                "suggest": "Please report this issue if it persists",
            },
            "success": False,
        }

    def format_validation_diagnostics(self, diagnostics: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Format validation diagnostics in ADR-0019 compatible format.

        Args:
            diagnostics: List of diagnostic items

        Returns:
            Formatted diagnostics with deterministic IDs
        """
        formatted = []
        for i, diag in enumerate(diagnostics):
            formatted_diag = {
                "type": diag.get("type", "error"),
                "line": diag.get("line", 0),
                "column": diag.get("column", 0),
                "message": diag.get("message", "Unknown error"),
                "id": self._generate_diagnostic_id(diag, i),
            }
            formatted.append(formatted_diag)
        return formatted

    def _generate_diagnostic_id(self, diagnostic: dict[str, Any], index: int) -> str:
        """Generate deterministic diagnostic ID."""
        diag_type = diagnostic.get("type", "error")
        line = diagnostic.get("line", 0)

        # Generate OML-specific error code
        if diag_type == "error":
            prefix = "OML001"
        elif diag_type == "warning":
            prefix = "OML002"
        else:
            prefix = "OML003"

        return f"{prefix}_{line}_{index}"


def _redact_secrets_from_message(message: str) -> str:
    """
    Redact secrets from error messages (DSNs, URLs with credentials).

    Args:
        message: Raw error message

    Returns:
        Sanitized message with secrets redacted
    """
    # Redact DSN/URL with credentials: scheme://user:password@host/path -> scheme://***@host/path
    message = re.sub(r"(\w+://)[^:/@\s]+:[^@\s]+@([^/\s]+)", r"\1***@\2", message)

    # Redact password= or token= parameters (handles both & and ; separators)
    message = re.sub(r"(password|token|secret|key)=[^\s&;]+", r"\1=***", message, flags=re.IGNORECASE)

    return message


def map_cli_error_to_mcp(exc_or_msg: Exception | str) -> OsirisError:
    """
    Map CLI subprocess output or exception to structured OsirisError.

    Analyzes error messages from subprocess stderr/stdout or Exception objects
    and returns an OsirisError with:
    - Inferred family (POLICY, DISCOVERY, SCHEMA, or SEMANTIC)
    - Stable code from ERROR_CODES (fallback to hash if no match)
    - Normalized message (single line, trimmed, secrets redacted)
    - Empty path list

    Args:
        exc_or_msg: Exception or error message string from subprocess

    Returns:
        OsirisError with deterministic classification
    """
    # Extract message
    if isinstance(exc_or_msg, Exception):
        raw_message = str(exc_or_msg)
    else:
        raw_message = exc_or_msg

    # Normalize: single line, strip whitespace
    normalized = " ".join(raw_message.strip().split())

    # Redact secrets
    normalized = _redact_secrets_from_message(normalized)

    message_lower = normalized.lower()

    # Pattern recognition for CLI-bridge errors
    family = ErrorFamily.SEMANTIC  # Default for connection errors
    suggest = None

    # OML/Schema errors (check first for priority)
    if any(pattern in message_lower for pattern in ["oml parse", "yaml parse", "missing required field"]):
        family = ErrorFamily.SCHEMA
    # Policy errors (check before auth to avoid conflict)
    elif any(pattern in message_lower for pattern in ["consent required", "rate limit", "forbidden"]) or re.search(
        r"\bunauthorized\b", message_lower
    ):
        family = ErrorFamily.POLICY
    # Timeout errors (DISCOVERY)
    elif any(pattern in message_lower for pattern in ["timeout", "timed out"]):
        family = ErrorFamily.DISCOVERY
        suggest = "Check network connectivity and increase timeout if needed"
    # Authentication errors (SEMANTIC) - check after policy checks
    elif any(
        pattern in message_lower
        for pattern in ["authentication failed", "invalid password", "invalid credentials", "auth error"]
    ):
        family = ErrorFamily.SEMANTIC
        suggest = "Verify credentials in osiris_connections.yaml and environment"
    # Secret/environment errors (SEMANTIC)
    elif any(pattern in message_lower for pattern in ["not set", "missing env", "${"]):
        family = ErrorFamily.SEMANTIC
        suggest = "Check environment variables and .env file"
    # Connection refused (SEMANTIC)
    elif "connection refused" in message_lower:
        family = ErrorFamily.SEMANTIC
        suggest = "Verify the service is running and port is correct"
    # DNS errors (SEMANTIC)
    elif any(pattern in message_lower for pattern in ["no such host", "name or service not known", "dns"]):
        family = ErrorFamily.SEMANTIC
        suggest = "Check hostname spelling and network connectivity"
    # Unreachable errors (SEMANTIC)
    elif any(pattern in message_lower for pattern in ["could not connect", "unreachable", "network is unreachable"]):
        family = ErrorFamily.SEMANTIC
        suggest = "Check network connectivity and firewall rules"

    # Build OsirisError
    return OsirisError(family=family, message=normalized, path=[], suggest=suggest)
