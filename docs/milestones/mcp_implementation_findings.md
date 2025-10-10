# MCP Implementation Findings for Osiris

## Executive Summary

This document presents comprehensive research findings on implementing a Model Context Protocol (MCP) server for Osiris, an LLM-first conversational ETL pipeline generator. Based on analysis of the latest MCP specifications (2025), SDK capabilities, and production implementations, this research identifies critical design decisions, recommends architectural patterns, and proposes enhancements to the current milestone plan.

### Key Recommendations

1. **Adopt FastMCP over base MCP SDK** for rapid development with production-ready features
2. **Implement fine-grained tool decomposition** for `generate_oml` to enable iterative refinement
3. **Use hybrid session management** combining server-side discovery cache with client-side context
4. **Leverage structured error taxonomy** with repair hints for self-correcting LLM loops
5. **Deploy in-memory testing** with deterministic fixtures for reliable MCP server validation
6. **Integrate AIOP exports as MCP resources** for enhanced observability and debugging

### Critical Decisions Required

- **Tool Granularity**: Monolithic `generate_oml` vs decomposed pipeline assembly tools
- **State Management**: Server-side session storage vs client-side context propagation
- **Resource Persistence**: Ephemeral in-memory cache vs durable storage backend
- **Error Recovery**: Automatic repair attempts vs explicit client-driven retries
- **Authentication**: Single-workspace MVP vs multi-tenant architecture preparation

## MCP Protocol Analysis

### Latest Protocol Specifications (2025)

The Model Context Protocol has evolved significantly since its November 2024 introduction. As of October 2025:

- **Protocol Version**: Uses date-based versioning (e.g., "2025-06-01")
- **Transport Layers**: STDIO, HTTP/SSE, WebSocket, and Streamable HTTP
- **JSON-RPC 2.0**: Foundation for request/response messaging
- **Adoption**: OpenAI (March 2025), Google DeepMind (April 2025) joined Anthropic
- **SDK Ecosystem**: Python (v1.15.0), TypeScript, C#, Java SDKs available

### SDK Capabilities Comparison

#### Official MCP Python SDK (v1.15.0) - Already Installed
- **Core Abstractions**: Resources, Tools, Prompts as first-class entities
- **Async-First Design**: Built on asyncio with sync compatibility
- **Type Safety**: Automatic schema generation from type hints
- **Lifecycle Management**: Context and ServerSession objects
- **Progress Reporting**: Built-in progress tracking and logging

#### FastMCP Framework (v2.12.3) - Already Installed
- **Enhanced Features**:
  - In-memory testing with FastMCPTransport
  - Automatic OpenAPI/FastAPI generation
  - Enterprise authentication (OAuth, JWT, API keys)
  - Server composition and proxying
  - Deployment tools for cloud hosting
  - Structured output with Pydantic models
  - Zero-configuration development

**Recommendation**: Use FastMCP for Osiris MCP server due to superior developer experience, testing capabilities, and production features.

### Best Practices from Production Implementations

Based on analysis of successful MCP servers (database tools, filesystem, GitHub integration):

1. **Never write to stdout** in STDIO servers (corrupts JSON-RPC messages)
2. **Use type hints extensively** for automatic schema generation
3. **Implement deterministic tool behavior** for reliable testing
4. **Leverage context injection** for logging and progress tracking
5. **Handle both sync and async** tool implementations
6. **Version tools explicitly** in manifests for compatibility
7. **Provide structured errors** with actionable repair hints

## Tool Design Research

### Patterns from Successful MCP Servers

Analysis of popular MCP servers reveals three design patterns:

#### Pattern 1: Fine-Grained Tools (Database Servers)
```python
# Example from MSSQL MCP Server
tools = [
    "schema.list",
    "table.info",
    "table.sample",
    "query.execute",
    "query.explain"
]
```
**Pros**: Maximum flexibility, composable, easy to test
**Cons**: Many round trips, complex client orchestration

#### Pattern 2: Coarse-Grained Tools (Pipeline Tools)
```python
# Example from ETL MCP servers
tools = [
    "pipeline.generate_and_validate",
    "pipeline.execute_with_monitoring"
]
```
**Pros**: Simple client, fewer round trips
**Cons**: Black box operations, hard to debug

#### Pattern 3: Hybrid Approach (Recommended for Osiris)
```python
# Proposed Osiris tool decomposition
tools = [
    # Discovery (coarse)
    "discovery.request",  # Triggers full progressive discovery

    # Generation (decomposed)
    "oml.interpret_intent",  # Parse user requirements
    "oml.generate_steps",    # Create pipeline steps
    "oml.assemble_pipeline", # Combine into full pipeline
    "oml.validate",          # Check assembled pipeline
    "oml.repair",            # Fix validation errors

    # Persistence (simple)
    "oml.save"               # Store validated pipeline
]
```

### Tool Decomposition Benefits Analysis

#### Current Monolithic Design Limitations
The milestone specifies a single `generate_oml` tool that does everything:
- Black box generation without intermediate visibility
- Difficult to debug when generation fails
- Can't iterate on specific parts
- Hard to test individual logic components

#### Proposed Decomposed Design Advantages
Breaking into smaller tools enables:
- **Transparent debugging**: See exactly where generation fails
- **Iterative refinement**: Fix specific steps without regenerating all
- **Better testing**: Unit test each tool independently
- **Client flexibility**: Advanced clients can customize flow
- **Fallback strategies**: Try alternative approaches per step

### Stateful vs Stateless Trade-offs

**Finding**: Most successful MCP servers use hybrid approach

| Aspect | Stateless | Stateful | Hybrid (Recommended) |
|--------|-----------|----------|----------------------|
| Scaling | Excellent | Challenging | Good |
| Testing | Simple | Complex | Moderate |
| Client Complexity | High | Low | Moderate |
| Memory Usage | Low | High | Moderate |
| Cache Efficiency | Poor | Excellent | Good |

## Resource Layer Architecture

### Enhanced Resource URI Design

Building on ADR-0036's resource layer, research suggests hierarchical organization:

```yaml
# Discovery Resources (Progressive Detail)
osiris://discovery/<session_id>/manifest.json         # Overview
osiris://discovery/<session_id>/tables/              # Table list
osiris://discovery/<session_id>/tables/<name>/schema # Schema only
osiris://discovery/<session_id>/tables/<name>/sample-10  # 10 rows
osiris://discovery/<session_id>/tables/<name>/sample-100 # 100 rows
osiris://discovery/<session_id>/tables/<name>/profile   # Statistics

# OML Resources (Version-Aware)
osiris://oml/schemas/v0.1.0/full.json               # Complete schema
osiris://oml/schemas/v0.1.0/components/<comp>.json  # Per-component
osiris://oml/drafts/<session>/<draft_id>.yaml       # Draft pipelines
osiris://oml/validated/<session>/<id>.yaml          # Validated

# AIOP Integration (New Proposal)
osiris://aiop/<run_id>/evidence.json    # Evidence layer
osiris://aiop/<run_id>/semantic.json    # Semantic layer
osiris://aiop/<run_id>/narrative.md     # Human-readable
osiris://aiop/<run_id>/metrics.json     # Performance data
```

### Caching Strategy Recommendations

**Three-Tier Cache Architecture**:

1. **Hot Cache** (In-Memory, <1ms access)
   - Recent discovery results (<1 hour old)
   - Active OML drafts
   - Size limit: 100MB total

2. **Warm Cache** (SQLite, <10ms access)
   - Discovery results (1-24 hours old)
   - Validated OML pipelines
   - Size limit: 1GB total

3. **Cold Storage** (Optional, Future)
   - S3/GCS for AIOP exports
   - Historical discovery results
   - Unlimited size

**MVP Recommendation**: Start with in-memory only, add SQLite in v0.5

## Session & State Management

### Session Lifecycle Patterns

Research reveals three phases in MCP session management:

```python
# 1. Initialization Phase
session = server.create_session()  # Allocate resources
session.authenticate()              # Future: verify credentials
session.load_workspace()            # Load connections, config

# 2. Operation Phase
discovery_id = session.run_discovery()     # Expensive, cached
oml = session.generate_oml(discovery_id)   # Uses cached discovery
validation = session.validate_oml(oml)     # Stateless validation
session.save_oml(oml)                      # Persist to storage

# 3. Cleanup Phase
session.expire_cache()              # After TTL
session.close()                     # Release resources
```

### Recommended Hybrid State Management

```python
class HybridSessionManager:
    """Combines server-side caching with client-side context"""

    def __init__(self):
        self.discovery_cache = TTLCache(ttl=86400)  # 24 hours
        self.generation_cache = LRUCache(max_size=100)

    @tool
    async def discovery_request(self, connection: str) -> str:
        """Run discovery, cache results, return session ID"""
        session_id = f"disc_{timestamp}_{uuid.short}"
        results = await run_discovery(connection)
        self.discovery_cache[session_id] = results
        return session_id  # Client stores this

    @tool
    async def generate_oml(
        self,
        intent: str,
        discovery_session: str,      # Server-cached reference
        client_context: Dict = None  # Client-maintained state
    ) -> OMLResult:
        """Generate using cached discovery + client context"""
        discovery = self.discovery_cache.get(discovery_session)
        if not discovery:
            raise DiscoveryCacheExpired(discovery_session)

        # Combine server cache with client context
        full_context = {
            "discovery": discovery,
            "user_context": client_context or {},
            "intent": intent
        }

        return await self._generate(full_context)
```

## Error Handling Strategy

### Enhanced Error Taxonomy

Research suggests hierarchical error codes with actionable repair hints:

```python
ERROR_TAXONOMY = {
    "SCHEMA": {
        "MISSING_FIELD": {
            "severity": "error",
            "repairable": True,
            "suggest": "Add required field '{field}' to {path}"
        },
        "INVALID_TYPE": {
            "severity": "error",
            "repairable": True,
            "suggest": "Change type from {current} to {expected}"
        }
    },
    "SEMANTIC": {
        "UNKNOWN_TABLE": {
            "severity": "error",
            "repairable": True,
            "suggest": "Did you mean '{suggestion}'?",
            "alternatives": lambda ctx: find_similar_tables(ctx)
        },
        "INVALID_JOIN": {
            "severity": "error",
            "repairable": False,
            "suggest": "Tables lack common key. Consider intermediate table."
        }
    },
    "GENERATION": {
        "INTENT_UNCLEAR": {
            "severity": "warning",
            "repairable": True,
            "suggest": "Specify source tables or provide example"
        },
        "TOO_COMPLEX": {
            "severity": "error",
            "repairable": True,
            "suggest": "Break into multiple pipelines"
        }
    }
}
```

### Self-Correction Pattern

```python
@tool
async def generate_with_auto_repair(
    intent: str,
    max_attempts: int = 2
) -> OMLResult:
    """Generate OML with automatic error correction"""

    for attempt in range(max_attempts):
        try:
            # Generate
            oml = await generate_oml(intent)

            # Validate
            validation = await validate_oml(oml)

            if validation.ok:
                return oml

            # Auto-repair if possible
            if validation.repairable and attempt < max_attempts - 1:
                repair_prompt = build_repair_prompt(
                    intent,
                    validation.errors,
                    validation.suggestions
                )
                intent = repair_prompt
                continue

            # Return with errors if can't repair
            return OMLResult(
                oml=oml,
                errors=validation.errors,
                repaired=False
            )

        except Exception as e:
            if attempt < max_attempts - 1:
                # Retry with enriched context
                intent = f"{intent}\n\nError: {e}"
                continue
            raise
```

## Testing & Observability

### Testing Strategy with FastMCP

**Key Finding**: FastMCP's in-memory testing enables deterministic validation

```python
# tests/mcp/test_determinism.py
import pytest
from fastmcp import FastMCP, FastMCPTransport

@pytest.fixture
async def mcp_server():
    """Create in-memory MCP server for testing"""
    server = FastMCP("osiris-test")

    # Register tools
    from osiris.mcp.tools import register_tools
    register_tools(server)

    return server

@pytest.fixture
async def mcp_client(mcp_server):
    """Create test client connected to server"""
    transport = FastMCPTransport(mcp_server)
    return await transport.connect()

async def test_generation_determinism(mcp_client):
    """Verify identical inputs produce identical outputs"""

    params = {
        "intent": "Extract customer data",
        "discovery_session": "test_session",
        "idempotency_key": "test123"
    }

    # Generate twice with same inputs
    result1 = await mcp_client.call_tool("generate_oml", params)
    result2 = await mcp_client.call_tool("generate_oml", params)

    # Should be identical (excluding timestamps)
    assert normalize_output(result1) == normalize_output(result2)
```

### Observability Metrics

**Critical Metrics for Production**:

