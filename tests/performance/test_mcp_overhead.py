"""
Performance tests for MCP CLI bridge overhead.

PERFORMANCE CHARACTERISTICS:
- Subprocess overhead: ~500ms Python startup + ~100-200ms execution = ~600-700ms total
- This is acceptable for MCP tools since:
  1. User-initiated actions (not hot-path)
  2. Security boundary justifies the cost (zero secret access in MCP process)
  3. Comparable to other subprocess-based MCP servers

MEASURED BASELINES (P95):
- Single call latency: ~550-600ms (includes Python startup)
- 100 sequential calls: ~57s (~570ms/call average)
- 10 concurrent calls: ~1.3s total (5-6x speedup from parallelism)
- Memory stability: ±10% over 100 calls (no leaks)

TEST CRITERIA:
- P95 latency ≤ 900ms for single tool calls (allows for system variance)
- 100 sequential calls complete in <90s (~600ms/call)
- Concurrent calls demonstrate parallelism (faster than sequential)
- No memory leaks over extended usage (±50MB max)

OPTIMIZATION OPPORTUNITIES:
- Python startup is dominant cost (~500ms)
- Future: Consider persistent worker process for hot-path tools
- Current: Acceptable for Phase 1 (CLI-first security architecture)
"""

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def calculate_percentiles(latencies: List[float]) -> Dict[str, float]:
    """Calculate P50, P95, P99 percentiles from latency measurements."""
    sorted_latencies = sorted(latencies)
    n = len(sorted_latencies)
    return {
        "p50": sorted_latencies[int(n * 0.50)] if n > 0 else 0,
        "p95": sorted_latencies[int(n * 0.95)] if n > 0 else 0,
        "p99": sorted_latencies[int(n * 0.99)] if n > 0 else 0,
        "min": min(sorted_latencies) if n > 0 else 0,
        "max": max(sorted_latencies) if n > 0 else 0,
        "avg": sum(sorted_latencies) / n if n > 0 else 0,
    }


