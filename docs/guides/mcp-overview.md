# Osiris MCP Server Overview

## Introduction

The Osiris Model Context Protocol (MCP) server provides a standardized interface for AI-assisted OML (Osiris Markup Language) pipeline authoring. Built on the official MCP Python SDK, it replaces the legacy chat interface with a clean, deterministic tool surface accessible via stdio transport.

## Architecture

The MCP server follows a modular architecture with clear separation of concerns:

```
osiris/mcp/
├── server.py           # Main MCP server with stdio transport
├── config.py           # Configuration and tunables
├── errors.py           # Error taxonomy (SCHEMA, SEMANTIC, DISCOVERY, LINT, POLICY)
├── telemetry.py        # Telemetry emission for observability
├── selftest.py         # Health check and validation
├── cache.py            # Discovery cache with 24-hour TTL
├── resolver.py         # Resource URI resolver
├── audit.py            # Audit logging for compliance
├── payload_limits.py   # Payload size enforcement
└── tools/              # Tool implementations
    ├── connections.py  # Connection management
    ├── components.py   # Component discovery
    ├── discovery.py    # Database introspection
    ├── oml.py          # OML validation and persistence
    ├── guide.py        # Guided authoring
    ├── memory.py       # Session memory with PII redaction
    └── usecases.py     # Use case templates
```

## CLI-First Adapter Architecture

Osiris MCP server employs a **CLI-first adapter pattern** where tools requiring database connections or secrets delegate to Osiris CLI commands instead of handling environment variables directly. This architectural decision ensures secure secret management and maintains consistency with the standalone CLI.

### How It Works

When MCP tools need to access database connections or perform operations requiring secrets (passwords, API keys), they:

1. **Delegate to CLI**: Call `osiris connections list --json`, `osiris discovery request --json`, etc. via subprocess
2. **Inherit Environment**: CLI commands run in the same shell environment, automatically resolving secrets from `.env` files or environment variables
3. **Return JSON**: Parse structured CLI output and return to MCP client
4. **No Direct Secret Access**: MCP server process never reads passwords or credentials directly

### Security Principle: No Secrets in MCP Process

Osiris MCP never accesses or stores any credentials.  
All operations that require secrets (such as database passwords or API keys) are executed via the CLI bridge subprocess,  
which inherits the user’s environment and resolves variables like `${MYSQL_PASSWORD}` securely.

> This ensures complete isolation: the MCP server never touches `.env` files or sensitive data —  
> it simply delegates to `osiris ... --json` and returns structured results to the AI client.

### Example: Connection Doctor Flow

```
Claude Desktop (MCP client)
    ↓ calls connections_doctor
MCP Server
    ↓ spawns subprocess
CLI: osiris connections doctor --json
    ↓ reads osiris_connections.yaml
    ↓ resolves ${MYSQL_PASSWORD} from environment
    ↓ tests connection
    ↓ returns JSON result
MCP Server
    ↓ parses JSON
    ↓ returns to client
Claude Desktop
```

### Benefits

- **Security**: Secrets stay in CLI process, never flow through MCP protocol or client config
- **Consistency**: Single source of truth for connection handling - CLI and MCP use identical logic
- **Simplicity**: MCP server remains lightweight, focused on protocol handling rather than business logic
- **Debugging**: Same `osiris connections doctor --json` works in CLI and MCP contexts
- **Zero Configuration**: No need to pass secrets in Claude Desktop config

### Tools Using CLI Delegation

The following tools delegate to CLI commands:

- `connections_list` → `osiris connections list --json`
- `connections_doctor` → `osiris connections doctor --json`
- `discovery_request` → `osiris components discover --json`

Other tools (validation, schema retrieval, etc.) operate in-process as they don't require secrets.

See [ADR-0036](../adr/0036-mcp-interface.md) for the complete architectural rationale.

## Protocol Details

