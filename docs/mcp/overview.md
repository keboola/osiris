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

## Protocol Details

- **MCP Version**: 0.5
- **Server Version**: 0.5.0
- **Transport**: stdio with JSON-RPC
- **Payload Limit**: 16MB (configurable via OSIRIS_MCP_PAYLOAD_LIMIT_MB)
- **Handshake Timeout**: 2 seconds

## Tool Surface

### Connection Tools

#### osiris.connections.list
List all configured database connections from `osiris_connections.yaml`.

**Input**: None required
**Output**: List of connections with family, alias, and sanitized configuration

#### osiris.connections.doctor
Diagnose connection issues and validate configuration.

**Input**: `connection_id` (string, required)
**Output**: Health status and diagnostic checks

### Component Tools

#### osiris.components.list
List available pipeline components from the component registry.

**Input**: None required
**Output**: Components categorized by type (extractors, writers, processors)

### Discovery Tools

#### osiris.introspect_sources (alias: discovery.request)
Discover database schema with optional sampling. Results are cached for 24 hours.

**Input**:
- `connection_id` (string, required)
- `component_id` (string, required)
- `samples` (integer, optional, 0-100)
- `idempotency_key` (string, optional)

**Output**: Discovery ID, cache status, artifact URIs

### OML Tools

#### osiris.oml.schema.get
Retrieve the OML v0.1.0 JSON schema.

**Input**: None required
**Output**: Schema URI and JSON schema definition

#### osiris.validate_oml (alias: oml.validate)
Validate OML pipeline definition with ADR-0019 compatible diagnostics.

**Input**:
- `oml_content` (string, required)
- `strict` (boolean, optional, default: true)

**Output**: Validation status and diagnostics

#### osiris.save_oml (alias: oml.save)
Save OML pipeline draft.

**Input**:
- `oml_content` (string, required)
- `session_id` (string, required)
- `filename` (string, optional)

**Output**: Save status and draft URI

### Guidance Tools

#### osiris.guide_start (alias: guide.start)
Get guided next steps for OML authoring based on current context.

**Input**:
- `intent` (string, required)
- `known_connections` (array, optional)
- `has_discovery` (boolean, optional)
- `has_previous_oml` (boolean, optional)
- `has_error_report` (boolean, optional)

**Output**: Objective, next step, example, and references

### Memory Tools

#### osiris.memory.capture
Capture session memory with consent and PII redaction.

**Input**:
- `consent` (boolean, required)
- `session_id` (string, required)
- `retention_days` (integer, optional, default: 365)
- Additional session data fields

**Output**: Capture status and memory URI

### Use Case Tools

#### osiris.usecases.list
List available OML use case templates.

**Input**: None required
**Output**: Use cases categorized by type with examples

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

Environment variables:
- `OSIRIS_MCP_PAYLOAD_LIMIT_MB`: Max payload size (default: 16)
- `OSIRIS_MCP_HANDSHAKE_TIMEOUT`: Handshake timeout in seconds (default: 2.0)
- `OSIRIS_MCP_CACHE_TTL_HOURS`: Discovery cache TTL (default: 24)
- `OSIRIS_MCP_MEMORY_RETENTION_DAYS`: Memory retention period (default: 365)
- `OSIRIS_MCP_TELEMETRY_ENABLED`: Enable telemetry (default: true)
- `OSIRIS_HOME`: Base directory for cache, memory, audit, telemetry

## Running the Server

### Via CLI
```bash
# Run MCP server
osiris mcp run

# Run with debug output
osiris mcp run --debug

# Run self-test
osiris mcp run --selftest
```

### Direct Python Module
```bash
# Run server
python -m osiris.cli.mcp_entrypoint

# With flags
python -m osiris.cli.mcp_entrypoint --debug --selftest
```

### Integration with Claude Desktop

Add to Claude Desktop configuration:

```json
{
  "mcpServers": {
    "osiris": {
      "command": "python",
      "args": ["-m", "osiris.cli.mcp_entrypoint"],
      "env": {
        "OSIRIS_HOME": "/path/to/osiris/home"
      }
    }
  }
}
```

## Observability

### Telemetry
When enabled, the server emits structured telemetry events to `~/.osiris_telemetry/`:
- Tool call events with duration and payload size
- Handshake timing
- Server start/stop events
- Session metrics

### Audit Logging
All tool invocations are logged to `~/.osiris_audit/` with:
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
2. connections.list responds successfully
3. oml.schema.get returns valid schema
4. All tools are properly registered

## Security Considerations

- **Payload Limits**: Enforced 16MB limit prevents DoS
- **Secret Redaction**: Automatic masking in audit logs
- **PII Protection**: Memory capture includes PII redaction
- **Consent Required**: Memory capture requires explicit consent
- **Connection Isolation**: Each session has isolated state

## Compatibility

- **Python**: 3.8+ required
- **MCP SDK**: modelcontextprotocol>=1.2.1
- **Protocol**: MCP v0.5
- **Clients**: Claude Desktop, any MCP-compatible client