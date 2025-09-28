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

"""Tests for CLI logs commands."""

import json
import os
import tempfile
import time
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from osiris.cli.logs import (
    _format_duration,
    _format_size,
    _get_directory_size,
    _get_session_info,
    bundle_session,
    gc_sessions,
    list_sessions,
    show_session,
)


class TestSessionInfoUtils:
    """Test utility functions for session info."""

    def test_get_session_info_valid_session(self):
        """Test getting session info from valid session directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            session_dir = Path(temp_dir) / "test_session_123"
            session_dir.mkdir()

            # Create events.jsonl with session data
            events_file = session_dir / "events.jsonl"
            events = [
                {"ts": "2025-09-01T10:00:00Z", "session": "test_session_123", "event": "run_start"},
                {
                    "ts": "2025-09-01T10:05:30Z",
                    "session": "test_session_123",
                    "event": "cache_hit",
                    "key": "abc123",
                },
                {
                    "ts": "2025-09-01T10:10:00Z",
                    "session": "test_session_123",
                    "event": "run_end",
                    "duration_seconds": 600,
                },
            ]

            with open(events_file, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            # Create some files for size calculation
            (session_dir / "osiris.log").write_text("log content")
            (session_dir / "test.txt").write_text("test content")

            info = _get_session_info(session_dir)

            assert info is not None
            assert info["session_id"] == "test_session_123"
            assert info["start_time"] == "2025-09-01T10:00:00Z"
            assert info["end_time"] == "2025-09-01T10:10:00Z"
            assert info["status"] == "completed"
            assert info["event_count"] == 3
            assert info["duration_seconds"] == 600
            assert info["size_bytes"] > 0

    def test_get_session_info_no_events(self):
        """Test getting session info when no events.jsonl exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            session_dir = Path(temp_dir) / "empty_session"
            session_dir.mkdir()

            info = _get_session_info(session_dir)
            assert info is None

    def test_get_session_info_running_session(self):
        """Test session info for running session (only run_start event)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            session_dir = Path(temp_dir) / "running_session"
            session_dir.mkdir()

            events_file = session_dir / "events.jsonl"
            events = [{"ts": "2025-09-01T10:00:00Z", "session": "running_session", "event": "run_start"}]

            with open(events_file, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            info = _get_session_info(session_dir)

            assert info is not None
            assert info["status"] == "running"
            assert info["duration_seconds"] is None  # No end time

    def test_get_session_info_error_session(self):
        """Test session info for session that ended with error."""
        with tempfile.TemporaryDirectory() as temp_dir:
            session_dir = Path(temp_dir) / "error_session"
            session_dir.mkdir()

            events_file = session_dir / "events.jsonl"
            events = [
                {"ts": "2025-09-01T10:00:00Z", "session": "error_session", "event": "run_start"},
                {
                    "ts": "2025-09-01T10:05:00Z",
                    "session": "error_session",
                    "event": "run_error",
                    "error_type": "ValueError",
                },
            ]

            with open(events_file, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            info = _get_session_info(session_dir)

            assert info is not None
            assert info["status"] == "error"

    def test_get_directory_size(self):
        """Test directory size calculation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_dir = Path(temp_dir) / "test_size"
            test_dir.mkdir()

            # Create files of known sizes
            (test_dir / "file1.txt").write_text("a" * 100)  # 100 bytes
            (test_dir / "file2.txt").write_text("b" * 200)  # 200 bytes

            # Create subdirectory with file
            subdir = test_dir / "subdir"
            subdir.mkdir()
            (subdir / "file3.txt").write_text("c" * 50)  # 50 bytes

            total_size = _get_directory_size(test_dir)
            assert total_size == 350  # 100 + 200 + 50

    def test_format_size(self):
        """Test size formatting."""
        assert _format_size(512) == "512.0B"
        assert _format_size(1024) == "1.0KB"
        assert _format_size(1536) == "1.5KB"  # 1.5 KB
        assert _format_size(1024 * 1024) == "1.0MB"
        assert _format_size(1024 * 1024 * 1024) == "1.0GB"

    def test_format_duration(self):
        """Test duration formatting."""
        assert _format_duration(None) == "unknown"
        assert _format_duration(30) == "30.0s"
        assert _format_duration(90) == "1.5m"
        assert _format_duration(3600) == "1.0h"
        assert _format_duration(7200) == "2.0h"


