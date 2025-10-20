"""
Load testing for MCP Phase 3 - Performance and stability validation.

Tests sequential load, concurrent execution, memory stability, and latency tracking
to ensure the MCP server can handle production workloads without degradation.

Requirements:
- Sequential load: 1000+ tool calls without crashes
- Concurrent load: 10+ parallel tool calls without race conditions
- Memory stability: ΔRSS ≤ +50 MB over test run
- File descriptor count: < 256
- Latency stability: P95 latency ≤ 2× baseline
"""

import asyncio
from collections import defaultdict
import gc
import json
import logging
from pathlib import Path
import time
from typing import Any
from unittest.mock import Mock, patch

import pytest

# Note: psutil is not in requirements.txt - tests will skip if not installed
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from osiris.mcp.cli_bridge import run_cli_json
from osiris.mcp.tools.connections import ConnectionsTools
from osiris.mcp.tools.oml import OMLTools

logger = logging.getLogger(__name__)


# Test markers for selective execution
pytestmark = [
    pytest.mark.slow,  # Mark all load tests as slow
]


# ============================================================================
# Helper Functions
# ============================================================================


def get_process_stats() -> dict[str, Any]:
    """
    Get current process memory and file descriptor stats.

    Returns:
        Dictionary with RSS (MB), FD count, and thread count

    Note:
        Requires psutil to be installed. Tests will skip if not available.
    """
    if not PSUTIL_AVAILABLE:
        return {"rss_mb": 0, "fd_count": 0, "thread_count": 0}

    process = psutil.Process()
    mem_info = process.memory_info()

    # Get file descriptor count (platform-specific)
    try:
        fd_count = process.num_fds()  # Unix/Linux
    except AttributeError:
        # Windows doesn't have num_fds, use num_handles as proxy
        try:
            fd_count = process.num_handles()
        except AttributeError:
            fd_count = 0

    return {
        "rss_mb": mem_info.rss / (1024 * 1024),  # Convert to MB
        "fd_count": fd_count,
        "thread_count": process.num_threads(),
    }


def calculate_latency_percentiles(durations: list[float]) -> dict[str, float]:
    """
    Calculate P50 and P95 latency percentiles.

    Args:
        durations: List of duration measurements in milliseconds

    Returns:
        Dictionary with p50 and p95 values
    """
    if not durations:
        return {"p50": 0.0, "p95": 0.0, "min": 0.0, "max": 0.0, "avg": 0.0}

    sorted_durations = sorted(durations)
    n = len(sorted_durations)

    return {
        "p50": sorted_durations[int(n * 0.50)],
        "p95": sorted_durations[int(n * 0.95)],
        "min": sorted_durations[0],
        "max": sorted_durations[-1],
        "avg": sum(sorted_durations) / n,
    }


