# Milestone M1c: Thin-Slice Compile and Run

## Status
Completed (Thin-Slice)

## Goal
Implement the absolute minimum viable path for OML compilation and execution: a deterministic compiler that transforms OML into secret-free artifacts and a local runner that executes a single linear ETL pipeline (Supabase → DuckDB → MySQL).

## Scope

### In Scope (Must Have)
- **Compiler v0**: Deterministic, no LLM, canonical YAML/JSON output
- **Manifest v0**: Minimal structure for runner needs
- **Runner v0**: Local, sequential execution of 3 components only:
  - SupabaseExtractor (read table/query)
  - DuckDBTransform (single SQL statement)
  - MySQLWriter (append/replace)
- **Parameter resolution**: `${params.*}` from CLI/ENV/profile
- **No secrets**: Compile error on inline secrets
- **Minimal artifacts**: `_artifacts/{step_id}/` directories

### Out of Scope (Explicitly Deferred)
- Fan-out/fan-in, branching, when conditions
- Retry/timeout/idempotency (parse but ignore)
- Compile cache and lockfiles
- Manifest utilities beyond skeleton
- Scheduling, distributed execution
- e2b, A2A, MCP, or agent integration
- Any components beyond the three listed above
- Complex expression evaluation
- Dynamic discovery or LLM involvement

## Implementation Plan

### m1c.1: Canonical IO & Fingerprints
**Goal**: Establish deterministic serialization foundation per ADR-0015

**Deliverables**:
- Canonical YAML/JSON dumpers with stable key ordering
- SHA-256 fingerprinting utilities
- UTF-8/LF normalization, no trailing spaces
- Unit tests proving byte-identical outputs

**Files**:
- `osiris/core/canonical.py`
- `osiris/core/fingerprint.py`
- `tests/unit/test_canonical.py`
- `tests/unit/test_fingerprint.py`

**Acceptance**:
- [ ] Identical inputs produce byte-identical canonical outputs
- [ ] Fingerprints are stable and deterministic
- [ ] Tests validate ordering independence

### m1c.2: Parameter Resolution
**Goal**: Implement `${params.*}` resolution with proper precedence

**Deliverables**:
- Parameter precedence: CLI > ENV > profile > defaults
- Template resolution throughout OML
- Compile error on unresolved parameters

**Files**:
- `osiris/core/params_resolver.py`
- `tests/unit/test_params_resolver.py`

**Acceptance**:
- [ ] All `${params.*}` placeholders resolved
- [ ] Precedence chain works correctly
- [ ] Unresolved parameters cause clear errors

### m1c.3: Compiler v0
**Goal**: Transform OML into deterministic manifest for linear pipeline

**Deliverables**:
- OML → IR → manifest transformation
- Generate manifest.yaml, cfg/*.json, meta.json
- Integrate fingerprinting and canonical output
- Hardcoded secret field detection (minimal Registry stub)

**Files**:
- `osiris/core/compiler_v0.py`
- `osiris/core/manifest_generator.py`
- `tests/unit/test_compiler_v0.py`

**Acceptance**:
- [ ] Generates valid manifest structure
- [ ] All outputs are deterministic
- [ ] Secrets cause compilation failure
- [ ] Fingerprints computed correctly

### m1c.4: Runner v0
**Goal**: Execute compiled manifest locally and sequentially

**Deliverables**:
- Read manifest.yaml and execute steps
- Load and run three specific components
- Save artifacts to `_artifacts/{step_id}/`
- Structured logging of execution events

**Files**:
- `osiris/core/runner_v0.py`
- `osiris/core/step_executor.py`
- `tests/unit/test_runner_v0.py`

**Acceptance**:
- [ ] Steps execute in correct order
- [ ] Artifacts saved to correct directories
- [ ] Components load and run successfully
- [ ] Execution events logged

### m1c.5: CLI Integration
**Goal**: Wire up compile and run commands

**Deliverables**:
- `osiris compile <pipeline.yaml> --out compiled/`
- `osiris run compiled/manifest.yaml`
- Proper exit codes (0=success, 1=error, 2=validation)
- Integration tests with example pipeline

**Files**:
- `osiris/cli/compile.py`
- `osiris/cli/run.py`
- Modify: `osiris/cli/main.py`
- `tests/integration/test_compile_run.py`

**Acceptance**:
- [ ] CLI commands work end-to-end
- [ ] Exit codes follow specification
- [ ] Golden test validates manifest output
- [ ] Example pipeline runs successfully

### m1c.6: Documentation
**Goal**: Document the thin-slice implementation

**Deliverables**:
- Example pipeline YAML
- Updated pipeline format documentation
- CHANGELOG entry
- This milestone document

**Files**:
- `docs/examples/supabase_to_mysql.yaml`
- Update: `docs/pipeline-format.md`
- Update: `CHANGELOG.md`

**Acceptance**:
- [ ] Example compiles and runs
- [ ] Documentation is accurate
- [ ] CHANGELOG reflects changes

## Success Criteria

1. **Determinism**: Identical OML inputs produce byte-identical manifests
2. **No Secrets**: Inline secrets cause compilation failure
3. **End-to-End**: Example pipeline compiles and runs successfully
4. **Clean Output**: No secrets in logs, artifacts, or console output
5. **Exit Codes**: Proper exit codes for success/error conditions

## Example OML (Target)

```yaml
oml_version: "0.1.0"
name: "Supabase to MySQL ETL"
params:
  supabase_url: "${OSIRIS_SUPABASE_URL}"
  supabase_key: "${OSIRIS_SUPABASE_ANON_KEY}"
  mysql_dsn: "${OSIRIS_MYSQL_DSN}"
  source_table: "public.customers"
  target_table: "dw.customers"
  transform_sql: "SELECT *, upper(email) AS email_up FROM input"

steps:
  - id: "extract_customers"
    uses: "extractors.supabase@0.1"
    with:
      url: "${params.supabase_url}"
      key: "${params.supabase_key}"
      table: "${params.source_table}"
  
  - id: "transform_enrich"
    uses: "transforms.duckdb@0.1"
    with:
      sql: "${params.transform_sql}"
  
  - id: "load_mysql"
    uses: "writers.mysql@0.1"
    with:
      dsn: "${params.mysql_dsn}"
      table: "${params.target_table}"
      mode: "replace"
```

## Follow-up (Post M1c)

- M1d: Full manifest utilities (verify/diff/lock)
- M2: Enhanced LLM context building
- M3: Production-ready compiler with caching
- M4: Distributed runner with scheduling
- Advanced flow control (branching, fan-out)
- Component Registry integration
- Retry/timeout/idempotency implementation

## References

- ADR-0014: OML v0.1.0 Schema & Scope
- ADR-0015: Compile Contract (Determinism & Fingerprints)
- Parent milestone: docs/milestones/m1c-compile-and-run-mvp.md
