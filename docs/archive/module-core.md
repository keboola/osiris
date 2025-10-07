# Core Module Documentation

## Overview
The Core module (`osiris/core/`) contains the fundamental business logic and orchestration components of Osiris.

## Module Structure
```
osiris/core/
├── conversational_agent.py  # LLM-driven conversation management
├── discovery.py             # Database schema discovery
├── compiler_v0.py           # OML to manifest compilation
├── config.py                # Configuration management
├── driver.py                # Driver protocol and registry
├── execution_adapter.py     # Adapter abstract base class
├── adapter_factory.py       # Adapter selection factory
├── session_logging.py       # Structured logging system
├── state_store.py           # SQLite session persistence
├── llm_adapter.py           # Multi-provider LLM interface
├── secrets_masking.py       # Automatic secret detection
├── cache_fingerprint.py     # Discovery cache management
├── env_loader.py            # Environment variable loading
└── error_taxonomy.py        # Error classification system
```

## Key Components

### conversational_agent.py - AI Orchestration
Manages the LLM-driven conversation flow for pipeline creation.

**Key Classes:**
- `ConversationalAgent` - Main conversation orchestrator
- `ChatState` - FSM states (INIT, INTENT_CAPTURED, DISCOVERY, etc.)
- `ConversationContext` - Maintains conversation state

**State Machine:**
```
INIT → INTENT_CAPTURED → [DISCOVERY] → OML_SYNTHESIS → VALIDATE_OML → COMPILE
```

**Key Methods:**
```python
def process_message(self, message: str) -> AgentResponse:
    """Process user input and advance conversation"""

def generate_oml(self, context: dict) -> str:
    """Generate OML from conversation context"""

def validate_and_save(self, oml: str) -> bool:
    """Validate OML and save to output/"""
```

### discovery.py - Schema Discovery
Intelligent database schema exploration with caching.

**Key Classes:**
- `DiscoveryAgent` - Manages discovery process
- `SchemaCache` - SQLite-based caching
- `SchemaFingerprint` - SHA-256 cache validation

**Key Features:**
- Progressive discovery (tables → columns → samples)
- Connection fingerprinting for cache validation
- Automatic cache invalidation on changes

**Example Usage:**
```python
discovery = DiscoveryAgent(connection_config)
schema = discovery.discover_schema()  # Cached if unchanged
tables = discovery.get_tables()
columns = discovery.get_columns("users")
```

### compiler_v0.py - OML Compiler
Compiles OML v0.1.0 to deterministic manifests.

**Key Functions:**
- `compile_oml()` - Main compilation entry
- `validate_schema()` - OML v0.1.0 validation
- `resolve_connections()` - Connection reference resolution
- `generate_fingerprint()` - SHA-256 manifest fingerprint

**Compilation Process:**
1. Parse and validate OML
2. Resolve connection references
3. Generate step configurations
4. Create deterministic manifest
5. Calculate SHA-256 fingerprint

### driver.py - Driver Protocol
Defines the driver interface and registry system.

**Protocol Definition:**
```python
class Driver(Protocol):
    def run(
        self,
        step_id: str,
        config: dict,
        inputs: dict | None,
        ctx: ExecutionContext
    ) -> dict:
        """Execute a pipeline step"""
```

**Registry System:**
```python
class DriverRegistry:
    @classmethod
    def register(cls, name: str, driver: Driver):
        """Register a driver implementation"""

    @classmethod
    def get(cls, name: str) -> Driver:
        """Retrieve registered driver"""
```

### execution_adapter.py - Adapter Pattern
Abstract base class for execution environments.

**Interface:**
```python
class ExecutionAdapter(ABC):
    @abstractmethod
    def prepare(self, manifest: dict, context: ExecutionContext) -> PreparedRun:
        """Prepare execution package"""

    @abstractmethod
    def execute(self, prepared: PreparedRun, context: ExecutionContext):
        """Execute the pipeline"""

    @abstractmethod
    def collect(self, prepared: PreparedRun, context: ExecutionContext) -> dict:
        """Collect results and artifacts"""
```

**Implementations:**
- `LocalAdapter` - Local execution
- `E2BTransparentProxy` - E2B cloud execution