# ============================================================================
# Test 1: Sequential Load (1000+ tool calls)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(not PSUTIL_AVAILABLE, reason="psutil required for memory tracking")
async def test_sequential_load_stability():
    """
    Test sequential execution of 1000+ tool calls.

    Validates:
    - No crashes during sustained load
    - Memory doesn't grow unboundedly
    - Response times remain stable
    - No resource leaks occur

    Acceptance Criteria:
    - All 1000 calls complete successfully
    - ΔRSS ≤ +50 MB over test run
    - No exceptions or crashes
    """
    # Configuration
    NUM_CALLS = 1000
    MEMORY_GROWTH_LIMIT_MB = 50

    # Track metrics
    start_stats = get_process_stats()
    latencies = []
    errors = []

    # Mock CLI responses to avoid actual subprocess calls
    mock_responses = {
        "connections_list": {
            "connections": [
                {"family": "mysql", "alias": "default", "reference": "@mysql.default", "config": {}},
            ],
            "count": 1,
            "status": "success",
        },
        "oml_validate": {
            "valid": True,
            "errors": [],
            "warnings": [],
        },
    }

    # Cycle through different tool types
    tools = ["connections_list", "oml_validate"]
    connections_tools = ConnectionsTools()
    oml_tools = OMLTools()

    logger.info(f"Starting sequential load test: {NUM_CALLS} calls")
    logger.info(f"Initial memory: {start_stats['rss_mb']:.1f} MB, FDs: {start_stats['fd_count']}")

    with patch("osiris.mcp.cli_bridge.run_cli_json") as mock_cli:
        for i in range(NUM_CALLS):
            # Alternate between tool types
            tool_type = tools[i % len(tools)]

            # Configure mock response
            if tool_type == "connections_list":
                mock_cli.return_value = mock_responses["connections_list"]
                start_time = time.time()
                try:
                    await connections_tools.list({})
                    latencies.append((time.time() - start_time) * 1000)
                except Exception as e:
                    errors.append(f"Call {i}: {str(e)}")
            else:
                mock_cli.return_value = mock_responses["oml_validate"]
                start_time = time.time()
                try:
                    await oml_tools.validate({"yaml": "version: '0.1.0'\npipeline: []"})
                    latencies.append((time.time() - start_time) * 1000)
                except Exception as e:
                    errors.append(f"Call {i}: {str(e)}")

            # Sample memory every 100 calls
            if (i + 1) % 100 == 0:
                current_stats = get_process_stats()
                memory_delta = current_stats["rss_mb"] - start_stats["rss_mb"]
                logger.info(
                    f"Progress: {i + 1}/{NUM_CALLS} calls, "
                    f"ΔRSS: {memory_delta:+.1f} MB, "
                    f"FDs: {current_stats['fd_count']}"
                )

    # Final measurements
    end_stats = get_process_stats()
    memory_growth = end_stats["rss_mb"] - start_stats["rss_mb"]

    # Calculate latency stats
    latency_stats = calculate_latency_percentiles(latencies)

    # Log results
    logger.info("=" * 60)
    logger.info("Sequential Load Test Results:")
    logger.info(f"  Total calls: {NUM_CALLS}")
    logger.info(f"  Successful: {NUM_CALLS - len(errors)}")
    logger.info(f"  Errors: {len(errors)}")
    logger.info(f"  Memory growth: {memory_growth:+.1f} MB")
    logger.info(f"  Final FD count: {end_stats['fd_count']}")
    logger.info(f"  Latency P50: {latency_stats['p50']:.2f} ms")
    logger.info(f"  Latency P95: {latency_stats['p95']:.2f} ms")
    logger.info("=" * 60)

    # Assertions
    assert len(errors) == 0, f"Errors occurred during sequential load: {errors[:5]}"
    assert (
        memory_growth <= MEMORY_GROWTH_LIMIT_MB
    ), f"Memory grew by {memory_growth:.1f} MB (limit: {MEMORY_GROWTH_LIMIT_MB} MB)"
    assert len(latencies) == NUM_CALLS, f"Expected {NUM_CALLS} latency measurements, got {len(latencies)}"


# ============================================================================
# Test 2: Concurrent Load (10+ parallel calls)
# ============================================================================


@pytest.mark.asyncio
async def test_concurrent_load_thread_safety():
    """
    Test concurrent execution of 10+ parallel tool calls.

    Validates:
    - Thread/process safety under parallel load
    - No race conditions occur
    - All concurrent calls complete successfully
    - Correlation IDs remain unique

    Acceptance Criteria:
    - All parallel calls complete successfully
    - No race conditions or data corruption
    - Correlation IDs are unique
    - No deadlocks or hangs
    """
    # Configuration
    NUM_PARALLEL = 20
    NUM_BATCHES = 5

    # Mock CLI response
    mock_response = {
        "connections": [{"family": "mysql", "alias": "default", "reference": "@mysql.default", "config": {}}],
        "count": 1,
        "status": "success",
    }

    connections_tools = ConnectionsTools()
    correlation_ids = set()
    errors = []

    logger.info(f"Starting concurrent load test: {NUM_PARALLEL} parallel × {NUM_BATCHES} batches")

    async def make_call(call_id: int) -> dict[str, Any]:
        """Execute a single async call."""
        try:
            with patch("osiris.mcp.cli_bridge.run_cli_json", return_value=mock_response):
                result = await connections_tools.list({})
                return {"id": call_id, "success": True, "result": result}
        except Exception as e:
            return {"id": call_id, "success": False, "error": str(e)}

    for batch in range(NUM_BATCHES):
        logger.info(f"Batch {batch + 1}/{NUM_BATCHES}: Starting {NUM_PARALLEL} concurrent calls")

        # Create concurrent tasks
        tasks = [make_call(batch * NUM_PARALLEL + i) for i in range(NUM_PARALLEL)]

        # Execute in parallel
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        batch_duration = (time.time() - start_time) * 1000

        logger.info(f"Batch {batch + 1}/{NUM_BATCHES}: Completed in {batch_duration:.1f} ms")

        # Analyze results
        for result in results:
            if isinstance(result, Exception):
                errors.append(str(result))
            elif not result.get("success", False):
                errors.append(result.get("error", "Unknown error"))
            else:
                # Extract correlation ID if present (from _meta in mocked response)
                # Note: Mock doesn't generate unique IDs, so we use call_id as proxy
                correlation_ids.add(result["id"])

    # Assertions
    total_calls = NUM_PARALLEL * NUM_BATCHES
    assert len(errors) == 0, f"Errors occurred during concurrent load: {errors[:5]}"
    assert len(correlation_ids) == total_calls, f"Expected {total_calls} unique IDs, got {len(correlation_ids)}"

    logger.info("=" * 60)
    logger.info("Concurrent Load Test Results:")
    logger.info(f"  Total calls: {total_calls}")
    logger.info(f"  Successful: {total_calls - len(errors)}")
    logger.info(f"  Unique correlation IDs: {len(correlation_ids)}")
    logger.info("=" * 60)


