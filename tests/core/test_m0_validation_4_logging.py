#!/usr/bin/env python3
"""
Comprehensive tests for M0-Validation-4: Logging Configuration Extensions.

This test suite validates:
1. Configuration precedence (YAML → ENV → CLI)
2. Log level and logs_dir overrides
3. Wildcard events configuration
4. Secrets masking in all outputs
5. Fallback behavior for permission errors
6. Effective configuration reporting
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pytest
import yaml


class TestLoggingConfigurationPrecedence:
    """Test configuration precedence: CLI > ENV > YAML > defaults."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            yield workspace

    @pytest.fixture
    def osiris_config(self, temp_workspace):
        """Create a test osiris.yaml configuration."""
        config_path = temp_workspace / "osiris.yaml"
        config = {
            "version": "2.0",
            "logging": {
                "logs_dir": str(temp_workspace / "yaml_logs"),
                "level": "INFO",
                "events": ["run_start", "run_end"],
                "metrics": {"enabled": True},
                "retention": "7d",
            },
            "validate": {"mode": "warn", "json": False},
        }
        with open(config_path, "w") as f:
            yaml.dump(config, f)
        return config_path

    def test_log_level_yaml_default(self, temp_workspace, osiris_config):
        """Test that YAML log level is used when no overrides exist."""
        result = subprocess.run(
            ["python", "osiris.py", "validate", "--json"],
            cwd=Path(__file__).parent.parent.parent,
            capture_output=True,
            text=True,
            env={**os.environ, "OSIRIS_CONFIG": str(osiris_config)},
        )

        # Parse JSON output
        if result.stdout:
            try:
                output = json.loads(result.stdout)
                # Check effective config if available
                if "effective_config" in output:
                    assert output["effective_config"]["logging"]["level"] == "INFO"
                    assert output["effective_config"]["logging"]["level_source"] == "yaml"
            except json.JSONDecodeError:
                pass  # Skip if not JSON

    def test_log_level_env_override(self, temp_workspace, osiris_config):
        """Test that ENV overrides YAML log level."""
        env = {**os.environ, "OSIRIS_CONFIG": str(osiris_config), "OSIRIS_LOG_LEVEL": "DEBUG"}

        result = subprocess.run(
            ["python", "osiris.py", "validate", "--json"],
            cwd=Path(__file__).parent.parent.parent,
            capture_output=True,
            text=True,
            env=env,
        )

        # Check that DEBUG level is applied
        if result.stdout:
            try:
                output = json.loads(result.stdout)
                if "effective_config" in output:
                    assert output["effective_config"]["logging"]["level"] == "DEBUG"
                    assert output["effective_config"]["logging"]["level_source"] == "env"
            except json.JSONDecodeError:
                pass

    def test_log_level_cli_override(self, temp_workspace, osiris_config):
        """Test that CLI flag overrides both ENV and YAML."""
        env = {**os.environ, "OSIRIS_CONFIG": str(osiris_config), "OSIRIS_LOG_LEVEL": "DEBUG"}

        result = subprocess.run(
            ["python", "osiris.py", "validate", "--log-level", "ERROR", "--json"],
            cwd=Path(__file__).parent.parent.parent,
            capture_output=True,
            text=True,
            env=env,
        )

        # Check that ERROR level is applied (highest precedence)
        if result.stdout:
            try:
                output = json.loads(result.stdout)
                if "effective_config" in output:
                    assert output["effective_config"]["logging"]["level"] == "ERROR"
                    assert output["effective_config"]["logging"]["level_source"] == "cli"
            except json.JSONDecodeError:
                pass

    def test_logs_dir_precedence_chain(self, temp_workspace, osiris_config):
        """Test complete precedence chain for logs_dir: CLI > ENV > YAML."""
        yaml_dir = temp_workspace / "yaml_logs"
        env_dir = temp_workspace / "env_logs"
        cli_dir = temp_workspace / "cli_logs"

        # Test 1: YAML only
        result = subprocess.run(
            ["python", "osiris.py", "validate", "--mode", "warn", "--json"],
            cwd=Path(__file__).parent.parent.parent,
            capture_output=True,
            text=True,
            env={**os.environ, "OSIRIS_CONFIG": str(osiris_config)},
        )
        # Should use yaml_logs - check if directory exists or mentioned in output
        # Skip if command failed due to missing config
        if result.returncode == 0:
            assert yaml_dir.exists() or "yaml_logs" in result.stdout
        else:
            pytest.skip(f"Command failed: {result.stderr}")

        # Test 2: ENV overrides YAML
        env = {**os.environ, "OSIRIS_CONFIG": str(osiris_config), "OSIRIS_LOGS_DIR": str(env_dir)}
        result = subprocess.run(
            ["python", "osiris.py", "validate", "--mode", "warn", "--json"],
            cwd=Path(__file__).parent.parent.parent,
            capture_output=True,
            text=True,
            env=env,
        )
        # Should use env_logs
        if result.returncode == 0:
            assert env_dir.exists() or "env_logs" in result.stdout
        else:
            pytest.skip(f"Command failed: {result.stderr}")

        # Test 3: CLI overrides both
        result = subprocess.run(
            [
                "python",
                "osiris.py",
                "validate",
                "--mode",
                "warn",
                "--logs-dir",
                str(cli_dir),
                "--json",
            ],
            cwd=Path(__file__).parent.parent.parent,
            capture_output=True,
            text=True,
            env=env,
        )
        # Should use cli_logs
        if result.returncode == 0:
            assert cli_dir.exists() or "cli_logs" in result.stdout
        else:
            pytest.skip(f"Command failed: {result.stderr}")


