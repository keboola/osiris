#!/usr/bin/env python3
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

"""Tests for osiris logs aiop subcommands."""

from unittest.mock import patch


def test_aiop_help():
    """Test that aiop command displays help text with subcommands."""
    from osiris.cli.logs import aiop_command

    with patch("osiris.cli.logs.console") as mock_console:
        aiop_command([])

        # Verify help was printed
        assert mock_console.print.called
        # Check for key help elements
        calls = str(mock_console.print.call_args_list)
        assert "AIOP Management" in calls or "aiop" in calls.lower()
        # Should list subcommands
        assert "list" in calls
        assert "show" in calls
        assert "export" in calls
        assert "prune" in calls


def test_aiop_export_last_run_no_runs(tmp_path, monkeypatch):
    """Test that export --last-run fails gracefully when no runs exist."""
    from osiris.cli.logs import aiop_export

    monkeypatch.chdir(tmp_path)

    # Create minimal osiris.yaml
    osiris_yaml = tmp_path / "osiris.yaml"
    osiris_yaml.write_text(
        """
version: "2.0"
filesystem:
  run_logs: "run_logs"
  aiop:
    root: "aiop"
"""
    )

    with patch("osiris.cli.logs.console"):
        with patch("sys.exit") as mock_exit:
            # Should exit when no runs found
            aiop_export(["--last-run"])
            # Should have called exit
            assert mock_exit.called


def test_aiop_export_with_run_id_not_found(tmp_path, monkeypatch):
    """Test that export --run exits when run ID not found."""
    from osiris.cli.logs import aiop_export

    monkeypatch.chdir(tmp_path)

    # Create minimal osiris.yaml
    osiris_yaml = tmp_path / "osiris.yaml"
    osiris_yaml.write_text(
        """
version: "2.0"
filesystem:
  run_logs: "run_logs"
  aiop:
    root: "aiop"
"""
    )

    with patch("osiris.cli.logs.console"):
        with patch("sys.exit") as mock_exit:
            # Non-existent run ID
            aiop_export(["--run", "nonexistent_run_123"])
            # Should have called exit
            assert mock_exit.called


def test_aiop_list_empty(tmp_path, monkeypatch):
    """Test that list works with no runs."""
    from osiris.cli.logs import aiop_list

    monkeypatch.chdir(tmp_path)

    # Create minimal osiris.yaml
    osiris_yaml = tmp_path / "osiris.yaml"
    osiris_yaml.write_text(
        """
version: "2.0"
filesystem:
  run_logs: "run_logs"
  aiop:
    root: "aiop"
"""
    )

    with patch("osiris.cli.logs.console"):
        # Should handle empty case gracefully
        aiop_list([])
        # No exception means success


def test_aiop_show_missing_run_id():
    """Test that show without --run shows help."""
    from osiris.cli.logs import aiop_show

    with patch("osiris.cli.logs.console") as mock_console:
        # Missing required --run flag shows help
        aiop_show([])
        # Should have printed help
        assert mock_console.print.called
        calls = str(mock_console.print.call_args_list)
        assert "Show AIOP Summary" in calls or "--run" in calls


def test_aiop_prune_dry_run(tmp_path, monkeypatch):
    """Test that prune --dry-run works."""
    from osiris.cli.logs import aiop_prune

    monkeypatch.chdir(tmp_path)

    # Create minimal osiris.yaml
    osiris_yaml = tmp_path / "osiris.yaml"
    osiris_yaml.write_text(
        """
version: "2.0"
filesystem:
  run_logs: "run_logs"
  aiop:
    root: "aiop"
"""
    )

    with patch("osiris.cli.logs.console"):
        # Dry run should succeed even with no data
        aiop_prune(["--dry-run"])
        # No exception means success