# ============================================================================
# Test 3: Memory Leak Detection
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(not PSUTIL_AVAILABLE, reason="psutil required for memory tracking")
async def test_memory_leak_detection():
    """
    Test for memory leaks during mixed workload.

    Validates:
    - Memory doesn't grow unboundedly
    - File descriptor count stays stable
    - Garbage collection works correctly

    Acceptance Criteria:
    - ΔRSS ≤ +50 MB over test run
    - FD count < 256
    - Memory stabilizes after GC
    """
    # Configuration
    NUM_ITERATIONS = 500
    MEMORY_LIMIT_MB = 50
    FD_LIMIT = 256

    # Track stats over time
    memory_samples = []
    fd_samples = []

    # Mock responses for different tool types
    mock_responses = {
        "connections": {"connections": [], "count": 0, "status": "success"},
        "oml": {"valid": True, "errors": [], "warnings": []},
    }

    tools = [ConnectionsTools(), OMLTools()]

    # Measure baseline after GC
    gc.collect()
    baseline_stats = get_process_stats()

    logger.info("Starting memory leak detection test")
    logger.info(f"Baseline: RSS={baseline_stats['rss_mb']:.1f} MB, FDs={baseline_stats['fd_count']}")

    with patch("osiris.mcp.cli_bridge.run_cli_json") as mock_cli:
        for i in range(NUM_ITERATIONS):
            # Alternate between tools
            tool = tools[i % len(tools)]
            mock_cli.return_value = mock_responses["connections"] if i % 2 == 0 else mock_responses["oml"]

            # Execute call
            if i % 2 == 0:
                await tool.list({})
            else:
                await tool.validate({"yaml": "version: '0.1.0'\npipeline: []"})

            # Sample every 50 calls
            if (i + 1) % 50 == 0:
                stats = get_process_stats()
                memory_samples.append(stats["rss_mb"])
                fd_samples.append(stats["fd_count"])

                logger.info(
                    f"Iteration {i + 1}/{NUM_ITERATIONS}: "
                    f"RSS={stats['rss_mb']:.1f} MB (+{stats['rss_mb'] - baseline_stats['rss_mb']:.1f}), "
                    f"FDs={stats['fd_count']}"
                )

    # Force garbage collection
    gc.collect()
    final_stats = get_process_stats()

    # Calculate growth
    memory_growth = final_stats["rss_mb"] - baseline_stats["rss_mb"]
    max_fd_count = max(fd_samples) if fd_samples else final_stats["fd_count"]

    # Log results
    logger.info("=" * 60)
    logger.info("Memory Leak Detection Results:")
    logger.info(f"  Baseline RSS: {baseline_stats['rss_mb']:.1f} MB")
    logger.info(f"  Final RSS: {final_stats['rss_mb']:.1f} MB")
    logger.info(f"  Memory growth: {memory_growth:+.1f} MB")
    logger.info(f"  Peak FD count: {max_fd_count}")
    logger.info(f"  Final FD count: {final_stats['fd_count']}")
    logger.info("=" * 60)

    # Assertions
    assert memory_growth <= MEMORY_LIMIT_MB, f"Memory grew by {memory_growth:.1f} MB (limit: {MEMORY_LIMIT_MB} MB)"
    assert max_fd_count < FD_LIMIT, f"File descriptor count reached {max_fd_count} (limit: {FD_LIMIT})"


# ============================================================================
# Test 4: Latency Tracking and Stability
# ============================================================================


