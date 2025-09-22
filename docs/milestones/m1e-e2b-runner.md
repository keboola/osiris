# Milestone M1e – E2B Remote Runner

**Status:** In Progress  
**Implementation Status:** Adapter contract and LocalAdapter merged; E2BAdapter pivoted to full CLI execution (removed mini_runner).  
**Owner:** Osiris Core Team  
**Depends on:** M1d (Logs & CLI Unification), ADR-0010 (E2B Integration), ADR-0020 (Connection Resolution)  
**Deliverable:** Functional E2B remote runner with unified logging and secrets management

## Links
- Implements: docs/adr/0010-e2b-integration-for-pipeline-execution.md
- Implements: docs/adr/0025-cli-ux-unification.md  
- Depends on: docs/milestones/m1d-logs-and-cli-unification.md
- Depends on: docs/adr/0020-connection-resolution-and-secrets.md
- Context: roadmap/0.x-initial-plan.md (runner and execution engines)

## Goals
- Transform Osiris into a proper remote runner using E2B sandboxes
- Integrate E2B execution with unified logging system from M1d
- Ensure secrets are handled securely via environment variables only
- Provide seamless UX where remote execution feels like local execution
- Close the gap left by M1d's focus on local runner and establish E2B as a first-class execution environment

## Scope

### Architecture & Execution Adapter

To guarantee that E2B behaves **identically** to local runs and to prevent drift, introduce a thin **execution adapter** boundary with two backends:

- **ExecutionAdapter (interface/contract)**
  - `prepare(plan, context) -> PreparedRun` (resolves connections, expands cfg refs, performs secret-substitution placeholders but never persists secrets)
  - `execute(prepared, io) -> ExecResult` (emits events/metrics with the same taxonomy as local)
  - `collect(prepared) -> CollectedArtifacts` (idempotent; no-op for local)
- **LocalAdapter** – current local runner implementation (reference backend)
- **E2BAdapter** – sandbox backend using the same plan/driver contracts
  - Packager reuses `PreparedRun` from the adapter boundary (no bespoke manifest mutation)
  - **Full CLI execution**: Runs complete Osiris CLI inside sandbox (no mini_runner) ensuring identical execution paths
  - Secrets are injected via env vars at sandbox startup and **never serialized** in payloads
  - Event names, fields, and error mapping mirror LocalAdapter one-to-one

### PreparedRun Data Structure

The `PreparedRun` represents all inputs required for deterministic execution, without secrets or runtime-specific details. Both LocalAdapter and E2BAdapter operate on the same contract.

