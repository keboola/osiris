"""Unit tests for env_loader module."""

import os
from pathlib import Path

from osiris.core.env_loader import load_env


class TestEnvLoader:
    """Test environment loading functionality."""

    def test_load_env_from_cwd(self, tmp_path):
        """Test loading .env from current working directory."""
        # Create a .env file in tmp directory
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_VAR_CWD=from_cwd\n")

        # Change to tmp directory temporarily
        original_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)

            # Load env
            loaded = load_env()

            # Check that file was loaded
            assert str(env_file) in loaded
            assert os.environ.get("TEST_VAR_CWD") == "from_cwd"

        finally:
            os.chdir(original_cwd)
            # Clean up
            os.environ.pop("TEST_VAR_CWD", None)

    def test_load_env_from_project_root(self, tmp_path):
        """Test loading .env from project root (where osiris.py lives)."""
        # Create project structure
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / "osiris.py").touch()

        env_file = project_root / ".env"
        env_file.write_text("TEST_VAR_ROOT=from_root\n")

        # Work from a subdirectory
        work_dir = project_root / "subdir"
        work_dir.mkdir()

        original_cwd = Path.cwd()
        try:
            os.chdir(work_dir)

            # Load env
            loaded = load_env()

            # Check that project root .env was loaded
            assert str(env_file) in loaded
            assert os.environ.get("TEST_VAR_ROOT") == "from_root"

        finally:
            os.chdir(original_cwd)
            os.environ.pop("TEST_VAR_ROOT", None)

    def test_load_env_from_testing_env(self, tmp_path):
        """Test loading .env from testing_env directory when CWD is testing_env."""
        # Create testing_env directory
        testing_env = tmp_path / "testing_env"
        testing_env.mkdir()

        env_file = testing_env / ".env"
        env_file.write_text("TEST_VAR_TESTING=from_testing_env\n")

        original_cwd = Path.cwd()
        try:
            os.chdir(testing_env)

            # Load env
            loaded = load_env()

            # Check that testing_env/.env was loaded
            assert str(env_file) in loaded
            assert os.environ.get("TEST_VAR_TESTING") == "from_testing_env"

        finally:
            os.chdir(original_cwd)
            os.environ.pop("TEST_VAR_TESTING", None)

    def test_exported_env_wins_over_dotenv(self, tmp_path):
        """Test that exported environment variables take precedence over .env files."""
        # Set an environment variable
        os.environ["TEST_VAR_PRECEDENCE"] = "exported_value"

        try:
            # Create .env with different value
            env_file = tmp_path / ".env"
            env_file.write_text("TEST_VAR_PRECEDENCE=dotenv_value\n")

            original_cwd = Path.cwd()
            try:
                os.chdir(tmp_path)

                # Load env
                load_env()

                # Exported value should win
                assert os.environ.get("TEST_VAR_PRECEDENCE") == "exported_value"

            finally:
                os.chdir(original_cwd)

        finally:
            os.environ.pop("TEST_VAR_PRECEDENCE", None)

    def test_empty_string_treated_as_set(self, tmp_path):
        """Test that empty string in env var is treated as set (not missing)."""
        # Set an empty environment variable
        os.environ["TEST_VAR_EMPTY"] = ""

        try:
            # Create .env with non-empty value
            env_file = tmp_path / ".env"
            env_file.write_text("TEST_VAR_EMPTY=should_not_override\n")

            original_cwd = Path.cwd()
            try:
                os.chdir(tmp_path)

                # Load env
                load_env()

                # Empty string should still win (it's "set")
                assert os.environ.get("TEST_VAR_EMPTY") == ""

            finally:
                os.chdir(original_cwd)

        finally:
            os.environ.pop("TEST_VAR_EMPTY", None)

    def test_explicit_dotenv_paths(self, tmp_path):
        """Test loading from explicit .env paths."""
        # Create multiple .env files
        env1 = tmp_path / "env1.env"
        env1.write_text("TEST_VAR_1=value1\n")

        env2 = tmp_path / "env2.env"
        env2.write_text("TEST_VAR_2=value2\n")

        try:
            # Load specific files
            loaded = load_env([str(env1), str(env2)])

            # Both files should be loaded
            assert str(env1) in loaded
            assert str(env2) in loaded
            assert os.environ.get("TEST_VAR_1") == "value1"
            assert os.environ.get("TEST_VAR_2") == "value2"

        finally:
            os.environ.pop("TEST_VAR_1", None)
            os.environ.pop("TEST_VAR_2", None)

    def test_nonexistent_file_ignored(self, tmp_path):
        """Test that nonexistent .env files are silently ignored."""
        original_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)

            # No .env file exists
            loaded = load_env()

            # Should return empty list, no error
            assert loaded == []

        finally:
            os.chdir(original_cwd)

    def test_idempotent_loading(self, tmp_path):
        """Test that load_env is idempotent (safe to call multiple times)."""
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_VAR_IDEMPOTENT=original\n")

        original_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)

            # Load multiple times
            loaded1 = load_env()

            # Change the value in memory
            os.environ["TEST_VAR_IDEMPOTENT"] = "modified"

            # Load again - should not override
            loaded2 = load_env()

            # Value should remain modified
            assert os.environ.get("TEST_VAR_IDEMPOTENT") == "modified"
            assert loaded1 == loaded2

        finally:
            os.chdir(original_cwd)
            os.environ.pop("TEST_VAR_IDEMPOTENT", None)
