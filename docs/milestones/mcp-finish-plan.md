# MCP v0.5.0 CLI-First Adapter Implementation Plan

**Document**: `docs/milestones/mcp-finish-plan.md`
**Branch**: `feature/mcp-server-opus`
**Target Release**: Osiris v0.5.0
**Created**: 2025-10-15
**Status**: Engineering Work Plan - FINAL

## Executive Summary

This plan completes the MCP server implementation to achieve production readiness by enforcing the CLI-first security model mandated by ADR-0036. The current implementation (~60% complete, 114 tests passing) has a **critical security violation** where MCP tools directly access secrets. This plan addresses all gaps identified in `docs/milestones/mcp-audit.md`.

**Total Estimated Effort**: 12.5-15.5 days (2.5-3 weeks)
**Priority**: =4 CRITICAL - Security violation blocks production use

---

## Phase 1: Critical Security Implementation

### Objective

Implement CLI-first adapter architecture to eliminate all secret access from MCP process. This is the **minimum viable security fix** required before any production use.

### Deliverables

#### 1.1 CLI Bridge Component

- **File**: `osiris/mcp/cli_bridge.py` (NEW - ~250 lines)
  ```python
  # Core functions to implement:
  async def run_cli_json(args: List[str], timeout_s: float = 30.0) -> Dict[str, Any]
  def ensure_base_path() -> Path
  def generate_correlation_id() -> str
  def track_metrics(start_time: float, bytes_in: int, bytes_out: int) -> Dict
  ```

#### 1.2 CLI Subcommand Infrastructure

- **File**: `osiris/cli/mcp_cmd.py` (UPDATE - add ~500 lines)
  - Add router for 10 new subcommands under `osiris mcp <tool>`
  - Each subcommand must output `--json` format matching tool schemas
  - Implement argument parsing for each tool

#### 1.3 Individual CLI Subcommands

- **Files**: Create or update in `osiris/cli/mcp_subcommands/` (NEW directory)
  - `connections_cmds.py`: `list()`, `doctor(connection_id)`
  - `discovery_cmds.py`: `run(connection_id, component_id, samples)`
  - `oml_cmds.py`: `schema()`, `validate(pipeline)`, `save(pipeline)`
  - `guide_cmds.py`: `start(context_file)`
  - `memory_cmds.py`: `capture(session_id, consent)`
  - `usecases_cmds.py`: `list(category)`
  - `components_cmds.py`: `list()`

#### 1.4 Tool Refactoring for Delegation

- **Files to modify**:
  - `osiris/mcp/tools/connections.py` (~50 lines changed)
    - Remove `_load_connections()`, replace with `run_cli_json(["mcp", "connections", "list"])`
    - Remove `resolve_connection()`, replace with `run_cli_json(["mcp", "connections", "doctor", id])`
  - `osiris/mcp/tools/discovery.py` (~75 lines changed)
    - Remove `_perform_discovery()`, replace with `run_cli_json(["mcp", "discovery", "run", ...])`
    - Remove all `parse_connection_ref()` and `resolve_connection()` calls
  - `osiris/mcp/tools/oml.py` (~30 lines changed)
    - Delegate `validate()` to CLI for consistency
  - Other tools: Minimal changes for consistency

#### 1.5 Filesystem Contract Compliance

- **File**: `osiris/mcp/config.py` (UPDATE - ~100 lines)

  ```python
  # Replace hardcoded paths with:
  class MCPFilesystemConfig:
      @classmethod
      def from_config(cls, config_path: str = "osiris.yaml") -> "MCPFilesystemConfig":
          # Load from osiris.yaml filesystem.* keys
          # Fall back to env vars with WARNING
          # Never use hardcoded home directory paths
  ```

- **File**: `osiris/core/config_generator.py` (UPDATE - ~20 lines)
  - Ensure `osiris init` writes:
    - `filesystem.base_path: "<absolute_path>"`
    - `filesystem.mcp_logs_dir: ".osiris/mcp/logs"`

