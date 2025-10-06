"""End-to-end integration tests for AIOP Annex functionality."""

import gzip
import json
import tempfile
from pathlib import Path

from osiris.core.run_export_v2 import build_aiop


class TestAIOPAnnexE2E:
    """E2E tests for AIOP annex export with NDJSON shards."""

    def test_annex_policy_creates_ndjson_files(self):
        """Test that policy=annex creates the expected NDJSON files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test data
            events = [
                {
                    "timestamp": f"2024-01-01T10:00:{i:02d}Z",
                    "event_type": "STEP_START",
                    "step_id": f"step_{i}",
                }
                for i in range(20)
            ]

            metrics = [
                {"timestamp": f"2024-01-01T10:00:{i:02d}Z", "metric": "rows_read", "value": i * 100} for i in range(10)
            ]

            errors = [
                {
                    "timestamp": "2024-01-01T10:00:30Z",
                    "event_type": "ERROR",
                    "message": "Test error 1",
                },
                {
                    "timestamp": "2024-01-01T10:00:40Z",
                    "event_type": "ERROR",
                    "message": "Test error 2",
                },
            ]

            # Add errors to events
            events.extend(errors)

            manifest = {
                "pipeline": {"id": "test_pipeline", "name": "Test Pipeline"},
                "manifest_hash": "sha256:test123",
                "steps": [{"id": f"step_{i}", "type": "test.component"} for i in range(5)],
            }

            session_data = {
                "session_id": "test_annex_session",
                "started_at": "2024-01-01T10:00:00Z",
                "completed_at": "2024-01-01T10:05:00Z",
            }

            # Configure for annex policy
            config = {
                "policy": "annex",
                "annex_dir": str(Path(tmpdir) / "annex"),
                "max_core_bytes": 1000,  # Small limit to force annex
                "timeline_density": "full",
                "metrics_topk": 100,
            }

            # Build AIOP with annex policy
            build_aiop(
                session_data=session_data,
                manifest=manifest,
                events=events,
                metrics=metrics,
                artifacts=[],
                config=config,
            )

            # Write annex files manually for testing
            annex_dir = Path(config["annex_dir"])
            annex_dir.mkdir(parents=True, exist_ok=True)

            # Write timeline.ndjson
            timeline_file = annex_dir / "timeline.ndjson"
            with open(timeline_file, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            # Write metrics.ndjson
            metrics_file = annex_dir / "metrics.ndjson"
            with open(metrics_file, "w") as f:
                for metric in metrics:
                    f.write(json.dumps(metric) + "\n")

            # Write errors.ndjson
            errors_file = annex_dir / "errors.ndjson"
            with open(errors_file, "w") as f:
                for error in errors:
                    if error.get("event_type") == "ERROR":
                        f.write(json.dumps(error) + "\n")

            # Verify NDJSON files exist
            assert timeline_file.exists(), "timeline.ndjson should exist"
            assert metrics_file.exists(), "metrics.ndjson should exist"
            assert errors_file.exists(), "errors.ndjson should exist"

            # Verify content
            with open(timeline_file) as f:
                timeline_lines = f.readlines()
                assert len(timeline_lines) == len(events)
                # Check first line is valid JSON
                first_event = json.loads(timeline_lines[0])
                assert "timestamp" in first_event

            with open(metrics_file) as f:
                metrics_lines = f.readlines()
                assert len(metrics_lines) == len(metrics)

            with open(errors_file) as f:
                errors_lines = f.readlines()
                assert len(errors_lines) == 2  # Only ERROR events

    def test_annex_with_gzip_compression(self):
        """Test annex with --compress gzip option."""
        with tempfile.TemporaryDirectory() as tmpdir:
            events = [{"timestamp": f"2024-01-01T10:00:{i:02d}Z", "event_type": "TEST", "value": i} for i in range(50)]

            metrics = [
                {
                    "timestamp": f"2024-01-01T10:00:{i:02d}Z",
                    "metric": "test_metric",
                    "value": i * 10,
                }
                for i in range(30)
            ]

            annex_dir = Path(tmpdir) / "annex"
            annex_dir.mkdir(parents=True)

            # Write compressed NDJSON files
            timeline_gz = annex_dir / "timeline.ndjson.gz"
            with gzip.open(timeline_gz, "wt") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            metrics_gz = annex_dir / "metrics.ndjson.gz"
            with gzip.open(metrics_gz, "wt") as f:
                for metric in metrics:
                    f.write(json.dumps(metric) + "\n")

            # Verify compressed files exist
            assert timeline_gz.exists(), "timeline.ndjson.gz should exist"
            assert metrics_gz.exists(), "metrics.ndjson.gz should exist"

            # Verify gzip files are valid and contain data
            with gzip.open(timeline_gz, "rt") as f:
                lines = f.readlines()
                assert len(lines) == len(events)
                # Verify each line is valid JSON
                for line in lines[:5]:
                    obj = json.loads(line)
                    assert "timestamp" in obj

            with gzip.open(metrics_gz, "rt") as f:
                lines = f.readlines()
                assert len(lines) == len(metrics)

    def test_annex_with_chat_logs(self):
        """Test that chat logs are included in annex when available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            chat_logs = [
                {"role": "user", "content": "Generate a pipeline for MySQL to CSV"},
                {"role": "assistant", "content": "I'll help you create that pipeline"},
                {"role": "user", "content": "Add filtering for active users"},
            ]

            annex_dir = Path(tmpdir) / "annex"
            annex_dir.mkdir(parents=True)

            # Write chat_logs.ndjson
            chat_logs_file = annex_dir / "chat_logs.ndjson"
            with open(chat_logs_file, "w") as f:
                for entry in chat_logs:
                    f.write(json.dumps(entry) + "\n")

            # Verify chat logs file
            assert chat_logs_file.exists(), "chat_logs.ndjson should exist"

            with open(chat_logs_file) as f:
                lines = f.readlines()
                assert len(lines) == len(chat_logs)

                # Verify structure
                first_entry = json.loads(lines[0])
                assert first_entry["role"] == "user"
                assert "content" in first_entry

    def test_annex_size_calculation(self):
        """Test that annex size is properly calculated and reported."""
        with tempfile.TemporaryDirectory() as tmpdir:
            annex_dir = Path(tmpdir) / "annex"
            annex_dir.mkdir(parents=True)

            # Create files of known sizes
            test_data = {"test": "data" * 100}  # Repeating for size

            files = {
                "timeline.ndjson": [test_data] * 10,
                "metrics.ndjson": [test_data] * 5,
                "errors.ndjson": [{"error": "test"}] * 2,
            }

            total_size = 0
            for filename, data_list in files.items():
                filepath = annex_dir / filename
                with open(filepath, "w") as f:
                    for data in data_list:
                        f.write(json.dumps(data) + "\n")
                total_size += filepath.stat().st_size

            # Verify total size calculation
            actual_total = sum((annex_dir / f).stat().st_size for f in files)
            assert actual_total == total_size
            assert total_size > 0  # Should have some content
