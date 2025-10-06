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

"""Tests for session-scoped logging and artifacts system."""

import json
import logging
import tempfile
import time
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

from osiris.core.session_logging import (
    SessionContext,
    clear_current_session,
    create_ephemeral_session,
    get_current_session,
    log_event,
    log_metric,
    set_current_session,
)


class TestSessionContext:
    """Test SessionContext class."""

    def test_session_context_initialization(self):
        """Test that SessionContext initializes correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            session = SessionContext(session_id="test_session_123", base_logs_dir=Path(temp_dir))

            assert session.session_id == "test_session_123"
            assert session.session_dir == Path(temp_dir) / "test_session_123"
            assert session.session_dir.exists()
            assert session.artifacts_dir.exists()

    def test_generated_session_id(self):
        """Test that session ID is generated when not provided."""
        with tempfile.TemporaryDirectory() as temp_dir:
            session = SessionContext(base_logs_dir=Path(temp_dir))

            # Should have timestamp format: YYYYMMDD_HHMMSS_uuid8
            assert len(session.session_id.split("_")) == 3
            assert len(session.session_id.split("_")[2]) == 8  # Short UUID

    def test_fallback_to_temp_directory(self):
        """Test fallback to temp directory when logs directory creation fails."""
        # Try to create session in a directory that doesn't exist and can't be created
        with patch("pathlib.Path.mkdir") as mock_mkdir:
            mock_mkdir.side_effect = PermissionError("Access denied")

            session = SessionContext(session_id="test_session", base_logs_dir=Path("/nonexistent/readonly"))

            # Should fallback to temp directory
            assert session._fallback_temp_dir is not None
            assert session.session_dir.exists()  # Should exist in temp location

    def test_context_manager(self):
        """Test SessionContext as context manager."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with SessionContext(base_logs_dir=Path(temp_dir)) as session:
                assert isinstance(session, SessionContext)
                assert session.session_dir.exists()

                # Log an event to verify it's working
                session.log_event("test_event", test_data="value")

            # After context exit, events.jsonl should contain the run_start and run_end events
            events_file = session.session_dir / "events.jsonl"
            assert events_file.exists()

            with open(events_file) as f:
                events = [json.loads(line) for line in f]

            # Should have run_start, test_event, and run_end
            assert len(events) >= 3
            assert events[0]["event"] == "run_start"
            assert events[-1]["event"] == "run_end"

    def test_session_logging_setup(self):
        """Test that session logging handlers are set up correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            session = SessionContext(base_logs_dir=Path(temp_dir))
            session.setup_logging(level=logging.INFO, enable_debug=True)

            # Test that log files are created
            logger = logging.getLogger("test")
            logger.info("Test info message")
            logger.debug("Test debug message")

            # Clean up handlers
            session.cleanup_logging()

            # Check that main log file exists and has content
            assert session.osiris_log.exists()
            assert session.debug_log.exists()

            # Verify log content
            with open(session.osiris_log) as f:
                content = f.read()
                assert "Test info message" in content
                assert session.session_id in content

    def test_log_event(self):
        """Test structured event logging."""
        with tempfile.TemporaryDirectory() as temp_dir:
            session = SessionContext(base_logs_dir=Path(temp_dir))

            session.log_event("cache_hit", cache_key="test_key", duration_ms=150, table="users")

            # Verify event was written to events.jsonl
            events_file = session.session_dir / "events.jsonl"
            assert events_file.exists()

            with open(events_file) as f:
                events = [json.loads(line) for line in f]

            # Find our test event (skip run_start)
            test_event = None
            for event in events:
                if event.get("event") == "cache_hit":
                    test_event = event
                    break

            assert test_event is not None
            assert test_event["event"] == "cache_hit"
            assert test_event["session"] == session.session_id
            assert test_event["cache_key"] == "test_key"
            assert test_event["duration_ms"] == 150
            assert test_event["table"] == "users"
            assert "ts" in test_event

    def test_log_metric(self):
        """Test metrics logging."""
        with tempfile.TemporaryDirectory() as temp_dir:
            session = SessionContext(base_logs_dir=Path(temp_dir))

            session.log_metric("discovery_time", 1234, table="products", row_count=5000)

            # Verify metric was written to metrics.jsonl
            metrics_file = session.session_dir / "metrics.jsonl"
            assert metrics_file.exists()

            with open(metrics_file) as f:
                metrics = [json.loads(line) for line in f]

            assert len(metrics) >= 1
            metric = metrics[0]
            assert metric["metric"] == "discovery_time"
            assert metric["value"] == 1234
            assert metric["session"] == session.session_id
            assert metric["table"] == "products"
            assert metric["row_count"] == 5000
            assert "ts" in metric

    def test_save_config(self):
        """Test configuration saving with secrets masking."""
        with tempfile.TemporaryDirectory() as temp_dir:
            session = SessionContext(base_logs_dir=Path(temp_dir))

            config = {
                "database": {
                    "host": "localhost",
                    "password": "secret123",
                    "user": "admin",
                },  # pragma: allowlist secret
                "api_key": "super_secret_key",  # pragma: allowlist secret
            }

            session.save_config(config)

            # Verify config was saved with secrets masked
            assert session.config_file.exists()

            with open(session.config_file) as f:
                saved_config = json.load(f)

            # Password should be masked
            assert saved_config["database"]["password"] == "***"
            assert saved_config["api_key"] == "***"
            # Non-sensitive data should remain
            assert saved_config["database"]["host"] == "localhost"
            assert saved_config["database"]["user"] == "admin"

    def test_save_manifest(self):
        """Test manifest saving with secrets masking."""
        with tempfile.TemporaryDirectory() as temp_dir:
            session = SessionContext(base_logs_dir=Path(temp_dir))

            manifest = {
                "source": {
                    "type": "mysql",
                    "connection": {
                        "host": "db.example.com",
                        "password": "db_secret",  # pragma: allowlist secret
                        "user": "app_user",
                    },
                },
                "destination": {"token": "auth_token_123"},
            }

            session.save_manifest(manifest)

            # Verify manifest was saved with secrets masked
            assert session.manifest_file.exists()

            with open(session.manifest_file) as f:
                saved_manifest = json.load(f)

            # Secrets should be masked
            assert saved_manifest["source"]["connection"]["password"] == "***"
            assert saved_manifest["destination"]["token"] == "***"
            # Non-sensitive data should remain
            assert saved_manifest["source"]["connection"]["host"] == "db.example.com"

    def test_save_artifact(self):
        """Test artifact saving."""
        with tempfile.TemporaryDirectory() as temp_dir:
            session = SessionContext(base_logs_dir=Path(temp_dir))

            # Test text artifact
            text_path = session.save_artifact("test.txt", "Hello World", "text")
            assert text_path is not None
            assert text_path.exists()
            assert text_path.read_text() == "Hello World"

            # Test JSON artifact with secrets masking
            json_data = {
                "name": "test",
                "password": "secret",
                "value": 42,
            }  # pragma: allowlist secret
            json_path = session.save_artifact("test.json", json_data, "json")
            assert json_path is not None
            assert json_path.exists()

            saved_data = json.loads(json_path.read_text())
            assert saved_data["password"] == "***"  # Should be masked
            assert saved_data["name"] == "test"
            assert saved_data["value"] == 42

            # Test binary artifact
            binary_data = b"binary content"
            binary_path = session.save_artifact("test.bin", binary_data, "binary")
            assert binary_path is not None
            assert binary_path.exists()
            assert binary_path.read_bytes() == binary_data

    def test_session_duration_tracking(self):
        """Test that session duration is tracked correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            start_time = time.time()

            with SessionContext(base_logs_dir=Path(temp_dir)) as session:
                time.sleep(0.1)  # Small delay to measure duration

            end_time = time.time()
            expected_duration = end_time - start_time

            # Check that run_end event has duration
            events_file = session.session_dir / "events.jsonl"
            with open(events_file) as f:
                events = [json.loads(line) for line in f]

            run_end_event = None
            for event in events:
                if event.get("event") == "run_end":
                    run_end_event = event
                    break

            assert run_end_event is not None
            assert "duration_seconds" in run_end_event
            assert abs(run_end_event["duration_seconds"] - expected_duration) < 0.5  # Within 0.5s

    def test_error_handling_in_session(self):
        """Test that errors in session are logged properly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                with SessionContext(base_logs_dir=Path(temp_dir)) as session:
                    raise ValueError("Test error")
            except ValueError:
                pass  # Expected

            # Check that run_error event was logged
            events_file = session.session_dir / "events.jsonl"
            with open(events_file) as f:
                events = [json.loads(line) for line in f]

            run_error_event = None
            for event in events:
                if event.get("event") == "run_error":
                    run_error_event = event
                    break

            assert run_error_event is not None
            assert run_error_event["error_type"] == "ValueError"
            assert run_error_event["error_message"] == "Test error"


class TestGlobalSessionFunctions:
    """Test global session functions."""

    def test_current_session_management(self):
        """Test getting and setting current session."""
        # Clear any existing session first
        clear_current_session()

        # Initially no current session
        assert get_current_session() is None

        with tempfile.TemporaryDirectory() as temp_dir:
            session = SessionContext(base_logs_dir=Path(temp_dir))
            set_current_session(session)

            # Should be able to get current session
            current = get_current_session()
            assert current is session

            # Global functions should work with current session
            log_event("test_event", data="test")
            log_metric("test_metric", 123, unit="ms")

            # Events should be logged to current session
            events_file = session.session_dir / "events.jsonl"
            metrics_file = session.session_dir / "metrics.jsonl"

            assert events_file.exists()
            assert metrics_file.exists()

        # Clean up global state
        clear_current_session()

    def test_log_event_without_session(self):
        """Test that log_event handles no current session gracefully."""
        set_current_session(None)

        # Should not raise an exception
        log_event("test_event", data="test")
        log_metric("test_metric", 123)

    def test_create_ephemeral_session(self):
        """Test creating ephemeral session for CLI commands."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("osiris.core.session_logging.Path", return_value=Path(temp_dir)):
                session = create_ephemeral_session("validate")

                assert "ephemeral_validate" in session.session_id
                assert session.session_dir.exists()


