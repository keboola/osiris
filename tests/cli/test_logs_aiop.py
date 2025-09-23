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

"""Tests for osiris logs aiop command (PR1 stub)."""

from unittest.mock import patch

import pytest


def test_aiop_help():
    """Test that aiop --help displays help text."""
    from osiris.cli.logs import aiop_export

    with patch("osiris.cli.logs.console") as mock_console:
        aiop_export(["--help"])

        # Verify help was printed
        assert mock_console.print.called
        # Check for key help elements
        calls = str(mock_console.print.call_args_list)
        assert "osiris logs aiop" in calls
        assert "--session" in calls
        assert "--last" in calls
        assert "--output" in calls
        assert "--format" in calls
        assert "--policy" in calls


def test_aiop_last_flag():
    """Test that --last returns stub message with exit code 0."""
    from osiris.cli.logs import aiop_export

    with patch("osiris.cli.logs.console") as mock_console:
        # Should not raise SystemExit since we return normally
        aiop_export(["--last"])

        # Verify stub message
        mock_console.print.assert_called_with("AIOP export not implemented yet (PR2).")


def test_aiop_session_with_id():
    """Test that --session with valid ID returns stub message."""
    from osiris.cli.logs import aiop_export

    with patch("osiris.cli.logs.console") as mock_console:
        aiop_export(["--session", "run_123456"])

        # Verify stub message
        mock_console.print.assert_called_with("AIOP export not implemented yet (PR2).")


def test_aiop_session_empty():
    """Test that --session with empty string exits with code 2."""
    from osiris.cli.logs import aiop_export

    with patch("osiris.cli.logs.console") as mock_console:
        with pytest.raises(SystemExit) as exc_info:
            aiop_export(["--session", ""])

        # Verify exit code
        assert exc_info.value.code == 2

        # Verify error message - empty session triggers the general error
        calls = str(mock_console.print.call_args_list)
        assert (
            "Error: session id required" in calls
            or "Either --session or --last is required" in calls
        )


def test_aiop_missing_required():
    """Test that missing --session and --last exits with code 2."""
    from osiris.cli.logs import aiop_export

    with patch("osiris.cli.logs.console") as mock_console:
        with pytest.raises(SystemExit) as exc_info:
            aiop_export([])

        # Verify exit code
        assert exc_info.value.code == 2

        # Verify error message
        calls = str(mock_console.print.call_args_list)
        assert "Either --session or --last is required" in calls


def test_aiop_parse_all_flags():
    """Test that all flags are parsed correctly."""
    from osiris.cli.logs import aiop_export

    with patch("osiris.cli.logs.console") as mock_console:
        # Test with all optional flags
        aiop_export(
            [
                "--last",
                "--output",
                "aiop.json",
                "--format",
                "json",
                "--policy",
                "annex",
                "--max-core-bytes",
                "500000",
                "--annex-dir",
                "/tmp/annex",
                "--timeline-density",
                "high",
                "--metrics-topk",
                "50",
                "--schema-mode",
                "detailed",
            ]
        )

        # Should still print stub message
        mock_console.print.assert_called_with("AIOP export not implemented yet (PR2).")


def test_aiop_invalid_format():
    """Test that invalid format choice is rejected."""
    from osiris.cli.logs import aiop_export

    with patch("osiris.cli.logs.console") as mock_console:
        # Invalid format should fail argument parsing
        aiop_export(["--last", "--format", "invalid"])

        # Check for error message
        calls = str(mock_console.print.call_args_list)
        assert "Invalid arguments" in calls


def test_aiop_invalid_policy():
    """Test that invalid policy choice is rejected."""
    from osiris.cli.logs import aiop_export

    with patch("osiris.cli.logs.console") as mock_console:
        # Invalid policy should fail argument parsing
        aiop_export(["--last", "--policy", "invalid"])

        # Check for error message
        calls = str(mock_console.print.call_args_list)
        assert "Invalid arguments" in calls


def test_aiop_invalid_timeline_density():
    """Test that invalid timeline density is rejected."""
    from osiris.cli.logs import aiop_export

    with patch("osiris.cli.logs.console") as mock_console:
        # Invalid timeline density should fail argument parsing
        aiop_export(["--last", "--timeline-density", "invalid"])

        # Check for error message
        calls = str(mock_console.print.call_args_list)
        assert "Invalid arguments" in calls


def test_aiop_invalid_schema_mode():
    """Test that invalid schema mode is rejected."""
    from osiris.cli.logs import aiop_export

    with patch("osiris.cli.logs.console") as mock_console:
        # Invalid schema mode should fail argument parsing
        aiop_export(["--last", "--schema-mode", "invalid"])

        # Check for error message
        calls = str(mock_console.print.call_args_list)
        assert "Invalid arguments" in calls
