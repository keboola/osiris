#!/usr/bin/env python3
"""Tests for JSON serialization with snapshot testing."""

import json
from pathlib import Path
import tempfile

from osiris.core.logs_serialize import to_index_json, to_session_json, validate_against_schema
from osiris.core.session_reader import SessionSummary


class TestIndexSerialization:
    """Test serialization to logs_index.schema.json format."""

    def test_empty_index(self):
        """Test serializing empty session list."""
        sessions = []
        json_str = to_index_json(sessions)
        data = json.loads(json_str)

        assert data["version"] == "1.0.0"
        assert "generated_at" in data
        assert data["total_sessions"] == 0
        assert data["sessions"] == []

    def test_single_session_index(self):
        """Test serializing single session."""
        session = SessionSummary(
            session_id="test_001",
            started_at="2025-01-01T10:00:00Z",
            finished_at="2025-01-01T10:05:00Z",
            duration_ms=300000,
            status="success",
            labels=["test", "automated"],
            pipeline_name="test_pipeline",
            steps_total=5,
            steps_ok=5,
            rows_in=1000,
            rows_out=950,
            errors=0,
            warnings=1,
        )

        json_str = to_index_json([session])
        data = json.loads(json_str)

        assert data["version"] == "1.0.0"
        assert data["total_sessions"] == 1
        assert len(data["sessions"]) == 1

        s = data["sessions"][0]
        assert s["session_id"] == "test_001"
        assert s["started_at"] == "2025-01-01T10:00:00Z"
        assert s["finished_at"] == "2025-01-01T10:05:00Z"
        assert s["duration_ms"] == 300000
        assert s["status"] == "success"
        assert s["labels"] == ["test", "automated"]
        assert s["pipeline_name"] == "test_pipeline"
        assert s["steps_total"] == 5
        assert s["steps_ok"] == 5
        assert s["rows_in"] == 1000
        assert s["rows_out"] == 950
        assert s["errors"] == 0
        assert s["warnings"] == 1

    def test_multiple_sessions_index(self):
        """Test serializing multiple sessions."""
        sessions = [
            SessionSummary(session_id="test_001", status="success", steps_total=5, steps_ok=5),
            SessionSummary(
                session_id="test_002",
                status="failed",
                steps_total=3,
                steps_ok=2,
                steps_failed=1,
                errors=1,
            ),
            SessionSummary(session_id="test_003", status="running", steps_total=0),
        ]

        json_str = to_index_json(sessions)
        data = json.loads(json_str)

        assert data["total_sessions"] == 3
        assert len(data["sessions"]) == 3
        assert data["sessions"][0]["session_id"] == "test_001"
        assert data["sessions"][1]["session_id"] == "test_002"
        assert data["sessions"][2]["session_id"] == "test_003"

    def test_unknown_status_normalization(self):
        """Test that invalid status values are normalized to 'unknown'."""
        session = SessionSummary(
            session_id="test_001", status="invalid_status"  # Should be normalized
        )

        json_str = to_index_json([session])
        data = json.loads(json_str)

        assert data["sessions"][0]["status"] == "unknown"

    def test_deterministic_json_output(self):
        """Test that JSON output is deterministic (except timestamp)."""
        session = SessionSummary(
            session_id="test_001",
            status="success",
            labels=["z", "a", "m"],  # Unordered
            tables=["users", "orders", "products"],  # Unordered
        )

        # Generate JSON multiple times
        json1 = to_index_json([session])
        json2 = to_index_json([session])

        data1 = json.loads(json1)
        data2 = json.loads(json2)

        # Remove timestamps for comparison
        del data1["generated_at"]
        del data2["generated_at"]

        # Now they should be identical
        assert data1 == data2

        # Keys should be sorted
        keys = list(data1.keys())
        assert keys == sorted(keys)


