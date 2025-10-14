# Milestone: Final MCP Server Implementation

🧩 **Updated for MCP v0.5.0 implementation parity (October 2025)**

## Purpose & Alignment

- Implement the clean MCP server mandated by `docs/adr/0036-mcp-interface.md`, using the official `modelcontextprotocol` Python SDK over stdio only.
- Retire legacy chat paths so all clients (Claude Desktop, Codex CLI, IDE extensions) talk to the same deterministic tool surface.
- Ensure handshake, resource URIs, and diagnostics conform to ADR-0036 and reuse the canonical OML validator without divergence.

## Deliverables

- **Server & Transport**
  - `osiris/mcp/__init__.py` and `osiris/mcp/server.py` bootstrap the SDK server with stdio transport.
  - `osiris/mcp/config.py` centralizes configuration and tunable parameters.
  - `osiris/mcp/selftest.py` exercises handshake and tool round-trips (<2s).
  - **CLI structure** (`osiris/cli/mcp_cmd.py` + `mcp_entrypoint.py`):
    - `osiris mcp run [--debug] [--selftest]` - Start server or run self-test
    - `osiris mcp clients` - Show auto-detected Claude Desktop configuration
    - `osiris mcp tools` - List registered tools with descriptions
    - `osiris mcp --help` - Display help without starting server
  - Direct module invocation: `python -m osiris.cli.mcp_entrypoint` supported for automation.
- **Tool Surface**
  - Tool handlers under `osiris/mcp/tools/` implement 10 tools with underscore-separated names (`connections_list`, `discovery_request`, `oml_validate`, etc.) to comply with MCP client validation requirements.
  - Backward compatibility aliases map legacy `osiris.*` prefixed names and dot-notation names to current underscore-based names.
  - All tools registered via `server._list_tools()` with deterministic ordering and schemas.
  - **Complete tool list**:
    - `connections_list` (aliases: `osiris.connections.list`, `connections.list`)
    - `connections_doctor` (aliases: `osiris.connections.doctor`, `connections.doctor`)
    - `components_list` (aliases: `osiris.components.list`, `components.list`)
    - `discovery_request` (aliases: `osiris.introspect_sources`, `discovery.request`)
    - `oml_schema_get` (aliases: `osiris.oml.schema.get`, `oml.schema.get`)
    - `oml_validate` (aliases: `osiris.validate_oml`, `oml.validate`)
    - `oml_save` (aliases: `osiris.save_oml`, `oml.save`)
    - `guide_start` (aliases: `osiris.guide_start`, `guide.start`)
    - `memory_capture` (aliases: `osiris.memory.capture`, `memory.capture`)
    - `usecases_list` (aliases: `osiris.usecases.list`, `usecases.list`)
  - `osiris/mcp/resources.py` serving canonical URIs (`osiris://mcp/schemas/oml/v0.1.0.json`, `osiris://mcp/usecases/catalog.yaml`, etc.).
  - Shared utilities: `osiris/mcp/errors.py`, `osiris/mcp/telemetry.py`, `osiris/mcp/payload_limits.py`, `osiris/mcp/audit.py`.
- **Testing Assets**
  - **Unit Tests** (12 test modules, 81+ tests total):
    - `tests/mcp/test_server_boot.py` - Server initialization and bootstrap
    - `tests/mcp/test_tools_connections.py` - Connection management tools
    - `tests/mcp/test_tools_components.py` - Component registry tools
    - `tests/mcp/test_tools_discovery.py` - Database discovery with caching
    - `tests/mcp/test_tools_oml.py` - OML validation, save, schema retrieval
    - `tests/mcp/test_tools_guide.py` - Guided authoring recommendations
    - `tests/mcp/test_tools_memory.py` - Memory capture with PII redaction
    - `tests/mcp/test_tools_usecases.py` - Use case template enumeration
    - `tests/mcp/test_cache_ttl.py` - Discovery cache TTL and invalidation
    - `tests/mcp/test_audit_events.py` - Audit logging for compliance
    - `tests/mcp/test_error_shape.py` - Error taxonomy and structured responses
    - `tests/mcp/test_oml_schema_parity.py` - OML schema version parity
  - **Integration Testing**: Selftest (`osiris mcp run --selftest`) exercises stdio handshake, all tools, and alias resolution (<2s)
  - **CI Integration**: Pytest suite runs on all commits; selftest smoke test in deployment pipeline
- **Documentation**
  - Updates to `docs/mcp/overview.md`, `docs/mcp/tool-reference.md`, and migration guides describing stdio launch, tool aliases, and ADR-0019 diagnostic parity.
  - Release note stub documenting chat deprecation and MCP activation.
