# ADR-0041: E2B PyPI-Based Execution Architecture

## Status
Proposed

## Context

The current E2B implementation (ADR-0026) uses a **Transparent Proxy Architecture** with an RPC-based protocol. While this achieved 100% parity with local execution and production-ready status, it has introduced significant architectural complexity:

### Current Architecture Issues

1. **Duplicated Execution Logic** (ProxyWorker ~1500 lines)
   - `osiris/remote/proxy_worker.py` reimplements step execution logic
   - LocalAdapter (`osiris/runtime/local_adapter.py`) implements similar logic for local runs
   - Both must stay in sync, increasing maintenance burden
   - Bug fixes must be applied to both code paths

2. **Secrets in Config Files**
   - Connection configs are resolved on host and uploaded to sandbox with credentials embedded
   - While E2B sandboxes are trusted and ephemeral, this violates principle of least privilege
   - Credentials exist as files in sandbox filesystem (even if masked in artifacts)

3. **Per-File Artifact Transfer**
   - Artifacts downloaded individually from sandbox to host
   - Multiple network requests for large pipelines
   - No compression during transfer

4. **Runtime Dependency Installation**
   - Each pipeline run installs dependencies via pip (5-15 seconds overhead)
   - Component specs declare dependencies in `x-runtime.requirements`
   - No caching between runs (even for identical dependency sets)

5. **Version Synchronization Complexity**
   - ProxyWorker code must match host version
   - Uploaded as script file to sandbox
   - Risk of version mismatch if deployment process fails

### Why This Matters

With the recent **osiris-pipelines PyPI package** (v0.5.4+), we now have a better deployment model available. The package provides:
- Official versioned releases on PyPI
- Single source of truth for Osiris code
- Standard Python packaging infrastructure
- Simplified dependency management

This opens the possibility of running **identical Osiris CLI code** in both local and E2B environments, eliminating the need for separate execution logic.

### Input Key Naming Inconsistency (Discovered 2025-11-09)

The current RPC Proxy architecture has **divergent input handling** between LocalAdapter and ProxyWorker:

**LocalAdapter** (`osiris/core/runner_v0.py`):
```python
# Line 415-427
safe_key = df_keys[upstream_id]  # "df_extract_actors"
inputs[safe_key] = upstream_result["df"]
# Result: {"df_extract_actors": DataFrame}
```

**ProxyWorker** (`osiris/remote/proxy_worker.py`):
```python
# Line 1226
resolved[input_key] = df  # Just "df"
# Result: {"df": DataFrame}
```

**Problem:** Writers must accept **both** formats, adding tech debt to every writer driver:

```python
# Every writer needs this workaround:
for key, value in inputs.items():
    if (key.startswith("df_") or key == "df"):  # ← Tech debt!
        df = value
```

**Affected drivers:**
- `filesystem_csv_writer_driver.py` (fixed 2025-11-09)
- `supabase_writer_driver.py` (fixed 2025-11-09)
- Future writers must remember this pattern

**Root Cause:** ProxyWorker reimplements LocalAdapter logic but uses different conventions.

**PyPI-based approach eliminates this:**
- Sandbox runs **same LocalAdapter** as host
- One code path = one convention
- Zero tech debt in drivers

## Decision

We will refactor the E2B architecture to use **PyPI-based execution**:

### Core Principle
**Sandbox runs the same `osiris run` command as localhost, installed via PyPI package.**

### Architecture Changes

#### 1. Unified Execution Path
```
Local:  osiris run --last-compile
        └─> LocalAdapter → Driver → Data

E2B:    E2BSimpleAdapter → E2B Sandbox
                              └─> pip install osiris-pipelines=={version}
                              └─> osiris run --last-compile
                                    └─> LocalAdapter → Driver → Data
```

**Key Insight:** ProxyWorker is eliminated. Sandbox uses LocalAdapter directly.

