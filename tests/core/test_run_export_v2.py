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

"""Tests for run_export_v2 (PR2 - Evidence Layer functions only)."""

import json
import tempfile
from pathlib import Path


class TestRunExportV2:
    """Test PR2 Evidence Layer functions."""

    def test_evidence_id_generation(self):
        """Test evidence ID generation follows correct format."""
        from osiris.core.run_export_v2 import generate_evidence_id

        # Test ID generation with step
        evidence_id = generate_evidence_id("event", "step_1", "complete", 1234567890)

        assert evidence_id == "ev.event.complete.step_1.1234567890"

        # Test run-level event (no step_id)
        evidence_id = generate_evidence_id("event", "", "start", 1234567890)

        assert evidence_id == "ev.event.start.run.1234567890"

        # Test sanitization
        evidence_id = generate_evidence_id("Error-Type", "Step-123", "Failed!", 1234567890)

        assert evidence_id == "ev.error_type.failed.step_123.1234567890"

    def test_timeline_chronological_ordering(self):
        """Test timeline events are sorted chronologically."""
        from osiris.core.run_export_v2 import build_timeline

        # Create unordered events
        events = [
            {"event": "step_complete", "step_id": "step_3", "ts": "2024-01-15T10:03:00Z"},
            {"event": "step_start", "step_id": "step_1", "ts": "2024-01-15T10:01:00Z"},
            {"event": "step_complete", "step_id": "step_2", "ts": "2024-01-15T10:02:00Z"},
        ]

        timeline = build_timeline(events, "high")

        # Verify chronological order and structure
        assert len(timeline) == 3
        assert timeline[0]["type"] == "STEP_START"
        assert timeline[0]["step_id"] == "step_1"
        assert timeline[1]["type"] == "STEP_COMPLETE"
        assert timeline[2]["type"] == "STEP_COMPLETE"

        # Verify @id format
        assert timeline[0]["@id"].startswith("ev.event.step_start.step_1.")
        assert "@id" in timeline[0]
        assert "ts" in timeline[0]

    def test_metrics_aggregation_and_topk(self):
        """Test metrics aggregation returns correct shape."""
        from osiris.core.run_export_v2 import aggregate_metrics

        # Create metrics
        metrics = [
            {"metric": "rows_read", "step_id": "extract", "value": 100},
            {"metric": "rows_read", "step_id": "extract", "value": 200},  # Should be summed
            {"metric": "rows_written", "step_id": "load", "value": 250},
            {"metric": "duration_ms", "step_id": "extract", "value": 1500},
            {"metric": "duration_ms", "step_id": "load", "value": 500},
        ]

        aggregated = aggregate_metrics(metrics, topk=3)

        # Verify structure
        assert "total_rows" in aggregated
        assert "total_duration_ms" in aggregated
        assert "steps" in aggregated

        # Verify totals - should use last writer
        assert aggregated["total_rows"] == 250  # Last writer (priority logic)
        assert aggregated["total_duration_ms"] == 2000  # 1500 + 500

        # Verify steps structure
        assert "extract" in aggregated["steps"]
        assert aggregated["steps"]["extract"]["rows_read"] == 300
        assert aggregated["steps"]["extract"]["duration_ms"] == 1500
        assert "load" in aggregated["steps"]
        assert aggregated["steps"]["load"]["rows_written"] == 250

    def test_deterministic_json_canonicalization(self):
        """Test JSON output is deterministic."""
        from osiris.core.run_export_v2 import canonicalize_json

        # Create data with unsorted keys
        data = {
            "z_field": "last",
            "a_field": "first",
            "m_field": "middle",
            "nested": {"z": 1, "a": 2},
        }

        json_str1 = canonicalize_json(data)
        json_str2 = canonicalize_json(data)

        # Verify deterministic output
        assert json_str1 == json_str2

        # Verify keys are sorted
        parsed = json.loads(json_str1)
        keys = list(parsed.keys())
        assert keys == ["a_field", "m_field", "nested", "z_field"]

    def test_truncation_with_markers(self):
        """Test truncation applies object-level markers."""
        from osiris.core.run_export_v2 import apply_truncation

        # Create large data structure - use AIOP structure with evidence layer
        data = {
            "evidence": {
                "timeline": [
                    {"@id": f"ev.event.test.run.{i}", "type": "DEBUG", "data": "x" * 100}
                    for i in range(300)
                ],
                "metrics": {
                    "total_rows": 1000,
                    "total_duration_ms": 5000,
                    "steps": {f"step_{i}": {"rows_read": i * 10} for i in range(50)},
                },
            }
        }

        # Apply truncation with small limit
        truncated_data, was_truncated = apply_truncation(data, max_bytes=10000)

        assert was_truncated is True

        # Check timeline truncation markers
        if isinstance(truncated_data["evidence"]["timeline"], dict):
            assert truncated_data["evidence"]["timeline"]["truncated"] is True
            assert "dropped_events" in truncated_data["evidence"]["timeline"]
            assert truncated_data["evidence"]["timeline"]["dropped_events"] > 0
            assert "items" in truncated_data["evidence"]["timeline"]

        # Check metrics truncation markers if applied
        if "truncated" in truncated_data["evidence"]["metrics"]:
            assert "dropped_series" in truncated_data["evidence"]["metrics"]

    def test_error_extraction(self):
        """Test error events are properly extracted from evidence layer."""
        from osiris.core.run_export_v2 import build_evidence_layer

        events = [
            {"event": "step_complete", "ts": "2024-01-15T10:01:00Z"},
            {"event": "error", "ts": "2024-01-15T10:02:00Z", "error": "Connection failed"},
            {
                "event": "step_error",
                "step_id": "extract",
                "ts": "2024-01-15T10:03:00Z",
                "msg": "Timeout",
            },
            {"level": "ERROR", "ts": "2024-01-15T10:04:00Z", "msg": "Critical error"},
        ]

        evidence = build_evidence_layer(events, [], [])
        errors = evidence["errors"]

        assert len(errors) == 3
        assert errors[0]["message"] == "Connection failed"
        assert errors[1]["message"] == "Timeout"
        assert errors[2]["message"] == "Critical error"

        # Check @id format
        assert all("@id" in error for error in errors)
        assert errors[0]["@id"].startswith("ev.event.error.")

    def test_artifact_listing(self):
        """Test artifact listing in evidence layer."""
        from osiris.core.run_export_v2 import build_evidence_layer

        with tempfile.TemporaryDirectory() as tmp_dir:
            artifacts_dir = Path(tmp_dir) / "artifacts"
            artifacts_dir.mkdir(parents=True)

            # Create sample artifacts
            output_csv = artifacts_dir / "output.csv"
            report_pdf = artifacts_dir / "report.pdf"
            output_csv.write_text("data")
            report_pdf.write_bytes(b"binary")

            # Build evidence layer with artifacts
            evidence = build_evidence_layer([], [], [output_csv, report_pdf])
            artifacts = evidence["artifacts"]

            assert len(artifacts) == 2

            # Check structure
            csv_artifact = next(a for a in artifacts if "output.csv" in a["path"])
            assert "@id" in csv_artifact
            assert "content_hash" in csv_artifact
            assert csv_artifact["content_hash"].startswith("sha256:")
            assert csv_artifact["size_bytes"] == 4  # "data" is 4 bytes

    def test_timeline_density_filtering(self):
        """Test timeline density affects event filtering."""
        from osiris.core.run_export_v2 import build_timeline

        # Create events with various types
        events = [
            {"event": "run_start", "ts": "2024-01-15T10:00:00Z"},
            {"event": "debug", "ts": "2024-01-15T10:01:00Z"},
            {"event": "step_complete", "step_id": "extract", "ts": "2024-01-15T10:02:00Z"},
            {"event": "trace", "ts": "2024-01-15T10:03:00Z"},
            {"event": "error", "ts": "2024-01-15T10:04:00Z"},
            {"event": "run_complete", "ts": "2024-01-15T10:05:00Z"},
        ]

        # Low density - only major events
        timeline_low = build_timeline(events, "low")
        assert len(timeline_low) == 4  # START, STEP_COMPLETE, ERROR, COMPLETE
        assert all(
            e["type"] in ["START", "STEP_COMPLETE", "ERROR", "COMPLETE"] for e in timeline_low
        )

        # Medium density - filter verbose
        timeline_medium = build_timeline(events, "medium")
        assert len(timeline_medium) == 4  # No DEBUG/TRACE
        assert all(e["type"] not in ["DEBUG", "TRACE"] for e in timeline_medium)

        # High density - all events
        timeline_high = build_timeline(events, "high")
        assert len(timeline_high) == 6  # All events

        # Verify no unknown types
        for timeline in [timeline_low, timeline_medium, timeline_high]:
            assert all("unknown" not in e["@id"] for e in timeline)

    def test_evidence_layer_structure(self):
        """Test evidence layer returns correct keys."""
        from osiris.core.run_export_v2 import build_evidence_layer

        events = [
            {"event": "run_start", "ts": "2024-01-15T10:00:00Z"},
            {"event": "step_complete", "step_id": "extract", "ts": "2024-01-15T10:01:00Z"},
        ]
        metrics = [
            {"metric": "rows_read", "step_id": "extract", "value": 100},
        ]

        evidence = build_evidence_layer(events, metrics, [])

        # Verify top-level keys
        assert "timeline" in evidence  # NOT "events"
        assert "metrics" in evidence
        assert "artifacts" in evidence
        assert "errors" in evidence

        # Verify timeline structure
        assert isinstance(evidence["timeline"], list)
        assert len(evidence["timeline"]) > 0
        assert all("@id" in item for item in evidence["timeline"])
        assert all(item["@id"].startswith("ev.event.") for item in evidence["timeline"])

        # Verify metrics has steps key
        assert "steps" in evidence["metrics"]

    def test_timeline_density_and_typing_exact(self):
        """Test A: Timeline density & typing with exact input."""
        from osiris.core.run_export_v2 import build_timeline

        # Exact input from reviewer
        events = [
            {
                "ts": "2024-01-15T10:00:05Z",
                "type": "METRICS",
                "step_id": "extract",
                "metrics": {"rows_read": 1000},
            },
            {"ts": "2024-01-15T10:00:01Z", "type": "STEP_START", "step_id": "extract"},
            {"ts": "2024-01-15T10:00:06Z", "type": "STEP_COMPLETE", "step_id": "extract"},
            {"ts": "2024-01-15T10:00:00Z", "type": "START", "session": "run_123"},
            {"ts": "2024-01-15T10:05:00Z", "type": "COMPLETE", "total_rows": 1000},
        ]

        # Low density test
        timeline_low = build_timeline(events, "low")
        low_types = [e["type"] for e in timeline_low]
        assert low_types == ["START", "STEP_START", "STEP_COMPLETE", "COMPLETE"]

        # Medium density test
        timeline_medium = build_timeline(events, "medium")
        medium_types = [e["type"] for e in timeline_medium]
        assert medium_types == ["START", "STEP_START", "METRICS", "STEP_COMPLETE", "COMPLETE"]

        # High density test
        timeline_high = build_timeline(events, "high")
        high_types = [e["type"] for e in timeline_high]
        assert high_types == ["START", "STEP_START", "METRICS", "STEP_COMPLETE", "COMPLETE"]

        # No unknown types
        for timeline in [timeline_low, timeline_medium, timeline_high]:
            assert all("unknown" not in e["type"].lower() for e in timeline)

    def test_metrics_aggregation_and_totals_exact(self):
        """Test B: Metrics aggregation & totals with exact input."""
        from osiris.core.run_export_v2 import aggregate_metrics

        # Exact input from reviewer
        metrics = [
            {"step_id": "extract", "rows_read": 10234, "duration_ms": 5000},
            {"step_id": "transform", "rows_out": 10234, "duration_ms": 180000},
            {"step_id": "export", "rows_written": 10234, "duration_ms": 120000},
        ]

        # Test topk=2
        result_2 = aggregate_metrics(metrics, topk=2)
        assert "steps" in result_2
        assert len(result_2["steps"]) == 2  # Exactly 2 steps

        # Test topk=3
        result_3 = aggregate_metrics(metrics, topk=3)
        assert result_3["total_rows"] is not None
        assert result_3["total_rows"] == 10234  # Export step (priority logic)
        assert result_3["total_duration_ms"] is not None
        assert result_3["total_duration_ms"] == 305000  # 5000 + 180000 + 120000

    def test_truncation_markers_exact(self):
        """Test C: Truncation markers with exact input."""

        from osiris.core.run_export_v2 import apply_truncation

        # Exact input from reviewer - wrap in evidence layer
        big = {
            "evidence": {
                "timeline": [
                    {"ts": f"2024-01-01T00:00:{i:02d}Z", "type": "DEBUG", "i": i}
                    for i in range(50000)
                ],
                "metrics": {
                    "total_rows": 50000,
                    "total_duration_ms": 100000,
                    "steps": {f"step_{i}": {"rows_read": i} for i in range(1000)},
                },
            }
        }

        cropped, did = apply_truncation(big, max_bytes=100_000)

        # Assertions
        assert did is True

        # Check object-level markers

        # Timeline markers
        if isinstance(cropped["evidence"].get("timeline"), dict):
            assert cropped["evidence"]["timeline"]["truncated"] is True
            assert "dropped_events" in cropped["evidence"]["timeline"]

        # Metrics markers (if truncated)
        if "truncated" in cropped["evidence"].get("metrics", {}):
            assert cropped["evidence"]["metrics"]["truncated"] is True
            assert "dropped_series" in cropped["evidence"]["metrics"]

    def test_evidence_layer_shape_exact(self):
        """Test D: Evidence layer shape with exact input."""
        from osiris.core.run_export_v2 import build_evidence_layer

        # Exact input from reviewer
        events = [
            {"ts": "2024-01-15T10:00:00Z", "type": "START", "session": "run_123"},
            {"ts": "2024-01-15T10:00:01Z", "type": "STEP_START", "step_id": "extract"},
            {
                "ts": "2024-01-15T10:00:05Z",
                "type": "METRICS",
                "step_id": "extract",
                "metrics": {"rows_read": 1000},
            },
            {"ts": "2024-01-15T10:00:06Z", "type": "STEP_COMPLETE", "step_id": "extract"},
            {"ts": "2024-01-15T10:05:00Z", "type": "COMPLETE", "total_rows": 1000},
        ]
        metrics = [{"step_id": "extract", "rows_read": 1000, "duration_ms": 6000}]
        artifacts = []

        e = build_evidence_layer(events, metrics, artifacts, max_bytes=300_000)

        # Top-level keys
        assert set(e.keys()) >= {"timeline", "metrics", "errors", "artifacts"}

        # Timeline checks
        assert len(e["timeline"]) == 5
        timeline_types = [event["type"] for event in e["timeline"]]
        assert timeline_types == ["START", "STEP_START", "METRICS", "STEP_COMPLETE", "COMPLETE"]

        # Metrics checks
        assert "steps" in e["metrics"]
        assert e["metrics"]["steps"]["extract"]["rows_read"] == 1000
        assert e["metrics"]["steps"]["extract"]["duration_ms"] == 6000

        # All timeline events have correct @id format
        for event in e["timeline"]:
            assert "@id" in event
            assert event["@id"].startswith("ev.event.")
            # Check format: ev.event.<type>.<step_or_run>.<ts_ms>
            parts = event["@id"].split(".")
            assert len(parts) == 5  # ev, event, type, step_or_run, ts_ms
            assert parts[0] == "ev"
            assert parts[1] == "event"
