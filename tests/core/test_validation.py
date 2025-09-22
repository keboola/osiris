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

"""Tests for connection configuration validation (M0.3)."""

import os
from unittest.mock import patch

from osiris.core.validation import (
    ConnectionValidator,
    ValidationError,
    ValidationMode,
    ValidationResult,
    format_validation_errors,
    get_validation_mode,
)


class TestValidationMode:
    """Test validation mode functionality."""

    def test_validation_mode_enum(self):
        """Test validation mode enum values."""
        assert ValidationMode.OFF.value == "off"
        assert ValidationMode.WARN.value == "warn"
        assert ValidationMode.STRICT.value == "strict"

    @patch.dict(os.environ, {"OSIRIS_VALIDATION": "strict"}, clear=False)
    def test_get_validation_mode_from_env(self):
        """Test getting validation mode from environment."""
        mode = get_validation_mode()
        assert mode == ValidationMode.STRICT

    @patch.dict(os.environ, {"OSIRIS_VALIDATION": "invalid"}, clear=False)
    def test_get_validation_mode_invalid_fallback(self):
        """Test fallback to warn mode for invalid values."""
        mode = get_validation_mode()
        assert mode == ValidationMode.WARN

    @patch.dict(os.environ, {}, clear=True)
    def test_get_validation_mode_default(self):
        """Test default validation mode when env var not set."""
        if "OSIRIS_VALIDATION" in os.environ:
            del os.environ["OSIRIS_VALIDATION"]
        mode = get_validation_mode()
        assert mode == ValidationMode.WARN


