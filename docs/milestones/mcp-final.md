# Milestone: Final MCP Server Implementation

## Purpose & Alignment

- Implement the clean MCP server mandated by `docs/adr/0036-mcp-interface.md`, using the official `modelcontextprotocol` Python SDK over stdio only.
- Retire legacy chat paths so all clients (Claude Desktop, Codex CLI, IDE extensions) talk to the same deterministic `osiris.*` tool surface.
- Ensure handshake, resource URIs, and diagnostics conform to ADR-0036 and reuse the canonical OML validator without divergence.

## Deliverables

- **Server & Transport**
  - `osiris/mcp/__init__.py` and `osiris/mcp/server.py` bootstrapping the SDK server, pinning MCP v0.5, and wiring stdio transport.
  - `osiris/mcp/config.py` for stdio-only configuration and payload limit constants.
  - `osiris/mcp/selftest.py` exercising handshake and tool round-trips for health checks.
  - `osiris/cli/mcp.py` command exposing `serve`, `--selftest`, and telemetry toggle flags.
- **Tool Surface**
  - Tool handlers under `osiris/mcp/tools/` registering deterministic names (`osiris.introspect_sources`, `osiris.guide_start`, `osiris.validate_oml`, `osiris.save_oml`, `osiris.usecases_list`) and ADR-0036 aliases (e.g., `discovery.request`, `guide.start`, `oml.validate`, `oml.save`).
  - `osiris/mcp/resources.py` serving canonical URIs (`osiris://schemas/oml/v0.1.0.json`, `osiris://usecases/catalog.yaml`, `osiris://templates/{name}.yaml`).
  - Shared utilities: `osiris/mcp/errors.py`, `osiris/mcp/telemetry.py`, `osiris/mcp/payload_limits.py`.
- **Testing Assets**
  - Unit tests: `tests/mcp/test_server_bootstrap.py`, `test_transport_stdio.py`, `test_tools_introspect.py`, `test_tools_validate.py`, `test_tools_save.py`, `test_tools_usecases.py`, `test_payload_limits.py`, `test_selftest.py`, `test_manifest_golden.py`.
  - Fixtures and golden manifest snapshot under `tests/mcp/data/tool_manifest.json`.
  - CI workflow (`.github/workflows/ci-mcp.yml` or equivalent) running pytest selection plus selftest smoke invocation.
- **Documentation**
  - Updates to `docs/mcp/overview.md`, `docs/mcp/selftest.md`, and `docs/migration/chat-to-mcp.md` describing stdio launch, tool aliases, and ADR-0019 diagnostic parity.
  - Release note stub documenting chat deprecation and MCP activation.
- **Build Artifact**
  - The milestone produces an installable command-line entrypoint exposed as osiris mcp run.
  - The CLI is packaged with the standard Osiris build and included in all release distributions (wheel, container, binary).
  - QA validation includes verifying that osiris mcp run initializes the MCP server, passes handshake within <2 s, and lists all registered tools.

## Deterministic Behavior Requirements

1. **Tool Names & Aliases**: Fixed primary names `osiris.*` with ADR-0036 aliases (`discovery.request`, `guide.start`, `oml.validate`, `oml.save`), enforced via manifest golden test.
2. **Validation Flow**: `osiris.validate_oml` delegates to `osiris/core/oml_validator.py`, returning ADR-0019-compatible diagnostics (`{"type": "error", "line": N, "column": M, "message": "...", "id": "OML###"}`) with deterministic error IDs.
3. **Guide Determinism**: `osiris.guide_start` returns identical recommendations for identical inputs.
4. **Resource URIs**: All schema and snippet payloads resolved through versioned `osiris://` URIs with immutable casing.
5. **Protocol & Payload**: MCP v0.5 and 16 MB payload cap announced during handshake; selftest verifies both.

## Implementation Plan

- **Phase 1 – Scaffold (Hour 0-1)**
  - Generate `osiris/mcp` package skeleton, add server bootstrap using SDK stdio transport, and lock protocol version.
  - Implement minimal CLI `osiris/cli/mcp.py serve` command invoking the server module.
  - Commit golden manifest harness (`tests/mcp/data/tool_manifest.json`) seeded with placeholder entries.