#### 2. Environment Variable-Based Secrets
```python
# Host prepares env vars from local .env
env_vars = {
    'OSIRIS_CONNECTION_MYSQL_PROD_PASSWORD': os.getenv('MYSQL_PASSWORD'),
    'OSIRIS_CONNECTION_SUPABASE_DEV_URL': os.getenv('SUPABASE_URL'),
    'OSIRIS_CONNECTION_SUPABASE_DEV_KEY': os.getenv('SUPABASE_SERVICE_ROLE_KEY'),
}

# Set in E2B sandbox
await sandbox.set_env_vars(env_vars)

# Upload UNRESOLVED configs (connection refs only, no credentials)
await sandbox.filesystem.write("manifest.yaml", manifest_with_connection_refs)
```

**Security Improvement:** Credentials never written to files in sandbox.

#### 3. TGZ Artifact Bundle
```python
# After execution completes in sandbox
await sandbox.process.start("tar -czf /tmp/artifacts.tgz /home/user/session/{session_id}")

# Single download
await sandbox.download_file("/tmp/artifacts.tgz", local_artifacts_path)

# Extract on host
subprocess.run(["tar", "-xzf", "artifacts.tgz", "-C", session_dir])
```

**Performance Improvement:** One compressed transfer instead of N individual files.

#### 4. PyPI-Based Deployment
```python
# Host validates version match
local_version = osiris.__version__  # "0.5.6"

# Install exact version in sandbox
await sandbox.process.start(
    f"pip install osiris-pipelines=={local_version} --quiet"
)
```

**Reliability Improvement:** Standard PyPI infrastructure for versioning and caching.

#### 5. RPC Streaming Preserved
```python
# Osiris CLI gets optional streaming mode
osiris run --last-compile --stream-events

# When running in E2B, stream events to stdout (JSON Lines format)
# Host reads from sandbox.process.stdout and forwards to local events.jsonl
```

**User Experience:** Real-time progress visibility maintained (current RPC protocol works well).

### Implementation Components

#### New: E2BSimpleAdapter
- Location: `osiris/remote/e2b_simple_adapter.py` (~200 lines vs 800 in current implementation)
- Responsibilities:
  1. Create E2B sandbox with version-matched Osiris
  2. Set environment variables from host .env
  3. Upload compiled manifest (unresolved configs)
  4. Execute: `osiris run --last-compile --stream-events`
  5. Stream events from stdout
  6. Download artifact TGZ
  7. Cleanup sandbox

#### Modified: Osiris CLI
- New flags:
  - `--stream-events`: Output events to stdout as JSON Lines (instead of events.jsonl file)
  - `--base-path-env`: Read base_path from `OSIRIS_BASE_PATH` env var
- Connection resolver: Already supports env var resolution (no changes needed)

#### Deprecated: ProxyWorker
- `osiris/remote/proxy_worker.py` (1500 lines) → Deleted
- `osiris/remote/rpc_protocol.py` → Simplified (only for event streaming, not execution)
- `osiris/remote/e2b_transparent_proxy.py` → Renamed to `e2b_legacy_adapter.py`

## Consequences

### Advantages

1. **-1300 Lines of Code**
   - ProxyWorker eliminated (1500 lines)
   - E2BSimpleAdapter replaces E2BTransparentProxy (200 lines vs 800)
   - RPC protocol simplified (100 lines vs 400)
   - **Net reduction: ~1400 lines of complex async code**

2. **Zero Duplicated Logic**
   - Sandbox runs LocalAdapter (same as localhost)
   - Bug fixes automatically apply to both environments
   - Single execution path to test and maintain

3. **Improved Security**
   - Secrets never written to files in sandbox
   - Environment variables are E2B's native secret management
   - Follows principle of least privilege

4. **Faster Artifact Transfer**
   - TGZ compression reduces network traffic
   - Single HTTP request vs N requests
   - Estimated 3-5x speedup for large pipelines

5. **Simplified Deployment**
   - PyPI handles versioning, dependencies, and caching
   - No custom script upload mechanism
   - Standard Python packaging best practices

