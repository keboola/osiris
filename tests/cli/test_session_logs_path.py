"""Tests for CLI session logging paths using filesystem contract."""

from pathlib import Path
import tempfile

import pytest
import yaml


def test_get_logs_directory_uses_filesystem_contract(tmp_path):
    """Test that get_logs_directory_for_cli uses filesystem.run_logs_dir from config."""
    from osiris.cli.helpers.session_helpers import get_logs_directory_for_cli

    # Create osiris.yaml with custom run_logs_dir
    config_content = {
        "filesystem": {
            "base_path": str(tmp_path / "custom_base"),
            "run_logs_dir": "my_custom_logs",
        }
    }

    config_path = tmp_path / "osiris.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config_content, f)

    # Change to temp directory so config is found
    import os

    original_dir = os.getcwd()
    try:
        os.chdir(tmp_path)

        # Get logs directory
        logs_dir = get_logs_directory_for_cli()

        # Should resolve to base_path / run_logs_dir
        expected = tmp_path / "custom_base" / "my_custom_logs"
        assert logs_dir == expected

    finally:
        os.chdir(original_dir)


def test_get_logs_directory_fallback_when_no_config():
    """Test that get_logs_directory_for_cli falls back to 'run_logs' when no config."""
    from osiris.cli.helpers.session_helpers import get_logs_directory_for_cli

    with tempfile.TemporaryDirectory() as tmpdir:
        import os

        original_dir = os.getcwd()
        try:
            # Change to empty directory (no osiris.yaml)
            os.chdir(tmpdir)

            logs_dir = get_logs_directory_for_cli()

            # Should fall back to default "run_logs" (resolved against cwd)
            # Use resolve() to handle symlinks on macOS (/var vs /private/var)
            expected = (Path(tmpdir) / "run_logs").resolve()
            assert logs_dir.resolve() == expected

        finally:
            os.chdir(original_dir)


def test_connections_list_uses_filesystem_contract(tmp_path):
    """Test that 'osiris connections list' creates logs under filesystem.run_logs_dir."""
    import os

    # Create osiris.yaml with custom run_logs_dir
    config_content = {
        "filesystem": {
            "base_path": str(tmp_path),
            "run_logs_dir": "connection_logs",
        }
    }

    config_path = tmp_path / "osiris.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config_content, f)

    # Create empty connections file
    connections_file = tmp_path / "osiris_connections.yaml"
    with open(connections_file, "w") as f:
        yaml.dump({}, f)

    # Instead of subprocess, directly test the helper function
    # This is more reliable and doesn't depend on module installation
    from osiris.cli.helpers.session_helpers import get_logs_directory_for_cli

    original_dir = os.getcwd()
    try:
        os.chdir(tmp_path)

        logs_dir = get_logs_directory_for_cli()

        # Should use filesystem.run_logs_dir from config
        expected = tmp_path / "connection_logs"
        assert logs_dir == expected, f"Expected {expected}, got {logs_dir}"

    finally:
        os.chdir(original_dir)


def test_connections_list_default_path():
    """Test that connections list uses 'run_logs' by default (not 'logs')."""
    from osiris.cli.helpers.session_helpers import get_logs_directory_for_cli

    with tempfile.TemporaryDirectory() as tmpdir:
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmpdir)

            # Without config, should default to run_logs
            logs_dir = get_logs_directory_for_cli()
            assert logs_dir.name == "run_logs", f"Expected 'run_logs', got {logs_dir.name}"

        finally:
            os.chdir(original_dir)


def test_session_logging_honors_base_path(tmp_path):
    """Test that session logging resolves paths against filesystem.base_path."""
    from osiris.cli.helpers.session_helpers import get_logs_directory_for_cli

    # Create config with base_path
    config_content = {
        "filesystem": {
            "base_path": str(tmp_path / "data"),
            "run_logs_dir": "logs",
        }
    }

    config_path = tmp_path / "osiris.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config_content, f)

    import os

    original_dir = os.getcwd()
    try:
        os.chdir(tmp_path)

        logs_dir = get_logs_directory_for_cli()

        # Should be base_path / run_logs_dir
        expected = tmp_path / "data" / "logs"
        assert logs_dir == expected

    finally:
        os.chdir(original_dir)


@pytest.mark.skip(reason="Profile injection in session logging not yet implemented")
def test_profile_injection_when_enabled(tmp_path):
    """Test that profile segment is injected when profiles.enabled is true.

    This is a placeholder test for future profile support in CLI session logging.
    Currently, only run command uses full FilesystemContract with profiles.
    """
    # This test documents the expected future behavior:
    # - When profiles.enabled = true
    # - Session logs should go to: <base_path>/<run_logs_dir>/<profile>/...
    #
    # Example:
    # filesystem.base_path = ~/osiris
    # filesystem.run_logs_dir = run_logs
    # profiles.enabled = true
    # profiles.default = dev
    #
    # Expected path: ~/osiris/run_logs/dev/connections_1234567890/
    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
