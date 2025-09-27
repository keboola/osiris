# Osiris Test Coverage Report
*Generated: 2025-09-27*

## Overall Coverage Statistics

- **Total Coverage**: 22.87%
- **Lines Covered**: 6,793 / 29,700
- **Test Execution Time**: 60.79 seconds
- **Tests Run**: 879 passed, 24 failed, 28 skipped, 19 errors

## Module Coverage Summary (Sorted by Coverage %)

| Module | Coverage % | Lines Covered | Total Lines | Status |
|--------|------------|---------------|-------------|--------|
| `agent` | **0.0%** | 0 | 898 | 🔴 Critical |
| `osiris` | **0.0%** | 0 | 14,783 | 🔴 Critical |
| `runtime` | **4.7%** | 17 | 362 | 🔴 Critical |
| `remote` | **18.1%** | 433 | 2,391 | 🔴 Critical |
| `cli` | **32.9%** | 1,242 | 3,780 | 🟡 Low |
| `connectors` | **53.0%** | 427 | 805 | 🟡 Moderate |
| `prompts` | **56.3%** | 112 | 199 | 🟡 Moderate |
| `components` | **62.6%** | 358 | 572 | 🟢 Acceptable |
| `core` | **70.8%** | 3,968 | 5,602 | 🟢 Good |
| `drivers` | **76.0%** | 228 | 300 | 🟢 Good |

## Top 20 Files with Lowest Coverage (<60%)

| File | Coverage % | Module | Why Coverage is Low |
|------|------------|--------|---------------------|
| `e2b_transparent_proxy.py` | **0.0%** | remote | New E2B proxy architecture, no tests written yet |
| `proxy_worker.py` | **0.0%** | remote | RPC worker runs in sandbox, hard to test locally |
| `proxy_worker_runner.py` | **0.0%** | remote | E2B sandbox entry point, requires live E2B environment |
| `e2b_pack.py` | **0.0%** | remote | Legacy packing code, superseded by transparent proxy |
| `local_adapter.py` | **4.7%** | runtime | Local execution adapter, complex driver interactions |
| `prompt_manager.py` | **13.1%** | core | LLM prompt construction, needs prompt validation tests |
| `e2b_adapter.py` | **22.1%** | remote | Legacy E2B adapter, being replaced by transparent proxy |
| `e2b_client.py` | **25.6%** | remote | E2B SDK wrapper, requires live E2B API for testing |
| `e2b_integration.py` | **31.2%** | remote | E2B integration layer, needs mock sandbox tests |
| `cli_orchestrator.py` | **38.5%** | cli | CLI flow orchestration, complex state machine |
| `compile.py` | **42.0%** | cli | Compilation CLI command, needs more edge case tests |
| `runner_v0.py` | **46.3%** | core | Legacy runner, being phased out |
| `compiler_v0.py` | **49.1%** | core | Legacy compiler, stable but under-tested |
| `conversational_agent.py` | **50.8%** | core | Core agent logic, complex LLM interactions |
| `session_reader.py` | **51.8%** | core | Session log reading, needs more format tests |
| `discovery.py` | **52.5%** | core | Database schema discovery, needs mock DB tests |
| `build_context.py` | **56.3%** | prompts | Context building for LLMs, needs template tests |
| `main.py` | **56.9%** | cli | CLI main entry point, needs command integration tests |
| `chat.py` | **58.8%** | cli | Interactive chat mode, needs mock conversation tests |
| `llm_adapter.py` | **59.6%** | core | Multi-provider LLM adapter, needs provider mocks |

## Test Failures Analysis

### Failed Tests (24)
- **AIOP Tests** (18 failures): Most AIOP end-to-end tests are failing, likely due to missing test fixtures or environment setup
- **Validation Tests** (4 failures): Configuration validation tests need environment variables
- **Component Tests** (19 errors): Bootstrap spec tests cannot find component files

### Key Problem Areas
1. **E2B/Remote Module**: 81.9% uncovered - Critical for cloud execution
2. **Runtime Module**: 95.3% uncovered - Local execution path
3. **CLI Module**: 67.1% uncovered - User-facing commands
4. **AIOP Integration**: Many test failures indicate fragile test setup

## Recommendations

### Quick Wins (Each adds ~3% coverage)
1. **Add E2B Transparent Proxy tests** (~600 lines, +2.0%): Mock RPC protocol tests
2. **Add ProxyWorker unit tests** (~450 lines, +1.5%): Test message handling
3. **Add LocalAdapter tests** (~350 lines, +1.2%): Mock driver execution
4. **Add PromptManager tests** (~200 lines, +0.7%): Template rendering tests
5. **Fix AIOP test fixtures** (~500 lines, +1.7%): Restore broken integration tests

### Risk Mitigation
- **External Dependencies**: Use mocks for E2B API, LLM providers, database connections
- **Flaky Tests**: Add retry logic for network-dependent tests
- **Test Isolation**: Ensure all tests use temp directories, no shared state