6. **Easier Debugging**
   - Identical code path locally and remotely
   - Can reproduce E2B issues locally by setting env vars
   - No custom RPC protocol to debug

7. **Better Version Control**
   - PyPI package versions are immutable
   - No risk of ProxyWorker/host version mismatch
   - Clear upgrade path (pip install --upgrade)

### Risks and Mitigations

1. **PyPI Availability Dependency**
   - Risk: PyPI downtime blocks E2B execution
   - Mitigation: E2B likely caches packages; fallback to legacy adapter if needed
   - Severity: Low (PyPI has 99.9% uptime SLA)

2. **Environment Variable Size Limits**
   - Risk: Large connection configs exceed env var size limits
   - Mitigation: E2B supports up to 32KB per variable (sufficient for typical configs)
   - Severity: Low (typical connection configs <1KB)

3. **RPC Streaming Complexity**
   - Risk: Streaming events from sandbox stdout may be less robust than current RPC
   - Mitigation: Use JSON Lines format (newline-delimited JSON) which is robust
   - Severity: Low (current RPC uses stdout anyway)

4. **Connection Resolution in Sandbox**
   - Risk: ConnectionResolver must work with only env vars (no .env file)
   - Mitigation: ConnectionResolver already supports env vars (search order includes os.environ)
   - Severity: None (already implemented)

5. **Base Path Configuration**
   - Risk: Osiris must use sandbox-specific base_path
   - Mitigation: Add `OSIRIS_BASE_PATH` env var support (simple change)
   - Severity: Low (10-line change in Config class)

### Performance Impact

| Metric | Current (RPC Proxy) | Proposed (PyPI) | Delta |
|--------|---------------------|-----------------|-------|
| Sandbox creation | ~8.3s | ~8.3s | No change |
| Dependency install | 5-15s per run | <1s (PyPI cache) | **-90%** |
| Artifact download | ~2.8s (N files) | <1s (TGZ) | **-65%** |
| Code upload | <1s (ProxyWorker) | 0s (PyPI) | **-100%** |
| Per-step overhead | <10ms | <10ms | No change |
| **Total E2B overhead** | **~11s** | **~7s** | **-36%** |

### Migration Path

1. **Phase 1: Add PyPI-based adapter**
   - Implement E2BSimpleAdapter alongside existing E2BTransparentProxy
   - Add CLI flags: `--stream-events`, `--base-path-env`
   - Test with parity suite

2. **Phase 2: Make PyPI-based default**
   - Change `--e2b` flag to use E2BSimpleAdapter
   - Add `--e2b-legacy` flag for old implementation
   - Update documentation

3. **Phase 3: Deprecate ProxyWorker**
   - Rename E2BTransparentProxy to E2BLegacyAdapter
   - Add deprecation warnings
   - Remove after 2 release cycles (v0.6.x)

4. **Phase 4: Cleanup**
   - Delete ProxyWorker code
   - Simplify RPC protocol (streaming only)
   - Update ADR-0026 with reference to ADR-0041

## Alternatives Considered

### Alternative 1: Keep Current RPC Proxy (Status Quo)
**Pros:**
- Already production-ready and tested
- No migration risk
- Full feature parity proven

**Cons:**
- Maintains duplicated logic (1500 lines)
- Secrets in config files
- Runtime dependency installation overhead
- Complex maintenance burden

**Decision:** Rejected. While functional, the architectural complexity is unsustainable long-term.

### Alternative 2: Docker-Based Execution
**Approach:** Package Osiris as Docker image, run in E2B container.

**Pros:**
- Standard container infrastructure
- Easy dependency management
- Reproducible environments

**Cons:**
- Heavier than pip install (~500MB vs ~50MB)
- E2B Docker support less mature than process execution
- Slower startup time (image pull)
- More complex image build/push pipeline

**Decision:** Rejected. Overkill for Osiris's needs; pip install is simpler and faster.

### Alternative 3: Hybrid (PyPI + Local ProxyWorker)
**Approach:** Install osiris-pipelines via PyPI but keep ProxyWorker for orchestration.

