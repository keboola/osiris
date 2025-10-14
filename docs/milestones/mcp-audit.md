# MCP Implementation Audit Report
**Branch**: `feature/mcp-server-opus`
**Date**: 2025-10-15
**Auditor**: Senior Release Auditor (Claude Code)
**Reference Documentation**:
- ADR-0036: MCP Interface
- docs/milestones/mcp-milestone.md
- docs/milestones/mcp-implementation.md
- docs/mcp/overview.md
- docs/mcp/tool-reference.md

---

## Executive Summary

The MCP server implementation on `feature/mcp-server-opus` is **NOT production-ready**. While the basic MCP server infrastructure exists and can perform handshakes, the **CLI-first adapter architecture** mandated by ADR-0036 is **completely missing**. Tools currently implement business logic directly instead of delegating to CLI commands, violating the core security principle that "no secrets flow through MCP."

**Readiness**: 🔴 **Critical Gaps** — ~40% complete
**Estimated Effort**: 2-3 weeks to production-readiness

### Critical Blockers (Phase 1)
1. ❌ CLI bridge component (`osiris/mcp/cli_bridge.py`) does not exist
2. ❌ CLI subcommand namespace (`osiris mcp <tool>`) not implemented
3. ❌ Tools bypass CLI delegation, access secrets directly
4. ❌ Filesystem contract not honored (hardcoded paths)
5. ❌ Error taxonomy partially implemented but not used in CLI bridge

---

## Detailed Gap Analysis

### 1. **Scope Completeness** ❌ FAIL

| Component | Expected (ADR-0036) | Actual | Status |
|-----------|---------------------|---------|---------|
| **CLI Bridge** | `osiris/mcp/cli_bridge.py` with `run_cli_json()` | ❌ **Missing** | 🔴 **CRITICAL** |
| **CLI Subcommands** | 10 tools under `osiris mcp <tool>` | ❌ Only 3 (`run`, `clients`, `tools`) | 🔴 **CRITICAL** |
| **connections_list** delegation | → `osiris mcp connections list --json` | ❌ Direct YAML loading | 🔴 **CRITICAL** |
| **connections_doctor** delegation | → `osiris mcp connections doctor --json` | ❌ Direct resolution | 🔴 **CRITICAL** |
| **discovery_request** delegation | → `osiris mcp discovery run --json` | ❌ Direct driver access | 🔴 **CRITICAL** |
| **oml_validate** delegation | → `osiris mcp oml validate --json` | ❓ Not verified | 🟡 REVIEW |
| **Tool registration** | 10 tools with aliases | ✅ Implemented | 🟢 PASS |
| **Selftest** | `osiris mcp run --selftest` | ✅ Exists | 🟢 PASS |

**Evidence**:
- `osiris/mcp/cli_bridge.py`: **File does not exist** (Glob search returned empty)
- `osiris/cli/mcp_cmd.py:283-293`: Only handles `run`, `clients`, `tools` subcommands
- `osiris/mcp/tools/connections.py:40-44`: Directly calls `load_connections_yaml()` instead of subprocess
- `osiris/mcp/tools/discovery.py:124-128`: Directly calls `parse_connection_ref()` and `resolve_connection()`

**Missing CLI Commands** (per mcp-implementation.md §10):
```bash
osiris mcp connections list --json    # ❌ Not implemented
osiris mcp connections doctor --json  # ❌ Not implemented
osiris mcp discovery run --json       # ❌ Not implemented
osiris mcp oml schema --json          # ❌ Not implemented
osiris mcp oml validate --json        # ❌ Not implemented
osiris mcp guide start --json         # ❌ Not implemented
osiris mcp memory capture --json      # ❌ Not implemented
osiris mcp usecases list --json       # ❌ Not implemented
osiris mcp components list --json     # ❌ Not implemented
osiris mcp oml save --json            # ❌ Not implemented
```

---

### 2. **Filesystem Contract** ❌ FAIL

