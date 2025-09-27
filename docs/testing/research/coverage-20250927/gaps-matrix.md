# Osiris Test Gaps Matrix
*Generated: 2025-09-27*

## Critical Modules Analysis

### 🔴 Remote Module (18.1% coverage)

| Module/File | Coverage | Critical Behaviors | Existing Tests | Missing Scenarios | Suggested Approach |
|-------------|----------|-------------------|----------------|-------------------|-------------------|
| **e2b_transparent_proxy.py** | **0.0%** | • Sandbox creation & lifecycle<br>• RPC communication<br>• Artifact collection<br>• Error handling<br>• Streaming events | None directly<br>• Parity tests exist but skip proxy | • Sandbox creation failure<br>• RPC timeout handling<br>• Connection interruption<br>• Large artifact handling<br>• Multi-step execution<br>• Progress streaming | • Mock AsyncSandbox<br>• Mock RPC protocol<br>• Fixture: `fake_sandbox`<br>• Test heartbeat mechanism |
| **proxy_worker.py** | **0.0%** | • Command reception<br>• Driver execution<br>• Event streaming<br>• Error propagation<br>• Heartbeat sending | None | • All command types<br>• Driver failures<br>• Timeout scenarios<br>• Memory limits<br>• Concurrent commands | • Mock stdin/stdout<br>• Fake driver registry<br>• Test in-process<br>• Capture JSON-RPC |
| **proxy_worker_runner.py** | **0.0%** | • Worker initialization<br>• Main loop execution<br>• Clean shutdown | None | • Entry point testing<br>• Signal handling<br>• Graceful shutdown | • Mock subprocess<br>• Test argv parsing |
| **e2b_adapter.py** | **22.1%** | • Legacy adapter<br>• Package building<br>• Sandbox management | • test_e2b_smoke.py<br>• test_e2b_full_cli.py | • Package size limits<br>• Missing dependencies<br>• Network failures<br>• API rate limiting | • Being deprecated<br>• Focus on proxy tests |
| **e2b_client.py** | **25.6%** | • SDK wrapper<br>• API interaction<br>• Error translation | • test_e2b_live.py (skipped) | • API errors<br>• Retry logic<br>• Timeout handling<br>• Resource cleanup | • Mock E2B SDK<br>• Fixture: `mock_e2b_api` |
| **rpc_protocol.py** | **99.1%** | • Message serialization<br>• Protocol definition | Well tested | • Edge cases only | Already good |

### 🔴 Runtime Module (4.7% coverage)

| Module/File | Coverage | Critical Behaviors | Existing Tests | Missing Scenarios | Suggested Approach |
|-------------|----------|-------------------|----------------|-------------------|-------------------|
| **local_adapter.py** | **4.7%** | • Driver loading<br>• Step execution<br>• Data flow<br>• Metrics collection<br>• Error handling | • test_local_e2e_with_cfg.py (1 test) | • Driver not found<br>• Driver exceptions<br>• Data type mismatches<br>• Large dataframes<br>• Concurrent execution<br>• Memory constraints | • Mock DriverRegistry<br>• Fake drivers<br>• Fixture: `mock_drivers`<br>• Test data generators |

### 🟡 CLI Module (32.9% coverage)

| Module/File | Coverage | Critical Behaviors | Existing Tests | Missing Scenarios | Suggested Approach |
|-------------|----------|-------------------|----------------|-------------------|-------------------|
| **cli_orchestrator.py** | **38.5%** | • Command dispatch<br>• State management<br>• Error recovery | Basic tests | • Command chaining<br>• Interrupt handling<br>• State corruption<br>• Concurrent commands | • Mock Rich console<br>• Capture output<br>• Test state machine |
| **compile.py** | **42.0%** | • Pipeline compilation<br>• Validation<br>• Output generation | • test_all_commands_json.py | • Invalid YAML<br>• Missing connections<br>• Circular dependencies<br>• Large pipelines | • Test fixtures<br>• Error scenarios |
| **chat.py** | **58.8%** | • Conversation flow<br>• LLM interaction<br>• Session management | • test_chat.py<br>• test_chat_session.py | • LLM failures<br>• Session recovery<br>• Multi-turn dialog<br>• Context overflow | • Mock LLM adapter<br>• Conversation fixtures |
| **main.py** | **56.9%** | • Entry point<br>• Argument parsing<br>• Command routing | • test_all_commands_json.py | • Invalid arguments<br>• Environment setup<br>• Signal handling | • Mock sys.argv<br>• Test Click commands |

