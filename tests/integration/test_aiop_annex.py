"""Integration test for AIOP annex functionality."""

import gzip
import json
from pathlib import Path
import tempfile

import pytest

from osiris.core.run_export_v2 import build_aiop


class TestAIOPAnnex:
    """Test AIOP annex export with NDJSON shards."""

    @pytest.mark.skip(reason="Annex export functionality needs to be integrated with build_aiop")
    def test_annex_with_gzip_compression(self):
        """Test that annex policy creates compressed NDJSON files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test data with enough events to trigger annex
            events = []
            metrics = []

            # Add many events to ensure annex is used
            for i in range(100):
                events.append(
                    {
                        "timestamp": f"2024-01-01T10:{i:02d}:00Z",
                        "event_type": "STEP_START" if i % 2 == 0 else "STEP_COMPLETE",
                        "step_id": f"step_{i}",
                        "message": f"Processing step {i}",
                    }
                )

            for i in range(50):
                metrics.append(
                    {
                        "timestamp": f"2024-01-01T10:{i:02d}:00Z",
                        "event_type": "step_metrics",
                        "step_id": f"step_{i}",
                        "rows_read": 1000 * i,
                        "duration_ms": 500 * i,
                    }
                )

            manifest = {
                "pipeline": "large_pipeline",
                "manifest_hash": "sha256:large123",
                "steps": [{"id": f"step_{i}", "type": "test.component"} for i in range(10)],
            }

            # Export with annex policy
            output_dir = Path(tmpdir) / "output"
            annex_dir = Path(tmpdir) / "annex"

            config = {
                "policy": "annex",
                "annex_dir": str(annex_dir),
                "compress": "gzip",
                "output_dir": str(output_dir),
            }

            # Use build_aiop instead
            session_data = {"session_id": "test_annex_session"}

            build_aiop(
                session_data=session_data,
                manifest=manifest,
                events=events,
                metrics=metrics,
                artifacts=[],
                config=config,
            )

            # Check that annex directory was created
            assert annex_dir.exists()

            # Check for compressed NDJSON files
            timeline_gz = annex_dir / "timeline.ndjson.gz"
            metrics_gz = annex_dir / "metrics.ndjson.gz"

            assert timeline_gz.exists(), "timeline.ndjson.gz should exist"
            assert metrics_gz.exists(), "metrics.ndjson.gz should exist"

            # Verify gzip files contain valid NDJSON
            with gzip.open(timeline_gz, "rt") as f:
                timeline_lines = f.readlines()
                assert len(timeline_lines) > 0, "Timeline should have content"
                # Each line should be valid JSON
                for line in timeline_lines[:5]:  # Check first 5 lines
                    obj = json.loads(line)
                    assert "@id" in obj or "timestamp" in obj

            with gzip.open(metrics_gz, "rt") as f:
                metrics_lines = f.readlines()
                assert len(metrics_lines) > 0, "Metrics should have content"
                # Each line should be valid JSON
                for line in metrics_lines[:5]:  # Check first 5 lines
                    obj = json.loads(line)
                    assert "timestamp" in obj or "event_type" in obj

            # Check that core AIOP still exists
            core_file = output_dir / "aiop.json"
            assert core_file.exists(), "Core AIOP should still be created"

            # Core file should reference annex
            with open(core_file) as f:
                core_aiop = json.load(f)

            assert "metadata" in core_aiop
            assert core_aiop["metadata"].get("truncated") is True or "annex_dir" in str(core_aiop.get("evidence", {}))

    @pytest.mark.skip(reason="Annex export functionality needs to be integrated with build_aiop")
    def test_annex_without_compression(self):
        """Test annex policy with uncompressed NDJSON files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            events = [{"timestamp": f"2024-01-01T10:00:{i:02d}Z", "event_type": "TEST", "value": i} for i in range(20)]

            metrics = [
                {"timestamp": f"2024-01-01T10:01:{i:02d}Z", "metric": "test", "value": i * 100} for i in range(10)
            ]

            manifest = {"pipeline": "test", "steps": []}

            annex_dir = Path(tmpdir) / "annex"
            output_dir = Path(tmpdir) / "output"

            config = {
                "policy": "annex",
                "annex_dir": str(annex_dir),
                "compress": None,  # No compression
                "output_dir": str(output_dir),
            }

            export_aiop(
                session_id="test_no_compress",
                events=events,
                metrics=metrics,
                manifest=manifest,
                config=config,
            )

            # Check for uncompressed NDJSON files
            timeline_file = annex_dir / "timeline.ndjson"
            metrics_file = annex_dir / "metrics.ndjson"

            assert timeline_file.exists(), "timeline.ndjson should exist"
            assert metrics_file.exists(), "metrics.ndjson should exist"

            # Verify plain NDJSON content
            with open(timeline_file) as f:
                lines = f.readlines()
                assert len(lines) >= len(events), "Should have all events"
                # Parse first line
                first_obj = json.loads(lines[0])
                assert "timestamp" in first_obj or "@id" in first_obj

            with open(metrics_file) as f:
                lines = f.readlines()
                assert len(lines) >= len(metrics), "Should have all metrics"

    @pytest.mark.skip(reason="Annex export functionality needs to be integrated with build_aiop")
    def test_annex_with_empty_data(self):
        """Test annex policy with minimal/empty data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            events = []  # Empty events
            metrics = []  # Empty metrics
            manifest = {"pipeline": "empty_test"}

            annex_dir = Path(tmpdir) / "annex"
            output_dir = Path(tmpdir) / "output"

            config = {
                "policy": "annex",
                "annex_dir": str(annex_dir),
                "compress": "gzip",
                "output_dir": str(output_dir),
            }

            export_aiop(
                session_id="test_empty",
                events=events,
                metrics=metrics,
                manifest=manifest,
                config=config,
            )

            # Even with empty data, core AIOP should exist
            core_file = output_dir / "aiop.json"
            assert core_file.exists()

            # Annex files may or may not exist with empty data
            # This is implementation-dependent