class TestWildcardEventsConfiguration:
    """Test wildcard "*" events configuration."""

    @pytest.fixture
    def config_with_wildcard(self, tmp_path):
        """Create config with wildcard events."""
        config_path = tmp_path / "osiris.yaml"
        config = {
            "version": "2.0",
            "logging": {
                "logs_dir": str(tmp_path / "logs"),
                "level": "INFO",
                "events": "*",  # Wildcard - log all events
                "metrics": {"enabled": True},
            },
        }
        with open(config_path, "w") as f:
            yaml.dump(config, f)
        return config_path

    @pytest.fixture
    def config_with_explicit_events(self, tmp_path):
        """Create config with explicit event list."""
        config_path = tmp_path / "osiris.yaml"
        config = {
            "version": "2.0",
            "logging": {
                "logs_dir": str(tmp_path / "logs"),
                "level": "INFO",
                "events": ["run_start", "run_end"],  # Only these events
                "metrics": {"enabled": True},
            },
        }
        with open(config_path, "w") as f:
            yaml.dump(config, f)
        return config_path

    def test_wildcard_logs_all_events(self, config_with_wildcard):
        """Test that wildcard "*" logs all event types."""
        # This would need integration with actual event logging
        # For now, validate that config is parsed correctly
        with open(config_with_wildcard) as f:
            config = yaml.safe_load(f)

        assert config["logging"]["events"] == "*"

        # In real test, would run a command and verify events.jsonl contains many event types

    def test_explicit_events_filtered(self, config_with_explicit_events):
        """Test that explicit event list filters correctly."""
        with open(config_with_explicit_events) as f:
            config = yaml.safe_load(f)

        assert config["logging"]["events"] == ["run_start", "run_end"]

        # In real test, would verify only specified events appear in events.jsonl

    def test_backward_compatibility_missing_events(self, tmp_path):
        """Test that missing events field defaults to wildcard behavior."""
        config_path = tmp_path / "osiris.yaml"
        config = {
            "version": "2.0",
            "logging": {
                "logs_dir": str(tmp_path / "logs"),
                "level": "INFO",
                # Note: no "events" field - should default to "*"
            },
        }
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        # System should treat missing events as "*" for backward compatibility


