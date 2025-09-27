# ADR-0027: AI Operation Package (AIOP)

## Status
✅ **IMPLEMENTED** (September 2025)

*Milestone M2a completed with WU7a/b/c stabilization work. All 24 acceptance criteria met. Full production-ready AIOP system operational.*

## Context

The current approach of providing a simple HTML logs browser offers rich visualization for human operators but falls short for AI-driven analysis and operation. As AI assistants such as GPT, Claude, Gemini, and others become integral to pipeline management, we need to move beyond raw logs or simple context bundles. The vision is to create a comprehensive **AI Operation Package (AIOP)** that enables any large language model (LLM) to fully understand Osiris, the Osiris Modeling Language (OML), and the entire pipeline lifecycle—from intent and manifest through execution—allowing intelligent monitoring, debugging, and operation.

This package must teach the AI about Osiris core concepts, including determinism, DAG structure, and pipeline semantics. It should provide layered context that not only describes what happened, but why it happened, with stable, citatable evidence and actionable capabilities. The AIOP must be model-agnostic, structured in a standard format (JSON-LD) to facilitate interoperability and machine reasoning. It must be free of secrets and include stable identifiers for all components and events, enabling precise referencing and traceability.

The goal is for AI systems to gain a deep operational understanding of Osiris pipelines, including:

- The intent and design of the pipeline as expressed in the manifest and OML
- The semantic relationships and ontologies underpinning pipeline components and configurations
- Deterministic execution flow and causal relationships in the DAG
- Evidence and metrics supporting performance and correctness claims
- Control interfaces enabling AI-driven interventions, suggestions, and automated operations

This approach transforms AI integration from passive log analysis into active, intelligent pipeline operation.

## Decision

We will replace the concept of a simple "run export bundle" with a richer, multi-layered **AI Operation Package (AIOP)**. The AIOP is a structured, deterministic, secret-free, JSON-LD-based package designed to be fully consumable by any LLM or AI system. It consists of four distinct layers, each serving a critical role in enabling AI understanding and operation:

### 1. Narrative Layer
A human- and machine-readable narrative describing the pipeline run in natural language, including intent, causality, and high-level explanations. This layer contextualizes the execution, summarizing why steps were taken, what business rules apply, and how outcomes relate to expectations.

#### Narrative Context Sources (Precedence Order)
1. **Manifest/OML metadata** - Including optional `metadata.intent` field (trust: high)
2. **Repository context** - README.md, PIPELINE.md, Osiris.yaml, commit/PR messages (trust: medium)
3. **Run facts** - Metrics, DAG structure, artifacts, delta analysis (trust: high)
4. **Discovery summaries** - Aggregate statistics only, no raw data (trust: medium)
5. **Session chat logs** - Optional, opt-in only, appears in Annex NDJSON, never in Core (trust: low)

#### Intent Discovery & Provenance
The narrative layer tracks intent provenance with explicit trust levels:

```json
{
  "intent_known": true,
  "intent": "Extract customer data for quarterly reporting",
  "intent_provenance": [
    {"source": "manifest.metadata.intent", "trust": "high"},
    {"source": "commit.message.intent_line", "trust": "medium", "ref": "abc123"}
  ],
  "narrative": {
    "inputs": ["manifest", "repo_readme", "metrics", "dag"],
    "citations": ["ev.metric.total.rows_processed", "ev.artifact.export.csv"]
  }
}
```

- **intent_known**: Boolean flag indicating if explicit intent was found
- **intent_provenance**: Array tracking all intent sources with trust levels
- **Commit/PR convention**: Lines matching `intent: <text>` are extracted with medium trust
- **Fallback**: When intent_known:false, may include `inferred_from: ["dag", "artifacts"]`

#### Annex Policy for Sensitive Content
- **Core narrative**: Always ≤5 paragraphs, neutral tone, deterministic, no free-text
- **Annex-only content**: Session chat logs, commit/PR snippets, discovery details
- **Redaction**: All PII and secrets removed before Annex inclusion
- **Size limits**: Chat logs truncated to configured max_chars (default 2000)

#### Chat Logs Handling in Annex
Session chat logs integration for AI context understanding:

