# AIOP Architecture: AI Operation Package

**Status**: Production (v0.3.0+)
**Last Updated**: September 2025
**Scope**: Technical architecture for AI Operation Package system

---

## Overview

The AI Operation Package (AIOP) is a deterministic, secret-free export system that transforms Osiris pipeline runs into AI-consumable structured data. AIOP enables LLMs to understand, analyze, and debug pipeline executions through multi-layered semantic context.

**Design Principles**:
- **Model-agnostic**: Works with any LLM (GPT, Claude, Gemini, etc.)
- **Deterministic**: Same inputs produce identical outputs
- **Secret-free**: Comprehensive redaction with zero-leak guarantee
- **Size-controlled**: Configurable truncation for LLM consumption
- **Parity**: Identical structure across execution environments

---

## System Architecture

### Data Flow Diagram

```mermaid
graph TD
    RUN[Pipeline Run] --> EVENTS[events.jsonl]
    RUN --> METRICS[metrics.jsonl]
    RUN --> ARTIFACTS[Artifacts/]

    EVENTS --> BUILDER[build_aiop]
    METRICS --> BUILDER
    ARTIFACTS --> BUILDER
    MANIFEST[Manifest] --> BUILDER
    CONFIG[osiris.yaml] --> BUILDER

    BUILDER --> CORE[Core JSON ≤300KB]
    BUILDER --> ANNEX[Annex NDJSON Unlimited]
    BUILDER --> RUNCARD[Markdown Run-card]

    CORE --> INDEX[Index Files]
    CORE --> LLM[LLM Consumers]
    ANNEX --> ANALYSIS[Analysis Tools]
    RUNCARD --> HUMAN[Human Review]

    INDEX --> DELTA[Delta Analysis]
    DELTA --> BUILDER
```

### Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AIOP Export Engine                       │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────┐ │
│ │   Evidence  │ │  Semantic   │ │  Narrative  │ │Metadata │ │
│ │    Layer    │ │    Layer    │ │    Layer    │ │  Layer  │ │
│ └─────────────┘ └─────────────┘ └─────────────┘ └─────────┘ │
├─────────────────────────────────────────────────────────────┤
│                   Core Stratification                       │
│ ┌─────────────────────────────┐ ┌─────────────────────────┐ │
│ │        Core Package         │ │      Annex Shards       │ │
│ │    (≤300KB, LLM-ready)      │ │   (Unlimited NDJSON)    │ │
│ └─────────────────────────────┘ └─────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                     Security Layer                          │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │  DSN Redaction • Field Filtering • PII Protection       │ │
│ └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                   Configuration System                      │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │     CLI > ENV > YAML > Defaults (Precedence)            │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## Layer Architecture

### 1. Evidence Layer
**Purpose**: Citeable, timestamped records of execution
**Content**: Timeline events, metrics aggregation, artifact tracking

**Key Components**:
- **Timeline**: Chronologically ordered events with stable IDs
- **Metrics**: Step-level and aggregate statistics
- **Errors**: Complete error records with context
- **Artifacts**: File references with checksums and metadata
- **Delta**: Run-over-run comparison via index lookup

**Evidence ID Format**: `ev.<type>.<step_id>.<name>.<timestamp_ms>`
- Charset: `[a-z0-9_]` only
- Timestamp: UTC milliseconds since epoch
- Examples: `ev.metric.extract.rows_read.1705315200000`

### 2. Semantic Layer
**Purpose**: Formal model of pipeline structure and relationships
**Content**: DAG, components, OML specification

**Key Components**:
- **DAG**: Nodes and edges with relationship types (`produces`, `consumes`, `depends_on`)
- **Components**: Registry integration with capabilities and schema
- **OML**: Embedded specification with version tracking
- **Manifest**: Pipeline fingerprint and metadata

### 3. Narrative Layer
**Purpose**: Natural language descriptions with evidence citations
**Content**: Intent discovery, causal explanations, provenance

**Key Components**:
- **Intent Discovery**: Multi-source intent with trust levels
  - Manifest metadata (high trust)
  - README/commit messages (medium trust)
  - Chat logs (low trust, opt-in only)
- **Provenance**: Explicit source tracking for all claims
- **Citations**: All statements link to evidence IDs
- **Transparency**: `narrative.inputs` array lists all sources

### 4. Metadata Layer
**Purpose**: Package metadata and LLM affordances
**Content**: Configuration, size hints, LLM primer

**Key Components**:
- **LLM Primer**: Osiris concepts, glossary, best practices
- **Controls**: Example commands for debugging and analysis
- **Config Effective**: Per-key configuration with source tracking
- **Size Hints**: Token estimates and chunking guidance
- **Delta**: Previous run comparison with percentage changes

---

## LLM Affordances

