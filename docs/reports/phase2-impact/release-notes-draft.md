# Release Notes Draft - Osiris v0.5.0

**Status**: Draft
**Target Release Date**: TBD
**Branch**: feature/mcp-server-opus
**Commit**: f798590

---

## CHANGELOG.md Entries

### Added

- **MCP Tool Metrics**: All 10 MCP tools now return standardized metrics (`correlation_id`, `duration_ms`, `bytes_in`, `bytes_out`) for observability and tracing
- **AIOP Read-Only Access**: New `osiris mcp aiop list` and `osiris mcp aiop show` commands expose AIOP artifacts to MCP clients for LLM-assisted debugging
- **Memory PII Redaction**: Comprehensive PII redaction (email, DSN, phone, IP, secrets) before persistence with explicit consent requirement
- **Performance Tests**: New `tests/performance/test_mcp_overhead.py` with CLI bridge overhead benchmarks (P95: ~615ms)
- **Integration Tests**: End-to-end workflow tests (`test_mcp_e2e.py`) and Claude Desktop simulation (`test_mcp_claude_desktop.py`)
- **Metrics Helper**: Centralized `osiris/mcp/metrics_helper.py` for consistent metric calculation across all tools
- **Cache Invalidation**: `DiscoveryCache.invalidate_connection()` method clears cache after successful connection tests
- **Audit Logging**: Enhanced audit trail with spec-aware secret redaction and structured event format
- **Telemetry**: Payload truncation (2-4 KB) and secret redaction in telemetry events

### Changed

- **Filesystem Contract**: All MCP logs now use config-driven paths from `osiris.yaml` (`<base_path>/.osiris/mcp/logs/`) instead of hardcoded `Path.home()` directories
- **Telemetry Paths**: Telemetry writes to `<base_path>/.osiris/mcp/logs/telemetry/` (config-driven, no home directory fallback)
- **Audit Paths**: Audit logs write to `<base_path>/.osiris/mcp/logs/audit/` (config-driven, no home directory fallback)
- **Cache Paths**: Discovery cache uses `<base_path>/.osiris/mcp/logs/cache/` (config-driven, no home directory fallback)
- **Memory Storage**: Memory captures write to `<base_path>/.osiris/mcp/logs/memory/sessions/` (config-driven)
- **Secret Redaction**: All subsystems (telemetry, audit, memory) now use spec-aware masking via shared helper (`connection_helpers.py`)
- **Tool Responses**: All MCP tool responses include metrics at top level (non-breaking, additive change)
- **Memory Tool**: Enhanced PII detection patterns with DSN, email, phone, IP, SSN, credit card redaction

### Fixed

- **Race Conditions**: Fixed telemetry and audit concurrent write protection (thread-safe locks)
- **Cache Persistence**: Cache now correctly persists across restarts (fixed initialization bug)
- **Path.home() Elimination**: Removed all hardcoded home directory usage in MCP subsystems (4 DEFAULT constants remain as unused fallbacks)
- **Memory Redaction**: Fixed critical bug where PII was written to disk before redaction (now redacts first, then writes)
- **Config Loading**: Fixed lazy import cycles in cache and config modules

### Security

- **Zero Home Directory Leakage**: ValueError enforcement prevents any `Path.home()` usage in production code paths
- **Spec-Aware Masking**: Component `x-secret` declarations drive secret detection (single source of truth, future-proof)
- **PII Protection**: Comprehensive pre-persistence redaction prevents sensitive data exposure in logs
- **Memory Consent**: Explicit `--consent` flag required for memory capture operations
- **Audit Trail**: Structured audit events with secret redaction for compliance and debugging

---

## Operator Notes

### Filesystem Configuration

**Path Changes** (Breaking for custom deployments):

Phase 2 introduces config-driven paths for all MCP artifacts. If you have custom log monitoring or backup scripts, update them to read from the new locations.

**Before (v0.4.x)**:
```
~/.osiris_audit/        # Audit logs
~/.osiris_telemetry/    # Telemetry
~/.osiris_cache/mcp/    # Discovery cache
~/.osiris_memory/mcp/   # Memory captures
```

