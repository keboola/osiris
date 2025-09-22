# ADR 0019: Chat State Machine and OML Synthesis

## Status
Accepted

## Context

The conversational pipeline agent requires a deterministic flow to move from user intent to executable OML pipelines. Prior implementations allowed open-ended questioning at any point, leading to unpredictable behavior and poor user experience after database discovery. The system needs clear state transitions, robust error handling, and a strict OML v0.1.0 contract to ensure consistent pipeline generation.

Key challenges addressed:
- Post-discovery behavior was non-deterministic with potential for endless clarification loops
- Legacy pipeline formats (with `connectors`, `tasks`, `outputs`) were being generated
- Empty LLM responses caused silent failures
- No clear separation between conversation phases and synthesis phases
- Missing structured event logging for debugging and observability

## Decision

Implement a formal state machine (FSM) with strict transitions and enforce OML v0.1.0 schema validation throughout the conversation flow.

### State Machine Definition

```
INIT → INTENT_CAPTURED → (optional) DISCOVERY → OML_SYNTHESIS → 
VALIDATE_OML → (optional) REGENERATE_ONCE → COMPILE → (optional) RUN → COMPLETE
```

**Hard Rule**: After DISCOVERY → no open-ended questions; proceed directly to OML_SYNTHESIS using (user intent + discovery summary).

### OML v0.1.0 Contract

The system enforces a single, reusable OML contract block used both initially and post-discovery:

**Required Keys**:
- `oml_version: "0.1.0"` - Mandatory version declaration
- `name` - Pipeline identifier (kebab-case)
- `steps` - Array of step definitions

**Forbidden Keys** (legacy format):
- `version` - Replaced by `oml_version`
- `connectors` - Components declared per-step
- `tasks` - Replaced by `steps`
- `outputs` - Managed within step configs

**Step Shape**:
```yaml
- id: string (unique, kebab-case)
  component: string (e.g., "mysql.extractor")
  mode: enum ∈ {read, write, transform}
  config: map (component-specific)
  needs: array<string> (optional, for dependencies)
```

**Example OML** (minimal, valid v0.1.0):
```yaml
oml_version: "0.1.0"
name: mysql-to-csv-export
steps:
  - id: extract-users
    component: mysql.extractor
    mode: read
    config:
      query: "SELECT * FROM users"
      connection: "@default"
  - id: write-users-csv
    component: duckdb.writer
    mode: write
    needs: ["extract-users"]
    config:
      format: csv
      path: "./users.csv"
      delimiter: ","
      header: true
```

**Security**: No secrets in YAML; connections resolved at runtime (outside of OML).

## Details

### Error Policy

1. **Schema Guard Before Compile**:
   - Validate using `oml_schema_guard.check_oml_schema()`
   - Check required keys, forbidden legacy keys, step structure

2. **On Failure → One Guided Regeneration**:
   - Generate targeted prompt using `create_oml_regeneration_prompt()`
   - Include specific error message and OML contract reminder
   - If still invalid → concise HITL (Human-In-The-Loop) message

3. **Non-empty Assistant Fallback**:
   - If LLM returns empty message, provide user-friendly fallback
   - Log `empty_llm_response` event for debugging

### Events & Logging

Structured events emitted to session logs (keep stdout clean):
- `intent_captured` - User intent parsed
- `discovery_done` - Database discovery completed
- `oml_synthesis_start` - Beginning pipeline generation
- `oml_synthesis_complete` - Pipeline YAML generated
- `schema_guard_pass` - OML validation successful
- `schema_guard_fail` - OML validation failed (with error details)
- `regeneration_attempt` - Attempting to fix invalid OML
- `compile_start` - Beginning compilation
- `compile_complete` - Compilation successful

### Capabilities Scoping

At synthesis time, limit LLM capabilities to `["generate_pipeline"]` to prevent:
- Additional discovery attempts
- Configuration validation loops
- Unrelated conversational responses