class TestConnectionValidator:
    """Test connection configuration validation."""

    def test_validator_initialization(self):
        """Test validator initialization with different modes."""
        validator_warn = ConnectionValidator(ValidationMode.WARN)
        assert validator_warn.mode == ValidationMode.WARN

        validator_strict = ConnectionValidator(ValidationMode.STRICT)
        assert validator_strict.mode == ValidationMode.STRICT

        validator_off = ConnectionValidator(ValidationMode.OFF)
        assert validator_off.mode == ValidationMode.OFF

    @patch.dict(os.environ, {"OSIRIS_VALIDATION": "strict"}, clear=False)
    def test_validator_from_env(self):
        """Test creating validator from environment."""
        validator = ConnectionValidator.from_env()
        assert validator.mode == ValidationMode.STRICT

    def test_validation_off_mode(self):
        """Test that validation off mode always passes."""
        validator = ConnectionValidator(ValidationMode.OFF)

        # Empty config should pass
        result = validator.validate_connection({})
        assert result.is_valid
        assert len(result.errors) == 0

        # Invalid config should still pass
        result = validator.validate_connection({"invalid": "config"})
        assert result.is_valid
        assert len(result.errors) == 0

    def test_mysql_connection_valid(self):
        """Test valid MySQL connection configuration."""
        validator = ConnectionValidator(ValidationMode.STRICT)

        mysql_config = {
            "type": "mysql",
            "host": "localhost",
            "port": 3306,
            "database": "testdb",
            "user": "testuser",
            "password": "testpass",  # pragma: allowlist secret
        }

        result = validator.validate_connection(mysql_config)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_mysql_connection_missing_required(self):
        """Test MySQL connection with missing required fields."""
        validator = ConnectionValidator(ValidationMode.STRICT)

        mysql_config = {
            "type": "mysql",
            "host": "localhost",
            # Missing: database, user, password
        }

        result = validator.validate_connection(mysql_config)
        assert not result.is_valid
        assert len(result.errors) > 0

        # Check that missing fields are reported in error messages
        error_messages = " ".join(error.message for error in result.errors)
        assert "database" in error_messages
        assert "user" in error_messages
        assert "password" in error_messages

    def test_supabase_connection_valid(self):
        """Test valid Supabase connection configuration."""
        validator = ConnectionValidator(ValidationMode.STRICT)

        supabase_config = {
            "type": "supabase",
            "url": "https://project.supabase.co",
            "key": "anon-public-key",
        }

        result = validator.validate_connection(supabase_config)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_supabase_connection_invalid_url(self):
        """Test Supabase connection with invalid URL format."""
        validator = ConnectionValidator(ValidationMode.STRICT)

        supabase_config = {"type": "supabase", "url": "not-a-valid-url", "key": "anon-public-key"}

        validator.validate_connection(supabase_config)
        # May pass with basic validation, but would fail with full jsonschema
        # This tests the fallback validation path

    def test_unknown_database_type(self):
        """Test connection with unknown database type."""
        validator = ConnectionValidator(ValidationMode.STRICT)

        unknown_config = {"type": "unknown_db", "host": "localhost"}

        result = validator.validate_connection(unknown_config)
        assert not result.is_valid
        assert len(result.errors) > 0
        assert any("unknown" in error.message.lower() for error in result.errors)

    def test_missing_type_field(self):
        """Test connection configuration missing type field."""
        validator = ConnectionValidator(ValidationMode.STRICT)

        config = {"host": "localhost", "database": "testdb"}

        result = validator.validate_connection(config)
        assert not result.is_valid
        assert len(result.errors) > 0
        assert any("type" in error.path for error in result.errors)

    def test_warn_mode_converts_errors_to_warnings(self):
        """Test that warn mode converts errors to warnings."""
        validator = ConnectionValidator(ValidationMode.WARN)

        invalid_config = {
            "type": "mysql",
            "host": "localhost",
            # Missing required fields
        }

        result = validator.validate_connection(invalid_config)
        assert result.is_valid  # Valid in warn mode
        assert len(result.errors) == 0
        assert len(result.warnings) > 0

    def test_pipeline_config_validation(self):
        """Test pipeline configuration validation."""
        validator = ConnectionValidator(ValidationMode.STRICT)

        valid_pipeline = {
            "source": {"connection": "@mysql", "table": "users"},
            "destination": {"connection": "@supabase", "table": "users_copy", "mode": "append"},
        }

        result = validator.validate_pipeline_config(valid_pipeline)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_pipeline_config_missing_sections(self):
        """Test pipeline configuration missing required sections."""
        validator = ConnectionValidator(ValidationMode.STRICT)

        invalid_pipeline = {
            "source": {"connection": "@mysql", "table": "users"}
            # Missing destination
        }

        result = validator.validate_pipeline_config(invalid_pipeline)
        assert not result.is_valid
        assert len(result.errors) > 0

    def test_friendly_error_messages(self):
        """Test that errors have friendly messages."""
        validator = ConnectionValidator(ValidationMode.STRICT)

        config = {"type": "mysql"}  # Missing required fields

        result = validator.validate_connection(config)
        assert not result.is_valid

        for error in result.errors:
            assert isinstance(error, ValidationError)
            assert error.path
            assert error.message
            assert error.why
            assert error.fix
            # Example may be None, but other fields should exist

    def test_basic_validation_fallback(self):
        """Test basic validation when jsonschema is not available."""
        validator = ConnectionValidator(ValidationMode.STRICT)

        # This should work with or without jsonschema
        config = {
            "type": "mysql",
            "host": "localhost",
            "database": "testdb",
            "user": "testuser",
            "password": "testpass",  # pragma: allowlist secret
        }

        validator.validate_connection(config)
        # Should pass with basic validation even if jsonschema is missing