**Pros:**
- Incremental migration
- Keeps proven RPC protocol

**Cons:**
- Still maintains duplicated logic
- Doesn't solve core architectural issue
- Adds PyPI dependency without simplification benefit

**Decision:** Rejected. Doesn't achieve the goal of eliminating duplication.

### Alternative 4: Pre-built E2B Images
**Approach:** Create E2B template images with Osiris pre-installed.

**Pros:**
- Zero install time in sandbox
- Fastest startup

**Cons:**
- Must maintain separate image build pipeline
- Version synchronization complexity (image vs host)
- E2B image storage costs
- Slower iteration (image rebuild for each version)

**Decision:** Deferred. Could be added later as optimization, but PyPI-based approach is simpler starting point.

## Related ADRs

- **ADR-0026: E2B Transparent Proxy** - Superseded by this ADR
  - Current production implementation
  - Established parity requirements and performance baselines
  - ProxyWorker architecture to be replaced

- **ADR-0034: RPC-Based Communication** (if exists)
  - RPC protocol to be simplified for streaming only
  - Core protocol design can be preserved

## Implementation Details

### Phase 1: CLI Enhancement (1-2 days)

#### 1.1: Add --stream-events Flag
Location: `osiris/cli/main.py`

```python
@click.option('--stream-events', is_flag=True,
              help='Output events to stdout as JSON Lines (for E2B streaming)')
def run_command(stream_events: bool, **kwargs):
    if stream_events:
        # Redirect event handler to stdout instead of events.jsonl
        context.event_handler = StreamEventHandler(sys.stdout)
```

#### 1.2: Add OSIRIS_BASE_PATH Support
Location: `osiris/core/config.py`

```python
class Config:
    def __init__(self):
        # Existing: base_path from config file
        # New: Allow override from env var
        self.base_path = os.getenv('OSIRIS_BASE_PATH') or self.load_from_config()
```

#### 1.3: Connection Resolver Validation
Location: `tests/test_connection_resolver.py`

```python
def test_connection_resolver_env_vars_only():
    """Verify ConnectionResolver works with only env vars (no .env file)"""
    os.environ['OSIRIS_CONNECTION_MYSQL_PROD_PASSWORD'] = 'test123'
    resolver = ConnectionResolver()
    config = resolver.resolve('mysql', 'prod')
    assert config['password'] == 'test123'
```

### Phase 2: E2BSimpleAdapter Implementation (3-5 days)

Location: `osiris/remote/e2b_simple_adapter.py`

#### Core Methods

