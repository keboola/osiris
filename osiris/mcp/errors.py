"""
Error taxonomy for Osiris MCP server.

Provides structured error handling with consistent format across all tools.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union


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
    "timeout": "DISC004",
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
}


class ErrorFamily(Enum):
    """Error family classification."""
    SCHEMA = "SCHEMA"      # Schema validation errors
    SEMANTIC = "SEMANTIC"  # Semantic/logic errors
    DISCOVERY = "DISCOVERY"  # Discovery-related errors
    LINT = "LINT"          # Linting/style errors
    POLICY = "POLICY"      # Policy/permission errors


class OsirisError(Exception):
    """Base exception for Osiris MCP errors."""

    def __init__(
        self,
        family: ErrorFamily,
        message: str,
        path: Optional[Union[str, List[str]]] = None,
        suggest: Optional[str] = None
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

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary format."""
        result = {
            "code": f"{self.family.value}/{self._generate_code()}",
            "message": self.message,
            "path": self.path
        }
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
        import hashlib
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

    def __init__(self, message: str, path: Optional[Union[str, List[str]]] = None, suggest: Optional[str] = None):
        super().__init__(ErrorFamily.SCHEMA, message, path, suggest)


class SemanticError(OsirisError):
    """Semantic/logic error."""

    def __init__(self, message: str, path: Optional[Union[str, List[str]]] = None, suggest: Optional[str] = None):
        super().__init__(ErrorFamily.SEMANTIC, message, path, suggest)


class DiscoveryError(OsirisError):
    """Discovery-related error."""

    def __init__(self, message: str, path: Optional[Union[str, List[str]]] = None, suggest: Optional[str] = None):
        super().__init__(ErrorFamily.DISCOVERY, message, path, suggest)


class LintError(OsirisError):
    """Linting/style error."""

    def __init__(self, message: str, path: Optional[Union[str, List[str]]] = None, suggest: Optional[str] = None):
        super().__init__(ErrorFamily.LINT, message, path, suggest)


class PolicyError(OsirisError):
    """Policy/permission error."""

    def __init__(self, message: str, path: Optional[Union[str, List[str]]] = None, suggest: Optional[str] = None):
        super().__init__(ErrorFamily.POLICY, message, path, suggest)


class OsirisErrorHandler:
    """Handler for formatting and managing errors."""

    def format_error(self, error: OsirisError) -> Dict[str, Any]:
        """Format an OsirisError for response."""
        return {
            "error": error.to_dict(),
            "success": False
        }

    def format_unexpected_error(self, message: str) -> Dict[str, Any]:
        """Format an unexpected error."""
        return {
            "error": {
                "code": "INTERNAL/UNEXPECTED",
                "message": f"An unexpected error occurred: {message}",
                "path": [],
                "suggest": "Please report this issue if it persists"
            },
            "success": False
        }

    def format_validation_diagnostics(
        self,
        diagnostics: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
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
                "id": self._generate_diagnostic_id(diag, i)
            }
            formatted.append(formatted_diag)
        return formatted

    def _generate_diagnostic_id(self, diagnostic: Dict[str, Any], index: int) -> str:
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