class TestSessionSerialization:
    """Test serialization to logs_session.schema.json format."""

    def test_basic_session(self):
        """Test serializing basic session details."""
        session = SessionSummary(
            session_id="test_001",
            started_at="2025-01-01T10:00:00Z",
            finished_at="2025-01-01T10:05:00Z",
            duration_ms=300000,
            status="success",
            labels=["test"],
            pipeline_name="test_pipeline",
            oml_version="0.1.0",
            steps_total=5,
            steps_ok=5,
            steps_failed=0,
            rows_in=1000,
            rows_out=950,
            tables=["users", "orders"],
            errors=0,
            warnings=1,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir) / "logs"
            logs_dir.mkdir()
            session_dir = logs_dir / "test_001"
            session_dir.mkdir()

            # Create artifact files
            artifacts_dir = session_dir / "artifacts"
            artifacts_dir.mkdir()
            (artifacts_dir / "pipeline.yaml").write_text("test")

            compiled_dir = artifacts_dir / "compiled"
            compiled_dir.mkdir()
            (compiled_dir / "manifest.yaml").write_text("test")

            json_str = to_session_json(session, str(logs_dir))
            data = json.loads(json_str)

            assert data["version"] == "1.0.0"
            assert data["session_id"] == "test_001"
            assert data["started_at"] == "2025-01-01T10:00:00Z"
            assert data["finished_at"] == "2025-01-01T10:05:00Z"
            assert data["duration_ms"] == 300000
            assert data["status"] == "success"
            assert data["labels"] == ["test"]
            assert data["pipeline_name"] == "test_pipeline"
            assert data["oml_version"] == "0.1.0"

            # Steps section
            assert data["steps"]["total"] == 5
            assert data["steps"]["completed"] == 5
            assert data["steps"]["failed"] == 0
            assert data["steps"]["success_rate"] == 1.0

            # Data flow section
            assert data["data_flow"]["rows_in"] == 1000
            assert data["data_flow"]["rows_out"] == 950
            assert data["data_flow"]["tables"] == ["users", "orders"]

            # Diagnostics section
            assert data["diagnostics"]["errors"] == 0
            assert data["diagnostics"]["warnings"] == 1

            # Artifacts section
            assert data["artifacts"]["pipeline_yaml"] == "artifacts/pipeline.yaml"
            assert data["artifacts"]["manifest"] == "artifacts/compiled/manifest.yaml"
            assert data["artifacts"]["logs"]["events"] == "events.jsonl"
            assert data["artifacts"]["logs"]["metrics"] == "metrics.jsonl"

    def test_session_without_artifacts(self):
        """Test session without artifact files."""
        session = SessionSummary(session_id="test_001", status="running")

        with tempfile.TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir) / "logs"
            logs_dir.mkdir()
            session_dir = logs_dir / "test_001"
            session_dir.mkdir()

            json_str = to_session_json(session, str(logs_dir))
            data = json.loads(json_str)

            assert data["artifacts"]["pipeline_yaml"] is None
            assert data["artifacts"]["manifest"] is None
            assert data["artifacts"]["logs"]["events"] == "events.jsonl"
            assert data["artifacts"]["logs"]["metrics"] == "metrics.jsonl"

    def test_success_rate_rounding(self):
        """Test that success rate is rounded to 3 decimal places."""
        session = SessionSummary(
            session_id="test_001", status="success", steps_total=3, steps_ok=2, steps_failed=1
        )

        json_str = to_session_json(session, "./logs")
        data = json.loads(json_str)

        # 2/3 = 0.666666... should round to 0.667
        assert data["steps"]["success_rate"] == 0.667


