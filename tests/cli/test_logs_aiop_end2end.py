"""End-to-end tests for osiris logs aiop CLI command."""

import json
import subprocess
import sys
from pathlib import Path


def create_test_session(logs_dir: Path) -> str:
    """Create a minimal test session with events and metrics."""
    session_id = "test_session_123"
    session_dir = logs_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # Create events file with lots of data
    events_file = session_dir / "events.jsonl"
    with open(events_file, "w") as f:
        # Start event
        f.write(json.dumps({"ts": "2024-01-01T00:00:00Z", "event": "run_start", "session": session_id}) + "\n")

        # Add many events to trigger truncation
        for i in range(1000):
            f.write(
                json.dumps(
                    {
                        "ts": f"2024-01-01T00:00:{i%60:02d}Z",
                        "event": "step_progress",
                        "step_id": f"step_{i}",
                        "data": "x" * 100,  # Make events larger
                    }
                )
                + "\n"
            )

        # End event
        f.write(
            json.dumps(
                {
                    "ts": "2024-01-01T01:00:00Z",
                    "event": "run_end",
                    "session": session_id,
                    "status": "completed",
                }
            )
            + "\n"
        )

    # Create metrics file
    metrics_file = session_dir / "metrics.jsonl"
    with open(metrics_file, "w") as f:
        for i in range(100):
            f.write(json.dumps({"step_id": f"step_{i}", "rows_read": i * 100, "duration_ms": i * 1000}) + "\n")

    # Create artifacts directory with manifest
    artifacts_dir = session_dir / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)

    manifest_file = artifacts_dir / "manifest.yaml"
    with open(manifest_file, "w") as f:
        f.write(
            """name: test_pipeline
manifest_hash: abc123
steps:
  - component: mysql.extractor
    step_id: extract
"""
        )

    return session_id


def test_cli_truncation_exit_and_markers(tmp_path):
    """Test that CLI truncation triggers exit code 4 and object markers."""
    # Create test session
    logs_dir = tmp_path / "logs"
    session_id = create_test_session(logs_dir)

    # Run CLI with tiny max-core-bytes to force truncation
    cmd = [
        sys.executable,
        "osiris.py",
        "logs",
        "aiop",
        "--session",
        session_id,
        "--format",
        "json",
        "--max-core-bytes",
        "1500",
        "--logs-dir",
        str(logs_dir),
    ]

    result = subprocess.run(cmd, check=False, capture_output=True, text=True)

    # Assert exit code 4 for truncation
    assert result.returncode == 4, f"Expected exit code 4, got {result.returncode}"

    # Parse JSON output
    aiop = json.loads(result.stdout)

    # Check metadata.truncated
    assert aiop["metadata"]["truncated"] is True

    # Check evidence.timeline is object with markers
    assert isinstance(aiop["evidence"]["timeline"], dict)
    assert aiop["evidence"]["timeline"]["truncated"] is True
    assert "dropped_events" in aiop["evidence"]["timeline"]
    assert "items" in aiop["evidence"]["timeline"]

    # Check evidence.metrics has markers
    assert aiop["evidence"]["metrics"]["truncated"] is True
    assert aiop["evidence"]["metrics"]["aggregates_only"] is True
    assert "dropped_series" in aiop["evidence"]["metrics"]


def test_annex_manifest_present(tmp_path):
    """Test that annex policy generates proper manifest with compress field."""
    # Create test session
    logs_dir = tmp_path / "logs"
    session_id = create_test_session(logs_dir)
    annex_dir = tmp_path / ".aiop-annex"

    # Run CLI with annex policy and gzip
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
        "--format",
        "json",
        "--max-core-bytes",
        "1000000",  # Increase limit to avoid truncation
        "--logs-dir",
        str(logs_dir),
    ]

    result = subprocess.run(cmd, check=False, capture_output=True, text=True)

    # Should succeed
    assert result.returncode == 0

    # Parse JSON output
    aiop = json.loads(result.stdout)

    # Check metadata.annex structure
    assert "annex" in aiop["metadata"]
    assert aiop["metadata"]["annex"]["compress"] == "gzip"
    assert "files" in aiop["metadata"]["annex"]
    assert len(aiop["metadata"]["annex"]["files"]) >= 2

    # Verify annex files exist (files have name, not path)
    # Use the annex_dir we created in tmp_path, not default
    for file_info in aiop["metadata"]["annex"]["files"]:
        file_path = annex_dir / file_info["name"]
        assert file_path.exists(), f"File {file_path} does not exist"
        assert file_path.suffix == ".gz"


def test_console_stderr_no_typeerror(tmp_path, capsys):
    """Test that truncation warning goes to stderr without TypeError."""
    # Create test session
    logs_dir = tmp_path / "logs"
    session_id = create_test_session(logs_dir)

    # Run CLI with truncation
    cmd = [
        sys.executable,
        "osiris.py",
        "logs",
        "aiop",
        "--session",
        session_id,
        "--format",
        "json",
        "--max-core-bytes",
        "1000",
        "--logs-dir",
        str(logs_dir),
    ]

    result = subprocess.run(cmd, check=False, capture_output=True, text=True)

    # Should exit with code 4 (truncated)
    assert result.returncode == 4

    # Check stderr has warning, no TypeError
    assert "truncated" in result.stderr.lower()
    assert "TypeError" not in result.stderr
    assert "file=" not in result.stderr  # Rich Console file= would cause TypeError


def test_md_export_non_empty(tmp_path):
    """Test that Markdown export is never empty."""
    # Create test session
    logs_dir = tmp_path / "logs"
    session_id = create_test_session(logs_dir)

    # Run CLI with MD format
    cmd = [
        sys.executable,
        "osiris.py",
        "logs",
        "aiop",
        "--session",
        session_id,
        "--format",
        "md",
        "--max-core-bytes",
        "1000000",  # Increase limit to avoid truncation
        "--logs-dir",
        str(logs_dir),
    ]

    result = subprocess.run(cmd, check=False, capture_output=True, text=True)

    # Check MD output is not empty
    assert result.returncode == 0
    assert len(result.stdout.strip()) > 0
    assert "##" in result.stdout  # Should have markdown headers
    assert "Status:" in result.stdout  # Should have status line
