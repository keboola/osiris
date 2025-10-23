# MCP Server Manual Testing Guide

## Overview

This guide provides comprehensive manual test procedures for the Osiris MCP (Model Context Protocol) server. These tests validate integration with Claude Desktop, multi-environment compatibility, secret rotation scenarios, and network interruption handling.

**Purpose**: Enable developers to manually validate MCP server functionality in real-world conditions beyond automated test coverage.

**Target Audience**: Developers performing pre-release validation, troubleshooting production issues, or verifying platform-specific behavior.

**Related Documentation**:
- Architecture: [ADR-0036: MCP Interface](../adr/0036-mcp-interface.md)
- Implementation: [MCP Phase 1 Completion](../milestones/mcp-phase1-completion.md)
- Automated Tests: [E2B Testing Guide](./e2b-testing-guide.md)

---

## Test Environment Setup

### Prerequisites

1. **Python Environment**:
   ```bash
   cd /Users/padak/github/osiris
   source .venv/bin/activate
   python --version  # Should be 3.10+
   ```

2. **Configuration Files**:
   ```bash
   cd testing_env
   ls -la osiris.yaml osiris_connections.yaml .env
   # Verify all three files exist
   ```

3. **Claude Desktop** (for integration tests):
   - Install from: https://claude.ai/download
   - Version: v0.7.0+ (supports MCP protocol 2025-06-18)

4. **Test Database Credentials** (optional for live tests):
   - MySQL connection configured in `osiris_connections.yaml`
   - Secrets in `testing_env/.env` or exported as environment variables

---

## Test Scenario 1: Claude Desktop Integration

### 1.1 Installation and Configuration

**Objective**: Verify MCP server can be configured and launched from Claude Desktop.

**Steps**:

1. **Generate Claude Desktop Configuration**:
   ```bash
   cd /Users/padak/github/osiris
   source .venv/bin/activate
   python osiris.py mcp clients
   ```

   **Expected Output**:
   ```json
   {
     "mcpServers": {
       "osiris": {
         "command": "/Users/padak/github/osiris/.venv/bin/python",
         "args": ["/Users/padak/github/osiris/osiris.py", "mcp", "run"],
         "env": {
           "OSIRIS_HOME": "/Users/padak/github/osiris/testing_env"
         }
       }
     }
   }
   ```

   **Pass Criteria**:
   - JSON output is valid and parseable
   - Paths are absolute (no relative paths)
   - `OSIRIS_HOME` points to testing_env directory

2. **Add Configuration to Claude Desktop**:
   ```bash
   # macOS
   open ~/Library/Application\ Support/Claude/claude_desktop_config.json

   # Linux
   xdg-open ~/.config/Claude/claude_desktop_config.json

   # Windows (WSL)
   notepad.exe "$APPDATA/Claude/claude_desktop_config.json"
   ```

   **Action**: Copy the JSON output from Step 1 into the config file.

3. **Restart Claude Desktop**:
   - Quit Claude Desktop completely (Cmd+Q on macOS)
   - Relaunch Claude Desktop
   - Look for MCP server icon in chat interface (hammer icon)

   **Pass Criteria**:
   - Claude Desktop starts without errors
   - MCP server icon appears in chat UI
   - No error messages in Claude Desktop logs

4. **Verify Server Logs**:
   ```bash
   cd /Users/padak/github/osiris/testing_env
   ls -la .osiris/mcp/logs/
   # Should see: audit/, cache/, mcp_server.log

   tail -f .osiris/mcp/logs/mcp_server.log
   ```

   **Expected Log Contents**:
   ```
   [INFO] MCP server starting...
   [INFO] Loaded 10 tools: connections_list, connections_doctor, ...
   [INFO] Server ready, awaiting client connection
   ```

   **Pass Criteria**:
   - Log directory exists under `.osiris/mcp/logs/`
   - Server startup logged successfully
   - No Python tracebacks or error messages

### 1.2 Basic Tool Invocation

**Objective**: Verify MCP tools can be invoked from Claude Desktop chat interface.

**Steps**:

1. **Test connections_list Tool**:

   In Claude Desktop chat, type:
   ```
   Use the connections_list tool to show me available database connections.
   ```

   **Expected Behavior**:
   - Claude invokes `connections_list` tool
   - Response shows connection list with masked secrets
   - Format: `{connections: [{family, alias, reference, config}], count, status}`

   **Example Response**:
   ```json
   {
     "connections": [
       {
         "family": "mysql",
         "alias": "main",
         "reference": "@mysql.main",
         "config": {
           "host": "localhost",
           "port": 3306,
           "user": "osiris_user",
           "password": "***MASKED***"
         }
       }
     ],
     "count": 1,
     "status": "success"
   }
   ```

   **Pass Criteria**:
   - Tool executes without errors
   - All password/key fields show `***MASKED***`
   - Response includes correlation_id, duration_ms, bytes_in, bytes_out metrics

2. **Test discovery_request Tool**:

   In Claude Desktop chat, type:
   ```
   Use discovery_request to inspect the database schema for @mysql.main
   ```

   **Expected Behavior**:
   - Claude invokes `discovery_request` with connection parameter
   - Server returns schema information (tables, columns, types)
   - Results cached in `.osiris/mcp/logs/cache/`

   **Pass Criteria**:
   - Discovery completes within 30 seconds
   - Schema JSON is valid and includes table/column metadata
   - Cache file created: `.osiris/mcp/logs/cache/disc_<id>/overview.json`

3. **Test oml_schema_get Tool**:

   In Claude Desktop chat, type:
   ```
   Show me the OML pipeline schema using oml_schema_get
   ```

   **Expected Behavior**:
   - Returns JSON Schema for OML v0.1.0
   - Schema includes required fields: version, pipeline, extract, load, transform

   **Pass Criteria**:
   - Valid JSON Schema returned
   - Schema version matches OML v0.1.0
   - No errors or truncation

### 1.3 Error Recovery Scenarios

**Objective**: Verify graceful error handling in Claude Desktop integration.

**Steps**:

1. **Invalid Connection Reference**:

   In Claude Desktop chat:
   ```
   Use connections_doctor with connection "@invalid.connection"
   ```

   **Expected Behavior**:
   - Error message: "Connection @invalid.connection not found"
   - Suggestion: "Check osiris_connections.yaml for available connections"
   - No server crash or restart

   **Pass Criteria**:
   - Error response is user-friendly
   - Contains `error_family: SEMANTIC`
   - Server remains responsive for next request

2. **Missing Required Argument**:

   In Claude Desktop chat:
   ```
   Use connections_doctor without providing connection
   ```

   **Expected Behavior**:
   - Error message: "connection is required"
   - Suggestion: "Provide a connection reference like @mysql.default"

   **Pass Criteria**:
   - Schema validation error returned
   - Claude understands error and can retry with correct argument

3. **Network Timeout Simulation**:

   ```bash
   # Terminal 1: Start server with debug mode
   cd /Users/padak/github/osiris
   source .venv/bin/activate
   python osiris.py mcp run --debug

   # Terminal 2: Kill server mid-request
   pkill -f "osiris.py mcp run"
   ```

   **Expected Behavior** (in Claude Desktop):
   - Error message: "Server disconnected" or "Tool execution failed"
   - Claude Desktop shows MCP server as offline (red icon)
   - User can restart conversation or reconnect

   **Pass Criteria**:
   - No data corruption in logs or cache
   - Clean shutdown or proper error state
   - Server can restart successfully after kill

---

## Test Scenario 2: Multi-Environment Testing

### 2.1 macOS Platform

**Environment**: macOS 14+ (Sonoma)

**Steps**:

1. **Server Startup**:
   ```bash
   cd /Users/padak/github/osiris
   source .venv/bin/activate
   python osiris.py mcp run --selftest
   ```

   **Expected Output**:
   ```
   ✓ Server initialized in <200ms
   ✓ 10 tools registered
   ✓ Audit logger functional
   ✓ CLI bridge operational
   ✓ Selftest completed in <1.3s
   ```

   **Pass Criteria**:
   - Selftest completes in <2 seconds
   - All checks pass with ✓ marks
   - No Python warnings or errors

