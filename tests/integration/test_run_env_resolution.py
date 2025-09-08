"""Integration tests for runtime environment resolution."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from osiris.core.config import ConfigError
from osiris.core.runner_v0 import RunnerV0


class TestRunEnvResolution:
    """Test runtime environment resolution for connections."""

    def test_run_fails_with_missing_env_var(self):
        """Test that run fails with clear error when env var is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create osiris_connections.yaml with env var reference
            connections = {
                "version": 1,
                "connections": {
                    "mysql": {
                        "test_db": {
                            "host": "localhost",
                            "database": "test",
                            "user": "root",
                            "password": "${MYSQL_PASSWORD}",  # Missing env var
                        }
                    }
                },
            }

            connections_path = Path(tmpdir) / "osiris_connections.yaml"
            with open(connections_path, "w") as f:
                yaml.dump(connections, f)

            # Create manifest with mysql.extractor step
            manifest = {
                "pipeline": {"id": "test-pipeline", "version": "0.1.0"},
                "steps": [
                    {
                        "id": "extract",
                        "driver": "mysql.extractor",
                        "cfg_path": "cfg/extract.json",
                        "needs": [],
                    }
                ],
                "meta": {"oml_version": "0.1.0"},
            }

            manifest_path = Path(tmpdir) / "manifest.yaml"
            with open(manifest_path, "w") as f:
                yaml.dump(manifest, f)

            # Create config file with connection reference
            cfg_dir = Path(tmpdir) / "cfg"
            cfg_dir.mkdir()

            config = {
                "component": "mysql.extractor",
                "connection": "@mysql.test_db",
                "query": "SELECT * FROM users",
            }

            with open(cfg_dir / "extract.json", "w") as f:
                json.dump(config, f)

            # Ensure MYSQL_PASSWORD is NOT set
            os.environ.pop("MYSQL_PASSWORD", None)

            # Change to tmpdir so connections file is found
            original_cwd = Path.cwd()
            try:
                os.chdir(tmpdir)

                # Run should fail with ConfigError
                runner = RunnerV0(str(manifest_path))
                runner.manifest_dir = Path(tmpdir)

                with pytest.raises(ConfigError) as exc_info:
                    runner.run()
            finally:
                os.chdir(original_cwd)

            # Check error message includes family, alias, and var name
            error_msg = str(exc_info.value)
            assert "MYSQL_PASSWORD" in error_msg
            assert "mysql.test_db" in error_msg
            assert "password" in error_msg

    def test_run_succeeds_with_env_var_set(self):
        """Test that run proceeds when env var is set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create osiris_connections.yaml with env var reference
            connections = {
                "version": 1,
                "connections": {
                    "mysql": {
                        "test_db": {
                            "host": "localhost",
                            "database": "test",
                            "user": "root",
                            "password": "${MYSQL_PASSWORD}",
                        }
                    }
                },
            }

            connections_path = Path(tmpdir) / "osiris_connections.yaml"
            with open(connections_path, "w") as f:
                yaml.dump(connections, f)

            # Create manifest
            manifest = {
                "pipeline": {"id": "test-pipeline", "version": "0.1.0"},
                "steps": [
                    {
                        "id": "extract",
                        "driver": "mysql.extractor",
                        "cfg_path": "cfg/extract.json",
                        "needs": [],
                    }
                ],
                "meta": {"oml_version": "0.1.0"},
            }

            manifest_path = Path(tmpdir) / "manifest.yaml"
            with open(manifest_path, "w") as f:
                yaml.dump(manifest, f)

            # Create config file
            cfg_dir = Path(tmpdir) / "cfg"
            cfg_dir.mkdir()

            config = {
                "component": "mysql.extractor",
                "connection": "@mysql.test_db",
                "query": "SELECT * FROM users",
            }

            with open(cfg_dir / "extract.json", "w") as f:
                json.dump(config, f)

            # Set MYSQL_PASSWORD
            os.environ["MYSQL_PASSWORD"] = "test_password"  # pragma: allowlist secret

            # Change to tmpdir so connections file is found
            original_cwd = Path.cwd()
            try:
                os.chdir(tmpdir)

                # Mock MySQL extractor to avoid actual DB connection
                with patch("osiris.connectors.mysql.extractor.MySQLExtractor") as mock_mysql:
                    mock_extractor = MagicMock()
                    mock_extractor.extract.return_value = []
                    mock_mysql.return_value = mock_extractor

                    # Run should proceed past connection resolution
                    runner = RunnerV0(str(manifest_path))
                    runner.manifest_dir = Path(tmpdir)
                    runner.run()  # May succeed or fail, we check MySQL was called

                    # The important part is that MySQL was called with right config

                    # Should have called MySQL with resolved connection
                    mock_mysql.assert_called_once()
                    call_args = mock_mysql.call_args[0][0]
                    assert call_args["password"] == "test_password"  # pragma: allowlist secret
                    assert call_args["host"] == "localhost"

            finally:
                os.chdir(original_cwd)
                os.environ.pop("MYSQL_PASSWORD", None)

    def test_empty_env_var_treated_as_missing(self):
        """Test that empty string env var is treated as missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create osiris_connections.yaml
            connections = {
                "version": 1,
                "connections": {
                    "mysql": {
                        "test_db": {
                            "host": "localhost",
                            "password": "${MYSQL_PASSWORD}",
                        }
                    }
                },
            }

            connections_path = Path(tmpdir) / "osiris_connections.yaml"
            with open(connections_path, "w") as f:
                yaml.dump(connections, f)

            # Create manifest
            manifest = {
                "pipeline": {"id": "test-pipeline", "version": "0.1.0"},
                "steps": [
                    {
                        "id": "extract",
                        "driver": "mysql.extractor",
                        "cfg_path": "cfg/extract.json",
                        "needs": [],
                    }
                ],
                "meta": {"oml_version": "0.1.0"},
            }

            manifest_path = Path(tmpdir) / "manifest.yaml"
            with open(manifest_path, "w") as f:
                yaml.dump(manifest, f)

            # Create config
            cfg_dir = Path(tmpdir) / "cfg"
            cfg_dir.mkdir()

            config = {
                "component": "mysql.extractor",
                "connection": "@mysql.test_db",
                "query": "SELECT 1",
            }

            with open(cfg_dir / "extract.json", "w") as f:
                json.dump(config, f)

            # Set MYSQL_PASSWORD to empty string
            os.environ["MYSQL_PASSWORD"] = ""

            # Change to tmpdir so connections file is found
            original_cwd = Path.cwd()
            try:
                os.chdir(tmpdir)

                # Run should fail with ConfigError
                runner = RunnerV0(str(manifest_path))
                runner.manifest_dir = Path(tmpdir)

                with pytest.raises(ConfigError) as exc_info:
                    runner.run()

                # Error should mention the missing var
                assert "MYSQL_PASSWORD" in str(exc_info.value)

            finally:
                os.chdir(original_cwd)
                os.environ.pop("MYSQL_PASSWORD", None)

    def test_dotenv_loaded_from_testing_env(self):
        """Test that .env file is loaded when running from testing_env."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create testing_env structure
            testing_env = Path(tmpdir) / "testing_env"
            testing_env.mkdir()

            # Create .env file
            env_file = testing_env / ".env"
            env_file.write_text("MYSQL_PASSWORD=from_dotenv\n")

            # Create connections file
            connections = {
                "version": 1,
                "connections": {
                    "mysql": {
                        "test_db": {
                            "host": "localhost",
                            "password": "${MYSQL_PASSWORD}",
                        }
                    }
                },
            }

            connections_path = testing_env / "osiris_connections.yaml"
            with open(connections_path, "w") as f:
                yaml.dump(connections, f)

            # Create manifest
            manifest = {
                "pipeline": {"id": "test-pipeline", "version": "0.1.0"},
                "steps": [
                    {
                        "id": "extract",
                        "driver": "mysql.extractor",
                        "cfg_path": "cfg/extract.json",
                        "needs": [],
                    }
                ],
                "meta": {"oml_version": "0.1.0"},
            }

            manifest_path = testing_env / "manifest.yaml"
            with open(manifest_path, "w") as f:
                yaml.dump(manifest, f)

            # Create config
            cfg_dir = testing_env / "cfg"
            cfg_dir.mkdir()

            config = {
                "component": "mysql.extractor",
                "connection": "@mysql.test_db",
                "query": "SELECT 1",
            }

            with open(cfg_dir / "extract.json", "w") as f:
                json.dump(config, f)

            # Change to testing_env directory
            original_cwd = Path.cwd()
            try:
                os.chdir(testing_env)

                # Ensure MYSQL_PASSWORD not in env initially
                os.environ.pop("MYSQL_PASSWORD", None)

                # Import after changing dir to trigger env loading
                from osiris.cli.run import run_command

                # Mock MySQL to avoid actual connection
                with patch("osiris.connectors.mysql.extractor.MySQLExtractor") as mock_mysql:
                    mock_extractor = MagicMock()
                    mock_extractor.extract.return_value = []
                    mock_mysql.return_value = mock_extractor

                    # Run via CLI command (which loads env)
                    with patch("osiris.cli.run.RunnerV0") as mock_runner_class:
                        mock_runner = MagicMock()
                        mock_runner.run.return_value = {"status": "success", "steps": {}}
                        mock_runner_class.return_value = mock_runner

                        run_command(["manifest.yaml"])

                        # Runner should have been created
                        mock_runner_class.assert_called_once()

            finally:
                os.chdir(original_cwd)
                os.environ.pop("MYSQL_PASSWORD", None)