```python
# Tool Performance
mcp.tool.latency{tool="generate_oml", p95=true}      # 95th percentile
mcp.tool.error_rate{tool="discovery.request"}        # Error percentage
mcp.tool.invocation.count{status="success"}          # Total calls

# Cache Efficiency
mcp.cache.hit_rate{cache="discovery"}                # Cache effectiveness
mcp.cache.size_bytes{cache="in_memory"}              # Memory usage
mcp.cache.evictions{reason="ttl_expired"}            # Cache churn

# Generation Quality
mcp.generation.first_pass_success_rate{}             # No repairs needed
mcp.generation.repair.success_rate{}                 # Repair effectiveness
mcp.validation.error_distribution{code="SEMANTIC/*"} # Error patterns

# Session Metrics
mcp.session.duration{outcome="completed"}            # Session length
mcp.session.tools_per_session{}                      # Tool usage patterns
```

## Osiris-Specific Opportunities

### AIOP Integration as MCP Resources

**Unique Value**: Expose AIOP for LLM debugging

```python
@server.resource
async def get_aiop_package(run_id: str) -> AIOPPackage:
    """Retrieve complete AIOP for pipeline run"""
    return {
        "evidence": f"osiris://aiop/{run_id}/evidence.json",
        "semantic": f"osiris://aiop/{run_id}/semantic.json",
        "narrative": f"osiris://aiop/{run_id}/narrative.md",
        "metrics": f"osiris://aiop/{run_id}/metrics.json"
    }

@server.tool
async def analyze_failure_with_aiop(run_id: str) -> Analysis:
    """Use AIOP to diagnose pipeline failures"""
    aiop = await load_aiop(run_id)

    # Leverage AIOP layers
    root_cause = analyze_evidence(aiop.evidence_layer)
    impact = assess_semantic_impact(aiop.semantic_layer)
    explanation = generate_narrative(aiop.narrative_layer)

    return FailureAnalysis(
        root_cause=root_cause,
        affected_components=impact.components,
        recommended_fix=generate_fix_suggestion(root_cause),
        explanation=explanation
    )
```

### E2B Execution Monitoring via MCP

```python
@server.tool
async def execute_pipeline_streaming(
    pipeline_path: str,
    use_e2b: bool = True
) -> AsyncIterator[ExecutionUpdate]:
    """Stream execution updates in real-time"""

    if use_e2b:
        executor = E2BTransparentProxy()
    else:
        executor = LocalAdapter()

    async for event in executor.stream_execution(pipeline_path):
        yield ExecutionUpdate(
            timestamp=event.timestamp,
            step_id=event.step_id,
            status=event.status,
            progress=event.progress,
            output_preview=event.output[:500]  # Truncated
        )

    # Final AIOP
    yield ExecutionComplete(
        aiop_uri=f"osiris://aiop/{event.run_id}/package.json"
    )
```

### Progressive Discovery Enhancement

```python
@server.tool
async def discovery_adaptive(
    connection: str,
    strategy: str = "progressive",
    budget: Dict = None
) -> DiscoverySession:
    """Adaptive discovery with cost/time budgets"""

    session = DiscoverySession()
    budget = budget or {"max_rows": 1000, "max_time": 60}

    # Always get schema (cheap)
    schema = await discover_schema(connection)
    session.add_layer("schema", schema)
    yield session.snapshot()

    # Sample if under budget
    if budget["max_rows"] > 0:
        samples = await sample_tables(
            connection,
            limit=min(10, budget["max_rows"])
        )
        session.add_layer("sample_10", samples)
        yield session.snapshot()

    # Profile if time allows
    if time_remaining(budget) > 10:
        profile = await profile_tables(connection)
        session.add_layer("profile", profile)
        yield session.snapshot()

    return session
```

## Proposed Implementation Enhancements

### 1. Add Tool Decomposition (Phase 3.5)

In addition to monolithic `generate_oml`, add:
```python
oml.interpret_intent     # Parse user requirements
oml.plan_pipeline        # Design execution strategy
oml.generate_steps       # Create individual steps
oml.optimize_pipeline    # Apply optimizations
oml.explain_pipeline     # Generate documentation
```

### 2. Implement Repair Tools (Phase 3.5)

```python
oml.diagnose_errors      # Analyze validation failures
oml.suggest_fixes        # Generate repair options
oml.apply_repair         # Execute repair strategy
```

### 3. Add Streaming Support (Phase 4)

- Modify `discovery.request` to stream progress
- Add `execution.monitor` for real-time status
- Implement `generation.stream` for incremental OML creation

### 4. Enhanced Testing Framework (Phase 2)

```
tests/mcp/
  fixtures/
    discovery/          # Deterministic discovery results
    oml/               # Valid/invalid OML samples
    errors/            # Error scenarios

  property/            # Property-based tests
    test_determinism.py
    test_idempotency.py
    test_error_recovery.py
```

### 5. Observability Integration (Phase 4)

- OpenTelemetry spans for tool invocations
- Prometheus metrics endpoint
- Correlation IDs for request tracing
- Integration with existing AIOP exports

## Implementation Priorities

### Revised Timeline with Enhancements

**Phase 1: Foundation** (Week 1)
- Set up FastMCP server framework ✓
- Create tool registration system
- Implement basic error handling
- Set up testing infrastructure

**Phase 2: Core Tools** (Week 2)
- Connections and components tools
- Discovery with caching
- OML validation wrapper
- Unit tests with fixtures

**Phase 3: Generation Tools** (Week 3)
- Monolithic generate_oml
- Resource serving
- Use case catalog

**Phase 3.5: Enhanced Tools** (Week 4)
- Decomposed generation tools
- Repair and diagnosis tools
- Streaming support

**Phase 4: Integration** (Week 5)
- Chat-to-MCP adapter
- CLI commands
- Observability hooks
- Documentation

**Phase 5: Polish** (Week 6)
- Performance optimization
- E2B monitoring integration
- AIOP resource endpoints
- Migration guide

## Risk Analysis & Mitigation

### Technical Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| FastMCP instability | High | Low | Fall back to base MCP SDK |
| LLM non-determinism | Medium | High | Idempotency keys, caching |
| Memory pressure from cache | Medium | Medium | TTL limits, size bounds |
| Schema drift | High | Medium | CI validation, auto-generation |
| Client compatibility | High | Low | Test with Claude Desktop early |