- **Phase 2 – Wire Tools (Hour 1-2)**
  - Implement each tool handler with alias registration and payload limit guard; reuse existing discovery, guide, validator, and persistence modules.
  - Build `resources.py` loaders for schema and catalog URIs; validate file paths.
  - Flesh out `errors.py`, `telemetry.py`, and deterministic diagnostics; update manifest snapshot.
- **Phase 3 – Self-test & Docs (Hour 2-3)**
  - Implement `selftest.py` to hit handshake, every tool, payload limit boundary, and resource fetch under 2 s.
  - Author pytest suites and stdio smoke test; integrate into CI workflow and ensure green run.
  - Update documentation artifacts and release note stub; remove or gate chat entrypoints.

## Acceptance Criteria / Definition of Done

- MCP handshake completes in < 2 seconds via `osiris/cli/mcp.py --selftest`, announcing MCP v0.5 and 16 MB limit.
- Claude Desktop (or scripted equivalent) connects over stdio, lists all tools with aliases, and successfully calls `validate_oml` and `usecases_list`.
- `osiris.validate_oml` returns ADR-0019 diagnostic JSON with deterministic `OML###` IDs and invokes `osiris/core/oml_validator.py`.
- Tool manifest golden test passes, confirming tool names, aliases, resources, and protocol version are unchanged.
- All `tests/mcp/` suites plus project-wide pytest run green in CI; selftest smoke job passes.
- Telemetry events emit per invocation with correlation IDs and no redacted secrets.

## Testing & Validation

- **Selftest**: `osiris/cli/mcp.py --selftest` covers handshake, each tool, alias mapping, payload limit rejection, and resource URIs; exits non-zero on failure.
- **Pytest**: `pytest tests/mcp` executes unit suites, manifest golden, payload boundary, and deterministic diagnostics checks.
- **Smoke Integration**: CI script launches server via stdio, executes scripted Claude Desktop sequence, and verifies deterministic outputs.
- **Staging Validation**: Nightly job runs selftest and sample tool calls against staging telemetry dashboards to ensure events are captured.
- **Telemetry Sample (for Observability)**
  - Example telemetry event emitted during MCP tool execution:

```
{
  "event": "tool_call",
  "tool": "validate_oml",
  "duration_ms": 482,
  "session_id": "sess-5fcb1a",
  "status": "ok",
  "payload_bytes": 1342,
  "timestamp": "2025-10-13T19:52:45.000Z"
}
```

These events are logged to OSIRIS_LOGS_DIR and collected by CI smoke tests to measure performance and determinism. The schema will be extended in 0.5.x for live dashboard integration.

## Risks & Mitigations

- **Tool Registry Drift**: Golden manifest test fails on any deviation; reviewers compare manifest diff against ADR-0036 before merge.
- **Protocol Version Drift**: Handshake asserts MCP v0.5; CI includes check to block unexpected version bumps.
- **Buffer Handling / Payload Backpressure**: Payload guard centralised in `payload_limits.py`; tests simulate 16 MB boundary; telemetry alerts on timeouts.
- **Payload Limit Enforcement Gaps**: Enforce checks at entry, log structured errors, and add regression tests for oversized requests.
- **Resource Availability Regressions**: Selftest and unit tests verify required `osiris://` URIs; release checklist includes resource audit.
- **Telemetry Gaps**: Tests assert event payload shape; staging dashboard alarms on missing events.
- **Client Integration Regressions**: Scripted Claude Desktop handshake runs in CI; failure blocks deployment.
- **Memory Leaks in Long-Running Server**: Incorporate 60-minute soak in staging, monitor memory baseline, and add automated alerts.

## Readiness Summary

Completing this milestone yields a stdio MCP server that handshakes in <2 s using the official SDK, exposes deterministic tools with ADR-0036 aliases, validates OML through the canonical pipeline, and ships with CI-enforced tests plus selftest automation—ready for immediate integration by AI pair agents and human engineers.

This milestone completes the full MCP migration plan defined in ADR-0036.

## Versioning Note

This milestone ships as **Osiris v0.5.0.**

It introduces a breaking interface change (chat interface removed, MCP server as the new entrypoint).

Backward compatibility is intentionally not maintained; downstream tools and scripts must migrate to the new osiris mcp CLI.
