# Osiris Test Inventory
*Generated: 2025-09-27*

## Test Collection Summary

- **Total Test Files**: 106
- **Total Test Cases**: 950
- **Total Test Classes**: 156
- **Collection Time**: ~2 seconds
- **Execution Time**: 60.79 seconds (full suite)

## Test Organization by Directory

| Directory | Files | Tests | Classes | Purpose | Coverage Focus |
|-----------|-------|-------|---------|---------|----------------|
| `core/` | 34 | 352 | 58 | Core business logic | 70.8% module coverage |
| `cli/` | 15 | 110 | 20 | Command-line interface | 32.9% module coverage |
| `components/` | 7 | 99 | 7 | Component registry | 62.6% module coverage |
| `integration/` | 13 | 87 | 22 | End-to-end flows | Cross-module |
| `unit/` | 7 | 68 | 12 | Unit tests | Isolated functions |
| `root` | 8 | 57 | 6 | Top-level tests | Overall functionality |
| `logs/` | 3 | 48 | 9 | Session logging | Log management |
| `remote/` | 1 | 26 | 5 | E2B remote execution | 18.1% module coverage |
| `connectors/` | 2 | 22 | 3 | Database connectors | 53.0% module coverage |
| `e2b/` | 4 | 20 | 5 | E2B integration | Live tests (skipped) |
| `chat/` | 4 | 18 | 1 | Conversational flow | Agent interactions |
| `drivers/` | 2 | 14 | 2 | Driver implementations | 76.0% module coverage |
| `validation/` | 1 | 11 | 1 | Validation harness | Config validation |
| `reference/` | 1 | 7 | 0 | Reference tests | Documentation |
| `prompts/` | 1 | 4 | 1 | Prompt management | 56.3% module coverage |
| `parity/` | 1 | 3 | 1 | Local/E2B parity | Execution consistency |
| `golden/` | 1 | 2 | 1 | Golden path tests | Happy path |
| `runtime/` | 1 | 2 | 2 | Runtime execution | 4.7% module coverage |

## Test Markers and Special Categories

### Detected Markers
| Marker | Count | Description | Status |
|--------|-------|-------------|--------|
| `@pytest.mark.asyncio` | 53 | Async test functions | Active |
| `@pytest.mark.skipif(E2B_LIVE_TESTS)` | 8 | E2B live environment tests | Skipped by default |
| `@pytest.mark.skipif(E2B_API_KEY)` | 4 | Requires E2B API key | Skipped without key |
| `@pytest.mark.skip` | 3 | Temporarily disabled tests | Always skipped |
| `@pytest.mark.integration` | 1 | Integration test marker | Active |
| `@pytest.mark.parametrize` | 1 | Parameterized tests | Active |

### Missing Standard Markers
- No `@pytest.mark.slow` detected (would be useful for long-running tests)
- No `@pytest.mark.unit` detected (relying on directory structure instead)
- No `@pytest.mark.smoke` detected (would help with quick CI runs)
- No `@pytest.mark.flaky` detected (for known intermittent failures)

## Test Performance Analysis (Top 20 Slowest)

| Test | Duration | File | Type |
|------|----------|------|------|
| `test_all_commands_have_json_in_help` | 6.81s | cli/test_all_commands_json.py | CLI validation |
| `test_json_output_consistency` | 3.38s | cli/test_all_commands_json.py | CLI validation |
| `test_ddl_execute_attempt_with_sql_channel` | 3.03s | test_supabase_ddl_generation.py | Database |
| `test_run_command_help` | 2.13s | cli/test_all_commands_json.py | CLI validation |
| `test_dump_prompts_command_help` | 2.02s | cli/test_all_commands_json.py | CLI validation |
| `test_init_command_help` | 1.98s | cli/test_all_commands_json.py | CLI validation |
| `test_validate_command_help` | 1.98s | cli/test_all_commands_json.py | CLI validation |
| `test_aiop_export_on_successful_run` | 1.45s | integration/test_aiop_autopilot_run.py | Integration |
| `test_retention_on_multiple_runs` | 1.43s | integration/test_aiop_autopilot.py | Integration |
| `test_chat_command_help` | 1.41s | cli/test_all_commands_json.py | CLI validation |
| `test_discover_all_commands` | 1.36s | cli/test_all_commands_json.py | CLI validation |
| `test_debug_vs_critical_log_levels` | 1.33s | core/test_m0_validation_4_logging.py | Logging |
| `test_scenario_log_level_comparison` | 1.33s | core/test_m0_validation_4_logging.py | Logging |
| `test_all_scenarios` | 1.24s | test_validation_harness.py | Validation |
| `test_cache_ttl_expiry` | 1.11s | integration/test_discovery_cache_invalidation.py | Cache |
| Others | <1s | - | - |

### Performance Insights
- **CLI tests are slowest**: Command help validation takes 2-7 seconds each
- **Integration tests**: 1-3 seconds typical for end-to-end flows
- **Unit tests**: Most complete in <1 second
- **Total suite time**: ~60 seconds is reasonable for 950 tests

## Test Distribution Analysis

### High Coverage Areas (>70%)
- `drivers/` - Well-tested driver implementations
- `core/` - Good coverage of business logic
- `root` - Basic functionality well covered

### Medium Coverage Areas (40-70%)
- `components/` - Component registry moderately tested
- `prompts/` - Prompt building has basic tests
- `connectors/` - Database connectors partially tested

### Low Coverage Areas (<40%)
- `runtime/` - Critical gap: Local execution barely tested
- `remote/` - Critical gap: E2B proxy completely untested
- `cli/` - User-facing commands under-tested
- `agent/` - No tests at all for agent module

## Recommended Test Markers to Add

```python
# Suggested marker scheme
@pytest.mark.smoke      # Quick tests for CI (<5s total)
@pytest.mark.slow       # Tests taking >1s each
@pytest.mark.unit       # Pure unit tests, no I/O
@pytest.mark.integration # Cross-module tests
@pytest.mark.e2b        # Requires E2B environment
@pytest.mark.llm        # Requires LLM API calls
@pytest.mark.db         # Requires database
@pytest.mark.flaky      # Known intermittent failures
```

## Test Infrastructure Observations

### Strengths
- Good test organization by module
- Reasonable execution time
- Mix of unit and integration tests
- Async test support

### Weaknesses
- Missing consistent marker strategy
- No apparent fixture sharing strategy
- Limited E2B test coverage (most skipped)
- No performance benchmarks
- Missing mock strategies for external services