### Process Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Scope creep | High | High | Strict MVP boundaries |
| Chat migration resistance | Medium | Medium | Gradual deprecation |
| Testing complexity | Medium | Medium | In-memory test fixtures |
| Documentation lag | Low | Medium | Write-as-you-go approach |

## Decision Matrix

### Critical Decisions with Recommendations

| Decision | Options | Recommendation | Rationale |
|----------|---------|----------------|-----------|
| **SDK Choice** | MCP SDK vs FastMCP | **FastMCP** | Better testing, auth, deployment |
| **Tool Granularity** | Monolithic vs Decomposed | **Start monolithic, add decomposed** | Balance simplicity with flexibility |
| **State Management** | Server vs Client vs Hybrid | **Hybrid** | Best of both worlds |
| **Caching** | Memory vs SQLite vs Both | **Memory for MVP** | Simpler, add SQLite later |
| **Error Recovery** | Auto vs Manual | **Auto with limits** | Better UX, prevent loops |
| **Testing** | Mock vs In-memory | **In-memory** | More realistic, FastMCP support |
| **Auth Scope** | None vs Basic vs Full | **None for MVP** | Focus on functionality first |

---

## 1. NEW FILES TO CREATE

### 1.1 MCP Server Core

#### `osiris/mcp/`
**Purpose**: New package for MCP server implementation

- **`osiris/mcp/__init__.py`**
  - Package initialization
  - Version exports
  - Public API surface

- **`osiris/mcp/server.py`**
  - MCP server bootstrap and lifecycle management
  - Tool registration
  - Resource registration
  - Use Anthropic MCP Python SDK
  - stdio transport configuration
  - Session management for discovery caching

- **`osiris/mcp/errors.py`**
  - Shared error model with taxonomy constants:
    - `SCHEMA/*` - Schema validation failures
    - `SEMANTIC/*` - Semantic validation errors
    - `DISCOVERY/*` - Discovery orchestration errors
    - `LINT/*` - Style and best-practice warnings
    - `POLICY/*` - Permissions and policy violations
  - Standard error shape: `{code, path, message, suggest?}`

- **`osiris/mcp/cache.py`**
  - In-memory TTL cache for discovery results
  - 24-hour TTL for discovery sessions
  - Cache key: session_id
  - Thread-safe implementation

- **`osiris/mcp/audit.py`**
  - Lightweight event logger
  - Emits `mcp.tool.invoke` events
  - Integrates with existing `osiris/core/session_logging.py`

### 1.2 MCP Tool Handlers

#### `osiris/mcp/tools/`
**Purpose**: Individual tool implementations

- **`osiris/mcp/tools/__init__.py`**
  - Tool registry
  - Tool manifest exports

- **`osiris/mcp/tools/connections.py`**
  - `connections.list` - List available connections
  - `connections.doctor` - Test connectivity
  - **Reuses**: `osiris/cli/connections_cmd.py` (lines 1-250)
  - **Wraps**: `osiris/core/config.py::load_connections_yaml()`

- **`osiris/mcp/tools/components.py`**
  - `components.list` - List available components with filtering
  - **Reuses**: `osiris/cli/components_cmd.py` (lines 20-100)
  - **Wraps**: `osiris/components/registry.py::ComponentRegistry`

- **`osiris/mcp/tools/discovery.py`**
  - `discovery.request` - Trigger progressive discovery
  - Returns session ID: `disc_<timestamp>_<uuid4-short>`
  - Stores results in cache with 24h TTL
  - **Reuses**: `osiris/core/discovery.py::ProgressiveDiscovery`
  - **Generates**: Discovery resource URIs

- **`osiris/mcp/tools/oml.py`**
  - `oml.schema.get` - Serve OML v0.1.0 JSON schema
  - `oml.validate` - Validate OML documents
  - `oml.save` - Persist OML drafts to session storage
  - **Reuses**: `osiris/core/oml_validator.py::OMLValidator`
  - **Integrates**: `osiris/core/session_logging.py` for persistence

- **`osiris/mcp/tools/usecases.py`**
  - `usecases.list` - Enumerate business scenarios
  - Loads from `resources/usecases/dummy_catalog.yaml`
  - Filtering by category/tag

- **`osiris/mcp/tools/generate.py`**
  - `generate_oml` - Deterministic OML synthesis
  - Single LLM call (Claude preferred, OpenAI fallback)
  - Idempotency via `idempotency_key`
  - Inputs: intent, discovery_uris, schema_uri, constraints
  - Optional: `previous_oml`, `error_report` for repairs
  - **Uses**: `osiris/mcp/prompts/generate_oml.md` as system prompt
  - **Wraps**: LLM adapter from `osiris/core/llm_adapter.py`

### 1.3 MCP Resources

#### `osiris/mcp/resources/`
**Purpose**: Resource serving and schema management

- **`osiris/mcp/resources/__init__.py`**
  - Resource registry

- **`osiris/mcp/resources/schema_loader.py`**
  - Helper to serve `/schemas/oml/v0.1.0.json`
  - Generate JSON Schema from `OMLValidator` contract
  - CI guard to ensure parity with Python validator

### 1.4 MCP Prompts

#### `osiris/mcp/prompts/`
**Purpose**: System prompts for LLM tools

- **`osiris/mcp/prompts/generate_oml.md`**
  - System prompt template for `generate_oml` tool
  - Includes OML v0.1.0 constraints
  - Discovery context integration patterns
  - Error repair instructions

### 1.5 Schemas and Resources

#### Top-level directories

- **`schemas/`** (NEW)
  - `schemas/oml/`
    - `schemas/oml/v0.1.0.json` - Canonical OML JSON Schema
    - Generated from `osiris/core/oml_validator.py` contract
    - Used by MCP resource `osiris://oml/schema/v0.1.0.json`

- **`resources/`** (NEW)
  - `resources/usecases/`
    - `resources/usecases/dummy_catalog.yaml` - Sample use-case catalog
    - Format: list of use-cases with id, name, description, category, tags, oml_snippet

### 1.6 MCP Client (Reference Implementation)

#### `osiris/mcp_client/`
**Purpose**: Lightweight Python MCP client for testing and CLI

- **`osiris/mcp_client/__init__.py`**
  - Client API exports

- **`osiris/mcp_client/client.py`**
  - Python MCP client implementation
  - Used for integration tests and CLI commands
  - Communicates via stdio with MCP server

### 1.7 CLI Integration

#### `osiris/cli/`

