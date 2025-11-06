# ADR-0037: MCP Component LLM Guidance System

**Status**: Proposed
**Date**: 2025-11-06
**Authors**: Osiris Team
**Related**: ADR-0036 (MCP Interface)

## Context

### Current State (MCP v0.5.0)

When an LLM generates OML pipelines via MCP, it must make configuration decisions based solely on:
1. **Component spec JSON schemas** - Defines what fields exist and their types
2. **LLM's general knowledge** - Generic understanding of databases, ETL patterns
3. **Trial and error** - Generate → validate → regenerate cycle

**Example: Creating a Supabase writer step**

Current MCP interaction:
1. LLM sees component spec: `components/supabase.writer/spec.yaml`
2. Spec shows fields like `create_if_missing: boolean`, `mode: string`
3. LLM must guess appropriate values based on context
4. User discovers missing `create_if_missing: true` only at runtime

**Problems**:
- **No contextual defaults**: LLM doesn't know `create_if_missing: true` is recommended for prototyping
- **Silent failures**: Missing table errors happen at execution time, not generation time
- **Ambiguous choices**: `mode: append|replace|upsert` has no guidance on when to use each
- **Repetitive questions**: LLM asks same clarifying questions for every pipeline

### Real-World Example

Today's movie pipeline generation via MCP:
```
User: "Create pipeline to join movies and reviews, write to Supabase"

MCP → LLM generates OML:
  - id: write-to-supabase
    component: supabase.writer
    config:
      table: movie_success
      mode: replace
      # ❌ Missing create_if_missing: true

Result: Pipeline fails at runtime:
  "Table movie_success does not exist and create_if_missing is false"
```

**What should have happened:**
- MCP should surface guidance from component spec
- LLM should see: "For prototyping, recommend create_if_missing: true"
- Or MCP should ask user directly: "Auto-create table if missing? (recommended: yes)"

## Decision

### Proposal: Component-Level LLM Guidance via `x-llm-guidance`

Extend component specs with structured guidance that MCP can expose during OML generation.

**New section in component spec YAML:**

```yaml
# components/supabase.writer/spec.yaml
openapi: 3.1.0
info:
  x-component-id: supabase.writer

# ... existing spec ...

x-llm-guidance:
  description: "Guidance for LLMs generating OML with this component"

  # 1. Smart defaults with reasoning
  smart_defaults:
    create_if_missing:
      value: true
      reasoning: "Recommended for prototyping and development. Set to false in production with strict schema control."
      applies_when: "environment != production"

    mode:
      value: "append"
      reasoning: "Safest default - never deletes data. Use 'replace' for full refresh, 'upsert' for incremental updates."

  # 2. Interactive assessment questions
  assessment_questions:
    - field: create_if_missing
      question: "Should I automatically create the table if it doesn't exist?"
      type: boolean
      default: true
      context: |
        For prototyping: YES (tables auto-created from DataFrame schema)
        For production: NO (enforce explicit schema management)

    - field: mode
      question: "How should I write data to this table?"
      type: choice
      options:
        - value: append
          label: "Append - Add new rows"
          description: "Safe: Never deletes data. Good for logs, events."
          when: "Incremental data loads"

        - value: replace
          label: "Replace - Delete all, insert new"
          description: "Destructive: Full table refresh. Good for snapshots."
          when: "Full data refreshes"

        - value: upsert
          label: "Upsert - Update if exists, insert if not"
          description: "Smart: Requires primary_key. Good for incremental updates."
          when: "Tracking changes over time"
          requires: [primary_key]
      default: append

    - field: primary_key
      question: "Which field(s) uniquely identify each row?"
      type: array
      required_when: "mode == 'upsert' or mode == 'replace'"
      context: "Used for deduplication in upsert mode and cleanup in replace mode"
      examples:
        - ["id"]
        - ["user_id", "date"]

  # 3. Validation hints
  validation_hints:
    - condition: "mode == 'upsert' and not primary_key"
      error: "Upsert mode requires primary_key field"
      suggestion: "Either specify primary_key or use 'append' mode"

    - condition: "mode == 'replace' and not primary_key"
      warning: "Replace without primary_key will delete ALL rows"
      suggestion: "Consider adding primary_key for safer replace operations"

  # 4. Common patterns
  patterns:
    - name: "Prototype new table"
      config:
        create_if_missing: true
        mode: append
      description: "Quick prototyping - auto-create table, append data"

    - name: "Daily snapshot refresh"
      config:
        create_if_missing: false
        mode: replace
        primary_key: ["snapshot_date"]
      description: "Replace yesterday's data with today's snapshot"

    - name: "Incremental sync"
      config:
        create_if_missing: false
        mode: upsert
        primary_key: ["record_id"]
      description: "Update changed records, insert new ones"
```

### MCP Workflow Changes

**Phase 1: OML Generation (via MCP tool `oml_generate`)**

