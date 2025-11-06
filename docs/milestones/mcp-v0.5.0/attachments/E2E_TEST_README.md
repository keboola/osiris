# MCP v0.5.0 End-to-End Test Suite

**Status**: Ready for use
**Last Updated**: 2025-10-20
**Runtime**: ~3-5 minutes (excludes manual Claude Desktop testing)

## Overview

The `e2e-test.sh` script provides comprehensive automated testing for the MCP v0.5.0 implementation. It covers all critical scenarios including server initialization, tool functionality, security validation, performance measurement, and error handling.

## Quick Start

```bash
# From repository root
cd docs/milestones/mcp-v0.5.0/attachments
./e2e-test.sh

# With verbose output
./e2e-test.sh --verbose

# Skip slow performance tests
./e2e-test.sh --skip-slow
```

## Requirements

### System Dependencies
- **bash 4.0+**: Shell interpreter
- **python 3.9+**: Python runtime
- **jq**: JSON parsing utility (`brew install jq` on macOS)
- **git**: Version control (for branch validation)

### Repository Setup
- Virtual environment at `.venv/` (auto-created if missing)
- `osiris.py` in repository root
- `testing_env/` directory with `osiris.yaml` configuration
- `.env` file in `testing_env/` (optional, but recommended for connection tests)

### Python Dependencies
All dependencies auto-installed from `requirements.txt` during setup phase.

## Test Scenarios

### Scenario A: Server Initialization & Selftest
**Purpose**: Validate MCP server can start and self-test successfully

**Tests**:
- ✅ Selftest completes with exit code 0
- ✅ Runtime <1.3s (target <2s)
- ✅ Returns valid JSON
- ✅ Version is 0.5.0
- ✅ All 10 tools registered
- ✅ Filesystem paths created (`.osiris/mcp/logs/`)

**Command**:
```bash
python osiris.py mcp run --selftest
```

**Expected Output**:
```json
{
  "status": "success",
  "version": "0.5.0",
  "tools": [...],
  "selftest_passed": true
}
```

---

### Scenario B: Connection Management
**Purpose**: Verify connection listing and diagnostics with secret masking

**Tests**:
- ✅ `connections list --json` returns valid JSON
- ✅ Connections array present
- ✅ Secrets masked as `***MASKED***`
- ✅ Reference format `@family.alias` verified
- ✅ No credential leakage in output
- ✅ `connections doctor` provides health status
- ❌ Invalid connection ID produces error

**Commands**:
```bash
osiris mcp connections list --json
osiris mcp connections doctor --connection-id @mysql.default --json
```

**Secret Masking Verified**:
- Passwords masked
- API keys masked
- DSN credentials masked
- Token fields masked

---

### Scenario C: Discovery & Caching
**Purpose**: Test database schema discovery and cache behavior

**Tests**:
- ✅ Discovery completes successfully
- ✅ Returns valid JSON with `discovery_id`
- ✅ Latency reasonable (<2000ms first run)
- ✅ No secrets in discovery output
- ✅ Cache hit on second run (`cache_hit=true`)
- ✅ Resource URIs generated

**Commands**:
```bash
osiris mcp discovery run @mysql.main --samples 10 --json
```

**Cache Behavior**:
- First run: Full discovery, `cache_hit=false`
- Second run: Cache hit, `cache_hit=true`, faster latency
- 24-hour TTL, auto-invalidation after `connections doctor`

---

### Scenario D: OML Authoring
**Purpose**: Validate OML schema and pipeline validation

**Tests**:
- ✅ `oml schema --json` returns valid schema
- ✅ Version is 0.1.0 (dual-layer: `.version` and `.schema.version`)
- ✅ Valid OML passes validation (`valid=true`)
- ❌ Invalid OML fails validation (`valid=false`)
- ✅ Error diagnostics include line/column positions

**Commands**:
```bash
osiris mcp oml schema --json
osiris mcp oml validate --pipeline pipeline.yaml --json
```

**Valid OML Example**:
```yaml
version: "0.1.0"
name: "test_pipeline"
steps:
  - name: "extract_data"
    component: "mysql_extractor"
    config:
      query: "SELECT * FROM users"
```

---

### Scenario E: Memory & AIOP
**Purpose**: Test session memory capture and AIOP artifact access

**Tests**:
- ✅ Memory capture with `--consent` succeeds
- ✅ Returns valid JSON with `resource_uri`
- ❌ Memory capture without `--consent` fails (POL001 error)
- ✅ `aiop list` returns runs array
- ✅ `aiop show` returns valid JSON
- ✅ No credential leakage in AIOP output
- ✅ PII redaction verified (email, DSN, secrets)

