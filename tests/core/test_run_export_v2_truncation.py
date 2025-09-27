"""Tests for run_export_v2 truncation functionality."""

from osiris.core.run_export_v2 import apply_truncation, canonicalize_json


def test_truncation_markers_present():
    """Test that truncation adds correct markers at object level."""
    # Create large data that exceeds limit - structure matches AIOP with evidence layer
    large_timeline = [{"event": f"event_{i}", "data": "x" * 100} for i in range(1000)]

    large_metrics = {
        "total_rows": 12345,
        "total_duration_ms": 5000,
        "steps": {f"step_{i}": {"rows_read": i, "duration_ms": i * 10} for i in range(500)},
    }

    large_artifacts = [{"name": f"file_{i}.csv", "content": "data" * 100} for i in range(100)]

    data = {
        "evidence": {
            "timeline": large_timeline,
            "metrics": large_metrics,
            "artifacts": large_artifacts,
        },
        "metadata": {"test": "value"},
    }

    # Apply truncation with small limit
    result, was_truncated = apply_truncation(data, max_bytes=1024)

    assert was_truncated is True

    # Check timeline becomes object with markers
    assert isinstance(result["evidence"]["timeline"], dict)
    assert result["evidence"]["timeline"]["truncated"] is True
    assert "dropped_events" in result["evidence"]["timeline"]
    assert result["evidence"]["timeline"]["dropped_events"] > 0
    assert "items" in result["evidence"]["timeline"]
    assert isinstance(result["evidence"]["timeline"]["items"], list)

    # Check metrics gets truncation markers
    assert result["evidence"]["metrics"]["truncated"] is True
    assert result["evidence"]["metrics"]["aggregates_only"] is True
    # Aggregates should be preserved
    assert result["evidence"]["metrics"]["total_rows"] == 12345
    assert result["evidence"]["metrics"]["total_duration_ms"] == 5000

    # Check artifacts becomes object with markers
    assert isinstance(result["evidence"]["artifacts"], dict)
    assert result["evidence"]["artifacts"]["truncated"] is True
    assert result["evidence"]["artifacts"]["content_omitted"] is True
    assert "files" in result["evidence"]["artifacts"]

    # Metadata should be preserved
    assert result["metadata"]["test"] == "value"


def test_truncation_determinism():
    """Test that truncation produces identical output for same input."""
    # Create test data
    import copy

    data = {
        "evidence": {
            "timeline": [{"id": i, "data": f"event_{i}" * 10} for i in range(200)],
            "metrics": {
                "total_rows": 7425,
                "total_duration_ms": 1500,
                "steps": {f"step_{i}": {"rows_read": i * 1.5} for i in range(100)},
            },
        }
    }

    # Apply truncation multiple times
    result1, _ = apply_truncation(copy.deepcopy(data), max_bytes=2048)
    result2, _ = apply_truncation(copy.deepcopy(data), max_bytes=2048)

    # Results should be identical (deterministic)
    json1 = canonicalize_json(result1)
    json2 = canonicalize_json(result2)
    assert json1 == json2


def test_truncation_respects_limit():
    """Test that truncated output respects max_bytes limit."""
    # Create very large data
    data = {
        "evidence": {
            "timeline": [{"event": f"e{i}", "payload": "x" * 1000} for i in range(500)],
            "metrics": {
                "total_rows": 1249750,
                "total_duration_ms": 25000,
                "steps": {f"step_{i}": {"rows_read": i * 2.5} for i in range(1000)},
            },
        }
    }

    max_bytes = 10 * 1024  # 10KB limit
    result, was_truncated = apply_truncation(data, max_bytes=max_bytes)

    assert was_truncated is True

    # Serialize and check size
    serialized = canonicalize_json(result)
    actual_bytes = len(serialized.encode("utf-8"))
    assert actual_bytes <= max_bytes, f"Size {actual_bytes} exceeds limit {max_bytes}"


def test_truncation_small_data_unchanged():
    """Test that small data below limit is not truncated."""
    data = {
        "evidence": {
            "timeline": [{"id": 1}, {"id": 2}],
            "metrics": {"total_rows": 2, "total_duration_ms": 100},
            "artifacts": ["a.txt", "b.txt"],
        }
    }

    result, was_truncated = apply_truncation(data, max_bytes=100 * 1024)

    assert was_truncated is False
    assert result == data  # Should be unchanged
    # Timeline should still be a list, not converted to object
    assert isinstance(result["evidence"]["timeline"], list)
    # Metrics should not have truncation markers
    assert "truncated" not in result["evidence"]["metrics"]
    # Artifacts should still be a list
    assert isinstance(result["evidence"]["artifacts"], list)