2. **Environment Variable Loading**:
   ```bash
   cd /Users/padak/github/osiris/testing_env
   cat .env  # Verify secrets exist
   export MYSQL_PASSWORD="test-password"  # pragma: allowlist secret
   python ../osiris.py mcp connections list --json
   ```

   **Pass Criteria**:
   - CLI inherits environment variables from shell
   - Secrets are masked in output
   - No "secret not found" errors

3. **Path Handling**:
   ```bash
   cd /Users/padak/github/osiris/testing_env
   python ../osiris.py init  # Verify auto-path detection
   grep "base_path" osiris.yaml
   ```

   **Expected**: `base_path: "/Users/padak/github/osiris/testing_env"` (absolute path)

   **Pass Criteria**:
   - `base_path` is absolute, not relative
   - MCP logs created under `<base_path>/.osiris/mcp/logs/`

### 2.2 Linux Platform (Ubuntu 22.04+)

**Environment**: Ubuntu 22.04 LTS or Debian 11+

**Steps**:

1. **Installation Check**:
   ```bash
   cd ~/osiris  # Adjust to your clone path
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   python osiris.py mcp run --selftest
   ```

   **Known Differences**:
   - Python may be `python3` instead of `python`
   - Virtual env activation: `source .venv/bin/activate` (same as macOS)

   **Pass Criteria**:
   - Dependencies install without errors
   - Selftest passes with same timing as macOS

2. **Claude Desktop Integration** (if available on Linux):
   ```bash
   # Linux config path
   mkdir -p ~/.config/Claude
   python osiris.py mcp clients > ~/.config/Claude/claude_desktop_config.json
   ```

   **Pass Criteria**:
   - Config file created successfully
   - Paths resolve correctly on Linux filesystem

### 2.3 Windows (WSL2)

**Environment**: WSL2 with Ubuntu 22.04

**Steps**:

1. **WSL Path Translation**:
   ```bash
   cd /mnt/c/Users/<username>/osiris  # Windows path mounted in WSL
   source .venv/bin/activate
   python osiris.py mcp run --selftest
   ```

   **Known Differences**:
   - Windows paths mounted under `/mnt/c/`
   - Line endings may differ (LF vs CRLF)

   **Pass Criteria**:
   - Server starts without path errors
   - Logs written to correct WSL filesystem paths

2. **Environment Variables**:
   ```bash
   # WSL inherits Windows environment variables
   export OSIRIS_HOME="/mnt/c/Users/<username>/osiris/testing_env"
   python osiris.py mcp connections list --json
   ```

   **Pass Criteria**:
   - Environment variables accessible from WSL
   - No permission errors on Windows-mounted filesystems

---

## Test Scenario 3: Secret Rotation

### 3.1 Mid-Session Credential Update

**Objective**: Verify that updating secrets mid-session does not break existing connections or cause security issues.

**Setup**:
```bash
cd /Users/padak/github/osiris/testing_env
cp .env .env.backup  # Backup current secrets
```

**Steps**:

1. **Establish Baseline Connection**:
   ```bash
   cd /Users/padak/github/osiris/testing_env
   python ../osiris.py mcp connections list --json | jq '.connections[0].family'
   # Expected: "mysql" or "supabase"
   ```

2. **Rotate Secret (Simulate Database Password Change)**:
   ```bash
   # Edit .env file
   nano .env
   # Change MYSQL_PASSWORD to new value (must be valid in your test DB)
   # Example: MYSQL_PASSWORD=new-rotated-password  # pragma: allowlist secret
   ```

3. **Verify New Secret Loaded**:
   ```bash
   # Export new secret
   export MYSQL_PASSWORD="new-rotated-password"  # pragma: allowlist secret

   # Test connection with new secret
   python ../osiris.py mcp connections doctor --connection-id @mysql.main --json
   ```

   **Expected Behavior**:
   - CLI subprocess picks up new environment variable
   - Connection test succeeds with new password
   - No cached old password used

   **Pass Criteria**:
   - `connections_doctor` reports "connection_ok: true"
   - No authentication errors
   - Audit log shows successful connection test