```
User → MCP: "Create pipeline to write movie data to Supabase"

MCP Server:
  1. Load component spec: components/supabase.writer/spec.yaml
  2. Extract x-llm-guidance section
  3. Inject into LLM system prompt:
     """
     Component: supabase.writer
     Smart defaults:
     - create_if_missing: true (recommended for prototyping)
     - mode: append (safest - never deletes)

     Assessment questions:
     - Should table be auto-created if missing? (default: yes)
     - Write mode: append/replace/upsert? (default: append)
     """

  4. LLM generates OML with guided defaults
  5. MCP validates against validation_hints
  6. Return OML with confidence scores

LLM → User:
  "I'll create a Supabase writer with auto-create enabled (good for prototyping).
   Using append mode to safely add data without deletions."
```

**Phase 2: Interactive Assessment (optional enhancement)**

```
User → MCP: "Create pipeline" (with --interactive flag)

MCP Server:
  1. Generate baseline OML
  2. Extract assessment_questions from all components
  3. Present to user via tool response:
     {
       "questions": [
         {
           "component": "supabase.writer",
           "field": "create_if_missing",
           "question": "Should I auto-create table if missing?",
           "default": true,
           "context": "Recommended for prototyping..."
         }
       ]
     }

User answers → MCP refines OML → Validate → Return
```

### Implementation Phases

**Phase 1: Spec Extension (v0.6.0)**
- Add `x-llm-guidance` to supabase.writer spec
- Add schema for x-llm-guidance structure
- Document in component creation guide

**Phase 2: MCP Integration (v0.7.0)**
- MCP tool `oml_schema_get` includes x-llm-guidance
- Update MCP handshake instructions to mention guidance
- LLMs can access guidance via schema endpoint

**Phase 3: Active Prompting (v0.8.0)**
- MCP injects guidance into LLM system prompts
- Smart defaults auto-applied during generation
- Validation hints checked before returning OML

**Phase 4: Interactive Mode (v0.9.0)**
- New MCP tool: `oml_assess` for interactive questions
- User can answer assessment questions
- Refined OML generated from answers

## Consequences

### Positive

✅ **Better first-try OML generation**
- LLMs make smarter default choices
- Fewer runtime errors from missing config

✅ **Self-documenting components**
- Guidance lives with component spec
- Single source of truth for best practices

✅ **Reduced user friction**
- Less trial-and-error
- Clear explanations for configuration choices

✅ **Extensible pattern**
- Any component can add guidance
- Works for all MCP-supported LLMs

### Negative

⚠️ **Spec complexity increases**
- More YAML to write per component
- Need to maintain guidance alongside code

⚠️ **LLM token consumption**
- Guidance adds to prompt size
- May need selective inclusion for large projects

⚠️ **Version skew risk**
- Guidance might lag behind code changes
- Need validation that guidance matches implementation

### Neutral

⚪ **Optional feature**
- Components without guidance still work
- Gradual adoption across component library

⚪ **Backward compatible**
- Existing specs unchanged
- x-llm-guidance is optional extension

## Alternatives Considered

### Alternative 1: Hardcode guidance in MCP server

**Rejected**: Couples guidance to MCP version, not component version

### Alternative 2: Separate guidance files

**Rejected**: Splits component definition across multiple files

### Alternative 3: LLM learns from examples

**Rejected**: Requires curated example library, less reliable

## Implementation Notes

### Schema for x-llm-guidance

```yaml
# JSON Schema for x-llm-guidance section
type: object
properties:
  description:
    type: string
    description: "Human-readable description of guidance"

  smart_defaults:
    type: object
    additionalProperties:
      type: object
      properties:
        value: {}  # Any type
        reasoning: {type: string}
        applies_when: {type: string}

  assessment_questions:
    type: array
    items:
      type: object
      properties:
        field: {type: string}
        question: {type: string}
        type: {enum: [boolean, choice, string, array]}
        default: {}
        context: {type: string}
        options: {type: array}
        required_when: {type: string}

  validation_hints:
    type: array
    items:
      type: object
      properties:
        condition: {type: string}
        error: {type: string}
        warning: {type: string}
        suggestion: {type: string}

  patterns:
    type: array
    items:
      type: object
      properties:
        name: {type: string}
        config: {type: object}
        description: {type: string}
```

### MCP Tool Changes

**New field in `oml_schema_get` response:**
```json
{
  "schema": {...},
  "guidance": {
    "smart_defaults": {...},
    "assessment_questions": [...],
    "patterns": [...]
  }
}
```

**New MCP tool (Phase 4):**
```
Tool: oml_assess
Input: {component: string, context: object}
Output: {questions: array, defaults: object}
```

## Related Work

- **ADR-0036**: MCP Interface - Foundation for this enhancement
- **Component Registry**: Already stores specs, natural place for guidance
- **OML Validator**: Can enforce validation_hints

## Future Enhancements

1. **Machine learning from feedback**
   - Track which defaults users change most often
   - Refine guidance based on real usage patterns

2. **Context-aware guidance**
   - Different defaults for dev vs. production
   - Adjust based on data volume, frequency, etc.

3. **Cross-component validation**
   - Warn if extractor schema doesn't match writer expectations
   - Suggest compatible component combinations

4. **Telemetry integration**
   - Track how often guidance prevents errors
   - Measure OML generation success rate improvement

## References

- Original feature request: Movie pipeline failure (2025-11-06)
- Component specs: `components/*/spec.yaml`
- MCP tools: `osiris/mcp/tools/oml.py`

## Status History

- **2025-11-06**: Proposed (drafted after movie pipeline debug session)
