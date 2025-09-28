#!/usr/bin/env python3
"""Tests for SessionReader class."""

import json
from pathlib import Path
import tempfile

import pytest

from osiris.core.session_reader import SessionReader


@pytest.fixture
def temp_logs_dir():
    """Create a temporary logs directory with test data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logs_dir = Path(tmpdir) / "logs"
        logs_dir.mkdir()

        # Create multiple test sessions
        _create_test_session(
            logs_dir,
            "session_001",
            "success",
            start_ts="2025-01-01T10:00:00Z",
            end_ts="2025-01-01T10:05:00Z",
            steps_ok=5,
            steps_failed=0,
            rows_in=1000,
            rows_out=950,
        )

        _create_test_session(
            logs_dir,
            "session_002",
            "failed",
            start_ts="2025-01-01T11:00:00Z",
            end_ts="2025-01-01T11:03:00Z",
            steps_ok=2,
            steps_failed=1,
            rows_in=500,
            rows_out=200,
        )

        _create_test_session(
            logs_dir,
            "session_003",
            "running",
            start_ts="2025-01-01T12:00:00Z",
            end_ts=None,
            steps_ok=3,
            steps_failed=0,
            rows_in=750,
            rows_out=0,
        )

        yield logs_dir


def _create_test_session(
    logs_dir, session_id, status, start_ts, end_ts, steps_ok, steps_failed, rows_in, rows_out
):
    """Helper to create a test session directory with logs."""
    session_dir = logs_dir / session_id
    session_dir.mkdir()

    # Create metadata.json
    metadata = {
        "session_id": session_id,
        "started_at": start_ts,
        "finished_at": end_ts,
        "duration_ms": 300000 if end_ts else 0,
        "status": status,
        "labels": ["test", "automated"],
        "pipeline_name": f"test_pipeline_{session_id}",
        "rows_in": rows_in,
        "rows_out": rows_out,
    }
    (session_dir / "metadata.json").write_text(json.dumps(metadata))

    # Create events.jsonl
    events = []
    events.append({"ts": start_ts, "session": session_id, "event": "run_start"})

    # Add step events (without rows_read/rows_written since metadata has totals)
    for i in range(steps_ok):
        events.append(
            {"ts": start_ts, "session": session_id, "event": "step_start", "step_id": f"step_{i+1}"}
        )
        events.append(
            {
                "ts": start_ts,
                "session": session_id,
                "event": "step_complete",
                "step_id": f"step_{i+1}",
            }
        )

    for i in range(steps_failed):
        events.append(
            {
                "ts": start_ts,
                "session": session_id,
                "event": "step_start",
                "step_id": f"step_failed_{i+1}",
            }
        )
        events.append(
            {
                "ts": start_ts,
                "session": session_id,
                "event": "step_error",
                "step_id": f"step_failed_{i+1}",
                "level": "error",
                "message": "Test error",
            }
        )

    # Add warnings
    events.append(
        {
            "ts": start_ts,
            "session": session_id,
            "event": "log",
            "level": "warning",
            "message": "Test warning",
        }
    )

    # Add OML validation event
    events.append(
        {
            "ts": start_ts,
            "session": session_id,
            "event": "oml_validated",
            "oml_version": "0.1.0",
            "pipeline": {"name": f"test_pipeline_{session_id}"},
        }
    )

    if end_ts:
        events.append(
            {
                "ts": end_ts,
                "session": session_id,
                "event": "run_end",
                "status": "failed" if status == "failed" else "completed",
            }
        )

    with open(session_dir / "events.jsonl", "w") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")

    # Create metrics.jsonl
    metrics = [{"ts": start_ts, "session": session_id, "metric": "total_rows", "value": rows_out}]
    with open(session_dir / "metrics.jsonl", "w") as f:
        for metric in metrics:
            f.write(json.dumps(metric) + "\n")

    # Create artifacts directory with a test YAML
    artifacts_dir = session_dir / "artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "pipeline.yaml").write_text(f"name: test_pipeline_{session_id}\n")


class TestSessionReader:
    """Test SessionReader functionality."""

    def test_list_sessions(self, temp_logs_dir):
        """Test listing all sessions."""
        reader = SessionReader(str(temp_logs_dir))
        sessions = reader.list_sessions()

        assert len(sessions) == 3
        # Should be sorted newest first
        assert sessions[0].session_id == "session_003"
        assert sessions[1].session_id == "session_002"
        assert sessions[2].session_id == "session_001"

    def test_list_sessions_with_limit(self, temp_logs_dir):
        """Test listing sessions with limit."""
        reader = SessionReader(str(temp_logs_dir))
        sessions = reader.list_sessions(limit=2)

        assert len(sessions) == 2
        assert sessions[0].session_id == "session_003"
        assert sessions[1].session_id == "session_002"

    def test_read_session(self, temp_logs_dir):
        """Test reading a single session."""
        reader = SessionReader(str(temp_logs_dir))
        session = reader.read_session("session_001")

        assert session is not None
        assert session.session_id == "session_001"
        assert session.status == "success"
        assert session.started_at == "2025-01-01T10:00:00Z"
        assert session.finished_at == "2025-01-01T10:05:00Z"
        assert session.duration_ms == 300000
        assert session.pipeline_name == "test_pipeline_session_001"
        assert session.steps_total == 5
        assert session.steps_ok == 5
        assert session.steps_failed == 0
        assert session.rows_in == 1000
        assert session.rows_out == 950
        assert session.warnings == 1
        assert session.errors == 0
        assert session.labels == ["test", "automated"]
        assert session.oml_version == "0.1.0"

    def test_read_failed_session(self, temp_logs_dir):
        """Test reading a failed session."""
        reader = SessionReader(str(temp_logs_dir))
        session = reader.read_session("session_002")

        assert session is not None
        assert session.status == "failed"
        assert session.steps_total == 3  # 2 ok + 1 failed
        assert session.steps_ok == 2
        assert session.steps_failed == 1
        assert session.errors == 2  # step_error event + level='error' both count

    def test_read_nonexistent_session(self, temp_logs_dir):
        """Test reading a nonexistent session."""
        reader = SessionReader(str(temp_logs_dir))
        session = reader.read_session("nonexistent")

        assert session is None

    def test_get_last_session(self, temp_logs_dir):
        """Test getting the most recent session."""
        reader = SessionReader(str(temp_logs_dir))
        session = reader.get_last_session()

        assert session is not None
        assert session.session_id == "session_003"
        assert session.status == "running"

    def test_success_rate_calculation(self, temp_logs_dir):
        """Test success rate calculation."""
        reader = SessionReader(str(temp_logs_dir))

        session1 = reader.read_session("session_001")
        assert session1.success_rate == 1.0  # 5/5

        session2 = reader.read_session("session_002")
        assert abs(session2.success_rate - 0.667) < 0.01  # 2/3

        session3 = reader.read_session("session_003")
        assert session3.success_rate == 1.0  # 3/3 (no failures yet)

    def test_empty_logs_directory(self):
        """Test with empty logs directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir) / "logs"
            logs_dir.mkdir()

            reader = SessionReader(str(logs_dir))
            sessions = reader.list_sessions()

            assert len(sessions) == 0
            assert reader.get_last_session() is None

    def test_nonexistent_logs_directory(self):
        """Test with nonexistent logs directory."""
        reader = SessionReader("/nonexistent/path")
        sessions = reader.list_sessions()

        assert len(sessions) == 0
        assert reader.get_last_session() is None

    def test_session_with_tables(self, temp_logs_dir):
        """Test session with table tracking."""
        # Add a session with table events
        session_dir = temp_logs_dir / "session_tables"
        session_dir.mkdir()

        events = [
            {"ts": "2025-01-01T13:00:00Z", "session": "session_tables", "event": "run_start"},
            {
                "ts": "2025-01-01T13:00:00Z",
                "session": "session_tables",
                "event": "step_start",
                "step_id": "extract",
                "table": "users",
            },
            {
                "ts": "2025-01-01T13:00:00Z",
                "session": "session_tables",
                "event": "step_complete",
                "step_id": "extract",
                "table": "orders",
            },
            {
                "ts": "2025-01-01T13:00:00Z",
                "session": "session_tables",
                "event": "step_start",
                "step_id": "write",
                "table": "customers",
            },
        ]

        with open(session_dir / "events.jsonl", "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        reader = SessionReader(str(temp_logs_dir))
        session = reader.read_session("session_tables")

        assert session is not None
        assert sorted(session.tables) == ["customers", "orders", "users"]

    def test_deterministic_ordering(self, temp_logs_dir):
        """Test that ordering is deterministic."""
        reader = SessionReader(str(temp_logs_dir))

        # Get sessions multiple times
        sessions1 = reader.list_sessions()
        sessions2 = reader.list_sessions()
        sessions3 = reader.list_sessions()

        # Should always be in same order
        assert [s.session_id for s in sessions1] == [s.session_id for s in sessions2]
        assert [s.session_id for s in sessions2] == [s.session_id for s in sessions3]


class TestRedaction:
    """Test sensitive data redaction."""

    def test_redact_mysql_connection(self):
        """Test MySQL connection string redaction."""
        reader = SessionReader()

        text = "mysql://user:password123@localhost:3306/db"  # pragma: allowlist secret
        redacted = reader.redact_text(text)
        assert redacted == "mysql://***@localhost:3306/db"

        text = "mysql://admin:secret@192.168.1.1/mydb"  # pragma: allowlist secret
        redacted = reader.redact_text(text)
        assert redacted == "mysql://***@192.168.1.1/mydb"

    def test_redact_postgresql_connection(self):
        """Test PostgreSQL connection string redaction."""
        reader = SessionReader()

        text = "postgresql://user:pass@host/db"  # pragma: allowlist secret
        redacted = reader.redact_text(text)
        assert redacted == "postgresql://***@host/db"

        text = "postgres://user:pass@host/db"  # pragma: allowlist secret
        redacted = reader.redact_text(text)
        assert redacted == "postgres://***@host/db"

    def test_redact_json_passwords(self):
        """Test JSON password field redaction."""
        reader = SessionReader()

        text = '{"password": "secret123", "user": "admin"}'  # pragma: allowlist secret
        redacted = reader.redact_text(text)
        assert '"password": "***"' in redacted
        assert '"user": "admin"' in redacted

    def test_redact_api_keys(self):
        """Test API key redaction."""
        reader = SessionReader()

        text = '{"api_key": "sk-1234567890", "endpoint": "https://api.example.com"}'  # pragma: allowlist secret
        redacted = reader.redact_text(text)
        assert '"api_key": "***"' in redacted
        assert '"endpoint": "https://api.example.com"' in redacted

    def test_redact_bearer_tokens(self):
        """Test Bearer token redaction."""
        reader = SessionReader()

        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM"  # pragma: allowlist secret
        redacted = reader.redact_text(text)
        assert redacted == "Authorization: Bearer ***"

    def test_filter_safe_fields(self):
        """Test filtering to only safe fields."""
        reader = SessionReader()

        data = {
            "session_id": "test_123",
            "status": "success",
            "password": "secret",  # Should be filtered  # pragma: allowlist secret
            "api_key": "key123",  # Should be filtered  # pragma: allowlist secret
            "started_at": "2025-01-01T10:00:00Z",
            "connection_string": "mysql://user:pass@host",  # Should be filtered  # pragma: allowlist secret
            "rows_read": 100,
        }

        filtered = reader.filter_safe_fields(data)

        assert "session_id" in filtered
        assert "status" in filtered
        assert "started_at" in filtered
        assert "rows_read" in filtered
        assert "password" not in filtered
        assert "api_key" not in filtered
        assert "connection_string" not in filtered
