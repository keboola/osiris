# Osiris MCP Server: Production Deployment Guide

**Version**: MCP v0.5.0
**Last Updated**: 2025-10-20
**Target Audience**: DevOps Engineers, Production Engineers, System Administrators

---

## Overview

This guide covers production deployment of the Osiris MCP (Model Context Protocol) server with Claude Desktop integration. It includes security best practices, monitoring setup, and troubleshooting procedures for production environments.

**Key Features**:
- **CLI-First Security**: MCP process never accesses secrets directly (ADR-0036)
- **Config-Driven Paths**: All artifacts isolated to configured base directory
- **Spec-Aware Secret Masking**: Automatic redaction based on component specifications
- **Performance**: <1.3s selftest, P95 latency ≤ 2× baseline under concurrent load
- **Zero Credential Leakage**: Verified across 10 security tests

---

## 1. Production Checklist

### Pre-Deployment Verification

Run these commands to verify production readiness:

```bash
# 1. Verify Python environment
python --version
# Expected: Python 3.11+ (3.11, 3.12, 3.13 supported)

# 2. Activate virtual environment
source .venv/bin/activate

# 3. Run selftest (<2s expected)
osiris mcp run --selftest
# Expected: "Selftest completed in <1.3s"

# 4. Verify configuration
osiris validate --json
# Expected: {"status": "valid", "errors": []}

# 5. Check connections
osiris connections list --json | jq '.connections | length'
# Expected: >0 connections configured

# 6. Test connection health
osiris connections doctor --json
# Expected: All connections show "status": "healthy"

# 7. Verify filesystem isolation
ls -la "$(yq '.filesystem.base_path' testing_env/osiris.yaml)/.osiris/mcp/logs/"
# Expected: audit/, cache/, telemetry/ directories exist
```

### Security Requirements Validation

```bash
# 1. Verify zero credential leakage in MCP process
pytest tests/security/test_mcp_secret_isolation.py -v
# Expected: 10/10 PASS

# 2. Verify spec-aware secret masking
osiris connections list --json | jq '.connections[].config | keys[]' | grep -i "password\|key\|secret"
# Expected: No raw credential values, only "***MASKED***"

# 3. Test CLI delegation boundary
unset MYSQL_PASSWORD SUPABASE_SERVICE_ROLE_KEY
pytest tests/mcp/test_no_env_scenario.py -v
# Expected: All tools still work (inherit env from subprocess)

# 4. Verify audit logging
osiris mcp connections list --json
ls -la .osiris/mcp/logs/audit/
# Expected: audit-YYYY-MM-DD.jsonl file created with tool invocation logs
```

### Performance Baseline Verification

```bash
# 1. Measure selftest latency
time osiris mcp run --selftest
# Expected: <1.3s (target <2s)

# 2. Run load tests
pytest tests/load/test_mcp_load.py -v
# Expected: P95 latency ≤ 2× baseline under 100 concurrent calls

# 3. Check resource cleanup
pytest tests/mcp/test_cli_bridge.py::test_subprocess_cleanup -v
# Expected: No resource leaks, all subprocesses terminate
```

---

## 2. Environment Setup

### Setting Production Base Path

The `base_path` determines where all Osiris artifacts are stored. Set this to your production data directory:

```bash
# Navigate to production directory
cd /srv/osiris/production

# Initialize configuration (auto-sets base_path to current dir)
osiris init

# Verify base_path
yq '.filesystem.base_path' osiris.yaml
# Expected: /srv/osiris/production
```

**Configuration Precedence** (highest to lowest):
1. CLI flags: `--base-path /custom/path`
2. Environment variables: `OSIRIS_HOME=/custom/path`
3. `osiris.yaml`: `filesystem.base_path: /custom/path`
4. Default: Current working directory

### Secret Management

Osiris supports three methods for secret management:

#### Method 1: Environment Variables (Recommended for Production)

```bash
# Export secrets before starting MCP server
export MYSQL_PASSWORD="prod_password_here"  # pragma: allowlist secret
export SUPABASE_SERVICE_ROLE_KEY="eyJhbGc..."  # pragma: allowlist secret

# Verify secrets are set
env | grep -E "MYSQL_PASSWORD|SUPABASE_SERVICE_ROLE_KEY"

# Start MCP server (inherits environment)
osiris mcp run
```

#### Method 2: .env File (Development/Testing)

```bash
# Create .env file in production directory
cat > /srv/osiris/production/.env << 'EOF'
MYSQL_PASSWORD=prod_password_here  # pragma: allowlist secret
SUPABASE_SERVICE_ROLE_KEY=eyJhbGc...  # pragma: allowlist secret
EOF

# Secure permissions (readable only by service account)
chmod 600 /srv/osiris/production/.env
chown osiris:osiris /srv/osiris/production/.env

# Osiris auto-loads .env from CWD or project root
cd /srv/osiris/production
osiris mcp run
```