### Implementation Files

**Core Implementation**:
- `osiris/core/conversational_agent.py` - State machine, post-discovery synthesis
- `osiris/core/oml_schema_guard.py` - Schema validation and regeneration prompts
- `osiris/core/prompt_manager.py` - OML_CONTRACT block in system prompt

**Test Coverage**:
- `tests/chat/test_post_discovery_synthesis.py` - Post-discovery direct synthesis
- `tests/chat/test_no_empty_responses.py` - Empty response handling
- `tests/core/test_oml_schema_guard.py` - Schema validation rules
- `tests/chat/test_chat_mysql_to_csv.py` - End-to-end OML generation

## Consequences

### Positive
- **Deterministic post-discovery behavior** - No more endless clarification loops
- **Improved developer UX** - Clear, predictable conversation flow
- **Enhanced reproducibility** - Same intent + discovery → same pipeline
- **Better observability** - Structured event logging for debugging
- **Robust error handling** - Graceful fallbacks and user-friendly messages

### Negative
- **Stricter contract may require prompt updates** - Mitigated by reusing one contract block
- **Less conversational flexibility** - Trade-off for MVP determinism
- **Single regeneration attempt** - May miss edge cases (acceptable for MVP)

## Alternatives Considered

1. **Agentic Questioning Post-Discovery** (Rejected)
   - Would allow continued clarification after discovery
   - Rejected for MVP determinism and predictability

2. **Schema-less Free-form Generation** (Rejected)
   - Would accept any YAML structure
   - Rejected due to downstream compilation complexity

3. **Multiple Regeneration Attempts** (Deferred)
   - Would retry OML generation multiple times
   - Deferred to post-MVP for simplicity

## Acceptance Checks

### Manual Testing
Given: "export all tables from MySQL to Supabase, no scheduler"
- ✅ Returns valid OML v0.1.0 with `steps` only
- ✅ Contains mysql.extractor + supabase.writer components
- ✅ No clarifying questions post-discovery
- ✅ No legacy keys in generated YAML

### Automated Tests
- ✅ `test_post_discovery_synthesis.py` - Direct synthesis after discovery
- ✅ `test_no_empty_responses.py` - Fallback message on empty LLM response
- ✅ `test_oml_schema_guard.py` - Schema validation catches legacy format
- ✅ `test_all_commands_json.py` - CLI help shows correct options

## References

- ADR 0014: OML v0.1.0 Scope and Schema - Defines the OML contract
- ADR 0015: Compile Contract Determinism - Compilation requirements
- `osiris/core/prompt_manager.py:OML_CONTRACT` - Prompt section enforcing v0.1.0
- Issue #M1c - Milestone documentation for state machine implementation

## Notes on Milestone M1

**Implementation Status**: Fully implemented in Milestone M1.

The chat state machine and OML synthesis enforcement has been implemented in:
- **Core enforcement**: `osiris/core/conversational_agent.py` - Contains the state machine logic, post-discovery synthesis, and strict OML v0.1.0 contract enforcement
- **Test coverage**: `tests/chat/test_post_discovery_synthesis.py` - Validates that no open questions are asked after discovery, direct synthesis occurs
- **Schema validation**: `osiris/core/oml_schema_guard.py` - Enforces required keys, forbids legacy keys, validates step structure
- **Additional tests**: Coverage in `tests/chat/test_no_empty_responses.py`, `tests/core/test_oml_schema_guard.py`, and `tests/chat/test_chat_mysql_to_csv.py`

Key features delivered:
- Mandatory FSM flow with deterministic transitions
- Hard rule: NO open questions after discovery phase
- Strict OML v0.1.0 contract with required keys {oml_version, name, steps}
- Forbidden legacy keys {version, connectors, tasks, outputs} with automatic detection
- Single regeneration attempt on validation failure
- Non-empty assistant message fallback for better UX
- Structured event logging for each state transition