**Commands**:
```bash
osiris mcp memory capture --session-id test --text "Note" --consent --json
osiris mcp aiop list --json
osiris mcp aiop show --run <run_id> --json
```

**PII Redaction Patterns**:
- Email addresses redacted
- DSN credentials redacted
- Secrets redacted
- Sensitive field masking

---

### Security Validation
**Purpose**: Prove zero credential leakage from MCP process

**Tests**:
- ✅ No password patterns in outputs
- ✅ No API keys in outputs
- ✅ No DSN credentials in outputs
- ✅ No tokens in outputs
- ✅ CLI subprocess delegation verified
- ✅ MCP logs scanned for credentials
- ✅ Spec-aware secret masking working

**Patterns Scanned**:
```regex
password=[^*]+
key=[a-zA-Z0-9]{20,}
mysql://[^:]+:[^@*]+@
postgresql://[^:]+:[^@*]+@
MYSQL_PASSWORD=[^*]
SUPABASE_.*_KEY=[^*]
```

---

### Performance Measurement
**Purpose**: Validate performance targets are met

**Tests**:
- ✅ Selftest runtime <1300ms (target)
- ✅ Tool call latency <400ms average (cached operations)
- ✅ P95 latency ≤ 2× baseline under concurrent load
- ✅ No memory leaks detected

**Benchmarks**:
- Selftest: <1.3s (actual: ~800ms)
- Discovery (cached): <400ms (actual: ~250ms)
- Discovery (first run): <2s (acceptable)
- Tool call overhead: 10-50ms subprocess overhead

---

### Error Handling Tests
**Purpose**: Verify graceful error handling and messaging

**Tests**:
- ✅ Timeout handling (30s default in CLI bridge)
- ✅ Invalid arguments produce error messages
- ✅ Malformed connection IDs detected
- ✅ Network errors handled gracefully
- ✅ Exit code mapping (CLI → MCP error codes)

**Error Codes Tested**:
- Connection refused
- Timeout (30s)
- Invalid JSON responses
- Malformed CLI output
- Missing credentials
- Permission denied

---

## Output & Reporting

### Console Output
The script provides color-coded, real-time feedback:

```
✅ PASS: Virtual environment activated
❌ FAIL: Selftest exit code is 1 (expected 0)
⚠️  WARN: No masked secrets found (may be expected)
ℹ️  INFO: Running selftest latency measurement...
```

### JSON Report
All test results are written to `/tmp/e2e-results.json`:

```json
{
  "timestamp": "2025-10-20T18:32:45Z",
  "branch": "feature/mcp-server-opus",
  "runtime_seconds": 182,
  "summary": {
    "passed": 45,
    "failed": 0,
    "warned": 3,
    "total": 48
  },
  "status": "success"
}
```

### Test Summary
```
═══════════════════════════════════════════════════════════════════
                        E2E TEST RESULTS
═══════════════════════════════════════════════════════════════════

  ✅ Passed:  45
  ❌ Failed:  0
  ⚠️  Warned:  3

  ⏱️  Runtime: 182s
  📋 Branch:  feature/mcp-server-opus

  ✅ ALL TESTS PASSED

═══════════════════════════════════════════════════════════════════
```

---

## Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | All tests passed | Proceed with deployment |
| 1 | Test failures detected | Review failures, fix issues |
| 2 | Setup failed | Check environment, dependencies |
| 3 | Configuration missing | Verify `osiris.yaml`, `.env` files |

---

## Common Issues & Solutions

### Issue: `jq: command not found`
**Solution**: Install jq
```bash
# macOS
brew install jq

# Ubuntu/Debian
sudo apt-get install jq

# Alpine Linux
apk add jq
```

### Issue: `connections list` returns empty array
**Solution**: Configure connections in `testing_env/osiris_connections.yaml`
```yaml
mysql:
  default:
    host: localhost
    user: root
    database: test
    # Password from env: MYSQL_PASSWORD
```

### Issue: Discovery tests skipped
**Solution**: Add `.env` file in `testing_env/`
```bash
MYSQL_PASSWORD=your-password
SUPABASE_SERVICE_ROLE_KEY=your-key
```

### Issue: Selftest timeout
**Solution**: Check virtual environment and dependencies
```bash
cd /path/to/osiris
source .venv/bin/activate
pip install -r requirements.txt
```

### Issue: Wrong git branch
**Solution**: Switch to feature branch
```bash
git checkout feature/mcp-server-opus
```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: MCP E2E Tests

on:
  push:
    branches: [feature/mcp-server-opus]
  pull_request:
    branches: [main]

