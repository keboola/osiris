#!/usr/bin/env python3
"""
Tests for MCP entrypoint environment setup.

Tests the setup_environment() function that configures OSIRIS_HOME
and PYTHONPATH before the MCP server starts.
"""

import os
import sys


def test_pythonpath_appends_to_existing(tmp_path):
    """Test that PYTHONPATH appends to existing value instead of replacing it."""
    # Setup
    existing_path = "/some/existing/path:/another/path"

    # Temporarily modify environment and sys.path
    original_pythonpath = os.environ.get("PYTHONPATH")
    original_sys_path = sys.path.copy()
    original_osiris_home = os.environ.get("OSIRIS_HOME")

    try:
        # Set existing PYTHONPATH (without repo_root to simulate fresh environment)
        os.environ["PYTHONPATH"] = existing_path

        # Import and run setup_environment
        # We need to reload the module to test the setup function
        from osiris.cli.mcp_entrypoint import setup_environment  # noqa: PLC0415

        repo_root, osiris_home = setup_environment()

        # Verify PYTHONPATH was extended, not replaced
        result_pythonpath = os.environ["PYTHONPATH"]

        # Should start with repo_root
        assert result_pythonpath.startswith(str(repo_root))

        # Should contain the existing paths
        assert existing_path in result_pythonpath

        # Should be in format: repo_root:existing_path
        # Note: May have duplicate repo_root if already loaded, so just verify pattern
        assert f":{existing_path}" in result_pythonpath or result_pythonpath.endswith(existing_path)
        assert str(repo_root) in result_pythonpath

    finally:
        # Restore original environment
        if original_pythonpath is not None:
            os.environ["PYTHONPATH"] = original_pythonpath
        elif "PYTHONPATH" in os.environ:
            del os.environ["PYTHONPATH"]

        sys.path = original_sys_path

        if original_osiris_home is not None:
            os.environ["OSIRIS_HOME"] = original_osiris_home
        elif "OSIRIS_HOME" in os.environ:
            del os.environ["OSIRIS_HOME"]


def test_pythonpath_sets_when_not_existing(tmp_path):
    """Test that PYTHONPATH is set correctly when not previously defined."""
    # Temporarily modify environment
    original_pythonpath = os.environ.get("PYTHONPATH")
    original_sys_path = sys.path.copy()
    original_osiris_home = os.environ.get("OSIRIS_HOME")

    try:
        # Remove PYTHONPATH if it exists
        if "PYTHONPATH" in os.environ:
            del os.environ["PYTHONPATH"]

        # Import and run setup_environment
        from osiris.cli.mcp_entrypoint import setup_environment  # noqa: PLC0415

        repo_root, osiris_home = setup_environment()

        # Verify PYTHONPATH was set to repo_root only
        result_pythonpath = os.environ["PYTHONPATH"]
        assert result_pythonpath == str(repo_root)

    finally:
        # Restore original environment
        if original_pythonpath is not None:
            os.environ["PYTHONPATH"] = original_pythonpath
        elif "PYTHONPATH" in os.environ:
            del os.environ["PYTHONPATH"]

        sys.path = original_sys_path

        if original_osiris_home is not None:
            os.environ["OSIRIS_HOME"] = original_osiris_home
        elif "OSIRIS_HOME" in os.environ:
            del os.environ["OSIRIS_HOME"]


def test_pythonpath_handles_empty_string(tmp_path):
    """Test that PYTHONPATH handles empty string correctly (treats as not set)."""
    # Temporarily modify environment
    original_pythonpath = os.environ.get("PYTHONPATH")
    original_sys_path = sys.path.copy()
    original_osiris_home = os.environ.get("OSIRIS_HOME")

    try:
        # Set PYTHONPATH to empty string
        os.environ["PYTHONPATH"] = ""

        # Import and run setup_environment
        from osiris.cli.mcp_entrypoint import setup_environment  # noqa: PLC0415

        repo_root, osiris_home = setup_environment()

        # Verify PYTHONPATH was set to repo_root only (empty string stripped)
        result_pythonpath = os.environ["PYTHONPATH"]
        assert result_pythonpath == str(repo_root)

    finally:
        # Restore original environment
        if original_pythonpath is not None:
            os.environ["PYTHONPATH"] = original_pythonpath
        elif "PYTHONPATH" in os.environ:
            del os.environ["PYTHONPATH"]

        sys.path = original_sys_path

        if original_osiris_home is not None:
            os.environ["OSIRIS_HOME"] = original_osiris_home
        elif "OSIRIS_HOME" in os.environ:
            del os.environ["OSIRIS_HOME"]