- **`osiris/cli/mcp_entrypoint.py`** (NEW)
  - CLI shim to launch MCP server
  - Command: `osiris mcp serve`
  - Stdio transport setup
  - Configuration loading

- **`osiris/cli/mcp_cmd.py`** (NEW)
  - CLI commands for MCP client interactions:
    - `osiris mcp connections list`
    - `osiris mcp discovery request`
    - `osiris mcp oml validate`
    - `osiris mcp usecases list`
    - `osiris mcp generate`
  - Uses `osiris/mcp_client/` for server communication

---

## 2. FILES TO MODIFY

### 2.1 Core Configuration

#### `osiris/core/config.py`
**Lines to modify**: Around 331-388 (AIOP config section)

**Changes needed**:
- Add MCP server configuration section:
  ```yaml
  mcp:
    enabled: true
    transport: stdio  # stdio|http
    host: localhost   # for http transport
    port: 8765        # for http transport
    cache_ttl: 86400  # 24 hours for discovery cache
    audit_events: true
  ```

#### `osiris/core/oml_validator.py`
**Current location**: Lines 1-411

**Changes needed**:
- Add method to export JSON Schema representation
- Method signature: `to_json_schema() -> dict`
- Will be used by `schemas/oml/v0.1.0.json` generator
- No changes to validation logic (preserve existing behavior)

### 2.2 CLI Entry Point

#### `osiris/cli/main.py`
**Current location**: CLI routing and command groups

**Changes needed**:
- Add MCP command group:
  ```python
  @cli.group()
  def mcp():
      """MCP server and client commands."""
      pass
  ```
- Register subcommands from `osiris/cli/mcp_cmd.py`
- Add deprecation warning to `chat` command:
  ```python
  @cli.command()
  def chat(...):
      console.print("[yellow]⚠ Warning: The chat interface is deprecated. Use MCP tools instead.[/yellow]")
      # existing chat logic
  ```

### 2.3 Chat Interface Deprecation

#### `osiris/cli/chat.py`
**Current location**: Lines 1-1500+ (full conversational interface)

**Changes needed**:
- Add deprecation notice at module level
- Emit warning on function entry (line ~114 in `show_epic_help`)
- Add to docstring: "DEPRECATED: This interface will be removed in v0.6. Use MCP tools instead."
- Timeline markers:
  - v0.4: Deprecation warnings
  - v0.5: Compatibility layer only
  - v0.6: Full removal

#### `osiris/core/conversational_agent.py`
**Current location**: Lines 1-2000+ (state machine implementation)

**Changes needed**:
- Add deprecation notice at module level
- Mark class `ConversationalPipelineAgent` as deprecated
- No functional changes (preserve for v0.4-v0.5)

### 2.4 Session Logging Integration

#### `osiris/core/session_logging.py`
**Current functionality**: Structured logging, session context

**Changes needed**:
- Add support for MCP-specific event types:
  - `mcp.tool.invoke` - Tool invocation event
  - `mcp.resource.read` - Resource access event
  - `mcp.cache.hit` / `mcp.cache.miss` - Cache events
- Ensure MCP session IDs follow format: `disc_<timestamp>_<uuid4>`
- No breaking changes to existing logging

### 2.5 Discovery System

#### `osiris/core/discovery.py`
**Current location**: Lines 1-1000+ (ProgressiveDiscovery class)

**Changes needed**:
- Add method to serialize discovery results for MCP cache:
  - Method: `to_resource() -> dict`
  - Returns: `{overview: dict, tables: list, session_id: str}`
- Add method to generate resource URIs:
  - `get_resource_uris(session_id: str) -> dict`
  - Returns: `{overview: "osiris://discovery/{id}/overview.json", ...}`
- Preserve all existing functionality (no breaking changes)

---

## 3. TESTING REQUIREMENTS

### 3.1 Unit Tests (NEW)

#### `tests/mcp/`
**Purpose**: Comprehensive MCP tool and server testing

- **`tests/mcp/test_server_boot.py`**
  - Smoke test for MCP server registration
  - Tool manifest shape validation
  - Resource registration verification

- **`tests/mcp/test_connections_tools.py`**
  - Unit tests for `connections.list` and `connections.doctor`
  - Mock connectors to ensure diagnostics surface correctly
  - Verify JSON output format

- **`tests/mcp/test_components_tools.py`**
  - Unit tests for `components.list`
  - Mode filtering verification
  - Runnable status checks

- **`tests/mcp/test_discovery_tool.py`**
  - Verify `discovery.request` reuses existing orchestrators
  - Session ID generation and format
  - Cache population
  - Resource URI generation

- **`tests/mcp/test_oml_tools.py`**
  - Validate `oml.schema.get` serves correct schema
  - Test `oml.validate` against fixture set
  - Verify `oml.save` persistence to session logs
  - Parity tests: MCP vs CLI validation results

- **`tests/mcp/test_usecases_tool.py`**
  - Load dummy catalog
  - Filter by category/tag
  - JSON output format

- **`tests/mcp/test_generate_tool.py`**
  - Deterministic output for identical inputs
  - Idempotency key enforcement
  - Generated OML passes `oml.validate`
  - Error cases return structured validation errors

- **`tests/mcp/test_generate_repair.py`**
  - Iterative repair using `previous_oml` and `error_report`
  - Verify repair suggestions incorporated

- **`tests/mcp/test_error_shape.py`**
  - All tool responses follow `{code, path, message, suggest?}` schema
  - Error taxonomy coverage (SCHEMA, SEMANTIC, DISCOVERY, LINT, POLICY)

- **`tests/mcp/test_cache_ttl.py`**
  - Discovery results expire after 24h TTL
  - Cache eviction behavior
  - Thread safety

- **`tests/mcp/test_audit_events.py`**
  - Tool invocations emit `mcp.tool.invoke` events
  - Event shape and metadata

### 3.2 Integration Tests (NEW)

- **`tests/mcp/test_client_e2e.py`**
  - End-to-end test: client → server → response
  - Full workflow: discovery → validate → generate → save
  - Verify resource reads

### 3.3 Parity Tests (MODIFIED)

- **Update existing tests** to compare MCP vs Chat/CLI behavior:
  - `tests/core/test_oml_validator.py` - Add MCP tool comparison
  - `tests/core/test_discovery.py` - Add resource serialization tests

---

## 4. DOCUMENTATION REQUIREMENTS

### 4.1 MCP Documentation (NEW)