| Requirement | Expected | Actual | Status |
|------------|----------|--------|--------|
| **Config-driven paths** | Load from `osiris.yaml` `filesystem.mcp_logs_dir` | ❌ Hardcoded `DEFAULT_AUDIT_DIR`, `DEFAULT_TELEMETRY_DIR` | 🔴 **CRITICAL** |
| **osiris init** writes keys | `filesystem.base_path`, `filesystem.mcp_logs_dir` | ❓ Not verified | 🟡 REVIEW |
| **MCP server reads config** | `get_base_path()`, `get_mcp_logs_dir()` from YAML | ❌ Uses `os.environ.get("OSIRIS_HOME")` | 🔴 **CRITICAL** |
| **Logs directory** | `<base_path>/.osiris/mcp/logs/` | ❌ `Path.home() / ".osiris_audit"` (wrong location) | 🔴 **CRITICAL** |

**Evidence**:
- `osiris/mcp/config.py:38-41`:
  ```python
  DEFAULT_CACHE_DIR = Path.home() / ".osiris_cache" / "mcp"
  DEFAULT_MEMORY_DIR = Path.home() / ".osiris_memory" / "mcp"
  DEFAULT_AUDIT_DIR = Path.home() / ".osiris_audit"  # ❌ Should be <base_path>/.osiris/mcp/logs/audit
  DEFAULT_TELEMETRY_DIR = Path.home() / ".osiris_telemetry"
  ```

- `osiris/mcp/config.py:109-122`: Uses `OSIRIS_HOME` env var instead of loading from `osiris.yaml`:
  ```python
  osiris_home = os.environ.get("OSIRIS_HOME")  # ❌ Should use config.filesystem.base_path
  if osiris_home:
      base_path = Path(osiris_home)
      self.cache_dir = base_path / "cache" / "mcp"
  ```

**Fix**: Must implement `MCPFilesystemConfig.from_config()` that loads `osiris.yaml` and resolves paths:
```python
from osiris.core.fs_config import load_osiris_config

def from_config(config_path: str = "osiris.yaml") -> MCPConfig:
    fs_config, ids_config, raw = load_osiris_config(config_path)
    base_path = Path(fs_config.base_path)
    mcp_logs_dir = raw.get("filesystem", {}).get("mcp_logs_dir", ".osiris/mcp/logs")
    return {
        "audit_dir": base_path / mcp_logs_dir / "audit",
        "telemetry_dir": base_path / mcp_logs_dir / "telemetry",
        ...
    }
```

---

### 3. **CLI-First Adapter Compliance** ❌ FAIL

**Critical Violation**: Tools directly access connection secrets instead of delegating to CLI layer.

| Tool | Expected Delegation | Actual Implementation | Violation |
|------|---------------------|----------------------|-----------|
| `connections_list` | Subprocess → `osiris mcp connections list --json` | Direct call to `load_connections_yaml()` | 🔴 **Secrets in MCP process** |
| `connections_doctor` | Subprocess → `osiris mcp connections doctor --json` | Direct call to `resolve_connection()` | 🔴 **Secrets in MCP process** |
| `discovery_request` | Subprocess → `osiris mcp discovery run --json` | Direct driver instantiation + connection resolution | 🔴 **Secrets in MCP process** |

**Evidence - Connections Tool (osiris/mcp/tools/connections.py)**:
```python
# Line 40-44: ❌ VIOLATES CLI-FIRST ARCHITECTURE
def _load_connections(self) -> Dict[str, Dict[str, Any]]:
    from osiris.core.config import load_connections_yaml  # ❌ Direct YAML loading
    connections = load_connections_yaml()  # ❌ Reads ${MYSQL_PASSWORD} in MCP process
    return connections

# Line 146-152: ❌ SECRETS EXPOSED TO MCP
resolved = resolve_connection(family, alias)  # ❌ Resolves env vars in MCP process
```

**Evidence - Discovery Tool (osiris/mcp/tools/discovery.py)**:
```python
# Line 124-128: ❌ VIOLATES CLI-FIRST ARCHITECTURE
from osiris.core.config import parse_connection_ref, resolve_connection
family, alias = parse_connection_ref(connection_id)
connection = resolve_connection(family, alias)  # ❌ Secrets leaked to MCP
```

