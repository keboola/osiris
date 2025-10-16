"""
Test telemetry race condition fixes (RC-002, RC-004).

Tests that:
1. Concurrent metrics updates don't lose data (RC-002)
2. Global telemetry singleton is thread-safe (RC-004)
"""

import threading
import time
from pathlib import Path
from typing import Any

from osiris.mcp.telemetry import TelemetryEmitter, init_telemetry


class TestRC002MetricsLock:
    """Test RC-002: Metrics updates must be synchronized."""

    def test_concurrent_tool_calls_preserve_all_metrics(self, tmp_path: Path):
        """100 concurrent tool calls should result in exactly 100 counted calls."""
        telemetry = TelemetryEmitter(enabled=True, output_dir=tmp_path)

        num_threads = 100
        barrier = threading.Barrier(num_threads)  # Sync all threads to start together

        def emit_tool_call():
            barrier.wait()  # Wait for all threads to be ready
            telemetry.emit_tool_call(
                tool="test_tool",
                status="ok",
                duration_ms=10,
                bytes_in=100,
                bytes_out=200,
            )

        threads = [threading.Thread(target=emit_tool_call) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify all metrics were counted
        summary = telemetry.get_session_summary()
        assert summary["metrics"]["tool_calls"] == num_threads
        assert summary["metrics"]["total_bytes_in"] == 100 * num_threads
        assert summary["metrics"]["total_bytes_out"] == 200 * num_threads
        assert summary["metrics"]["total_duration_ms"] == 10 * num_threads
        assert summary["metrics"]["errors"] == 0

    def test_concurrent_error_increments(self, tmp_path: Path):
        """Concurrent error tool calls should increment error counter correctly."""
        telemetry = TelemetryEmitter(enabled=True, output_dir=tmp_path)

        num_threads = 50
        barrier = threading.Barrier(num_threads)

        def emit_error():
            barrier.wait()
            telemetry.emit_tool_call(
                tool="failing_tool",
                status="error",
                duration_ms=5,
                bytes_in=50,
                bytes_out=100,
                error="Test error",
            )

        threads = [threading.Thread(target=emit_error) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        summary = telemetry.get_session_summary()
        assert summary["metrics"]["tool_calls"] == num_threads
        assert summary["metrics"]["errors"] == num_threads

    def test_get_session_summary_returns_consistent_snapshot(self, tmp_path: Path):
        """Reading metrics while updating should return consistent snapshot."""
        telemetry = TelemetryEmitter(enabled=True, output_dir=tmp_path)

        stop_flag = threading.Event()
        summaries: list[dict[str, Any]] = []

        def writer():
            """Continuously update metrics."""
            counter = 0
            while not stop_flag.is_set():
                telemetry.emit_tool_call(
                    tool="writer_tool",
                    status="ok",
                    duration_ms=1,
                    bytes_in=10,
                    bytes_out=20,
                )
                counter += 1
                if counter >= 100:
                    stop_flag.set()

        def reader():
            """Continuously read metrics."""
            while not stop_flag.is_set():
                summary = telemetry.get_session_summary()
                summaries.append(summary)
                time.sleep(0.001)  # Small delay to allow concurrent access

        writer_thread = threading.Thread(target=writer)
        reader_thread = threading.Thread(target=reader)

        writer_thread.start()
        reader_thread.start()

        writer_thread.join()
        stop_flag.set()
        reader_thread.join()

        # Verify all summaries have consistent data (no torn reads)
        for summary in summaries:
            metrics = summary["metrics"]
            # Each increment is atomic, so counts should be consistent
            assert metrics["tool_calls"] >= 0
            assert metrics["total_bytes_in"] == metrics["tool_calls"] * 10
            assert metrics["total_bytes_out"] == metrics["tool_calls"] * 20
            assert metrics["total_duration_ms"] == metrics["tool_calls"] * 1

    def test_emit_server_stop_captures_final_metrics_atomically(self, tmp_path: Path):
        """Server stop should capture final metrics without race conditions."""
        telemetry = TelemetryEmitter(enabled=True, output_dir=tmp_path)

        # Emit some tool calls
        for _ in range(10):
            telemetry.emit_tool_call(
                tool="test",
                status="ok",
                duration_ms=1,
                bytes_in=10,
                bytes_out=20,
            )

        # Emit server stop (should capture metrics snapshot)
        telemetry.emit_server_stop(reason="test")

        # Verify telemetry file contains server_stop event with correct metrics
        telemetry_file = tmp_path / f"mcp_telemetry_{time.strftime('%Y%m%d')}.jsonl"
        assert telemetry_file.exists()

        import json

        with open(telemetry_file) as f:
            lines = f.readlines()
            # Find server_stop event
            server_stop_event = None
            for line in lines:
                event = json.loads(line)
                if event["event"] == "server_stop":
                    server_stop_event = event
                    break

            assert server_stop_event is not None
            assert server_stop_event["metrics"]["tool_calls"] == 10
            assert server_stop_event["metrics"]["total_bytes_in"] == 100
            assert server_stop_event["metrics"]["total_bytes_out"] == 200


class TestRC004GlobalTelemetryLock:
    """Test RC-004: Global telemetry initialization must be thread-safe."""

    def test_concurrent_init_creates_single_instance(self, tmp_path: Path):
        """Multiple threads calling init_telemetry should get the same instance."""
        # Reset global state
        import osiris.mcp.telemetry as telemetry_module

        telemetry_module._telemetry = None  # noqa: SLF001  # Reset for test

        num_threads = 50
        barrier = threading.Barrier(num_threads)
        instances: list[TelemetryEmitter] = []

        def initialize():
            barrier.wait()  # Wait for all threads
            instance = init_telemetry(enabled=True, output_dir=tmp_path)
            instances.append(instance)

        threads = [threading.Thread(target=initialize) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All instances should be the same object (singleton)
        assert len(instances) == num_threads
        first_instance = instances[0]
        for instance in instances:
            assert instance is first_instance, "All threads should get same singleton instance"

    def test_init_telemetry_idempotent(self, tmp_path: Path):
        """Calling init_telemetry multiple times should return existing instance."""
        # Reset global state
        import osiris.mcp.telemetry as telemetry_module

        telemetry_module._telemetry = None  # noqa: SLF001  # Reset for test

        instance1 = init_telemetry(enabled=True, output_dir=tmp_path / "dir1")
        instance2 = init_telemetry(enabled=True, output_dir=tmp_path / "dir2")

        # Should return same instance (first initialization wins)
        assert instance1 is instance2
        assert instance1.output_dir == tmp_path / "dir1"  # First config preserved

    def test_init_telemetry_preserves_session_id(self, tmp_path: Path):
        """Concurrent initialization should preserve single session ID."""
        # Reset global state
        import osiris.mcp.telemetry as telemetry_module

        telemetry_module._telemetry = None  # noqa: SLF001  # Reset for test

        num_threads = 20
        barrier = threading.Barrier(num_threads)
        session_ids: list[str] = []

        def get_session_id():
            barrier.wait()
            instance = init_telemetry(enabled=True, output_dir=tmp_path)
            session_ids.append(instance.session_id)

        threads = [threading.Thread(target=get_session_id) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should see the same session ID
        assert len(set(session_ids)) == 1, "All threads should see same session ID"


class TestPerformanceUnderLoad:
    """Verify thread safety doesn't cause significant performance degradation."""

    def test_high_volume_concurrent_metrics(self, tmp_path: Path):
        """High volume concurrent metrics updates should complete in reasonable time."""
        telemetry = TelemetryEmitter(enabled=True, output_dir=tmp_path)

        num_threads = 10
        calls_per_thread = 100

        start_time = time.time()

        def emit_many():
            for _ in range(calls_per_thread):
                telemetry.emit_tool_call(
                    tool="perf_test",
                    status="ok",
                    duration_ms=1,
                    bytes_in=100,
                    bytes_out=200,
                )

        threads = [threading.Thread(target=emit_many) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        elapsed = time.time() - start_time

        # Verify all calls were counted
        summary = telemetry.get_session_summary()
        assert summary["metrics"]["tool_calls"] == num_threads * calls_per_thread

        # Performance check: 1000 calls should complete in < 5 seconds
        assert elapsed < 5.0, f"Took too long: {elapsed:.2f}s for {num_threads * calls_per_thread} calls"
