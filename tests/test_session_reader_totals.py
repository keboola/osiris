#!/usr/bin/env python3
"""Unit tests for SessionReader row totals normalization."""

import json
from pathlib import Path
import tempfile

from osiris.core.session_reader import SessionReader


class TestSessionReaderTotals:
    """Test row counting logic without double counting."""

    def test_cleanup_total_takes_priority(self):
        """When cleanup_complete has total_rows, it should be the single source of truth."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / "test_session"
            session_dir.mkdir()

            # Create events with both step data and cleanup total
            events = [
                {"event": "step_start", "step_id": "extract-1", "driver": "mysql.extractor"},
                {"event": "step_complete", "step_id": "extract-1", "rows_processed": 100},
                {"event": "step_start", "step_id": "write-1", "driver": "supabase.writer"},
                {"event": "step_complete", "step_id": "write-1", "rows_processed": 100},
                {
                    "event": "write.complete",
                    "step_id": "write-1",
                    "rows_written": 100,
                },  # Should be ignored
                {"event": "cleanup_complete", "steps_executed": 2, "total_rows": 84},  # This wins
            ]

            events_file = session_dir / "events.jsonl"
            with open(events_file, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            # Create metrics that would normally add to the count
            metrics = [
                {"metric": "rows_written", "value": 100, "step_id": "write-1"},
            ]

            metrics_file = session_dir / "metrics.jsonl"
            with open(metrics_file, "w") as f:
                for metric in metrics:
                    f.write(json.dumps(metric) + "\n")

            reader = SessionReader(tmpdir)
            summary = reader.read_session("test_session")

            # Should use cleanup_complete total, not sum of events/metrics
            assert summary.rows_out == 84

    def test_no_double_counting_from_events_and_metrics(self):
        """Rows should not be counted twice from events and metrics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / "test_session"
            session_dir.mkdir()

            # Create events with write.complete
            events = [
                {"event": "step_start", "step_id": "write-data", "driver": "filesystem.csv_writer"},
                {
                    "event": "write.complete",
                    "step_id": "write-data",
                    "table": "output",
                    "rows_written": 50,
                },
                {"event": "step_complete", "step_id": "write-data"},
            ]

            events_file = session_dir / "events.jsonl"
            with open(events_file, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            # Create metrics with same rows
            metrics = [
                {"metric": "rows_written", "value": 50, "step_id": "write-data"},
            ]

            metrics_file = session_dir / "metrics.jsonl"
            with open(metrics_file, "w") as f:
                for metric in metrics:
                    f.write(json.dumps(metric) + "\n")

            reader = SessionReader(tmpdir)
            summary = reader.read_session("test_session")

            # Should be 50, not 100 (no double counting)
            assert summary.rows_out == 50

    def test_extract_only_pipeline_uses_extractor_rows(self):
        """Pipeline with only extractors should use extractor row count."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / "test_session"
            session_dir.mkdir()

            events = [
                {"event": "step_start", "step_id": "extract-1", "driver": "mysql.extractor"},
                {"event": "step_complete", "step_id": "extract-1", "rows_processed": 30},
                {"event": "step_start", "step_id": "extract-2", "driver": "postgres.extractor"},
                {"event": "step_complete", "step_id": "extract-2", "rows_processed": 20},
            ]

            events_file = session_dir / "events.jsonl"
            with open(events_file, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            reader = SessionReader(tmpdir)
            summary = reader.read_session("test_session")

            # Should use sum of extractors since no writers
            assert summary.rows_out == 50

    def test_writer_priority_over_extractors(self):
        """Pipeline with both should use writer rows only."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / "test_session"
            session_dir.mkdir()

            events = [
                {"event": "step_start", "step_id": "extract-data", "driver": "mysql.extractor"},
                {"event": "step_complete", "step_id": "extract-data"},
                {"event": "step_start", "step_id": "write-output", "driver": "supabase.writer"},
                {"event": "step_complete", "step_id": "write-output"},
            ]

            events_file = session_dir / "events.jsonl"
            with open(events_file, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            # Metrics with both extractors and writers
            metrics = [
                {"metric": "rows_read", "value": 100, "step_id": "extract-data"},
                {"metric": "rows_written", "value": 100, "step_id": "write-output"},
            ]

            metrics_file = session_dir / "metrics.jsonl"
            with open(metrics_file, "w") as f:
                for metric in metrics:
                    f.write(json.dumps(metric) + "\n")

            reader = SessionReader(tmpdir)
            summary = reader.read_session("test_session")

            # Should use writer rows only
            assert summary.rows_out == 100
            assert summary.rows_in == 100  # Extractors go to rows_in

    def test_multi_sink_pipeline_sums_all_writers(self):
        """Pipeline writing to multiple sinks should sum all writer rows."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / "test_session"
            session_dir.mkdir()

            events = [
                {"event": "step_start", "step_id": "extract-source", "driver": "mysql.extractor"},
                {"event": "step_complete", "step_id": "extract-source"},
                {"event": "step_start", "step_id": "write-csv", "driver": "filesystem.csv_writer"},
                {"event": "step_complete", "step_id": "write-csv"},
                {
                    "event": "step_start",
                    "step_id": "write-parquet",
                    "driver": "filesystem.parquet_writer",
                },
                {"event": "step_complete", "step_id": "write-parquet"},
                {"event": "step_start", "step_id": "write-db", "driver": "postgres.writer"},
                {"event": "step_complete", "step_id": "write-db"},
            ]

            events_file = session_dir / "events.jsonl"
            with open(events_file, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            metrics = [
                {"metric": "rows_read", "value": 100, "step_id": "extract-source"},
                {"metric": "rows_written", "value": 100, "step_id": "write-csv"},
                {"metric": "rows_written", "value": 100, "step_id": "write-parquet"},
                {"metric": "rows_written", "value": 100, "step_id": "write-db"},
            ]

            metrics_file = session_dir / "metrics.jsonl"
            with open(metrics_file, "w") as f:
                for metric in metrics:
                    f.write(json.dumps(metric) + "\n")

            reader = SessionReader(tmpdir)
            summary = reader.read_session("test_session")

            # Should sum all three writers
            assert summary.rows_out == 300
            assert summary.rows_in == 100  # Just the extractor

    def test_driver_classification_by_name(self):
        """Test driver classification logic."""
        reader = SessionReader()

        # Writers
        assert reader._is_writer_driver("supabase.writer") is True
        assert reader._is_writer_driver("filesystem.writer") is True
        assert reader._is_writer_driver("postgres.load") is True

        # Extractors
        assert reader._is_writer_driver("mysql.extractor") is False
        assert reader._is_writer_driver("api.extract") is False

        # Fallback to step_id when driver name doesn't match patterns
        assert reader._is_writer_driver("filesystem.csv", "write-output") is True
        assert reader._is_writer_driver("unknown", "load-data") is True
        assert reader._is_writer_driver("unknown", "extract-source") is False
        assert reader._is_writer_driver("unknown", "read-api") is False

        # Unknown defaults to extractor
        assert reader._is_writer_driver("", "transform-data") is False
        assert reader._is_writer_driver("transform.processor", "") is False
