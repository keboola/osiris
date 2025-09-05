# Milestone M1c: Compile and Run MVP

## Goal

Transform validated OML pipelines into deterministic, secret-free execution artifacts ("manifest") and implement a minimal local runner that executes simple pipelines reliably.

## Non-Goals (0.x)

- No scheduler or distributed runtime
- No LLM in compilation
- No inline secrets in OML or artifacts
- No automatic retries beyond component-local behavior

## Inputs & Constraints

- **Inputs**: Validated OML (M1b), Component Registry view, parameters (CLI/ENV/profile/defaults), active profile, compiler version
- **Constraints**: Determinism, no-secrets, reproducible fingerprints (ADR-0014, ADR-0015)

## High-Level Business Flow

1. **OML YAML** (pipeline description from LLM or human) → validated by M1b
2. **Compiler** produces production-ready manifests with all required metadata
3. **Runner** executes those manifests step by step locally

---

## Scope trim for e2b

- In-scope (e2b): supabase.extractor → (duckdb.transform) → mysql.writer, sequential only.
- Out-of-scope (post-e2b): branching/when/fan_out, retries/timeouts beyond basic error, manifest utilities (full), scheduling/distribution, agent calls, long-term memory/store, A2A/MCP.


## Scope

### 1. Compiler (OML → IR → Manifest)

- Deterministic IR generation from OML (no LLM)
- Fill defaults and normalize aliases using Registry specs
- Expand control flow: needs, simple fan_out/fan_in (Cartesian product over explicit lists, no dynamic queries in MVP)
- Resolve `${params.*}`; unresolved placeholders → compile error
- Emit secret-free artifacts:
  - `compiled/manifest.yaml` (canonical YAML)
  - `compiled/cfg/{step_id}.json` (per-step minimal configs)
  - `compiled/meta.json` (provenance, fingerprints)
  - `compiled/effective_config.json` (resolved parameters)

### 2. Runner (MVP)

- Read manifest.yaml and execute steps locally, sequentially, honoring needs (topological order) and deterministic fan_out/fan_in
- Integrate with Component Registry: load driver and pass cfg_path
- Log structured session events (run_start, step_start, step_complete, step_error, run_complete)
- Store outputs under `_artifacts/`, with per-step subdirectories keyed by step_id

### 3. Configuration Surface

- **CLI**:
  - `osiris compile <pipeline.yaml> --out compiled/ [--profile P] [--param k=v ...] [--compile auto|force|never]`
  - `osiris run compiled/manifest.yaml [--out _artifacts/]`
- **Param precedence** (per ADR-0004): defaults < ENV `OSIRIS_PARAM_*` < CLI `--param`
- **Profiles** (e.g., dev, prod) influence parameter resolution and fingerprint key

### 4. Caching & Determinism

- Cache key = `(oml_fp, registry_fp, compiler_fp, params_fp, profile)`
- Canonicalization rules: UTF-8/LF, stable key ordering, stable list ordering, lexicographic tie-breakers
- Stable IDs: compiler generates deterministic suffixes for expanded steps, e.g. `orders[eu]`, `orders[us]`, ordered lexicographically by iteration values

### 5. Logging & Security

- **Compile events**: compile_start, compile_complete, cache_hit|miss, compile_error
- **Run events**: run_start, step_start, step_complete, step_error, run_complete
- **Redaction rules** reused from M1b:
  - No secrets in manifests, configs, or CLI output
  - If inline secret is detected in OML → compile error with category `secret_inline_forbidden`

---

## Artifacts & Layout

```
compiled/
├── manifest.yaml                 # Canonical execution plan
├── cfg/
│   └── {step_id}.json           # Per-step configuration
├── meta.json                     # Provenance & fingerprints
└── effective_config.json         # Resolved parameters

_artifacts/                       # Execution outputs
└── {step_id}/                   # Per-step subdirectories
```

---

## CLI & Exit Codes

### `osiris compile`
- Exit 0 → success
- Exit 2 → validation or secret errors
- Exit 1 → internal errors