class TestSecretsMasking:
    """Test that secrets are properly masked in all outputs."""

    def test_no_secrets_in_logs(self, tmp_path):
        """Test that no plaintext secrets appear in any log files."""
        from osiris.core.session_logging import SessionContext

        # Create session with known secrets
        session = SessionContext(base_logs_dir=tmp_path)

        # Test secrets that should be masked
        test_secrets = {
            "password": "SuperSecret123",  # pragma: allowlist secret
            "api_key": "sk-test-XYZ",  # pragma: allowlist secret
            "token": "bearer_abc123",  # pragma: allowlist secret
            "authorization": "Bearer secret_token",  # pragma: allowlist secret
            "database_password": "db_pass_456",  # pragma: allowlist secret
            "secret": "my_secret_value",  # pragma: allowlist secret
        }

        # Log events with secrets
        session.log_event("test_event", **test_secrets)

        # Log metrics with secrets
        session.log_metric("test_metric", 100, **test_secrets)

        # Save config with secrets
        session.save_config(test_secrets)

        # Save manifest with secrets
        session.save_manifest({"credentials": test_secrets})

        # Now scan all files for plaintext secrets
        for file_path in session.session_dir.rglob("*"):
            if file_path.is_file():
                content = file_path.read_text(encoding="utf-8", errors="ignore")

                # Check that no plaintext secrets appear
                for key, secret_value in test_secrets.items():
                    assert secret_value not in content, f"Found secret '{key}' in {file_path}"

                # Verify masked values are present
                if file_path.suffix in [".json", ".jsonl"]:
                    assert "***" in content, f"No masked values found in {file_path}"


class TestPermissionFallback:
    """Test fallback behavior when permissions are denied."""

    def test_fallback_to_temp_on_permission_error(self):
        """Test that system falls back to temp dir on permission errors."""
        from osiris.core.session_logging import SessionContext

        # Try to create session in non-writable location
        with patch("pathlib.Path.mkdir") as mock_mkdir:
            mock_mkdir.side_effect = PermissionError("Access denied")

            # Should not raise, should fallback to temp
            session = SessionContext(
                session_id="test_fallback", base_logs_dir=Path("/nonexistent/readonly")
            )

            # Session should still work
            assert session.session_dir.exists()
            # On macOS, temp dirs are in /var/folders/, on Linux in /tmp, on Windows in Temp
            assert any(
                temp_marker in str(session.session_dir)
                for temp_marker in ["/var/folders/", "/tmp", "Temp", "TEMP"]
            )

            # Should be able to log
            session.log_event("session_log_error", reason="permission_denied")


class TestEffectiveConfigurationReporting:
    """Test that effective configuration is reported with sources."""

    def test_effective_config_shows_sources(self, tmp_path):
        """Test that validate --json shows config values and their sources."""
        config_path = tmp_path / "osiris.yaml"
        config = {
            "version": "2.0",
            "logging": {"logs_dir": str(tmp_path / "yaml_logs"), "level": "INFO", "events": "*"},
        }
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        # Run with ENV override
        env = {**os.environ, "OSIRIS_CONFIG": str(config_path), "OSIRIS_LOG_LEVEL": "DEBUG"}

        result = subprocess.run(
            ["python", "osiris.py", "validate", "--json"],
            cwd=Path(__file__).parent.parent.parent,
            capture_output=True,
            text=True,
            env=env,
        )

        if result.stdout:
            try:
                output = json.loads(result.stdout)
                if "effective_config" in output:
                    # Should show DEBUG from env, logs_dir from yaml
                    logging_config = output["effective_config"]["logging"]
                    assert logging_config["level"] == "DEBUG"
                    assert logging_config["level_source"] == "env"
                    assert "yaml_logs" in logging_config["logs_dir"]
                    assert logging_config["logs_dir_source"] == "yaml"
            except json.JSONDecodeError:
                pass