**Expected Implementation** (per ADR-0036 §56-79):
```python
# osiris/mcp/cli_bridge.py (MISSING FILE)
async def run_cli_json(args: List[str], timeout_s: float = 30.0) -> Dict[str, Any]:
    """Run CLI command and return parsed JSON output."""
    import subprocess
    result = subprocess.run(
        ["osiris"] + args + ["--json"],
        capture_output=True,
        timeout=timeout_s,
        env=os.environ  # Inherit secrets from shell
    )
    if result.returncode != 0:
        raise CLIBridgeError(result.stderr.decode())
    return json.loads(result.stdout.decode())

# osiris/mcp/tools/connections.py (FIX REQUIRED)
async def list(self, args: Dict[str, Any]) -> Dict[str, Any]:
    # ✅ CORRECT: Delegate to CLI
    return await run_cli_json(["mcp", "connections", "list"])
```

---

### 4. **Error Taxonomy** 🟡 PARTIAL

| Component | Expected | Actual | Status |
|-----------|----------|--------|--------|
| **Deterministic codes** | E_CONN_*, SCHEMA/OML###, POLICY/POL### | ✅ Implemented in `errors.py` | 🟢 PASS |
| **CLI bridge error mapping** | `map_cli_error_to_mcp()` function | ✅ Implemented (just added) | 🟢 PASS |
| **Tools use error taxonomy** | All tools return `OsirisError` with codes | ✅ Partially (tools use ErrorFamily) | 🟡 PARTIAL |
| **CLI bridge uses mapper** | CLI output mapped to MCP errors | ❌ CLI bridge doesn't exist | 🔴 **BLOCKED** |

**Evidence**:
- `osiris/mcp/errors.py:12-70`: ✅ Deterministic ERROR_CODES table complete
- `osiris/mcp/errors.py:271-343`: ✅ `map_cli_error_to_mcp()` function exists
- `osiris/mcp/tools/connections.py:85-90`: ✅ Tools raise `OsirisError` with proper families

**Blocker**: Error mapping is implemented but **cannot be used** until CLI bridge exists.

---

### 5. **Configuration Resolution** 🟡 PARTIAL

| Component | Expected | Actual | Status |
|-----------|----------|--------|--------|
| **OSIRIS_HOME resolution** | Env → `osiris.yaml` → default | ✅ Implemented in `mcp_entrypoint.py` | 🟢 PASS |
| **Connection file search** | OSIRIS_HOME → CWD → parent → repo | ❓ Not verified (depends on CLI layer) | 🟡 REVIEW |
| **Claude Desktop config** | `osiris mcp clients` outputs correct snippet | ✅ Implemented | 🟢 PASS |

**Evidence**:
- `osiris/cli/mcp_entrypoint.py:54-84`: ✅ Proper OSIRIS_HOME resolution with precedence
- `osiris/cli/mcp_cmd.py:151-195`: ✅ `cmd_clients()` generates correct Claude Desktop config

**Issue**: Resolution works for MCP server bootstrap, but tools bypass it by accessing config directly.

---

### 6. **Security Model** ❌ FAIL

**Critical Security Violation**: MCP server process **directly accesses secrets**.

| Principle | Expected | Actual | Status |
|-----------|----------|--------|--------|
| **No secrets in MCP** | All secret ops delegated to CLI subprocess | ❌ MCP calls `resolve_connection()` directly | 🔴 **CRITICAL** |
| **Environment inheritance** | CLI subprocess inherits env, MCP doesn't touch | ❌ MCP reads env vars for resolution | 🔴 **CRITICAL** |
| **Secret redaction** | Secrets masked in audit logs | ✅ Implemented in `_sanitize_config()` | 🟢 PASS |

**Evidence of Violation**:
```python
# osiris/mcp/tools/connections.py:146-152
resolved = resolve_connection(family, alias)  # ← This resolves ${MYSQL_PASSWORD} in MCP process!
```

**Expected**: MCP should NEVER call `resolve_connection()`. Instead:
```python
result = await run_cli_json(["mcp", "connections", "doctor", connection_id])
# CLI process (with shell env) resolves ${MYSQL_PASSWORD}
# MCP receives sanitized JSON response
```

---

### 7. **Test Coverage** 🟡 PARTIAL

| Test Area | Expected | Actual | Status |
|-----------|----------|--------|--------|
| **MCP server boot** | ✅ `test_server_boot.py` | ✅ Exists (114 tests pass) | 🟢 PASS |
| **CLI bridge tests** | `test_cli_bridge.py` with mock subprocess | ❌ **Missing** | 🔴 **CRITICAL** |
| **No-env scenario** | `test_no_env_scenario.py` | ❌ **Missing** | 🔴 **CRITICAL** |
| **Tool tests** | Mock CLI calls in tool tests | ❌ Tests use direct mocks | 🔴 **CRITICAL** |
| **Selftest** | <2s, exercises delegated tools | ✅ Exists but doesn't test delegation | 🟡 PARTIAL |