#### 1.6 Additional Infrastructure & Verification

- **File**: `tests/cli/test_init_writes_mcp_logs_dir.py` (NEW - ~100 lines)
  - Test that `osiris init` writes required MCP config keys
  - Verify absolute `base_path` is generated
  - Verify `filesystem.mcp_logs_dir` is added to config

- **File**: `osiris/mcp/clients_config.py` (NEW/UPDATE - ~150 lines)
  - Implement `osiris mcp clients` command behavior
  - Output Claude Desktop snippet with `osiris.py mcp run`
  - Command: `/bin/bash`, args: `["-lc", "cd <base_path> && exec <venv_python> <base_path>/osiris.py mcp run"]`
  - **No** `OSIRIS_HOME`/`PYTHONPATH` by default
  - `--json` flag returns only JSON snippet

- **CI Verification Guards** (UPDATE - CI configuration)
  - Verify `osiris.yaml` has absolute `base_path` and `mcp_logs_dir`
  - Verify `osiris mcp clients --json` contains `osiris.py mcp run`
  - Add to GitHub Actions workflow or equivalent CI system

### Test Coverage Requirements

#### New Test Files

- `tests/mcp/test_cli_bridge.py` (~200 lines)

  - Test `run_cli_json()` with mocked subprocess
  - Test timeout handling (30s default)
  - Test error mapping with `map_cli_error_to_mcp()`
  - Test correlation ID generation
  - Test metrics tracking

- `tests/mcp/test_cli_subcommands.py` (~300 lines)

  - Test all 10 CLI subcommands with mocked dependencies
  - Verify JSON output schemas
  - Test argument parsing
  - Test error codes

- `tests/mcp/test_no_env_scenario.py` (~150 lines)

  - Run MCP server with all env vars unset
  - Verify tools work via CLI delegation
  - Verify no direct secret access

- `tests/mcp/test_filesystem_contract_mcp.py` (~100 lines)
  - Verify logs write to `<base_path>/.osiris/mcp/logs/`
  - Test config-first precedence (YAML > env > default)
  - Verify no hardcoded paths

#### Updated Test Files

- `tests/mcp/test_tools_connections.py` - Mock `run_cli_json()` instead of `load_connections_yaml()`
- `tests/mcp/test_tools_discovery.py` - Mock CLI delegation instead of direct driver calls
- All other tool tests: Update mocks for delegation pattern

### Risks & Dependencies

- **=4 Critical Risk**: Current code exposes secrets in MCP process (production blocker)
- **=� Medium Risk**: Subprocess overhead (~10-50ms per call) may affect performance
- **=� Medium Risk**: Breaking change for any existing MCP integrations
- **Dependencies**: Requires `osiris.yaml` config to be properly initialized

### Estimated Effort

**6-7.5 days** (48-60 hours)

- CLI Bridge: 1 day
- CLI Subcommands: 2 days
- Tool Refactoring: 1-2 days
- Filesystem Contract: 0.5 days
- Additional Infrastructure: 0.5 days (F1.18-F1.20)
- Testing: 1.5-2 days

### Definition of Done

- [ ] `osiris/mcp/cli_bridge.py` exists and all functions implemented
- [ ] All 10 CLI subcommands executable: `osiris mcp <tool> <action> --json`
- [ ] Zero imports of `resolve_connection()` or `load_connections_yaml()` in `osiris/mcp/tools/*.py`
- [ ] `pytest tests/mcp/test_no_env_scenario.py` passes with no env vars
- [ ] `osiris mcp run --selftest` completes in <2s and exercises delegated tools
- [ ] Logs appear in `<base_path>/.osiris/mcp/logs/` not `~/.osiris_audit/`
- [ ] CI check added: Fail on forbidden imports in MCP tools
- [ ] Run-anywhere behavior verified: selftest & server work from any CWD
- [ ] `osiris mcp clients` outputs correct Claude Desktop snippet with `osiris.py mcp run`

---

## Phase 2: Functional Parity & Completeness

### Objective