```python
class E2BSimpleAdapter(ExecutionAdapter):
    """Simplified E2B adapter using PyPI-installed Osiris in sandbox."""

    async def prepare(self, plan: dict, context: ExecutionContext) -> PreparedRun:
        """Prepare E2B sandbox with Osiris installed via PyPI."""
        # 1. Create E2B sandbox
        self.sandbox = await e2b.Sandbox.create(
            timeout=600,
            metadata={'session_id': context.session_id}
        )

        # 2. Set environment variables (secrets from host .env)
        env_vars = self._prepare_env_vars(context)
        await self.sandbox.set_env_vars(env_vars)

        # 3. Install Osiris from PyPI (version-matched)
        local_version = osiris.__version__
        await self.sandbox.process.start(
            f"pip install osiris-pipelines=={local_version} --quiet",
            timeout=60
        )

        # 4. Upload compiled manifest (unresolved configs)
        session_path = f"/home/user/session/{context.session_id}"
        await self.sandbox.filesystem.make_dir(session_path)
        await self.sandbox.filesystem.write(
            f"{session_path}/manifest.yaml",
            yaml.dump(plan)
        )

        return PreparedRun(session_id=context.session_id)

    async def execute(self, prepared: PreparedRun, context: ExecutionContext):
        """Execute pipeline in sandbox using standard Osiris CLI."""
        session_path = f"/home/user/session/{context.session_id}"

        # Execute: osiris run --last-compile --stream-events
        process = await self.sandbox.process.start(
            f"cd {session_path} && osiris run --last-compile --stream-events",
            on_stdout=self._handle_event_stream,
            on_stderr=lambda data: logger.error(data),
        )

        # Wait for completion
        await process.wait()

        return process.exit_code == 0

    async def collect(self, prepared: PreparedRun, context: ExecutionContext):
        """Download artifacts as TGZ bundle."""
        session_path = f"/home/user/session/{context.session_id}"

        # Create TGZ in sandbox
        await self.sandbox.process.start(
            f"tar -czf /tmp/artifacts.tgz -C {session_path} ."
        )

        # Download to host
        await self.sandbox.download_file(
            "/tmp/artifacts.tgz",
            context.base_path / f"artifacts_{context.session_id}.tgz"
        )

        # Extract
        subprocess.run([
            "tar", "-xzf",
            context.base_path / f"artifacts_{context.session_id}.tgz",
            "-C", context.session_dir
        ])

        # Cleanup
        await self.sandbox.close()

    def _prepare_env_vars(self, context: ExecutionContext) -> dict:
        """Extract Osiris-related env vars from host."""
        env_vars = {}

        # 1. Osiris config
        env_vars['OSIRIS_BASE_PATH'] = f"/home/user/session/{context.session_id}"

        # 2. Connection secrets (prefixed with OSIRIS_CONNECTION_)
        for key, value in os.environ.items():
            if key.startswith('OSIRIS_CONNECTION_'):
                env_vars[key] = value

        # 3. Legacy connection vars (MYSQL_PASSWORD, SUPABASE_URL, etc.)
        legacy_vars = [
            'MYSQL_PASSWORD', 'MYSQL_USER', 'MYSQL_HOST', 'MYSQL_DATABASE',
            'SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY',
        ]
        for key in legacy_vars:
            if key in os.environ:
                env_vars[key] = os.environ[key]

        return env_vars

    def _handle_event_stream(self, line: str):
        """Parse JSON Lines events from sandbox stdout."""
        try:
            event = json.loads(line)
            # Forward to host event handler
            self.context.emit_event(event)
        except json.JSONDecodeError:
            # Not an event, treat as log
            logger.info(f"[E2B] {line}")
```

### Phase 3: Testing and Validation (2-3 days)

#### 3.1: Parity Tests
Location: `tests/e2b/test_pypi_parity.py`

```python
@pytest.mark.e2b
def test_pypi_adapter_parity():
    """Verify PyPI-based E2B produces identical artifacts to local run."""
    # Run locally
    local_result = run_local("tests/fixtures/mysql_to_csv.yaml")

    # Run with PyPI adapter
    e2b_result = run_e2b_pypi("tests/fixtures/mysql_to_csv.yaml")

    # Compare artifacts
    assert_artifacts_identical(local_result.artifacts, e2b_result.artifacts)
    assert_event_counts_match(local_result.events, e2b_result.events)
    assert local_result.exit_code == e2b_result.exit_code
```

#### 3.2: Security Tests
Location: `tests/e2b/test_pypi_security.py`

```python
@pytest.mark.e2b
def test_secrets_not_in_sandbox_files():
    """Verify credentials never written to files in sandbox."""
    result = run_e2b_pypi_with_inspection("tests/fixtures/supabase_write.yaml")

    # Check all files in sandbox for password patterns
    for file_path in result.sandbox_files:
        content = read_sandbox_file(file_path)
        assert 'SUPABASE_SERVICE_ROLE_KEY' not in content
        assert os.getenv('MYSQL_PASSWORD') not in content
```

#### 3.3: Performance Tests
Location: `tests/e2b/test_pypi_performance.py`