- **Build Artifact**
  - The milestone produces an installable command-line entrypoint exposed as `osiris mcp run`.
  - The CLI is packaged with the standard Osiris build and included in all release distributions (wheel, container, binary).
  - QA validation includes verifying that `osiris mcp run` initializes the MCP server, passes handshake within <2 s, and lists all registered tools.

## Repository Structure & Resource Namespace

All MCP-related resources are now consolidated under the `osiris/mcp/` directory, using the following structure:

```
osiris/mcp/
  data/                 # read-only resources
    schemas/
    prompts/
    usecases/
  state/                # writable, ephemeral runtime data
    discovery/cache/
    drafts/oml/
    memory/sessions/
  tools/                # tool implementation modules
  storage/              # storage layer (memory store, persistence)
  server.py
  resolver.py
  config.py
  ...
```

All MCP URIs are unified under the `osiris://mcp/...` namespace, with the following mappings:

- `osiris://mcp/schemas/...` → `osiris/mcp/data/schemas/...`
- `osiris://mcp/prompts/...` → `osiris/mcp/data/prompts/...`
- `osiris://mcp/usecases/...` → `osiris/mcp/data/usecases/...`
- `osiris://mcp/discovery/...` → `osiris/mcp/state/discovery/cache/...`
- `osiris://mcp/drafts/...` → `osiris/mcp/state/drafts/...`
- `osiris://mcp/memory/...` → `osiris/mcp/state/memory/...`

All read-only data is versioned and immutable under `data/`, while all runtime state is isolated under `state/` and tied to `OSIRIS_HOME`.

The `resolver.py` module enforces this namespace boundary and validates all resource access through canonical `osiris://mcp/` URIs.

This consolidation replaces prior scattered paths (such as `/memory`, `/oml`, `/schemas`, etc.) and ensures predictability, clean packaging, and easier mempack generation.

## Environment Configuration

### OSIRIS_HOME Resolution

The server resolves `OSIRIS_HOME` with the following priority:

1. **Environment variable** `OSIRIS_HOME` (if set and non-empty) - takes precedence
2. **Default**: `<repo_root>/testing_env` - calculated via repository root detection

**Repository Root Detection**:

- Walk up directory tree from `osiris/cli/mcp_entrypoint.py`
- Find first parent directory containing `osiris` package directory
- Fallback to grandparent (2 levels up) if not found

**OSIRIS_HOME is used for**:

- Connection files: `<OSIRIS_HOME>/osiris_connections.yaml` (searched first)
- Discovery cache: `<OSIRIS_HOME>/.osiris/discovery/cache/`
- OML drafts: `<OSIRIS_HOME>/.osiris/drafts/oml/`
- Session memory: `<OSIRIS_HOME>/.osiris/memory/sessions/`
- Audit logs: `<OSIRIS_HOME>/.osiris_audit/`
- Telemetry: `<OSIRIS_HOME>/.osiris_telemetry/`

### Connection File Resolution

`osiris_connections.yaml` is searched in this order:

1. **`OSIRIS_HOME/osiris_connections.yaml`** (highest priority) - enables environment-specific configurations
2. Current working directory (`./osiris_connections.yaml`)
3. Parent directory (`../osiris_connections.yaml`)
4. Repository root (`<repo_root>/osiris_connections.yaml`)

This hierarchy allows:

- Production deployments to isolate connection configs in `OSIRIS_HOME`
- Local development to use repo-root connections as defaults
- Testing to override connections per test environment

**Connection files use environment variable substitution** for secrets:

```yaml
connections:
  mysql:
    db_movies:
      password: "${MYSQL_PASSWORD}" # Resolved from environment
```

### Environment Variables

| Variable                       | Purpose                                      | Default                   | Required                 |
| ------------------------------ | -------------------------------------------- | ------------------------- | ------------------------ |
| `OSIRIS_HOME`                  | Base directory for connections, cache, state | `<repo_root>/testing_env` | No                       |
| `PYTHONPATH`                   | Repository root for imports                  | Detected                  | Yes (for Claude Desktop) |
| `OSIRIS_LOGS_DIR`              | Logs directory                               | `<OSIRIS_HOME>/logs`      | No                       |
| `OSIRIS_MCP_PAYLOAD_LIMIT_MB`  | Max payload size                             | `16`                      | No                       |
| `OSIRIS_MCP_TELEMETRY_ENABLED` | Enable telemetry                             | `true`                    | No                       |

## Deterministic Behavior Requirements

