# Migration Guide: v0.4.x to v0.5.0

This guide provides step-by-step instructions for migrating from Osiris v0.4.x to v0.5.0, which introduces the CLI-first MCP architecture (ADR-0036) with significant security and configuration improvements.

## Executive Summary

**What Changed**:
- MCP server adopts CLI-first security architecture (zero secret access in MCP process)
- Tool names use underscore format with backward-compatible aliases
- Configuration requires explicit `filesystem.base_path` setting
- New `osiris mcp` CLI namespace for all MCP-delegated operations
- Tool response schemas include performance metrics

**Migration Time**: 15-30 minutes for typical deployments

**Breaking Changes**: Configuration structure (mandatory base_path), tool response schema (new metadata fields)

---

## 1. Breaking Changes from v0.4.x

### 1.1 Tool Name Changes

**Primary Names** (underscore format):
- `connections_list` (was: `osiris.connections.list`)
- `connections_doctor` (was: `osiris.connections.doctor`)
- `discovery_request` (was: `osiris.introspect_sources`)
- `oml_schema_get` (was: `osiris.oml.schema.get`)
- `oml_validate` (was: `osiris.validate_oml`)
- `oml_save` (was: `osiris.save_oml`)
- `guide_start` (was: `osiris.guide_start`)
- `memory_capture` (was: `osiris.memory.capture`)
- `components_list` (was: `osiris.components.list`)
- `usecases_list` (was: `osiris.usecases.list`)
- `aiop_list` (new in v0.5.0)
- `aiop_show` (new in v0.5.0)

**Backward Compatibility**: All legacy names continue to work as aliases. No client code changes required immediately, but underscore format is recommended.

```python
# Both work in v0.5.0:
await session.call_tool("connections_list", {})           # ✅ Preferred
await session.call_tool("osiris.connections.list", {})    # ✅ Still works (alias)
```

### 1.2 Tool Response Schema Changes

**v0.4.x Response**:
```json
{
  "status": "success",
  "result": { ... }
}
```

**v0.5.0 Response** (includes performance metrics):
```json
{
  "status": "success",
  "result": { ... },
  "_meta": {
    "correlation_id": "mcp_20251020_143022_abc123",
    "duration_ms": 145,
    "bytes_in": 256,
    "bytes_out": 4821
  }
}
```

**Migration Impact**: If your client parses responses, ignore the `_meta` field or use it for observability. The `status` and `result` fields remain unchanged.

### 1.3 Memory Tool Consent Requirement

**v0.4.x**: Consent was optional for memory capture.

**v0.5.0**: Explicit `consent: true` required to capture session memory.

```python
# v0.4.x (no longer works)
await session.call_tool("memory_capture", {
    "session_id": "chat_20251020_143022"
})

# v0.5.0 (required)
await session.call_tool("memory_capture", {
    "session_id": "chat_20251020_143022",
    "consent": True  # ← Required
})
```

### 1.4 Configuration Structure Changes

**Critical**: `filesystem.base_path` is now mandatory for MCP server deployments.

---

## 2. Configuration Updates Required

### 2.1 Mandatory Base Path Setting

**Before (v0.4.x)**: `osiris.yaml` used relative paths, defaulted to repo root.

**After (v0.5.0)**: Must explicitly set `filesystem.base_path` to an absolute path.

#### Example: osiris.yaml Before

```yaml
# v0.4.x configuration
version: '2.0'

filesystem:
  pipelines_dir: "pipelines"
  build_dir: "build"
  aiop_dir: "aiop"
```

#### Example: osiris.yaml After

```yaml
# v0.5.0 configuration
version: '2.0'

filesystem:
  # ⚠️ REQUIRED: Absolute path to project root
  base_path: "/Users/you/projects/osiris-instance"

  # Optional: Custom MCP logs directory (relative to base_path)
  mcp_logs_dir: ".osiris/mcp/logs"  # Default if omitted

  pipelines_dir: "pipelines"
  build_dir: "build"
  aiop_dir: "aiop"

  profiles:
    enabled: true
    values: ["dev", "staging", "prod"]
    default: "dev"
```

