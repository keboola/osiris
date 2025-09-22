# ADR-0027: AI Operation Package (AIOP)

## Status
Partially Accepted

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

### 2. Semantic / Ontology Layer
A formal semantic model of the pipeline manifest, OML definitions, component capabilities, and configuration metadata. This includes ontologies that define relationships between data, components, and execution semantics, enabling AI to reason about pipeline structure and intent.

### 3. Evidence Layer
Deterministic, timestamped, and citatable records of execution events, metrics, schema validations, errors, and warnings. This layer provides verifiable proof of what happened during the run, with stable IDs linking back to semantic entities, supporting auditability and traceability.

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

## Implementation Plan

TODO: Implementation phases:

### Phase 1: MVP (Week 1)
- Basic AIOP generation with Narrative, Semantic, and Evidence layers
- CLI command implementation (`osiris logs aiop`)
- Secret redaction and stable ID assignment

### Phase 2: Enhanced Context (Week 2)
- Full semantic ontology integration
- Execution timeline and detailed evidence
- AI analysis hints and narrative enrichment

### Phase 3: Control Layer (Week 3)
- Define and implement Control Layer interfaces
- Enable AI-driven operational commands

### Phase 4: Integration and Optimization (Week 4)
- AI model testing and feedback incorporation
- Performance tuning and compression support
- Documentation and tooling

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
