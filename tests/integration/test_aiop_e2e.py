"""End-to-end integration tests for AIOP export functionality."""

import json
import subprocess
import sys

import pytest
import yaml


class TestAIOPEndToEnd:
    """Integration tests for AIOP export covering all formats and policies."""

    @pytest.fixture
    def sample_session(self, tmp_path):
        """Create a minimal test session with events and metrics."""
        session_id = "test_aiop_e2e_session"
        logs_dir = tmp_path / "logs"
        session_dir = logs_dir / session_id
        session_dir.mkdir(parents=True)

        # Create events file
        events_file = session_dir / "events.jsonl"
        events = [
            {
                "ts": "2024-01-01T00:00:00Z",
                "event": "run_start",
                "session": session_id,
                "data": {"pipeline": "test_pipeline"},
            },
            {
                "ts": "2024-01-01T00:00:10Z",
                "event": "step_start",
                "step_id": "extract",
                "data": {"component": "mysql.extractor"},
            },
            {
                "ts": "2024-01-01T00:00:20Z",
                "event": "step_complete",
                "step_id": "extract",
                "data": {"rows_read": 1000},
            },
            {
                "ts": "2024-01-01T00:01:00Z",
                "event": "run_end",
                "session": session_id,
                "status": "success",
            },
        ]
        with open(events_file, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        # Create metrics file
        metrics_file = session_dir / "metrics.jsonl"
        metrics = [
            {"step_id": "extract", "rows_read": 1000, "duration_ms": 10000},
            {"step_id": "transform", "rows_processed": 950, "duration_ms": 5000},
            {"step_id": "write", "rows_written": 950, "duration_ms": 3000},
        ]
        with open(metrics_file, "w") as f:
            for metric in metrics:
                f.write(json.dumps(metric) + "\n")

        # Create artifacts directory with manifest
        artifacts_dir = session_dir / "artifacts"
        artifacts_dir.mkdir()
        manifest_file = artifacts_dir / "manifest.yaml"
        manifest = {
            "name": "test_pipeline",
            "oml_version": "0.1.0",
            "steps": [
                {"step_id": "extract", "component": "mysql.extractor"},
                {"step_id": "transform", "component": "duckdb.transformer"},
                {"step_id": "write", "component": "filesystem.csv_writer"},
            ],
        }
        with open(manifest_file, "w") as f:
            yaml.dump(manifest, f)

        return session_id, logs_dir

    def test_aiop_json_export(self, sample_session):
        """Test AIOP export in JSON format."""
        session_id, logs_dir = sample_session

        # Run AIOP export
        cmd = [
            sys.executable,
            "osiris.py",
            "logs",
            "aiop",
            "--session",
            session_id,
            "--format",
            "json",
            "--logs-dir",
            str(logs_dir),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Verify successful execution
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Parse and validate JSON structure
        aiop = json.loads(result.stdout)
        assert "@context" in aiop
        assert "@id" in aiop
        assert "evidence" in aiop
        assert "semantic" in aiop
        assert "narrative" in aiop
        assert "metadata" in aiop

        # Validate evidence layer
        assert "timeline" in aiop["evidence"]
        assert "metrics" in aiop["evidence"]
        assert "errors" in aiop["evidence"]
        assert "artifacts" in aiop["evidence"]

        # Validate metadata
        assert aiop["metadata"]["aiop_format"] == "1.0"
        assert "truncated" in aiop["metadata"]
        assert "size_bytes" in aiop["metadata"]

    def test_aiop_markdown_export(self, sample_session):
        """Test AIOP export in Markdown format."""
        session_id, logs_dir = sample_session

        # Run AIOP export
        cmd = [
            sys.executable,
            "osiris.py",
            "logs",
            "aiop",
            "--session",
            session_id,
            "--format",
            "md",
            "--logs-dir",
            str(logs_dir),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Verify successful execution
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Validate Markdown structure
        output = result.stdout
        assert "## " in output  # Has headers
        assert "**Status:**" in output
        assert "**Duration:**" in output
        assert "### " in output  # Has subsections

    def test_aiop_annex_policy(self, sample_session, tmp_path):
        """Test AIOP export with annex policy."""
        session_id, logs_dir = sample_session
        annex_dir = tmp_path / "aiop-annex"

        # Run AIOP export with annex
        cmd = [
            sys.executable,
            "osiris.py",
            "logs",
            "aiop",
            "--session",
            session_id,
            "--policy",
            "annex",
            "--annex-dir",
            str(annex_dir),
            "--compress",
            "gzip",
            "--logs-dir",
            str(logs_dir),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Verify successful execution
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Parse AIOP and check for annex manifest
        aiop = json.loads(result.stdout)
        assert "annex" in aiop["metadata"]
        assert aiop["metadata"]["annex"]["compress"] == "gzip"
        assert "files" in aiop["metadata"]["annex"]

        # Verify annex files exist
        assert annex_dir.exists()
        assert (annex_dir / "events.ndjson.gz").exists()
        assert (annex_dir / "metrics.ndjson.gz").exists()
        assert (annex_dir / "errors.ndjson.gz").exists()

    def test_aiop_truncation(self, sample_session):
        """Test AIOP truncation with size limits."""
        session_id, logs_dir = sample_session

        # Run with very small size limit to force truncation
        cmd = [
            sys.executable,
            "osiris.py",
            "logs",
            "aiop",
            "--session",
            session_id,
            "--max-core-bytes",
            "1000",
            "--logs-dir",
            str(logs_dir),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Should exit with code 4 for truncation
        assert result.returncode == 4, f"Expected exit code 4, got {result.returncode}"

        # Verify truncation markers
        aiop = json.loads(result.stdout)
        assert aiop["metadata"]["truncated"] is True

        # Check for object-level markers
        if isinstance(aiop["evidence"]["timeline"], dict):
            assert aiop["evidence"]["timeline"]["truncated"] is True
            assert "dropped_events" in aiop["evidence"]["timeline"]

    def test_aiop_config_precedence(self, sample_session, tmp_path, monkeypatch):
        """Test configuration precedence: CLI > ENV > YAML > defaults."""
        session_id, logs_dir = sample_session

        # Set environment variable
        monkeypatch.setenv("OSIRIS_AIOP_MAX_CORE_BYTES", "200000")

        # Run with CLI override
        cmd = [
            sys.executable,
            "osiris.py",
            "logs",
            "aiop",
            "--session",
            session_id,
            "--max-core-bytes",
            "100000",  # CLI should override ENV
            "--logs-dir",
            str(logs_dir),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Verify execution
        assert result.returncode in [0, 4]  # May or may not truncate

        # Parse output
        aiop = json.loads(result.stdout)

        # Size should respect CLI value (100000), not ENV value (200000)
        assert aiop["metadata"]["size_bytes"] <= 100000 * 1.1  # Allow 10% overhead

    def test_aiop_last_session(self, sample_session):
        """Test AIOP export with --last flag."""
        session_id, logs_dir = sample_session

        # Run with --last flag
        cmd = [
            sys.executable,
            "osiris.py",
            "logs",
            "aiop",
            "--last",
            "--format",
            "json",
            "--logs-dir",
            str(logs_dir),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Verify successful execution
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Verify it exported the correct session
        aiop = json.loads(result.stdout)
        assert session_id in aiop["run"]["session_id"]

    def test_aiop_determinism(self, sample_session):
        """Test that same input produces identical AIOP."""
        session_id, logs_dir = sample_session

        # Run twice with same parameters
        cmd = [
            sys.executable,
            "osiris.py",
            "logs",
            "aiop",
            "--session",
            session_id,
            "--format",
            "json",
            "--logs-dir",
            str(logs_dir),
        ]

        result1 = subprocess.run(cmd, capture_output=True, text=True)
        result2 = subprocess.run(cmd, capture_output=True, text=True)

        # Both should succeed
        assert result1.returncode == 0
        assert result2.returncode == 0

        # Output should be identical (deterministic)
        assert result1.stdout == result2.stdout

    def test_aiop_secret_redaction(self, tmp_path):
        """Test that secrets are properly redacted in AIOP."""
        session_id = "test_secrets"
        logs_dir = tmp_path / "logs"
        session_dir = logs_dir / session_id
        session_dir.mkdir(parents=True)

        # Create events with secrets
        events_file = session_dir / "events.jsonl"
        events = [
            {
                "ts": "2024-01-01T00:00:00Z",
                "event": "run_start",
                "session": session_id,
                "data": {
                    "connection_url": "postgresql://user:secretpassword@localhost/db",  # pragma: allowlist secret
                    "api_key": "sk-1234567890",  # pragma: allowlist secret
                    "token": "bearer-xyz",  # pragma: allowlist secret
                },
            },
            {
                "ts": "2024-01-01T00:00:10Z",
                "event": "step_start",
                "step_id": "extract",
                "data": {
                    "url": "postgresql://user:secretpassword@localhost/db",  # pragma: allowlist secret
                },
            },
        ]
        with open(events_file, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        # Run AIOP export
        cmd = [
            sys.executable,
            "osiris.py",
            "logs",
            "aiop",
            "--session",
            session_id,
            "--logs-dir",
            str(logs_dir),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Parse output
        aiop_str = result.stdout

        # Verify secrets are not in output
        assert "secretpassword" not in aiop_str
        assert "sk-1234567890" not in aiop_str
        assert "bearer-xyz" not in aiop_str

        # Verify redaction markers are present
        assert "***" in aiop_str or "[REDACTED]" in aiop_str

    def test_aiop_output_to_file(self, sample_session, tmp_path):
        """Test AIOP export to file."""
        session_id, logs_dir = sample_session
        output_file = tmp_path / "aiop.json"

        # Run with --output flag
        cmd = [
            sys.executable,
            "osiris.py",
            "logs",
            "aiop",
            "--session",
            session_id,
            "--output",
            str(output_file),
            "--logs-dir",
            str(logs_dir),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Should succeed
        assert result.returncode == 0

        # File should exist and contain valid JSON
        assert output_file.exists()
        with open(output_file) as f:
            aiop = json.load(f)
            assert "@context" in aiop
            assert "evidence" in aiop

    def test_aiop_invalid_session(self, tmp_path):
        """Test AIOP export with non-existent session."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        # Try to export non-existent session
        cmd = [
            sys.executable,
            "osiris.py",
            "logs",
            "aiop",
            "--session",
            "nonexistent",
            "--logs-dir",
            str(logs_dir),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Should fail with exit code 2
        assert result.returncode == 2
        assert "not found" in result.stderr.lower() or "not found" in result.stdout.lower()

    def test_config_precedence_echo(self, sample_session):
        """Test that config_effective echoes final configuration after precedence."""
        session_id, logs_dir = sample_session

        # Set environment variable
        import os

        os.environ["OSIRIS_AIOP_TIMELINE_DENSITY"] = "high"

        # Run with CLI override
        cmd = [
            sys.executable,
            "osiris.py",
            "logs",
            "aiop",
            "--session",
            session_id,
            "--timeline-density",
            "low",  # CLI should win
            "--logs-dir",
            str(logs_dir),
            "--format",
            "json",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Parse JSON output
        aiop = json.loads(result.stdout)

        # Check config_effective exists and has correct values
        assert "metadata" in aiop
        assert "config_effective" in aiop["metadata"]
        config = aiop["metadata"]["config_effective"]

        # CLI should override ENV
        assert config["timeline_density"] == "low"

        # Check other defaults are present
        assert config["policy"] == "core"
        assert config["max_core_bytes"] == 300000
        assert config["compress"] == "none"
        assert config["metrics_topk"] == 100
        assert config["schema_mode"] == "summary"

        # Clean up env
        del os.environ["OSIRIS_AIOP_TIMELINE_DENSITY"]

    def test_annex_manifest_in_core(self, sample_session, tmp_path):
        """Test that annex policy includes manifest in Core JSON."""
        session_id, logs_dir = sample_session
        annex_dir = tmp_path / ".aiop-annex"

        # Run with annex policy
        cmd = [
            sys.executable,
            "osiris.py",
            "logs",
            "aiop",
            "--session",
            session_id,
            "--policy",
            "annex",
            "--annex-dir",
            str(annex_dir),
            "--compress",
            "gzip",
            "--logs-dir",
            str(logs_dir),
            "--format",
            "json",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Parse JSON output
        aiop = json.loads(result.stdout)

        # Check annex manifest exists
        assert "metadata" in aiop
        assert "annex" in aiop["metadata"]
        annex = aiop["metadata"]["annex"]

        # Check structure
        assert annex["compress"] == "gzip"
        assert "files" in annex
        assert isinstance(annex["files"], list)
        assert len(annex["files"]) > 0

        # Check each file entry
        for f in annex["files"]:
            assert "name" in f
            assert "count" in f
            assert "bytes" in f
            assert f["name"].endswith(".ndjson.gz")  # Should be gzipped

        # Check annex files actually exist
        assert annex_dir.exists()
        for f in annex["files"]:
            file_path = annex_dir / f["name"]
            assert file_path.exists()