### Primer System
Every AIOP includes educational content for AI systems:

```json
{
  "metadata": {
    "llm_primer": {
      "about": "Structured guide to Osiris pipeline concepts...",
      "glossary": {
        "run": "Single execution instance of a pipeline with deterministic session ID",
        "step": "Atomic operation in pipeline DAG with specific component",
        "manifest_hash": "Deterministic fingerprint of compiled pipeline...",
        "delta": "Comparison metrics with previous run of same pipeline"
      }
    }
  }
}
```

### Control Examples
Actionable command templates for AI debugging:

```json
{
  "controls": {
    "examples": [
      {
        "command": "osiris logs aiop --session run_123",
        "title": "Export this run's AIOP",
        "notes": "Get machine-readable analysis package"
      },
      {
        "command": "osiris run --last-compile --dry-run",
        "title": "Replay with dry-run",
        "notes": "Test configuration without execution"
      }
    ]
  }
}
```

---

## Security Architecture

### Redaction Pipeline

```mermaid
flowchart TD
    %% Stages with visually distinctive colors
    Input["Input Data"]:::stage1
    Raw["Raw JSON"]:::stage1sub

    Scanner["Field Scanner"]:::stage2
    Identify["Identify<br/>Secrets"]:::stage2sub

    Parser["DSN Parser"]:::stage3
    Extract["Extract URLs<br/>&amp; Params"]:::stage3sub

    Masker["Connection Masker"]:::stage4
    MaskCreds["Mask Creds<br/>with ***"]:::stage4sub

    Output["Output"]:::stage5
    Clean["Clean JSON"]:::stage5sub

    %% Diagonal arrangement    
    Input --> Scanner
    Scanner --> Parser
    Parser --> Masker
    Masker --> Output

    Raw --> Identify
    Identify --> Extract
    Extract --> MaskCreds
    MaskCreds --> Clean

    %% Vertical stage connections
    Input --> Raw
    Scanner --> Identify
    Parser --> Extract
    Masker --> MaskCreds
    Output --> Clean

    %% Style definitions for vibrant colors
    classDef stage1 fill:#E9F7EF,stroke:#27AE60,stroke-width:2px;
    classDef stage1sub fill:#D4EFDF,stroke:#27AE60,stroke-width:1.5px;
    classDef stage2 fill:#FEF9E7,stroke:#F4D03F,stroke-width:2px;
    classDef stage2sub fill:#FCF3CF,stroke:#F4D03F,stroke-width:1.5px;
    classDef stage3 fill:#EBF5FB,stroke:#2980B9,stroke-width:2px;
    classDef stage3sub fill:#D6EAF8,stroke:#2980B9,stroke-width:1.5px;
    classDef stage4 fill:#FDEDEC,stroke:#C0392B,stroke-width:2px;
    classDef stage4sub fill:#FADBD8,stroke:#C0392B,stroke-width:1.5px;
    classDef stage5 fill:#F9EBEA,stroke:#7D3C98,stroke-width:2px;
    classDef stage5sub fill:#E8DAEF,stroke:#7D3C98,stroke-width:1.5px;
```

### Security Guarantees

1. **Field-Level Filtering**: Recursive scanning for `password`, `key`, `token`, `secret` fields
2. **DSN Masking**: Connection string credentials replaced with `***`
   - `postgres://user:pass@host/db` → `postgres://***@host/db`
   - `redis://:password@host:port` → `redis://***@host:port`
3. **Query Parameter Redaction**: URL parameters containing sensitive keys
4. **PII Protection**: Configurable redaction for chat logs and free text

**Test Coverage**: Comprehensive secret injection tests with zero-leak validation

### Threat Model

**Protected Against**:
- Credential leakage in logs or exports
- DSN exposure in configuration dumps
- PII inclusion in narrative content
- Secret persistence in artifacts

**Not Protected Against** (by design):
- Schema names and table structures (intentionally included)
- Performance metrics and row counts (business-relevant)
- Pipeline logic and component usage (needed for analysis)

---

## Performance Architecture

### Size Control Strategy

**Core Package Limits**:
- Default: ≤300KB for optimal LLM consumption
- Configurable: `max_core_bytes` setting
- Truncation: Object-level with explicit markers

**Annex Offloading**:
- Policy: `core` (default) vs `annex` (unlimited)
- Format: NDJSON for streaming ingestion
- Compression: Optional gzip/zstd for large datasets

### Truncation Algorithm

1. **Priority Ordering**: Events > Metrics > Artifacts > Timeline details
2. **Preservation**: Always keep essential narrative and semantic layers
3. **Markers**: Explicit `truncated: true` and `dropped_count` indicators
4. **References**: Annex pointers when content moved to shards

### Performance Metrics