1. **Tool Names & Aliases**: Primary names use underscore format (`connections_list`, `discovery_request`). Legacy `osiris.*` prefixed and dot-notation names are supported via backward compatibility aliases.
2. **Validation Flow**: `oml_validate` delegates to `osiris/core/oml_validator.py`, returning ADR-0019-compatible diagnostics (`{"type": "error", "line": N, "column": M, "message": "...", "id": "OML###"}`) with deterministic error IDs.
3. **Guide Determinism**: `guide_start` returns identical recommendations for identical inputs.
4. **Resource URIs**: All schema and snippet payloads resolved through versioned `osiris://mcp/` URIs with immutable casing.
5. **Protocol & Payload**: MCP protocol version negotiated by SDK during handshake (config reference: v0.5); 16 MB payload cap enforced and announced; selftest verifies both.

## Claude Desktop Integration

- **Configuration Generator**: `osiris mcp clients` outputs auto-detected config
- **Bash Wrapper**: Uses `bash -lc` with `cd` to ensure correct working directory
- **Environment Detection**:
  - Repository root via `find_repo_root()`
  - Virtual environment python executable
  - Resolved `OSIRIS_HOME` path
  - Suggested `OSIRIS_LOGS_DIR`
- **Config Format**:
  ```json
  {
    "mcpServers": {
      "osiris": {
        "command": "/bin/bash",
        "args": [
          "-lc",
          "cd <repo_root> && exec <venv_python> -m osiris.cli.mcp_entrypoint"
        ],
        "transport": { "type": "stdio" },
        "env": {
          "OSIRIS_HOME": "<OSIRIS_HOME>",
          "PYTHONPATH": "<repo_root>"
        }
      }
    }
  }
  ```

## CLI-Bridge Architecture

To ensure secure and consistent delegation from the MCP server to the Osiris CLI, the implementation introduces a dedicated CLI Bridge component at `osiris/mcp/cli_bridge.py`.

### How the CLI Bridge Works

The CLI Bridge is responsible for invoking Osiris CLI commands (such as `osiris connections list`, `osiris oml validate`, etc.) on behalf of the MCP server. It executes these commands within the current process environment, inheriting all secrets, credentials, and configuration files from the user's shell or deployment context. This approach ensures that secret resolution and environment-specific logic remain outside the MCP server's direct control, improving security and simplifying configuration management.

Key aspects of the CLI Bridge:

- **Secure Environment Inheritance:** CLI commands are executed with the same environment variables and file system access as the invoking process. This allows for seamless use of secrets (e.g., database passwords, API keys) resolved by the CLI, without MCP ever reading or storing them directly.
- **Standardized JSON I/O:** The bridge communicates with CLI commands using JSON input/output, enforcing a uniform contract for all delegated operations.
- **Exit Code & Error Mapping:** CLI exit codes are mapped to structured MCP errors, ensuring that failures are reported in a consistent, protocol-compliant manner.
- **Centralized Logging:** All CLI Bridge invocations and outputs are logged to the MCP log directories as defined by the filesystem contract (e.g., `<OSIRIS_HOME>/logs`), supporting unified observability and troubleshooting.

#### Benefits of the CLI Bridge

- Reuses existing CLI logic for consistency with standalone CLI behavior.
- Avoids duplicating secret resolution or environment logic within the MCP server.
- Keeps the MCP server lightweight and focused on protocol handling.
- Maintains full parity with Osiris CLI features and side effects.

## Implementation Plan

- **Phase 1 – Scaffold (Hour 0-1)**
  - Generate `osiris/mcp` package skeleton, add server bootstrap using SDK stdio transport, and lock protocol version.
  - Implement minimal CLI `osiris/cli/mcp_cmd.py` command structure with subcommands.
  - Commit golden manifest harness (`tests/mcp/data/tool_manifest.json`) seeded with placeholder entries.
- **Phase 2 – Wire Tools (Hour 1-2)**
  - Implement each tool handler with alias registration and payload limit guard; reuse existing discovery, guide, validator, and persistence modules.
  - Build `resources.py` loaders for schema and catalog URIs; validate file paths.
  - Flesh out `errors.py`, `telemetry.py`, `audit.py`, and deterministic diagnostics; update manifest snapshot.
- **Phase 3 – Self-test & Docs (Hour 2-3)**
  - Implement `selftest.py` to hit handshake, every tool, payload limit boundary, and resource fetch under 2 s.
  - Author pytest suites and stdio smoke test; integrate into CI workflow and ensure green run.
  - Update documentation artifacts and release note stub; remove or gate chat entrypoints.

## Acceptance Criteria / Definition of Done

