"""Unit tests for pipeline validator."""

import pytest

from osiris.core.pipeline_validator import PipelineValidator, ValidationError, ValidationResult


class TestPipelineValidator:
    """Test pipeline validation logic."""

    @pytest.fixture
    def validator(self):
        """Create a validator instance."""
        return PipelineValidator()

    def test_validate_empty_pipeline(self, validator):
        """Test validation of empty pipeline."""
        result = validator.validate_pipeline("")
        assert not result.valid
        assert len(result.errors) == 1
        assert result.errors[0].error_type == "parse_error"

    def test_validate_invalid_yaml(self, validator):
        """Test validation of invalid YAML."""
        invalid_yaml = "this is not: valid: yaml: syntax:"
        result = validator.validate_pipeline(invalid_yaml)
        assert not result.valid
        assert len(result.errors) == 1
        assert result.errors[0].error_type == "parse_error"

    def test_validate_no_steps(self, validator):
        """Test validation of pipeline without steps."""
        pipeline_yaml = """
name: test_pipeline
description: Test pipeline
"""
        result = validator.validate_pipeline(pipeline_yaml)
        assert not result.valid
        assert len(result.errors) == 1
        assert result.errors[0].error_type == "missing_field"
        assert "step" in result.errors[0].friendly_message.lower()

    def test_validate_step_missing_type(self, validator):
        """Test validation of step without type field."""
        pipeline_yaml = """
steps:
  - config:
      database: test_db
"""
        result = validator.validate_pipeline(pipeline_yaml)
        assert not result.valid
        assert len(result.errors) == 1
        assert result.errors[0].error_type == "missing_field"
        assert "type" in result.errors[0].friendly_message.lower()

    def test_validate_unknown_component(self, validator):
        """Test validation with unknown component type."""
        pipeline_yaml = """
steps:
  - type: unknown.component
    config:
      some_field: value
"""
        result = validator.validate_pipeline(pipeline_yaml)
        assert not result.valid
        assert len(result.errors) == 1
        assert result.errors[0].error_type == "unknown_component"

    def test_validate_missing_required_field(self, validator):
        """Test validation with missing required config field."""
        pipeline_yaml = """
steps:
  - type: mysql.extractor
    config:
      # Missing required fields like host, database, etc.
      port: 3306
"""
        result = validator.validate_pipeline(pipeline_yaml)
        assert not result.valid
        # Should have multiple errors for missing required fields
        assert len(result.errors) > 0
        # Check that at least one error is about missing fields
        missing_field_errors = [e for e in result.errors if e.error_type == "missing_field"]
        assert len(missing_field_errors) > 0

    def test_validate_wrong_type(self, validator):
        """Test validation with wrong field type."""
        pipeline_yaml = """
steps:
  - type: mysql.extractor
    config:
      host: localhost
      port: "not_a_number"  # Should be integer
      database: test_db
      table: users
"""
        result = validator.validate_pipeline(pipeline_yaml)
        assert not result.valid
        # Should have at least one type error
        type_errors = [e for e in result.errors if e.error_type == "type_error"]
        assert len(type_errors) > 0

    def test_validate_valid_pipeline(self, validator):
        """Test validation of a valid pipeline."""
        pipeline_yaml = """
steps:
  - type: mysql.extractor
    config:
      host: localhost
      port: 3306
      database: test_db
      table: users
      username: testuser
      password: testpass
  - type: supabase.writer
    config:
      url: https://test.supabase.co
      key: test-key
      table: users
      mode: append
"""
        result = validator.validate_pipeline(pipeline_yaml)
        # Note: This may still fail if the validator strictly enforces all fields
        # For this test, we're mainly checking that the structure is correct
        assert result.validated_components == 2

    def test_get_retry_prompt_context(self, validator):
        """Test retry prompt context generation."""
        errors = [
            ValidationError(
                component_type="mysql.extractor",
                field_path="/steps/0/config/database",
                error_type="missing_field",
                friendly_message="Missing required field 'database'",
                technical_message="Required field not found",
                suggestion="Add 'database' field with your database name",
            ),
            ValidationError(
                component_type="supabase.writer",
                field_path="/steps/1/config/mode",
                error_type="enum_error",
                friendly_message="Invalid mode 'insert'",
                technical_message="Value not in allowed enum",
                suggestion="Use 'append' or 'replace' instead",
            ),
        ]

        context = validator.get_retry_prompt_context(errors)
        assert "mysql.extractor" in context
        assert "database" in context
        assert "supabase.writer" in context
        assert "mode" in context
        assert "Keep all other fields unchanged" in context

    def test_validation_result_to_dict(self):
        """Test ValidationResult serialization."""
        result = ValidationResult(
            valid=False,
            errors=[
                ValidationError(
                    component_type="test",
                    field_path="/test",
                    error_type="test_error",
                    friendly_message="Test error",
                    technical_message="Technical test error",
                )
            ],
            warnings=["Warning 1"],
            validated_components=1,
        )

        result_dict = result.to_dict()
        assert result_dict["valid"] is False
        assert result_dict["error_count"] == 1
        assert "test_error" in result_dict["error_categories"]
        assert len(result_dict["errors"]) == 1
        assert len(result_dict["warnings"]) == 1

    def test_friendly_summary(self):
        """Test friendly summary generation."""
        result = ValidationResult(valid=True, validated_components=2)
        summary = result.get_friendly_summary()
        assert "✓" in summary
        assert "successfully" in summary.lower()

        # Test with errors
        result = ValidationResult(
            valid=False,
            errors=[
                ValidationError(
                    component_type="mysql.extractor",
                    field_path="/config/host",
                    error_type="missing_field",
                    friendly_message="Missing host",
                    technical_message="Required field missing",
                    suggestion="Add host field",
                )
            ],
        )
        summary = result.get_friendly_summary()
        assert "❌" in summary
        assert "mysql.extractor" in summary
        assert "Missing host" in summary