4. **Test MCP Server Picks Up Rotation**:

   **In Claude Desktop** (if server is running):
   ```
   Use connections_doctor to test @mysql.main connection
   ```

   **Expected Behavior**:
   - MCP server delegates to CLI subprocess
   - CLI subprocess inherits new environment variable
   - Connection succeeds with rotated credential

   **Pass Criteria**:
   - No "authentication failed" errors
   - Server does not need restart to pick up new secret
   - Old secret not cached anywhere in MCP process

5. **Restore Original Secrets**:
   ```bash
   mv .env.backup .env
   ```

### 3.2 Invalid Secret Handling

**Objective**: Verify proper error messages when secrets are invalid.

**Steps**:

1. **Set Invalid Secret**:
   ```bash
   export MYSQL_PASSWORD="wrong-password-123"  # pragma: allowlist secret
   python ../osiris.py mcp connections doctor --connection-id @mysql.main --json
   ```

   **Expected Output**:
   ```json
   {
     "connection_ok": false,
     "error": "Authentication failed",
     "suggest": "Verify MYSQL_PASSWORD environment variable"
   }
   ```

   **Pass Criteria**:
   - Error message is clear and actionable
   - No stack traces in user-facing output
   - Diagnostic suggests checking environment variable

---

## Test Scenario 4: Network Interruption Handling

### 4.1 Database Connection Timeout

**Objective**: Verify graceful handling of database connection timeouts.

**Setup**:
```bash
# Option 1: Use firewall to block MySQL port
sudo pfctl -f /etc/pf.conf  # macOS
sudo iptables -A OUTPUT -p tcp --dport 3306 -j DROP  # Linux

# Option 2: Configure invalid host in osiris_connections.yaml
cp testing_env/osiris_connections.yaml testing_env/osiris_connections.yaml.backup
```

**Steps**:

1. **Configure Unreachable Host**:
   ```bash
   cd /Users/padak/github/osiris/testing_env
   nano osiris_connections.yaml
   ```

   Edit connection to point to unreachable host:
   ```yaml
   mysql:
     main:
       host: "192.0.2.1"  # TEST-NET-1, guaranteed unreachable
       port: 3306
       user: osiris_user
       password_env: MYSQL_PASSWORD
       database: test_db
   ```

2. **Test Connection with Timeout**:
   ```bash
   time python ../osiris.py mcp connections doctor --connection-id @mysql.main --json
   ```

   **Expected Behavior**:
   - Connection attempt times out after ~30 seconds (configurable)
   - Error message: "Connection timeout to 192.0.2.1:3306"
   - Command returns non-zero exit code

   **Pass Criteria**:
   - Timeout occurs within expected duration (not hanging indefinitely)
   - Error message is clear and includes host/port
   - No Python tracebacks in JSON output
   - Server remains responsive after timeout

3. **Test Discovery with Unreachable Database**:
   ```bash
   python ../osiris.py mcp discovery run --connection-id @mysql.main --json
   ```

   **Expected Output**:
   ```json
   {
     "error": "Discovery failed: connection timeout",
     "error_family": "CONNECTIVITY",
     "suggest": "Verify database host and network connectivity",
     "correlation_id": "disc_abc123...",
     "duration_ms": 30000
   }
   ```

   **Pass Criteria**:
   - Discovery fails gracefully (no crash)
   - Error family is `CONNECTIVITY`
   - Response includes metrics (duration_ms)

4. **Restore Working Configuration**:
   ```bash
   mv osiris_connections.yaml.backup osiris_connections.yaml
   ```

### 4.2 MCP Client Disconnect/Reconnect

**Objective**: Verify MCP server handles client disconnects gracefully.

**Steps**:

1. **Start MCP Server in Debug Mode**:
   ```bash
   cd /Users/padak/github/osiris
   source .venv/bin/activate
   python osiris.py mcp run --debug 2>&1 | tee mcp-debug.log
   ```

2. **Connect Claude Desktop** and invoke a tool:
   ```
   Use connections_list to show database connections
   ```