#### `docs/mcp/`
**Purpose**: MCP interface documentation for integrators

- **`docs/mcp/overview.md`**
  - MCP architecture overview
  - Tool catalogue with descriptions
  - Request/response shapes
  - Client integration guidance
  - Transport options (stdio, future HTTP)

- **`docs/mcp/tool-reference.md`**
  - Detailed per-tool specification
  - Input/output schemas with examples
  - Error codes and handling
  - Idempotency semantics
  - Rate limits and quotas (future)

- **`docs/mcp/resource-reference.md`**
  - Resource URI taxonomy
  - MIME types and schemas
  - TTL and retention policies
  - Access patterns and caching

### 4.2 Migration Documentation (NEW)

#### `docs/migration/`
**Purpose**: Guide users from chat to MCP

- **`docs/migration/chat-to-mcp.md`**
  - Mapping table: Chat flow → MCP tool calls
  - Side-by-side examples
  - Timeline for deprecation (v0.4 → v0.6)
  - Breaking changes and compatibility notes

### 4.3 ADR Updates (MODIFY)

- **`docs/adr/0036-mcp-interface.md`**
  - Add links to:
    - Milestone: `docs/milestones/mcp-interface.md`
    - Documentation: `docs/mcp/overview.md`
    - Migration guide: `docs/migration/chat-to-mcp.md`
  - Update status from "Proposed" to "Accepted" after review

- **`docs/adr/0019-chat-state-machine.md`**
  - Add deprecation notice at top
  - Link to ADR-0036 as superseding ADR
  - Mark status as "Superseded"

### 4.4 User Documentation (MODIFY)

- **`docs/user-guide/user-guide.md`**
  - Add section on MCP usage with Claude Desktop
  - Update CLI examples to include MCP commands
  - Deprecation notice for chat interface

- **`docs/quickstart.md`**
  - Add MCP quickstart section
  - Example: Connecting Claude Desktop to Osiris MCP server

---

## 5. OPERATIONAL ASSETS

### 5.1 Build System (MODIFY)

#### `Makefile`
**Current location**: Root directory

**Changes needed**:
- Add MCP targets:
  ```makefile
  .PHONY: mcp-serve
  mcp-serve:  ## Start MCP server locally
      @python osiris.py mcp serve

  .PHONY: mcp-test
  mcp-test:  ## Run MCP integration tests
      @pytest tests/mcp/ -v
  ```

#### `scripts/` (NEW)
- **`scripts/run_mcp_server.sh`**
  - Bash script to start MCP server with proper environment
  - Loads `.env` file
  - Activates venv
  - Launches server with stdio transport

### 5.2 Configuration (MODIFY)

#### `.osiris/config.example.yaml`
**Current location**: Example configuration

**Changes needed**:
- Add MCP server configuration stanza (see section 2.1)

### 5.3 CI/CD (MODIFY)

#### `.github/workflows/` (if exists)
**Changes needed**:
- Add MCP test job
- Schema parity check: Ensure `schemas/oml/v0.1.0.json` matches `OMLValidator`
- Run MCP integration tests

---

## 6. DEPENDENCIES AND PREREQUISITES

### 6.1 Python Dependencies

**Add to `requirements.txt`**:
```
mcp>=1.0.0  # Anthropic MCP Python SDK
```

### 6.2 Existing Code to Preserve

**MUST NOT MODIFY** (preserve exact behavior):
- `osiris/core/discovery.py` - Discovery orchestration logic
- `osiris/core/oml_validator.py` - Validation rules (only add export method)
- `osiris/components/registry.py` - Component registry
- `osiris/connectors/` - Database connectors
- `osiris/core/session_logging.py` - Logging infrastructure (only add event types)

### 6.3 Stable Contracts

**These interfaces are stable and used by MCP**:
- `IExtractor` protocol
- `IDiscovery` protocol
- `ComponentRegistry.get_component()`, `.list_components()`
- `OMLValidator.validate()` signature
- `load_connections_yaml()` function

---

## 7. IMPLEMENTATION PHASES

### Phase 1 - Foundations (Week 1)
**Goal**: Server bootstrap and schema export

**Tasks**:
1. Create `osiris/mcp/` package structure
2. Implement `server.py` with empty tool handlers
3. Add `mcp_entrypoint.py` CLI command
4. Generate `schemas/oml/v0.1.0.json` from `OMLValidator`
5. Add CI guard for schema parity
6. Draft `docs/mcp/overview.md`

**Acceptance**: MCP server starts, registers tools (no-ops), serves schema

### Phase 2 - Tool Implementation (Week 2-3)
**Goal**: Working tools for connections, components, discovery

**Tasks**:
1. Implement `connections.py` tools (list, doctor)
2. Implement `components.py` tools (list)
3. Implement `discovery.py` tool (request)
4. Add resource layer for discovery results
5. Implement cache with 24h TTL
6. Write unit tests for Phase 2 tools

**Acceptance**: All read-only tools working, discovery cached

### Phase 3 - OML Authoring Flow (Week 4-5)
**Goal**: Complete OML validation, generation, and persistence

**Tasks**:
1. Implement `oml.py` tools (schema.get, validate, save)
2. Create `resources/usecases/dummy_catalog.yaml`
3. Implement `usecases.py` tool (list)
4. Implement `generate.py` tool with LLM integration
5. Create `prompts/generate_oml.md` system prompt
6. Write comprehensive tests for OML flow
7. Add integration test (end-to-end)

**Acceptance**: Full OML authoring workflow functional

### Phase 4 - Documentation and Migration (Week 6)
**Goal**: Complete docs, deprecation notices, release prep

**Tasks**:
1. Finalize `docs/mcp/tool-reference.md`
2. Write `docs/migration/chat-to-mcp.md`
3. Update ADR-0036 and ADR-0019
4. Add deprecation warnings to `chat.py`
5. Update user guide and quickstart
6. Review and stakeholder sign-off

**Acceptance**: Docs complete, chat deprecated, ready for v0.4 release

---

## 8. RISKS AND MITIGATIONS

### Risk 1: Schema Drift
**Problem**: JSON schema diverges from Python validator

**Mitigation**:
- CI test: Generate schema from `OMLValidator`, compare to committed file
- Fail build if mismatch
- Automate schema regeneration on validator changes

### Risk 2: Chat Compatibility Break
**Problem**: Users depend on chat interface

**Mitigation**:
- Gradual deprecation timeline (v0.4 → v0.6)
- Clear migration guide with examples
- Compatibility layer in v0.5 (thin adapter to MCP)

