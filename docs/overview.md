# Osiris Pipeline Overview

## Introduction

TODO: Write comprehensive introduction covering:
- What is Osiris Pipeline
- Key value proposition (LLM-first conversational ETL)
- Target audience (data engineers, analysts, ML engineers)
- How it differs from traditional ETL tools
- Quick example of conversational pipeline creation

## Conceptual Flow

TODO: Explain the high-level flow:
- User describes data needs in natural language
- AI discovers database schemas progressively
- OML (Osiris Markup Language) generation
- Compilation to deterministic manifest
- Execution in local or E2B cloud environment
- Session-scoped logging and artifacts

### Diagram 1: Chat → OML State Machine

```mermaid
stateDiagram-v2
    [*] --> INIT
    INIT --> INTENT_CAPTURED: User describes need
    INTENT_CAPTURED --> DISCOVERY: Schema exploration
    DISCOVERY --> OML_SYNTHESIS: Generate pipeline
    OML_SYNTHESIS --> VALIDATE_OML: Validate syntax
    VALIDATE_OML --> REGENERATE_ONCE: Validation failed
    REGENERATE_ONCE --> VALIDATE_OML: Retry
    VALIDATE_OML --> COMPILE: Valid OML
    COMPILE --> RUN: Execute pipeline
    RUN --> COMPLETE: Success

    note right of DISCOVERY
        TODO: Add details about:
        - Progressive profiling
        - Cache fingerprinting
        - Discovery snapshots
    end note

    note right of OML_SYNTHESIS
        TODO: Add details about:
        - OML v0.1.0 schema
        - Required/forbidden keys
        - Connection resolution
    end note
```

## Detailed Execution

TODO: Deep dive into execution model:

### Local Execution
- ExecutionAdapter pattern
- LocalAdapter implementation
- Driver registration and lookup
- In-memory data caching between steps
- Artifact generation

### E2B Cloud Execution
- Transparent proxy architecture
- RPC communication protocol
- Sandbox lifecycle management
- Artifact synchronization
- Performance characteristics (<1% overhead)

### Diagram 2: Compile Pipeline

```mermaid
graph LR
    subgraph "Compilation Process"
        OML[OML File] --> Parser[Parse & Validate]
        Parser --> Resolver[Resolve Connections]
        Resolver --> Fingerprint[Generate Fingerprints]
        Fingerprint --> Manifest[Deterministic Manifest]

        Config[osiris_connections.yaml] --> Resolver
        Env[Environment Variables] --> Resolver
    end

    style OML fill:#f9f,stroke:#333,stroke-width:2px
    style Manifest fill:#9f9,stroke:#333,stroke-width:2px

    %% TODO: Add more detail about:
    %% - Connection precedence rules
    %% - Secret masking during compilation
    %% - Fingerprint calculation
    %% - Manifest structure
```

### Diagram 3: Run Pipeline

```mermaid
graph TB
    subgraph "Runtime Execution"
        Start[Start Runner] --> Adapter{Local or E2B?}

        Adapter -->|Local| LocalRun[LocalAdapter]
        Adapter -->|E2B| E2BRun[E2BTransparentProxy]

        LocalRun --> Drivers[Load Drivers]
        E2BRun --> Sandbox[Create Sandbox]
        Sandbox --> ProxyWorker[Deploy ProxyWorker]
        ProxyWorker --> Drivers

        Drivers --> Execute[Execute Steps]
        Execute --> Artifacts[Generate Artifacts]
        Artifacts --> Logs[Session Logs]

        Logs --> Complete[Pipeline Complete]
    end

    style Start fill:#f9f,stroke:#333,stroke-width:2px
    style Complete fill:#9f9,stroke:#333,stroke-width:2px

    %% TODO: Add details about:
    %% - Driver protocol (run method)
    %% - Data flow between steps
    %% - Metric collection
    %% - Error handling & retry
```

## Error Handling

TODO: Document error handling strategies:

### Compilation Errors
- OML validation failures
- Missing connections
- Invalid configurations
- Schema mismatches

### Runtime Errors
- Driver failures
- Connection issues
- Data validation errors
- E2B sandbox errors

### Recovery Strategies
- Retry policies
- HITL (Human-In-The-Loop) escalation
- Session preservation
- Partial execution recovery

### Error Reporting
- Structured error events
- Human-readable messages
- Debug information in logs
- Troubleshooting guides

## Performance Considerations

TODO: Add performance guidelines:
- Memory usage with large datasets
- Streaming vs in-memory processing
- E2B overhead characteristics
- Optimization strategies

## Security Model

TODO: Document security features:
- Secret masking in logs
- Connection isolation
- E2B sandbox security
- Data privacy considerations

## Next Steps

TODO: Link to other guides:
- [Getting Started Guide](user-guide/kickstart.md)
- [How-To Guide](user-guide/how-to.md)
- [Developer Guide](developer-guide/components.md)
- [API Reference](#) - TODO: Create API docs