### `osiris run`
- Exit 0 → success
- Exit 1 → runtime or step error

---

## Tests

### Unit Tests (Compiler)
- Deterministic manifest: identical inputs ⇒ byte-identical outputs
- Defaults & aliasing filled per Registry
- Parameter resolution: success and failure cases
- Inline secret detection → error
- Fan-out expansions generate stable IDs and ordering

### Unit Tests (Runner)
- Executes linear pipeline correctly
- Handles simple fan_out/fan_in branches deterministically
- Honors needs dependencies

### Integration Tests
- `osiris compile` + `osiris run` on `docs/examples/*`
- Cache hit/miss scenarios and `--compile force|never`
- Exit-code correctness for compile/run commands
- Golden tests: compare `compiled/manifest.yaml` against canonical snapshots
- Redaction tests: ensure no secrets appear in outputs, artifacts, or CLI

---

## Acceptance Criteria

- [ ] Compiler produces deterministic, secret-free artifacts with correct fingerprints
- [ ] Runner executes linear pipelines and simple fan_out/fan_in correctly
- [ ] CLI and exit codes behave as specified
- [ ] Logs contain the defined compile/run events
- [ ] Artifacts are written following the documented layout
- [ ] All unit, integration, and golden tests for both compiler and runner pass

---

## Sub-Milestones & Implementation Plan

### M1c.1: Canonicalization & Fingerprinting Foundation
**Scope**: Establish deterministic serialization and fingerprinting infrastructure per ADR-0015.

**Deliverables**:
- `osiris/core/canonical.py` - Canonical serialization functions (JSON/YAML)
- `osiris/core/fingerprint.py` - SHA-256 fingerprinting utilities
- Stable key ordering, UTF-8/LF normalization, no trailing spaces
- Deterministic number/boolean serialization

**Files to Create/Modify**:
- Create: `osiris/core/canonical.py`
- Create: `osiris/core/fingerprint.py` 
- Create: `tests/unit/test_canonical.py`
- Create: `tests/unit/test_fingerprint.py`

**Acceptance Criteria**:
- [ ] Identical inputs produce byte-identical canonical outputs
- [ ] Fingerprints change when any input changes
- [ ] Unit tests prove determinism across different Python dict orderings
- [ ] Golden snapshot test validates canonical format stability

### M1c.2: OML Schema Validation & Loading
**Scope**: Implement OML v0.1.0 schema validation per ADR-0014.

**Deliverables**:
- OML schema validator using JSON Schema or similar
- Support for all OML v0.1.0 fields (params, profiles, steps, etc.)
- Version checking (reject unknown major versions)
- Custom extension validation (`x-*` fields)

**Files to Create/Modify**:
- Create: `osiris/core/oml_schema.py`
- Create: `osiris/core/oml_loader.py`
- Create: `tests/unit/test_oml_schema.py`
- Create: `tests/fixtures/oml/` (valid and invalid examples)

**Acceptance Criteria**:
- [ ] Valid OML documents load successfully
- [ ] Invalid OML documents fail with clear error messages
- [ ] Version compatibility checking works
- [ ] Schema enforces all constraints from ADR-0014

### M1c.3: Parameter Resolution Engine
**Scope**: Implement parameter resolution with proper precedence per ADR-0014/0015.

**Deliverables**:
- Parameter precedence: CLI > ENV > profile > defaults
- `${params.*}` template resolution throughout OML
- Type validation (string, int, number, bool, list, map)
- Enum constraint validation
- Profile application to params and safe config fields

**Files to Create/Modify**:
- Create: `osiris/core/params_resolver.py`
- Create: `tests/unit/test_params_resolver.py`
- Modify: `osiris/core/oml_loader.py` (integrate param resolution)

**Acceptance Criteria**:
- [ ] Precedence chain works correctly (CLI > ENV > profile > default)
- [ ] All `${params.*}` placeholders are resolved
- [ ] Unresolved parameters cause compilation failure
- [ ] Type and enum constraints are enforced
- [ ] Profile overrides work for allowed fields only

