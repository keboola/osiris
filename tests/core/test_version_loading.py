"""Tests for version loading mechanism in osiris/__init__.py.

This module tests the three-tier fallback strategy:
1. Development mode: Read from pyproject.toml (primary)
2. Production mode: Read from package metadata via importlib.metadata (fallback)
3. Unknown fallback: Return "unknown" if both fail (last resort)
"""

from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import pytest


def test_version_loaded_successfully():
    """Test that __version__ is loaded and is a non-empty string."""
    import osiris

    assert hasattr(osiris, "__version__")
    assert isinstance(osiris.__version__, str)
    assert len(osiris.__version__) > 0
    assert osiris.__version__ != "unknown"


def test_version_format():
    """Test that __version__ follows semver format (X.Y.Z)."""
    import osiris

    # Should be either semver format (0.5.4) or "unknown"
    version = osiris.__version__
    if version != "unknown":
        parts = version.split(".")
        assert len(parts) >= 2, f"Version should have at least 2 parts: {version}"
        # First two parts should be numeric
        assert parts[0].isdigit(), f"Major version should be numeric: {version}"
        assert parts[1].isdigit(), f"Minor version should be numeric: {version}"


def test_fallback_to_importlib_metadata(tmp_path, monkeypatch):
    """Test that version falls back to importlib.metadata when pyproject.toml is missing.

    This simulates the production scenario where the package is installed via wheel
    and pyproject.toml is not included in the distribution.
    """
    # Create a mock module to simulate fresh import
    mock_version_func = MagicMock(return_value="0.5.4")

    # Mock the Path to make pyproject.toml appear missing
    def mock_read_text():
        raise FileNotFoundError("pyproject.toml not found")

    with patch("pathlib.Path.read_text", side_effect=mock_read_text):
        with patch("importlib.metadata.version", mock_version_func):
            # Force reimport to trigger fallback logic
            if "osiris" in sys.modules:
                del sys.modules["osiris"]

            import osiris

            # Should have fallen back to importlib.metadata
            assert osiris.__version__ == "0.5.4"
            mock_version_func.assert_called_once_with("osiris-pipeline")


def test_fallback_to_unknown_when_all_fail(monkeypatch):
    """Test that version falls back to 'unknown' when both methods fail.

    This is the last resort fallback that should rarely happen in practice.
    """

    # Mock both fallback mechanisms to fail
    def mock_read_text():
        raise FileNotFoundError("pyproject.toml not found")

    def mock_version(package_name):
        raise Exception("Package not found in metadata")

    with patch("pathlib.Path.read_text", side_effect=mock_read_text):
        with patch("importlib.metadata.version", side_effect=mock_version):
            # Force reimport to trigger fallback logic
            if "osiris" in sys.modules:
                del sys.modules["osiris"]

            import osiris

            # Should have fallen back to "unknown"
            assert osiris.__version__ == "unknown"


def test_development_mode_uses_pyproject_toml():
    """Test that development mode reads from pyproject.toml.

    In development (editable install), pyproject.toml should be present
    and readable, so this should be the primary code path.
    """
    # In CI/dev environment, pyproject.toml should exist
    project_root = Path(__file__).parent.parent.parent
    pyproject_file = project_root / "pyproject.toml"

    if pyproject_file.exists():
        # If pyproject.toml exists, version should match what's in the file
        import tomllib

        expected_version = tomllib.loads(pyproject_file.read_text())["project"]["version"]

        # Force fresh import to test primary path
        if "osiris" in sys.modules:
            del sys.modules["osiris"]

        import osiris

        # Should read from pyproject.toml in development mode
        assert osiris.__version__ == expected_version
    else:
        # In production install, pyproject.toml may not exist
        # Skip this test as we're testing development mode
        pytest.skip("pyproject.toml not found - skipping development mode test")