```json
{
  "annex": {
    "chat_logs.ndjson": [
      {"role": "user", "content": "[REDACTED] process customer data"},
      {"role": "assistant", "content": "I'll help you create a pipeline..."}
    ]
  }
}
```

- **Opt-in only**: Requires `aiop.narrative.session_chat.enabled: true`
- **Location**: `logs/<session>/artifacts/chat_log.json` or `logs/<session>/chat_log.json`
- **Redaction modes**:
  - `masked`: Apply PII/secret redaction via redact_secrets()
  - `quotes`: Include as-is with truncation only
  - `off`: Exclude from export entirely
- **Max size**: Truncated at configured max_chars (default 10000)
- **Export**: Written to Annex as `chat_logs.ndjson[.gz]`
- **Trust level**: Low - used only for intent discovery fallback

### 2. Semantic / Ontology Layer
A formal semantic model of the pipeline manifest, OML definitions, component capabilities, and configuration metadata. This includes ontologies that define relationships between data, components, and execution semantics, enabling AI to reason about pipeline structure and intent.

### 3. Evidence Layer
Deterministic, timestamped, and citatable records of execution events, metrics, schema validations, errors, and warnings. This layer provides verifiable proof of what happened during the run, with stable IDs linking back to semantic entities, supporting auditability and traceability.

#### Delta Analysis & Persistence
The Evidence layer includes delta analysis comparing runs of the same pipeline:

```json
{
  "delta": {
    "first_run": false,
    "delta_source": "by_pipeline_index",
    "rows": {
      "previous": 1000,
      "current": 1500,
      "change": 500,
      "change_percent": 50.0
    },
    "duration_ms": {
      "previous": 5000,
      "current": 4000,
      "change": -1000,
      "change_percent": -20.0
    },
    "errors_count": {
      "previous": 0,
      "current": 2,
      "change": 2
    }
  }
}
```

- **Index lookup**: Uses `logs/aiop/index/by_pipeline/<manifest_hash>.jsonl`
- **Comparison**: Previous successful run metrics vs current run
- **Deterministic rounding**: Percentages rounded to 2 decimal places
- **First run detection**: Returns `{"first_run": true}` when no history exists

### 4. Control Layer
Machine-actionable interfaces and metadata that allow AI systems to propose or execute interventions, such as configuration changes, reruns, or alerts. This layer encodes operational controls and constraints, enabling AI-driven pipeline management.

The AIOP will be:

- **Model-agnostic**: Designed to be usable by GPT, Claude, Gemini, or any future LLM.
- **JSON-LD based**: Leveraging linked data standards for semantic richness and interoperability.
- **Deterministic and stable**: Ensuring consistent IDs and references across runs.
- **Secret-free**: All sensitive information redacted or replaced with safe placeholders.
- **Comprehensive**: Covering from pipeline intent through execution, evidence, and control.

This approach will enable AI not just to analyze, but to deeply understand and operate Osiris pipelines intelligently and autonomously.

### AI Operation Package Structure (Example)

```
================================================================================
OSIRIS AI OPERATION PACKAGE (AIOP)
================================================================================
Session ID: run_1234567890
Pipeline: customer_etl_pipeline
Status: completed | failed | partial
Start Time: 2024-01-15T10:00:00Z
End Time: 2024-01-15T10:05:00Z
Duration: 5m 0s
Environment: local | e2b

================================================================================
NARRATIVE LAYER
================================================================================
# Natural language explanations of pipeline intent, causality, and outcomes

================================================================================
SEMANTIC / ONTOLOGY LAYER
================================================================================
# Formal semantic descriptions of manifest, OML, components, and configurations

================================================================================
EVIDENCE LAYER
================================================================================
# Timestamped, citatable records of execution events, metrics, schemas, errors

================================================================================
CONTROL LAYER
================================================================================
# Interfaces and metadata enabling AI-driven operational interventions

================================================================================
END OF PACKAGE
================================================================================
Generated: 2024-01-15T10:06:00Z
Osiris Version: 2.0.0
Package Format: 1.0
```

## Consequences

