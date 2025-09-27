"""Tests for AIOP metrics duration calculations."""

from osiris.core.run_export_v2 import aggregate_metrics


class TestMetricsDuration:
    """Test duration metrics calculation."""

    def test_active_duration_calculated(self):
        """Test that active_duration_ms is calculated from step durations."""
        events = []

        metrics = [
            {
                "timestamp": "2024-01-01T10:00:00Z",
                "event_type": "step_metrics",
                "step_id": "extract_users",
                "component": "mysql.extractor",
                "duration_ms": 1200,
                "rows_read": 500,
            },
            {
                "timestamp": "2024-01-01T10:00:01Z",
                "event_type": "step_metrics",
                "step_id": "transform_data",
                "component": "transform.filter",
                "duration_ms": 800,
                "rows_processed": 450,
            },
            {
                "timestamp": "2024-01-01T10:00:02Z",
                "event_type": "step_metrics",
                "step_id": "write_output",
                "component": "filesystem.csv_writer",
                "duration_ms": 500,
                "rows_written": 450,
            },
        ]

        result = aggregate_metrics(metrics, topk=100, events=events)

        # Wall time (total duration) should be present
        assert "total_duration_ms" in result
        assert result["total_duration_ms"] > 0

        # Active duration should be the sum of step durations
        assert "active_duration_ms" in result
        assert result["active_duration_ms"] == 1200 + 800 + 500  # 2500ms

        # Active duration should be <= wall time
        assert result["active_duration_ms"] <= result["total_duration_ms"]

    def test_active_duration_from_step_events(self):
        """Test active duration calculated from STEP_START/STEP_COMPLETE events."""
        events = [
            {
                "timestamp": "2024-01-01T10:00:00.000Z",
                "event_type": "RUN_START",
                "session_id": "s1",
            },
            {
                "timestamp": "2024-01-01T10:00:01.000Z",
                "event_type": "STEP_START",
                "step_id": "extract",
                "component": "mysql.extractor",
            },
            {
                "timestamp": "2024-01-01T10:00:02.500Z",
                "event_type": "STEP_COMPLETE",
                "step_id": "extract",
                "component": "mysql.extractor",
                "status": "success",
            },
            {
                "timestamp": "2024-01-01T10:00:03.000Z",
                "event_type": "STEP_START",
                "step_id": "write",
                "component": "csv.writer",
            },
            {
                "timestamp": "2024-01-01T10:00:04.200Z",
                "event_type": "STEP_COMPLETE",
                "step_id": "write",
                "component": "csv.writer",
                "status": "success",
            },
            {
                "timestamp": "2024-01-01T10:00:05.000Z",
                "event_type": "RUN_COMPLETE",
                "status": "success",
            },
        ]

        metrics = []  # No explicit metrics, calculate from events

        result = aggregate_metrics(metrics, topk=100, events=events)

        # Should calculate step durations from START/COMPLETE pairs
        # extract: 2.5s - 1s = 1.5s = 1500ms
        # write: 4.2s - 3s = 1.2s = 1200ms
        # total active: 2700ms
        assert "active_duration_ms" in result
        assert result["active_duration_ms"] == 2700

        # Wall time should be 5s (10:00:00 to 10:00:05)
        assert result["total_duration_ms"] == 5000

    def test_active_duration_with_no_steps(self):
        """Test active duration when no step metrics are available."""
        events = [
            {"timestamp": "2024-01-01T10:00:00Z", "event_type": "RUN_START"},
            {
                "timestamp": "2024-01-01T10:00:05Z",
                "event_type": "RUN_COMPLETE",
                "status": "success",
            },
        ]

        metrics = []

        result = aggregate_metrics(metrics, topk=100, events=events)

        # With no step data, active_duration should be 0
        assert "active_duration_ms" in result
        assert result["active_duration_ms"] == 0

        # But wall time should still be calculated
        assert result["total_duration_ms"] == 5000

    def test_active_duration_with_mixed_sources(self):
        """Test active duration with both metrics and events."""
        events = [
            {"timestamp": "2024-01-01T10:00:00Z", "event_type": "RUN_START"},
            {"timestamp": "2024-01-01T10:00:01Z", "event_type": "STEP_START", "step_id": "step1"},
            {
                "timestamp": "2024-01-01T10:00:02Z",
                "event_type": "STEP_COMPLETE",
                "step_id": "step1",
            },
            {"timestamp": "2024-01-01T10:00:10Z", "event_type": "RUN_COMPLETE"},
        ]

        metrics = [
            {
                "timestamp": "2024-01-01T10:00:03Z",
                "event_type": "step_metrics",
                "step_id": "step2",
                "duration_ms": 3000,
            }
        ]

        result = aggregate_metrics(metrics, topk=100, events=events)

        # Should combine both sources:
        # step1 from events: 1000ms
        # step2 from metrics: 3000ms
        # total: 4000ms
        assert result["active_duration_ms"] == 4000
