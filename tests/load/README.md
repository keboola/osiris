# MCP Load Tests

Comprehensive load testing suite for Osiris MCP Phase 3 performance and stability validation.

## Overview

This test suite validates MCP server performance under various load conditions:

1. **Sequential Load** - 1000+ tool calls without degradation
2. **Concurrent Load** - 10+ parallel calls with thread safety
3. **Memory Leak Detection** - Memory stability over sustained load
4. **Latency Tracking** - P95 latency stability validation
5. **Mixed Workload** - Realistic usage patterns
6. **CLI Bridge Overhead** - Subprocess delegation performance

## Running Tests

### All Load Tests
```bash
python -m pytest tests/load/ -v
```

### With psutil (Required for Memory Tests)
```bash
pip install psutil
python -m pytest tests/load/ -v
```

### Individual Tests
```bash
# Concurrent load (no dependencies)
python -m pytest tests/load/test_mcp_load.py::test_concurrent_load_thread_safety -v

# Latency stability (no dependencies)
python -m pytest tests/load/test_mcp_load.py::test_latency_stability_under_load -v

# Memory tests (requires psutil)
python -m pytest tests/load/test_mcp_load.py::test_sequential_load_stability -v
python -m pytest tests/load/test_mcp_load.py::test_memory_leak_detection -v
```

## Test Coverage

### Test 1: Sequential Load Stability
- **Volume**: 1000+ sequential tool calls
- **Metrics**: Memory growth, FD count, latency stability
- **Acceptance**: ΔRSS ≤ +50 MB, no crashes
- **Requires**: psutil

### Test 2: Concurrent Load Thread Safety
- **Volume**: 20 parallel × 5 batches = 100 concurrent calls
- **Metrics**: Success rate, correlation ID uniqueness
- **Acceptance**: 100% success, no race conditions
- **Requires**: None

### Test 3: Memory Leak Detection
- **Volume**: 500 mixed workload calls
- **Metrics**: RSS growth, FD count, GC effectiveness
- **Acceptance**: ΔRSS ≤ +50 MB, FD count < 256
- **Requires**: psutil

### Test 4: Latency Stability Under Load
- **Volume**: 50 warmup + 500 load calls
- **Metrics**: P50/P95 latency, degradation ratio
- **Acceptance**: P95 ≤ 2× baseline, 99%+ success rate
- **Requires**: None

### Test 5: Mixed Workload Realistic Usage
- **Volume**: 300 mixed calls (connections, OML, discovery)
- **Metrics**: Per-tool latency, memory growth
- **Acceptance**: All tools succeed, memory stable
- **Requires**: psutil

### Test 6: CLI Bridge Subprocess Overhead
- **Volume**: 100 subprocess delegations
- **Metrics**: Subprocess latency variance
- **Acceptance**: Variance < 100ms
- **Requires**: None

## Performance Baselines

Based on CLAUDE.md requirements:

- **Selftest Target**: < 2 seconds (< 1.3s actual in Phase 2)
- **P95 Latency**: ~615ms (acceptable for security boundary)
- **Memory Overhead**: Minimal (<1% per E2B operation)
- **FD Limit**: < 256 (system stability)

## Dependencies

### Required
- `pytest>=7.0.0`
- `pytest-asyncio>=0.21.0`

### Optional (for memory tests)
- `psutil` - Provides RSS, FD count, thread tracking
  - Install: `pip install psutil`
  - Without psutil: 3 memory tests skip, 3 tests pass

## Test Markers

All tests are marked with:
- `@pytest.mark.slow` - Long-running load tests
- `@pytest.mark.skipif(not PSUTIL_AVAILABLE)` - Memory tests

Skip slow tests:
```bash
pytest tests/load/ -v -m "not slow"  # Skip all load tests
```

## CI Integration

Load tests should run in CI with psutil installed:

```yaml
# .github/workflows/test.yml
- name: Run load tests
  run: |
    pip install psutil
    pytest tests/load/ -v --tb=short
```

## Interpreting Results

### Success Criteria
- ✅ All tests pass or skip (if psutil missing)
- ✅ Memory growth ≤ +50 MB
- ✅ FD count < 256
- ✅ P95 latency ≤ 2× baseline
- ✅ 99%+ success rate under load

### Failure Investigation
- **Memory growth**: Check for unclosed file handles, cached data
- **FD leaks**: Investigate subprocess cleanup, file I/O
- **Latency spikes**: Profile slow CLI subcommands
- **Race conditions**: Review async code, shared state

## Development

To add new load tests:

1. Import required tools from `osiris.mcp.tools.*`
2. Mock `osiris.mcp.cli_bridge.run_cli_json` to avoid subprocess overhead
3. Track metrics: latency, memory, FD count
4. Use `@pytest.mark.skipif(not PSUTIL_AVAILABLE)` for memory tests
5. Assert against acceptance criteria

Example:
```python
@pytest.mark.asyncio
@pytest.mark.skipif(not PSUTIL_AVAILABLE, reason="psutil required")
async def test_new_load_scenario():
    start_stats = get_process_stats()

    # Your load test here

    end_stats = get_process_stats()
    memory_growth = end_stats["rss_mb"] - start_stats["rss_mb"]
    assert memory_growth <= 50, f"Memory grew {memory_growth:.1f} MB"
```

## References

- **Phase 3 Acceptance**: `docs/milestones/mcp-finish-plan.md`
- **Baseline Metrics**: `docs/reports/phase2-impact/`
- **CLI Bridge**: `osiris/mcp/cli_bridge.py`