### session_logging.py - Structured Logging
Session-scoped logging with events and metrics.

**Key Classes:**
- `SessionLogger` - Main logging interface
- `EventLogger` - Structured event emission
- `MetricsCollector` - Performance metrics

**Log Structure:**
```
logs/run_XXXXXXXXXX/
├── events.jsonl      # Structured events
├── metrics.jsonl     # Performance metrics
├── artifacts/        # Generated files
└── manifest.json     # Compiled manifest
```

**Event Format:**
```json
{
  "ts": "2025-01-01T12:00:00Z",
  "session": "run_1234567890",
  "event": "step_start",
  "step_id": "extract_data",
  "driver": "mysql.extractor"
}
```

### config.py - Configuration Management
Handles configuration loading with precedence.

**Precedence Order:**
1. CLI arguments (highest)
2. Environment variables
3. Configuration files
4. Defaults (lowest)

**Key Classes:**
- `Config` - Main configuration container
- `ConnectionConfig` - Connection settings
- `RuntimeConfig` - Execution settings

### llm_adapter.py - LLM Integration
Unified interface for multiple LLM providers.

**Supported Providers:**
- OpenAI (GPT-4, GPT-4o)
- Anthropic (Claude 3.5)
- Google (Gemini)

**Interface:**
```python
class LLMAdapter:
    def complete(self, prompt: str, **kwargs) -> str:
        """Generate completion"""

    def stream(self, prompt: str, **kwargs) -> Iterator[str]:
        """Stream completion chunks"""
```

### state_store.py - Session Persistence
SQLite-based session state management.

**Key Features:**
- Conversation history persistence
- Discovery cache storage
- Session recovery on interruption
- Automatic cleanup of old sessions

### secrets_masking.py - Security
Automatic detection and masking of sensitive data.

**Detection Methods:**
- Pattern-based (regex)
- Entropy analysis
- Known secret formats
- Connection password detection

**Masking:**
```python
mask_secrets("password=secret123")
# Returns: "password=***"
```

### error_taxonomy.py - Error Classification
Standardized error types and handling.

**Error Categories:**
- `ConfigurationError` - Invalid configuration
- `CompilationError` - OML compilation failures
- `ExecutionError` - Runtime failures
- `ConnectionError` - Database connectivity
- `ValidationError` - Schema validation

## Design Patterns

### Factory Pattern
Used in `adapter_factory.py` for adapter selection:
```python
adapter = AdapterFactory.create(target="e2b")  # or "local"
```

### Registry Pattern
Used in `driver.py` for component registration:
```python
DriverRegistry.register("mysql.extractor", MySQLExtractor())
driver = DriverRegistry.get("mysql.extractor")
```

### Strategy Pattern
Used in `llm_adapter.py` for provider selection:
```python
llm = LLMAdapter.create(provider="openai", model="gpt-4")
```

## Key Interfaces

### ExecutionContext
Passed to drivers and adapters:
```python
@dataclass
class ExecutionContext:
    session_id: str
    working_dir: Path
    artifacts_dir: Path
    logger: SessionLogger

    def log_event(self, event: str, data: dict):
        """Log structured event"""

    def log_metric(self, name: str, value: float):
        """Log performance metric"""
```

## Best Practices

1. **Use protocols** for interfaces (typing.Protocol)
2. **Emit structured events** for observability
3. **Handle errors gracefully** with context
4. **Cache expensive operations** (discovery)
5. **Validate early** (configuration, OML)
6. **Mask secrets** in all outputs
7. **Use type hints** throughout

## Testing Guidelines

### Unit Tests
```python
def test_driver_registration():
    driver = MockDriver()
    DriverRegistry.register("test.driver", driver)
    retrieved = DriverRegistry.get("test.driver")
    assert retrieved is driver
```

### Integration Tests
```python
def test_compilation_flow():
    oml = load_fixture("pipeline.yaml")
    manifest = compile_oml(oml)
    assert manifest["fingerprint"]
    assert len(manifest["steps"]) > 0
```

## Future Enhancements

- Parallel step execution
- Streaming data processing
- Advanced caching strategies
- Plugin system for drivers
- Distributed execution support