Complete all missing features to achieve full parity with ADR-0036 specification. Ensure end-to-end workflows function correctly with CLI delegation.

### Deliverables

#### 2.1 Complete Tool Response Schemas

- **Files**: All `osiris/mcp/tools/*.py` (~200 lines total)
  - Add missing response fields (correlation_id, duration_ms, bytes_in/out)
  - Ensure deterministic error codes in all error paths
  - Verify alias resolution (`connections.list` � `connections_list`)

#### 2.2 Telemetry & Audit Enhancements

- **File**: `osiris/mcp/telemetry.py` (UPDATE - ~50 lines)

  - Ensure all events include: tool, correlation_id, duration_ms, payload size
  - Write to `<base_path>/.osiris/mcp/logs/telemetry/events.jsonl`

- **File**: `osiris/mcp/audit.py` (UPDATE - ~75 lines)
  - Implement structured audit events with secret redaction
  - Write to `<base_path>/.osiris/mcp/logs/audit/<correlation_id>.json`
  - Include CLI delegation details

#### 2.3 Resource URI Compliance

- **File**: `osiris/mcp/resolver.py` (VERIFY - existing 319 lines)
  - Verify all `osiris://mcp/` URIs resolve correctly
  - Ensure resources load from `osiris/mcp/data/` structure
  - Test with selftest

#### 2.4 Discovery Cache Integration

- **File**: `osiris/mcp/cache.py` (UPDATE - ~50 lines)
  - Ensure cache writes to `<base_path>/.osiris/mcp/logs/cache/`
  - Implement 24-hour TTL correctly
  - Work with CLI delegation

#### 2.5 Memory & Session Management

- **File**: `osiris/mcp/tools/memory.py` (UPDATE - ~100 lines)
  - Implement PII redaction before capture
  - Require explicit consent flag
  - Store in `<base_path>/.osiris/mcp/logs/memory/sessions/`

### Test Coverage Requirements

#### Integration Tests

- `tests/integration/test_mcp_e2e.py` (NEW - ~300 lines)

  - Full workflow: connections � discovery � oml_validate � oml_save
  - Mock CLI layer completely
  - Verify no env vars required
  - Test with realistic data

- `tests/integration/test_mcp_claude_desktop.py` (NEW - ~200 lines)
  - Simulate Claude Desktop handshake
  - Test all tool calls with aliases
  - Verify stdio protocol compliance
  - Test payload limits (16MB)

#### Performance Tests

- `tests/performance/test_mcp_overhead.py` (NEW - ~150 lines)
  - Measure subprocess overhead per tool
  - Verify selftest <2s requirement
  - Test with 100+ sequential tool calls
  - Profile memory usage

### Risks & Dependencies

- **=� Medium Risk**: Performance regression from subprocess calls
- **=� Medium Risk**: Cache invalidation issues with delegation
- **Dependencies**: CLI subcommands from Phase 1 must be complete

### Estimated Effort

**3-4 days** (24-32 hours)

- Tool Response Schemas: 0.5 days
- Telemetry & Audit: 1 day
- Resource & Cache: 0.5 days
- Memory Management: 0.5 days
- Integration Testing: 1-1.5 days
- Performance Testing: 0.5 days

### Definition of Done

- [ ] All 10 tools return spec-compliant JSON with all required fields
- [ ] Telemetry events contain correlation_id, duration_ms, tool name
- [ ] Audit logs write to correct paths with secret redaction
- [ ] Discovery cache works with CLI delegation
- [ ] Integration test passes: full OML authoring workflow
- [ ] Selftest verifies all tools and aliases in <2s
- [ ] Performance overhead <50ms per tool call (p95)

---

## Phase 3: Comprehensive Testing & Validation

### Objective

Achieve >95% test coverage for MCP implementation. Validate security model, error handling, and edge cases. Ensure production reliability.

### Deliverables

#### 3.1 Security Validation Tests