class TestSchemaValidation:
    """Test schema validation functionality."""

    def test_validate_valid_index(self):
        """Test validating a valid index JSON."""
        sessions = [
            SessionSummary(session_id="test_001", status="success"),
            SessionSummary(session_id="test_002", status="failed"),
        ]

        json_str = to_index_json(sessions)
        schema_path = Path(__file__).parent.parent.parent / "schemas" / "logs_index.schema.json"

        if schema_path.exists():
            assert validate_against_schema(json_str, str(schema_path))

    def test_validate_valid_session(self):
        """Test validating a valid session JSON."""
        session = SessionSummary(session_id="test_001", status="success", pipeline_name="test")

        json_str = to_session_json(session, "./logs")
        schema_path = Path(__file__).parent.parent.parent / "schemas" / "logs_session.schema.json"

        if schema_path.exists():
            assert validate_against_schema(json_str, str(schema_path))

    def test_validate_missing_required_field(self):
        """Test validation fails with missing required field."""
        # Create invalid JSON missing required "version" field
        invalid_json = json.dumps({"generated_at": "2025-01-01T10:00:00Z", "sessions": []})

        schema_path = Path(__file__).parent.parent.parent / "schemas" / "logs_index.schema.json"

        if schema_path.exists():
            assert not validate_against_schema(invalid_json, str(schema_path))

    def test_validate_wrong_version(self):
        """Test validation fails with wrong version."""
        # Create JSON with wrong version
        invalid_json = json.dumps(
            {
                "version": "2.0.0",  # Should be "1.0.0"
                "generated_at": "2025-01-01T10:00:00Z",
                "sessions": [],
            }
        )

        schema_path = Path(__file__).parent.parent.parent / "schemas" / "logs_index.schema.json"

        if schema_path.exists():
            assert not validate_against_schema(invalid_json, str(schema_path))

    def test_validate_invalid_json(self):
        """Test validation handles invalid JSON gracefully."""
        invalid_json = "{ this is not valid json }"
        schema_path = Path(__file__).parent.parent.parent / "schemas" / "logs_index.schema.json"

        assert not validate_against_schema(invalid_json, str(schema_path))

    def test_validate_nonexistent_schema(self):
        """Test validation handles missing schema file gracefully."""
        valid_json = json.dumps({"version": "1.0.0"})

        assert not validate_against_schema(valid_json, "/nonexistent/schema.json")


class TestSnapshotCompatibility:
    """Test that serialized output matches expected snapshots."""

    def test_index_snapshot(self):
        """Test index JSON matches expected structure."""
        sessions = [
            SessionSummary(
                session_id="compile_1234567890",
                started_at="2025-01-01T10:00:00.000Z",
                finished_at="2025-01-01T10:05:30.123Z",
                duration_ms=330123,
                status="success",
                labels=["production", "automated"],
                pipeline_name="etl_customer_data",
                steps_total=10,
                steps_ok=10,
                rows_in=50000,
                rows_out=48500,
                errors=0,
                warnings=3,
            ),
            SessionSummary(
                session_id="run_9876543210",
                started_at="2025-01-01T09:30:00.000Z",
                finished_at="2025-01-01T09:31:15.456Z",
                duration_ms=75456,
                status="failed",
                labels=["debug"],
                pipeline_name="test_pipeline",
                steps_total=5,
                steps_ok=3,
                rows_in=1000,
                rows_out=600,
                errors=2,
                warnings=1,
            ),
        ]

        json_str = to_index_json(sessions)
        data = json.loads(json_str)

        # Verify structure matches schema expectations
        assert "version" in data
        assert "generated_at" in data
        assert "total_sessions" in data
        assert "sessions" in data

        # Verify all required session fields are present
        for session in data["sessions"]:
            assert "session_id" in session
            assert "status" in session
            assert session["status"] in ["success", "failed", "running", "unknown"]

    def test_session_snapshot(self):
        """Test session JSON matches expected structure."""
        session = SessionSummary(
            session_id="compile_1234567890",
            started_at="2025-01-01T10:00:00.000Z",
            finished_at="2025-01-01T10:05:30.123Z",
            duration_ms=330123,
            status="success",
            labels=["production"],
            pipeline_name="etl_customer_data",
            oml_version="0.1.0",
            steps_total=10,
            steps_ok=10,
            steps_failed=0,
            rows_in=50000,
            rows_out=48500,
            tables=["customers", "orders", "products"],
            errors=0,
            warnings=3,
        )

        json_str = to_session_json(session, "./logs")
        data = json.loads(json_str)

        # Verify all top-level sections are present
        assert "version" in data
        assert "session_id" in data
        assert "status" in data
        assert "steps" in data
        assert "data_flow" in data
        assert "diagnostics" in data
        assert "artifacts" in data

        # Verify nested structure
        assert "total" in data["steps"]
        assert "completed" in data["steps"]
        assert "failed" in data["steps"]
        assert "success_rate" in data["steps"]

        assert "rows_in" in data["data_flow"]
        assert "rows_out" in data["data_flow"]
        assert "tables" in data["data_flow"]

        assert "errors" in data["diagnostics"]
        assert "warnings" in data["diagnostics"]

        assert "pipeline_yaml" in data["artifacts"]
        assert "manifest" in data["artifacts"]
        assert "logs" in data["artifacts"]