### M1c.4: Secret Detection & Registry Integration
**Scope**: Enforce no-secrets policy and integrate with Component Registry per ADR-0015.

**Deliverables**:
- Detect inline secrets using Registry field metadata
- Fill defaults and normalize aliases from Registry specs
- Validate component references exist in Registry
- Generate compilation errors for secret violations

**Files to Create/Modify**:
- Create: `osiris/core/secrets_validator.py`
- Create: `osiris/core/registry_client.py` (interface to M1a registry)
- Create: `tests/unit/test_secrets_validator.py`
- Create: `tests/unit/test_registry_integration.py`

**Acceptance Criteria**:
- [ ] Inline secrets in OML cause compilation failure
- [ ] Error category is `secret_inline_forbidden`
- [ ] Component specs are loaded from Registry
- [ ] Defaults and aliases are normalized correctly
- [ ] Unknown components cause clear errors

### M1c.5: DAG Expansion & Topological Sort
**Scope**: Expand OML control flow into deterministic DAG per ADR-0014/0015.

**Deliverables**:
- Expand `needs` dependencies into explicit DAG
- Handle `branch` conditions (simple boolean expressions)
- Expand `fan_out/fan_in` with stable child IDs
- Topological sort with lexical tie-breakers (Kahn's algorithm)
- Support `when` conditions (minimal expression language)

**Files to Create/Modify**:
- Create: `osiris/core/dag_expander.py`
- Create: `osiris/core/dag_sort.py`
- Create: `tests/unit/test_dag_expander.py`
- Create: `tests/unit/test_dag_sort.py`

**Acceptance Criteria**:
- [ ] Linear pipelines maintain order
- [ ] Dependencies (`needs`) are respected
- [ ] Fan-out generates stable IDs (e.g., `step[eu]`, `step[us]`)
- [ ] Topological sort is deterministic (lexical tie-breaking)
- [ ] Branch expansion creates correct DAG nodes

### M1c.6: Manifest Generation
**Scope**: Generate deterministic manifest and per-step configs per ADR-0015.

**Deliverables**:
- Generate `manifest.yaml` with pipeline metadata
- Generate `cfg/{step_id}.json` for each expanded step
- Generate `meta.json` with fingerprints and provenance
- Generate `effective_config.json` with resolved parameters
- All outputs are canonical and secret-free

**Files to Create/Modify**:
- Create: `osiris/core/manifest_generator.py`
- Create: `osiris/core/compiler.py` (orchestrates all compilation steps)
- Create: `tests/unit/test_manifest_generator.py`
- Create: `tests/golden/manifests/` (golden test fixtures)

**Acceptance Criteria**:
- [ ] Manifest structure matches ADR-0015 specification
- [ ] All fingerprints are computed correctly
- [ ] Per-step configs contain only necessary data
- [ ] Meta.json contains all provenance information
- [ ] Golden tests validate deterministic output

### M1c.7: Compile CLI & Caching
**Scope**: Implement `osiris compile` command with caching per ADR-0015.

**Deliverables**:
- `osiris compile <pipeline.yaml>` CLI command
- Options: `--out`, `--profile`, `--param`, `--compile=auto|force|never`
- Cache key computation from fingerprints
- Cache storage and retrieval logic
- Structured logging events (compile_start, compile_complete, cache_hit/miss)

**Files to Create/Modify**:
- Create: `osiris/cli/compile.py`
- Create: `osiris/core/compile_cache.py`
- Modify: `osiris/cli/main.py` (add compile command)
- Create: `tests/integration/test_compile_cli.py`

**Acceptance Criteria**:
- [ ] CLI command works with all specified options
- [ ] Exit codes: 0=success, 2=validation/secrets, 1=internal
- [ ] Cache hit avoids recompilation
- [ ] `--compile=force` ignores cache
- [ ] `--compile=never` fails if not cached
- [ ] Logs follow existing redaction policy

### M1c.8: Runner Core Implementation
**Scope**: Implement local sequential runner per milestone requirements.

**Deliverables**:
- Read and parse `manifest.yaml`
- Execute steps in topological order
- Integrate with Component Registry to load drivers
- Handle retry/timeout/idempotency per step
- Store outputs in `_artifacts/{step_id}/`

**Files to Create/Modify**:
- Create: `osiris/core/runner.py`
- Create: `osiris/core/step_executor.py`
- Create: `tests/unit/test_runner.py`
- Create: `tests/unit/test_step_executor.py`

**Acceptance Criteria**:
- [ ] Steps execute in correct topological order
- [ ] Component drivers are loaded from Registry
- [ ] Retry logic works (exponential backoff)
- [ ] Timeout is enforced per step
- [ ] Artifacts are stored in correct directories

### M1c.9: Run CLI & Session Management
**Scope**: Implement `osiris run` command with session logging.

**Deliverables**:
- `osiris run <manifest.yaml>` CLI command
- Options: `--out` (artifacts directory)
- Structured logging events (run_start, step_start/complete/error, run_complete)
- Integration with existing session logging system

**Files to Create/Modify**:
- Create: `osiris/cli/run.py`
- Modify: `osiris/cli/main.py` (add run command)
- Modify: `osiris/core/session_logging.py` (add run events)
- Create: `tests/integration/test_run_cli.py`

**Acceptance Criteria**:
- [ ] CLI command executes manifests successfully
- [ ] Exit codes: 0=success, 1=runtime error
- [ ] All run events are logged with proper structure
- [ ] Session logs contain execution details
- [ ] Logs follow existing redaction policy

### M1c.10: Manifest Utilities (Skeleton)
**Scope**: Implement basic manifest utilities as skeleton for future enhancement.

**Deliverables**:
- `osiris manifest verify` - Check manifest integrity
- `osiris manifest diff` - Compare two manifests
- `osiris manifest lock` - Skeleton for dependency locking
- `osiris manifest unlock` - Skeleton for unlocking

**Files to Create/Modify**:
- Create: `osiris/cli/manifest.py`
- Modify: `osiris/cli/main.py` (add manifest commands)
- Create: `tests/unit/test_manifest_utils.py`

**Acceptance Criteria**:
- [ ] Verify checks fingerprint integrity
- [ ] Diff shows basic structural differences
- [ ] Lock/unlock commands exist (can be no-op for MVP)
- [ ] Commands have proper help text

### M1c.11: Integration Tests & Examples
**Scope**: Comprehensive testing and example pipelines.

**Deliverables**:
- Example pipelines (linear, branching, fan-out)
- Golden test snapshots for determinism validation
- End-to-end compile + run tests
- Updated documentation

**Files to Create/Modify**:
- Create: `docs/examples/linear_pipeline.yaml`
- Create: `docs/examples/branching_pipeline.yaml`
- Create: `docs/examples/fanout_pipeline.yaml`
- Create: `tests/golden/snapshots/`
- Create: `tests/integration/test_end_to_end.py`
- Update: `docs/pipeline-format.md`

**Acceptance Criteria**:
- [ ] All example pipelines compile successfully
- [ ] Golden tests validate byte-identical outputs
- [ ] End-to-end tests pass for all examples
- [ ] No secrets appear in any artifacts
- [ ] Documentation is complete and accurate

---

## Deliverables

- `osiris/core/compiler.py` - Compiler orchestration
- `osiris/core/runner.py` - Runner implementation
- `osiris/core/canonical.py` - Canonicalization utilities
- `osiris/core/fingerprint.py` - Fingerprinting utilities
- `osiris/core/params_resolver.py` - Parameter resolution
- `osiris/core/dag_expander.py` - DAG expansion logic
- `osiris/core/manifest_generator.py` - Manifest generation
- CLI commands: `osiris compile`, `osiris run`, `osiris manifest`
- Updated `docs/pipeline-format.md` with manifest schema and examples
- CHANGELOG + updated milestone status
- Example pipelines under `docs/examples/` with golden snapshots