def test_pythonpath_handles_whitespace_only(tmp_path):
    """Test that PYTHONPATH handles whitespace-only string correctly."""
    # Temporarily modify environment
    original_pythonpath = os.environ.get("PYTHONPATH")
    original_sys_path = sys.path.copy()
    original_osiris_home = os.environ.get("OSIRIS_HOME")

    try:
        # Set PYTHONPATH to whitespace only
        os.environ["PYTHONPATH"] = "   "

        # Import and run setup_environment
        from osiris.cli.mcp_entrypoint import setup_environment  # noqa: PLC0415

        repo_root, osiris_home = setup_environment()

        # Verify PYTHONPATH was set to repo_root only (whitespace stripped)
        result_pythonpath = os.environ["PYTHONPATH"]
        assert result_pythonpath == str(repo_root)

    finally:
        # Restore original environment
        if original_pythonpath is not None:
            os.environ["PYTHONPATH"] = original_pythonpath
        elif "PYTHONPATH" in os.environ:
            del os.environ["PYTHONPATH"]

        sys.path = original_sys_path

        if original_osiris_home is not None:
            os.environ["OSIRIS_HOME"] = original_osiris_home
        elif "OSIRIS_HOME" in os.environ:
            del os.environ["OSIRIS_HOME"]


def test_osiris_home_uses_env_when_set(tmp_path):
    """Test that OSIRIS_HOME env variable is respected when set."""
    # Temporarily modify environment
    original_osiris_home = os.environ.get("OSIRIS_HOME")
    original_sys_path = sys.path.copy()
    original_pythonpath = os.environ.get("PYTHONPATH")

    custom_home = tmp_path / "custom_osiris_home"

    try:
        # Set custom OSIRIS_HOME
        os.environ["OSIRIS_HOME"] = str(custom_home)

        # Import and run setup_environment
        from osiris.cli.mcp_entrypoint import setup_environment  # noqa: PLC0415

        repo_root, osiris_home = setup_environment()

        # Verify OSIRIS_HOME was used and created
        assert osiris_home == custom_home.resolve()
        assert custom_home.exists()
        assert custom_home.is_dir()

    finally:
        # Restore original environment
        if original_osiris_home is not None:
            os.environ["OSIRIS_HOME"] = original_osiris_home
        elif "OSIRIS_HOME" in os.environ:
            del os.environ["OSIRIS_HOME"]

        sys.path = original_sys_path

        if original_pythonpath is not None:
            os.environ["PYTHONPATH"] = original_pythonpath
        elif "PYTHONPATH" in os.environ:
            del os.environ["PYTHONPATH"]


def test_osiris_home_defaults_to_testing_env(tmp_path):
    """Test that OSIRIS_HOME defaults to testing_env when not set."""
    # Temporarily modify environment
    original_osiris_home = os.environ.get("OSIRIS_HOME")
    original_sys_path = sys.path.copy()
    original_pythonpath = os.environ.get("PYTHONPATH")

    try:
        # Remove OSIRIS_HOME if it exists
        if "OSIRIS_HOME" in os.environ:
            del os.environ["OSIRIS_HOME"]

        # Import and run setup_environment
        from osiris.cli.mcp_entrypoint import setup_environment  # noqa: PLC0415

        repo_root, osiris_home = setup_environment()

        # Verify OSIRIS_HOME defaults to testing_env
        expected = (repo_root / "testing_env").resolve()
        assert osiris_home == expected

    finally:
        # Restore original environment
        if original_osiris_home is not None:
            os.environ["OSIRIS_HOME"] = original_osiris_home
        elif "OSIRIS_HOME" in os.environ:
            del os.environ["OSIRIS_HOME"]

        sys.path = original_sys_path

        if original_pythonpath is not None:
            os.environ["PYTHONPATH"] = original_pythonpath
        elif "PYTHONPATH" in os.environ:
            del os.environ["PYTHONPATH"]


def test_repo_root_added_to_sys_path():
    """Test that repo_root is added to sys.path."""
    from osiris.cli.mcp_entrypoint import find_repo_root  # noqa: PLC0415

    repo_root = find_repo_root()

    # Repo root should be in sys.path
    assert str(repo_root) in sys.path
