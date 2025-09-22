# Osiris Pipeline - Crash Course

## Core Concepts

TODO: Deep dive into fundamental concepts:

### The Osiris Philosophy
TODO: Explain core principles:
- LLM-first approach vs template-based
- Conversational interface advantages
- Progressive discovery methodology
- Human-in-the-loop validation
- Deterministic execution guarantee

### Architecture Overview
TODO: System architecture:
```
User → Chat Interface → LLM Agent → OML Generation
                          ↓
                     Discovery Cache
                          ↓
                OML → Compiler → Manifest
                          ↓
                 Runner → Drivers → Data Flow
                          ↓
                    Session Logs
```

### Key Components

#### OML (Osiris Markup Language)
TODO: Complete OML specification:
- Version semantics (v0.1.0)
- Required fields: oml_version, name, steps
- Forbidden fields: version, connectors, tasks
- Step structure and modes
- Connection references

#### Component System
TODO: Component architecture:
- Component specifications (spec.yaml)
- Capabilities declaration
- Driver implementation
- Registry and discovery

#### Execution Model
TODO: Execution details:
- Three-phase execution: prepare, execute, collect
- ExecutionAdapter pattern
- Local vs E2B execution parity
- Driver protocol and data flow

#### Session Management
TODO: Session concepts:
- Session IDs and isolation
- Structured logging (events.jsonl, metrics.jsonl)
- Artifact management
- Session lifecycle

## Reading Logs

TODO: Log interpretation guide:

### Log Structure
```
logs/
└── run_<timestamp>/
    ├── events.jsonl       # Structured events
    ├── metrics.jsonl      # Performance metrics
    ├── artifacts/         # Generated files
    │   └── <step_id>/
    └── status.json        # Execution summary
```

### Event Types
TODO: Document all event types:
```json
// Discovery event
{
  "timestamp": "2024-01-15T10:00:00Z",
  "event_type": "discovery.schema",
  "session_id": "run_123",
  "data": {
    "table": "customers",
    "columns": ["id", "name", "email"]
  }
}

// TODO: Add more event examples:
// - compilation.start/complete
// - execution.step.start/complete
// - error events
// - metric events
```

### Metrics Analysis
TODO: Understanding metrics:
```json
// Performance metric
{
  "timestamp": "2024-01-15T10:00:05Z",
  "metric": "rows_written",
  "value": 1000,
  "step_id": "write_1",
  "tags": {
    "component": "filesystem.csv_writer"
  }
}

// TODO: Document all metrics:
// - rows_read
// - rows_written
// - execution_time_ms
// - memory_usage_mb
// - e2b_overhead_ms
```

### Using Log Bundles
TODO: AI-friendly log analysis:
```bash
# Generate bundle for AI
osiris logs bundle --session <id> > analysis.txt

# TODO: Explain bundle contents:
# - Manifest with comments
# - Resolved configs
# - Event timeline
# - Metrics summary
# - Artifact listing
```

## Working with OML

TODO: Advanced OML usage:

### OML Schema Deep Dive
```yaml
# TODO: Complete annotated schema
oml_version: "0.1.0"  # Required, exact match
name: "pipeline_name"  # Required, identifier
steps:  # Required, non-empty array
  - id: "step_1"  # Unique identifier
    component: "mysql.extractor"  # Component reference
    mode: "read"  # Execution mode
    config:  # Component-specific config
      connection: "@mysql.primary"  # Connection alias
      query: |  # Multi-line SQL
        SELECT *
        FROM customers
        WHERE created_at > '2024-01-01'
    inputs: {}  # Optional input mapping
```

### Connection Resolution
TODO: Connection precedence:
1. Inline configuration (highest priority)
2. Connection alias reference
3. Default connection
4. Environment variables

### Advanced Patterns
TODO: Complex OML patterns:

#### Multi-Step Pipeline
```yaml
# TODO: Example with multiple steps
# - Extract from MySQL
# - Transform with DuckDB
# - Write to multiple destinations
```

#### Dynamic Inputs
```yaml
# TODO: Example with input references
steps:
  - id: "transform_1"
    inputs:
      df: "${extract_1.output.df}"
```

#### Conditional Execution (Future)
```yaml
# TODO: Planned conditional syntax
```

## Troubleshooting

TODO: Systematic troubleshooting:

### Debugging Workflow
1. **Identify the phase**: Chat, Compile, or Run?
2. **Check logs**: What's the last successful event?
3. **Validate inputs**: Are connections valid?
4. **Test in isolation**: Can you run a simpler pipeline?
5. **Enable debug mode**: Get verbose output
6. **Check resources**: Memory, disk, network?

### Common Issues and Solutions

#### Chat/OML Generation Issues
TODO: Troubleshooting LLM issues:
```
Issue: OML generation fails repeatedly
Diagnosis:
1. Check LLM API key validity
2. Verify context size limits
3. Review discovery cache

Solutions:
- Simplify query requirements
- Clear discovery cache
- Switch LLM provider
```

#### Compilation Issues
TODO: Compilation troubleshooting:
```
Issue: Connection not found
Diagnosis:
1. Check osiris_connections.yaml
2. Verify connection alias
3. Check environment variables

Solutions:
- Add missing connection
- Fix typo in alias
- Export required env vars
```

#### Runtime Issues
TODO: Execution troubleshooting:
```
Issue: Pipeline fails mid-execution
Diagnosis:
1. Check step logs
2. Verify data availability
3. Check driver errors

Solutions:
- Fix SQL queries
- Handle missing data
- Increase timeout
```

### Performance Optimization
TODO: Performance tuning:

#### Memory Optimization
- Batch size tuning
- Query result limiting
- Streaming (future)

#### Query Optimization
- Index usage
- Partition pruning
- Pushdown filters

#### E2B Optimization
- Resource allocation
- Dependency caching
- Artifact compression

### Advanced Debugging
TODO: Deep debugging techniques:

#### Enable Trace Logging
```bash
export OSIRIS_LOG_LEVEL=TRACE
osiris run pipeline.oml
```

#### Inspect Compiled Manifest
```bash
osiris compile pipeline.oml --debug
cat compiled/manifest.yaml
```

#### Manual Driver Testing
```python
# TODO: Python snippet for testing drivers directly
```

## Best Practices

TODO: Production best practices:

### Development Workflow
1. Start with simple pipelines
2. Test with small datasets
3. Validate incrementally
4. Version control everything
5. Document assumptions

### Production Readiness
- Health checks before deployment
- Monitoring and alerting setup
- Backup and recovery plans
- Security audit
- Performance baselines

### Team Collaboration
- Shared connection configurations
- Git workflow for OML files
- Code review for pipelines
- Knowledge sharing via memory store

## Advanced Topics

TODO: Link to advanced content:
- [Component Development](../developer-guide/components.md)
- [Adapter Implementation](../developer-guide/adapters.md)
- [LLM Optimization](../developer-guide/llms.txt)
- [Contributing](../developer-guide/extending.md)
