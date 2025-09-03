"""Tests for session-aware component validation CLI."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from osiris.cli.components_cmd import validate_component


class TestComponentValidationLogging:
    """Test suite for session-aware component validation."""

    @pytest.fixture
    def temp_logs_dir(self):
        """Create a temporary logs directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def temp_components_dir(self):
        """Create temporary components with test specs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            components_dir = Path(tmpdir) / "components"
            components_dir.mkdir()

            # Create schema
            schema = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["name", "version", "modes"],
                "properties": {
                    "name": {"type": "string"},
                    "version": {"type": "string"},
                    "modes": {"type": "array", "items": {"type": "string"}},
                    "configSchema": {"type": "object"},
                    "secrets": {"type": "array", "items": {"type": "string"}},
                },
            }
            with open(components_dir / "spec.schema.json", "w") as f:
                json.dump(schema, f)

            # Create valid component
            valid_dir = components_dir / "test.valid"
            valid_dir.mkdir()
            valid_spec = {
                "name": "test.valid",
                "version": "1.0.0",
                "modes": ["extract"],
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "configSchema": {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "properties": {"host": {"type": "string"}},
                },
                "secrets": ["/password"],
            }
            with open(valid_dir / "spec.yaml", "w") as f:
                yaml.dump(valid_spec, f)

            # Create invalid component
            invalid_dir = components_dir / "test.invalid"
            invalid_dir.mkdir()
            invalid_spec = {
                "name": "test.invalid",
                # Missing required fields
            }
            with open(invalid_dir / "spec.yaml", "w") as f:
                yaml.dump(invalid_spec, f)

            yield components_dir

    def test_session_creation_with_custom_id(self, temp_logs_dir, temp_components_dir):
        """Test that validation creates a session with custom ID."""
        session_id = "test_validation_123"

        # Patch the registry root to use our temp components
        with patch("osiris.components.registry.Path") as mock_path:
            mock_path.return_value = temp_components_dir

            # Run validation
            validate_component(
                "test.valid",
                level="basic",
                session_id=session_id,
                logs_dir=str(temp_logs_dir),
                events=["*"],
            )

        # Assert session folder was created
        session_dir = temp_logs_dir / session_id
        assert session_dir.exists()
        assert (session_dir / "events.jsonl").exists()
        assert (session_dir / "metrics.jsonl").exists()

    def test_validation_events_logged(self, temp_logs_dir, temp_components_dir):
        """Test that validation events are properly logged."""
        session_id = "test_events_456"

        # Patch the registry root to use our temp components
        with patch("osiris.components.registry.Path") as mock_path:
            mock_path.return_value = temp_components_dir

            # Run validation
            validate_component(
                "test.valid",
                level="enhanced",
                session_id=session_id,
                logs_dir=str(temp_logs_dir),
                events=["component_validation_*"],
            )

        # Read events from JSONL
        events_file = temp_logs_dir / session_id / "events.jsonl"
        assert events_file.exists()

        events = []
        with open(events_file) as f:
            for line in f:
                events.append(json.loads(line))

        # Filter for validation events
        validation_events = [e for e in events if e["event"].startswith("component_validation_")]

        # Should have start and complete events
        assert len(validation_events) >= 2

        # Check start event
        start_events = [e for e in validation_events if e["event"] == "component_validation_start"]
        assert len(start_events) == 1
        start_event = start_events[0]
        assert start_event["data"]["component"] == "test.valid"
        assert start_event["data"]["level"] == "enhanced"
        assert "schema_version" in start_event["data"]
        assert start_event["data"]["command"] == "components.validate"

        # Check complete event
        complete_events = [
            e for e in validation_events if e["event"] == "component_validation_complete"
        ]
        assert len(complete_events) == 1
        complete_event = complete_events[0]
        assert complete_event["data"]["component"] == "test.valid"
        assert complete_event["data"]["level"] == "enhanced"
        assert complete_event["data"]["status"] == "ok"
        assert complete_event["data"]["errors"] == 0
        assert "duration_ms" in complete_event["data"]
        assert complete_event["data"]["command"] == "components.validate"

    def test_failed_validation_events(self, temp_logs_dir, temp_components_dir):
        """Test events for failed validation."""
        session_id = "test_failed_789"

        # Patch the registry root to use our temp components
        with patch("osiris.components.registry.Path") as mock_path:
            mock_path.return_value = temp_components_dir

            # Run validation on invalid component
            validate_component(
                "test.invalid",
                level="basic",
                session_id=session_id,
                logs_dir=str(temp_logs_dir),
            )

        # Read events
        events_file = temp_logs_dir / session_id / "events.jsonl"
        events = []
        with open(events_file) as f:
            for line in f:
                event = json.loads(line)
                if event["event"] == "component_validation_complete":
                    events.append(event)

        assert len(events) == 1
        assert events[0]["data"]["status"] == "failed"
        assert events[0]["data"]["errors"] > 0

    def test_nonexistent_component_logging(self, temp_logs_dir, temp_components_dir):
        """Test that non-existent components still create session and log events."""
        session_id = "test_nonexistent_999"

        # Patch the registry root to use our temp components
        with patch("osiris.components.registry.Path") as mock_path:
            mock_path.return_value = temp_components_dir

            # Run validation on non-existent component
            validate_component(
                "does.not.exist",
                level="basic",
                session_id=session_id,
                logs_dir=str(temp_logs_dir),
            )

        # Session should still be created
        session_dir = temp_logs_dir / session_id
        assert session_dir.exists()

        # Check events
        events_file = session_dir / "events.jsonl"
        events = []
        with open(events_file) as f:
            for line in f:
                event = json.loads(line)
                if "component_validation" in event["event"]:
                    events.append(event)

        # Should have both start and complete events
        assert any(e["event"] == "component_validation_start" for e in events)
        assert any(
            e["event"] == "component_validation_complete" and e["data"]["status"] == "failed"
            for e in events
        )

    def test_secrets_masking_in_logs(self, temp_logs_dir, temp_components_dir):
        """Test that sensitive paths are masked in logs."""
        session_id = "test_secrets_111"

        # Create a component with sensitive data in spec
        secret_dir = temp_components_dir / "test.secret"
        secret_dir.mkdir()
        secret_spec = {
            "name": "test.secret",
            "version": "1.0.0",
            "modes": ["extract"],
            "secrets": ["/password", "/api_key"],
            "examples": [
                {
                    "config": {
                        "password": "secret123",  # pragma: allowlist secret
                        "api_key": "sk-abc123",  # pragma: allowlist secret
                    }
                }
            ],
        }
        with open(secret_dir / "spec.yaml", "w") as f:
            yaml.dump(secret_spec, f)

        # Patch the registry root to use our temp components
        with patch("osiris.components.registry.Path") as mock_path:
            mock_path.return_value = temp_components_dir

            # Run validation
            validate_component(
                "test.secret",
                level="enhanced",
                session_id=session_id,
                logs_dir=str(temp_logs_dir),
                log_level="DEBUG",  # Enable debug to get more logs
            )

        # Check that logs don't contain actual secrets
        for log_file in ["osiris.log", "debug.log"]:
            log_path = temp_logs_dir / session_id / log_file
            if log_path.exists():
                content = log_path.read_text()
                assert "secret123" not in content
                assert "sk-abc123" not in content

    def test_precedence_cli_overrides_yaml(self, temp_logs_dir, temp_components_dir):
        """Test that CLI log level overrides YAML config."""
        session_id = "test_precedence_222"

        # Create a temporary YAML config with different settings
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(
                {
                    "logging": {
                        "level": "ERROR",  # YAML says ERROR
                        "logs_dir": "/tmp/yaml_logs",
                        "events": ["yaml_event"],
                    }
                },
                f,
            )
            config_file = f.name

        try:
            # Patch load_config to use our temp config
            with patch("osiris.cli.main.load_config") as mock_load:
                with open(config_file) as f:
                    mock_load.return_value = yaml.safe_load(f)

                # Also patch the registry root
                with patch("osiris.components.registry.Path") as mock_path:
                    mock_path.return_value = temp_components_dir

                    # Run with CLI override
                    validate_component(
                        "test.valid",
                        level="basic",
                        session_id=session_id,
                        logs_dir=str(temp_logs_dir),  # CLI override
                        log_level="DEBUG",  # CLI says DEBUG (should win)
                        events=["cli_event"],  # CLI override
                    )

            # Session should be in CLI-specified directory, not YAML directory
            assert (temp_logs_dir / session_id).exists()
            assert not Path("/tmp/yaml_logs" / session_id).exists()

            # Check that DEBUG level was used (by looking for debug.log)
            assert (temp_logs_dir / session_id / "debug.log").exists()
        finally:
            os.unlink(config_file)

    def test_json_output_format(self, temp_logs_dir, temp_components_dir, capsys):
        """Test JSON output format for validation."""
        session_id = "test_json_333"

        # Patch the registry root to use our temp components
        with patch("osiris.components.registry.Path") as mock_path:
            mock_path.return_value = temp_components_dir

            # Run validation with JSON output
            validate_component(
                "test.valid",
                level="basic",
                session_id=session_id,
                logs_dir=str(temp_logs_dir),
                json_output=True,
            )

        # Capture JSON output
        captured = capsys.readouterr()
        result = json.loads(captured.out)

        # Check JSON structure
        assert result["component"] == "test.valid"
        assert result["level"] == "basic"
        assert result["is_valid"] is True
        assert result["errors"] == []
        assert result["session_id"] == session_id
        assert "duration_ms" in result
        assert result["version"] == "1.0.0"
        assert result["modes"] == ["extract"]

    def test_event_filtering(self, temp_logs_dir, temp_components_dir):
        """Test that event filtering works correctly."""
        session_id = "test_filter_444"

        # Patch the registry root to use our temp components
        with patch("osiris.components.registry.Path") as mock_path:
            mock_path.return_value = temp_components_dir

            # Run with specific event filter
            validate_component(
                "test.valid",
                level="basic",
                session_id=session_id,
                logs_dir=str(temp_logs_dir),
                events=["component_validation_complete"],  # Only log complete events
            )

        # Read events
        events_file = temp_logs_dir / session_id / "events.jsonl"
        events = []
        with open(events_file) as f:
            for line in f:
                events.append(json.loads(line))

        # Should only have complete event (and maybe run_start/run_end)
        validation_events = [e for e in events if "component_validation" in e["event"]]
        assert len(validation_events) == 1
        assert validation_events[0]["event"] == "component_validation_complete"
