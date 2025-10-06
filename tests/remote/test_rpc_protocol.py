"""Unit tests for JSON-RPC protocol."""

import json

from pydantic import ValidationError
import pytest

from osiris.remote.rpc_protocol import (
    CleanupCommand,
    CleanupResponse,
    CommandType,
    ErrorMessage,
    ErrorResponse,
    EventMessage,
    ExecStepCommand,
    ExecStepResponse,
    MessageType,
    MetricMessage,
    PingCommand,
    PingResponse,
    PrepareCommand,
    PrepareResponse,
    ResponseStatus,
    parse_command,
    parse_message,
)


class TestCommands:
    """Test command parsing and validation."""

    def test_prepare_command(self):
        """Test PrepareCommand parsing."""
        data = {
            "cmd": "prepare",
            "session_id": "test_123",
            "manifest": {"pipeline": {"name": "test"}},
            "log_level": "DEBUG",
        }

        cmd = parse_command(data)
        assert isinstance(cmd, PrepareCommand)
        assert cmd.session_id == "test_123"
        assert cmd.manifest["pipeline"]["name"] == "test"
        assert cmd.log_level == "DEBUG"

    def test_prepare_command_defaults(self):
        """Test PrepareCommand with defaults."""
        data = {"cmd": "prepare", "session_id": "test_123", "manifest": {}}

        cmd = parse_command(data)
        assert cmd.log_level == "INFO"  # Default

    def test_exec_step_command(self):
        """Test ExecStepCommand parsing."""
        data = {
            "cmd": "exec_step",
            "step_id": "step-1",
            "driver": "mysql.extractor",
            "config": {"query": "SELECT * FROM users"},
            "inputs": {"df": "mock_dataframe"},
        }

        cmd = parse_command(data)
        assert isinstance(cmd, ExecStepCommand)
        assert cmd.step_id == "step-1"
        assert cmd.driver == "mysql.extractor"
        assert cmd.config["query"] == "SELECT * FROM users"
        assert cmd.inputs["df"] == "mock_dataframe"

    def test_exec_step_command_no_inputs(self):
        """Test ExecStepCommand without inputs."""
        data = {"cmd": "exec_step", "step_id": "step-1", "driver": "mysql.extractor", "config": {}}

        cmd = parse_command(data)
        assert cmd.inputs is None

    def test_cleanup_command(self):
        """Test CleanupCommand parsing."""
        data = {"cmd": "cleanup"}

        cmd = parse_command(data)
        assert isinstance(cmd, CleanupCommand)
        assert cmd.cmd == CommandType.CLEANUP

    def test_ping_command(self):
        """Test PingCommand parsing."""
        data = {"cmd": "ping", "data": "echo_test"}

        cmd = parse_command(data)
        assert isinstance(cmd, PingCommand)
        assert cmd.data == "echo_test"

    def test_unknown_command(self):
        """Test parsing unknown command."""
        data = {"cmd": "unknown"}

        with pytest.raises(ValueError, match="Unknown command type"):
            parse_command(data)

    def test_invalid_command_data(self):
        """Test parsing invalid command data."""
        data = {
            "cmd": "prepare",
            # Missing required fields
        }

        with pytest.raises(ValidationError):
            parse_command(data)


class TestResponses:
    """Test response parsing and validation."""

    def test_prepare_response(self):
        """Test PrepareResponse parsing."""
        data = {
            "status": "ready",
            "session_id": "test_123",
            "session_dir": "/session/test_123",
            "drivers_loaded": ["mysql.extractor", "csv.writer"],
        }

        resp = parse_message(data)
        assert isinstance(resp, PrepareResponse)
        assert resp.status == ResponseStatus.READY
        assert resp.session_id == "test_123"
        assert len(resp.drivers_loaded) == 2

    def test_exec_step_response(self):
        """Test ExecStepResponse parsing."""
        data = {
            "status": "complete",
            "step_id": "step-1",
            "rows_processed": 42,
            "outputs": {"df": "dataframe"},
            "duration_ms": 123.45,
        }

        resp = parse_message(data)
        assert isinstance(resp, ExecStepResponse)
        assert resp.status == ResponseStatus.COMPLETE
        assert resp.rows_processed == 42
        assert resp.duration_ms == 123.45

    def test_cleanup_response(self):
        """Test CleanupResponse parsing."""
        data = {
            "status": "cleaned",
            "session_id": "test_123",
            "steps_executed": 3,
            "total_rows": 100,
        }

        resp = parse_message(data)
        assert isinstance(resp, CleanupResponse)
        assert resp.status == ResponseStatus.CLEANED
        assert resp.steps_executed == 3
        assert resp.total_rows == 100

    def test_ping_response(self):
        """Test PingResponse parsing."""
        data = {"status": "pong", "timestamp": 1234567890.123, "echo": "test_data"}

        resp = parse_message(data)
        assert isinstance(resp, PingResponse)
        assert resp.status == ResponseStatus.PONG
        assert resp.timestamp == 1234567890.123
        assert resp.echo == "test_data"

    def test_error_response(self):
        """Test ErrorResponse parsing."""
        data = {"status": "error", "error": "Something went wrong", "traceback": "Stack trace here"}

        resp = parse_message(data)
        assert isinstance(resp, ErrorResponse)
        assert resp.status == ResponseStatus.ERROR
        assert resp.error == "Something went wrong"
        assert resp.traceback == "Stack trace here"