**Target Performance**:
- Generation time: <2 seconds for typical runs
- Memory usage: <50MB during export
- Core size: ≤300KB (90% compliance)
- Parity overhead: <1% between local/E2B

**Monitoring**:
- Size distribution tracking
- Generation time percentiles
- Truncation frequency analysis

---

## Data Persistence

### Index Architecture

```
logs/aiop/index/
├── runs.jsonl              # All runs chronologically
├── by_pipeline/
│   ├── {hash1}.jsonl       # Runs by manifest hash
│   ├── {hash2}.jsonl       # For delta analysis
│   └── ...
└── by_status/
    ├── completed.jsonl     # Successful runs
    ├── failed.jsonl        # Failed runs
    └── interrupted.jsonl   # Partial runs
```

### File Organization

```
logs/aiop/
├── {session_id}_aiop.json     # Core exports
├── {session_id}_runcard.md    # Human summaries
├── latest.json                # Symlink to newest
├── index/                     # Catalogs for lookup
└── annex/                     # NDJSON shards
    ├── timeline.ndjson[.gz]
    ├── metrics.ndjson[.gz]
    └── errors.ndjson[.gz]
```

### Retention Policies

**Configurable Cleanup**:
- `keep_runs`: Number of core exports to retain
- `annex_keep_days`: Age-based cleanup for large files
- `index_compact`: Periodic index optimization

**Automated Triggers**:
- Post-run cleanup after each export
- Manual: `osiris aiop prune` command
- Scheduled: Via external cron/scheduler

---

## Configuration Architecture

### Precedence Hierarchy

```
1. CLI Flags           (--max-core-bytes 500000)
   ↓
2. Environment         (OSIRIS_AIOP_MAX_CORE_BYTES=500000)
   ↓
3. YAML Configuration  (aiop.max_core_bytes: 500000)
   ↓
4. Built-in Defaults   (300000)
```

### Configuration Schema

**Core Settings**:
```yaml
aiop:
  enabled: bool                    # Auto-export toggle
  policy: core|annex               # Size strategy
  max_core_bytes: int              # Truncation threshold
  timeline_density: low|med|high   # Event filtering
  metrics_topk: int                # Top metrics count
```

**Path Templating**:
```yaml
output:
  core_path: "logs/aiop/{session_id}_aiop.json"
  run_card_path: "logs/aiop/{session_id}_runcard.md"
```

**Template Variables**:
- `{session_id}`: Run session identifier
- `{ts}`: ISO timestamp
- `{status}`: Run outcome (completed/failed/interrupted)
- `{manifest_hash}`: Pipeline fingerprint

---

## Integration Points

### CLI Integration
- **Entry Point**: `osiris logs aiop` command
- **Auto-Export**: Post-run hook in `cli/run.py`
- **Exit Codes**: 0=success, 4=truncated, 1=error, 2=not-found

### E2B Integration
- **Parity Requirement**: Identical AIOP structure local vs cloud
- **Artifact Collection**: Transparent file retrieval
- **Session Mapping**: Consistent session IDs across environments

### Future GraphRAG Preparation
- **Triple Hints**: RDF-style relationship extraction
- **Embedding Tags**: Content marked for vector generation
- **LTM Touchpoints**: Organizational memory integration points

---

## Quality Assurance

### Testing Strategy

**Determinism Tests**:
- Same input → identical AIOP output
- Stable ID generation across runs
- Sorted JSON keys and arrays

**Parity Tests**:
- Local vs E2B structural comparison
- Session-normalized output validation
- Performance characteristic alignment

**Security Tests**:
- Secret injection with zero-leak validation
- DSN redaction across all connection types
- PII detection and masking verification

**Performance Tests**:
- Size limit compliance
- Generation time benchmarks
- Memory usage profiling

### Monitoring

**Quality Metrics**:
- Test coverage: >90% for AIOP modules
- Parity success rate: >99.9%
- Secret detection: 100% (zero false negatives)
- Size compliance: >90% under limits

---

## Evolution Strategy

### API Stability
**Stable (Public)**:
- CLI interface and exit codes
- AIOP JSON-LD structure
- Configuration schema
- Environment variables

**Evolving (Internal)**:
- Build function signatures
- Evidence ID schemes
- Truncation algorithms
- Index file formats

### Future Enhancements

**M2b - Real-time Streaming**:
- Live AIOP updates during execution
- WebSocket/SSE delivery
- Incremental export building

**M3 - Discovery Integration**:
- Schema catalog inclusion
- Data lineage mapping
- Organizational memory

**M4 - Control Layer**:
- Actionable AI interfaces
- Pipeline modification capabilities
- Automated remediation hooks

---

This architecture document serves as the technical foundation for understanding AIOP's design, implementation, and operational characteristics. It guides both development decisions and operational practices for the AI Operation Package system.