#### Method 3: Secrets Manager Integration (Enterprise)

```bash
# Fetch secrets from AWS Secrets Manager / HashiCorp Vault
export MYSQL_PASSWORD=$(aws secretsmanager get-secret-value \
  --secret-id prod/osiris/mysql --query SecretString --output text)

export SUPABASE_SERVICE_ROLE_KEY=$(vault kv get \
  -field=key secret/osiris/supabase)

# Start MCP server
osiris mcp run
```

### Configuration Best Practices

**Production `osiris.yaml` template**:

```yaml
filesystem:
  base_path: "/srv/osiris/production"  # Absolute production path
  mcp_logs_dir: ".osiris/mcp/logs"    # Relative to base_path

logging:
  level: INFO  # Use INFO in production, DEBUG for troubleshooting
  events:
    - "*"  # Log all structured events
  metrics:
    enabled: true
    retention_hours: 168  # 7 days

validation:
  retry:
    max_attempts: 2  # Allow retry for validation errors

aiop:
  enabled: true  # Enable for LLM-assisted debugging
  policy: core  # Core only (no large annex files)
  max_core_bytes: 300000
```

---

## 3. Claude Desktop Integration

### Automatic Configuration Generation

```bash
# Generate Claude Desktop config with resolved paths
osiris mcp clients --json

# Output includes:
# - Absolute repository path
# - Virtual environment Python executable
# - Suggested OSIRIS_HOME
# - Complete JSON config block
```

### Manual Configuration

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**Linux**: `~/.config/Claude/claude_desktop_config.json`

**Production Configuration Example**:

```json
{
  "mcpServers": {
    "osiris": {
      "command": "/bin/bash",
      "args": [
        "-lc",
        "cd /srv/osiris/production && exec /srv/osiris/production/.venv/bin/python -m osiris.cli.mcp_entrypoint"
      ],
      "transport": {
        "type": "stdio"
      },
      "env": {
        "OSIRIS_HOME": "/srv/osiris/production",
        "PYTHONPATH": "/srv/osiris/production"
      }
    }
  }
}
```

**Key Points**:
- Use absolute paths for `command` and working directory
- Set `OSIRIS_HOME` to production base path
- Use `-lc` to load login shell (inherits environment variables)
- Do NOT include secrets in `env` block (use .env or export instead)

### Verifying Connection

**Step 1**: Restart Claude Desktop

**Step 2**: In Claude Desktop, check for Osiris MCP server in available tools:
- Should see tools: `connections_list`, `discovery_request`, `oml_validate`, etc.

**Step 3**: Test basic tool:
```
# In Claude Desktop chat:
Use the connections_list tool to show available database connections
```

**Expected**: JSON response with masked credentials (`***MASKED***`)

**Step 4**: Check MCP logs:
```bash
ls -la /srv/osiris/production/.osiris/mcp/logs/
# Expected:
# - audit/audit-YYYY-MM-DD.jsonl (tool invocations)
# - telemetry/telemetry-YYYY-MM-DD.jsonl (performance metrics)
# - cache/ (discovery cache artifacts)
```

---

## 4. Secret Management Best Practices

### Rotating Connection Secrets

When rotating database passwords or API keys:

```bash
# 1. Update .env file or export new secret
export MYSQL_PASSWORD="new_password_here"  # pragma: allowlist secret

# 2. Test connection with new credentials
osiris connections doctor --json

# 3. Restart Claude Desktop to reload environment
# (MCP server inherits parent environment)

# 4. Verify no old credentials in logs
grep -r "old_password" /srv/osiris/production/.osiris/mcp/logs/
# Expected: No matches (secrets are masked)
```

### Protecting MCP Logs (Audit Trail)

MCP logs contain sensitive audit information but **never contain raw secrets** (spec-aware masking enforced):

```bash
# Set restrictive permissions on log directories
chmod 700 /srv/osiris/production/.osiris/mcp/logs/
chmod 600 /srv/osiris/production/.osiris/mcp/logs/audit/*.jsonl
chmod 600 /srv/osiris/production/.osiris/mcp/logs/telemetry/*.jsonl

# Verify no secrets leaked to logs
grep -r "MASKED" /srv/osiris/production/.osiris/mcp/logs/audit/
# Expected: All password/key fields show "***MASKED***"
```

### Preventing Secret Leakage in Logs

Osiris uses **spec-aware secret masking** based on component `x-secret` declarations:

```bash
# Example: MySQL connector spec declares secrets
# osiris/components/mysql/extractor/spec.yaml:
#   x-secret: [/password, /ssl_key, /ssl_cert]

# Verification:
osiris connections list --json | jq '.connections.mysql.main.config.password'
# Expected: "***MASKED***" (not raw password)

# Test masking for all families
for family in mysql supabase postgres; do
  echo "Testing $family:"
  osiris connections list --json | \
    jq ".connections.$family // {} | .[] | .config | keys"
done
```

---

## 5. Monitoring Recommendations

### Telemetry Logs

Monitor performance and health via structured telemetry:

```bash
# View latest telemetry
tail -f /srv/osiris/production/.osiris/mcp/logs/telemetry/telemetry-$(date +%Y-%m-%d).jsonl | jq '.'

# Key metrics to monitor:
# - duration_ms: Tool execution time
# - bytes_in / bytes_out: Payload sizes
# - correlation_id: Request tracing
# - timestamp: Event timing
```

**Alerting Thresholds** (suggested):

```bash
# Extract P95 latency from telemetry
jq -s '[.[].duration_ms] | sort | .[length * 0.95 | floor]' \
  /srv/osiris/production/.osiris/mcp/logs/telemetry/telemetry-*.jsonl

# Alert if:
# - P95 latency > 2000ms (baseline × 2)
# - Error rate > 5% (more than 1 in 20 calls fail)
# - Selftest duration > 2s (target <1.3s)
```

### Audit Log Review Procedures

Review audit logs for security compliance:

```bash
# Daily audit review
jq 'select(.timestamp >= "2025-10-20")' \
  /srv/osiris/production/.osiris/mcp/logs/audit/audit-*.jsonl | \
  jq -r '[.timestamp, .tool_name, .status, .correlation_id] | @tsv'

# Check for suspicious patterns
# - Repeated connection failures
# - Unusually large payloads (>16MB blocked)
# - High-frequency tool calls (potential abuse)

# Example: Detect >10 calls/minute from single correlation prefix
jq -r '.correlation_id[:8]' audit-*.jsonl | sort | uniq -c | awk '$1 > 10'
```

### Performance Metrics to Track

**Metrics Dashboard** (Grafana/DataDog/etc.):

1. **Selftest Latency** (SLO: <2s)
   ```bash
   time osiris mcp run --selftest
   ```

2. **Tool Invocation P95** (SLO: <2× baseline ~1.2s)
   ```bash
   jq -s 'map(.duration_ms) | add / length' telemetry-*.jsonl
   ```

3. **Error Rate** (Target: <5%)
   ```bash
   jq -s 'map(select(.status == "error")) | length' audit-*.jsonl
   ```

4. **Cache Hit Rate** (Higher = better performance)
   ```bash
   grep "cache_hit\|cache_miss" telemetry-*.jsonl | \
     awk '/cache_hit/{h++} /cache_miss/{m++} END{print "Hit rate:", h/(h+m)*100"%"}'
   ```

5. **Resource Usage**
   ```bash
   # Monitor MCP server process (PID from Claude Desktop)
   ps aux | grep "osiris.cli.mcp_entrypoint" | awk '{print "RSS:", $6/1024"MB"}'
   ```

### Alerting Recommendations

**Critical Alerts**:
- Selftest fails (exit code ≠ 0)
- Error rate >10% over 5 minutes
- P95 latency >3× baseline
- Secret detected in logs (grep for non-MASKED credentials)

**Warning Alerts**:
- Error rate >5% over 10 minutes
- Cache invalidation failures
- Disk space <10% free on base_path mount

---

## 6. Troubleshooting Common Issues

### Server Won't Start

**Symptom**: Claude Desktop shows "MCP server failed to start"

**Diagnosis**:
```bash
# Test command manually
cd /srv/osiris/production
.venv/bin/python -m osiris.cli.mcp_entrypoint

# Check for errors in output
# Common issues:
# - ModuleNotFoundError: Virtual environment not activated
# - Permission denied: Incorrect file permissions
# - Config not found: OSIRIS_HOME not set correctly
```

**Solutions**:
1. **Missing dependencies**: `pip install -r requirements.txt`
2. **Wrong Python path**: Use absolute path to venv Python in config
3. **Missing OSIRIS_HOME**: Set in Claude Desktop config `env` block
4. **Permission issues**: `chown -R osiris:osiris /srv/osiris/production`

### Tools Returning Errors

**Symptom**: Tools return `{"status": "error", "error_code": "INTERNAL_ERROR"}`