3. **Simulate Client Disconnect**:
   - Quit Claude Desktop (Cmd+Q or Alt+F4)
   - Observe server logs in terminal

   **Expected Log Output**:
   ```
   [INFO] Client disconnected
   [INFO] Cleaning up resources...
   [INFO] Server shutdown complete
   ```

   **Pass Criteria**:
   - Server detects client disconnect
   - No error tracebacks in logs
   - Resources cleaned up (no orphaned processes)

4. **Reconnect Claude Desktop**:
   - Relaunch Claude Desktop
   - Verify MCP server icon appears

   **Expected Behavior**:
   - New server process starts automatically
   - Previous session state is not carried over (stateless)
   - Server responds to new tool invocations

   **Pass Criteria**:
   - Server restarts cleanly
   - No stale cache data causes errors
   - New correlation IDs generated for each request

### 4.3 Long-Running Request Interruption

**Objective**: Verify cancellation of long-running discovery operations.

**Setup**:
Configure a very large database (1000+ tables) in `osiris_connections.yaml` (optional, or mock with delay).

**Steps**:

1. **Start Long-Running Discovery**:

   In Claude Desktop:
   ```
   Use discovery_request to inspect all tables in @mysql.main with full sampling
   ```

2. **Interrupt During Execution**:
   - Send Cmd+. (macOS) or Ctrl+C in Claude Desktop chat
   - Or quit Claude Desktop mid-request

3. **Check Server State**:
   ```bash
   tail -n 50 /Users/padak/github/osiris/testing_env/.osiris/mcp/logs/mcp_server.log
   ```

   **Expected Log Output**:
   ```
   [INFO] Discovery started: disc_xyz123...
   [WARN] Client cancelled request: disc_xyz123...
   [INFO] Cleaning up discovery resources
   ```

   **Pass Criteria**:
   - Server detects cancellation
   - Partial results not written to cache
   - No zombie processes or leaked file handles

4. **Verify Clean State After Cancellation**:
   ```bash
   python ../osiris.py mcp connections list --json
   # Should work normally
   ```

   **Pass Criteria**:
   - Server remains responsive
   - Next request succeeds
   - No corrupted cache files

---

## Test Scenario 5: Audit and Telemetry Validation

### 5.1 Audit Trail Completeness

**Objective**: Verify all tool invocations are logged to audit trail.

**Steps**:

1. **Clear Existing Audit Logs**:
   ```bash
   cd /Users/padak/github/osiris/testing_env
   rm -rf .osiris/mcp/logs/audit/*
   mkdir -p .osiris/mcp/logs/audit
   ```

2. **Invoke Multiple Tools**:
   ```bash
   python ../osiris.py mcp connections list --json > /dev/null
   python ../osiris.py mcp discovery run --connection-id @mysql.main --json > /dev/null
   python ../osiris.py mcp oml schema --json > /dev/null
   ```

3. **Inspect Audit Logs**:
   ```bash
   ls -lh .osiris/mcp/logs/audit/
   # Expected: audit_YYYYMMDD.jsonl files

   cat .osiris/mcp/logs/audit/audit_$(date +%Y%m%d).jsonl | jq '.tool_name'
   ```

   **Expected Output**:
   ```
   "connections_list"
   "discovery_request"
   "oml_schema_get"
   ```

   **Pass Criteria**:
   - All tool invocations logged
   - Each log entry has: timestamp, tool_name, correlation_id, duration_ms
   - Secrets are masked in logged arguments
   - No PII leaked in audit trail

### 5.2 Metrics Validation

**Objective**: Verify tool response metrics are accurate.

**Steps**:

1. **Invoke Tool and Capture Metrics**:
   ```bash
   cd /Users/padak/github/osiris/testing_env
   python ../osiris.py mcp connections list --json | jq '.correlation_id, .duration_ms, .bytes_in, .bytes_out'
   ```

   **Example Output**:
   ```json
   "conn_1729456789_abc123"
   450
   0
   2048
   ```

