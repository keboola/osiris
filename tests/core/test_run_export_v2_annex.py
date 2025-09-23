"""Tests for run_export_v2 annex functionality."""

import gzip
import json
from pathlib import Path

from osiris.core.run_export_v2 import export_annex_shards


def test_export_annex_shards_plain(tmp_path):
    """Test exporting plain NDJSON shards."""
    events = [
        {"event": "start", "timestamp": "2024-01-01T00:00:00Z"},
        {"event": "process", "timestamp": "2024-01-01T00:00:01Z"},
        {"event": "complete", "timestamp": "2024-01-01T00:00:02Z"},
    ]
    metrics = [{"name": "rows_read", "value": 100}, {"name": "rows_written", "value": 100}]
    errors = [{"error": "warning", "message": "Slow query"}]

    annex_dir = tmp_path / "annex"
    annex_dir.mkdir()

    manifest = export_annex_shards(events, metrics, errors, annex_dir, compress="none")

    # Check manifest structure
    assert "files" in manifest
    assert "compress" in manifest
    assert manifest["compress"] == "none"
    assert len(manifest["files"]) == 3

    # Check files were created
    events_file = annex_dir / "events.ndjson"
    metrics_file = annex_dir / "metrics.ndjson"
    errors_file = annex_dir / "errors.ndjson"

    assert events_file.exists()
    assert metrics_file.exists()
    assert errors_file.exists()

    # Validate NDJSON content
    with open(events_file) as f:
        lines = f.readlines()
        assert len(lines) == 3
        for i, line in enumerate(lines):
            parsed = json.loads(line)
            assert parsed == events[i]

    with open(metrics_file) as f:
        lines = f.readlines()
        assert len(lines) == 2
        for i, line in enumerate(lines):
            parsed = json.loads(line)
            assert parsed == metrics[i]

    with open(errors_file) as f:
        lines = f.readlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed == errors[0]

    # Check manifest file info
    events_info = next(f for f in manifest["files"] if f["name"] == "events.ndjson")
    assert events_info["count"] == 3
    assert events_info["size_bytes"] > 0
    assert str(annex_dir / "events.ndjson") in events_info["path"]


def test_export_annex_shards_gzip(tmp_path):
    """Test exporting gzipped NDJSON shards."""
    events = [{"id": i, "data": f"event_{i}"} for i in range(10)]
    metrics = [{"metric": f"m_{i}", "value": i * 1.5} for i in range(5)]
    errors = []  # Empty errors list

    annex_dir = tmp_path / "annex_gz"
    annex_dir.mkdir()

    manifest = export_annex_shards(events, metrics, errors, annex_dir, compress="gzip")

    assert manifest["compress"] == "gzip"

    # Check gzipped files were created
    events_gz = annex_dir / "events.ndjson.gz"
    metrics_gz = annex_dir / "metrics.ndjson.gz"
    errors_gz = annex_dir / "errors.ndjson.gz"

    assert events_gz.exists()
    assert metrics_gz.exists()
    assert errors_gz.exists()

    # Validate gzipped NDJSON content
    with gzip.open(events_gz, "rt") as f:
        lines = f.readlines()
        assert len(lines) == 10
        for i, line in enumerate(lines):
            parsed = json.loads(line)
            assert parsed["id"] == i

    with gzip.open(metrics_gz, "rt") as f:
        lines = f.readlines()
        assert len(lines) == 5

    with gzip.open(errors_gz, "rt") as f:
        lines = f.readlines()
        assert len(lines) == 0  # Empty but file exists

    # Check manifest
    events_info = next(f for f in manifest["files"] if "events" in f["name"])
    assert events_info["name"] == "events.ndjson.gz"
    assert events_info["count"] == 10
    assert events_info["size_bytes"] > 0


def test_export_annex_empty_collections(tmp_path):
    """Test exporting with empty collections."""
    annex_dir = tmp_path / "empty_annex"
    annex_dir.mkdir()

    manifest = export_annex_shards([], [], [], annex_dir, compress="none")

    # Files should still be created even if empty
    assert (annex_dir / "events.ndjson").exists()
    assert (annex_dir / "metrics.ndjson").exists()
    assert (annex_dir / "errors.ndjson").exists()

    # Check manifest
    assert len(manifest["files"]) == 3
    for file_info in manifest["files"]:
        assert file_info["count"] == 0
        assert file_info["size_bytes"] >= 0


def test_export_annex_large_data(tmp_path):
    """Test exporting large amounts of data."""
    # Create large datasets
    events = [{"event": f"e_{i}", "payload": "x" * 100} for i in range(1000)]
    metrics = [{"metric": f"metric_{i}", "value": i} for i in range(500)]
    errors = [{"error": f"err_{i}", "stack": "trace" * 20} for i in range(100)]

    annex_dir = tmp_path / "large_annex"
    annex_dir.mkdir()

    manifest = export_annex_shards(events, metrics, errors, annex_dir, compress="none")

    # Verify counts
    events_info = next(f for f in manifest["files"] if "events" in f["name"])
    metrics_info = next(f for f in manifest["files"] if "metrics" in f["name"])
    errors_info = next(f for f in manifest["files"] if "errors" in f["name"])

    assert events_info["count"] == 1000
    assert metrics_info["count"] == 500
    assert errors_info["count"] == 100

    # Verify all lines are valid JSON
    with open(annex_dir / "events.ndjson") as f:
        line_count = 0
        for line in f:
            json.loads(line)  # Should not raise
            line_count += 1
        assert line_count == 1000


def test_annex_manifest_structure():
    """Test the structure of the annex manifest."""
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmpdir:
        annex_dir = Path(tmpdir) / "test_annex"
        annex_dir.mkdir()

        events = [{"e": 1}]
        metrics = [{"m": 1}]
        errors = [{"err": 1}]

        manifest = export_annex_shards(events, metrics, errors, annex_dir, compress="none")

        # Check required fields
        assert "files" in manifest
        assert "compress" in manifest
        assert isinstance(manifest["files"], list)

        # Check each file entry
        for file_info in manifest["files"]:
            assert "name" in file_info
            assert "path" in file_info
            assert "count" in file_info
            assert "size_bytes" in file_info
            assert isinstance(file_info["count"], int)
            assert isinstance(file_info["size_bytes"], int)
            assert file_info["size_bytes"] >= 0
