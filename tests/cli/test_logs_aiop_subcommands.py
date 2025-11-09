# Copyright (c) 2025 Osiris Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for osiris logs aiop subcommands (list, show, export, prune)."""

from pathlib import Path
import subprocess
import sys

import pytest

# Get the absolute path to osiris.py from project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
OSIRIS_SCRIPT = PROJECT_ROOT / "osiris.py"


def test_aiop_command_help():
    """Test that 'osiris logs aiop --help' shows subcommands."""
    result = subprocess.run(
        [sys.executable, str(OSIRIS_SCRIPT), "logs", "aiop", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "list" in result.stdout
    assert "show" in result.stdout
    assert "export" in result.stdout
    assert "prune" in result.stdout


def test_aiop_list_help():
    """Test that 'osiris logs aiop list --help' works."""
    result = subprocess.run(
        [sys.executable, str(OSIRIS_SCRIPT), "logs", "aiop", "list", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--pipeline" in result.stdout
    assert "--profile" in result.stdout


def test_aiop_show_help():
    """Test that 'osiris logs aiop show --help' works."""
    result = subprocess.run(
        [sys.executable, str(OSIRIS_SCRIPT), "logs", "aiop", "show", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--run" in result.stdout


def test_aiop_export_help():
    """Test that 'osiris logs aiop export --help' works."""
    result = subprocess.run(
        [sys.executable, str(OSIRIS_SCRIPT), "logs", "aiop", "export", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--last-run" in result.stdout


def test_aiop_prune_help():
    """Test that 'osiris logs aiop prune --help' works."""
    result = subprocess.run(
        [sys.executable, str(OSIRIS_SCRIPT), "logs", "aiop", "prune", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--dry-run" in result.stdout


def test_aiop_unknown_subcommand():
    """Test that unknown subcommands are rejected."""
    result = subprocess.run(
        [sys.executable, str(OSIRIS_SCRIPT), "logs", "aiop", "invalid"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0  # Help shown, no error
    assert "Unknown subcommand" in result.stdout


def test_aiop_list_no_runs(tmp_path):
    """Test 'osiris logs aiop list' when no runs exist."""
    # This test verifies the command structure, not actual functionality
    # Actual functionality tests will be added once FilesystemContract is fully integrated
    # For now, we just verify that the command accepts the right arguments

    # Create minimal osiris.yaml in the project root
    config_file = PROJECT_ROOT / "osiris.yaml"
    if not config_file.exists():
        pytest.skip("osiris.yaml not found - skipping integration test")

    result = subprocess.run(
        [sys.executable, str(OSIRIS_SCRIPT), "logs", "aiop", "list", "--json"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )

    # Should not crash - may return 0 or 1 depending on whether runs exist
    assert result.returncode in (0, 1), f"Unexpected return code: {result.returncode}, stderr: {result.stderr}"