### 2.2 Auto-Configuration via `osiris init`

**Recommended**: Let `osiris init` auto-configure `base_path` for you.

```bash
# Navigate to your project directory
cd /path/to/your/osiris-instance

# Run init (automatically sets base_path to current directory)
osiris init

# Verify base_path was set correctly
grep base_path osiris.yaml
# Output: base_path: "/path/to/your/osiris-instance"
```

### 2.3 MCP Server Log Paths

**v0.4.x**: Logs written to hardcoded `~/.osiris_audit/`

**v0.5.0**: Logs written to config-driven paths:
- Logs: `<base_path>/.osiris/mcp/logs/`
- Audit: `<base_path>/.osiris/mcp/logs/audit/`
- Cache: `<base_path>/.osiris/mcp/logs/cache/`
- Telemetry: `<base_path>/.osiris/mcp/logs/telemetry/`

**No migration action needed** — old logs in `~/.osiris_audit/` can be deleted after verifying new logs appear in the correct location.

### 2.4 Environment Variables (Optional)

**v0.5.0** introduces new MCP-specific environment variables:

```bash
# Override base_path from environment (useful for CI/CD)
export OSIRIS_HOME="/srv/osiris/production"

# Override MCP logs directory
export OSIRIS_MCP_LOGS_DIR="/var/log/osiris/mcp"

# MCP server configuration
export OSIRIS_MCP_PAYLOAD_LIMIT_MB=16       # Default: 16
export OSIRIS_MCP_CACHE_TTL_HOURS=24        # Default: 24
export OSIRIS_MCP_TELEMETRY_ENABLED=true    # Default: true
```

**Precedence**: Environment variables > `osiris.yaml` > defaults

---

## 3. CLI Command Changes

### 3.1 New `osiris mcp` Namespace

**v0.5.0** introduces a unified `osiris mcp` namespace for all MCP-delegated operations.

```bash
# New MCP command structure
osiris mcp <tool> <action> [options]

# Examples:
osiris mcp connections list --json
osiris mcp discovery run --connection-id @mysql.default --json
osiris mcp oml validate --file pipeline.yaml --json
osiris mcp memory capture --session-id chat_123 --consent --json
osiris mcp aiop list --json
```

### 3.2 Command Mapping

| v0.4.x Command | v0.5.0 Equivalent | Notes |
|----------------|-------------------|-------|
| `osiris connections list` | `osiris mcp connections list` | CLI parity maintained |
| `osiris connections doctor` | `osiris mcp connections doctor` | Now available via MCP |
| N/A | `osiris mcp discovery run` | New CLI command for MCP |
| `osiris compile --validate` | `osiris mcp oml validate` | MCP-specific validator |
| N/A | `osiris mcp memory capture` | New CLI command for MCP |
| N/A | `osiris mcp aiop list` | New AIOP read-only access |

**Note**: Original CLI commands (`osiris connections list`, `osiris compile`, etc.) remain unchanged. The `osiris mcp` namespace provides MCP-specific JSON output for tool delegation.

### 3.3 MCP Server Commands

```bash
# Start MCP server (stdio transport)
osiris mcp run

# Self-test (validates server health in <2s)
osiris mcp run --selftest

# Debug mode (verbose logging to stderr)
osiris mcp run --debug

# Generate Claude Desktop config snippet
osiris mcp clients --json

# List all registered tools
osiris mcp tools
```

---

## 4. Step-by-Step Migration

### Step 1: Backup Current Configuration

```bash
# Backup your existing configuration
cp osiris.yaml osiris.yaml.v0.4.backup
cp osiris_connections.yaml osiris_connections.yaml.backup  # If using
```

### Step 2: Update Osiris to v0.5.0

```bash
# Pull latest changes
git pull origin main

# Activate virtual environment
source .venv/bin/activate

# Update dependencies
pip install -r requirements.txt --upgrade

# Verify version
python osiris.py --version
# Expected: v0.5.0 or higher
```

### Step 3: Update Configuration

**Option A: Auto-Configure** (Recommended)

```bash
# Navigate to your project directory
cd /path/to/your/osiris-instance

# Re-run init to update configuration
osiris init

# Verify base_path is absolute
grep base_path osiris.yaml
```