jobs:
  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'

      - name: Install jq
        run: sudo apt-get install -y jq

      - name: Run E2E Tests
        run: |
          cd docs/milestones/mcp-v0.5.0/attachments
          ./e2e-test.sh --skip-slow

      - name: Upload Results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: e2e-results
          path: /tmp/e2e-results.json
```

---

## Manual Testing Complement

The E2E script **does not replace** manual Claude Desktop integration testing. After automated tests pass, perform manual testing:

### Manual Test Procedures (from 30-verification.md)

**Scenario 1**: Server starts in Claude Desktop
- Configure `claude_desktop_config.json`
- Restart Claude Desktop
- Verify server appears in MCP menu

**Scenario 2**: Tools callable from chat
- Ask Claude: "List available Osiris tools"
- Expected: All 10 tools listed

**Scenario 3**: Discovery workflow
- Ask Claude: "Discover my MySQL database schema"
- Expected: Schema summary, no secrets leaked

**Scenario 4**: Pipeline authoring
- Ask Claude: "Create a pipeline to extract users table"
- Expected: Valid OML YAML generated

**Scenario 5**: Error handling
- Ask Claude: "Connect to nonexistent database"
- Expected: Graceful error, no crash

---

## Maintenance

### Adding New Tests

1. **Add test function**:
```bash
scenario_f_new_feature() {
    log_section "SCENARIO F: New Feature"

    # Test implementation
    local output
    output=$(python "$OSIRIS_PY" mcp new-tool --json 2>&1)

    if echo "$output" | jq -e . >/dev/null 2>&1; then
        log_pass "new-tool returns valid JSON"
    else
        log_fail "new-tool output is not valid JSON"
    fi
}
```

2. **Add to main()**:
```bash
main() {
    # ... existing scenarios ...
    scenario_f_new_feature || true
    # ...
}
```

3. **Update this README** with new scenario documentation

### Updating Thresholds

Edit script constants:
```bash
# Performance targets
SELFTEST_TARGET_MS=1300
TOOL_CALL_TARGET_MS=400
DISCOVERY_MAX_MS=2000

# Version expectations
EXPECTED_VERSION="0.5.0"
EXPECTED_TOOLS_COUNT=10
```

---

## Debugging

### Enable Verbose Mode
```bash
./e2e-test.sh --verbose
```

Shows:
- Command executions
- Full output from tools
- Detailed JSON parsing
- Intermediate results

### Check Individual Outputs
```bash
# Selftest output
cat /tmp/selftest-output.txt

# Discovery output
cat /tmp/discovery-output.json

# Final results
cat /tmp/e2e-results.json
```

### Run Single Scenario
Edit script and comment out other scenarios in `main()`:
```bash
main() {
    setup_environment
    validate_configuration
    health_checks

    # Only run scenario C
    scenario_c_discovery_caching || true

    generate_report
}
```

---

## Performance Baseline

### Expected Timings (macOS, M1 Pro)

| Operation | Target | Typical | Status |
|-----------|--------|---------|--------|
| Selftest | <1300ms | ~800ms | ✅ Excellent |
| Connections list | <400ms | ~150ms | ✅ Excellent |
| Discovery (cached) | <400ms | ~250ms | ✅ Good |
| Discovery (fresh) | <2000ms | ~1200ms | ✅ Good |
| Memory capture | <500ms | ~180ms | ✅ Excellent |
| OML schema | <200ms | ~120ms | ✅ Excellent |
| Full E2E suite | <300s | ~180s | ✅ Good |

### Slower Systems
On CI runners or slower hardware:
- Allow 2× timing thresholds
- Use `--skip-slow` flag
- Focus on correctness over speed

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-10-20 | Initial release with all 5 scenarios |
| - | - | Security validation included |
| - | - | Performance measurement included |
| - | - | Error handling tests included |

---

## Related Documentation

- **MCP v0.5.0 Initiative**: [`00-initiative.md`](../00-initiative.md)
- **Verification Plan**: [`30-verification.md`](../30-verification.md)
- **Phase 3 Final Audit**: [`PHASE3_FINAL_AUDIT.md`](PHASE3_FINAL_AUDIT.md)
- **ADR-0036**: [MCP CLI-First Security Architecture](../../../adr/0036-mcp-interface.md)

---

## Support

For issues or questions:
1. Check **Common Issues & Solutions** section above
2. Review verbose output: `./e2e-test.sh --verbose`
3. Consult verification plan: `docs/milestones/mcp-v0.5.0/30-verification.md`
4. Review test implementation in `e2e-test.sh` source code

---

**Status**: Production-ready, comprehensive E2E testing suite for MCP v0.5.0 ✅
