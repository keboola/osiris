# MCP v0.5.0 E2E Test Quick Reference

**One-Page Cheat Sheet for Running E2E Tests**

---

## Quick Commands

```bash
# Navigate to script location
cd docs/milestones/mcp-v0.5.0/attachments

# Run full test suite (~3-5 minutes)
./e2e-test.sh

# Run with verbose output
./e2e-test.sh --verbose

# Skip slow performance tests (~2 minutes)
./e2e-test.sh --skip-slow

# View results
cat /tmp/e2e-results.json
```

---

## Prerequisites Checklist

```bash
# ✅ Check Python version (need 3.9+)
python3 --version

# ✅ Check jq installed
jq --version || brew install jq

# ✅ Check virtual environment exists
ls -la /path/to/osiris/.venv

# ✅ Check osiris.yaml configured
cat testing_env/osiris.yaml | grep base_path

# ✅ Check git branch
git branch --show-current  # Should be: feature/mcp-server-opus

# ✅ Optional: Check .env file
cat testing_env/.env | grep MYSQL_PASSWORD
```

---

## Expected Results

### Success Output
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

### Exit Codes
- **0** = All tests passed (proceed)
- **1** = Test failures (review output)
- **2** = Setup failed (check environment)
- **3** = Config missing (check `osiris.yaml`)

---

## Test Coverage Matrix

| Scenario | Tests | Pass Criteria | Runtime |
|----------|-------|---------------|---------|
| **A. Server Init** | 6 | Selftest <1.3s, 10 tools registered | ~2s |
| **B. Connections** | 7 | Secrets masked, no leakage | ~3s |
| **C. Discovery** | 5 | Cache working, no secrets | ~5s |
| **D. OML** | 6 | Valid/invalid detection | ~2s |
| **E. Memory/AIOP** | 8 | PII redacted, consent enforced | ~4s |
| **Security** | 5 | Zero credential leakage | ~3s |
| **Performance** | 3 | Latencies within targets | ~20s |
| **Error Handling** | 4 | Graceful failures | ~2s |
| **Total** | **44** | | **~180s** |

---

## Common Fixes

### ❌ `jq: command not found`
```bash
brew install jq  # macOS
```

### ❌ `osiris.py not found`
```bash
# Ensure you're in repo root subdirectory
cd docs/milestones/mcp-v0.5.0/attachments
ls ../../../../osiris.py  # Should exist
```

### ⚠️ `connections list` returns empty
```bash
# Add connections to testing_env/osiris_connections.yaml
cat > testing_env/osiris_connections.yaml <<EOF
mysql:
  default:
    host: localhost
    user: root
    database: test
EOF

# Add password to testing_env/.env
echo "MYSQL_PASSWORD=your-password" >> testing_env/.env
```

### ⚠️ Discovery tests skipped
```bash
# Check connection credentials in .env
cat testing_env/.env

# Should contain:
MYSQL_PASSWORD=your-password
SUPABASE_SERVICE_ROLE_KEY=your-key
```

### ❌ Selftest timeout
```bash
# Reinstall dependencies
source .venv/bin/activate
pip install -r requirements.txt

# Test manually
cd testing_env
python ../osiris.py mcp run --selftest
```

---

## Key Performance Targets

| Metric | Target | Acceptable | Needs Work |
|--------|--------|------------|------------|
| Selftest | <1.3s | <2s | >2s |
| Connections list | <400ms | <600ms | >600ms |
| Discovery (cached) | <400ms | <800ms | >800ms |
| Discovery (fresh) | <2s | <3s | >3s |
| Tool call avg | <400ms | <600ms | >600ms |

---

## Security Checks Performed

✅ **No credential patterns in outputs**:
- `password=` with actual values
- `key=` with 20+ character values
- DSN credentials: `mysql://user:pass@host`
- Environment variable leaks

✅ **Spec-aware secret masking**:
- All secrets masked as `***MASKED***`
- ComponentRegistry x-secret declarations used
- Consistent masking across tools

✅ **CLI subprocess delegation**:
- MCP process has no env vars
- CLI subcommands inherit environment
- Security boundary verified

---

## Test Scenarios Summary

### 🔧 A. Server Initialization
- Starts in <1.3s
- Registers 10 tools
- Version 0.5.0
- Creates log directories

### 🔌 B. Connection Management
- Lists connections with masking
- Doctor diagnoses issues
- Invalid IDs handled

### 🔍 C. Discovery & Caching
- Discovers schemas
- Caches results (24hr TTL)
- No secrets leaked

### 📝 D. OML Authoring
- Schema v0.1.0 (dual-layer)
- Validates pipelines
- Error diagnostics with line/col

### 💾 E. Memory & AIOP
- Captures with consent
- PII redaction verified
- AIOP reads working

### 🔒 Security Validation
- Zero credential leakage
- All patterns scanned
- Logs verified clean

### ⚡ Performance
- Selftest: <1.3s ✅
- Tool calls: <400ms avg ✅
- No memory leaks ✅

### ⚠️ Error Handling
- Timeouts (30s)
- Invalid inputs
- Network failures

---

## Debugging Commands

```bash
# Show full verbose output
./e2e-test.sh --verbose 2>&1 | tee /tmp/e2e-debug.log

# Check specific test output files
cat /tmp/selftest-output.txt
cat /tmp/discovery-output.json

# View JSON results
cat /tmp/e2e-results.json | jq '.'

# Test individual MCP commands
cd testing_env
python ../osiris.py mcp run --selftest
python ../osiris.py mcp connections list --json
python ../osiris.py mcp discovery run @mysql.default --json
```

---

## CI/CD Integration Snippet

```yaml
# .github/workflows/mcp-e2e.yml
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

## Manual Testing (Post-E2E)

After automated tests pass, perform **manual Claude Desktop testing**:

1. **Configure Claude Desktop**: Add MCP server to config
2. **Restart Claude**: Verify server appears in menu
3. **Test discovery**: "Discover my database schema"
4. **Test authoring**: "Create a pipeline to extract users"
5. **Test errors**: "Connect to nonexistent database"

See: `docs/milestones/mcp-v0.5.0/30-verification.md` (Manual Test Procedures)

---

## Files Created

```
docs/milestones/mcp-v0.5.0/attachments/
├── e2e-test.sh                  # Main test script (executable)
├── E2E_TEST_README.md           # Comprehensive documentation
└── E2E_QUICK_REFERENCE.md       # This quick reference
```

---

## Next Steps After Tests Pass

1. ✅ Review test output for warnings
2. ✅ Check `/tmp/e2e-results.json` for metrics
3. ✅ Perform manual Claude Desktop testing
4. ✅ Review security validation results
5. ✅ Verify performance within targets
6. ✅ Create PR to main branch
7. ✅ Tag v0.5.0 release

---

**Questions?** See full documentation: [`E2E_TEST_README.md`](E2E_TEST_README.md)

**Issues?** Check verbose output: `./e2e-test.sh --verbose`
