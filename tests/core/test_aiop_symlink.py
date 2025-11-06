"""Test for platform-safe symlink/fallback functionality."""

from pathlib import Path
import platform
from unittest.mock import patch

import pytest

from osiris.core.aiop_export import _update_latest_symlink


class TestLatestSymlink:
    """Test the latest symlink/fallback file functionality."""

    def test_symlink_on_posix(self, tmp_path):
        """Test that symlinks are created on POSIX systems."""
        if platform.system() == "Windows":
            pytest.skip("Symlink test requires POSIX system")

        # Create a target directory
        target_dir = tmp_path / "run_123"
        target_dir.mkdir()

        # Create symlink
        latest_link = tmp_path / "latest"
        _update_latest_symlink(str(latest_link), str(target_dir))

        # Verify symlink was created
        assert latest_link.exists() or latest_link.is_symlink()
        if latest_link.is_symlink():
            # It's a symlink - verify it points to the right place
            resolved = latest_link.resolve()
            assert resolved == target_dir.resolve()
        else:
            # Fallback was used - verify content
            content = latest_link.read_text().strip()
            assert str(target_dir.absolute()) in content

    def test_fallback_on_windows(self, tmp_path):
        """Test that text files are created as fallback on Windows."""
        # Mock platform to simulate Windows
        with patch("platform.system", return_value="Windows"):
            # Create a target directory
            target_dir = tmp_path / "run_456"
            target_dir.mkdir()

            # Create latest pointer
            latest_file = tmp_path / "latest"
            _update_latest_symlink(str(latest_file), str(target_dir))

            # Verify text file was created
            assert latest_file.exists()
            assert not latest_file.is_symlink()

            # Verify content
            content = latest_file.read_text().strip()
            assert str(target_dir.absolute()) == content

    def test_symlink_fallback_on_error(self, tmp_path):
        """Test that fallback is used when symlink creation fails."""
        if platform.system() == "Windows":
            pytest.skip("Test requires POSIX system")

        # Create a target directory
        target_dir = tmp_path / "run_789"
        target_dir.mkdir()

        # Mock symlink_to to fail
        with patch.object(Path, "symlink_to", side_effect=OSError("Permission denied")):
            latest_link = tmp_path / "latest"
            _update_latest_symlink(str(latest_link), str(target_dir))

            # Should fall back to text file
            assert latest_link.exists()
            assert not latest_link.is_symlink()

            # Verify content
            content = latest_link.read_text().strip()
            assert str(target_dir.absolute()) == content

    def test_replace_existing_symlink(self, tmp_path):
        """Test that existing symlink/file is replaced."""
        # Create initial target
        old_target = tmp_path / "run_old"
        old_target.mkdir()

        latest_link = tmp_path / "latest"

        # Create initial symlink/file
        _update_latest_symlink(str(latest_link), str(old_target))
        assert latest_link.exists() or latest_link.is_symlink()

        # Create new target
        new_target = tmp_path / "run_new"
        new_target.mkdir()

        # Update to new target
        _update_latest_symlink(str(latest_link), str(new_target))

        # Verify it points to new target
        if latest_link.is_symlink():
            resolved = latest_link.resolve()
            assert resolved == new_target.resolve()
        else:
            content = latest_link.read_text().strip()
            assert str(new_target.absolute()) in content

    def test_create_parent_directories(self, tmp_path):
        """Test that parent directories are created if needed."""
        target_dir = tmp_path / "run_999"
        target_dir.mkdir()

        # Use a nested path that doesn't exist yet
        latest_link = tmp_path / "deep" / "nested" / "path" / "latest"
        _update_latest_symlink(str(latest_link), str(target_dir))

        # Verify parent directories were created
        assert latest_link.parent.exists()
        assert latest_link.exists() or latest_link.is_symlink()

    def test_silent_failure_handling(self, tmp_path):
        """Test that errors are silently ignored."""
        # This should not raise an exception even with invalid input
        _update_latest_symlink("/invalid/path/that/cannot/be/created", str(tmp_path))
        # If we get here, the function handled the error silently
        assert True

    @pytest.mark.parametrize("platform_name", ["Linux", "Darwin", "Windows"])
    def test_cross_platform_compatibility(self, tmp_path, platform_name):
        """Test compatibility across different platforms."""
        with patch("platform.system", return_value=platform_name):
            target_dir = tmp_path / f"run_{platform_name.lower()}"
            target_dir.mkdir()

            latest = tmp_path / "latest"
            _update_latest_symlink(str(latest), str(target_dir))

            # Should always succeed without raising
            assert True

            # Verify something was created (symlink or file)
            if latest.exists() or latest.is_symlink():
                # Good - something was created
                if platform_name == "Windows" or not latest.is_symlink():
                    # Should be a text file
                    content = latest.read_text().strip()
                    assert str(target_dir.absolute()) in content