**Option B: Manual Configuration**

Edit `osiris.yaml` and add `filesystem.base_path`:

```yaml
filesystem:
  base_path: "/absolute/path/to/project"  # ← Add this line
  # ... rest of configuration
```

### Step 4: Verify MCP Server Health

```bash
# Run self-test (<2s expected)
osiris mcp run --selftest

# Expected output:
# ✅ Server initialized successfully
# ✅ Selftest completed in 1.23s
# ✅ All 12 tools registered
# ✅ Zero credential leakage verified
```

### Step 5: Test Tool Calls

```bash
# Test connections listing
osiris mcp connections list --json

# Test discovery
osiris mcp discovery run --connection-id @mysql.default --samples 5 --json

# Test AIOP access (new feature)
osiris mcp aiop list --json
```

### Step 6: Update Client Code (If Applicable)

If you have custom MCP clients, update tool names to use underscore format:

```python
# Before (v0.4.x)
result = await session.call_tool("osiris.connections.list", {})

# After (v0.5.0) — preferred
result = await session.call_tool("connections_list", {})

# Or keep using aliases (backward compatible)
result = await session.call_tool("osiris.connections.list", {})  # Still works
```

### Step 7: Verify Logs Appear in New Location

```bash
# Check MCP logs directory exists
ls -la <base_path>/.osiris/mcp/logs/

# Should see:
# audit/        — Audit trail logs
# cache/        — Discovery cache
# telemetry/    — Performance metrics

# Run a few MCP commands
osiris mcp connections list --json
osiris mcp oml schema --json

# Verify telemetry logs were created
ls -la <base_path>/.osiris/mcp/logs/telemetry/
```

### Step 8: Update Claude Desktop Configuration (Optional)

If using Claude Desktop, update your MCP server configuration:

```json
{
  "mcpServers": {
    "osiris": {
      "command": "python",
      "args": ["-m", "osiris.cli.mcp_entrypoint"],
      "env": {
        "OSIRIS_HOME": "/absolute/path/to/osiris-instance"
      }
    }
  }
}
```

**Location**:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Linux: `~/.config/claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

### Step 9: Clean Up Old Logs (Optional)

```bash
# After verifying new logs are working, remove old audit logs
rm -rf ~/.osiris_audit/  # v0.4.x location

# Confirm new logs are accumulating
du -sh <base_path>/.osiris/mcp/logs/
```

---

## 5. Testing Checklist

### Core Functionality

- [ ] `osiris mcp run --selftest` completes in <2s
- [ ] `osiris mcp connections list --json` returns connections
- [ ] `osiris mcp discovery run` completes without errors
- [ ] `osiris mcp oml validate --file pipeline.yaml` validates pipelines
- [ ] `osiris mcp memory capture --session-id <id> --consent` captures memory
- [ ] Logs appear in `<base_path>/.osiris/mcp/logs/` (not `~/.osiris_audit/`)

### Security Validation

- [ ] MCP server starts without requiring environment variables
- [ ] Tool responses contain no plaintext secrets (passwords, API keys)
- [ ] Connection configs show `***MASKED***` for secret fields
- [ ] Audit logs redact DSN credentials (`mysql://***@host/db`)

### Performance

- [ ] Selftest completes in <2s (requirement)
- [ ] Tool calls respond in <500ms for cached operations
- [ ] No memory leaks observed during extended usage
- [ ] Concurrent tool calls do not cause crashes

### Backward Compatibility

- [ ] Legacy tool names (`osiris.connections.list`) still work
- [ ] Existing `osiris_connections.yaml` file still loads correctly
- [ ] Environment variable precedence unchanged
- [ ] CLI commands (`osiris compile`, `osiris run`) unaffected

---

## 6. Troubleshooting

### Issue: MCP Server Fails to Start

**Symptom**: `osiris mcp run` exits with configuration error.

**Solution**:
```bash
# Check if base_path is set
grep base_path osiris.yaml

# If missing, run init to auto-configure
osiris init

# Verify base_path is absolute (not relative)
python -c "from pathlib import Path; print(Path('$(grep base_path osiris.yaml | cut -d: -f2)').resolve())"
```

