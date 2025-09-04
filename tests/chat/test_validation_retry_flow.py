"""Integration tests for validation retry flow in chat."""

import json
from unittest.mock import patch

import pytest

from osiris.core.pipeline_validator import ValidationError, ValidationResult
from osiris.core.validation_retry import RetryAttempt, RetryTrail, ValidationRetryManager


class TestValidationRetryFlow:
    """Test validation and retry flow integration."""

    @pytest.fixture
    def mock_config(self):
        """Create mock configuration."""
        return {
            "validation": {
                "retry": {
                    "max_attempts": 2,
                    "include_history_in_hitl": True,
                    "history_limit": 3,
                    "diff_format": "patch",
                }
            }
        }

    @pytest.fixture
    def valid_pipeline(self):
        """Create a valid pipeline YAML."""
        return """
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

    @pytest.fixture
    def invalid_pipeline(self):
        """Create an invalid pipeline YAML."""
        return """
steps:
  - type: mysql.extractor
    config:
      # Missing required fields
      port: 3306
  - type: supabase.writer
    config:
      url: https://test.supabase.co
      # Invalid mode
      mode: insert
"""

    def test_retry_manager_init(self, mock_config):
        """Test ValidationRetryManager initialization."""
        manager = ValidationRetryManager.from_config(mock_config)
        assert manager.max_attempts == 2
        assert manager.include_history_in_hitl is True
        assert manager.history_limit == 3
        assert manager.diff_format == "patch"

    def test_retry_manager_max_attempts_bounds(self):
        """Test that max_attempts is bounded to 0-5."""
        manager = ValidationRetryManager(max_attempts=-1)
        assert manager.max_attempts == 0

        manager = ValidationRetryManager(max_attempts=10)
        assert manager.max_attempts == 5

        manager = ValidationRetryManager(max_attempts=3)
        assert manager.max_attempts == 3

    @pytest.mark.asyncio
    async def test_validate_with_retry_success(self, valid_pipeline):
        """Test successful validation without retry."""
        manager = ValidationRetryManager(max_attempts=2)

        # Mock validator to return success
        with patch.object(manager.validator, "validate_pipeline") as mock_validate:
            mock_validate.return_value = ValidationResult(valid=True, validated_components=2)

            success, result, trail = manager.validate_with_retry(valid_pipeline)

            assert success is True
            assert result.valid is True
            assert len(trail.attempts) == 1
            assert trail.final_status == "success"

    @pytest.mark.asyncio
    async def test_validate_with_retry_fixes_on_first_retry(self, invalid_pipeline, valid_pipeline):
        """Test validation that succeeds on first retry."""
        manager = ValidationRetryManager(max_attempts=2)

        # Mock validator to fail first, then succeed
        validation_results = [
            ValidationResult(
                valid=False,
                errors=[
                    ValidationError(
                        component_type="mysql.extractor",
                        field_path="/config/database",
                        error_type="missing_field",
                        friendly_message="Missing database",
                        technical_message="Required field",
                    )
                ],
            ),
            ValidationResult(valid=True, validated_components=2),
        ]

        with patch.object(manager.validator, "validate_pipeline") as mock_validate:
            mock_validate.side_effect = validation_results

            # Mock retry callback
            async def mock_retry_callback(yaml_str, error_ctx, attempt):
                return valid_pipeline, {"total_tokens": 100}

            success, result, trail = manager.validate_with_retry(
                invalid_pipeline, retry_callback=mock_retry_callback
            )

            assert success is True
            assert len(trail.attempts) == 2
            assert trail.attempts[0].validation_result.valid is False
            assert trail.attempts[1].validation_result.valid is True
            assert trail.final_status == "success"

    @pytest.mark.asyncio
    async def test_validate_with_retry_all_fail(self, invalid_pipeline):
        """Test validation that fails after all retries."""
        manager = ValidationRetryManager(max_attempts=2)

        # Mock validator to always fail
        validation_result = ValidationResult(
            valid=False,
            errors=[
                ValidationError(
                    component_type="mysql.extractor",
                    field_path="/config/database",
                    error_type="missing_field",
                    friendly_message="Missing database",
                    technical_message="Required field",
                )
            ],
        )

        with patch.object(manager.validator, "validate_pipeline") as mock_validate:
            mock_validate.return_value = validation_result

            # Mock retry callback that also produces invalid YAML
            async def mock_retry_callback(yaml_str, error_ctx, attempt):
                return invalid_pipeline, {"total_tokens": 100}

            success, result, trail = manager.validate_with_retry(
                invalid_pipeline, retry_callback=mock_retry_callback
            )

            assert success is False
            assert len(trail.attempts) == 3  # Initial + 2 retries
            assert all(not a.validation_result.valid for a in trail.attempts)
            assert trail.final_status == "failed"

    def test_retry_attempt_summary(self):
        """Test retry attempt summary generation."""
        attempt = RetryAttempt(
            attempt_number=1,
            pipeline_yaml="test",
            validation_result=ValidationResult(valid=True),
            token_usage={"total": 100},
            duration_ms=500,
        )

        summary = attempt.get_summary()
        assert "✓ Success" in summary

        # Test with errors
        attempt = RetryAttempt(
            attempt_number=2,
            pipeline_yaml="test",
            validation_result=ValidationResult(
                valid=False,
                errors=[
                    ValidationError(
                        component_type="mysql.extractor",
                        field_path="/config",
                        error_type="missing_field",
                        friendly_message="Missing database field",
                        technical_message="Required",
                    )
                ],
            ),
        )

        summary = attempt.get_summary()
        assert "❌ Failed" in summary
        assert "mysql.extractor" in summary

    def test_retry_trail_hitl_summary(self):
        """Test HITL summary generation."""
        trail = RetryTrail()

        # Add some attempts
        for i in range(3):
            trail.add_attempt(
                RetryAttempt(
                    attempt_number=i + 1,
                    pipeline_yaml="test",
                    validation_result=ValidationResult(
                        valid=False,
                        errors=[
                            ValidationError(
                                component_type=f"component_{i}",
                                field_path="/config",
                                error_type="error",
                                friendly_message=f"Error {i}",
                                technical_message="Tech error",
                            )
                        ],
                    ),
                    token_usage={"total": 100},
                    duration_ms=500,
                )
            )

        summary = trail.get_hitl_summary(history_limit=2)
        assert "Retry History" in summary
        assert "Total tokens used: 300" in summary
        assert "Showing last 2 of 3 attempts" in summary

    def test_retry_trail_artifacts(self, tmp_path):
        """Test saving retry trail artifacts."""
        session_dir = tmp_path / "test_session"
        session_dir.mkdir()

        trail = RetryTrail()

        # Add attempts with different pipelines
        pipeline1 = "steps:\n  - type: test1"
        pipeline2 = "steps:\n  - type: test2"

        trail.add_attempt(
            RetryAttempt(
                attempt_number=1,
                pipeline_yaml=pipeline1,
                validation_result=ValidationResult(valid=False, errors=[]),
            )
        )

        trail.add_attempt(
            RetryAttempt(
                attempt_number=2,
                pipeline_yaml=pipeline2,
                validation_result=ValidationResult(valid=True),
            )
        )

        # Save artifacts
        trail.save_artifacts(session_dir)

        # Check artifacts were created
        artifacts_dir = session_dir / "artifacts" / "retries"
        assert artifacts_dir.exists()

        # Check attempt directories
        attempt1_dir = artifacts_dir / "attempt_1"
        assert attempt1_dir.exists()
        assert (attempt1_dir / "pipeline.yaml").exists()
        assert (attempt1_dir / "errors.json").exists()

        attempt2_dir = artifacts_dir / "attempt_2"
        assert attempt2_dir.exists()
        assert (attempt2_dir / "patch.json").exists()  # Should have patch for second attempt

        # Check summary
        summary_file = session_dir / "artifacts" / "summary" / "retry_trail.json"
        assert summary_file.exists()

        with open(summary_file) as f:
            summary_data = json.load(f)
            assert summary_data["total_attempts"] == 2
            assert summary_data["final_status"] == "success"

    def test_hitl_prompt_generation(self):
        """Test HITL prompt generation."""
        manager = ValidationRetryManager(
            max_attempts=2, include_history_in_hitl=True, history_limit=3
        )

        # Create a retry trail with failures
        trail = RetryTrail()
        trail.add_attempt(
            RetryAttempt(
                attempt_number=1,
                pipeline_yaml="test",
                validation_result=ValidationResult(
                    valid=False,
                    errors=[
                        ValidationError(
                            component_type="mysql.extractor",
                            field_path="/config/database",
                            error_type="missing_field",
                            friendly_message="Missing database field",
                            technical_message="Required field",
                        )
                    ],
                ),
            )
        )

        manager.retry_trail = trail
        prompt = manager.get_hitl_prompt()

        assert "Automatic validation failed" in prompt
        assert "Retry History" in prompt
        assert "mysql.extractor" in prompt
        assert "provide additional information" in prompt.lower()

    def test_hitl_prompt_without_history(self):
        """Test HITL prompt without history."""
        manager = ValidationRetryManager(max_attempts=2, include_history_in_hitl=False)

        trail = RetryTrail()
        trail.add_attempt(
            RetryAttempt(
                attempt_number=1,
                pipeline_yaml="test",
                validation_result=ValidationResult(valid=False, errors=[]),
            )
        )

        manager.retry_trail = trail
        prompt = manager.get_hitl_prompt()

        assert "Automatic validation failed" in prompt
        assert "Retry History" not in prompt

    @pytest.mark.asyncio
    async def test_strict_mode_no_retry(self, invalid_pipeline):
        """Test strict mode with max_attempts=0."""
        manager = ValidationRetryManager(max_attempts=0)

        validation_result = ValidationResult(
            valid=False,
            errors=[
                ValidationError(
                    component_type="test",
                    field_path="/test",
                    error_type="error",
                    friendly_message="Error",
                    technical_message="Error",
                )
            ],
        )

        with patch.object(manager.validator, "validate_pipeline") as mock_validate:
            mock_validate.return_value = validation_result

            success, result, trail = manager.validate_with_retry(invalid_pipeline)

            assert success is False
            assert len(trail.attempts) == 1  # Only initial attempt, no retries
            assert trail.final_status == "failed"