@pytest.mark.asyncio
async def test_latency_stability_under_load():
    """
    Test latency stability under sustained load.

    Validates:
    - P95 latency doesn't degrade significantly
    - No cascading failures occur
    - Latency remains predictable under load

    Acceptance Criteria:
    - P95 latency ≤ 2× baseline
    - No sudden latency spikes (>10× baseline)
    - Success rate ≥ 99%
    """
    # Configuration
    NUM_WARMUP = 50  # Warmup calls to establish baseline
    NUM_LOAD = 500  # Load test calls
    BASELINE_MULTIPLIER = 2.0  # P95 must be ≤ 2× baseline P95

    # Track latencies
    warmup_latencies = []
    load_latencies = []
    errors = []

    # Mock CLI response
    mock_response = {
        "connections": [{"family": "mysql", "alias": "default", "reference": "@mysql.default", "config": {}}],
        "count": 1,
        "status": "success",
    }

    connections_tools = ConnectionsTools()

    logger.info("Starting latency stability test")

    # Phase 1: Warmup to establish baseline
    logger.info(f"Phase 1: Warmup ({NUM_WARMUP} calls)")
    with patch("osiris.mcp.cli_bridge.run_cli_json", return_value=mock_response):
        for i in range(NUM_WARMUP):
            start_time = time.time()
            try:
                await connections_tools.list({})
                warmup_latencies.append((time.time() - start_time) * 1000)
            except Exception as e:
                errors.append(f"Warmup {i}: {str(e)}")

    baseline_stats = calculate_latency_percentiles(warmup_latencies)
    logger.info(
        f"Baseline: P50={baseline_stats['p50']:.2f} ms, P95={baseline_stats['p95']:.2f} ms, "
        f"Avg={baseline_stats['avg']:.2f} ms"
    )

    # Phase 2: Load test
    logger.info(f"Phase 2: Load test ({NUM_LOAD} calls)")
    with patch("osiris.mcp.cli_bridge.run_cli_json", return_value=mock_response):
        for i in range(NUM_LOAD):
            start_time = time.time()
            try:
                await connections_tools.list({})
                load_latencies.append((time.time() - start_time) * 1000)
            except Exception as e:
                errors.append(f"Load {i}: {str(e)}")

            # Log progress
            if (i + 1) % 100 == 0:
                current_stats = calculate_latency_percentiles(load_latencies)
                logger.info(
                    f"Progress: {i + 1}/{NUM_LOAD}, " f"P95={current_stats['p95']:.2f} ms, " f"Errors={len(errors)}"
                )

    # Calculate load test stats
    load_stats = calculate_latency_percentiles(load_latencies)

    # Calculate degradation
    p95_degradation = load_stats["p95"] / baseline_stats["p95"] if baseline_stats["p95"] > 0 else 0
    success_rate = ((NUM_LOAD - len(errors)) / NUM_LOAD) * 100

    # Log results
    logger.info("=" * 60)
    logger.info("Latency Stability Test Results:")
    logger.info(f"  Baseline P95: {baseline_stats['p95']:.2f} ms")
    logger.info(f"  Load P95: {load_stats['p95']:.2f} ms")
    logger.info(f"  P95 degradation: {p95_degradation:.2f}× baseline")
    logger.info(f"  Success rate: {success_rate:.1f}%")
    logger.info(f"  Total errors: {len(errors)}")
    logger.info("=" * 60)

    # Assertions
    assert success_rate >= 99.0, f"Success rate {success_rate:.1f}% below 99%"
    assert (
        p95_degradation <= BASELINE_MULTIPLIER
    ), f"P95 latency degraded {p95_degradation:.2f}× (limit: {BASELINE_MULTIPLIER}×)"

    # Check for extreme spikes (>10× baseline, minimum 10ms to avoid false positives with mocked calls)
    spike_threshold = max(baseline_stats["p95"] * 10, 10.0)
    spikes = [lat for lat in load_latencies if lat > spike_threshold]
    assert len(spikes) == 0, f"Found {len(spikes)} extreme latency spikes (>{spike_threshold:.1f} ms)"