### Risk 3: MCP Protocol Changes
**Problem**: Anthropic updates MCP spec, breaks Osiris

**Mitigation**:
- Pin MCP SDK version in requirements
- Monitor MCP SDK releases
- Version MCP tools explicitly in manifest

### Risk 4: Discovery Cache Invalidation
**Problem**: Stale cache leads to incorrect OML generation

**Mitigation**:
- 24h TTL enforced
- Add manual invalidation command: `osiris mcp cache clear`
- Log cache hits/misses for observability

### Risk 5: LLM Non-Determinism
**Problem**: `generate_oml` produces different output for same input

**Mitigation**:
- Set `temperature=0` for deterministic sampling
- Use idempotency_key to detect retries
- Cache results by (intent_hash, discovery_hash, idempotency_key)
- Add test to verify determinism

---

## 9. SUCCESS CRITERIA

**The milestone is complete when**:

1. ✅ All MVP tools respond correctly via MCP-compliant client
2. ✅ `oml.schema.get` serves valid JSON Schema matching validator
3. ✅ `oml.validate` produces identical results to CLI validator
4. ✅ `oml.save` persists to same storage as chat interface
5. ✅ Documentation complete and reviewed
6. ✅ Integration tests pass (client → server → response)
7. ✅ Chat interface marked deprecated with warnings
8. ✅ Migration guide published
9. ✅ Stakeholder sign-off obtained

---

## 10. CROSS-REFERENCE INDEX

### Existing Files Referenced

| File Path | Lines | Purpose |
|-----------|-------|---------|
| `osiris/core/oml_validator.py` | 1-411 | OML validation logic (ADD export method) |
| `osiris/core/discovery.py` | 1-1000+ | Progressive discovery (ADD serialization) |
| `osiris/cli/connections_cmd.py` | 1-250 | Connection management (WRAP in MCP) |
| `osiris/cli/components_cmd.py` | 20-100 | Component listing (WRAP in MCP) |
| `osiris/cli/chat.py` | 1-1500+ | Chat interface (ADD deprecation) |
| `osiris/core/conversational_agent.py` | 1-2000+ | State machine (ADD deprecation) |
| `osiris/core/session_logging.py` | - | Logging infrastructure (ADD MCP events) |
| `osiris/core/config.py` | 331-388 | Configuration (ADD MCP section) |
| `osiris/cli/main.py` | - | CLI entry point (ADD MCP group) |

### Run-card Generation Context

**Note**: Run-card generation remains unchanged by MCP implementation. These locations are preserved:
- `osiris/core/run_export_v2.py:1594` - `generate_markdown_runcard()`
- `osiris/remote/proxy_worker.py:1280` - `_write_run_card()`
- `osiris/core/aiop_export.py:219` - AIOP integration

---

## 11. SEARCH KEYWORDS FOR CLAUDE CONTEXT MCP

**Use these keywords to find relevant code sections**:

- `oml_validator` - Validation logic
- `discovery` - Discovery orchestration
- `connections_cmd` - Connection management CLI
- `components_cmd` - Component registry CLI
- `session_logging` - Structured logging
- `conversational_agent` - Chat state machine (to deprecate)
- `chat.py` - Chat interface (to deprecate)
- `ComponentRegistry` - Component management
- `ProgressiveDiscovery` - Discovery implementation
- `OMLValidator` - OML validation
- `load_connections_yaml` - Connection loading
- `mask_sensitive_dict` - Secret masking

---

## APPENDIX A: Tool Mapping Table

| MCP Tool | Wraps/Reuses | New Code? | Test File |
|----------|--------------|-----------|-----------|
| `connections.list` | `connections_cmd.py` | Wrapper | `test_connections_tools.py` |
| `connections.doctor` | `connections_cmd.py` | Wrapper | `test_connections_tools.py` |
| `components.list` | `components_cmd.py` | Wrapper | `test_components_tools.py` |
| `discovery.request` | `discovery.py` | + Caching | `test_discovery_tool.py` |
| `oml.schema.get` | `oml_validator.py` | + Export | `test_oml_tools.py` |
| `oml.validate` | `oml_validator.py` | Wrapper | `test_oml_tools.py` |
| `oml.save` | `session_logging.py` | Wrapper | `test_oml_tools.py` |
| `usecases.list` | - | New | `test_usecases_tool.py` |
| `generate_oml` | `llm_adapter.py` | New | `test_generate_tool.py` |

---

## APPENDIX B: Resource URI Schema

| Resource URI | Backend | TTL | Size Limit |
|-------------|---------|-----|------------|
| `osiris://discovery/<id>/overview.json` | In-memory cache | 24h | 50KB |
| `osiris://discovery/<id>/tables.json` | In-memory cache | 24h | 500KB |
| `osiris://oml/schema/v0.1.0.json` | Static file | Immutable | 20KB |
| `osiris://oml/drafts/<id>.json` | Session logs | Unlimited | 100KB |
| `osiris://usecases/<id>/oml_snippet_v1.json` | Static file | Immutable | 10KB |

---

## APPENDIX C: Error Code Taxonomy

| Family | Code Example | Meaning |
|--------|--------------|---------|
| `SCHEMA/*` | `SCHEMA/INVALID` | JSON schema validation failed |
| `SCHEMA/*` | `SCHEMA/MISSING_REQUIRED` | Required field missing |
| `SEMANTIC/*` | `SEMANTIC/UNKNOWN_COMPONENT` | Component not in registry |
| `SEMANTIC/*` | `SEMANTIC/INVALID_DEPENDENCY` | Step dependency not found |
| `DISCOVERY/*` | `DISCOVERY/CONNECTION_FAILED` | Database connection failed |
| `DISCOVERY/*` | `DISCOVERY/TIMEOUT` | Discovery exceeded time limit |
| `LINT/*` | `LINT/NAMING_CONVENTION` | Pipeline name doesn't follow convention |
| `POLICY/*` | `POLICY/UNAUTHORIZED` | User lacks permission |
| `POLICY/*` | `POLICY/QUOTA_EXCEEDED` | Rate limit exceeded |

---

## Conclusions and Next Steps

### Summary of Key Findings

This research reveals that implementing an MCP server for Osiris is not only feasible but offers significant advantages over the current chat interface:

1. **Technology Readiness**: FastMCP framework provides production-ready capabilities including in-memory testing, authentication, and deployment tools - all critical for enterprise adoption.