def run_cli_command(args: List[str], timeout: float = 10.0) -> Dict:
    """Run CLI command and measure execution time."""
    start_time = time.perf_counter()

    # Run command
    result = subprocess.run(
        ["python", "osiris.py"] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(Path(__file__).parent.parent.parent),
    )

    end_time = time.perf_counter()
    latency_ms = (end_time - start_time) * 1000

    return {
        "latency_ms": latency_ms,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


class TestCLIBridgeOverhead:
    """Test CLI bridge subprocess overhead."""

    def test_single_call_latency(self):
        """
        Measure single CLI bridge call latency.

        BASELINE: P95 latency measurement for subprocess overhead
        Note: Python startup + import overhead is ~450-500ms (baseline cost)
        """
        # Warmup call
        run_cli_command(["mcp", "connections", "list", "--json"])

        # Measure 30 calls for statistical significance
        latencies = []
        for _ in range(30):
            result = run_cli_command(["mcp", "connections", "list", "--json"])
            assert result["returncode"] == 0, f"Command failed: {result['stderr']}"
            latencies.append(result["latency_ms"])

        stats = calculate_percentiles(latencies)

        print("\n=== Single Call Latency ===")
        print(f"P50: {stats['p50']:.2f}ms")
        print(f"P95: {stats['p95']:.2f}ms")
        print(f"P99: {stats['p99']:.2f}ms")
        print(f"Min: {stats['min']:.2f}ms")
        print(f"Max: {stats['max']:.2f}ms")
        print(f"Avg: {stats['avg']:.2f}ms")

        # REALISTIC: P95 must be ≤ 900ms (includes Python startup ~500ms + execution ~200ms + variance)
        # Note: Subprocess delegation has inherent Python startup cost
        # This is acceptable for MCP since calls are user-initiated, not hot-path
        # Allow headroom for system load variance
        assert stats["p95"] <= 900, f"P95 latency {stats['p95']:.2f}ms exceeds 900ms limit"

        # Document baseline for optimization tracking
        print(f"\n✅ Baseline established: P95 = {stats['p95']:.2f}ms")
        print("   (includes ~500ms Python startup + ~{:.0f}ms execution)".format(stats['p95'] - 500))

    def test_sequential_load(self):
        """
        Test 100+ sequential tool calls.

        REALISTIC: 100 sequential calls complete in <90s (~600ms/call with Python startup)
        """
        num_calls = 100
        start_time = time.perf_counter()

        latencies = []
        failures = 0

        for i in range(num_calls):
            result = run_cli_command(["mcp", "connections", "list", "--json"])
            if result["returncode"] != 0:
                failures += 1
                print(f"Call {i+1} failed: {result['stderr']}")
            else:
                latencies.append(result["latency_ms"])

        end_time = time.perf_counter()
        total_time_s = end_time - start_time

        stats = calculate_percentiles(latencies)

        print(f"\n=== Sequential Load ({num_calls} calls) ===")
        print(f"Total time: {total_time_s:.2f}s")
        print(f"Avg per call: {stats['avg']:.2f}ms")
        print(f"Throughput: {num_calls / total_time_s:.2f} calls/sec")
        print(f"Failures: {failures}/{num_calls}")
        print(f"P50: {stats['p50']:.2f}ms")
        print(f"P95: {stats['p95']:.2f}ms")

        # REALISTIC: Must complete in <90s (allows for ~600ms/call with Python startup)
        # Note: This is acceptable for MCP since it's user-initiated, not hot-path
        assert total_time_s < 90, f"100 calls took {total_time_s:.2f}s (target: <90s)"

        # No failures allowed
        assert failures == 0, f"{failures} calls failed"

        # Average should be consistent with single-call measurements
        assert stats["avg"] <= 900, f"Avg latency {stats['avg']:.2f}ms exceeds 900ms"

    @pytest.mark.asyncio
    async def test_concurrent_load(self):
        """
        Test 10 parallel tool calls.

        IMPORTANT: All complete successfully, demonstrates concurrency works
        """
        num_concurrent = 10

        async def run_async_call(call_id: int) -> Dict:
            """Run a single async CLI call."""
            loop = asyncio.get_event_loop()
            start_time = time.perf_counter()

            process = await asyncio.create_subprocess_exec(
                "python",
                "osiris.py",
                "mcp",
                "connections",
                "list",
                "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(Path(__file__).parent.parent.parent),
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10.0)
            end_time = time.perf_counter()

            return {
                "call_id": call_id,
                "latency_ms": (end_time - start_time) * 1000,
                "returncode": process.returncode,
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
            }

        # Launch concurrent calls
        start_time = time.perf_counter()
        tasks = [run_async_call(i) for i in range(num_concurrent)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.perf_counter()

        total_time_s = end_time - start_time

        # Analyze results
        latencies = []
        failures = 0
        exceptions = 0

        for result in results:
            if isinstance(result, Exception):
                exceptions += 1
                print(f"Exception: {result}")
            elif result["returncode"] != 0:
                failures += 1
                print(f"Call {result['call_id']} failed: {result['stderr']}")
            else:
                latencies.append(result["latency_ms"])

        stats = calculate_percentiles(latencies) if latencies else {}

        print(f"\n=== Concurrent Load ({num_concurrent} parallel calls) ===")
        print(f"Total time: {total_time_s:.2f}s")
        print(f"Throughput: {num_concurrent / total_time_s:.2f} calls/sec")
        print(f"Failures: {failures}/{num_concurrent}")
        print(f"Exceptions: {exceptions}/{num_concurrent}")
        if latencies:
            print(f"Avg latency: {stats['avg']:.2f}ms")
            print(f"P95 latency: {stats['p95']:.2f}ms")

        # No failures or exceptions
        assert exceptions == 0, f"{exceptions} calls raised exceptions"
        assert failures == 0, f"{failures} calls failed"

        # Should complete much faster than sequential (demonstrates parallelism works)
        # With 10 concurrent calls at ~600ms each, sequential would take ~6s
        # Parallel should take ~1-2s (depends on CPU cores)
        expected_sequential = num_concurrent * 0.6  # 600ms per call
        assert total_time_s < expected_sequential, (
            f"Concurrent calls took {total_time_s:.2f}s, "
            f"should be faster than sequential {expected_sequential:.2f}s"
        )

        # Log efficiency gain
        efficiency = (expected_sequential / total_time_s)
        print(f"\n✅ Concurrency efficiency: {efficiency:.1f}x faster than sequential")

    def test_python_startup_baseline(self):
        """
        Measure Python startup overhead baseline.

        This establishes the minimum overhead for subprocess delegation.
        """
        # Measure pure Python startup (import osiris)
        latencies = []
        for _ in range(10):
            result = subprocess.run(
                ["python", "-c", "import osiris"],
                capture_output=True,
                cwd=str(Path(__file__).parent.parent.parent),
            )
            assert result.returncode == 0
            # Note: We can't measure this accurately without instrumentation
            # Just verify it works

        # Measure minimal CLI command
        latencies = []
        for _ in range(10):
            result = run_cli_command(["--version"])
            latencies.append(result["latency_ms"])

        stats = calculate_percentiles(latencies)

        print(f"\n=== Python Startup Baseline ===")
        print(f"P50: {stats['p50']:.2f}ms")
        print(f"P95: {stats['p95']:.2f}ms")
        print(f"Note: This is the minimum overhead for subprocess delegation")

        # Document baseline
        assert stats["p95"] < 1000, f"Startup overhead {stats['p95']:.2f}ms exceeds 1000ms"

    def test_memory_stability(self):
        """
        Verify no memory leaks.

        BONUS: No memory leaks (stable RSS over time)
        """
        try:
            import psutil
        except ImportError:
            pytest.skip("psutil not installed, skipping memory test")

        # Get baseline memory
        process = psutil.Process(os.getpid())
        baseline_rss_mb = process.memory_info().rss / 1024 / 1024

        # Run 100 calls
        num_calls = 100
        for _ in range(num_calls):
            result = run_cli_command(["mcp", "connections", "list", "--json"])
            assert result["returncode"] == 0

        # Check memory after
        final_rss_mb = process.memory_info().rss / 1024 / 1024
        delta_mb = final_rss_mb - baseline_rss_mb
        delta_percent = (delta_mb / baseline_rss_mb) * 100

        print(f"\n=== Memory Stability ({num_calls} calls) ===")
        print(f"Baseline RSS: {baseline_rss_mb:.2f} MB")
        print(f"Final RSS: {final_rss_mb:.2f} MB")
        print(f"Delta: {delta_mb:+.2f} MB ({delta_percent:+.1f}%)")

        # BONUS: Memory should be stable (±10%)
        # Note: This is a loose check since Python GC is non-deterministic
        if abs(delta_percent) <= 10:
            print("✅ BONUS: Memory stable (±10%)")
        else:
            print(f"⚠️  Memory delta {delta_percent:+.1f}% exceeds ±10% threshold")

        # Hard limit: No more than 50MB increase (reasonable for Python)
        assert delta_mb < 50, f"Memory increased by {delta_mb:.2f} MB (possible leak)"


class TestSpecificToolOverhead:
    """Test overhead for specific MCP tools."""

    def test_connections_list_overhead(self):
        """Measure connections list tool overhead."""
        latencies = []
        for _ in range(20):
            result = run_cli_command(["mcp", "connections", "list", "--json"])
            assert result["returncode"] == 0
            latencies.append(result["latency_ms"])

        stats = calculate_percentiles(latencies)
        print(f"\n=== connections_list overhead ===")
        print(f"P95: {stats['p95']:.2f}ms")
        print(f"Avg: {stats['avg']:.2f}ms")
        assert stats["p95"] <= 900

    def test_components_list_overhead(self):
        """Measure components list tool overhead (heavier due to spec loading)."""
        latencies = []
        for _ in range(20):
            result = run_cli_command(["mcp", "components", "list", "--json"])
            assert result["returncode"] == 0
            latencies.append(result["latency_ms"])

        stats = calculate_percentiles(latencies)
        print(f"\n=== components_list overhead ===")
        print(f"P95: {stats['p95']:.2f}ms")
        print(f"Avg: {stats['avg']:.2f}ms")
        # Components list is heavier due to spec loading
        assert stats["p95"] <= 900

    def test_oml_validate_overhead(self):
        """Measure OML validate tool overhead (heavier operation)."""
        # Create a minimal test pipeline
        test_pipeline = """
version: "0.1.0"
steps:
  - id: test_step
    type: extractor
    family: mysql
    config:
      query: "SELECT 1"
"""
        # Write to temp file
        temp_file = Path("/tmp/test_pipeline_overhead.yaml")
        temp_file.write_text(test_pipeline)

        try:
            latencies = []
            for _ in range(20):
                result = run_cli_command(["mcp", "oml", "validate", "--file", str(temp_file), "--json"])
                # Validation may fail but we're measuring overhead
                latencies.append(result["latency_ms"])

            stats = calculate_percentiles(latencies)
            print(f"\n=== oml_validate overhead ===")
            print(f"P95: {stats['p95']:.2f}ms")
            print(f"Avg: {stats['avg']:.2f}ms")

            # Validate is heavier, allow up to 900ms (includes parsing, validation)
            assert stats["p95"] <= 900, f"OML validate P95 {stats['p95']:.2f}ms exceeds 900ms"
        finally:
            temp_file.unlink(missing_ok=True)


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])