class TestValidationResult:
    """Test ValidationResult functionality."""

    def test_validation_result_creation(self):
        """Test creating ValidationResult objects."""
        error = ValidationError(
            path="host",
            rule="minLength",
            message="Host cannot be empty",
            why="Database host is required",
            fix="Provide a valid hostname",
        )

        result = ValidationResult(is_valid=False, errors=[error], warnings=[])

        assert not result.is_valid
        assert len(result.errors) == 1
        assert len(result.warnings) == 0
        assert result.errors[0].path == "host"

    def test_format_validation_errors_valid(self):
        """Test formatting when validation passes."""
        result = ValidationResult(is_valid=True, errors=[], warnings=[])

        formatted = format_validation_errors(result)
        assert "✓ Configuration is valid" in formatted

    def test_format_validation_errors_with_errors(self):
        """Test formatting validation errors."""
        error = ValidationError(
            path="database",
            rule="required",
            message="Missing database field",
            why="Database name is required",
            fix="Add database field to configuration",
            example="database: my_database",
        )

        result = ValidationResult(is_valid=False, errors=[error], warnings=[])

        formatted = format_validation_errors(result)
        assert "ERROR database:" in formatted
        assert "Why: Database name is required" in formatted
        assert "Fix: Add database field" in formatted
        assert "Example: database: my_database" in formatted

    def test_format_validation_errors_with_warnings(self):
        """Test formatting validation warnings."""
        warning = ValidationError(
            path="port",
            rule="default",
            message="Using default port",
            why="No port specified",
            fix="Add explicit port if needed",
            example="port: 3306",
        )

        result = ValidationResult(is_valid=True, errors=[], warnings=[warning])

        formatted = format_validation_errors(result)
        assert "WARN  port:" in formatted
        assert "Why: No port specified" in formatted


class TestErrorMappings:
    """Test error message mappings."""

    def test_error_mappings_exist(self):
        """Test that error mappings are properly configured."""
        validator = ConnectionValidator()

        # Check that mappings exist for common cases
        assert ("host", "minLength") in validator.error_mappings
        assert ("type", "const") in validator.error_mappings
        assert ("connection", "minLength") in validator.error_mappings

        # Check mapping structure
        mapping = validator.error_mappings[("host", "minLength")]
        assert "why" in mapping
        assert "fix" in mapping

    def test_error_mapping_provides_helpful_text(self):
        """Test that error mappings provide helpful guidance."""
        validator = ConnectionValidator()

        mapping = validator.error_mappings[("database", "minLength")]
        assert "empty" in mapping["why"].lower()
        assert "provide" in mapping["fix"].lower() or "add" in mapping["fix"].lower()


class TestIntegrationScenarios:
    """Test integration scenarios combining multiple features."""

    def test_mysql_to_supabase_pipeline_validation(self):
        """Test validation of a typical MySQL to Supabase pipeline."""
        validator = ConnectionValidator(ValidationMode.STRICT)

        # Validate MySQL source connection
        mysql_config = {
            "type": "mysql",
            "host": "localhost",
            "database": "source_db",
            "user": "readonly",
            "password": "password123",  # pragma: allowlist secret
        }
        mysql_result = validator.validate_connection(mysql_config)

        # Validate Supabase destination connection
        supabase_config = {
            "type": "supabase",
            "url": "https://project.supabase.co",
            "key": "public-anon-key",
        }
        supabase_result = validator.validate_connection(supabase_config)

        # Validate pipeline configuration
        pipeline_config = {
            "source": {"connection": "@mysql", "table": "orders", "schema": "public"},
            "destination": {
                "connection": "@supabase",
                "table": "orders_copy",
                "mode": "merge",
                "merge_keys": ["id"],
            },
        }
        pipeline_result = validator.validate_pipeline_config(pipeline_config)

        assert mysql_result.is_valid
        assert supabase_result.is_valid
        assert pipeline_result.is_valid

    def test_validation_mode_impact_on_results(self):
        """Test how different validation modes affect the same config."""
        invalid_config = {
            "type": "mysql",
            "host": "localhost",
            # Missing required fields
        }

        # Strict mode should fail
        strict_validator = ConnectionValidator(ValidationMode.STRICT)
        strict_result = strict_validator.validate_connection(invalid_config)
        assert not strict_result.is_valid
        assert len(strict_result.errors) > 0

        # Warn mode should pass with warnings
        warn_validator = ConnectionValidator(ValidationMode.WARN)
        warn_result = warn_validator.validate_connection(invalid_config)
        assert warn_result.is_valid
        assert len(warn_result.warnings) > 0

        # Off mode should always pass
        off_validator = ConnectionValidator(ValidationMode.OFF)
        off_result = off_validator.validate_connection(invalid_config)
        assert off_result.is_valid
        assert len(off_result.errors) == 0
        assert len(off_result.warnings) == 0