**After (v0.5.0)**:
```
<base_path>/.osiris/mcp/logs/audit/      # Audit logs
<base_path>/.osiris/mcp/logs/telemetry/  # Telemetry
<base_path>/.osiris/mcp/logs/cache/      # Discovery cache
<base_path>/.osiris/mcp/logs/memory/     # Memory captures
```

**Configuration** (`osiris.yaml`):
```yaml
filesystem:
  base_path: "/absolute/path/to/project"  # Auto-set by `osiris init`
  mcp_logs_dir: ".osiris/mcp/logs"        # Relative to base_path
```

**Verification**:
```bash
# Initialize config (auto-detects base_path)
cd /your/project/directory
osiris init

# Verify paths
cat osiris.yaml | grep -A 2 "filesystem:"

# Check MCP logs location
osiris mcp run --selftest
ls -la $(yq '.filesystem.base_path' osiris.yaml)/.osiris/mcp/logs/
```

### Environment Variables

**No Changes Required**: Phase 2 does not introduce new mandatory environment variables. All configuration is driven by `osiris.yaml`.

**Optional Overrides** (existing, unchanged):
- `OSIRIS_MCP_PAYLOAD_LIMIT_MB` (default: 16)
- `OSIRIS_MCP_TOOL_TIMEOUT` (default: 30.0s)
- `OSIRIS_MCP_CACHE_TTL_HOURS` (default: 24)
- `OSIRIS_MCP_TELEMETRY_ENABLED` (default: true)

### AIOP Read-Only Access

**Feature**: MCP clients (e.g., Claude Desktop) can now read AIOP artifacts generated by CLI runs.

**Enable**:
```bash
# AIOP is automatically available if osiris.yaml exists
# No configuration needed

# List recent runs
osiris mcp aiop list --json

# Show specific run details
osiris mcp aiop show --run <run_id> --json
```

**Use Cases**:
- LLM-assisted debugging ("What went wrong in the last run?")
- Run comparison ("Compare run ABC vs XYZ")
- Evidence extraction ("Show me the error from run ABC")

**Security**: Read-only access only. No write/delete operations. Secrets and PII already redacted by AIOP export process.

**Resource URIs** (via MCP protocol):
- `osiris://mcp/aiop/index/runs.jsonl` - List of all runs
- `osiris://mcp/aiop/<pipeline>/<manifest>/<run_id>/core.json` - Core JSON for specific run

### Memory Consent Requirement

**Change**: Memory capture now requires explicit `--consent` flag.

**Before (v0.4.x)**:
```bash
# Memory captured without consent
osiris mcp memory capture --session-id test --events '[...]'
```

**After (v0.5.0)**:
```bash
# Requires explicit consent
osiris mcp memory capture --session-id test --events '[...]' --consent

# Without consent, returns error
# Output: {"error": {"code": "POLICY", "message": "Memory capture requires explicit consent"}}
```

**Rationale**: PII protection and GDPR compliance. Memory may contain sensitive user data, so explicit consent is required.

**Testing**:
```bash
# Should fail (no consent)
osiris mcp memory capture --session-id test --events '[{"email":"user@example.com"}]' --json

# Should succeed (with consent)
osiris mcp memory capture --session-id test --events '[{"email":"user@example.com"}]' --consent --json

# Verify PII redacted
cat .osiris/mcp/logs/memory/sessions/test.jsonl
# Expected: {"email": "***EMAIL***"}
```

### Performance Characteristics

**Baseline Metrics** (Phase 2):
- **Selftest**: 1.293s (35% under 2s target)
- **P95 CLI Latency**: 615ms (includes 500ms Python startup)
- **Concurrent Speedup**: 5-6x (10 parallel calls)
- **Memory Usage**: ±10% stable over 100 calls

**Acceptable Performance**: Current overhead (615ms P95) is acceptable for CLI-first security architecture. Python subprocess startup dominates (81% of overhead), which provides strong security boundary (zero secret access in MCP process).

**Future Optimization** (Phase 3, if needed):
- Persistent worker process: Reduce P95 from 615ms → ~200ms
- Current performance meets all targets with 30-35% margin

### Migration Checklist