### Positive
- **AI-Friendly**: The AIOP provides a comprehensive, layered context that enables deep AI understanding and autonomous operation.
- **Debugging**: Rich narrative and evidence support precise root cause analysis and actionable suggestions.
- **Portability**: JSON-LD format ensures interoperability and ease of sharing.
- **Versioning**: Stable IDs and format versioning support long-term maintainability and evolution.
- **Security**: Strict redaction policies ensure no secrets are exposed.

### Negative
- **Size**: Packages may be large for complex pipelines.
- **Complexity**: Maintaining the multi-layered format requires additional effort.
- **Performance**: Package generation adds computational overhead.

### Neutral
- **Format Evolution**: The package format will evolve based on AI model feedback.
- **Integration**: Third-party tools will need to adapt to the new format.
- **Storage**: Organizations must manage retention and storage of AIOPs.

## Implementation

### Configuration & Precedence

**Implemented in code (commit b6ed2cc).** Configuration follows this precedence order:
```
Precedence: CLI > Environment variables ($OSIRIS_AIOP_*) > Osiris.yaml > built-in defaults
```

The configuration layer provides:
- Full precedence resolution with per-key source tracking
- Integration with `osiris init` for scaffold generation
- Effective config echoed in `metadata.config_effective`

**Automatic export is now supported when `aiop.enabled: true`** (Work Unit 4). Every run automatically generates an AIOP export with:
- Path templating to prevent overwrites
- Index files for LTM/GraphRAG discovery
- Retention policies to manage disk usage
- Latest symlink for convenience

Environment variables use the prefix `OSIRIS_AIOP_` for all AIOP-related settings. See Milestone M2a for the full list of Osiris.yaml keys, ENV mappings, and CLI interactions.

**Narrative-specific configuration:**
```yaml
aiop:
  narrative:
    sources: [manifest, repo_readme, commit_message, discovery]  # default
    session_chat:
      enabled: false      # opt-in for chat logs
      mode: masked        # masked|quotes|off
      max_chars: 2000     # truncation limit
      redact_pii: true    # PII removal before Annex
```

Environment variable mappings for narrative:
- `OSIRIS_AIOP_NARRATIVE_SOURCES` - Comma-separated list of sources
- `OSIRIS_AIOP_NARRATIVE_SESSION_CHAT_ENABLED` - true/false
- `OSIRIS_AIOP_NARRATIVE_SESSION_CHAT_MODE` - masked/quotes/off
- `OSIRIS_AIOP_NARRATIVE_SESSION_CHAT_MAX_CHARS` - Integer limit
- `OSIRIS_AIOP_NARRATIVE_SESSION_CHAT_REDACT_PII` - true/false

### Canonical Rules

**Core vs Annex Stratification:**
- Core: Size ≤ max_core_bytes with deterministic truncation and explicit markers
- Annex: Optional NDJSON shards with full data; includes annex_ref pointers from Core

**URI Scheme (no trailing slashes):**
- Run: `osiris://run/@<session_id>`
- Pipeline: `osiris://pipeline/<name>@<manifest_hash>`
- Step: `osiris://pipeline/<name>@<manifest_hash>/step/<step_id>`
- Artifact: `osiris://run/@<session_id>/artifact/<repo_rel_path>`
- Evidence: `osiris://run/@<session_id>/evidence/<evidence_id>`

**Run Fingerprint:**
Computed for reproducibility as `SHA-256({version}:{env}:{manifest}:{session}:{timestamp})` but not used in URIs (URIs use session_id directly).

**Evidence IDs:**
Format: `ev.<type>.<step_id>.<name>.<ts_ms>`
- Name charset: `[a-z0-9_]` only (spaces and dashes converted to underscores)
- Timestamps: UTC milliseconds since epoch

**Delta Behavior:**
- Comparison by `pipeline@manifest_hash` to find previous run
- First runs set `delta.first_run: true` instead of comparison values

### GraphRAG Preparation

The JSON-LD @context is stabilized and versioned with terms for DAG relationships:
- `produces`, `consumes`, `depends_on`: Step relationships
- `materializes`, `verifies`, `remediates`: Run-level relationships

Graph index included in Core with:
- Node/edge counts, context version, canonical hash
- 1-to-1 mapping between evidence_id and @id

Annex NDJSON ingestion follows one record per line with required back-references to run_session_id.

### Context Hosting