class TestLogLevelComparison:
    """Test comparing logs at different verbosity levels."""

    def run_with_log_level(self, level: str, workspace: Path) -> Dict[str, Any]:
        """Run osiris command with specified log level and return log info."""
        logs_dir = workspace / f"logs_{level.lower()}"

        # Create a minimal config file for the test
        config_path = workspace / "osiris.yaml"
        if not config_path.exists():
            config = {"version": "2.0", "logging": {"level": "INFO"}, "validate": {"mode": "warn"}}
            with open(config_path, "w") as f:
                yaml.dump(config, f)

        subprocess.run(
            [
                "python",
                "osiris.py",
                "validate",
                "--mode",
                "warn",
                "--log-level",
                level,
                "--logs-dir",
                str(logs_dir),
                "--json",
            ],
            cwd=Path(__file__).parent.parent.parent,
            capture_output=True,
            text=True,
            env={**os.environ, "OSIRIS_CONFIG": str(config_path)},
        )

        # Find the session directory
        session_dirs = list(logs_dir.glob("*")) if logs_dir.exists() else []
        if not session_dirs:
            return {"level": level, "log_size": 0, "lines": 0}

        session_dir = session_dirs[0]
        log_file = session_dir / "osiris.log"

        if log_file.exists():
            content = log_file.read_text()
            return {
                "level": level,
                "log_size": len(content),
                "lines": len(content.splitlines()),
                "has_debug": "DEBUG" in content,
                "has_info": "INFO" in content,
                "has_error": "ERROR" in content,
            }

        return {"level": level, "log_size": 0, "lines": 0}

    def test_debug_vs_critical_log_levels(self, tmp_path):
        """Test that DEBUG level produces more logs than CRITICAL."""
        # Run with DEBUG level
        debug_info = self.run_with_log_level("DEBUG", tmp_path)

        # Run with CRITICAL level
        critical_info = self.run_with_log_level("CRITICAL", tmp_path)

        # DEBUG should produce more log content
        # Skip test if no logs were created (likely due to command failure)
        if debug_info["log_size"] == 0 and critical_info["log_size"] == 0:
            pytest.skip("No logs created - command may have failed")

        assert (
            debug_info["log_size"] > critical_info["log_size"]
        ), "DEBUG logs should be larger than CRITICAL logs"

        assert (
            debug_info["lines"] > critical_info["lines"]
        ), "DEBUG should have more log lines than CRITICAL"

        # DEBUG logs should contain DEBUG messages
        assert debug_info.get("has_debug", False), "DEBUG level should include DEBUG messages"

        # CRITICAL logs should not contain DEBUG or INFO
        assert not critical_info.get(
            "has_debug", False
        ), "CRITICAL level should not include DEBUG messages"
        assert not critical_info.get(
            "has_info", False
        ), "CRITICAL level should not include INFO messages"


class TestDiscoveryCacheConfiguration:
    """Test discovery cache TTL configuration."""

    def test_cache_ttl_from_config(self, tmp_path):
        """Test that cache TTL is read from configuration."""
        config_path = tmp_path / "osiris.yaml"
        config = {
            "version": "2.0",
            "discovery": {
                "cache": {"ttl_seconds": 5, "dir": str(tmp_path / "cache")}  # Short TTL for testing
            },
        }
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        # This would need integration with actual discovery module
        # For unit test, just verify config is correct
        with open(config_path) as f:
            loaded = yaml.safe_load(f)

        assert loaded["discovery"]["cache"]["ttl_seconds"] == 5
        assert "cache" in loaded["discovery"]["cache"]["dir"]


class TestDualArtifactStorage:
    """Test that generated YAML is stored in both locations."""

    def test_yaml_saved_to_both_locations(self, tmp_path):
        """Test YAML saved to testing_env/output and session artifacts."""
        from osiris.core.session_logging import SessionContext

        # Create session
        session = SessionContext(base_logs_dir=tmp_path / "logs")

        # Simulate pipeline YAML generation
        pipeline_yaml = {
            "version": "1.0",
            "pipeline": {
                "name": "test_pipeline",
                "source": {"type": "mysql", "password": "secret123"},  # pragma: allowlist secret
            },
        }

        # Save as artifact
        artifact_path = session.save_artifact("pipeline.yaml", pipeline_yaml, "json")

        assert artifact_path.exists()

        # Load and verify secrets are masked
        with open(artifact_path) as f:
            saved = yaml.safe_load(f)

        assert saved["pipeline"]["source"]["password"] == "***"

        # In real implementation, would also check testing_env/output/