- **File**: `tests/security/test_mcp_secret_isolation.py` (NEW - ~250 lines)
  - Attempt to access secrets from MCP process (must fail)
  - Verify subprocess isolation boundary
  - Test with malicious inputs
  - Verify secret redaction in all outputs

#### 3.2 Error Scenario Tests

- **File**: `tests/mcp/test_error_scenarios.py` (NEW - ~300 lines)
  - Test all ERROR_CODES patterns
  - CLI subprocess failures (exit codes 1-255)
  - Timeout scenarios (>30s)
  - Invalid JSON responses
  - Network failures

#### 3.3 Backward Compatibility Tests

- **File**: `tests/mcp/test_backward_compat.py` (NEW - ~200 lines)
  - Test all tool aliases work correctly
  - Verify `osiris.*` prefixed names map to underscore names
  - Test dot-notation aliases (`connections.list`)
  - Ensure no breaking changes for existing configs

#### 3.4 Load & Soak Tests

- **File**: `tests/load/test_mcp_load.py` (NEW - ~150 lines)
  - 1000+ tool calls in sequence
  - Concurrent tool calls (10+ parallel)
  - 60-minute soak test for memory leaks
  - Verify no file descriptor leaks

#### 3.5 Manual Test Scenarios

- **Document**: `docs/testing/mcp-manual-tests.md` (NEW - ~100 lines)
  - Claude Desktop integration checklist
  - Multi-environment testing (Linux, macOS, Windows via WSL)
  - Secret rotation scenarios
  - Network interruption handling

### Test Coverage Requirements

- Line coverage: >95% for all MCP modules
- Branch coverage: >90% for critical paths
- All error codes tested with examples
- All tool aliases verified
- Security boundaries validated

### Risks & Dependencies

- **=� Medium Risk**: Test flakiness from subprocess timing
- **=� Low Risk**: Coverage gaps in error paths
- **Dependencies**: Phases 1-2 must be complete

### Estimated Effort

**2-3 days** (16-24 hours)

- Security Tests: 0.5 days
- Error Scenarios: 0.5 days
- Compatibility Tests: 0.5 days
- Load Tests: 0.5 days
- Manual Testing: 0.5-1 days
- Coverage Analysis: 0.5 days

### Definition of Done

- [ ] Test coverage >95% for `osiris/mcp/` modules
- [ ] All security tests pass (no secret leakage)
- [ ] All error scenarios handled gracefully
- [ ] Backward compatibility verified for all aliases
- [ ] 60-minute soak test passes with stable memory
- [ ] Manual Claude Desktop test successful
- [ ] CI pipeline green with all new tests

---

## Phase 4: Documentation & Release Preparation

### Objective

Complete documentation, ensure smooth migration path, and prepare for v0.5.0 release. Archive legacy chat interface.

### Deliverables

#### 4.1 Documentation Updates

- **File**: `docs/adr/0036-mcp-interface.md` (UPDATE - ~50 lines)

  - Add implementation notes section
  - Document subprocess overhead trade-offs
  - Add security validation results

- **File**: `docs/mcp/overview.md` (UPDATE - ~100 lines)

  - Update all examples with actual CLI commands
  - Add troubleshooting section
  - Include performance characteristics

- **File**: `docs/mcp/tool-reference.md` (VERIFY - existing 597 lines)

  - Verify all schemas match implementation
  - Add delegation details per tool
  - Include example requests/responses

- **File**: `docs/migration/mcp-v0.5-migration.md` (NEW - ~200 lines)
  - Breaking changes from v0.4.x
  - Step-by-step migration guide
  - Tool name changes (dots to underscores)
  - Configuration updates required

#### 4.2 Configuration & Deployment

- **File**: `docs/deployment/mcp-production.md` (NEW - ~150 lines)

  - Production deployment checklist
  - Environment setup guide
  - Secret management best practices
  - Monitoring recommendations

- **File**: `osiris/mcp/clients_config.py` (UPDATE - ~50 lines)
  - Ensure `osiris mcp clients --json` output is production-ready
  - Remove any development paths
  - Add platform-specific handling

#### 4.3 Release Artifacts