**Evidence**:
- `tests/mcp/` directory: ✅ 12 test modules, 114 tests pass
- `tests/mcp/test_cli_bridge.py`: ❌ File does not exist
- `tests/mcp/test_tools_connections.py`: Tests mock `load_connections_yaml()` directly instead of mocking subprocess

**Required Tests** (per mcp-implementation.md §11):
```python
# tests/mcp/test_cli_bridge.py (MISSING)
def test_run_cli_json_success():
    """Test successful CLI delegation."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout=b'{"status": "ok"}')
        result = run_cli_json(["mcp", "connections", "list"])
        assert result["status"] == "ok"
```

---

### 8. **Usability & Integration** 🟡 PARTIAL

| Flow | Expected | Actual | Status |
|------|----------|--------|--------|
| **End-to-end OML authoring** | Claude Desktop → MCP → CLI → DB → OML | ❌ Breaks at MCP→CLI boundary | 🔴 **BLOCKED** |
| **Connection discovery** | Works without env vars in Claude config | ❌ Requires env vars (violates spec) | 🔴 **FAIL** |
| **Schema validation** | `oml_validate` returns ADR-0019 diagnostics | ❓ Not verified | 🟡 REVIEW |
| **Tool discovery** | `osiris mcp tools` lists all 10 tools | ✅ Implemented | 🟢 PASS |

**Evidence - User Experience Failure**:
1. User runs `osiris mcp clients` → Gets config with `OSIRIS_HOME` env var
2. User adds config to Claude Desktop → **Secrets still don't work**
3. Claude Desktop runs MCP server → MCP tries `resolve_connection()` → **Fails** because Claude Desktop doesn't pass `.env` variables
4. User **forced to add secrets to Claude Desktop config** → Violates security model

**Expected**: User should NOT need any env vars in Claude Desktop config. CLI should handle all secrets.

---

## Phased Work Plan

### **Phase 1: Critical Blockers** (Est: 5-7 days)

**Goal**: Implement CLI-first adapter architecture and restore security model.

#### 1.1 Create CLI Bridge Component
- [ ] **File**: `osiris/mcp/cli_bridge.py`
  - Implement `run_cli_json(args, timeout_s)` with subprocess.run
  - Implement `ensure_base_path()` for config resolution
  - Add error mapping using `map_cli_error_to_mcp()`
  - Add correlation ID generation (`mcp_<uuid>`)
  - Add duration_ms, bytes_in/out tracking