class TestSecretsMaskingInSession:
    """Test that secrets are properly masked in session logging."""

    def test_event_secrets_masking(self):
        """Test that sensitive data in events is masked."""
        with tempfile.TemporaryDirectory() as temp_dir:
            session = SessionContext(base_logs_dir=Path(temp_dir))

            session.log_event(
                "database_connection",
                host="db.example.com",
                password="secret123",  # pragma: allowlist secret
                api_key="key_abc",  # pragma: allowlist secret
                user="admin",
            )

            events_file = session.session_dir / "events.jsonl"
            with open(events_file) as f:
                events = [json.loads(line) for line in f]

            # Find our event
            test_event = None
            for event in events:
                if event.get("event") == "database_connection":
                    test_event = event
                    break

            assert test_event is not None
            assert test_event["password"] == "***"
            assert test_event["api_key"] == "***"
            assert test_event["host"] == "db.example.com"  # Not sensitive
            assert test_event["user"] == "admin"  # Not sensitive

    def test_metric_secrets_masking(self):
        """Test that sensitive data in metrics is masked."""
        with tempfile.TemporaryDirectory() as temp_dir:
            session = SessionContext(base_logs_dir=Path(temp_dir))

            session.log_metric(
                "connection_time",
                150,
                host="db.example.com",
                password="secret123",  # pragma: allowlist secret
                token="bearer_token",  # pragma: allowlist secret
            )

            metrics_file = session.session_dir / "metrics.jsonl"
            with open(metrics_file) as f:
                metrics = [json.loads(line) for line in f]

            metric = metrics[0]
            assert metric["password"] == "***"
            assert metric["token"] == "***"
            assert metric["host"] == "db.example.com"  # Not sensitive
            assert metric["value"] == 150  # Not sensitive

    def test_no_secrets_leak_verification(self):
        """Critical test: Verify that no known secrets appear in any session file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            session = SessionContext(base_logs_dir=Path(temp_dir))
            session.setup_logging()

            # Use known secret values
            secret_password = "super_secret_password_123"  # pragma: allowlist secret
            secret_token = "secret_api_token_xyz"  # pragma: allowlist secret
            secret_key = "secret_encryption_key_456"  # pragma: allowlist secret

            # Log events and metrics with secrets
            session.log_event(
                "test_event",
                password=secret_password,
                api_key=secret_token,
                authorization=f"Bearer {secret_token}",
            )

            session.log_metric("test_metric", 100, token=secret_token, secret=secret_key)

            # Save config and manifest with secrets
            config_with_secrets = {
                "db": {"password": secret_password},
                "api": {"token": secret_token, "secret": secret_key},
            }
            session.save_config(config_with_secrets)
            session.save_manifest(config_with_secrets)

            # Save artifact with secrets
            session.save_artifact("secret_data.json", config_with_secrets, "json")

            # Also log to regular logger
            logger = logging.getLogger("test")
            logger.info(f"Connecting with password: {secret_password}")

            session.cleanup_logging()

            # Now scan ALL files in session directory for secrets
            secret_values = [secret_password, secret_token, secret_key]

            for file_path in session.session_dir.rglob("*"):
                if file_path.is_file():
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="ignore")
                        for secret in secret_values:
                            assert secret not in content, f"Secret '{secret}' found in {file_path}"
                    except UnicodeDecodeError:
                        # For binary files, check as bytes
                        content = file_path.read_bytes()
                        for secret in secret_values:
                            secret_bytes = secret.encode("utf-8")
                            assert secret_bytes not in content, f"Secret bytes '{secret}' found in {file_path}"


class TestErrorHandling:
    """Test error handling in session logging."""

    def test_permission_error_handling(self):
        """Test graceful handling of permission errors."""
        # Mock file operations to raise permission errors
        with patch("builtins.open", mock_open()) as mock_file:
            mock_file.side_effect = PermissionError("Access denied")

            with tempfile.TemporaryDirectory() as temp_dir:
                session = SessionContext(base_logs_dir=Path(temp_dir))

                # Should not raise exception
                session.log_event("test_event", data="test")
                session.log_metric("test_metric", 123)
                session.save_config({"key": "value"})
                session.save_manifest({"key": "value"})
                session.save_artifact("test.txt", "content", "text")

    def test_invalid_json_handling(self):
        """Test handling of data that can't be JSON serialized."""
        with tempfile.TemporaryDirectory() as temp_dir:
            session = SessionContext(base_logs_dir=Path(temp_dir))

            # Test with non-serializable object
            class NonSerializable:
                pass

            # Should handle gracefully (convert to string representation)
            session.log_event("test_event", obj=NonSerializable())

            # Event should still be logged (object converted to string)
            events_file = session.session_dir / "events.jsonl"
            assert events_file.exists()


if __name__ == "__main__":
    pytest.main([__file__])