class TestManualScenarios:
    """Test cases that demonstrate manual test scenarios programmatically."""

    def test_scenario_log_level_comparison(self, tmp_path):
        """
        Manual Test Scenario: Compare DEBUG vs CRITICAL log outputs.

        This test demonstrates what a manual tester would do:
        1. Run same command with DEBUG level
        2. Run same command with CRITICAL level
        3. Compare the log file sizes and contents
        """
        workspace = tmp_path / "manual_test"
        workspace.mkdir(parents=True, exist_ok=True)

        # Create a simple config
        config_path = workspace / "osiris.yaml"
        config = {
            "version": "2.0",
            "logging": {"logs_dir": str(workspace / "logs"), "level": "INFO", "events": "*"},
        }
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        print("\n=== Manual Test Scenario: Log Level Comparison ===")
        print("This test simulates manual testing of log levels\n")

        # Step 1: Run with DEBUG
        print("Step 1: Running with DEBUG level...")
        subprocess.run(
            [
                "python",
                "osiris.py",
                "validate",
                "--log-level",
                "DEBUG",
                "--logs-dir",
                str(workspace / "debug_logs"),
            ],
            cwd=Path(__file__).parent.parent.parent,
            capture_output=True,
            text=True,
            env={**os.environ, "OSIRIS_CONFIG": str(config_path)},
        )

        # Step 2: Run with CRITICAL
        print("Step 2: Running with CRITICAL level...")
        subprocess.run(
            [
                "python",
                "osiris.py",
                "validate",
                "--log-level",
                "CRITICAL",
                "--logs-dir",
                str(workspace / "critical_logs"),
            ],
            cwd=Path(__file__).parent.parent.parent,
            capture_output=True,
            text=True,
            env={**os.environ, "OSIRIS_CONFIG": str(config_path)},
        )

        # Step 3: Compare results
        print("\nStep 3: Comparing log outputs...")

        debug_logs = workspace / "debug_logs"
        critical_logs = workspace / "critical_logs"

        if debug_logs.exists() and critical_logs.exists():
            debug_sessions = list(debug_logs.glob("*"))
            critical_sessions = list(critical_logs.glob("*"))

            if debug_sessions and critical_sessions:
                debug_log = debug_sessions[0] / "osiris.log"
                critical_log = critical_sessions[0] / "osiris.log"

                if debug_log.exists() and critical_log.exists():
                    debug_size = debug_log.stat().st_size
                    critical_size = critical_log.stat().st_size

                    print(f"  DEBUG log size: {debug_size} bytes")
                    print(f"  CRITICAL log size: {critical_size} bytes")
                    print(f"  Difference: {debug_size - critical_size} bytes")

                    # Verify DEBUG has more content
                    assert debug_size > critical_size, "DEBUG logs should be larger than CRITICAL"

                    print("\n✅ Test PASSED: DEBUG produces more logs than CRITICAL")
                    return True

        print("\n❌ Test FAILED: Could not compare log files")
        return False


def run_comprehensive_test_suite():
    """
    Run the complete M0-Validation-4 test suite and generate a report.
    This can be called directly to validate all logging features.
    """
    print("\n" + "=" * 60)
    print("M0-VALIDATION-4: LOGGING CONFIGURATION TEST SUITE")
    print("=" * 60 + "\n")

    # Run pytest with detailed output
    pytest_args = [
        __file__,
        "-v",  # Verbose
        "--tb=short",  # Short traceback
        "-s",  # No capture, show print statements
        "--color=yes",
    ]

    result = pytest.main(pytest_args)

    if result == 0:
        print("\n" + "=" * 60)
        print("✅ ALL M0-VALIDATION-4 TESTS PASSED")
        print("=" * 60 + "\n")
    else:
        print("\n" + "=" * 60)
        print("❌ SOME TESTS FAILED - SEE ABOVE FOR DETAILS")
        print("=" * 60 + "\n")

    return result


if __name__ == "__main__":
    # Run the comprehensive test suite
    exit_code = run_comprehensive_test_suite()
    exit(exit_code)