2. **Architecture Clarity**: The hybrid state management approach (server-side caching + client context) elegantly solves the tension between scalability and performance.

3. **Tool Design**: Starting with monolithic `generate_oml` for MVP while planning decomposed tools for v0.5 balances immediate delivery with future flexibility.

4. **Unique Differentiators**: Osiris can leverage its AIOP system and E2B integration to provide MCP capabilities that no other ETL tool currently offers.

5. **Risk Management**: All identified risks have viable mitigations, with FastMCP's testing framework addressing the historically challenging problem of MCP server validation.

### Recommended Action Plan

**Immediate Actions** (This Week):
1. **Decision Meeting**: Review this document with stakeholders to finalize critical decisions
2. **FastMCP Prototype**: Build minimal "hello world" MCP server to validate setup
3. **Schema Generation**: Implement OMLValidator.to_json_schema() method
4. **Team Alignment**: Ensure all developers understand MCP concepts and timeline

**Phase 1 Actions** (Week 1):
1. Set up FastMCP server structure with tool registration
2. Create basic error handling framework
3. Implement connection.list as first working tool
4. Establish testing patterns with in-memory fixtures

**Critical Path Items**:
- FastMCP server initialization must work before any tools
- Discovery caching is prerequisite for generation tools
- OML schema export blocks all validation tools
- Test infrastructure must be ready before Phase 2

### Open Questions Requiring User Decision

1. **Tool Granularity**: Should we implement decomposed generation tools in MVP or defer to v0.5?
   - Impact: Development time vs debugging capability
   - Recommendation: Defer to v0.5

2. **Caching Backend**: Should we add SQLite persistence in MVP?
   - Impact: Complexity vs durability
   - Recommendation: In-memory only for MVP

3. **Error Recovery**: How aggressive should auto-repair be?
   - Impact: User experience vs transparency
   - Recommendation: Single retry with explicit logging

4. **Testing Strategy**: What's the minimum test coverage for MVP release?
   - Impact: Quality vs speed
   - Recommendation: 80% coverage for tools, 100% for error paths

5. **Migration Timeline**: How aggressive should chat deprecation be?
   - Impact: User disruption vs maintenance burden
   - Recommendation: Gentle deprecation over 3 versions

### Success Metrics

The MCP implementation will be considered successful when:

1. **Functional Metrics**:
   - All MVP tools respond correctly to MCP client requests
   - OML generation achieves >90% first-pass validation success
   - Discovery caching reduces redundant database queries by >80%

2. **Performance Metrics**:
   - Tool response latency <500ms for cached operations
   - Discovery session creation <5 seconds for typical database
   - Memory usage <500MB for 100 concurrent sessions

3. **Quality Metrics**:
   - Zero regression in OML validation accuracy vs chat
   - Test coverage >80% for all MCP modules
   - All error responses follow structured format

4. **Adoption Metrics**:
   - Claude Desktop successfully connects and uses tools
   - At least one production pipeline generated via MCP
   - Positive feedback from early adopters

## References

### MCP Protocol & Specifications
- [Model Context Protocol Official Site](https://modelcontextprotocol.io/)
- [MCP Protocol Specification](https://modelcontextprotocol.io/docs/specification)
- [Anthropic MCP Announcement](https://www.anthropic.com/news/model-context-protocol)
- [Claude MCP Documentation](https://docs.claude.com/en/docs/mcp)

### SDK & Framework Documentation
- [MCP Python SDK (Official)](https://github.com/modelcontextprotocol/python-sdk)
- [FastMCP Framework](https://github.com/jlowin/fastmcp)
- [FastMCP Documentation](https://www.jlowin.dev/fastmcp)
- [MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk)

### Example MCP Servers
- [Awesome MCP Servers](https://github.com/wong2/awesome-mcp-servers)
- [Official MCP Example Servers](https://github.com/modelcontextprotocol/servers)
- [MSSQL MCP Server](https://github.com/bymcs/mssql-mcp)
- [PostgreSQL MCP Server](https://github.com/modelcontextprotocol/servers/tree/main/postgres)
- [Filesystem MCP Server](https://github.com/modelcontextprotocol/servers/tree/main/filesystem)

### Best Practices & Patterns
- [Stop Vibe-Testing Your MCP Server](https://www.jlowin.dev/blog/stop-vibe-testing-mcp-servers)
- [MCP Error Handling Guide](https://www.stainless.com/mcp/error-handling-and-debugging-mcp-servers)
- [Building Production MCP Servers](https://medium.com/data-engineering-with-dremio/building-a-basic-mcp-server-with-python)
- [MCP Testing Framework](https://github.com/haakco/mcp-testing-framework)

### Integration & Migration Guides
- [Connect Claude Code to MCP](https://docs.claude.com/en/docs/claude-code/mcp)
- [MCP Client Integration](https://modelcontextprotocol.io/docs/develop/build-client)
- [Claude Desktop Configuration](https://generect.com/blog/claude-mcp/)
- [VS Code MCP Integration](https://developer.microsoft.com/blog/10-microsoft-mcp-servers)

### Observability & Monitoring
- [MCP Observability with New Relic](https://newrelic.com/blog/nerdlog/introducing-mcp-support)
- [MCP Server Metrics Guide](https://zeo.org/resources/blog/mcp-server-observability-monitoring-testing-performance-metrics)
- [OpenTelemetry for MCP](https://devsecopsai.today/observability-for-mcp-server-otlp-mcp-servers-and-metrics)

### Academic & Industry Research
- [Model Context Protocol on Wikipedia](https://en.wikipedia.org/wiki/Model_Context_Protocol)
- [MCP Architecture Analysis](https://workos.com/blog/how-mcp-servers-work)
- [MCP Adoption Trends 2025](https://testguild.com/top-model-context-protocols-mcp/)
- [Enterprise MCP Deployment](https://dzone.com/articles/model-context-protocol-mcp-guide-architecture-uses-implementation)

---

## Document Metadata

**Document**: MCP Implementation Findings for Osiris
**Version**: 2.0.0
**Date**: October 10, 2025
**Author**: Claude (Anthropic)
**Status**: Complete - Ready for Review
**Classification**: Technical Research & Architecture

**Revision History**:
- v1.0.0 (Initial): Implementation file mapping
- v2.0.0 (Current): Comprehensive research and recommendations

**Distribution**: Osiris Development Team

---

**END OF DOCUMENT**