- **File**: `CHANGELOG.md` (UPDATE - ~100 lines)

  - v0.5.0 release notes
  - Breaking changes section
  - Migration guide reference
  - Known issues (if any)

- **File**: `pyproject.toml` (UPDATE - 2 lines)

  - Bump version to 0.5.0
  - Update dependencies if needed

- **File**: `requirements.txt` (VERIFY)
  - Ensure `modelcontextprotocol>=1.2.1`
  - Remove any `fastmcp` references
  - Lock all versions

#### 4.4 Legacy Cleanup

- **Files to deprecate/remove**:
  - Mark `osiris/core/websocket_controller.py` as deprecated
  - Add deprecation warnings to chat interface
  - Update all docs to remove chat references

### Test Coverage Requirements

- Documentation examples tested
- Migration guide validated
- Configuration generation verified
- Release checklist executed

### Risks & Dependencies

- **=� Medium Risk**: Documentation drift from implementation
- **=� Low Risk**: Version conflicts
- **Dependencies**: All phases 1-3 complete and tested

### Estimated Effort

**2 days** (16 hours)

- Documentation Updates: 1 day
- Configuration & Deployment: 0.5 days
- Release Preparation: 0.5 days

### Definition of Done

- [ ] All documentation matches implementation exactly
- [ ] Migration guide tested with example project
- [ ] CHANGELOG.md complete with all changes
- [ ] Version bumped to 0.5.0
- [ ] `osiris mcp clients --json` produces working Claude Desktop config
- [ ] Release branch created and CI passing
- [ ] Manual smoke test of release artifacts

---

## Implementation Execution Table

