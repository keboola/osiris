# ADR-0031: OML Control Flow and Conditional Execution

## Status
Proposed

## Context
The current OML (Osiris Markup Language) v0.1.0 only supports linear pipeline execution. As pipelines become more complex, there's a need for conditional execution, branching, and iteration patterns. Modern orchestrators like Prefect and Dagster support sophisticated control flow, and Osiris should provide similar capabilities while maintaining simplicity and determinism.

## Problem
- Pipelines often need conditional execution based on data characteristics (e.g., skip processing if no new data)
- Some workflows require branching logic (e.g., different transformations for different data types)
- Batch processing often needs fan-out/fan-in patterns for parallel processing
- Current OML lacks these control flow primitives

## Constraints
- Must maintain deterministic compilation (no runtime surprises)
- Control flow must be declarative, not imperative
- Must be simple enough for LLMs to generate correctly
- Should not require changes to existing linear pipelines
- Security: conditions must not expose secrets

## Decision
Add declarative control flow primitives to OML:

### 1. Conditional Execution (`when` clause)
```yaml
steps:
  - id: check-data
    component: mysql.extractor
    config:
      query: "SELECT COUNT(*) as cnt FROM new_records"
    outputs: [record_count]

  - id: process-data
    component: data.transformer
    when: "${steps.check-data.outputs.record_count.cnt} > 0"
    inputs: [new_data]
```

### 2. Simple Branching (`branch` blocks)
```yaml
steps:
  - id: classify-data
    component: data.classifier
    outputs: [data_type]

  - branch:
      when: "${steps.classify-data.outputs.data_type} == 'structured'"
      then:
        - id: process-structured
          component: structured.processor
      else:
        - id: process-unstructured
          component: unstructured.processor
```

### 3. Fan-out/Fan-in for Parallel Processing
```yaml
steps:
  - id: list-tables
    component: mysql.discovery
    outputs: [table_list]

  - fan_out:
      over: "${steps.list-tables.outputs.table_list}"
      as: table
      step:
        id: "extract-${table}"
        component: mysql.extractor
        config:
          table: "${table}"

  - fan_in:
      from: "extract-*"
      mode: concat
      outputs: [all_data]
```

## Alternatives Considered
1. **Imperative scripting**: Allow Python/bash snippets for control flow (rejected: breaks determinism)
2. **External orchestrator only**: Delegate all control flow to Airflow/Prefect (rejected: limits Osiris autonomy)
3. **Complex DSL**: Full programming language features (rejected: too complex for LLMs)

## Consequences
### Positive
- Enables more sophisticated pipelines without external orchestration
- Maintains declarative, deterministic nature
- Simple enough for LLM generation
- Compatible with existing linear pipelines

### Negative
- Increases compiler complexity
- Requires careful validation to prevent cycles
- May complicate debugging

## Implementation Notes
- Compiler (M1c) translates control flow to expanded DAG
- Runner (M1d) executes based on runtime conditions
- All conditions evaluated using safe expression evaluator (no code execution)
- Branch selection logged in events for audit trail

## Status Tracking
- Phase 1 (M2): Basic `when` conditions
- Phase 2 (M3): Branch blocks
- Phase 3 (M4): Fan-out/fan-in patterns