- **MCP Version**: 2025-06-18 (latest)
- **Server Version**: 0.5.0
- **Transport**: stdio with JSON-RPC
- **Payload Limit**: 16MB (configurable via OSIRIS_MCP_PAYLOAD_LIMIT_MB)
- **Handshake Timeout**: 2 seconds
- **Tool Naming**: Underscore-separated (e.g., `connections_list`) to comply with MCP validation

## Tool Surface

**IMPORTANT**: All tool names use underscores instead of periods to comply with Claude Desktop's MCP tool naming requirements (`^[a-zA-Z0-9_-]{1,64}$`).

### Connection Tools

#### connections_list

List all configured database connections from `osiris_connections.yaml`.

**Input**: None required
**Output**: List of connections with family, alias, and sanitized configuration

#### connections_doctor

Diagnose connection issues and validate configuration.

**Input**: `connection` (string, required)
**Output**: Health status and diagnostic checks

### Component Tools

#### components_list

List available pipeline components from the component registry.

**Input**: None required
**Output**: Components categorized by type (extractors, writers, processors)

### Discovery Tools

#### discovery_request

Discover database schema with optional sampling. Results are cached for 24 hours.

**Input**:

- `connection` (string, required)
- `component` (string, required)
- `samples` (integer, optional, 0-100)
- `idempotency_key` (string, optional)

**Output**: Discovery ID, cache status, artifact URIs

### OML Tools

#### oml_schema_get

Retrieve the OML v0.1.0 JSON schema.

**Input**: None required
**Output**: Schema URI and JSON schema definition

#### oml_validate

Validate OML pipeline definition with ADR-0019 compatible diagnostics.

**Input**:

- `oml_content` (string, required)
- `strict` (boolean, optional, default: true)

**Output**: Validation status and diagnostics

#### oml_save

Save OML pipeline draft.

**Input**:

- `oml_content` (string, required)
- `session_id` (string, required)
- `filename` (string, optional)

**Output**: Save status and draft URI

### Guidance Tools

#### guide_start

Get guided next steps for OML authoring based on current context.

**Input**:

- `intent` (string, required)
- `known_connections` (array, optional)
- `has_discovery` (boolean, optional)
- `has_previous_oml` (boolean, optional)
- `has_error_report` (boolean, optional)

**Output**: Objective, next step, example, and references

### Memory Tools

#### memory_capture

Capture session memory with consent and PII redaction.

**Input**:

- `consent` (boolean, required)
- `session_id` (string, required)
- `retention_days` (integer, optional, default: 365)
- Additional session data fields

**Output**: Capture status and memory URI

### Use Case Tools

#### usecases_list

List available OML use case templates.

**Input**: None required
**Output**: Use cases categorized by type with examples

## Tool Aliases (Backward Compatibility)

For backward compatibility, the server supports legacy tool names via aliasing:

### Osiris-Prefixed Names (ADR-0036 Legacy)

- `osiris.connections.list` → `connections_list`
- `osiris.connections.doctor` → `connections_doctor`
- `osiris.components.list` → `components_list`
- `osiris.introspect_sources` → `discovery_request`
- `osiris.usecases.list` → `usecases_list`
- `osiris.oml.schema.get` → `oml_schema_get`
- `osiris.validate_oml` → `oml_validate`
- `osiris.save_oml` → `oml_save`
- `osiris.guide_start` → `guide_start`
- `osiris.memory.capture` → `memory_capture`

### Dot-Notation Names (Pre-0.5.0)

- `connections.list` → `connections_list`
- `connections.doctor` → `connections_doctor`
- `components.list` → `components_list`
- `discovery.request` → `discovery_request`
- `usecases.list` → `usecases_list`
- `oml.schema.get` → `oml_schema_get`
- `oml.validate` → `oml_validate`
- `oml.save` → `oml_save`
- `guide.start` → `guide_start`
- `memory.capture` → `memory_capture`

## Resource Layer

All resources are served under the `osiris://mcp/` namespace:

### Read-Only Resources (data/)