- [ ] **Tests**: `tests/mcp/test_cli_bridge.py`
  - Mock subprocess for all CLI commands
  - Test timeout handling
  - Test error code mapping (E_CONN_*, SCHEMA/*, etc.)
  - Test config path resolution

#### 1.2 Implement CLI Subcommands
- [ ] **File**: `osiris/cli/mcp_cmd.py` - Add subcommands:
  ```python
  def cmd_connections_list(args): ...
  def cmd_connections_doctor(args): ...
  def cmd_discovery_run(args): ...
  def cmd_oml_schema(args): ...
  def cmd_oml_validate(args): ...
  def cmd_oml_save(args): ...
  def cmd_guide_start(args): ...
  def cmd_memory_capture(args): ...
  def cmd_usecases_list(args): ...
  def cmd_components_list(args): ...
  ```
- [ ] Each command outputs `--json` format matching tool schemas
- [ ] Commands load secrets from env (via shell inheritance)
- [ ] Verify: `osiris mcp connections list --json` works standalone

#### 1.3 Refactor Tools to Use CLI Delegation
- [ ] **File**: `osiris/mcp/tools/connections.py`
  - Replace `_load_connections()` with `await run_cli_json(["mcp", "connections", "list"])`
  - Replace `resolve_connection()` with `await run_cli_json(["mcp", "connections", "doctor", connection_id])`
- [ ] **File**: `osiris/mcp/tools/discovery.py`
  - Replace `_perform_discovery()` with `await run_cli_json(["mcp", "discovery", "run", ...])

`
  - Remove direct `parse_connection_ref()` and `resolve_connection()` calls
- [ ] **Files**: `oml.py`, `guide.py`, `memory.py`, `usecases.py`, `components.py`
  - Implement CLI delegation for all secret-requiring operations
  - In-process operations (validation, schema retrieval) can remain if they don't touch secrets

#### 1.4 Fix Filesystem Contract
- [ ] **File**: `osiris/mcp/config.py`
  - Replace hardcoded `DEFAULT_*_DIR` with config loader
  - Implement `MCPFilesystemConfig.from_config(config_path)` using `load_osiris_config()`
  - Use `filesystem.base_path` and `filesystem.mcp_logs_dir` from YAML
  - Emit WARNING if falling back to env vars
- [ ] **File**: `osiris/core/config_generator.py` (or init command)
  - Ensure `osiris init` writes:
    ```yaml
    filesystem:
      base_path: "<absolute_project_path>"
      mcp_logs_dir: ".osiris/mcp/logs"
    ```
- [ ] **Tests**: `tests/mcp/test_filesystem_contract_mcp.py`
  - Verify logs write to `<base_path>/.osiris/mcp/logs/`
  - Verify config-first precedence (YAML > env > default)

#### 1.5 Update Tests
- [ ] **File**: `tests/mcp/test_no_env_scenario.py`
  - Run MCP server with all env vars unset
  - Verify CLI delegation works (mocked subprocess)
  - Verify connections resolve in CLI layer (not MCP)
- [ ] **Files**: `tests/mcp/test_tools_*.py`
  - Replace direct mocks with subprocess mocks
  - Mock `run_cli_json()` instead of `load_connections_yaml()`

**Definition of Done**:
- ✅ All 10 CLI commands exist under `osiris mcp <tool> --json`
- ✅ `osiris/mcp/cli_bridge.py` exists with full subprocess delegation
- ✅ MCP server NEVER calls `resolve_connection()` or `load_connections_yaml()` directly
- ✅ `pytest tests/mcp/` passes with no env vars set
- ✅ `osiris mcp run --selftest` exercises at least one delegated tool (<2s)
- ✅ Logs appear in `<base_path>/.osiris/mcp/logs/` (not `~/.osiris_audit/`)

---

### **Phase 2: Functional Alignments** (Est: 3-4 days)

**Goal**: Complete missing features and ensure end-to-end workflows.

#### 2.1 Complete Tool Implementations
- [ ] Verify all 10 tools return spec-compliant JSON (per tool-reference.md)
- [ ] Add missing fields in tool responses (correlation_id, duration_ms, etc.)
- [ ] Ensure deterministic error codes in all error paths
- [ ] Test alias resolution (`connections.list` → `connections_list`)

#### 2.2 Observability & Telemetry
- [ ] Verify audit logs include:
  - Tool name, sanitized arguments
  - Correlation ID (`mcp_<uuid>`)
  - Duration, payload size
  - Secret redaction
- [ ] Verify telemetry events emit per ADR-0036 spec
- [ ] Test log rotation/retention (if applicable)

#### 2.3 Integration Testing
- [ ] **File**: `tests/integration/test_mcp_e2e.py`
  - Test full workflow: connections → discovery → oml_validate → oml_save
  - Mock CLI layer (subprocess)
  - Verify no env vars required in MCP process
- [ ] Manual test with Claude Desktop (real stdio connection)
- [ ] Verify selftest completes <2s

**Definition of Done**:
- ✅ All tools return correct JSON schemas
- ✅ Audit logs written to correct location with all required fields
- ✅ Selftest verifies tool registry, alias resolution, and at least one delegated call
- ✅ Manual Claude Desktop test succeeds without env vars in config

---

### **Phase 3: Documentation & Polish** (Est: 2-3 days)

**Goal**: Align documentation with implementation and prepare for release.

#### 3.1 Documentation Updates
- [ ] **ADR-0036 addendum**: Document actual CLI bridge implementation
- [ ] **docs/mcp/overview.md**: Update CLI delegation examples with actual commands
- [ ] **docs/mcp/tool-reference.md**: Verify all tool schemas match implementation
- [ ] **docs/milestones/mcp-implementation.md**: Check off completed items

#### 3.2 Configuration Reference
- [ ] Document `filesystem.mcp_logs_dir` in config reference
- [ ] Document env var precedence (YAML > env > default)
- [ ] Add troubleshooting guide for common Claude Desktop issues

#### 3.3 Release Preparation
- [ ] Update CHANGELOG.md with MCP v0.5.0 changes
- [ ] Verify `requirements.txt` pins official MCP SDK (no `fastmcp`)
- [ ] Bump version to 0.5.0 in `pyproject.toml`
- [ ] Create migration guide from v0.4.x

**Definition of Done**:
- ✅ All docs match actual implementation
- ✅ `osiris mcp clients --json` snippet works copy/paste in Claude Desktop
- ✅ CHANGELOG.md documents breaking changes (tool names, CLI-first adapter)
- ✅ Release checklist complete

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **Secret exposure in current state** | 🔴 Critical | High | Do NOT merge to main until Phase 1 complete |
| **Breaking changes for existing users** | 🟡 Medium | High | Provide clear migration guide, test backward compat aliases |
| **Claude Desktop integration failures** | 🟡 Medium | Medium | Manual testing before release, document known issues |
| **Performance regression from subprocess** | 🟢 Low | Low | Profile CLI calls, optimize subprocess overhead |
| **Test coverage gaps** | 🟡 Medium | Medium | Add integration tests, manual QA checklist |

---

## Recommendations

### Immediate Actions
1. **DO NOT MERGE** to main until Phase 1 is complete
2. Create `feature/mcp-cli-bridge` sub-branch for CLI adapter work
3. Assign senior developer to Phase 1 implementation (critical security work)
4. Add PR template requiring CLI bridge tests for any MCP tool changes

### Architecture Decisions
1. **Reaffirm ADR-0036**: CLI-first is non-negotiable for security
2. **Document trade-offs**: Subprocess overhead (~10-50ms per call) acceptable for security isolation
3. **Consider**: Direct implementation for read-only tools (oml_schema_get, usecases_list) if documented

### Process Improvements
1. Add CI check: Fail if `osiris/mcp/tools/*.py` imports `resolve_connection` or `load_connections_yaml`
2. Add integration test: Run MCP with empty env, verify all tools work
3. Add docs sync check: Verify ADR/milestone docs match implementation

---

## Appendix: File-Level Evidence

### Missing Files
| File | Status | Priority |
|------|--------|----------|
| `osiris/mcp/cli_bridge.py` | ❌ **Missing** | 🔴 **Critical** |
| `tests/mcp/test_cli_bridge.py` | ❌ **Missing** | 🔴 **Critical** |
| `tests/mcp/test_no_env_scenario.py` | ❌ **Missing** | 🔴 **Critical** |

### Files Requiring Major Changes
| File | Issue | Fix |
|------|-------|-----|
| `osiris/mcp/tools/connections.py` | Direct `load_connections_yaml()` call | Replace with `run_cli_json(["mcp", "connections", "list"])` |
| `osiris/mcp/tools/discovery.py` | Direct `resolve_connection()` call | Replace with `run_cli_json(["mcp", "discovery", "run", ...])` |
| `osiris/mcp/config.py` | Hardcoded `DEFAULT_AUDIT_DIR` | Load from `osiris.yaml` via `load_osiris_config()` |
| `osiris/cli/mcp_cmd.py` | Only 3 subcommands | Add 10 CLI subcommands for tool delegation |

### Files Compliant with Spec
| File | Compliance | Notes |
|------|------------|-------|
| `osiris/mcp/errors.py` | ✅ Full | Deterministic error codes implemented correctly |
| `osiris/mcp/server.py` | ✅ Partial | Server boot compliant, tools need delegation |
| `osiris/cli/mcp_entrypoint.py` | ✅ Full | OSIRIS_HOME resolution correct |

---

## Sign-Off

**Audit Status**: 🔴 **NOT PRODUCTION-READY**

**Recommendation**: Implement Phase 1 (Critical Blockers) before any production deployment or main branch merge. Current implementation violates ADR-0036 security model and exposes secrets in MCP process.

**Next Review**: After Phase 1 completion, re-audit security model and CLI delegation compliance.

---

*This audit treats documentation as source of truth per requirements. Implementation must be brought into compliance with ADR-0036, docs/milestones/mcp-milestone.md, and docs/mcp/*.md specifications.*