| ID        | File/Module                                      | Description                                   | Test Coverage                     | Effort | Phase |
| --------- | ------------------------------------------------ | --------------------------------------------- | --------------------------------- | ------ | ----- |
| **F1.1**  | `osiris/mcp/cli_bridge.py`                       | Create CLI bridge with `run_cli_json()`       | `test_cli_bridge.py`              | 8h     | 1     |
| **F1.2**  | `osiris/cli/mcp_cmd.py`                          | Add router for 10 subcommands                 | `test_cli_subcommands.py`         | 6h     | 1     |
| **F1.3**  | `osiris/cli/mcp_subcommands/connections_cmds.py` | Implement list, doctor commands               | `test_cli_subcommands.py`         | 4h     | 1     |
| **F1.4**  | `osiris/cli/mcp_subcommands/discovery_cmds.py`   | Implement discovery run command               | `test_cli_subcommands.py`         | 4h     | 1     |
| **F1.5**  | `osiris/cli/mcp_subcommands/oml_cmds.py`         | Implement schema, validate, save              | `test_cli_subcommands.py`         | 4h     | 1     |
| **F1.6**  | `osiris/cli/mcp_subcommands/guide_cmds.py`       | Implement guide start command                 | `test_cli_subcommands.py`         | 2h     | 1     |
| **F1.7**  | `osiris/cli/mcp_subcommands/memory_cmds.py`      | Implement memory capture command              | `test_cli_subcommands.py`         | 2h     | 1     |
| **F1.8**  | `osiris/cli/mcp_subcommands/usecases_cmds.py`    | Implement usecases list command               | `test_cli_subcommands.py`         | 2h     | 1     |
| **F1.9**  | `osiris/cli/mcp_subcommands/components_cmds.py`  | Implement components list command             | `test_cli_subcommands.py`         | 2h     | 1     |
| **F1.10** | `osiris/mcp/tools/connections.py`                | Refactor to use CLI delegation                | `test_tools_connections.py`       | 3h     | 1     |
| **F1.11** | `osiris/mcp/tools/discovery.py`                  | Refactor to use CLI delegation                | `test_tools_discovery.py`         | 4h     | 1     |
| **F1.12** | `osiris/mcp/tools/oml.py`                        | Refactor validate to use CLI                  | `test_tools_oml.py`               | 2h     | 1     |
| **F1.13** | `osiris/mcp/config.py`                           | Implement `MCPFilesystemConfig.from_config()` | `test_filesystem_contract_mcp.py` | 4h     | 1     |
| **F1.14** | `osiris/core/config_generator.py`                | Add MCP keys to init                          | `test_config_generator.py`        | 2h     | 1     |
| **F1.15** | `tests/mcp/test_cli_bridge.py`                   | Test CLI bridge component                     | -                                 | 4h     | 1     |
| **F1.16** | `tests/mcp/test_no_env_scenario.py`              | Test without environment vars                 | -                                 | 3h     | 1     |
| **F1.17** | CI: Add forbidden import check                   | Fail on `resolve_connection` imports          | -                                 | 2h     | 1     |
| **F1.18** | `tests/cli/test_init_writes_mcp_logs_dir.py`    | Test `osiris init` writes MCP config keys     | -                                 | 2h     | 1     |
| **F1.19** | CI: Add config verification guards               | Verify config format and clients output       | -                                 | 2h     | 1     |
| **F1.20** | `osiris/mcp/clients_config.py`                   | Implement `osiris mcp clients` behavior       | `test_mcp_clients_snippet.py`    | 3h     | 1     |
| **F2.1**  | All `osiris/mcp/tools/*.py`                      | Add correlation_id, duration_ms fields        | Existing tool tests               | 4h     | 2     |
| **F2.2**  | `osiris/mcp/telemetry.py`                        | Write to filesystem contract paths            | `test_telemetry.py`               | 4h     | 2     |
| **F2.3**  | `osiris/mcp/audit.py`                            | Structured audit with CLI details             | `test_audit_events.py`            | 6h     | 2     |
| **F2.4**  | `osiris/mcp/cache.py`                            | Fix cache paths for filesystem contract       | `test_cache_ttl.py`               | 4h     | 2     |
| **F2.5**  | `osiris/mcp/tools/memory.py`                     | PII redaction, consent handling               | `test_tools_memory.py`            | 4h     | 2     |
| **F2.6**  | `tests/integration/test_mcp_e2e.py`              | End-to-end integration test                   | -                                 | 8h     | 2     |
| **F2.7**  | `tests/integration/test_mcp_claude_desktop.py`   | Claude Desktop simulation                     | -                                 | 6h     | 2     |
| **F2.8**  | `tests/performance/test_mcp_overhead.py`         | Performance benchmarks                        | -                                 | 4h     | 2     |
| **F3.1**  | `tests/security/test_mcp_secret_isolation.py`    | Security boundary validation                  | -                                 | 4h     | 3     |
| **F3.2**  | `tests/mcp/test_error_scenarios.py`              | All error paths tested                        | -                                 | 4h     | 3     |
| **F3.3**  | `tests/mcp/test_backward_compat.py`              | Alias compatibility tests                     | -                                 | 4h     | 3     |
| **F3.4**  | `tests/load/test_mcp_load.py`                    | Load and soak testing                         | -                                 | 4h     | 3     |
| **F3.5**  | `docs/testing/mcp-manual-tests.md`               | Manual test procedures                        | -                                 | 4h     | 3     |
| **F3.6**  | Coverage analysis and fixes                      | Achieve >95% coverage                         | -                                 | 4h     | 3     |
| **F4.1**  | `docs/adr/0036-mcp-interface.md`                 | Add implementation notes                      | -                                 | 2h     | 4     |
| **F4.2**  | `docs/mcp/overview.md`                           | Update with CLI examples                      | -                                 | 3h     | 4     |
| **F4.3**  | `docs/mcp/tool-reference.md`                     | Verify schemas match code                     | -                                 | 2h     | 4     |
| **F4.4**  | `docs/migration/mcp-v0.5-migration.md`           | Migration guide                               | -                                 | 4h     | 4     |
| **F4.5**  | `docs/deployment/mcp-production.md`              | Production deployment guide                   | -                                 | 3h     | 4     |
| **F4.6**  | `CHANGELOG.md`                                   | v0.5.0 release notes                          | -                                 | 2h     | 4     |
| **F4.7**  | `pyproject.toml`, `requirements.txt`             | Version bump and deps                         | -                                 | 1h     | 4     |
| **F4.8**  | Legacy cleanup and deprecations                  | Remove chat references                        | -                                 | 3h     | 4     |