### 🟡 Core Module (70.8% coverage - but key files need work)

| Module/File | Coverage | Critical Behaviors | Existing Tests | Missing Scenarios | Suggested Approach |
|-------------|----------|-------------------|----------------|-------------------|-------------------|
| **prompt_manager.py** | **13.1%** | • Template rendering<br>• Context building<br>• Prompt optimization | Minimal | • All template types<br>• Large contexts<br>• Token limits<br>• Variable substitution | • Template fixtures<br>• Mock tokenizer<br>• Test all providers |
| **llm_adapter.py** | **59.6%** | • Multi-provider support<br>• API calls<br>• Response parsing<br>• Retry logic | • test_llm_adapter.py | • Provider failures<br>• Rate limiting<br>• Streaming responses<br>• Token counting | • Mock API clients<br>• Response fixtures<br>• Error scenarios |
| **conversational_agent.py** | **50.8%** | • FSM transitions<br>• State persistence<br>• Intent recognition | • test_chat_*.py files | • State recovery<br>• Invalid transitions<br>• Context limits<br>• Parallel conversations | • State fixtures<br>• Mock state store<br>• FSM test harness |

### 🟢 Well-Tested Modules (>70% coverage)

| Module | Coverage | Notes |
|--------|----------|-------|
| **drivers/** | 76.0% | Good driver coverage |
| **core/secrets_masking.py** | 100% | Complete coverage |
| **core/state_store.py** | 100% | Complete coverage |
| **components/** | 62.6% | Acceptable, needs edge cases |

## Priority Gaps by Impact

### 🚨 P0 - Critical Gaps (Blocks Production)
1. **E2B Transparent Proxy** - 0% coverage of new architecture
2. **ProxyWorker** - 0% coverage of sandbox execution
3. **LocalAdapter** - 4.7% coverage of execution path

### ⚠️ P1 - High Priority (User-Facing)
1. **PromptManager** - 13% coverage, critical for LLM interaction
2. **CLI Orchestrator** - 38% coverage of user commands
3. **Compile Command** - 42% coverage of pipeline generation

### 📝 P2 - Medium Priority (Stability)
1. **LLM Adapter** - Missing provider-specific tests
2. **Conversational Agent** - FSM edge cases
3. **Chat CLI** - Multi-turn conversation tests

## Recommended Test Fixtures

### For E2B/Remote Testing
```python
@pytest.fixture
def mock_sandbox():
    """Mock E2B sandbox with controllable behavior"""

@pytest.fixture
def fake_rpc_channel():
    """In-memory RPC channel for testing protocol"""

@pytest.fixture
def proxy_worker_harness():
    """Test harness for ProxyWorker without subprocess"""
```

### For Runtime Testing
```python
@pytest.fixture
def mock_driver_registry():
    """Registry with fake drivers for testing"""

@pytest.fixture
def fake_execution_context():
    """Context with temp directories and session"""

@pytest.fixture
def sample_manifests():
    """Collection of test manifests"""
```

### For CLI Testing
```python
@pytest.fixture
def cli_runner():
    """Click test runner with captured output"""

@pytest.fixture
def mock_rich_console():
    """Rich console that captures formatted output"""

@pytest.fixture
def temp_config_env():
    """Temporary configuration environment"""
```

## Test Implementation Priorities

### Week 1: E2B Foundation (Expected +8% coverage)
- Mock E2B SDK and AsyncSandbox
- Test E2BTransparentProxy lifecycle
- Test RPC protocol with mock channels
- Test ProxyWorker message handling

### Week 2: Runtime & Execution (Expected +6% coverage)
- Mock driver registry and drivers
- Test LocalAdapter execution flow
- Test error propagation and recovery
- Test metrics collection

### Week 3: CLI & User Experience (Expected +5% coverage)
- Test all CLI commands with fixtures
- Test error messages and help text
- Test configuration handling
- Test session management

### Week 4: Core Logic & Integration (Expected +4% coverage)
- Test prompt templates and rendering
- Test LLM provider failover
- Test conversation state machine
- End-to-end integration tests

## Success Metrics

| Metric | Current | Target | Milestone |
|--------|---------|--------|-----------|
| Overall Coverage | 22.87% | 50% | 3 months |
| E2B/Remote Coverage | 18.1% | 80% | Week 1 |
| Runtime Coverage | 4.7% | 70% | Week 2 |
| CLI Coverage | 32.9% | 70% | Week 3 |
| Test Execution Time | 60s | <90s | Ongoing |
| Flaky Test Rate | Unknown | <2% | Week 4 |