**Fields:**
- `plan`: canonical, deterministic manifest JSON (post-compile/normalize)
- `resolved_connections`: descriptors after resolution (driver, host, db, user, port, with `secret_placeholders` = env var names only, no values)
- `cfg_index`: map of cfg/*.json paths → normalized spec (included in payload; validated pre-run)
- `io_layout`: relative paths for artifacts/logs within the session
- `run_params`: profile, parameters, seed, flags (no secrets)
- `constraints`: limits/policies (max rows, redaction rules)
- `metadata`: session_id, created_at, compiler_fingerprint, adapter_target (`local|e2b`)

**Guarantees:**
- No secrets are persisted; only placeholders for env injection at runtime.
- Payloads derive strictly from `PreparedRun`; no ad-hoc manifest mutation.
- Adapters differ only in transport/execution mechanics, never in semantics.

**Driver & Connection rules**
- Drivers are always loaded through the existing **DriverRegistry** (both local and E2B use same code).
- Full CLI in sandbox uses standard osiris_connections.yaml with env var substitution.
- Secret values are supplied to the sandbox exclusively via env vars at startup; CLI resolves them normally at runtime.

**Artifact & Logging parity**
- Artifacts layout inside `logs/<session>/remote/` mirrors local: `events.jsonl`, `metrics.jsonl`, `osiris.log`, `artifacts/…`
- SessionReader merges phases but **does not alter** event schema; HTML browser consumes the same shapes.

**Error model**
- Map remote failures to the same error codes/reasons used locally (e.g., `extract.connection_error`, `write.schema_mismatch`); add a `source: "remote"` tag.

### 1. Full Source Payload Packer
- **Full Osiris source**: Include complete Osiris package, pyproject.toml, and all dependencies
- **Compiled artifacts**: Include manifest.yaml and all referenced `cfg/*.json` files  
- **Run script**: Shell script entrypoint that installs deps and runs `osiris run manifest.yaml`
- **Compression**: Create optimized payload.tgz for E2B upload
- **Validation**: Fail fast if any required files are missing

### 2. Full CLI Execution in Sandbox
- **Architecture**: Run exact same `osiris.cli.main` as local execution (no code duplication)
- **Dependencies**: Install via pip in sandbox before execution
- **Connection resolution**: Standard osiris_connections.yaml with env var substitution
- **Error handling**: Normal CLI error propagation, captured by E2B adapter

### 3. Golden Path Pipeline Execution
- **Target pipeline**: MySQL extractor → CSV writer (filesystem.csv_writer)
- **End-to-end flow**: `osiris run pipeline.yaml --e2b` executes completely inside E2B
- **Data validation**: Verify output CSV matches expected format and content
- **Performance**: Reasonable execution time for demo scenarios

### 4. Secrets Management
- **Environment-only secrets**: Pass secrets via environment variables at sandbox start (per E2B model)
- **No secret leakage**: Ensure no secrets appear in payload files, logs, or artifacts
- **Connection resolution**: Use `${ENV_VAR}` substitution from sandbox environment
- **Validation**: Redaction tests must pass for all E2B execution paths

### 5. Unified Logging Integration
- **Download mechanism**: Pull full logs (`osiris.log`, `events.jsonl`, `metrics.jsonl`, `artifacts/`) from E2B
- **Storage layout**: Logs stored in `logs/<session>/remote/` directory
- **SessionReader merge**: Unified timeline showing local prepare/upload/download and remote exec segment
- **HTML Logs Browser**: Remote exec segment visible with links to `remote/osiris.log`

### 6. CLI Integration
- **New flag**: `osiris run pipeline.yaml --e2b` triggers remote execution
- **Status reporting**: Real-time status updates during E2B execution
- **Error handling**: Clear error messages for E2B API failures, timeout, etc.
- **Fallback**: Graceful handling when E2B is unavailable

## Deliverables

### Core Components
- **Execution Adapter** (`osiris/core/execution_adapter.py`) – shared contract and two backends: LocalAdapter and E2BAdapter
- **Full Source Packer** (`osiris/remote/e2b_full_pack.py`) - Builds complete Osiris source payload for sandbox
- **E2B Client** (`osiris/remote/e2b_client.py`) - E2B Code Interpreter SDK wrapper
- **E2B Adapter** (`osiris/remote/e2b_adapter.py`) - ExecutionAdapter implementation for E2B
- **CLI Support** (`osiris/cli/run.py`) - Add `--e2b` flag and remote execution logic

### Logging & Session Management
- **Remote log downloader** - Pull all execution artifacts from E2B
- **SessionReader enhancements** - Merge local and remote execution timelines
- **HTML browser updates** - Display remote execution segment with proper navigation

### Testing & Documentation
- **Integration tests** - E2B execution with dummy database
- **CI integration** - Live test with E2B API key (skipped if no key provided)
- **Redaction tests** - Ensure no secrets leak in remote execution paths
- **Documentation updates** - Update CLAUDE.md and CLI help

## Acceptance Criteria

### Parity with Local Runner
- Running the same pipeline locally vs. with `--e2b` yields **identical**:
  - event taxonomy (names/fields) and ordering (modulo phase timestamps),
  - metrics aggregates (rows_in/out, steps_ok/total, durations within ±5%),
  - artifact shapes and filenames (content may differ only in timestamp/host-specific metadata).
- Golden snapshot tests: `local` vs `e2b` JSON normalized diff is empty (with allowed-field mask for timestamps, durations, host IDs).
- CLI UX remains unchanged except for the additional `--e2b*` flags; help text matches M1d wording.

### Functional Requirements
- `osiris run pipeline.yaml --e2b` successfully executes a real pipeline inside E2B using resolved connections
- Payload assembly fails fast if any `cfg/*.json` referenced in manifest is missing
- Golden Path pipeline (MySQL → CSV) executes successfully in E2B environment
- Output artifacts are downloaded and match expected format and content

### Security Requirements
- No secrets appear in JSON payload files, compilation artifacts, or HTML logs
- All redaction tests pass for E2B execution paths
- Secrets are passed only via environment variables at sandbox start
- Connection resolution works correctly with `${ENV_VAR}` substitution in sandbox

### Logging & Observability
- Logs and artifacts are merged into unified timeline
- HTML Logs Browser loads remote execution segment and shows link to `remote/osiris.log`
- SessionReader correctly displays both local (prepare/upload/download) and remote (exec) segments
- All execution events are captured with proper timestamps and correlation

### Testing & Quality
- Live test with E2B API key and dummy database passes in CI (skipped if no key available)
- All existing tests continue to pass
- Integration test covers complete E2B flow: pack → upload → execute → download
- Error handling tests cover E2B API failures and timeout scenarios
- Parity test suite: run the Golden Path both locally and in E2B; compare normalized `events.jsonl`/`metrics.jsonl` and artifact inventories.
- Adapter conformance tests: enforce that both backends pass the same behavioral tests from a shared test harness.

### User Experience
- `--e2b` flag provides clear status updates during remote execution
- Error messages are actionable and clearly distinguish local vs remote failures
- Execution time is reasonable for demo scenarios (< 2 minutes for simple pipelines)
- Remote execution feels seamless and integrated with local Osiris experience

## Out of Scope

### Advanced Pipeline Features
- Advanced fan-out/fan-in pipelines (complex branching logic)
- Multi-agent orchestration or distributed pipeline execution
- Scheduler integration or recurring pipeline execution

### Performance Optimizations
- Streaming execution or pipeline parallelization
- Advanced caching strategies for E2B payloads
- Load balancing across multiple E2B instances

### Enterprise Features
- Multi-tenant isolation or user management
- Audit logging beyond basic session management
- Cost optimization or resource quotas

## Notes

- This milestone formally closes the gap after M1d and establishes E2B as a first-class execution environment
- **Architectural Pivot**: Removed mini_runner approach in favor of full CLI execution in sandbox for true parity
- E2B integration builds on the solid foundation established in M1c (driver registry) and M1d (unified logging)
- Focus is on getting the "happy path" working reliably rather than handling edge cases
- Success criteria emphasize end-to-end functionality over performance optimization
- See README.md section "Running in E2B" for user instructions

## Implementation History

### Initial Approach (Abandoned)
- Originally implemented mini_runner.py as lightweight execution engine
- Discovered connection resolution mismatches between mini_runner and main CLI
- Mini_runner introduced maintenance burden and semantic drift risk

### Current Approach (Full CLI)
- Execute complete Osiris CLI inside E2B sandbox
- Guarantees identical execution paths between local and remote
- Eliminates code duplication and maintenance burden
- Simplifies connection resolution by using standard mechanisms

### Session Log Transfer (Completed)
- **Deterministic session paths**: Set `OSIRIS_LOGS_DIR="$PWD/logs"` in run.sh for predictable location
- **Full session copy**: Use `cp -a` to preserve timestamps when copying to `remote/session/`
- **Comprehensive status.json**: Include file sizes, counts, and existence checks for validation
- **Four-proof validation**: Exit code, steps completion, session copy, and events.jsonl existence
- **Recursive download**: E2B adapter downloads entire `remote/` directory including nested session logs
- **EntryInfo parsing**: Handle E2B SDK's EntryInfo objects by parsing name from string representation
- **Zero data loss**: Complete session artifacts transferred back to host for analysis

### Benign Warning Classification (Completed)
- **Stderr classification**: Categorize output into ERROR/WARNING/INFO severities using regex patterns
- **Smart display logic**: Show "Warnings from sandbox" for benign warnings, reserve "Errors detected" for real failures
- **Enhanced status.json**: Add `warnings_count` and `errors_count` fields for better observability
- **Common patterns**: Handle RuntimeWarning, DeprecationWarning, UserWarning, and other Python warnings
- **Traceback detection**: Properly identify Python exceptions and stack traces as errors
