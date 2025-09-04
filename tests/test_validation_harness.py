"""Pytest tests for automated validation test harness.

These tests ensure the validation test harness correctly runs scenarios
and produces expected artifacts without secrets leakage.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest


class TestValidationHarness:
    """Test suite for validation test harness."""

    @pytest.fixture
    def artifacts_dir(self, tmp_path):
        """Create temporary artifacts directory."""
        return tmp_path / "test_artifacts"

    def run_osiris_test(self, scenario: str, output_dir: Path) -> subprocess.CompletedProcess:
        """Run osiris test validation command."""
        cmd = [
            sys.executable,
            "osiris.py",
            "test",
            "validation",
            "--scenario",
            scenario,
            "--out",
            str(output_dir),
        ]
        return subprocess.run(cmd, capture_output=True, text=True)

    def test_valid_scenario(self, artifacts_dir):
        """Test that valid scenario passes on first attempt."""
        output_dir = artifacts_dir / "valid"
        result = self.run_osiris_test("valid", output_dir)

        # Check exit code
        assert result.returncode == 0, f"Valid scenario should pass. Output: {result.stdout}"

        # Check result.json exists and is correct
        result_file = output_dir / "result.json"
        assert result_file.exists(), "result.json should be created"

        with open(result_file) as f:
            result_data = json.load(f)

        assert result_data["scenario"] == "valid"
        assert result_data["status"] == "success"
        assert result_data["return_code"] == 0, "Return code should be 0"
        assert result_data["attempts"] == 1, "Valid scenario should pass on first attempt"
        assert len(result_data["errors"]) == 0

        # Check retry trail
        retry_trail_file = output_dir / "retry_trail.json"
        assert retry_trail_file.exists(), "retry_trail.json should be created"

        with open(retry_trail_file) as f:
            retry_trail = json.load(f)

        assert len(retry_trail["attempts"]) == 1
        assert retry_trail["attempts"][0]["valid"] is True, "First attempt should be valid"

        # Check no secrets in artifacts
        self._check_no_secrets(output_dir)

    def test_broken_scenario(self, artifacts_dir):
        """Test that broken scenario is fixed after retry."""
        output_dir = artifacts_dir / "broken"
        result = self.run_osiris_test("broken", output_dir)

        # Check exit code
        assert result.returncode == 0, f"Broken scenario should be fixed. Output: {result.stdout}"

        # Check result.json
        result_file = output_dir / "result.json"
        assert result_file.exists()

        with open(result_file) as f:
            result_data = json.load(f)

        assert result_data["scenario"] == "broken"
        assert result_data["status"] == "success"
        assert result_data["return_code"] == 0, "Return code should be 0 for success"
        assert result_data["attempts"] == 2, "Broken scenario should be fixed on retry"

        # Check retry trail exists
        retry_trail_file = output_dir / "retry_trail.json"
        assert retry_trail_file.exists(), "retry_trail.json should be created"

        with open(retry_trail_file) as f:
            retry_trail = json.load(f)

        assert len(retry_trail["attempts"]) == 2
        assert retry_trail["attempts"][0]["valid"] is False
        assert retry_trail["attempts"][1]["valid"] is True

        # Check attempt artifacts are in artifacts subdirectory
        artifacts_dir = output_dir / "artifacts"
        assert artifacts_dir.exists(), "artifacts subdirectory should exist"

        attempt1_dir = artifacts_dir / "attempt_1"
        assert attempt1_dir.exists()
        assert (attempt1_dir / "pipeline.yaml").exists()
        assert (attempt1_dir / "errors.json").exists()

        attempt2_dir = artifacts_dir / "attempt_2"
        assert attempt2_dir.exists()
        assert (attempt2_dir / "pipeline.yaml").exists()

        # Check no secrets
        self._check_no_secrets(output_dir)

    def test_unfixable_scenario(self, artifacts_dir):
        """Test that unfixable scenario fails after max attempts."""
        output_dir = artifacts_dir / "unfixable"
        # Run with --max-attempts 3 to get 3 total attempts (1 initial + 2 retries)
        cmd = [
            sys.executable,
            "osiris.py",
            "test",
            "validation",
            "--scenario",
            "unfixable",
            "--out",
            str(output_dir),
            "--max-attempts",
            "3",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Check exit code (should fail with code 1)
        assert result.returncode == 1, f"Unfixable scenario should fail. Output: {result.stdout}"

        # Check result.json
        result_file = output_dir / "result.json"
        assert result_file.exists()

        with open(result_file) as f:
            result_data = json.load(f)

        assert result_data["scenario"] == "unfixable"
        assert result_data["status"] == "failed"
        assert result_data["return_code"] == 1, "Return code should be 1 for failed scenario"
        assert result_data["attempts"] == 3, "Should have 3 total attempts"
        assert len(result_data["errors"]) > 0, "Should have errors"

        # Check error details
        errors = result_data["errors"]
        error_types = {e["type"] for e in errors}
        assert "unknown_component" in error_types or "invalid_component" in error_types

        # Check retry trail
        retry_trail_file = output_dir / "retry_trail.json"
        assert retry_trail_file.exists()

        with open(retry_trail_file) as f:
            retry_trail = json.load(f)

        # Check that all attempts are invalid
        assert all(
            not attempt["valid"] for attempt in retry_trail["attempts"]
        ), "All attempts should be invalid"
        assert retry_trail["attempts"][-1]["valid"] is False, "Last attempt should be invalid"
        assert retry_trail["final_status"] == "failed"

        # Check each failed attempt has errors.json in artifacts subdirectory
        artifacts_dir = output_dir / "artifacts"
        assert artifacts_dir.exists(), "artifacts subdirectory should exist"

        for i in range(1, len(retry_trail["attempts"]) + 1):
            attempt_dir = artifacts_dir / f"attempt_{i}"
            assert attempt_dir.exists(), f"Attempt {i} directory should exist"
            errors_file = attempt_dir / "errors.json"
            assert errors_file.exists(), f"Attempt {i} should have errors.json"

        # Check no secrets
        self._check_no_secrets(output_dir)

    def test_all_scenarios(self, artifacts_dir):
        """Test running all scenarios at once."""
        result = self.run_osiris_test("all", artifacts_dir)

        # All scenarios together should fail (unfixable fails)
        assert result.returncode == 1

        # Check each scenario directory exists
        for scenario in ["valid", "broken", "unfixable"]:
            scenario_dir = artifacts_dir / scenario
            assert scenario_dir.exists(), f"{scenario} directory should exist"
            assert (scenario_dir / "result.json").exists()

    def test_max_attempts_override(self, artifacts_dir):
        """Test that max-attempts flag overrides default."""
        output_dir = artifacts_dir / "max_attempts_test"

        # Run with max-attempts=1 (only initial attempt, no retries)
        cmd = [
            sys.executable,
            "osiris.py",
            "test",
            "validation",
            "--scenario",
            "broken",
            "--out",
            str(output_dir),
            "--max-attempts",
            "1",  # Only initial attempt, no retries
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Should fail because no retries allowed
        assert result.returncode == 1

        # Check only 1 attempt was made
        result_file = output_dir / "result.json"
        if result_file.exists():
            with open(result_file) as f:
                result_data = json.load(f)
            assert result_data["attempts"] == 1

    def test_console_output_format(self, artifacts_dir):
        """Test that console output is clean and formatted correctly."""
        output_dir = artifacts_dir / "console_test"
        result = self.run_osiris_test("valid", output_dir)

        # Check for expected output elements
        assert "Running scenario: valid" in result.stdout
        assert "Validation Attempts" in result.stdout  # Table title
        assert "✓" in result.stdout or "Valid" in result.stdout  # Success indicator
        assert "Scenario passed expectations" in result.stdout

        # No verbose logs by default
        assert "DEBUG" not in result.stdout
        assert "TRACE" not in result.stdout

    def test_no_console_warnings_in_default_mode(self, artifacts_dir):
        """Test that error mapping warnings don't appear in console output."""
        output_dir = artifacts_dir / "no_warnings"
        cmd = [
            sys.executable,
            "osiris.py",
            "test",
            "validation",
            "--scenario",
            "unfixable",
            "--out",
            str(output_dir),
            "--max-attempts",
            "1",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Check that "Failed to map error" doesn't appear
        assert "Failed to map error" not in result.stdout
        assert "Failed to map error" not in result.stderr
        assert "WARNING: Failed to map" not in result.stdout

    def test_artifacts_structure(self, artifacts_dir):
        """Test that artifacts are structured correctly."""
        output_dir = artifacts_dir / "structure_test"
        self.run_osiris_test("broken", output_dir)

        # Check directory structure
        assert output_dir.exists()
        assert (output_dir / "result.json").exists()
        assert (output_dir / "retry_trail.json").exists()

        # Check attempt directories in artifacts subdirectory
        artifacts_dir = output_dir / "artifacts"
        assert artifacts_dir.exists(), "artifacts subdirectory should exist"

        for i in range(1, 3):  # 2 attempts for broken scenario
            attempt_dir = artifacts_dir / f"attempt_{i}"
            assert attempt_dir.exists()
            assert (attempt_dir / "pipeline.yaml").exists()

            # First attempt should have errors
            if i == 1:
                assert (attempt_dir / "errors.json").exists()

    def _check_no_secrets(self, output_dir: Path):
        """Check that no secrets are present in output files."""
        # These are actual secret values that should never appear
        # (excluding test fixture comments like "hardcoded_password_violation")
        secret_patterns = [
            '"secret123"',  # Actual secret value in quotes
            '"key123"',  # Actual key value in quotes
            '"password123"',  # Actual password in quotes
            '"my_secret"',  # Actual secret in quotes
            "api_token: secret",  # Key-value pattern
        ]

        # Check all JSON and YAML files
        for file_path in output_dir.rglob("*.json"):
            content = file_path.read_text()
            for pattern in secret_patterns:
                assert pattern not in content, f"Secret '{pattern}' found in {file_path}"

        for file_path in output_dir.rglob("*.yaml"):
            content = file_path.read_text()
            # Allow {{ secrets.xxx }} patterns and comments, but not actual hardcoded values
            for pattern in secret_patterns:
                # Skip if it's in a template or comment line
                if "{{" not in pattern and not pattern.startswith("#"):
                    assert pattern not in content, f"Secret '{pattern}' found in {file_path}"


@pytest.mark.integration
class TestValidationHarnessIntegration:
    """Integration tests for validation harness with actual components."""

    def test_with_real_validator(self):
        """Test harness with real pipeline validator."""
        from osiris.core.test_harness import ValidationTestHarness

        harness = ValidationTestHarness()

        # Run valid scenario
        success, result = harness.run_scenario("valid")
        assert success is True
        assert result["status"] == "success"
        assert result["attempts"] == 1

    def test_retry_mechanism(self):
        """Test that retry mechanism works correctly."""
        from osiris.core.test_harness import ValidationTestHarness

        harness = ValidationTestHarness(max_attempts=2)

        # Run broken scenario
        success, result = harness.run_scenario("broken")
        assert success is True
        assert result["attempts"] == 2

        # Verify retry history
        retry_history = result["retry_history"]
        assert len(retry_history["attempts"]) == 2
        assert retry_history["final_status"] == "success"


class TestLogsRedaction:
    """Test logs redaction policy."""

    def test_logs_list_not_masking_session_id(self):
        """Test that logs list doesn't mask session_id."""
        # Test the masking function directly
        from osiris.core.secrets_masking import mask_sensitive_dict

        test_data = {
            "session_id": "test-session-123",
            "event": "validation_start",
            "event_type": "test_event",
            "password": "secret123",  # pragma: allowlist secret
            "api_key": "key123",  # pragma: allowlist secret
            "tokens": 100,
            "duration_ms": 500,
        }

        masked = mask_sensitive_dict(test_data)

        # Structural keys should not be masked
        assert masked["session_id"] == "test-session-123"
        assert masked["event"] == "validation_start"
        assert masked["event_type"] == "test_event"
        assert masked["tokens"] == 100
        assert masked["duration_ms"] == 500

        # Sensitive keys should be masked
        assert masked["password"] == "***"
        assert masked["api_key"] == "***"
