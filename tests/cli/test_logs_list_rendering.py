"""Tests for logs list rendering with session ID wrapping."""

import io
from unittest.mock import patch

from rich.console import Console

from osiris.cli.logs import _display_sessions_table


class TestLogsListRendering:
    """Test suite for logs list command rendering."""

    def test_session_id_wraps_by_default(self):
        """Test that long session IDs wrap to multiple lines by default."""
        # Create mock session with very long ID
        sessions = [
            {
                "session_id": "this_is_a_very_long_session_id_that_will_definitely_need_to_wrap_in_narrow_terminals",
                "start_time": "2025-01-03T12:34:56",
                "status": "completed",
                "duration_seconds": 5.2,
                "size_bytes": 1024,
                "event_count": 10,
                "path": "/path/to/session",
            }
        ]

        # Capture output using StringIO
        output = io.StringIO()
        test_console = Console(file=output, width=80, force_terminal=True)

        # Patch the module's console with our test console
        with patch("osiris.cli.logs.console", test_console):
            _display_sessions_table(sessions, no_wrap=False)

        # Get the output
        result = output.getvalue()

        # Verify no ellipsis truncation (Rich uses … character)
        assert "…" not in result  # No ellipsis means it's not truncated

        # Verify key parts of the session ID appear (wrapped across lines)
        assert "this_is_a_very_long" in result
        assert "definitely_need_to" in result or "_definitely_need_to_" in result
        assert "narrow_termi" in result or "terminals" in result

        # Verify wrapping occurred (session ID appears across multiple lines)
        lines = result.split("\n")
        session_id_lines = [line for line in lines if "this_is" in line or "definitely" in line or "termi" in line]
        assert len(session_id_lines) > 1, "Session ID should wrap to multiple lines"

    def test_session_id_single_line_with_no_wrap(self):
        """Test that session IDs stay on single line with --no-wrap flag."""
        # Create mock session with very long ID
        sessions = [
            {
                "session_id": "this_is_a_very_long_session_id_that_will_definitely_need_to_wrap_in_narrow_terminals",
                "start_time": "2025-01-03T12:34:56",
                "status": "completed",
                "duration_seconds": 5.2,
                "size_bytes": 1024,
                "event_count": 10,
                "path": "/path/to/session",
            }
        ]

        # Capture output using StringIO with narrow width
        output = io.StringIO()
        test_console = Console(file=output, width=80, force_terminal=True)

        # Patch the module's console with our test console
        with patch("osiris.cli.logs.console", test_console):
            _display_sessions_table(sessions, no_wrap=True)

        # Get the output
        result = output.getvalue()

        # With no-wrap and narrow terminal, should see truncation with ellipsis
        assert "…" in result or "..." in result  # Rich may use either style

        # Full ID should NOT appear since it's truncated
        assert "this_is_a_very_long_session_id_that_will_definitely_need_to_wrap_in_narrow_terminals" not in result

    def test_short_session_id_no_wrapping_needed(self):
        """Test that short session IDs don't wrap unnecessarily."""
        # Create mock session with short ID
        sessions = [
            {
                "session_id": "short_id",
                "start_time": "2025-01-03T12:34:56",
                "status": "completed",
                "duration_seconds": 5.2,
                "size_bytes": 1024,
                "event_count": 10,
                "path": "/path/to/session",
            }
        ]

        # Capture output using StringIO
        output = io.StringIO()
        test_console = Console(file=output, width=80, force_terminal=True)

        # Patch the module's console with our test console
        with patch("osiris.cli.logs.console", test_console):
            _display_sessions_table(sessions, no_wrap=False)

        # Get the output
        result = output.getvalue()

        # Verify the session ID appears
        assert "short_id" in result

        # Count how many lines contain the session ID
        lines = result.split("\n")
        session_id_lines = [line for line in lines if "short_id" in line]
        # Should only appear on one line since it's short
        assert len(session_id_lines) == 1, "Short session ID should not wrap"

    def test_empty_sessions_list(self):
        """Test handling of empty sessions list."""
        sessions = []

        # Capture output using StringIO
        output = io.StringIO()
        test_console = Console(file=output, force_terminal=True)

        # Patch the module's console with our test console
        with patch("osiris.cli.logs.console", test_console):
            _display_sessions_table(sessions, no_wrap=False)

        # Get the output
        result = output.getvalue()

        # Should show "No sessions found" message
        assert "No sessions found" in result

    def test_multiple_sessions_rendering(self):
        """Test rendering multiple sessions with mixed ID lengths."""
        sessions = [
            {
                "session_id": "very_long_session_id_that_needs_wrapping_for_sure",
                "start_time": "2025-01-03T12:34:56",
                "status": "completed",
                "duration_seconds": 5.2,
                "size_bytes": 1024,
                "event_count": 10,
                "path": "/path/to/session1",
            },
            {
                "session_id": "short",
                "start_time": "2025-01-03T12:35:00",
                "status": "failed",
                "duration_seconds": 1.5,
                "size_bytes": 512,
                "event_count": 5,
                "path": "/path/to/session2",
            },
        ]

        # Capture output using StringIO
        output = io.StringIO()
        test_console = Console(file=output, width=80, force_terminal=True)

        # Patch the module's console with our test console
        with patch("osiris.cli.logs.console", test_console):
            _display_sessions_table(sessions, no_wrap=False)

        # Get the output
        result = output.getvalue()

        # Both session IDs should appear (long one may be wrapped)
        assert "very_long_session_id" in result
        assert "wrapping_for_sure" in result or "_for_sure" in result
        assert "short" in result

        # Status indicators should be present
        assert "completed" in result
        assert "failed" in result
