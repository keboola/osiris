"""Friendly error mapper for component validation failures."""

from dataclasses import dataclass
import re
from typing import Any


@dataclass
class FriendlyError:
    """Structured friendly error with actionable fix suggestions."""

    category: str  # schema_error, config_error, type_error, constraint_error, runtime_error
    field_label: str  # Human-readable field name
    problem: str  # Clear description of what's wrong
    fix_hint: str  # How to fix it
    example: str | None = None  # Example of valid value
    technical_details: dict[str, Any] | None = None  # Original error info for --verbose


class FriendlyErrorMapper:
    """Maps technical validation errors to user-friendly messages."""

    # JSON Pointer path to human-readable label mapping
    PATH_LABELS = {
        # Config schema fields
        "/configSchema/properties/host": "Database Host",
        "/configSchema/properties/port": "Connection Port",
        "/configSchema/properties/database": "Database Name",
        "/configSchema/properties/user": "Database User",
        "/configSchema/properties/password": "Database Password",  # pragma: allowlist secret
        "/configSchema/properties/table": "Table Name",
        "/configSchema/properties/schema": "Schema Name",
        "/configSchema/properties/mode": "Operation Mode",
        "/configSchema/properties/batch_size": "Batch Size",
        "/configSchema/properties/pool_size": "Connection Pool Size",
        "/configSchema/properties/echo": "SQL Echo Mode",
        "/configSchema/properties/url": "Service URL",
        "/configSchema/properties/key": "API Key",  # pragma: allowlist secret
        "/configSchema/properties/project_id": "Project ID",
        "/configSchema/properties/select": "Select Columns",
        "/configSchema/properties/filter": "Filter Conditions",
        "/configSchema/properties/limit": "Row Limit",
        "/configSchema/properties/upsert_keys": "Upsert Key Fields",
        # Top-level spec fields
        "/name": "Component Name",
        "/version": "Component Version",
        "/title": "Component Title",
        "/description": "Component Description",
        "/modes": "Supported Modes",
        "/capabilities": "Component Capabilities",
        "/secrets": "Secret Fields",  # pragma: allowlist secret
        "/redaction": "Redaction Settings",
        "/examples": "Configuration Examples",
        "/constraints": "Field Constraints",
    }

    # Fix suggestions for common missing required fields
    MISSING_FIELD_SUGGESTIONS = {
        "host": "Add 'host: your-database-server.com' to your configuration. For local development, use 'host: localhost'",
        "database": "Specify the database name with 'database: your_db_name'",
        "user": "Add 'user: your_username' to authenticate with the database",
        "password": "Set 'password: your_password' or use environment variable for security",  # pragma: allowlist secret
        "table": "Specify which table to work with using 'table: your_table_name'",
        "key": "Add your API key from the service dashboard. Example: 'key: eyJhbGc...'",
        "url": "Provide the service URL. Example: 'url: https://project.supabase.co'",
        "project_id": "Add your project ID from the service dashboard",
        "name": "Every component must have a unique name (e.g., 'mysql.writer')",
        "version": "Specify component version using semantic versioning (e.g., '1.0.0')",
        "modes": "List the operational modes this component supports (e.g., ['write', 'discover'])",
    }

    # Fix suggestions for type errors
    TYPE_ERROR_SUGGESTIONS = {
        "integer": "Must be a whole number without quotes (e.g., 3306, not '3306')",
        "number": "Must be a numeric value (integer or decimal)",
        "boolean": "Must be true or false (without quotes)",
        "string": "Must be text enclosed in quotes if it contains special characters",
        "array": "Must be a list of values in square brackets (e.g., ['value1', 'value2'])",
        "object": "Must be a mapping with key-value pairs",
    }

    # Fix suggestions for constraint violations
    CONSTRAINT_SUGGESTIONS = {
        "minimum": "Value must be at least {minimum}",
        "maximum": "Value must be at most {maximum}",
        "minLength": "Text must be at least {minLength} characters long",
        "maxLength": "Text must be at most {maxLength} characters long",
        "minItems": "List must contain at least {minItems} items",
        "maxItems": "List can contain at most {maxItems} items",
        "pattern": "Value must match the pattern: {pattern}",
        "enum": "Value must be one of: {enum}",
    }

    def map_error(self, error: dict[str, Any] | Exception) -> FriendlyError:
        """Transform a raw validation error into a friendly error.

        Args:
            error: Raw error from jsonschema validation or custom validation

        Returns:
            FriendlyError with category, friendly message, and fix suggestions
        """
        if isinstance(error, dict):
            return self._map_validation_error(error)
        elif isinstance(error, Exception):
            return self._map_exception(error)
        else:
            # Fallback for unknown error types
            return FriendlyError(
                category="unknown_error",
                field_label="Unknown Field",
                problem=str(error),
                fix_hint="Check the component specification for correct format",
                technical_details={"raw_error": str(error)},
            )

    def _map_validation_error(self, error: dict[str, Any]) -> FriendlyError:
        """Map a jsonschema validation error to friendly format."""
        # Extract error details
        message = error.get("message", "Validation failed")
        path = error.get("path", "")
        validator = error.get("validator", "")
        schema_path = error.get("schema_path", [])

        # Determine field label from path
        field_label = self._get_field_label(path, schema_path)

        # Determine category and generate fix hint
        category, fix_hint, example = self._categorize_and_suggest(validator, message, field_label, error)

        # Create friendly problem description
        problem = self._create_friendly_problem(validator, message, field_label, error)

        return FriendlyError(
            category=category,
            field_label=field_label,
            problem=problem,
            fix_hint=fix_hint,
            example=example,
            technical_details={
                "message": message,
                "path": path,
                "validator": validator,
                "schema_path": schema_path,
            },
        )

    def _map_exception(self, error: Exception) -> FriendlyError:
        """Map a Python exception to friendly format."""
        error_type = type(error).__name__
        error_msg = str(error)

        # Common exception mappings
        if "ValidationError" in error_type and hasattr(error, "message"):
            # jsonschema ValidationError
            return self._map_validation_error(
                {
                    "message": error.message,
                    "path": getattr(error, "path", ""),
                    "validator": getattr(error, "validator", ""),
                    "schema_path": getattr(error, "schema_path", []),
                }
            )

        return FriendlyError(
            category="runtime_error",
            field_label="System",
            problem=f"{error_type}: {error_msg}",
            fix_hint="Check the error details and component configuration",
            technical_details={"error_type": error_type, "message": error_msg},
        )

    def _get_field_label(self, path: str, schema_path: list[str]) -> str:
        """Convert JSON pointer path to human-readable label."""
        # Try direct path lookup
        if path in self.PATH_LABELS:
            return self.PATH_LABELS[path]

        # Try to build path from schema_path
        if schema_path:
            constructed_path = "/" + "/".join(str(p) for p in schema_path)
            if constructed_path in self.PATH_LABELS:
                return self.PATH_LABELS[constructed_path]

            # Try to extract just the field name from the end
            if len(schema_path) > 0:
                last_part = str(schema_path[-1])
                # If it's a property name, make it friendly
                if last_part and not last_part.isdigit():
                    return self._make_friendly_name(last_part)

        # Extract field name from path if possible
        if path:
            parts = path.split("/")
            if parts:
                last = parts[-1]
                if last and not last.isdigit():
                    return self._make_friendly_name(last)

        return "Configuration Field"

    def _make_friendly_name(self, field_name: str) -> str:
        """Convert snake_case or camelCase to Title Case."""
        # Handle snake_case
        if "_" in field_name:
            return " ".join(word.capitalize() for word in field_name.split("_"))

        # Handle camelCase
        words = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)", field_name)
        if words:
            return " ".join(word.capitalize() for word in words)

        # Default: just capitalize
        return field_name.capitalize()

    def _categorize_and_suggest(
        self, validator: str, message: str, field_label: str, error: dict[str, Any]
    ) -> tuple[str, str, str | None]:
        """Categorize error and generate fix suggestion with example."""
        field_name = self._extract_field_name(error)

        # For required field errors, extract the actual missing field from message
        if validator == "required" or "required property" in message.lower():
            # Extract the missing field name from message like "'host' is a required property"
            import re

            match = re.search(r"'(\w+)'", message)
            if match:
                field_name = match.group(1)

            category = "config_error"
            fix_hint = self.MISSING_FIELD_SUGGESTIONS.get(
                field_name, f"Add the required field '{field_name}' to your configuration"
            )
            example = self._get_example_for_field(field_name)
            return category, fix_hint, example

        # Type mismatch
        if validator == "type" or "type" in message.lower():
            category = "type_error"
            expected_type = error.get("schema", {}).get("type", "correct type")
            fix_hint = self.TYPE_ERROR_SUGGESTIONS.get(expected_type, f"Value must be of type {expected_type}")
            example = self._get_example_for_type(expected_type, field_name)
            return category, fix_hint, example

        # Constraint violations
        if validator in ["minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems"]:
            category = "constraint_error"
            schema = error.get("schema", {})
            template = self.CONSTRAINT_SUGGESTIONS.get(validator, "Value must meet constraints")
            fix_hint = template.format(**schema)
            example = self._get_example_for_constraint(validator, schema, field_name)
            return category, fix_hint, example

        # Pattern mismatch
        if validator == "pattern":
            category = "constraint_error"
            pattern = error.get("schema", {}).get("pattern", "")
            fix_hint = f"Value must match pattern: {pattern}"
            example = self._get_pattern_example(pattern, field_name)
            return category, fix_hint, example

        # Enum constraint
        if validator == "enum":
            category = "constraint_error"
            allowed = error.get("schema", {}).get("enum", [])
            fix_hint = f"Value must be one of: {', '.join(str(v) for v in allowed)}"
            example = f"{field_name}: {allowed[0]}" if allowed else None
            return category, fix_hint, example

        # Default category
        category = "schema_error"
        fix_hint = f"Check the component specification for valid {field_label} format"
        return category, fix_hint, None

    def _create_friendly_problem(self, validator: str, message: str, field_label: str, error: dict[str, Any]) -> str:
        """Create a user-friendly problem description."""
        instance = error.get("instance")

        # Required field missing
        if validator == "required" or "required property" in message.lower():
            # Extract the missing field name from the message
            match = re.search(r"'(\w+)'", message)
            if match:
                missing_field = match.group(1)
                return f"Required field '{missing_field}' is missing from configuration"
            return f"The {field_label} is required but was not provided"

        # Type mismatch
        if validator == "type":
            expected = error.get("schema", {}).get("type", "unknown")
            actual = type(instance).__name__ if instance is not None else "null"
            return f"Expected {expected} but got {actual}"

        # Value constraints
        if validator == "minimum":
            min_val = error.get("schema", {}).get("minimum")
            return f"Value {instance} is less than minimum {min_val}"

        if validator == "maximum":
            max_val = error.get("schema", {}).get("maximum")
            return f"Value {instance} is greater than maximum {max_val}"

        if validator == "minLength":
            min_len = error.get("schema", {}).get("minLength")
            actual_len = len(instance) if instance else 0
            return f"Text has {actual_len} characters but needs at least {min_len}"

        if validator == "enum":
            return f"Value '{instance}' is not one of the allowed options"

        # Default: use original message but make it cleaner
        return message.replace("'", "").replace('"', "")

    def _extract_field_name(self, error: dict[str, Any]) -> str:
        """Extract the actual field name from error details."""
        # Try to get from path
        path = error.get("path", "")
        if path:
            parts = path.split("/")
            if parts:
                last = parts[-1]
                if last and not last.isdigit():
                    return last

        # Try to extract from message
        message = error.get("message", "")
        match = re.search(r"'(\w+)'", message)
        if match:
            return match.group(1)

        # Try schema_path
        schema_path = error.get("schema_path", [])
        if schema_path and len(schema_path) > 1:
            # Often the field name is at schema_path[-1] or schema_path[-2]
            for i in range(len(schema_path) - 1, -1, -1):
                part = str(schema_path[i])
                if part not in ["properties", "items", "required"] and not part.isdigit():
                    return part

        return "field"

    def _get_example_for_field(self, field_name: str) -> str | None:
        """Get example value for a specific field."""
        examples = {
            "host": "host: localhost",
            "port": "port: 3306",
            "database": "database: myapp_db",
            "user": "user: db_user",
            "password": "password: ${DB_PASSWORD}  # Use env var for security",  # pragma: allowlist secret
            "table": "table: customers",
            "key": "key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "url": "url: https://myproject.supabase.co",
            "project_id": "project_id: abc123xyz",
            "batch_size": "batch_size: 1000",
            "mode": "mode: write",
            "modes": "modes: [write, discover]",
            "version": "version: 1.0.0",
        }
        return examples.get(field_name)

    def _get_example_for_type(self, expected_type: str, field_name: str) -> str | None:
        """Get example value for a specific type."""
        type_examples = {
            "integer": f"{field_name}: 42",
            "number": f"{field_name}: 3.14",
            "boolean": f"{field_name}: true",
            "string": f'{field_name}: "example text"',
            "array": f"{field_name}: [item1, item2]",
            "object": f"{field_name}:\n  key1: value1\n  key2: value2",
        }
        return type_examples.get(expected_type)

    def _get_example_for_constraint(self, validator: str, schema: dict[str, Any], field_name: str) -> str | None:
        """Get example that satisfies a constraint."""
        if validator == "minimum":
            min_val = schema.get("minimum", 0)
            return f"{field_name}: {min_val + 1}"
        elif validator == "maximum":
            max_val = schema.get("maximum", 100)
            return f"{field_name}: {max_val - 1}"
        elif validator == "minLength":
            min_len = schema.get("minLength", 1)
            return f'{field_name}: "{"a" * min_len}"'
        elif validator == "minItems":
            min_items = schema.get("minItems", 1)
            items = [f"item{i}" for i in range(min_items)]
            return f"{field_name}: [{', '.join(items)}]"
        return None

    def _get_pattern_example(self, pattern: str, field_name: str) -> str | None:
        """Get example that matches a regex pattern."""
        # Common patterns
        if "https://" in pattern:
            return f"{field_name}: https://example.com"
        elif r"\d+" in pattern:
            return f"{field_name}: 12345"
        elif "^[a-zA-Z]" in pattern:
            return f"{field_name}: example_value"
        return None

    def format_friendly_errors(self, errors: list[FriendlyError], verbose: bool = False) -> list[str]:
        """Format friendly errors for display.

        Args:
            errors: List of FriendlyError objects
            verbose: Include technical details if True

        Returns:
            List of formatted error strings
        """
        formatted = []
        for error in errors:
            lines = []

            # Error header with category icon
            icon = self._get_category_icon(error.category)
            lines.append(f"{icon} {self._get_category_title(error.category)}")

            # Field and problem
            lines.append(f"   Field: {error.field_label}")
            lines.append(f"   Problem: {error.problem}")

            # Fix suggestion
            lines.append(f"   Fix: {error.fix_hint}")

            # Example if available
            if error.example:
                lines.append(f"   Example: {error.example}")

            # Technical details if verbose
            if verbose and error.technical_details:
                lines.append("\n   Technical Details:")
                for key, value in error.technical_details.items():
                    lines.append(f"   - {key}: {value}")

            formatted.append("\n".join(lines))

        return formatted

    def _get_category_icon(self, category: str) -> str:
        """Get icon for error category."""
        icons = {
            "schema_error": "🔧",
            "config_error": "❌",
            "type_error": "⚠️",
            "constraint_error": "📏",
            "runtime_error": "💥",
            "unknown_error": "❓",
        }
        return icons.get(category, "•")

    def _get_category_title(self, category: str) -> str:
        """Get title for error category."""
        titles = {
            "schema_error": "Schema Structure Error",
            "config_error": "Missing Required Configuration",
            "type_error": "Invalid Type",
            "constraint_error": "Constraint Violation",
            "runtime_error": "Runtime Error",
            "unknown_error": "Validation Error",
        }
        return titles.get(category, "Error")