class TestStreamingMessages:
    """Test streaming message parsing."""

    def test_event_message(self):
        """Test EventMessage parsing."""
        data = {
            "type": "event",
            "name": "step_start",
            "timestamp": 1234567890.123,
            "data": {"step_id": "step-1", "driver": "mysql"},
        }

        msg = parse_message(data)
        assert isinstance(msg, EventMessage)
        assert msg.type == MessageType.EVENT
        assert msg.name == "step_start"
        assert msg.data["step_id"] == "step-1"

    def test_metric_message(self):
        """Test MetricMessage parsing."""
        data = {
            "type": "metric",
            "name": "rows_processed",
            "value": 42,
            "timestamp": 1234567890.123,
            "tags": {"step": "step-1", "table": "users"},
        }

        msg = parse_message(data)
        assert isinstance(msg, MetricMessage)
        assert msg.type == MessageType.METRIC
        assert msg.name == "rows_processed"
        assert msg.value == 42
        assert msg.tags["step"] == "step-1"

    def test_metric_message_no_tags(self):
        """Test MetricMessage without tags."""
        data = {"type": "metric", "name": "total_rows", "value": 100, "timestamp": 1234567890.123}

        msg = parse_message(data)
        assert msg.tags is None

    def test_error_message(self):
        """Test ErrorMessage parsing."""
        data = {
            "type": "error",
            "error": "Failed to execute step",
            "timestamp": 1234567890.123,
            "context": {"step_id": "step-1", "attempt": 2},
        }

        msg = parse_message(data)
        assert isinstance(msg, ErrorMessage)
        assert msg.type == MessageType.ERROR
        assert msg.error == "Failed to execute step"
        assert msg.context["attempt"] == 2


class TestSerialization:
    """Test message serialization."""

    def test_command_serialization(self):
        """Test command serialization to JSON."""
        cmd = PrepareCommand(session_id="test_123", manifest={"pipeline": {"name": "test"}}, log_level="DEBUG")

        # Serialize to JSON
        json_str = json.dumps(cmd.model_dump())

        # Parse back
        data = json.loads(json_str)
        parsed = parse_command(data)

        assert parsed.session_id == cmd.session_id
        assert parsed.manifest == cmd.manifest
        assert parsed.log_level == cmd.log_level

    def test_response_serialization(self):
        """Test response serialization to JSON."""
        resp = ExecStepResponse(step_id="step-1", rows_processed=42, outputs={"df": "dataframe"}, duration_ms=123.45)

        # Serialize to JSON
        json_str = json.dumps(resp.model_dump(exclude_none=True))

        # Parse back
        data = json.loads(json_str)
        parsed = parse_message(data)

        assert parsed.step_id == resp.step_id
        assert parsed.rows_processed == resp.rows_processed

    def test_event_serialization(self):
        """Test event message serialization."""
        event = EventMessage(name="step_complete", timestamp=1234567890.123, data={"step_id": "step-1", "rows": 42})

        # Serialize to JSON
        json_str = json.dumps(event.model_dump())

        # Parse back
        data = json.loads(json_str)
        parsed = parse_message(data)

        assert parsed.name == event.name
        assert parsed.timestamp == event.timestamp
        assert parsed.data == event.data


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_data(self):
        """Test parsing empty data."""
        with pytest.raises(ValueError):
            parse_command({})

    def test_none_command(self):
        """Test parsing None command."""
        with pytest.raises(AttributeError):
            parse_command(None)

    def test_malformed_json(self):
        """Test handling malformed JSON."""
        json_str = '{"cmd": "prepare", "session_id": '  # Incomplete JSON

        with pytest.raises(json.JSONDecodeError):
            data = json.loads(json_str)
            parse_command(data)

    def test_extra_fields_ignored(self):
        """Test that extra fields are ignored."""
        data = {"cmd": "ping", "data": "test", "extra_field": "should_be_ignored"}

        cmd = parse_command(data)
        assert isinstance(cmd, PingCommand)
        assert not hasattr(cmd, "extra_field")

    def test_missing_required_field(self):
        """Test missing required field."""
        data = {
            "cmd": "exec_step",
            "step_id": "step-1",
            # Missing "driver" and "config"
        }

        with pytest.raises(ValidationError):
            parse_command(data)

    def test_invalid_enum_value(self):
        """Test invalid enum value."""
        data = {"status": "invalid_status", "session_id": "test"}

        with pytest.raises(ValueError):
            parse_message(data)