- MCP handshake completes in < 2 seconds via `osiris mcp run --selftest`, announcing negotiated protocol version and 16 MB limit.
- Claude Desktop (or scripted equivalent) connects over stdio, lists all tools with aliases, and successfully calls `oml_validate` and `usecases_list`.
- `oml_validate` returns ADR-0019 diagnostic JSON with deterministic `OML###` IDs and invokes `osiris/core/oml_validator.py`.
- Tool manifest golden test passes, confirming tool names, aliases, resources, and protocol version are unchanged.
- All `tests/mcp/` suites (12 modules, 81+ tests) plus project-wide pytest run green in CI; selftest smoke job passes.
- Telemetry events emit per invocation with correlation IDs and no redacted secrets.

## Testing & Validation

- **Selftest**: `osiris mcp run --selftest` covers:
  - Handshake completion in <2 seconds
  - Backward compatibility alias resolution (`connections.list` → `connections_list`)
  - Tool response validation (`connections_list`, `oml_schema_get`)
  - Tool registry completeness (verifies all 10 tools registered)
  - Exit code 0 on success, 1 on failure
  - Total runtime <1 second typical
- **Pytest**: `pytest tests/mcp` executes unit suites, manifest golden, payload boundary, and deterministic diagnostics checks.
- **Smoke Integration**: CI script launches server via stdio, executes scripted Claude Desktop sequence, and verifies deterministic outputs.
- **Staging Validation**: Nightly job runs selftest and sample tool calls against staging telemetry dashboards to ensure events are captured.

## Observability

All MCP runtime outputs follow the Osiris Filesystem Contract defined in `osiris.yaml`.

### Logging and Audit Paths

MCP log destinations are configuration-driven:

```yaml
filesystem:
  base_path: "/path/to/project"
  mcp_logs_dir: ".osiris/mcp/logs" # default
  mcp_audit_dir: ".osiris/mcp/logs/audit" # default
```

If omitted, Osiris defaults to <base_path>/.osiris/mcp/logs/server.log for the main server log
and <base_path>/.osiris/mcp/logs/audit/ for per-tool audit events.

The osiris init command automatically writes these keys when generating a new project configuration.

Event Telemetry
• Audit Logging: All MCP tool invocations are appended to the audit directory with correlation IDs, timestamps, and secret redaction.
• Telemetry: Structured JSONL events are emitted to <OSIRIS_HOME>/.osiris_telemetry/ (configurable via logging.telemetry_dir).
• Schema: Duration, payload size, session ID, and status fields are standardized across all events.

**Example telemetry event emitted during MCP tool execution**:

```json
{
  "event": "tool_call",
  "tool": "oml_validate",
  "duration_ms": 482,
  "session_id": "sess-5fcb1a",
  "status": "ok",
  "payload_bytes": 1342,
  "timestamp": "2025-10-13T19:52:45.000Z"
}
```

These events are logged to `<OSIRIS_HOME>/.osiris_telemetry/` and collected by CI smoke tests to measure performance and determinism. The schema will be extended in 0.5.x for live dashboard integration.

## Risks & Mitigations

- **Tool Registry Drift**: Golden manifest test fails on any deviation; reviewers compare manifest diff against ADR-0036 before merge.
- **Protocol Version Drift**: Handshake asserts negotiated protocol version; CI includes check to block unexpected version bumps.
- **Buffer Handling / Payload Backpressure**: Payload guard centralized in `payload_limits.py`; tests simulate 16 MB boundary; telemetry alerts on timeouts.
- **Payload Limit Enforcement Gaps**: Enforce checks at entry, log structured errors, and add regression tests for oversized requests.
- **Resource Availability Regressions**: Selftest and unit tests verify required `osiris://mcp/` URIs; release checklist includes resource audit.
- **Telemetry Gaps**: Tests assert event payload shape; staging dashboard alarms on missing events.
- **Client Integration Regressions**: Scripted Claude Desktop handshake runs in CI; failure blocks deployment.
- **Memory Leaks in Long-Running Server**: Incorporate 60-minute soak in staging, monitor memory baseline, and add automated alerts.

## Readiness Summary

Completing this milestone yields a stdio MCP server that handshakes in <2 s using the official SDK, exposes deterministic tools with underscore-based names and backward compatibility aliases, validates OML through the canonical pipeline, and ships with CI-enforced tests plus selftest automation—ready for immediate integration by AI pair agents and human engineers.

This milestone completes the full MCP migration plan defined in ADR-0036.

## Versioning Note

This milestone ships as **Osiris v0.5.0.**

It introduces a breaking interface change (chat interface removed, MCP server as the new entrypoint).

Backward compatibility is intentionally not maintained; downstream tools and scripts must migrate to the new `osiris mcp` CLI.