```python
@pytest.mark.e2b
def test_pypi_adapter_overhead():
    """Measure E2B overhead with PyPI-based adapter."""
    result = run_e2b_pypi("tests/fixtures/mysql_to_csv.yaml")

    # Should be faster than current implementation
    assert result.metrics['e2b_overhead_ms'] < 7000  # <7s (vs 11s current)
    assert result.metrics['dependency_install_ms'] < 1000  # <1s (PyPI cache)
    assert result.metrics['artifacts_download_ms'] < 1000  # <1s (TGZ)
```

### Phase 4: Migration and Deprecation (1-2 days)

#### 4.1: Update Adapter Factory
Location: `osiris/core/adapter_factory.py`

```python
def create_adapter(config: AdapterConfig) -> ExecutionAdapter:
    if config.e2b:
        if config.e2b_legacy:
            # Old implementation
            return E2BLegacyAdapter(config)
        else:
            # New default
            return E2BSimpleAdapter(config)
    else:
        return LocalAdapter(config)
```

#### 4.2: Add Deprecation Warnings
Location: `osiris/remote/e2b_legacy_adapter.py`

```python
class E2BLegacyAdapter(ExecutionAdapter):
    """Legacy E2B adapter using ProxyWorker (DEPRECATED)."""

    def __init__(self, config):
        warnings.warn(
            "E2BLegacyAdapter is deprecated. Use E2BSimpleAdapter (default with --e2b). "
            "Legacy adapter will be removed in v0.7.0.",
            DeprecationWarning,
            stacklevel=2
        )
        super().__init__(config)
```

## Success Criteria

### Must Have (Phase 1-2)
- ✅ E2BSimpleAdapter passes all parity tests
- ✅ Secrets verified absent from sandbox files
- ✅ E2B overhead <7 seconds (vs 11s current)
- ✅ No regressions in local execution

### Should Have (Phase 3)
- ✅ PyPI adapter becomes default with --e2b flag
- ✅ Documentation updated with new architecture
- ✅ Migration guide for users

### Nice to Have (Phase 4)
- ✅ ProxyWorker code deleted
- ✅ RPC protocol simplified (streaming only)
- ✅ E2B template images (pre-installed Osiris) for <3s startup

## Timeline Estimate

| Phase | Task | Effort | Dependencies |
|-------|------|--------|--------------|
| 1 | CLI enhancement | 1-2 days | None |
| 2 | E2BSimpleAdapter | 3-5 days | Phase 1 |
| 3 | Testing | 2-3 days | Phase 2 |
| 4 | Migration | 1-2 days | Phase 3 |
| **Total** | **End-to-end** | **7-12 days** | Sequential |

## Questions and Decisions

### Q1: Should we support offline mode (no PyPI)?
**Decision:** No. E2B requires internet anyway. If PyPI is down, fallback to legacy adapter.

### Q2: How to handle version mismatches?
**Decision:** Fail fast. If host is v0.5.6 but PyPI only has v0.5.4, raise error and suggest upgrade/downgrade.

### Q3: What about component-specific dependencies?
**Decision:** Keep `x-runtime.requirements` in component specs. PyPI package includes core dependencies; component-specific ones still installed on-demand.

### Q4: Should we keep ProxyWorker for gradual migration?
**Decision:** Yes, keep as E2BLegacyAdapter for 2 release cycles (v0.6.x, v0.7.x), then remove.

### Q5: How to test locally without E2B API key?
**Decision:** Add `--e2b-simulate` flag that runs PyPI adapter logic but uses local subprocess instead of E2B sandbox.

## Conclusion

The PyPI-based E2B architecture represents a **major simplification** of the Osiris execution model. By eliminating ProxyWorker and using the same LocalAdapter in both environments, we reduce code complexity by ~1400 lines while improving security and performance.

This refactoring aligns with Osiris's core principle of **LLM-first design**: simple, transparent, and maintainable code that's easy for AI agents to understand and modify.

The migration path is low-risk (incremental, with fallback to legacy adapter) and the benefits are substantial (reduced maintenance, faster execution, better security).

**Recommendation:** Proceed with implementation starting with Phase 1 (CLI enhancement) to validate technical feasibility.