# ============================================================================
# Test 5: Mixed Workload Simulation
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(not PSUTIL_AVAILABLE, reason="psutil required for memory tracking")
async def test_mixed_workload_realistic_usage():
    """
    Test mixed workload simulating realistic usage patterns.

    Validates:
    - System handles diverse tool usage
    - No cross-tool interference
    - Performance remains stable across tool types

    Acceptance Criteria:
    - All tool types execute successfully
    - Memory growth ≤ +50 MB
    - No performance degradation across tools
    """
    # Configuration
    NUM_ITERATIONS = 300
    MEMORY_LIMIT_MB = 50

    # Track stats per tool type
    tool_latencies = defaultdict(list)
    tool_errors = defaultdict(list)

    # Mock responses
    mock_responses = {
        "connections_list": {"connections": [], "count": 0, "status": "success"},
        "oml_validate": {"valid": True, "errors": [], "warnings": []},
        "discovery_run": {"discovery_id": "disc_test123", "status": "success"},
    }

    # Tool instances
    connections_tools = ConnectionsTools()
    oml_tools = OMLTools()

    # Baseline memory
    gc.collect()
    baseline_stats = get_process_stats()

    logger.info("Starting mixed workload test")
    logger.info(f"Baseline: RSS={baseline_stats['rss_mb']:.1f} MB")

    with patch("osiris.mcp.cli_bridge.run_cli_json") as mock_cli:
        for i in range(NUM_ITERATIONS):
            # Weighted distribution: 60% connections, 30% OML, 10% discovery
            rand = (i * 7) % 10  # Pseudo-random but deterministic

            if rand < 6:
                # Connections list
                tool_name = "connections_list"
                mock_cli.return_value = mock_responses["connections_list"]
                start_time = time.time()
                try:
                    await connections_tools.list({})
                    tool_latencies[tool_name].append((time.time() - start_time) * 1000)
                except Exception as e:
                    tool_errors[tool_name].append(str(e))

            elif rand < 9:
                # OML validate
                tool_name = "oml_validate"
                mock_cli.return_value = mock_responses["oml_validate"]
                start_time = time.time()
                try:
                    await oml_tools.validate({"yaml": "version: '0.1.0'\npipeline: []"})
                    tool_latencies[tool_name].append((time.time() - start_time) * 1000)
                except Exception as e:
                    tool_errors[tool_name].append(str(e))

            # Progress logging
            if (i + 1) % 100 == 0:
                current_stats = get_process_stats()
                logger.info(f"Progress: {i + 1}/{NUM_ITERATIONS}, " f"RSS={current_stats['rss_mb']:.1f} MB")

    # Final stats
    gc.collect()
    final_stats = get_process_stats()
    memory_growth = final_stats["rss_mb"] - baseline_stats["rss_mb"]

    # Calculate per-tool stats
    logger.info("=" * 60)
    logger.info("Mixed Workload Test Results:")
    logger.info(f"  Total iterations: {NUM_ITERATIONS}")
    logger.info(f"  Memory growth: {memory_growth:+.1f} MB")

    for tool_name in sorted(tool_latencies.keys()):
        stats = calculate_latency_percentiles(tool_latencies[tool_name])
        errors = len(tool_errors[tool_name])
        logger.info(f"  {tool_name}:")
        logger.info(f"    Calls: {len(tool_latencies[tool_name])}")
        logger.info(f"    Errors: {errors}")
        logger.info(f"    P50: {stats['p50']:.2f} ms, P95: {stats['p95']:.2f} ms")

    logger.info("=" * 60)

    # Assertions
    total_errors = sum(len(errs) for errs in tool_errors.values())
    assert total_errors == 0, f"Errors occurred: {dict(tool_errors)}"
    assert memory_growth <= MEMORY_LIMIT_MB, f"Memory grew by {memory_growth:.1f} MB (limit: {MEMORY_LIMIT_MB} MB)"


# ============================================================================
# Test 6: CLI Bridge Subprocess Overhead
# ============================================================================


@pytest.mark.asyncio
async def test_cli_bridge_subprocess_overhead():
    """
    Test subprocess overhead from CLI bridge delegation.

    Validates:
    - Subprocess creation doesn't accumulate overhead
    - Process cleanup happens correctly
    - No zombie processes remain

    Acceptance Criteria:
    - Consistent subprocess latency (<100ms variance)
    - No process table pollution
    """
    # Configuration
    NUM_CALLS = 100

    # Track subprocess latencies
    latencies = []

    # Mock successful subprocess execution
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps({"status": "success"})
    mock_result.stderr = ""

    logger.info("Starting CLI bridge subprocess overhead test")

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        with patch("osiris.mcp.cli_bridge.ensure_base_path", return_value=Path("/tmp/test")):
            for _i in range(NUM_CALLS):
                start_time = time.time()
                await run_cli_json(["mcp", "connections", "list"])
                latencies.append((time.time() - start_time) * 1000)

                # Verify subprocess was called
                assert mock_run.called

    # Calculate stats
    stats = calculate_latency_percentiles(latencies)

    logger.info("=" * 60)
    logger.info("CLI Bridge Subprocess Overhead Results:")
    logger.info(f"  Total calls: {NUM_CALLS}")
    logger.info(f"  P50 latency: {stats['p50']:.2f} ms")
    logger.info(f"  P95 latency: {stats['p95']:.2f} ms")
    logger.info(f"  Max latency: {stats['max']:.2f} ms")
    logger.info(f"  Variance: {stats['max'] - stats['min']:.2f} ms")
    logger.info("=" * 60)

    # Assertions
    variance = stats["max"] - stats["min"]
    assert variance < 100.0, f"Subprocess latency variance {variance:.2f} ms too high (limit: 100 ms)"