---

## Critical Path & Milestones

### Week 1 (Days 1-5): Security Foundation

- **Milestone**: CLI bridge operational, no secrets in MCP
- **Verification**: `test_no_env_scenario.py` passes
- **Go/No-Go**: Security audit of Phase 1 implementation

### Week 2 (Days 6-10): Functional Completion

- **Milestone**: All tools working with delegation, full test coverage
- **Verification**: Integration tests pass, selftest <2s
- **Go/No-Go**: Manual Claude Desktop testing successful

### Week 3 (Days 11-15): Polish & Release

- **Milestone**: v0.5.0 ready for release
- **Verification**: All tests pass, docs complete, migration tested
- **Go/No-Go**: Release checklist complete

---

## Success Criteria

### Mandatory (Release Blockers)

-  Zero secret access from MCP process (verified by security tests)
-  All 10 CLI subcommands implemented and working
-  Filesystem contract honored (logs in correct locations)
-  Selftest passes in <2s from any CWD
-  Claude Desktop integration working without env vars
-  Test coverage >95% for MCP modules
-  Migration guide complete and tested

### Recommended (Quality Gates)

-  Subprocess overhead <50ms p95
-  Memory stable over 60-minute soak test
-  All tool aliases working correctly
-  Telemetry and audit logs structured correctly
-  Error taxonomy applied consistently

### Nice-to-Have (Future Improvements)

- Connection pooling for subprocess calls
- Async/parallel tool execution optimization
- Prometheus metrics export
- OpenTelemetry trace integration

---

## Risk Register

| Risk                          | Probability | Impact   | Mitigation                                                    |
| ----------------------------- | ----------- | -------- | ------------------------------------------------------------- |
| Subprocess overhead too high  | Medium      | Medium   | Profile and optimize; consider connection pooling             |
| Breaking changes affect users | High        | Medium   | Clear migration guide, support both old/new names temporarily |
| Security vulnerability found  | Low         | Critical | Security tests, code review, principle of least privilege     |
| Test flakiness from timing    | Medium      | Low      | Proper mocking, avoid time-dependent tests                    |
| Documentation drift           | Medium      | Medium   | Doc tests, examples in CI                                     |

---

## Sign-Off Checklist

Before declaring v0.5.0 ready:

- [ ] **Security**: No secrets accessible from MCP process
- [ ] **Functionality**: All 10 tools working via CLI delegation
- [ ] **Testing**: >95% coverage, all tests green
- [ ] **Performance**: Selftest <2s, overhead <50ms p95
- [ ] **Documentation**: All docs updated, migration guide tested
- [ ] **Integration**: Claude Desktop manual test successful
- [ ] **Release**: Version bumped, CHANGELOG complete
- [ ] **CI/CD**: All pipelines green, release artifacts built

---

## Appendix: File Change Summary

### New Files (22 files, ~4,000 lines)

- `osiris/mcp/cli_bridge.py` - 250 lines
- `osiris/mcp/clients_config.py` - 150 lines
- `osiris/cli/mcp_subcommands/*.py` - 9 files, ~900 lines total
- `tests/mcp/test_cli_bridge.py` - 200 lines
- `tests/mcp/test_cli_subcommands.py` - 300 lines
- `tests/mcp/test_no_env_scenario.py` - 150 lines
- `tests/mcp/test_filesystem_contract_mcp.py` - 100 lines
- `tests/cli/test_init_writes_mcp_logs_dir.py` - 100 lines
- `tests/cli/test_mcp_clients_snippet.py` - 100 lines
- `tests/integration/test_mcp_*.py` - 2 files, 500 lines
- `tests/security/test_mcp_secret_isolation.py` - 250 lines
- `tests/mcp/test_error_scenarios.py` - 300 lines
- `tests/mcp/test_backward_compat.py` - 200 lines
- `tests/load/test_mcp_load.py` - 150 lines
- `tests/performance/test_mcp_overhead.py` - 150 lines
- `docs/migration/mcp-v0.5-migration.md` - 200 lines
- `docs/deployment/mcp-production.md` - 150 lines
- `docs/testing/mcp-manual-tests.md` - 100 lines