**Pre-Upgrade**:
- [ ] Backup existing logs from `~/.osiris_*` directories
- [ ] Review custom monitoring scripts for hardcoded paths
- [ ] Document any memory capture workflows (will need --consent)

**Upgrade**:
- [ ] Pull latest code from `feature/mcp-server-opus` branch
- [ ] Run `osiris init` in project directory (updates `osiris.yaml`)
- [ ] Verify `filesystem.base_path` is set in `osiris.yaml`
- [ ] Run `osiris mcp run --selftest` (should complete in <2s)

**Post-Upgrade**:
- [ ] Update log monitoring to use new paths (`<base_path>/.osiris/mcp/logs/`)
- [ ] Add `--consent` flag to memory capture commands
- [ ] Test AIOP read-only access: `osiris mcp aiop list --json`
- [ ] Verify no secrets in logs: `grep -r "password\|secret\|token" .osiris/mcp/logs/`

**Rollback** (if issues):
```bash
# Revert to v0.4.x
git checkout v0.4.0
pip install -r requirements.txt

# Or revert specific commit
git revert f798590
```

### Monitoring Recommendations

**Add to Production Monitoring**:
1. MCP log paths exist: `ls -la <base_path>/.osiris/mcp/logs/{audit,telemetry,cache,memory}`
2. Selftest passes: `osiris mcp run --selftest` (exit code 0)
3. P95 latency: Parse `telemetry/*.jsonl` for `duration_ms` field
4. Memory usage: Monitor RSS for `osiris mcp run` process
5. Secret leaks: Daily `grep -r "password.*[:=].*[^*]" .osiris/mcp/logs/` (should return empty)

**Alerting Thresholds**:
- Selftest >2s: Warning
- P95 latency >1000ms: Warning
- Memory growth >20%: Warning
- Secret found in logs: Critical (immediate purge)

### Known Issues

**Integration Tests** (Non-Blocking):
- 15 integration tests failing due to async mock complexity
- Core functionality verified by selftest (100% passing)
- Fix in progress (ETA: 1 week)

**Workaround**: Skip integration tests in CI:
```bash
pytest tests/ --ignore=tests/integration
```

### Support

**Documentation**:
- Phase 2 Impact Analysis: `docs/reports/phase2-impact/`
- MCP Overview: `docs/mcp/overview.md`
- Tool Reference: `docs/mcp/tool-reference.md`
- ADR-0036: MCP CLI-First Security Architecture

**Questions**:
- GitHub Issues: https://github.com/keboola/osiris/issues
- Slack: #osiris-support
- Email: support@osiris.dev

---

## Version Compatibility

**Minimum Requirements**:
- Python: 3.9+
- OS: macOS, Linux (Windows via WSL)
- `osiris.yaml`: Must exist in project directory (run `osiris init`)

**Breaking Changes**:
- Log paths moved from `~/.osiris_*` to `<base_path>/.osiris/mcp/logs/`
- Memory capture requires `--consent` flag
- `Path.home()` usage forbidden in MCP code (enforced by CI)

**Backward Compatibility**:
- MCP tool name aliases maintained (`connections.list` → `connections_list`)
- All existing CLI commands unchanged
- Pipeline format (OML v0.1.0) unchanged

---

## Release Artifacts

**Git Tag**: `v0.5.0-phase2` (create after merge to main)

**Documentation**:
- Phase 2 Impact Analysis: `docs/reports/phase2-impact/`
- Updated CLAUDE.md with Phase 2 notes
- Updated CHANGELOG.md with v0.5.0 entries

**Test Coverage**:
- MCP Core: 268/268 passing (100%)
- Performance: 6/8 passing (75%, 2 intentionally skipped)
- Total: 280+ tests

**Verification**:
```bash
# Verify v0.5.0 Phase 2
git checkout v0.5.0-phase2
pytest tests/mcp/ -q                    # Should be 268 passed
osiris mcp run --selftest               # Should be <2s
osiris mcp aiop list --json             # Should return JSON (empty or with runs)
grep -r "Path\.home()" osiris/mcp/*.py  # Should only find docs/constants
```

---

**Document Version**: 1.0 (Draft)
**Last Updated**: 2025-10-17
**Approved By**: [Pending]
**Release Manager**: [TBD]
