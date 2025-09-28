"""Tests for the validate command with .env file loading and JSON output."""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# Add parent directory to path to import osiris modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from osiris.cli.main import validate_command


class TestValidateCommand:
    """Test suite for validate command with JSON output."""

    @pytest.fixture
    def temp_config(self):
        """Create a temporary configuration file."""
        config_content = """logging:
  level: INFO
  file: osiris.log

output:
  format: csv
  directory: output/

sessions:
  cleanup_days: 30
  cache_ttl: 3600

discovery:
  sample_size: 10
  timeout_seconds: 30

llm:
  provider: openai
  temperature: 0.1
  max_tokens: 2000

pipeline:
  validation_required: true
  auto_execute: false
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            temp_path = f.name

        yield temp_path

        # Cleanup
        Path(temp_path).unlink(missing_ok=True)

    @pytest.fixture
    def temp_env_file(self):
        """Create a temporary .env file."""
        env_content = """# Test environment variables
MYSQL_HOST=test-host.example.com
MYSQL_PORT=3306
MYSQL_DATABASE=testdb
MYSQL_USER=testuser
MYSQL_PASSWORD=testpass

SUPABASE_PROJECT_ID=test-project-id
SUPABASE_ANON_PUBLIC_KEY=test-anon-key

OPENAI_API_KEY=sk-test-key-123
CLAUDE_API_KEY=claude-test-key
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(env_content)
            temp_path = f.name

        yield temp_path

        # Cleanup
        Path(temp_path).unlink(missing_ok=True)

    def test_validate_without_env_file_json(self, temp_config, monkeypatch, capsys, clean_project_root):
        """Test validate command without .env file using JSON output."""
        # Clear any existing environment variables
        env_vars = [
            "MYSQL_HOST",
            "MYSQL_USER",
            "MYSQL_PASSWORD",
            "MYSQL_DATABASE",
            "SUPABASE_PROJECT_ID",
            "SUPABASE_ANON_PUBLIC_KEY",
            "OPENAI_API_KEY",
            "CLAUDE_API_KEY",
            "GEMINI_API_KEY",
        ]
        for var in env_vars:
            monkeypatch.delenv(var, raising=False)

        # Mock Path.exists to return False for .env
        original_exists = Path.exists

        def mock_exists(self):
            # Return False for .env, True for everything else
            if str(self).endswith(".env"):
                return False
            return original_exists(self)

        with mock.patch.object(Path, "exists", mock_exists):

            # Run validate command with JSON output
            from contextlib import suppress

            with suppress(SystemExit):
                validate_command(["--config", temp_config, "--json"])

        # Capture and parse JSON output
        captured = capsys.readouterr()
        print(f"DEBUG: Captured stdout: {repr(captured.out)}")
        print(f"DEBUG: Captured stderr: {repr(captured.err)}")
        if not captured.out:
            raise AssertionError("No output captured from validate command")
        result = json.loads(captured.out)

        # Check that all sections are validated
        assert result["config_valid"] is True
        assert result["config_file"] == temp_config

        # Check that database connections are not configured
        assert result["database_connections"]["mysql"]["configured"] is False
        assert "MYSQL_HOST" in result["database_connections"]["mysql"]["missing_vars"]
        assert result["database_connections"]["supabase"]["configured"] is False

        # Check that LLM providers are not configured
        assert result["llm_providers"]["openai"]["configured"] is False
        assert result["llm_providers"]["claude"]["configured"] is False

    def test_validate_with_env_file_json(self, temp_config, temp_env_file, monkeypatch, clean_project_root):
        """Test validate command with .env file using JSON output."""
        # Clear any existing environment variables first
        env_vars = [
            "MYSQL_HOST",
            "MYSQL_USER",
            "MYSQL_PASSWORD",
            "MYSQL_DATABASE",
            "SUPABASE_PROJECT_ID",
            "SUPABASE_ANON_PUBLIC_KEY",
            "OPENAI_API_KEY",
            "CLAUDE_API_KEY",
            "GEMINI_API_KEY",
        ]
        for var in env_vars:
            monkeypatch.delenv(var, raising=False)

        # Change to temp directory and create .env symlink
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)

                # Create symlink to temp env file
                Path(".env").symlink_to(temp_env_file)

                # Run validate command with JSON output
                import subprocess

                result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        f"""
import sys
sys.path.insert(0, '{original_cwd}')
from osiris.cli.main import validate_command
validate_command(['--config', '{temp_config}', '--json'])
""",
                    ],
                    check=False, capture_output=True,
                    text=True,
                )

                # Parse JSON output
                output = json.loads(result.stdout)

                # Check that variables are loaded correctly
                assert output["database_connections"]["mysql"]["configured"] is True
                assert output["database_connections"]["mysql"]["missing_vars"] == []
                assert output["database_connections"]["supabase"]["configured"] is True
                assert output["llm_providers"]["openai"]["configured"] is True
                assert output["llm_providers"]["claude"]["configured"] is True

            finally:
                os.chdir(original_cwd)

    def test_validate_env_variables_directly_set_json(self, temp_config, monkeypatch, capsys, clean_project_root):
        """Test validate command with environment variables set directly using JSON output."""
        # Set environment variables directly
        monkeypatch.setenv("MYSQL_HOST", "direct-host.example.com")
        monkeypatch.setenv("MYSQL_USER", "directuser")
        monkeypatch.setenv("MYSQL_PASSWORD", "directpass")
        monkeypatch.setenv("MYSQL_DATABASE", "directdb")
        monkeypatch.setenv("SUPABASE_PROJECT_ID", "direct-project")
        monkeypatch.setenv("SUPABASE_ANON_PUBLIC_KEY", "direct-key")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-direct-key")

        # Mock Path.exists to return False for .env
        original_exists = Path.exists

        def mock_exists(self):
            # Return False for .env, True for everything else
            if str(self).endswith(".env"):
                return False
            return original_exists(self)

        with mock.patch.object(Path, "exists", mock_exists):

            # Run validate command with JSON output
            from contextlib import suppress

            with suppress(SystemExit):
                validate_command(["--config", temp_config, "--json"])

        # Capture and parse JSON output
        captured = capsys.readouterr()
        result = json.loads(captured.out)

        # Should still show configured even without .env file
        assert result["database_connections"]["mysql"]["configured"] is True
        assert result["database_connections"]["supabase"]["configured"] is True
        assert result["llm_providers"]["openai"]["configured"] is True

    def test_validate_partial_env_configuration_json(self, temp_config, monkeypatch, capsys, clean_project_root):
        """Test validate command with partial environment configuration using JSON output."""
        # Set only MySQL variables
        monkeypatch.setenv("MYSQL_HOST", "partial-host.example.com")
        monkeypatch.setenv("MYSQL_USER", "partialuser")
        monkeypatch.setenv("MYSQL_PASSWORD", "partialpass")
        monkeypatch.setenv("MYSQL_DATABASE", "partialdb")

        # Clear Supabase and API key variables
        monkeypatch.delenv("SUPABASE_PROJECT_ID", raising=False)
        monkeypatch.delenv("SUPABASE_ANON_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        # Mock Path.exists to return False for .env
        original_exists = Path.exists

        def mock_exists(self):
            # Return False for .env, True for everything else
            if str(self).endswith(".env"):
                return False
            return original_exists(self)

        with mock.patch.object(Path, "exists", mock_exists):

            # Run validate command with JSON output
            from contextlib import suppress

            with suppress(SystemExit):
                validate_command(["--config", temp_config, "--json"])

        # Capture and parse JSON output
        captured = capsys.readouterr()
        result = json.loads(captured.out)

        # Check mixed configuration status
        assert result["database_connections"]["mysql"]["configured"] is True
        assert result["database_connections"]["supabase"]["configured"] is False
        assert len(result["database_connections"]["supabase"]["missing_vars"]) > 0
        assert result["llm_providers"]["openai"]["configured"] is False

    def test_validate_config_sections_json(self, temp_config, monkeypatch, capsys, clean_project_root):
        """Test that all config sections are properly validated in JSON output."""
        # Clear environment variables
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        # Mock Path.exists to return False for .env
        original_exists = Path.exists

        def mock_exists(self):
            # Return False for .env, True for everything else
            if str(self).endswith(".env"):
                return False
            return original_exists(self)

        with mock.patch.object(Path, "exists", mock_exists):

            # Run validate command with JSON output
            from contextlib import suppress

            with suppress(SystemExit):
                validate_command(["--config", temp_config, "--json"])

        # Capture and parse JSON output
        captured = capsys.readouterr()
        result = json.loads(captured.out)

        # Check all config sections
        assert "sections" in result
        assert result["sections"]["logging"]["status"] == "configured"
        assert result["sections"]["logging"]["level"] == "INFO"
        assert result["sections"]["output"]["status"] == "configured"
        assert result["sections"]["output"]["format"] == "csv"
        assert result["sections"]["sessions"]["status"] == "configured"
        assert result["sections"]["discovery"]["status"] == "configured"
        assert result["sections"]["llm"]["status"] == "configured"
        assert result["sections"]["llm"]["provider"] == "openai"
        assert result["sections"]["pipeline"]["status"] == "configured"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