class TestListSessions:
    """Test list_sessions command."""

    def test_list_sessions_empty_directory(self):
        """Test listing sessions when no sessions exist."""
        with tempfile.TemporaryDirectory() as temp_dir, patch("sys.stdout"):
            list_sessions(["--logs-dir", temp_dir])

            # Should not crash and should indicate no sessions found

    def test_list_sessions_with_sessions(self):
        """Test listing sessions with actual session directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_dir = Path(temp_dir)

            # Create mock session directories
            for i, status in enumerate(["completed", "error", "running"]):
                session_id = f"test_session_{i}"
                session_dir = logs_dir / session_id
                session_dir.mkdir()

                # Create events.jsonl
                events_file = session_dir / "events.jsonl"
                events = [{"ts": f"2025-09-01T10:0{i}:00Z", "session": session_id, "event": "run_start"}]

                if status == "completed":
                    events.append({"ts": f"2025-09-01T10:1{i}:00Z", "session": session_id, "event": "run_end"})
                elif status == "error":
                    events.append(
                        {
                            "ts": f"2025-09-01T10:1{i}:00Z",
                            "session": session_id,
                            "event": "run_error",
                        }
                    )

                with open(events_file, "w") as f:
                    for event in events:
                        f.write(json.dumps(event) + "\n")

            # Test regular output
            with patch("rich.console.Console.print") as mock_print:
                list_sessions(["--logs-dir", temp_dir])

                # Should have called print to display table
                assert mock_print.called

    def test_list_sessions_json_output(self):
        """Test list sessions with JSON output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_dir = Path(temp_dir)

            # Create one session
            session_dir = logs_dir / "test_session"
            session_dir.mkdir()

            events_file = session_dir / "events.jsonl"
            events = [
                {"ts": "2025-09-01T10:00:00Z", "session": "test_session", "event": "run_start"},
                {"ts": "2025-09-01T10:05:00Z", "session": "test_session", "event": "run_end"},
            ]

            with open(events_file, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            with patch("builtins.print") as mock_print:
                list_sessions(["--logs-dir", temp_dir, "--json"])

                # Should have printed JSON
                assert mock_print.called
                printed_output = mock_print.call_args[0][0]
                parsed_json = json.loads(printed_output)

                assert "sessions" in parsed_json
                assert len(parsed_json["sessions"]) == 1
                assert parsed_json["sessions"][0]["session_id"] == "test_session"

    def test_list_sessions_nonexistent_directory(self):
        """Test listing sessions when logs directory doesn't exist."""
        nonexistent_dir = "/tmp/nonexistent_logs_dir_12345"

        with patch("builtins.print") as mock_print:
            list_sessions(["--logs-dir", nonexistent_dir, "--json"])

            # Should print error in JSON format
            assert mock_print.called
            printed_output = mock_print.call_args[0][0]
            parsed_json = json.loads(printed_output)

            assert "error" in parsed_json
            assert "Logs directory not found" in parsed_json["error"]


class TestShowSession:
    """Test show_session command."""

    def test_show_session_basic(self):
        """Test showing session details."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_dir = Path(temp_dir)
            session_dir = logs_dir / "test_session"
            session_dir.mkdir()

            # Create session files
            events_file = session_dir / "events.jsonl"
            events = [
                {"ts": "2025-09-01T10:00:00Z", "session": "test_session", "event": "run_start"},
                {"ts": "2025-09-01T10:05:00Z", "session": "test_session", "event": "cache_hit"},
                {"ts": "2025-09-01T10:10:00Z", "session": "test_session", "event": "run_end"},
            ]

            with open(events_file, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            (session_dir / "osiris.log").write_text("log content")

            with patch("rich.console.Console.print") as mock_print:
                show_session(["--session", "test_session", "--logs-dir", temp_dir])

                # Should display session summary
                assert mock_print.called

    def test_show_session_events(self):
        """Test showing session events."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_dir = Path(temp_dir)
            session_dir = logs_dir / "test_session"
            session_dir.mkdir()

            events_file = session_dir / "events.jsonl"
            events = [
                {"ts": "2025-09-01T10:00:00Z", "session": "test_session", "event": "run_start"},
                {
                    "ts": "2025-09-01T10:05:00Z",
                    "session": "test_session",
                    "event": "cache_hit",
                    "key": "abc123",
                },
            ]

            with open(events_file, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            with patch("rich.console.Console.print") as mock_print:
                show_session(["--session", "test_session", "--events", "--logs-dir", temp_dir])

                # Should display events table
                assert mock_print.called

    def test_show_session_metrics(self):
        """Test showing session metrics."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_dir = Path(temp_dir)
            session_dir = logs_dir / "test_session"
            session_dir.mkdir()

            # Create events.jsonl (required for session info)
            events_file = session_dir / "events.jsonl"
            events = [{"ts": "2025-09-01T10:00:00Z", "session": "test_session", "event": "run_start"}]

            with open(events_file, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            # Create metrics.jsonl
            metrics_file = session_dir / "metrics.jsonl"
            metrics = [
                {
                    "ts": "2025-09-01T10:05:00Z",
                    "session": "test_session",
                    "metric": "discovery_time",
                    "value": 1500,
                    "table": "users",
                }
            ]

            with open(metrics_file, "w") as f:
                for metric in metrics:
                    f.write(json.dumps(metric) + "\n")

            with patch("rich.console.Console.print") as mock_print:
                show_session(["--session", "test_session", "--metrics", "--logs-dir", temp_dir])

                # Should display metrics table
                assert mock_print.called

    def test_show_session_nonexistent(self):
        """Test showing nonexistent session."""
        with tempfile.TemporaryDirectory() as temp_dir, patch("rich.console.Console.print") as mock_print:
            show_session(["--session", "nonexistent", "--logs-dir", temp_dir])

            # Should print error message
            assert mock_print.called

    def test_show_session_json_output(self):
        """Test showing session with JSON output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_dir = Path(temp_dir)
            session_dir = logs_dir / "test_session"
            session_dir.mkdir()

            events_file = session_dir / "events.jsonl"
            events = [
                {"ts": "2025-09-01T10:00:00Z", "session": "test_session", "event": "run_start"},
                {"ts": "2025-09-01T10:05:00Z", "session": "test_session", "event": "run_end"},
            ]

            with open(events_file, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            with patch("builtins.print") as mock_print:
                show_session(["--session", "test_session", "--json", "--logs-dir", temp_dir])

                # Should print session info as JSON
                assert mock_print.called
                printed_output = mock_print.call_args[0][0]
                parsed_json = json.loads(printed_output)

                assert parsed_json["session_id"] == "test_session"


class TestBundleSession:
    """Test bundle_session command."""

    def test_bundle_session_basic(self):
        """Test bundling a session into a zip file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_dir = Path(temp_dir) / "logs"
            logs_dir.mkdir()
            session_dir = logs_dir / "test_session"
            session_dir.mkdir()

            # Create session files
            events_file = session_dir / "events.jsonl"
            events = [{"ts": "2025-09-01T10:00:00Z", "session": "test_session", "event": "run_start"}]

            with open(events_file, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            (session_dir / "osiris.log").write_text("log content")
            (session_dir / "test.txt").write_text("test content")

            # Create subdirectory with file
            artifacts_dir = session_dir / "artifacts"
            artifacts_dir.mkdir()
            (artifacts_dir / "artifact.json").write_text('{"key": "value"}')

            output_file = Path(temp_dir) / "test_bundle.zip"

            with patch("rich.console.Console.print") as mock_print:
                bundle_session(
                    [
                        "--session",
                        "test_session",
                        "--logs-dir",
                        str(logs_dir),
                        "-o",
                        str(output_file),
                    ]
                )

                # Should have created the bundle
                assert output_file.exists()

                # Verify bundle contents
                with zipfile.ZipFile(output_file, "r") as zf:
                    files = zf.namelist()
                    assert "events.jsonl" in files
                    assert "osiris.log" in files
                    assert "test.txt" in files
                    assert "artifacts/artifact.json" in files

                # Should have printed success message
                assert mock_print.called

    def test_bundle_session_default_output(self):
        """Test bundling session with default output filename."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_dir = Path(temp_dir)
            session_dir = logs_dir / "test_session"
            session_dir.mkdir()

            events_file = session_dir / "events.jsonl"
            with open(events_file, "w") as f:
                f.write(
                    json.dumps(
                        {
                            "ts": "2025-09-01T10:00:00Z",
                            "session": "test_session",
                            "event": "run_start",
                        }
                    )
                    + "\n"
                )

            # Change to temp directory so default output file is created there
            original_cwd = Path.cwd()
            try:
                import os

                os.chdir(temp_dir)

                with patch("rich.console.Console.print"):
                    bundle_session(["--session", "test_session", "--logs-dir", temp_dir])

                    # Should create test_session.zip in current directory
                    expected_file = Path("test_session.zip")
                    assert expected_file.exists()

            finally:
                os.chdir(original_cwd)

    def test_bundle_session_nonexistent(self):
        """Test bundling nonexistent session."""
        with tempfile.TemporaryDirectory() as temp_dir, patch("rich.console.Console.print") as mock_print:
            bundle_session(["--session", "nonexistent", "--logs-dir", temp_dir])

            # Should print error message
            assert mock_print.called

    def test_bundle_session_json_output(self):
        """Test bundling session with JSON output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_dir = Path(temp_dir)
            session_dir = logs_dir / "test_session"
            session_dir.mkdir()

            events_file = session_dir / "events.jsonl"
            with open(events_file, "w") as f:
                f.write(
                    json.dumps(
                        {
                            "ts": "2025-09-01T10:00:00Z",
                            "session": "test_session",
                            "event": "run_start",
                        }
                    )
                    + "\n"
                )

            output_file = Path(temp_dir) / "bundle.zip"

            with patch("builtins.print") as mock_print:
                bundle_session(
                    [
                        "--session",
                        "test_session",
                        "--logs-dir",
                        temp_dir,
                        "-o",
                        str(output_file),
                        "--json",
                    ]
                )

                # Should print JSON response
                assert mock_print.called
                printed_output = mock_print.call_args[0][0]
                parsed_json = json.loads(printed_output)

                assert parsed_json["status"] == "success"
                assert parsed_json["session_id"] == "test_session"
                assert "bundle_path" in parsed_json
                assert "size_bytes" in parsed_json


class TestGcSessions:
    """Test gc_sessions command."""

    def test_gc_sessions_by_age(self):
        """Test garbage collecting sessions by age."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_dir = Path(temp_dir)

            # Create old and new session directories
            old_time = time.time() - (8 * 24 * 3600)  # 8 days ago
            new_time = time.time() - (1 * 24 * 3600)  # 1 day ago

            for age, timestamp in [("old", old_time), ("new", new_time)]:
                session_dir = logs_dir / f"{age}_session"
                session_dir.mkdir()

                # Create some files
                (session_dir / "events.jsonl").write_text('{"event": "test"}\n')
                (session_dir / "osiris.log").write_text("log content")

                # Set directory modification time AFTER creating files
                os.utime(session_dir, (timestamp, timestamp))

            with patch("rich.console.Console.print") as mock_print:
                gc_sessions(["--days", "7", "--logs-dir", temp_dir])

                # Old session should be deleted, new one should remain
                assert not (logs_dir / "old_session").exists()
                assert (logs_dir / "new_session").exists()

                # Should print success message
                assert mock_print.called

    def test_gc_sessions_dry_run(self):
        """Test garbage collection dry run."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_dir = Path(temp_dir)

            # Create old session
            old_time = time.time() - (8 * 24 * 3600)  # 8 days ago
            session_dir = logs_dir / "old_session"
            session_dir.mkdir()

            os.utime(session_dir, (old_time, old_time))
            (session_dir / "events.jsonl").write_text('{"event": "test"}\n')

            with patch("rich.console.Console.print") as mock_print:
                gc_sessions(["--days", "7", "--dry-run", "--logs-dir", temp_dir])

                # Session should still exist (dry run)
                assert session_dir.exists()

                # Should print what would be deleted
                assert mock_print.called

    def test_gc_sessions_by_size(self):
        """Test garbage collection by total size limit."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_dir = Path(temp_dir)

            # Create sessions with different sizes
            for i in range(3):
                session_dir = logs_dir / f"session_{i}"
                session_dir.mkdir()

                # Create file of specific size (1KB each)
                (session_dir / "large_file.txt").write_text("x" * 1024)
                (session_dir / "events.jsonl").write_text('{"event": "test"}\n')

                # Set different modification times (oldest first will be deleted first)
                old_time = time.time() - ((3 - i) * 3600)  # session_0 is oldest
                os.utime(session_dir, (old_time, old_time))

            # Set size limit to ~2KB (should keep only 2 newest sessions)
            with patch("rich.console.Console.print"):
                gc_sessions(["--max-gb", "0.000002", "--logs-dir", temp_dir])  # ~2KB

                # Oldest session should be deleted
                assert not (logs_dir / "session_0").exists()
                assert (logs_dir / "session_1").exists()
                assert (logs_dir / "session_2").exists()

    def test_gc_sessions_json_output(self):
        """Test garbage collection with JSON output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_dir = Path(temp_dir)

            # Create old session
            old_time = time.time() - (8 * 24 * 3600)
            session_dir = logs_dir / "old_session"
            session_dir.mkdir()

            (session_dir / "events.jsonl").write_text('{"event": "test"}\n')
            os.utime(session_dir, (old_time, old_time))

            with patch("builtins.print") as mock_print:
                gc_sessions(["--days", "7", "--json", "--logs-dir", temp_dir])

                # Should print JSON response
                assert mock_print.called
                printed_output = mock_print.call_args[0][0]
                parsed_json = json.loads(printed_output)

                assert "deleted_count" in parsed_json
                assert "freed_bytes" in parsed_json
                assert parsed_json["deleted_count"] == 1

    def test_gc_sessions_no_cleanup_needed(self):
        """Test garbage collection when no cleanup is needed."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_dir = Path(temp_dir)

            # Create recent session
            session_dir = logs_dir / "recent_session"
            session_dir.mkdir()
            (session_dir / "events.jsonl").write_text('{"event": "test"}\n')

            with patch("rich.console.Console.print") as mock_print:
                gc_sessions(["--days", "7", "--logs-dir", temp_dir])

                # Session should still exist
                assert session_dir.exists()

                # Should indicate no cleanup needed
                assert mock_print.called


if __name__ == "__main__":
    pytest.main([__file__])
