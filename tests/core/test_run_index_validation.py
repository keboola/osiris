"""Tests for run index manifest_hash validation (rejects algorithm prefixes)."""

import pytest

from osiris.core.run_index import RunIndexWriter, RunRecord


def test_run_index_rejects_sha256_prefix(tmp_path):
    """Test that RunIndexWriter.append() rejects manifest_hash with 'sha256:' prefix."""
    index_dir = tmp_path / ".osiris" / "index"
    writer = RunIndexWriter(index_dir)

    # Create a record with prefixed hash
    record = RunRecord(
        run_id="test_run_001",
        pipeline_slug="test_pipeline",
        profile="dev",
        manifest_hash="sha256:abc123def456",  # Invalid: has algorithm prefix
        manifest_short="abc123d",
        run_ts="2025-10-08T10:00:00Z",
        status="success",
        duration_ms=1000,
        run_logs_path="/path/to/logs",
        aiop_path="/path/to/aiop",
        build_manifest_path="/path/to/manifest",
        tags=[],
    )

    # Should raise ValueError
    with pytest.raises(ValueError, match="manifest_hash must be pure hex"):
        writer.append(record)


def test_run_index_rejects_custom_prefix(tmp_path):
    """Test that RunIndexWriter.append() rejects manifest_hash with custom prefix."""
    index_dir = tmp_path / ".osiris" / "index"
    writer = RunIndexWriter(index_dir)

    # Create a record with custom prefixed hash
    record = RunRecord(
        run_id="test_run_002",
        pipeline_slug="test_pipeline",
        profile="dev",
        manifest_hash="custom:xyz789",  # Invalid: has algorithm prefix
        manifest_short="xyz789",
        run_ts="2025-10-08T10:00:00Z",
        status="success",
        duration_ms=1000,
        run_logs_path="/path/to/logs",
        aiop_path="/path/to/aiop",
        build_manifest_path="/path/to/manifest",
        tags=[],
    )

    # Should raise ValueError
    with pytest.raises(ValueError, match="manifest_hash must be pure hex"):
        writer.append(record)


def test_run_index_accepts_pure_hex(tmp_path):
    """Test that RunIndexWriter.append() accepts pure hex manifest_hash."""
    index_dir = tmp_path / ".osiris" / "index"
    writer = RunIndexWriter(index_dir)

    # Create a record with pure hex hash (no prefix)
    record = RunRecord(
        run_id="test_run_003",
        pipeline_slug="test_pipeline",
        profile="dev",
        manifest_hash="abc123def456",  # pragma: allowlist secret
        manifest_short="abc123d",
        run_ts="2025-10-08T10:00:00Z",
        status="success",
        duration_ms=1000,
        run_logs_path="/path/to/logs",
        aiop_path="/path/to/aiop",
        build_manifest_path="/path/to/manifest",
        tags=[],
    )

    # Should not raise any exception
    writer.append(record)

    # Verify it was written
    runs_jsonl = index_dir / "runs.jsonl"
    assert runs_jsonl.exists()

    # Verify content
    import json

    with open(runs_jsonl) as f:
        line = f.readline()
        data = json.loads(line)
        assert data["manifest_hash"] == "abc123def456"  # pragma: allowlist secret
        assert data["run_id"] == "test_run_003"


def test_run_index_accepts_64_char_hex(tmp_path):
    """Test that RunIndexWriter accepts full 64-character SHA-256 hex hash."""
    index_dir = tmp_path / ".osiris" / "index"
    writer = RunIndexWriter(index_dir)

    # Full SHA-256 hash (64 hex characters)
    full_hash = "a" * 64

    record = RunRecord(
        run_id="test_run_004",
        pipeline_slug="test_pipeline",
        profile="dev",
        manifest_hash=full_hash,  # Valid: pure hex
        manifest_short=full_hash[:7],
        run_ts="2025-10-08T10:00:00Z",
        status="success",
        duration_ms=1000,
        run_logs_path="/path/to/logs",
        aiop_path="/path/to/aiop",
        build_manifest_path="/path/to/manifest",
        tags=[],
    )

    # Should not raise any exception
    writer.append(record)

    # Verify it was written correctly
    runs_jsonl = index_dir / "runs.jsonl"
    import json

    with open(runs_jsonl) as f:
        line = f.readline()
        data = json.loads(line)
        assert data["manifest_hash"] == full_hash
        assert len(data["manifest_hash"]) == 64


def test_run_index_empty_hash_allowed(tmp_path):
    """Test that RunIndexWriter allows empty manifest_hash (edge case)."""
    index_dir = tmp_path / ".osiris" / "index"
    writer = RunIndexWriter(index_dir)

    record = RunRecord(
        run_id="test_run_005",
        pipeline_slug="test_pipeline",
        profile="dev",
        manifest_hash="",  # Empty hash (edge case)
        manifest_short="",
        run_ts="2025-10-08T10:00:00Z",
        status="success",
        duration_ms=1000,
        run_logs_path="/path/to/logs",
        aiop_path="/path/to/aiop",
        build_manifest_path="/path/to/manifest",
        tags=[],
    )

    # Should not raise (empty string has no colon)
    writer.append(record)


def test_run_index_colon_in_middle_rejected(tmp_path):
    """Test that manifest_hash with colon anywhere is rejected (not just as prefix)."""
    index_dir = tmp_path / ".osiris" / "index"
    writer = RunIndexWriter(index_dir)

    record = RunRecord(
        run_id="test_run_006",
        pipeline_slug="test_pipeline",
        profile="dev",
        manifest_hash="abc:def:123",  # Invalid: contains colons
        manifest_short="abc",
        run_ts="2025-10-08T10:00:00Z",
        status="success",
        duration_ms=1000,
        run_logs_path="/path/to/logs",
        aiop_path="/path/to/aiop",
        build_manifest_path="/path/to/manifest",
        tags=[],
    )

    # Should raise ValueError
    with pytest.raises(ValueError, match="manifest_hash must be pure hex"):
        writer.append(record)
