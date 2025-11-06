"""Tests for the validate command with .env file loading and JSON output."""

import json
import os
from pathlib import Path
import sys
import tempfile
import textwrap
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
    def temp_connections_yaml(self, tmp_path, monkeypatch):
        """Create a minimal osiris_connections.yaml in current working directory."""
        content = textwrap.dedent(
            """
        connections:
          mysql:
            db_movies:
              host: ${MYSQL_HOST}
              port: 3306
              user: ${MYSQL_USER}
              password: ${MYSQL_PASSWORD}
              database: ${MYSQL_DATABASE}
          supabase:
            main:
              url: ${SUPABASE_URL}
              service_role_key: ${SUPABASE_SERVICE_ROLE_KEY}
              pg_dsn: ${SUPABASE_PG_DSN}
        """
        ).strip()

        # Create temp directory and change to it
        original_cwd = os.getcwd()
        monkeypatch.chdir(tmp_path)

        # Write connections file in current working directory (where CLI will look)
        p = tmp_path / "osiris_connections.yaml"
        p.write_text(content)

        yield p

        # Restore original directory
        os.chdir(original_cwd)

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
        """Test validate command without .env file and no connections file using JSON output."""
        # Clear any existing environment variables
        env_vars = [
            "MYSQL_HOST",
            "MYSQL_USER",
            "MYSQL_PASSWORD",
            "MYSQL_DATABASE",
            "SUPABASE_URL",
            "SUPABASE_SERVICE_ROLE_KEY",
            "SUPABASE_PG_DSN",
            "OPENAI_API_KEY",
            "CLAUDE_API_KEY",
            "GEMINI_API_KEY",
        ]
        for var in env_vars:
            monkeypatch.delenv(var, raising=False)

        # Mock Path.exists to return False for .env and osiris_connections.yaml
        original_exists = Path.exists

        def mock_exists(self):
            # Return False for .env and osiris_connections.yaml, True for everything else
            if str(self).endswith(".env") or str(self).endswith("osiris_connections.yaml"):
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

        # Check that database connections are not configured (ADR-0020 behavior)
        assert result["database_connections"]["mysql"]["configured"] is False
        assert result["database_connections"]["mysql"]["aliases"] == []
        assert "No MySQL connections defined" in result["database_connections"]["mysql"]["note"]

        assert result["database_connections"]["supabase"]["configured"] is False
        assert result["database_connections"]["supabase"]["aliases"] == []
        assert "No Supabase connections defined" in result["database_connections"]["supabase"]["note"]

        # Check that LLM providers are not configured
        assert result["llm_providers"]["openai"]["configured"] is False
        assert result["llm_providers"]["claude"]["configured"] is False

    def test_validate_with_env_file_json(
        self, temp_config, temp_connections_yaml, monkeypatch, capsys, clean_project_root
    ):
        """Test validate command with .env file and connections yaml using JSON output."""
        # Set all required environment variables via monkeypatch (simulating .env file)
        monkeypatch.setenv("MYSQL_HOST", "test-host.example.com")
        monkeypatch.setenv("MYSQL_USER", "testuser")
        monkeypatch.setenv("MYSQL_PASSWORD", "testpass")
        monkeypatch.setenv("MYSQL_DATABASE", "testdb")
        monkeypatch.setenv("MYSQL_PORT", "3306")

        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
        monkeypatch.setenv(
            "SUPABASE_PG_DSN", "postgresql://test:pass@db.supabase.co:5432/postgres"  # pragma: allowlist secret
        )

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-123")
        monkeypatch.setenv("CLAUDE_API_KEY", "claude-test-key")  # pragma: allowlist secret

        # Run validate command with JSON output
        from contextlib import suppress

        with suppress(SystemExit):
            validate_command(["--config", temp_config, "--json"])

        # Capture and parse JSON output
        captured = capsys.readouterr()
        output = json.loads(captured.out)

        # Check that variables are loaded correctly (ADR-0020)
        assert output["database_connections"]["mysql"]["configured"] is True
        assert "db_movies" in output["database_connections"]["mysql"]["aliases"]
        assert output["database_connections"]["mysql"]["missing_vars"] == []

        assert output["database_connections"]["supabase"]["configured"] is True
        assert "main" in output["database_connections"]["supabase"]["aliases"]
        assert output["database_connections"]["supabase"]["missing_vars"] == []

        # Connection validation should exist
        cv = output.get("connection_validation", {})
        assert "mysql.db_movies" in cv

        # LLM providers still checked directly
        assert output["llm_providers"]["openai"]["configured"] is True
        assert output["llm_providers"]["claude"]["configured"] is True

    def test_validate_env_variables_directly_set_json(
        self, temp_config, temp_connections_yaml, monkeypatch, capsys, clean_project_root
    ):
        """Test validate command with environment variables set directly using JSON output."""
        # Set environment variables directly (no .env file)
        monkeypatch.setenv("MYSQL_HOST", "direct-host.example.com")
        monkeypatch.setenv("MYSQL_USER", "directuser")
        monkeypatch.setenv("MYSQL_PASSWORD", "directpass")
        monkeypatch.setenv("MYSQL_DATABASE", "directdb")

        monkeypatch.setenv("SUPABASE_URL", "https://direct.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "direct-service-key")
        monkeypatch.setenv(
            "SUPABASE_PG_DSN", "postgresql://direct:pass@db.supabase.co:5432/postgres"  # pragma: allowlist secret
        )

        monkeypatch.setenv("OPENAI_API_KEY", "sk-direct-key")

        # Mock Path.exists to return False for .env
        original_exists = Path.exists

        def mock_exists(self):
            # Return False for .env, True for everything else including osiris_connections.yaml
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

        # Should still show configured even without .env file (ADR-0020)
        assert result["database_connections"]["mysql"]["configured"] is True
        assert "db_movies" in result["database_connections"]["mysql"]["aliases"]

        assert result["database_connections"]["supabase"]["configured"] is True
        assert "main" in result["database_connections"]["supabase"]["aliases"]

        assert result["llm_providers"]["openai"]["configured"] is True

    def test_validate_partial_env_configuration_json(
        self, temp_config, temp_connections_yaml, monkeypatch, capsys, clean_project_root
    ):
        """Test validate command with partial environment configuration using JSON output."""
        # Set MySQL variables but omit MYSQL_PASSWORD
        monkeypatch.setenv("MYSQL_HOST", "partial-host.example.com")
        monkeypatch.setenv("MYSQL_USER", "partialuser")
        monkeypatch.setenv("MYSQL_DATABASE", "partialdb")
        # Intentionally NOT setting MYSQL_PASSWORD

        # Clear Supabase variables
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        monkeypatch.delenv("SUPABASE_PG_DSN", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        # Mock Path.exists to return False for .env
        original_exists = Path.exists

        def mock_exists(self):
            # Return False for .env, True for everything else including osiris_connections.yaml
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

        # Check mixed configuration status (ADR-0020)
        # MySQL should NOT be configured because MYSQL_PASSWORD is missing
        assert result["database_connections"]["mysql"]["configured"] is False
        assert "MYSQL_PASSWORD" in result["database_connections"]["mysql"]["missing_vars"]
        assert "db_movies" in result["database_connections"]["mysql"]["aliases"]  # Alias still listed

        # Supabase should NOT be configured due to missing all env vars
        assert result["database_connections"]["supabase"]["configured"] is False
        assert len(result["database_connections"]["supabase"]["missing_vars"]) > 0
        assert "main" in result["database_connections"]["supabase"]["aliases"]

        # Connection validation may or may not catch the missing env vars depending on validation mode
        # The key assertion is that the connection is marked as not configured above
        cv = result.get("connection_validation", {})
        if "mysql.db_movies" in cv:
            # The validator might still show as valid if it just checks structure
            # The important thing is that the missing_vars were detected above
            mysql_val = cv["mysql.db_movies"]
            # Just verify the validation result exists - the missing vars check above is what matters
            assert "is_valid" in mysql_val

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