### Modified Files (15 files, ~1,200 lines changed)

- `osiris/cli/mcp_cmd.py` - +500 lines
- `osiris/mcp/tools/connections.py` - �50 lines
- `osiris/mcp/tools/discovery.py` - �75 lines
- `osiris/mcp/tools/oml.py` - �30 lines
- `osiris/mcp/config.py` - �100 lines
- `osiris/mcp/telemetry.py` - �50 lines
- `osiris/mcp/audit.py` - �75 lines
- `osiris/mcp/cache.py` - �50 lines
- `osiris/mcp/tools/memory.py` - �100 lines
- `osiris/core/config_generator.py` - +20 lines
- All tool test files - �100 lines total
- Documentation files - �200 lines total

### Total Impact

- **New code**: ~4,000 lines
- **Modified code**: ~1,200 lines
- **Test code**: ~2,200 lines (55% of new code)
- **Documentation**: ~650 lines

---

## Appendix: Verification Commands

### Phase 1 Verification

#### Config-first Paths (Section 1)
```bash
# Verify osiris init writes config keys
osiris init
rg -n "mcp_logs_dir|base_path" osiris.yaml
python osiris.py mcp run --selftest
ls -la "$(yq '.filesystem.base_path' osiris.yaml)/.osiris/mcp/logs"
```

#### CLI Clients Output (Section 2)
```bash
# Verify osiris mcp clients output
python osiris.py mcp clients --json | jq .
# Expect: osiris.py mcp run and cd <base_path>, no env block
```

#### Run-Anywhere Behavior (Section 3)
```bash
# Test from any CWD
(cd /tmp && python /abs/path/osiris/osiris.py mcp run --selftest)
```

#### Test Verification (Section 4)
```bash
# Run new tests
pytest -q tests/cli/test_init_writes_mcp_logs_dir.py
pytest -q tests/cli/test_mcp_clients_snippet.py
pytest -q tests/mcp/test_server_uses_config_paths.py
```

#### Tool Count Verification (Section 6)
```bash
# Verify final tool names and schemas
python osiris.py mcp tools --json | jq '.tools | length'
# Expect: 10
```

### Phase 2 Verification

#### CLI Commands Testing (Section 10)
```bash
# Test each new CLI command
osiris discovery request --help
osiris oml schema --json | jq '.schema.version'
osiris guide start --context /tmp/ctx.json --json
osiris memory capture --session test123 --consent --json
osiris usecases list --json | jq '.[].name'
```

#### CLI Bridge Testing (Section 11)
```bash
# Run bridge tests
pytest tests/mcp/test_cli_bridge.py -v

# Test without environment
unset MYSQL_PASSWORD SUPABASE_SERVICE_ROLE_KEY
pytest tests/mcp/test_no_env_scenario.py -v

# Full MCP test suite with mocked CLI
pytest tests/mcp/ -v
```

### End-to-End Verification

```bash
# Complete production readiness check
python osiris.py mcp run --selftest  # <2s from any CWD
pytest -q tests/mcp  # All green
osiris mcp clients --json  # Valid Claude Desktop config
ls -la "$(yq '.filesystem.base_path' osiris.yaml)/.osiris/mcp/logs"  # Logs in correct location

# Final integration test
unset OSIRIS_HOME OSIRIS_LOGS_DIR  # No env vars needed
python osiris.py mcp run --selftest  # Still works
```

---

_This plan represents the authoritative implementation roadmap for completing Osiris MCP v0.5.0 with CLI-first security architecture. Execution begins with Phase 1 to address the critical security violation._