2. **Validate Metric Accuracy**:

   **correlation_id**:
   - Format: `<tool_prefix>_<timestamp>_<random_hex>`
   - Example: `conn_1729456789_abc123` (connections tool)

   **duration_ms**:
   - Should be >0 and <5000ms for simple operations
   - Discovery may take longer (up to 30 seconds)

   **bytes_in / bytes_out**:
   - `bytes_in`: Size of input arguments (usually 0 for list operations)
   - `bytes_out`: Size of JSON response payload

   **Pass Criteria**:
   - All metrics present in response
   - Values are reasonable (not negative or absurdly large)
   - Matches actual execution time (measure with `time` command)

---

## Troubleshooting

### Common Issues and Resolutions

#### Issue: "MCP server not found in Claude Desktop"

**Symptoms**: Hammer icon missing, no tools available

**Diagnosis**:
```bash
# Check config file exists
cat ~/Library/Application\ Support/Claude/claude_desktop_config.json

# Verify paths in config are absolute
python /Users/padak/github/osiris/osiris.py mcp clients
```

**Resolution**:
1. Ensure `claude_desktop_config.json` has correct paths
2. Restart Claude Desktop completely (quit and relaunch)
3. Check `~/.config/Claude/logs/` for error messages (Linux/macOS)

#### Issue: "Authentication failed" for database connections

**Symptoms**: `connections_doctor` reports connection failure

**Diagnosis**:
```bash
# Verify secrets are set
echo $MYSQL_PASSWORD  # Should NOT be empty
cat testing_env/.env | grep MYSQL_PASSWORD

# Test CLI directly
cd testing_env
python ../osiris.py mcp connections doctor --connection-id @mysql.main --json
```

**Resolution**:
1. Verify secret exists in `.env` file or exported as environment variable
2. Test database connection manually (e.g., `mysql -h localhost -u user -p`)
3. Check `osiris_connections.yaml` has correct host/port/user

#### Issue: "Discovery cache is stale"

**Symptoms**: Discovery returns outdated schema after database changes

**Diagnosis**:
```bash
# Check cache age
ls -lh testing_env/.osiris/mcp/logs/cache/disc_*/
# Cache expires after 24 hours

# View cached discovery
cat testing_env/.osiris/mcp/logs/cache/disc_*/overview.json | jq '.tables | length'
```

**Resolution**:
```bash
# Clear cache to force fresh discovery
rm -rf testing_env/.osiris/mcp/logs/cache/disc_*

# Or run connections_doctor which invalidates cache
python osiris.py mcp connections doctor --connection-id @mysql.main --json
```

#### Issue: "Server logs show stderr mixed with JSON"

**Symptoms**: Debug output contaminating JSON responses

**Diagnosis**:
```bash
# Check if debug mode is enabled
grep -r "logging.DEBUG" osiris/mcp/
```

**Resolution**:
1. Ensure `--debug` flag is NOT used in production Claude Desktop config
2. Verify CLI bridge redirects stderr properly:
   ```python
   # Expected in cli_bridge.py
   result = subprocess.run(..., capture_output=True, text=True)
   # stderr is separated from stdout
   ```

#### Issue: "Performance degradation over time"

**Symptoms**: Tool invocations slow down after server runs for hours

**Diagnosis**:
```bash
# Check log file size
du -sh testing_env/.osiris/mcp/logs/
# Should be <100MB

# Check for orphaned processes
ps aux | grep osiris
```

**Resolution**:
1. Restart MCP server (quit Claude Desktop)
2. Rotate large log files:
   ```bash
   cd testing_env/.osiris/mcp/logs
   mv mcp_server.log mcp_server.log.old
   ```
3. Consider log rotation policy (future enhancement)

---

## Pass/Fail Summary

### Test Scenario 1: Claude Desktop Integration
- [ ] 1.1 Installation and Configuration: Server starts, logs created, config valid
- [ ] 1.2 Basic Tool Invocation: All tools execute, secrets masked, metrics present
- [ ] 1.3 Error Recovery: Graceful errors, server stays responsive

### Test Scenario 2: Multi-Environment Testing
- [ ] 2.1 macOS: Selftest <2s, paths absolute, env vars loaded
- [ ] 2.2 Linux: Dependencies install, selftest passes
- [ ] 2.3 Windows WSL: Server starts, paths resolve correctly