### Issue: Logs Not Appearing in Expected Location

**Symptom**: Running MCP commands but logs are empty.

**Solution**:
```bash
# Check MCP logs directory exists
ls -la <base_path>/.osiris/mcp/logs/

# Check configuration precedence
osiris mcp run --debug 2>&1 | grep "base_path:"
# Should show resolved base_path

# Verify telemetry is enabled
echo $OSIRIS_MCP_TELEMETRY_ENABLED  # Should be empty or "true"

# Run command with verbose logging
OSIRIS_MCP_TELEMETRY_ENABLED=true osiris mcp connections list --json
```

### Issue: Tool Names Not Recognized

**Symptom**: `call_tool("connections_list")` returns "Tool not found".

**Solution**:
```bash
# List all available tools
osiris mcp tools

# Check aliases are registered
osiris mcp tools | grep connections

# Verify MCP server version
osiris --version  # Should be v0.5.0+
```

### Issue: Memory Capture Fails with Consent Error

**Symptom**: `Error: Memory capture requires explicit --consent flag`

**Solution**:
```python
# v0.5.0 requires explicit consent
await session.call_tool("memory_capture", {
    "session_id": "chat_20251020_143022",
    "consent": True  # ← Required in v0.5.0
})
```

```bash
# CLI usage
osiris mcp memory capture --session-id chat_123 --consent --json
```

### Issue: Secrets Visible in Logs

**Symptom**: Plaintext passwords appearing in audit logs or tool responses.

**Solution**:
```bash
# Verify spec-aware masking is working
osiris mcp connections list --json | jq '.result.connections[].config'
# Should show "***MASKED***" for password/key fields

# Check component specs declare secrets
cat osiris/components/<family>/spec.yaml | grep x-secret
# Should see: x-secret: [/password, /key, ...]

# Report security issue if masking is broken
# This is a critical bug — do not use in production
```

### Issue: Self-Test Fails

**Symptom**: `osiris mcp run --selftest` exits with errors.

**Solution**:
```bash
# Run with debug logging
osiris mcp run --selftest --debug 2>&1 | tee selftest.log

# Common issues:
# 1. Missing base_path → run `osiris init`
# 2. Permission errors → check directory permissions
# 3. Import errors → reinstall dependencies: pip install -r requirements.txt

# Verify all tests pass
make test  # Should show 1577+ tests passing
```

---

## 7. Rollback Procedure

If migration fails, rollback to v0.4.x:

```bash
# Restore configuration backups
cp osiris.yaml.v0.4.backup osiris.yaml
cp osiris_connections.yaml.backup osiris_connections.yaml

# Checkout v0.4.x branch/tag
git checkout v0.4.1  # Or your previous stable version

# Reinstall dependencies
pip install -r requirements.txt

# Verify rollback
python osiris.py --version  # Should show v0.4.x
```

---

## 8. Migration Verification

### Final Verification Script

```bash
#!/bin/bash
# verify-migration.sh

echo "=== Osiris v0.5.0 Migration Verification ==="

# 1. Version check
VERSION=$(python osiris.py --version 2>/dev/null | grep -o 'v[0-9.]*')
echo "✓ Version: $VERSION"
[[ "$VERSION" == "v0.5.0" ]] || echo "⚠️  Expected v0.5.0"

# 2. Base path configured
BASE_PATH=$(grep 'base_path:' osiris.yaml | awk '{print $2}' | tr -d '"')
echo "✓ Base path: $BASE_PATH"
[[ -d "$BASE_PATH" ]] || echo "⚠️  Base path does not exist"

# 3. Self-test passes
echo "Running self-test..."
SELFTEST=$(osiris mcp run --selftest 2>&1)
echo "$SELFTEST" | grep -q "✅" && echo "✓ Self-test passed" || echo "❌ Self-test failed"

# 4. Logs directory exists
LOGS_DIR="$BASE_PATH/.osiris/mcp/logs"
[[ -d "$LOGS_DIR" ]] && echo "✓ Logs directory: $LOGS_DIR" || echo "❌ Logs directory missing"

# 5. Tool call works
TOOLS=$(osiris mcp connections list --json 2>/dev/null)
echo "$TOOLS" | jq -e '.status == "success"' >/dev/null && echo "✓ Tool call successful" || echo "❌ Tool call failed"

# 6. No secrets in output
echo "$TOOLS" | grep -q 'password.*:.*[^*]' && echo "❌ Secrets visible!" || echo "✓ Secrets masked"

echo ""
echo "=== Migration verification complete ==="
```

