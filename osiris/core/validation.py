# Copyright (c) 2025 Osiris Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Basic connection configuration validation for M0.3.

This module provides JSON Schema-based validation for connection configurations
with friendly error messages and validation modes (warn/strict/off).
"""

from dataclasses import dataclass
from enum import Enum
import os
from typing import Any

# Basic JSON schemas for connection validation
MYSQL_CONNECTION_SCHEMA = {
    "type": "object",
    "required": ["type", "host", "database", "user", "password"],
    "properties": {
        "type": {"type": "string", "const": "mysql"},
        "host": {"type": "string", "minLength": 1},
        "port": {"type": "integer", "minimum": 1, "maximum": 65535, "default": 3306},
        "database": {"type": "string", "minLength": 1},
        "user": {"type": "string", "minLength": 1},
        "password": {"type": "string"},
        "charset": {"type": "string", "default": "utf8mb4"},
        "connect_timeout": {"type": "integer", "minimum": 1, "default": 10},
        "read_timeout": {"type": "integer", "minimum": 1, "default": 10},
        "write_timeout": {"type": "integer", "minimum": 1, "default": 10},
        # Connection management fields per ADR-0020
        "default": {"type": "boolean", "description": "Mark as default connection for family"},
        "alias": {"type": "string", "description": "Connection alias name (metadata only)"},
        # Alternative connection methods
        "dsn": {"type": "string", "description": "Alternative DSN connection string"},
    },
    "additionalProperties": False,
}

SUPABASE_CONNECTION_SCHEMA = {
    "type": "object",
    "required": ["type", "url", "key"],
    "properties": {
        "type": {"type": "string", "const": "supabase"},
        "url": {"type": "string", "format": "uri"},
        "key": {"type": "string", "minLength": 1},
        "schema": {"type": "string", "default": "public"},
        # Connection management fields per ADR-0020
        "default": {"type": "boolean", "description": "Mark as default connection for family"},
        "alias": {"type": "string", "description": "Connection alias name (metadata only)"},
        # Alternative connection methods and metadata
        "pg_dsn": {"type": "string", "description": "PostgreSQL DSN for direct connection"},
        "service_role_key": {"type": "string", "description": "Alternative: service role key"},
        "anon_key": {"type": "string", "description": "Alternative: anonymous/public key"},
        "password": {"type": "string", "description": "Database password for pg_dsn"},
    },
    "additionalProperties": False,
}

PIPELINE_CONFIG_SCHEMA = {
    "type": "object",
    "required": ["source", "destination"],
    "properties": {
        "source": {
            "type": "object",
            "required": ["connection", "table"],
            "properties": {
                "connection": {"type": "string", "minLength": 1},
                "table": {"type": "string", "minLength": 1},
                "schema": {"type": "string"},
                "columns": {"type": "array", "items": {"type": "string"}},
                "filters": {"type": "array", "items": {"type": "string"}},
            },
        },
        "destination": {
            "type": "object",
            "required": ["connection", "table"],
            "properties": {
                "connection": {"type": "string", "minLength": 1},
                "table": {"type": "string", "minLength": 1},
                "schema": {"type": "string"},
                "mode": {
                    "type": "string",
                    "enum": ["append", "merge", "replace"],
                    "default": "append",
                },
                "merge_keys": {"type": "array", "items": {"type": "string"}},
            },
        },
        "options": {
            "type": "object",
            "properties": {
                "batch_size": {"type": "integer", "minimum": 1, "default": 1000},
                "parallel": {"type": "boolean", "default": False},
            },
        },
    },
    "additionalProperties": True,
}


class ValidationMode(Enum):
    """Validation modes for backward compatibility."""

    OFF = "off"
    WARN = "warn"
    STRICT = "strict"


@dataclass
class ValidationError:
    """Friendly validation error with context."""

    path: str
    rule: str
    message: str
    why: str
    fix: str
    example: str | None = None


@dataclass
class ValidationResult:
    """Result of validation with errors and warnings."""

    is_valid: bool
    errors: list[ValidationError]
    warnings: list[ValidationError]


class ConnectionValidator:
    """Validates connection configurations against JSON schemas."""

    def __init__(self, mode: ValidationMode = ValidationMode.WARN):
        """Initialize validator with mode.

        Args:
            mode: Validation mode (off/warn/strict)
        """
        self.mode = mode
        self.schemas = {
            "mysql": MYSQL_CONNECTION_SCHEMA,
            "supabase": SUPABASE_CONNECTION_SCHEMA,
            "pipeline": PIPELINE_CONFIG_SCHEMA,
        }

        # Error mappings for friendly messages
        self.error_mappings = {
            ("type", "const"): {
                "why": "Connection type must match the expected value",
                "fix": "Set the 'type' field to the correct database type",
            },
            ("host", "minLength"): {
                "why": "Database host cannot be empty",
                "fix": "Provide a valid hostname or IP address",
                "example": "localhost or 192.168.1.1",
            },
            ("database", "minLength"): {
                "why": "Database name cannot be empty",
                "fix": "Provide a valid database name",
                "example": "my_database",
            },
            ("user", "minLength"): {
                "why": "Username cannot be empty",
                "fix": "Provide a valid database username",
                "example": "admin",
            },
            ("url", "format"): {
                "why": "URL must be a valid URI format",
                "fix": "Provide a valid Supabase URL",
                "example": "https://your-project.supabase.co",
            },
            ("key", "minLength"): {
                "why": "API key cannot be empty",
                "fix": "Provide a valid Supabase API key",
            },
            ("connection", "minLength"): {
                "why": "Connection reference cannot be empty",
                "fix": "Provide a valid connection reference",
                "example": "@mysql or @supabase",
            },
            ("table", "minLength"): {
                "why": "Table name cannot be empty",
                "fix": "Provide a valid table name",
                "example": "orders or users",
            },
            ("mode", "enum"): {
                "why": "Write mode must be one of the allowed values",
                "fix": "Use 'append', 'merge', or 'replace'",
                "example": "mode: append",
            },
        }

    @classmethod
    def from_env(cls) -> "ConnectionValidator":
        """Create validator with mode from environment.

        Returns:
            ConnectionValidator configured from OSIRIS_VALIDATION env var
        """
        mode_str = os.getenv("OSIRIS_VALIDATION", "warn")
        try:
            mode = ValidationMode(mode_str)
        except ValueError:
            mode = ValidationMode.WARN
        return cls(mode)

    def validate_connection(self, config: dict[str, Any]) -> ValidationResult:
        """Validate connection configuration.

        Args:
            config: Connection configuration dictionary

        Returns:
            ValidationResult with errors and warnings
        """
        if self.mode == ValidationMode.OFF:
            return ValidationResult(is_valid=True, errors=[], warnings=[])

        db_type = config.get("type")
        if not db_type:
            error = ValidationError(
                path="type",
                rule="required",
                message="Missing required field 'type'",
                why="Database type is required to validate connection",
                fix="Add 'type' field with value 'mysql' or 'supabase'",
                example="type: mysql",
            )
            return ValidationResult(is_valid=False, errors=[error], warnings=[])

        schema = self.schemas.get(db_type)
        if not schema:
            error = ValidationError(
                path="type",
                rule="unknown",
                message=f"Unknown database type: {db_type}",
                why="Only mysql and supabase are supported in MVP",
                fix="Use 'mysql' or 'supabase' as the type",
                example="type: mysql",
            )
            return ValidationResult(is_valid=False, errors=[error], warnings=[])

        return self._validate_against_schema(config, schema, "connection")

    def validate_pipeline_config(self, config: dict[str, Any]) -> ValidationResult:
        """Validate pipeline configuration.

        Args:
            config: Pipeline configuration dictionary

        Returns:
            ValidationResult with errors and warnings
        """
        if self.mode == ValidationMode.OFF:
            return ValidationResult(is_valid=True, errors=[], warnings=[])

        return self._validate_against_schema(config, PIPELINE_CONFIG_SCHEMA, "pipeline")

    def _validate_against_schema(
        self, config: dict[str, Any], schema: dict[str, Any], config_type: str
    ) -> ValidationResult:
        """Validate configuration against JSON schema.

        Args:
            config: Configuration to validate
            schema: JSON schema to validate against
            config_type: Type of configuration for error context

        Returns:
            ValidationResult with errors and warnings
        """
        try:
            from jsonschema import Draft7Validator

            validator = Draft7Validator(schema)
            errors = []

            for error in validator.iter_errors(config):
                friendly_error = self._create_friendly_error(error)
                errors.append(friendly_error)

            is_valid = len(errors) == 0
            warnings = []

            # In warn mode, convert errors to warnings
            if self.mode == ValidationMode.WARN and errors:
                warnings = errors
                errors = []
                is_valid = True

            return ValidationResult(is_valid=is_valid, errors=errors, warnings=warnings)

        except ImportError:
            # jsonschema not available - do basic validation
            return self._basic_validation(config, schema, config_type)

    def _basic_validation(self, config: dict[str, Any], schema: dict[str, Any], config_type: str) -> ValidationResult:
        """Basic validation without jsonschema library.

        Args:
            config: Configuration to validate
            schema: Schema to validate against
            config_type: Type of configuration

        Returns:
            ValidationResult with basic validation
        """
        errors = []

        # Check required fields
        required = schema.get("required", [])
        for field in required:
            if field not in config or not config[field]:
                error = ValidationError(
                    path=field,
                    rule="required",
                    message=f"Missing required field '{field}'",
                    why=f"Field '{field}' is required for {config_type} configuration",
                    fix=f"Add '{field}' field to configuration",
                )
                errors.append(error)

        is_valid = len(errors) == 0
        warnings = []

        # In warn mode, convert errors to warnings
        if self.mode == ValidationMode.WARN and errors:
            warnings = errors
            errors = []
            is_valid = True

        return ValidationResult(is_valid=is_valid, errors=errors, warnings=warnings)

    def _create_friendly_error(self, json_error) -> ValidationError:
        """Convert jsonschema error to friendly error.

        Args:
            json_error: jsonschema ValidationError

        Returns:
            ValidationError with friendly message
        """
        path = ".".join(str(p) for p in json_error.path) if json_error.path else json_error.schema_path[-1]
        rule = json_error.validator

        # Look up friendly mapping
        mapping = self.error_mappings.get((path, rule), {})
        if not mapping:
            # Special handling for additionalProperties
            if rule == "additionalProperties":
                # Extract the unexpected keys from the error message
                import re

                match = re.search(r"Additional properties are not allowed \((.*?)\)", json_error.message)
                unexpected_keys = match.group(1) if match else "unknown keys"

                # Get allowed keys from schema
                schema_props = json_error.schema.get("properties", {})
                allowed_keys = ", ".join(sorted(schema_props.keys()))

                mapping = {
                    "why": f"Configuration contains unexpected keys: {unexpected_keys}",
                    "fix": f"Remove unexpected keys or use only allowed keys: {allowed_keys}",
                    "example": None,
                }
            else:
                # Generic fallback
                mapping = {
                    "why": f"Validation rule '{rule}' failed",
                    "fix": "Check the configuration value",
                    "example": None,
                }

        return ValidationError(
            path=path,
            rule=rule,
            message=json_error.message,
            why=mapping["why"],
            fix=mapping["fix"],
            example=mapping.get("example"),
        )


def get_validation_mode() -> ValidationMode:
    """Get current validation mode from environment.

    Returns:
        Current validation mode
    """
    mode_str = os.getenv("OSIRIS_VALIDATION", "warn")
    try:
        return ValidationMode(mode_str)
    except ValueError:
        return ValidationMode.WARN


def format_validation_errors(result: ValidationResult) -> str:
    """Format validation errors for display.

    Args:
        result: ValidationResult to format

    Returns:
        Formatted error message
    """
    if result.is_valid and not result.warnings:
        return "✓ Configuration is valid"

    lines = []

    for error in result.errors:
        lines.append(f"ERROR {error.path}: {error.message}")
        lines.append(f"  Why: {error.why}")
        lines.append(f"  Fix: {error.fix}")
        if error.example:
            lines.append(f"  Example: {error.example}")
        lines.append("")

    for warning in result.warnings:
        lines.append(f"WARN  {warning.path}: {warning.message}")
        lines.append(f"  Why: {warning.why}")
        lines.append(f"  Fix: {warning.fix}")
        if warning.example:
            lines.append(f"  Example: {warning.example}")
        lines.append("")

    return "\n".join(lines)