### Test Scenario 3: Secret Rotation
- [ ] 3.1 Mid-Session Update: New secrets picked up without restart
- [ ] 3.2 Invalid Secrets: Clear error messages, no crashes

### Test Scenario 4: Network Interruption Handling
- [ ] 4.1 Database Timeout: Graceful timeout, clear errors, server responsive
- [ ] 4.2 Client Disconnect/Reconnect: Clean shutdown, successful restart
- [ ] 4.3 Long-Running Interruption: Cancellation detected, no corruption

### Test Scenario 5: Audit and Telemetry
- [ ] 5.1 Audit Trail: All invocations logged, secrets masked
- [ ] 5.2 Metrics: correlation_id, duration_ms, bytes_in/out present and accurate

---

## Test Execution Checklist

Use this checklist when performing a full manual test pass:

```
Pre-Test Setup:
[ ] Virtual environment activated
[ ] Configuration files exist (osiris.yaml, osiris_connections.yaml, .env)
[ ] Claude Desktop installed (v0.7.0+)
[ ] Test database accessible (optional for offline tests)

Scenario 1 - Claude Desktop Integration:
[ ] MCP config generated and added to Claude Desktop
[ ] Server starts without errors, logs created
[ ] connections_list invoked successfully
[ ] discovery_request completes with cached results
[ ] oml_schema_get returns valid schema
[ ] Invalid connection reference returns user-friendly error
[ ] Missing argument returns schema validation error
[ ] Server recovers from mid-request kill

Scenario 2 - Multi-Environment:
[ ] macOS selftest passes in <2s
[ ] Linux selftest passes (if available)
[ ] WSL selftest passes (if available)
[ ] Environment variables loaded correctly on all platforms

Scenario 3 - Secret Rotation:
[ ] Baseline connection established
[ ] Secret rotated mid-session
[ ] New secret picked up by CLI subprocess
[ ] connections_doctor succeeds with new credential
[ ] Invalid secret produces clear error message

Scenario 4 - Network Interruption:
[ ] Database timeout handled gracefully
[ ] Discovery fails with CONNECTIVITY error
[ ] Client disconnect detected, resources cleaned
[ ] Claude Desktop reconnects successfully
[ ] Long-running request cancellation handled

Scenario 5 - Audit and Telemetry:
[ ] All tool invocations logged to audit trail
[ ] Secrets masked in audit logs
[ ] Metrics present in all tool responses
[ ] Metric values reasonable and accurate

Post-Test:
[ ] All test artifacts cleaned up (if desired)
[ ] Original configuration restored
[ ] No orphaned processes (ps aux | grep osiris)
[ ] Logs reviewed for unexpected errors
```

---

## Appendix: Test Data

### Sample osiris_connections.yaml

```yaml
mysql:
  main:
    host: localhost
    port: 3306
    user: osiris_user
    password_env: MYSQL_PASSWORD
    database: test_db

supabase:
  main:
    url: https://yourproject.supabase.co
    key_env: SUPABASE_SERVICE_ROLE_KEY
```

### Sample .env

```bash
# Database credentials
MYSQL_PASSWORD=your-mysql-password  # pragma: allowlist secret
SUPABASE_SERVICE_ROLE_KEY=your-supabase-key  # pragma: allowlist secret

# Optional overrides
OSIRIS_HOME=/Users/padak/github/osiris/testing_env
```

### Sample Claude Desktop Config (macOS)

```json
{
  "mcpServers": {
    "osiris": {
      "command": "/Users/padak/github/osiris/.venv/bin/python",
      "args": [
        "/Users/padak/github/osiris/osiris.py",
        "mcp",
        "run"
      ],
      "env": {
        "OSIRIS_HOME": "/Users/padak/github/osiris/testing_env"
      }
    }
  }
}
```

---

## Version History

- **v1.0** (2025-10-20): Initial manual test guide for MCP v0.5.0 Phase 3
  - Claude Desktop integration tests
  - Multi-environment validation (macOS, Linux, WSL)
  - Secret rotation scenarios
  - Network interruption handling
  - Audit and telemetry validation