Run it:
```bash
chmod +x verify-migration.sh
./verify-migration.sh
```

Expected output:
```
=== Osiris v0.5.0 Migration Verification ===
✓ Version: v0.5.0
✓ Base path: /Users/you/projects/osiris-instance
Running self-test...
✓ Self-test passed
✓ Logs directory: /Users/you/projects/osiris-instance/.osiris/mcp/logs
✓ Tool call successful
✓ Secrets masked

=== Migration verification complete ===
```

---

## 9. Post-Migration Best Practices

### Recommended After Migration

1. **Update Documentation**: Update any internal documentation referencing tool names to use underscore format.

2. **Monitor Logs**: Watch MCP logs for the first few days to catch any unexpected behavior:
   ```bash
   tail -f <base_path>/.osiris/mcp/logs/telemetry/$(date +%Y%m%d).jsonl
   ```

3. **Performance Baseline**: Establish performance baselines for your workload:
   ```bash
   # Run 100 tool calls and measure P95 latency
   for i in {1..100}; do
     osiris mcp connections list --json 2>&1 | grep duration_ms
   done | sort -n | tail -5
   ```

4. **Security Audit**: Verify no secrets leak in production:
   ```bash
   # Audit all tool responses
   grep -r "password\|secret\|key" <base_path>/.osiris/mcp/logs/audit/ | grep -v "***MASKED***"
   # Should return empty (no matches)
   ```

5. **Cleanup Legacy Artifacts**: Remove old audit logs after 30 days:
   ```bash
   # Archive old logs
   tar -czf osiris-v0.4-logs-$(date +%Y%m%d).tar.gz ~/.osiris_audit/

   # Remove after verification
   rm -rf ~/.osiris_audit/
   ```

---

## 10. Support and Resources

### Documentation
- [ADR-0036: MCP CLI-First Security Architecture](../adr/0036-mcp-interface.md)
- [MCP v0.5.0 Initiative Overview](../milestones/mcp-v0.5.0/00-initiative.md)
- [Chat to MCP Migration Guide](./chat-to-mcp.md)
- [MCP Manual Test Procedures](../testing/mcp-manual-tests.md)

### Key Changes by Phase
- **Phase 1**: CLI-first security architecture (zero secret access)
- **Phase 2**: Functional parity (metrics, AIOP access, telemetry)
- **Phase 3**: Comprehensive testing (490 tests, 78.4% coverage)
- **Phase 4**: Documentation and release preparation

### Getting Help

**Common Issues**: Check [Troubleshooting](#6-troubleshooting) section above.

**Bug Reports**: File issues on GitHub with:
- Output of `osiris --version`
- Relevant section of `osiris.yaml`
- Error messages from `osiris mcp run --debug`
- Output of migration verification script

**Security Issues**: Report privately via security policy (SECURITY.md).

---

## Summary

The v0.4.x → v0.5.0 migration brings significant security and architectural improvements via the CLI-first MCP design. While configuration changes are required (`filesystem.base_path`), the migration process is straightforward and backward-compatible for most use cases.

**Key Takeaways**:
- ✅ Set `filesystem.base_path` to an absolute path (use `osiris init`)
- ✅ Tool names use underscores (aliases maintain backward compatibility)
- ✅ Memory capture requires explicit consent (`consent: true`)
- ✅ Logs move to config-driven paths (`<base_path>/.osiris/mcp/logs/`)
- ✅ Self-test verifies migration success (`osiris mcp run --selftest`)

**Estimated Migration Time**: 15-30 minutes for typical deployments.

If you encounter issues not covered in this guide, consult the documentation links above or file a GitHub issue.