def test_truncation_first_last_strategy():
    """Test that timeline truncation keeps appropriate first K and last K events."""
    # Create 500 events
    events = [{"id": i, "type": f"event_{i}"} for i in range(500)]
    data = {"evidence": {"timeline": events}}

    result, was_truncated = apply_truncation(data, max_bytes=5 * 1024)

    if was_truncated and isinstance(result["evidence"]["timeline"], dict):
        timeline_obj = result["evidence"]["timeline"]
        assert "items" in timeline_obj
        kept_events = timeline_obj["items"]
        # Should keep first and last portions based on ratio
        # With 500 events and 5KB limit, likely keeps first 20 and last 20
        assert len(kept_events) < len(events)
        # Check we have first events
        if len(kept_events) >= 2:
            assert kept_events[0]["id"] == 0
            # Check we have last event
            assert kept_events[-1]["id"] == 499


def test_truncation_preserves_jsonld_shape():
    """Test that truncation never breaks JSON-LD structure."""
    data = {
        "@context": "https://osiris.io/schemas/aiop/v1",
        "@type": "AIOPRun",
        "evidence": {"timeline": [{"e": i} for i in range(1000)]},
        "metadata": {"@type": "Metadata", "version": "1.0"},
    }

    result, _ = apply_truncation(data, max_bytes=1024)

    # JSON-LD fields should be preserved
    assert "@context" in result
    assert "@type" in result
    assert result["@context"] == "https://osiris.io/schemas/aiop/v1"
    assert result["@type"] == "AIOPRun"

    # Nested @type should be preserved
    if "metadata" in result:
        assert result["metadata"].get("@type") == "Metadata"


def test_apply_truncation_object_markers():
    """Test that apply_truncation creates proper object-level markers."""
    from osiris.core.run_export_v2 import apply_truncation

    # Create large data structure
    big_data = {
        "evidence": {
            "timeline": [{"event": f"event_{i}", "data": "x" * 200} for i in range(2000)],
            "metrics": {
                "total_rows": 100000,
                "total_duration_ms": 50000,
                "steps": {f"step_{i}": {"rows_read": i * 100} for i in range(500)},
            },
            "artifacts": [{"file": f"file_{i}.csv", "size": 1000 * i} for i in range(100)],
        }
    }

    # Apply truncation with small limit
    result, was_truncated = apply_truncation(big_data, max_bytes=5000)

    assert was_truncated is True

    # Timeline must be object with specific structure
    timeline = result["evidence"]["timeline"]
    assert isinstance(timeline, dict), "Timeline must be object when truncated"
    assert timeline["truncated"] is True
    assert isinstance(timeline["items"], list)
    assert "dropped_events" in timeline
    assert timeline["dropped_events"] > 0

    # Metrics must have truncation markers
    metrics = result["evidence"]["metrics"]
    assert metrics["truncated"] is True
    assert metrics["aggregates_only"] is True
    assert "dropped_series" in metrics
    assert metrics["total_rows"] == 100000  # Aggregates preserved
    assert metrics["total_duration_ms"] == 50000

    # Artifacts must be object when truncated
    artifacts = result["evidence"]["artifacts"]
    assert isinstance(artifacts, dict), "Artifacts must be object when truncated"
    assert artifacts["truncated"] is True
    assert artifacts["content_omitted"] is True
    assert isinstance(artifacts["files"], list)


def test_cli_exit_code_on_truncation():
    """Test that CLI returns exit code 4 when truncation occurs."""
    from osiris.core.run_export_v2 import build_aiop

    # Create data that will trigger truncation
    large_events = [{"event": f"e_{i}", "data": "x" * 500} for i in range(1000)]
    session_data = {
        "session_id": "test_123",
        "started_at": "2024-01-01T00:00:00Z",
        "completed_at": "2024-01-01T01:00:00Z",
        "status": "completed",
        "environment": "local",
    }

    manifest = {"name": "test_pipeline", "manifest_hash": "abc123", "steps": []}

    config = {
        "max_core_bytes": 1024,  # Very small limit to force truncation
        "timeline_density": "medium",
        "metrics_topk": 10,
    }

    # Build AIOP with truncation
    aiop = build_aiop(
        session_data=session_data,
        manifest=manifest,
        events=large_events,
        metrics=[],
        artifacts=[],
        config=config,
    )

    # Check that metadata.truncated is set to True
    assert aiop.get("metadata", {}).get("truncated") is True

    # Simulate CLI exit code logic
    exit_code = 4 if aiop.get("metadata", {}).get("truncated", False) else 0
    assert exit_code == 4
