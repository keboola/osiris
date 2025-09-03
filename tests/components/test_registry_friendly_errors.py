"""Tests for friendly error handling in registry and CLI."""

import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from osiris.cli.components_cmd import validate_component
from osiris.components.error_mapper import FriendlyError


class TestRegistryFriendlyErrors:
    """Test suite for friendly error integration in registry and CLI."""

    @pytest.fixture
    def temp_logs_dir(self):
        """Create a temporary logs directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_registry_with_friendly_errors(self):
        """Create a mock registry that returns friendly errors."""
        mock_registry = MagicMock()
        mock_registry.get_component.return_value = {
            "name": "test.component",
            "version": "1.0.0",
        }

        # Return structured errors with friendly info
        friendly_error = FriendlyError(
            category="config_error",
            field_label="Database Host",
            problem="Required field 'host' is missing",
            fix_hint="Add 'host: your-server.com' to your configuration",
            example="host: localhost",
            technical_details={"path": "/configSchema/properties/host"},
        )

        mock_registry.validate_spec.return_value = (
            False,
            [
                {
                    "friendly": friendly_error,
                    "technical": "Schema validation: 'host' is required at configSchema -> properties",
                }
            ],
        )
        return mock_registry

    def test_validation_with_friendly_errors_display(
        self, mock_registry_with_friendly_errors, temp_logs_dir
    ):
        """Test that friendly errors are displayed correctly in CLI output."""

        with patch("osiris.cli.components_cmd.get_registry") as mock_get_registry:
            mock_get_registry.return_value = mock_registry_with_friendly_errors
            with patch("osiris.cli.components_cmd.rprint") as mock_print:
                validate_component(
                    "test.component",
                    level="enhanced",
                    logs_dir=str(temp_logs_dir),
                    json_output=False,
                    verbose=False,
                )

        # Check that friendly error parts were printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        all_output = " ".join(print_calls)

        # Should contain the friendly error components
        assert "Missing Required Configuration" in all_output
        assert "Database Host" in all_output
        assert "Add 'host: your-server.com'" in all_output
        assert "host: localhost" in all_output

    def test_validation_with_verbose_shows_technical(
        self, mock_registry_with_friendly_errors, temp_logs_dir
    ):
        """Test that verbose mode shows technical details."""

        with patch("osiris.cli.components_cmd.get_registry") as mock_get_registry:
            mock_get_registry.return_value = mock_registry_with_friendly_errors
            with patch("osiris.cli.components_cmd.rprint") as mock_print:
                validate_component(
                    "test.component",
                    level="enhanced",
                    logs_dir=str(temp_logs_dir),
                    json_output=False,
                    verbose=True,  # Enable verbose
                )

        print_calls = [str(call) for call in mock_print.call_args_list]
        all_output = " ".join(print_calls)

        # Should show technical details
        assert "Technical Details" in all_output or "/configSchema/properties/host" in all_output

    def test_validation_json_output_includes_friendly(
        self, mock_registry_with_friendly_errors, temp_logs_dir
    ):
        """Test that JSON output includes friendly error info."""
        captured_output = StringIO()

        with patch("osiris.cli.components_cmd.get_registry") as mock_get_registry:
            mock_get_registry.return_value = mock_registry_with_friendly_errors
            with patch("sys.stdout", captured_output):
                validate_component(
                    "test.component",
                    level="enhanced",
                    logs_dir=str(temp_logs_dir),
                    json_output=True,
                )

        output = captured_output.getvalue()
        data = json.loads(output)

        assert not data["is_valid"]
        assert len(data["errors"]) == 1

        error = data["errors"][0]
        assert "friendly" in error
        assert error["friendly"]["category"] == "config_error"
        assert error["friendly"]["field"] == "Database Host"
        assert "technical" in error

    def test_session_logs_contain_friendly_errors(
        self, mock_registry_with_friendly_errors, temp_logs_dir
    ):
        """Test that session logs include friendly error details."""
        session_id = "test_session_123"

        with patch("osiris.cli.components_cmd.get_registry") as mock_get_registry:
            mock_get_registry.return_value = mock_registry_with_friendly_errors
            with patch("osiris.cli.components_cmd.rprint"):
                validate_component(
                    "test.component",
                    level="enhanced",
                    session_id=session_id,
                    logs_dir=str(temp_logs_dir),
                    json_output=False,
                )

        # Check that session events were logged
        session_dir = temp_logs_dir / session_id
        assert session_dir.exists()

        events_file = session_dir / "events.jsonl"
        assert events_file.exists()

        # Read events and check for friendly errors
        events = []
        with open(events_file) as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))

        # Find the validation complete event
        complete_events = [e for e in events if e.get("event") == "component_validation_complete"]
        assert len(complete_events) == 1

        complete_event = complete_events[0]
        assert complete_event["status"] == "failed"
        assert "friendly_errors" in complete_event
        assert len(complete_event["friendly_errors"]) == 1

        friendly = complete_event["friendly_errors"][0]
        assert friendly["category"] == "config_error"
        assert friendly["field"] == "Database Host"

    def test_multiple_friendly_errors(self, temp_logs_dir):
        """Test handling of multiple validation errors."""
        mock_registry = MagicMock()
        mock_registry.get_component.return_value = {"name": "test.multi"}

        errors = [
            {
                "friendly": FriendlyError(
                    category="config_error",
                    field_label="Database Host",
                    problem="Missing required field",
                    fix_hint="Add host configuration",
                    example="host: localhost",
                ),
                "technical": "Missing host",
            },
            {
                "friendly": FriendlyError(
                    category="type_error",
                    field_label="Port",
                    problem="Expected integer but got string",
                    fix_hint="Use number without quotes",
                    example="port: 3306",
                ),
                "technical": "Type error for port",
            },
        ]

        mock_registry.validate_spec.return_value = (False, errors)

        with patch("osiris.cli.components_cmd.get_registry") as mock_get_registry:
            mock_get_registry.return_value = mock_registry
            with patch("osiris.cli.components_cmd.rprint") as mock_print:
                validate_component(
                    "test.multi", level="enhanced", logs_dir=str(temp_logs_dir), json_output=False
                )

        print_calls = [str(call) for call in mock_print.call_args_list]
        all_output = " ".join(print_calls)

        # Both errors should be displayed
        assert "Database Host" in all_output
        assert "Port" in all_output
        assert "Missing Required Configuration" in all_output
        assert "Invalid Type" in all_output

    def test_backward_compatibility_with_string_errors(self, temp_logs_dir):
        """Test that old-style string errors still work."""
        mock_registry = MagicMock()
        mock_registry.get_component.return_value = {"name": "test.legacy"}
        mock_registry.validate_spec.return_value = (
            False,
            ["Simple string error 1", "Simple string error 2"],
        )

        with patch("osiris.cli.components_cmd.get_registry") as mock_get_registry:
            mock_get_registry.return_value = mock_registry
            with patch("osiris.cli.components_cmd.rprint") as mock_print:
                validate_component(
                    "test.legacy", level="basic", logs_dir=str(temp_logs_dir), json_output=False
                )

        print_calls = [str(call) for call in mock_print.call_args_list]
        all_output = " ".join(print_calls)

        # String errors should still be displayed
        assert "Simple string error 1" in all_output
        assert "Simple string error 2" in all_output

    def test_no_duplicate_events_with_friendly_errors(
        self, mock_registry_with_friendly_errors, temp_logs_dir
    ):
        """Test that friendly errors don't cause duplicate event emission."""
        session_id = "test_no_dup_123"

        with patch("osiris.cli.components_cmd.get_registry") as mock_get_registry:
            mock_get_registry.return_value = mock_registry_with_friendly_errors
            with patch("osiris.cli.components_cmd.rprint"):
                validate_component(
                    "test.component",
                    level="enhanced",
                    session_id=session_id,
                    logs_dir=str(temp_logs_dir),
                )

        # Check events
        events_file = temp_logs_dir / session_id / "events.jsonl"
        events = []
        with open(events_file) as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))

        # Should have exactly 4 events (no duplicates)
        assert len(events) == 4

        event_types = [e.get("event") for e in events]
        assert event_types == [
            "run_start",
            "component_validation_start",
            "component_validation_complete",
            "run_end",
        ]