- `osiris://mcp/schemas/oml/v0.1.0.json` - OML JSON schema
- `osiris://mcp/prompts/oml_authoring_guide.md` - Authoring guide
- `osiris://mcp/usecases/catalog.yaml` - Use case catalog

### Runtime Resources (state/)

- `osiris://mcp/discovery/{id}/*.json` - Discovery artifacts (cached)
- `osiris://mcp/drafts/oml/{session}.yaml` - OML drafts
- `osiris://mcp/memory/sessions/{session}.jsonl` - Session memory

## Error Handling

The server implements a structured error taxonomy:

```json
{
  "code": "FAMILY/HASH",
  "path": ["field", "subfield"],
  "message": "Human-readable error description",
  "suggest": "Optional fix suggestion"
}
```

Error families:

- **SCHEMA**: Schema validation errors
- **SEMANTIC**: Logic and semantic errors
- **DISCOVERY**: Discovery operation failures
- **LINT**: Code style and formatting issues
- **POLICY**: Permission and policy violations

## Configuration

### Environment Variables

#### Core Configuration

- `OSIRIS_HOME`: Base directory for connections, cache, memory, audit, telemetry (default: `<repo_root>/testing_env`)
- `PYTHONPATH`: Repository root path (required for imports)

#### MCP Server Configuration

- `OSIRIS_MCP_PAYLOAD_LIMIT_MB`: Max payload size (default: 16)
- `OSIRIS_MCP_HANDSHAKE_TIMEOUT`: Handshake timeout in seconds (default: 2.0)
- `OSIRIS_MCP_CACHE_TTL_HOURS`: Discovery cache TTL (default: 24)
- `OSIRIS_MCP_MEMORY_RETENTION_DAYS`: Memory retention period (default: 365)
- `OSIRIS_MCP_TELEMETRY_ENABLED`: Enable telemetry (default: true)

### OSIRIS_HOME Resolution

The server resolves `OSIRIS_HOME` with the following priority:

1. **Environment variable** `OSIRIS_HOME` (if set and non-empty) - takes precedence
2. **Default**: `<repo_root>/testing_env` - fallback if not set

This path is used for:

- **Connection files**: `osiris_connections.yaml` searched in OSIRIS_HOME first
- **Discovery cache**: `<OSIRIS_HOME>/.osiris/discovery/cache/`
- **OML drafts**: `<OSIRIS_HOME>/.osiris/drafts/oml/`
- **Session memory**: `<OSIRIS_HOME>/.osiris/memory/sessions/`
- **Audit logs**: `<OSIRIS_HOME>/.osiris_audit/`
- **Telemetry**: `<OSIRIS_HOME>/.osiris_telemetry/`

### Connection File Resolution

`osiris_connections.yaml` is searched in this order:

1. **`OSIRIS_HOME/osiris_connections.yaml`** (highest priority) - NEW in v0.5.0
2. Current working directory
3. Parent of current working directory
4. Repository root

## Running the Server

### CLI Subcommands (Recommended)

```bash
# Show help (does NOT start server)
osiris mcp --help

# Start MCP server
osiris mcp run

# Run with debug output
osiris mcp run --debug

# Run self-test (<2s)
osiris mcp run --selftest

# Show Claude Desktop config
osiris mcp clients

# List available tools
osiris mcp tools
```

### Direct Python Module

```bash
# Run server
python -m osiris.cli.mcp_entrypoint

# With flags
python -m osiris.cli.mcp_entrypoint --debug
python -m osiris.cli.mcp_entrypoint --selftest
```

### Integration with Claude Desktop

**Recommended configuration** (uses bash wrapper for proper environment):

```json
{
  "mcpServers": {
    "osiris": {
      "command": "/bin/bash",
      "args": [
        "-lc",
        "cd /path/to/osiris && exec /path/to/osiris/.venv/bin/python -m osiris.cli.mcp_entrypoint"
      ],
      "transport": {
        "type": "stdio"
      },
      "env": {
        "OSIRIS_HOME": "/path/to/osiris/testing_env",
        "PYTHONPATH": "/path/to/osiris"
      }
    }
  }
}
```