**Diagnosis**:
```bash
# Check MCP audit logs for error details
jq 'select(.status == "error")' \
  /srv/osiris/production/.osiris/mcp/logs/audit/audit-$(date +%Y-%m-%d).jsonl

# Common error codes:
# - CONNECTION_ERROR: Database unreachable
# - TIMEOUT_ERROR: CLI subprocess timeout (>30s)
# - VALIDATION_ERROR: Invalid OML syntax
# - SUBPROCESS_ERROR: CLI exit code ≠ 0
```

**Solutions**:
1. **CONNECTION_ERROR**: Verify `osiris connections doctor --json`
2. **TIMEOUT_ERROR**: Increase timeout in `mcp/cli_bridge.py` or optimize query
3. **VALIDATION_ERROR**: Run `osiris oml validate <file>` for detailed errors
4. **SUBPROCESS_ERROR**: Check stderr in audit logs for CLI error message

### Connection Issues

**Symptom**: `connections_doctor` reports unhealthy connections

**Diagnosis**:
```bash
# Test connection manually
osiris connections doctor --json | jq '.connections[] | select(.status == "unhealthy")'

# Check specific connection
MYSQL_PASSWORD="test" osiris connections doctor --json | \  # pragma: allowlist secret
  jq '.connections.mysql.main'
```

**Solutions**:
1. **Auth failure**: Verify credentials in .env file or exports
2. **Network timeout**: Check firewall rules, DNS resolution
3. **SSL/TLS errors**: Verify SSL certificate paths in `osiris_connections.yaml`
4. **Wrong host/port**: Double-check connection parameters

### Secret Masking Not Working

**Symptom**: Raw credentials appear in logs or tool output

**Critical Security Issue**: Stop MCP server immediately and investigate

**Diagnosis**:
```bash
# Verify spec-aware masking
osiris connections list --json | jq '.connections[].config' | grep -v "MASKED"

# Expected: Only non-secret fields (host, port, database) visible
# If passwords/keys visible: SECURITY BUG

# Check component spec declarations
grep -r "x-secret" osiris/components/*/spec.yaml
```

**Solutions**:
1. **Missing x-secret declaration**: Add to component spec.yaml
2. **New secret field**: Update ComponentRegistry and add to spec
3. **Bypass in code**: Search for direct config access without masking
4. **Report immediately**: File security bug if masking bypassed

### Performance Degradation

**Symptom**: Tools slow, timeouts, high latency

**Diagnosis**:
```bash
# Check P95 latency trend
jq -s 'group_by(.timestamp[:10]) | map({date: .[0].timestamp[:10], p95: ([.[].duration_ms] | sort | .[length * 0.95 | floor])})' \
  telemetry-*.jsonl

# Check concurrent load
jq 'select(.tool_name)' audit-*.jsonl | \
  awk '{print $1}' | uniq -c | sort -rn | head -10
```

**Solutions**:
1. **High discovery load**: Enable cache, increase `cache_ttl` to 48h
2. **Concurrent requests**: Monitor subprocess cleanup, check for leaks
3. **Large payloads**: Enable payload limits (<16MB enforced)
4. **Database slow**: Optimize queries, add indexes, review discovery config

---

## Appendix: Quick Reference

### Essential Commands

```bash
# Health check
osiris mcp run --selftest

# Configuration
osiris validate --json
osiris mcp clients --json

# Connections
osiris connections list --json
osiris connections doctor --json

# Logs
tail -f .osiris/mcp/logs/audit/audit-$(date +%Y-%m-%d).jsonl
tail -f .osiris/mcp/logs/telemetry/telemetry-$(date +%Y-%m-%d).jsonl

# Testing
pytest tests/security/test_mcp_secret_isolation.py -v
pytest tests/mcp/test_error_scenarios.py -v
pytest tests/load/test_mcp_load.py -v
```

### Log Locations

```
<base_path>/.osiris/mcp/logs/
├── audit/
│   └── audit-YYYY-MM-DD.jsonl      # Tool invocation audit trail
├── telemetry/
│   └── telemetry-YYYY-MM-DD.jsonl  # Performance metrics
└── cache/
    └── disc_<id>/                  # Discovery cache artifacts
```

### Security Checklist

- [ ] Secrets managed via environment variables (not config files)
- [ ] .env file has 600 permissions (`chmod 600 .env`)
- [ ] Base path has restricted access (`chmod 700 /srv/osiris`)
- [ ] Audit logs monitored daily for suspicious activity
- [ ] No raw credentials in logs (verify `grep -r MASKED`)
- [ ] Security tests passing (`pytest tests/security/ -v`)

---

**Support**: For issues not covered in this guide, see:
- [MCP Overview](./mcp-overview.md) - Architecture and design
- [ADR-0036](../adr/0036-mcp-interface.md) - CLI-first security model
- [Phase 3 Verification](../milestones/mcp-v0.5.0/30-verification.md) - Test procedures