For M2a, the @context will be hosted at `docs/reference/aiop.context.jsonld` in the repository (or via raw GitHub URL). Future production deployments may use a custom domain alias.

## Implementation Status

**✅ COMPLETE**: Full implementation delivered in Milestone M2a (September 2025).

### Architecture Delivered

The production AIOP system implements a four-layer architecture with deterministic, secret-free exports:

1. **Evidence Layer**: Timestamped events, metrics aggregation, artifact tracking with stable IDs
2. **Semantic Layer**: DAG representation, component registry, OML specification embedding
3. **Narrative Layer**: Intent discovery with provenance, natural language descriptions, evidence citations
4. **Metadata Layer**: LLM primer, configuration effective, size hints, delta analysis

### Key Features Operational

- **Autopilot Export**: Automatic AIOP generation after every run (success/failure)
- **CLI Integration**: `osiris logs aiop` command with JSON/Markdown formats
- **Size Control**: Core/Annex policies with configurable truncation
- **Security**: Comprehensive DSN redaction and secret masking
- **Determinism**: Stable output for reproducible analysis
- **Configuration**: Full precedence (CLI > ENV > YAML > defaults)
- **Parity**: Identical structure for local and E2B execution

### Quality Assurance

- **921 tests passing** with comprehensive coverage
- **Parity validation** between execution environments
- **Secret detection** with redaction guarantees
- **Performance optimized** for LLM consumption
- **Delta analysis** with run-over-run comparison
- **Intent discovery** with multi-source provenance

### APIs & Stability

**Stable public APIs** for M2a completion:
- `osiris logs aiop` CLI interface
- AIOP JSON-LD structure and @context
- Configuration schema in osiris.yaml
- Environment variable mappings

**Internal APIs** (subject to evolution):
- `build_aiop()` function signatures
- Evidence ID generation schemes
- Truncation algorithms

### Future Roadmap

While M2a is complete, the following enhancements are planned:

- **M2b**: Real-time AIOP streaming during execution
- **M3**: Full discovery ingestion and catalog storage (ADR-0029)
- **M4**: Control Layer implementation for AI-driven operations
- **GraphRAG**: Enhanced triple generation and embedding support

## Graph Export Hints for Future GraphRAG

The AIOP will include optional "graph hints" designed to prepare for future GraphRAG (Graph-based Retrieval-Augmented Generation) systems. This is not a full knowledge graph implementation, but rather strategic metadata that enables future graph construction.

### Triple Generation Strategy
The package will emit RDF-style triples following the pattern `[subject, predicate, object]`:

```json
{
  "graph_hints": {
    "triples": [
      ["osiris://run/@run_123", "rdf:type", "osiris:PipelineRun"],
      ["osiris://run/@run_123", "osiris:executedPipeline", "customer_etl"],
      ["osiris://run/@run_123", "osiris:hasStep", "osiris://run/@run_123/step/extract"],
      ["osiris://run/@run_123/step/extract", "osiris:rowsProcessed", "10234"],
      ["osiris://run/@run_123/step/extract", "osiris:followedBy", "osiris://run/@run_123/step/write"]
    ]
  }
}
```

### LTM (Long-Term Memory) Touchpoints
The package identifies key patterns and metrics that should be tracked across runs for organizational learning:

```json
{
  "ltm_touchpoints": {
    "pipeline_pattern": "mysql_to_csv_export",
    "data_lineage": ["source.mysql.customers", "target.csv.output"],
    "performance_baseline": {
      "p50_duration_ms": 323000,
      "p95_duration_ms": 451000
    },
    "failure_signatures": [],
    "schema_evolution": {
      "source.mysql.customers": "v2.1"
    }
  }
}
```

### Embedding-Ready Content
Specific text fields will be marked as suitable for vector embedding:

```json
{
  "embeddings_ready": [
    "narrative.summary",      // Natural language description
    "semantic.intent",         // Business purpose
    "evidence.errors[].message" // Error messages for similarity search
  ]
}
```

## Security Considerations for GraphRAG

When preparing graph hints and LTM touchpoints, the following security measures apply:

1. **No PII in Triples**: Entity URIs use stable IDs, never user data
2. **Aggregated Metrics Only**: Performance baselines use statistical aggregates
3. **Schema Fingerprints**: Schema versions use hashes, not actual schemas
4. **Lineage Abstraction**: Data lineage uses logical names, not physical paths

## References
- Issue #XXX: AI-friendly log format request
- ADR-0003: Session-scoped logging (related)
- Claude/ChatGPT best practices for context
- JSON-LD and linked data standards
- docs/milestones/m2a-aiop.md: Implementation plan for M2a

## Notes on Milestone M1

**Implementation Status**: Partially implemented in Milestone M1. Integration postponed to Milestone M2.

The context builder foundation has been implemented, but the full AI Operation Package described in this ADR has not yet been fully integrated:
- **Context builder implemented**: `osiris/prompts/build_context.py` - Builds minimal component context for LLM consumption
- **JSON schema defined**: `osiris/prompts/context.schema.json` - Schema for context format with strict validation
- **CLI command exists**: `osiris prompts build-context` - Generates component context with caching and fingerprinting

What has NOT been implemented:
- **AIOP generation**: The `osiris logs aiop` command does not exist
- **Full AI-optimized run export**: No integration between run logs and AI context in multi-layered package format
- **Enhanced context sections**: Timeline, metrics summary, AI hints not implemented in package form
- **Control Layer**: Operational interfaces for AI-driven control not yet implemented

Current state:
- The context builder successfully generates a minimal (~330 token) JSON representation of component capabilities
- It includes SHA-256 fingerprinting and disk caching for efficiency
- NO-SECRETS guarantee implemented with comprehensive secret filtering
- Session-aware logging with structured events

The full AI Operation Package feature is postponed to Milestone M2 for implementation alongside other AI enhancement features.

## Acceptance Criteria for M2a Implementation

### Core Package Generation
- [ ] `osiris logs aiop --session <id>` generates valid JSON-LD package
- [ ] Package size ≤300 KB by default (configurable via `--max-core-bytes`)
- [ ] All three layers present: Narrative, Semantic, Evidence
- [ ] Deterministic output for same input (stable IDs and ordering)
- [ ] NO secrets in output (comprehensive redaction)

### Narrative Layer Requirements
- [ ] Narrative sets `intent_known: true/false` deterministically
- [ ] Intent provenance tracked with trust levels (high/medium/low)
- [ ] Session chat logs appear only in Annex when explicitly enabled
- [ ] All narrative claims cite evidence IDs (ev.*)
- [ ] Narrative.inputs array lists contributing sources
- [ ] Secrets and PII never leak into narrative
- [ ] Core narrative remains ≤5 paragraphs

### GraphRAG Preparation
- [ ] Graph hints section includes valid RDF triples
- [ ] LTM touchpoints identify pipeline patterns and baselines
- [ ] Embedding-ready fields marked for vector generation
- [ ] Triple URIs follow osiris:// scheme without trailing slashes

### Annex Shards (Optional)
- [ ] `--policy annex` generates NDJSON shard files
- [ ] Timeline, metrics, errors exported as separate streams
- [ ] Core package includes references to annex files

### Validation & Testing
- [ ] JSON Schema validation for package structure
- [ ] Secret scanning tests pass (no PII/credentials)
- [ ] Performance: <5s generation for typical runs
- [ ] Cross-referenced evidence IDs resolve correctly
- [ ] Delta calculation works correctly for first run, subsequent runs, and missing previous runs

## Future Work

Beyond the current M2a implementation, the following work units are planned:

### Work Unit 2: Intent Discovery & Provenance
Implement comprehensive intent discovery from multiple sources with provenance tracking. See [Work Unit 2 in m2a-aiop.md](../milestones/m2a-aiop.md#work-unit-2--intent-discovery--provenance-mvp) for detailed scope.

### Work Unit 3: Delta Analysis
Implement run-over-run delta comparison by manifest_hash with caching. See [Work Unit 3 in m2a-aiop.md](../milestones/m2a-aiop.md#work-unit-3--delta-analysis-mvp) for implementation details.

### Future Milestones
- **M2b**: Real-time AIOP streaming during execution
- **M3**: Full discovery ingestion and catalog storage (ADR-0029)
- **M4**: Control Layer implementation for AI-driven operations