**Get auto-detected config**:

```bash
osiris mcp clients
```

This will output the correct paths for your system, including:

- Detected repository root
- Virtual environment python path
- Resolved OSIRIS_HOME
- Suggested OSIRIS_LOGS_DIR

## Observability

### Telemetry

When enabled, the server emits structured telemetry events to `<OSIRIS_HOME>/.osiris_telemetry/`:

- Tool call events with duration and payload size
- Handshake timing
- Server start/stop events
- Session metrics

### Audit Logging

All tool invocations are logged to `<OSIRIS_HOME>/.osiris_audit/` with:

- Tool name and sanitized arguments
- Session and correlation IDs
- Timestamps and call counters
- Automatic secret redaction

## Self-Test

The server includes a comprehensive self-test mode:

```bash
osiris mcp run --selftest
```

Tests:

1. Handshake completes in <2 seconds
2. `connections_list` responds successfully (tests alias resolution)
3. `oml_schema_get` returns valid v0.1.0 schema
4. All 10 tools are properly registered
5. Tool names comply with MCP validation pattern

Expected output:

```
✅ Handshake completed in 0.6s (<2s requirement)
✅ connections_list responded successfully
✅ oml_schema_get returned valid schema (v0.1.0)
✅ Found 10 registered tools
✅ All tests PASSED
```

## Security Considerations

- **Payload Limits**: Enforced 16MB limit prevents DoS
- **Secret Redaction**: Automatic masking in audit logs and telemetry
- **PII Protection**: Memory capture includes PII redaction
- **Consent Required**: Memory capture requires explicit consent
- **Connection Isolation**: Each session has isolated state
- **Environment Variable Substitution**: Connections support `${VAR}` for secrets

## Troubleshooting

### Tools Not Appearing in Claude Desktop

**Problem**: Claude Desktop shows validation error for tool names with periods.

**Solution**: We migrated to underscore-based tool names in v0.5.0. Restart Claude Desktop to pick up changes. Old dot-notation names work via backward compatibility aliases.

### Empty Connections List

**Problem**: `connections_list` returns empty array.

**Cause**: Connection file not found at expected location.

**Solution**:

1. Ensure `osiris_connections.yaml` exists in `OSIRIS_HOME`
2. Set `OSIRIS_HOME` environment variable in Claude Desktop config
3. Check connection file search order (see Configuration section)
4. Run `osiris mcp clients` to verify detected paths

### Handshake Timeout

**Problem**: Server fails to start or times out during handshake.

**Solution**:

1. Ensure `PYTHONPATH` is set to repository root
2. Activate virtual environment or specify full python path
3. Check `OSIRIS_HOME` exists and is writable
4. Run `osiris mcp run --selftest` for diagnostics

## Compatibility

- **Python**: 3.10+ required (3.13 recommended)
- **MCP SDK**: modelcontextprotocol>=1.2.1
- **Protocol**: MCP v2025-06-18 (latest)
- **Clients**: Claude Desktop v0.7.0+, any MCP-compatible client
- **Breaking Changes from v0.4.x**: Tool names changed from dot-notation to underscores (aliases provided for compatibility)

## Related Documentation

### Core Documentation

- **[ADR-0036: MCP Interface](../adr/0036-mcp-interface.md)** - Architectural decision record explaining why MCP was chosen over the legacy chat interface and the CLI-first adapter pattern
- **[MCP v0.5.0 Milestone](../milestones/mcp-milestone.md)** - Complete milestone specification including deliverables, acceptance criteria, and testing requirements
- **[MCP Implementation Checklist](../milestones/mcp-implementation.md)** - Known implementation gaps, work in progress, and production hardening tasks

### API Reference

- **[Tool Reference](./tool-reference.md)** - Detailed input/output schemas and examples for all 10 MCP tools

### Migration Guides

- **[Chat to MCP Migration](../migration/chat-to-mcp.md)** - Guide for migrating from legacy chat interface (if exists)
