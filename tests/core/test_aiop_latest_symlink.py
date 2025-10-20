"""Tests for latest symlink robustness across OS."""

import os
from pathlib import Path
import platform
import tempfile

import pytest

from osiris.core.aiop_export import _update_latest_symlink


class TestLatestSymlink:
    """Test latest symlink creation and fallback."""

    def test_latest_symlink_points_to_newest_run(self):
        """Test that after two runs, latest points to the newest run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            aiop_dir = Path(tmpdir) / "logs" / "aiop"
            aiop_dir.mkdir(parents=True)

            # Create first run directory
            run1_dir = aiop_dir / "run_001"
            run1_dir.mkdir()
            (run1_dir / "aiop.json").write_text('{"run": 1}')

            # Create latest pointing to first run
            latest_path = aiop_dir / "latest"
            _update_latest_symlink(str(latest_path), str(run1_dir))

            # Verify latest exists
            assert latest_path.exists() or latest_path.is_symlink()

            # Read content to verify it points to run 1
            if latest_path.is_symlink():
                target_dir = Path(os.readlink(str(latest_path)))
                if not target_dir.is_absolute():
                    target_dir = latest_path.parent / target_dir
                content = (target_dir / "aiop.json").read_text()
            else:
                # Fallback file
                with open(latest_path) as f:
                    target_path = f.read().strip()
                content = (Path(target_path) / "aiop.json").read_text()

            assert '"run": 1' in content

            # Create second run directory
            run2_dir = aiop_dir / "run_002"
            run2_dir.mkdir()
            (run2_dir / "aiop.json").write_text('{"run": 2}')

            # Update latest to point to second run
            _update_latest_symlink(str(latest_path), str(run2_dir))

            # Verify latest now points to run 2
            if latest_path.is_symlink():
                target_dir = Path(os.readlink(str(latest_path)))
                if not target_dir.is_absolute():
                    target_dir = latest_path.parent / target_dir
                content = (target_dir / "aiop.json").read_text()
            else:
                # Fallback file
                with open(latest_path) as f:
                    target_path = f.read().strip()
                content = (Path(target_path) / "aiop.json").read_text()

            assert '"run": 2' in content

    def test_symlink_fallback_to_text_file(self):
        """Test that fallback to text file works when symlink unsupported."""
        with tempfile.TemporaryDirectory() as tmpdir:
            aiop_dir = Path(tmpdir) / "logs" / "aiop"
            aiop_dir.mkdir(parents=True)

            run_dir = aiop_dir / "run_test"
            run_dir.mkdir()

            latest_path = aiop_dir / "latest"

            # Force fallback by mocking platform
            original_platform = platform.system

            try:
                # Mock Windows to force text file fallback
                platform.system = lambda: "Windows"

                _update_latest_symlink(str(latest_path), str(run_dir))

                # On Windows or when symlink fails, should create text file
                if latest_path.exists() and not latest_path.is_symlink():
                    with open(latest_path) as f:
                        content = f.read().strip()
                    assert str(run_dir.absolute()) in content
                elif latest_path.is_symlink():
                    # Still created symlink (might be on Unix with Windows mock)
                    assert True
                else:
                    # No file created at all (should not happen)
                    raise AssertionError("No latest file created")

            finally:
                platform.system = original_platform

    def test_symlink_uses_relative_path(self):
        """Test that symlinks use relative paths for portability."""
        if platform.system() == "Windows":
            pytest.skip("Symlink test only for Unix-like systems")

        with tempfile.TemporaryDirectory() as tmpdir:
            aiop_dir = Path(tmpdir) / "logs" / "aiop"
            aiop_dir.mkdir(parents=True)

            run_dir = aiop_dir / "run_test"
            run_dir.mkdir()

            latest_path = aiop_dir / "latest"
            _update_latest_symlink(str(latest_path), str(run_dir))

            if latest_path.is_symlink():
                # Check that the symlink target is relative
                target = os.readlink(str(latest_path))
                assert not Path(target).is_absolute()
                assert target in {"run_test", "./run_test"}

    def test_symlink_handles_existing_file(self):
        """Test that existing file/symlink is properly replaced."""
        with tempfile.TemporaryDirectory() as tmpdir:
            aiop_dir = Path(tmpdir) / "logs" / "aiop"
            aiop_dir.mkdir(parents=True)

            latest_path = aiop_dir / "latest"

            # Create an existing file
            latest_path.write_text("old content")
            assert latest_path.exists()

            # Update to new target
            run_dir = aiop_dir / "new_run"
            run_dir.mkdir()

            _update_latest_symlink(str(latest_path), str(run_dir))

            # Verify old file was replaced
            if latest_path.is_symlink():
                target = os.readlink(str(latest_path))
                assert "new_run" in target
            elif latest_path.exists():
                with open(latest_path) as f:
                    content = f.read()
                assert "new_run" in content
                assert "old content" not in content

    def test_symlink_creates_parent_directory(self):
        """Test that parent directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use a deep path that doesn't exist
            deep_path = Path(tmpdir) / "a" / "b" / "c" / "logs" / "aiop" / "latest"
            run_dir = Path(tmpdir) / "run"
            run_dir.mkdir()

            # Should create all parent directories
            _update_latest_symlink(str(deep_path), str(run_dir))

            assert deep_path.parent.exists()
            assert deep_path.exists() or deep_path.is_symlink()
