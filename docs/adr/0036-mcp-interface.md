# ADR-0036: Adopt Clean MCP Interface via Official SDK for Osiris

🧩 **Updated for MCP v0.5.0 implementation parity (October 2025)**

## Status

Proposed (supersedes ADR-0019 when accepted)

## Context

Osiris currently exposes OML pipeline authoring capabilities through a bespoke chat state machine defined by ADR-0019. While effective, this approach introduces fragmentation, duplicated logic, and limited automation potential. The Model Context Protocol (MCP) has emerged as a robust, standardized interface for LLM tool integration, enabling structured, language-agnostic communication with minimal overhead.

To modernize Osiris and unify client interactions, we propose adopting MCP as the single public interface for OML authoring and related workflows. This eliminates the legacy chat model and leverages the official `modelcontextprotocol` Python SDK to implement a clean, maintainable MCP server.

## Decision

We will replace the legacy chat interface with a first-class MCP server implemented exclusively via the official `modelcontextprotocol` Python SDK. This SDK-based server will pin the MCP protocol version, define a fixed tool surface, and enforce safety behaviors consistently.

### MCP Server Implementation

- **Protocol Version**: MCP v0.5 (config reference), actual protocol version negotiated by SDK during handshake (typically `2025-06-18` for modern clients like Claude Desktop v0.7.0+)
- **SDK**: Use the official `modelcontextprotocol` Python SDK (v1.2.1+) as the sole implementation. No stdio or hybrid paths.
- **Tool Naming**: All tool names use underscore-separated format (`connections_list`, `discovery_request`) to comply with MCP client validation pattern `^[a-zA-Z0-9_-]{1,64}$`. Legacy `osiris.*` prefixed names and dot-notation names are supported via backward compatibility aliases.
- **Tool Surface** (10 tools total):
  - **Connection Management**:
    - `connections_list` (aliases: `osiris.connections.list`, `connections.list`): List configured database connections from `osiris_connections.yaml`.
    - `connections_doctor` (aliases: `osiris.connections.doctor`, `connections.doctor`): Diagnose connection configuration issues.
  - **Component Management**:
    - `components_list` (aliases: `osiris.components.list`, `components.list`): List available pipeline components from registry.
  - **Discovery**:
    - `discovery_request` (aliases: `osiris.introspect_sources`, `discovery.request`): Discover database schema with optional sampling and 24-hour caching.
  - **OML Operations**:
    - `oml_schema_get` (aliases: `osiris.oml.schema.get`, `oml.schema.get`): Retrieve OML v0.1.0 JSON Schema.
    - `oml_validate` (aliases: `osiris.validate_oml`, `oml.validate`): Validate OML pipeline with ADR-0019-compatible diagnostics.
    - `oml_save` (aliases: `osiris.save_oml`, `oml.save`): Persist OML pipeline drafts to session-scoped storage.
  - **Guidance**:
    - `guide_start` (aliases: `osiris.guide_start`, `guide.start`): Provide guided next steps for OML authoring.
  - **Memory**:
    - `memory_capture` (aliases: `osiris.memory.capture`, `memory.capture`): Capture session memory with consent and PII redaction.
  - **Use Cases**:
    - `usecases_list` (aliases: `osiris.usecases.list`, `usecases.list`): Enumerate OML use case templates.
- **Safety and Limits**:
  - Payload size capped at 16 MB (`payload_limit_mb = 16`).
  - Memory capture requires explicit user consent with redaction enforced.
- **Environment Integration**:
  - `OSIRIS_HOME` environment variable controls base directory for all stateful data
  - Defaults to `<repo_root>/testing_env` if not set, enabling zero-config local development
  - Connection files searched in `OSIRIS_HOME` first, then CWD, enabling multi-environment deployment
- **Observability**:
  - Emit structured telemetry events mirroring ADR-0019 for discovery, validation, and regeneration.
  - Integrate selftest endpoints to verify MCP server health and tool responsiveness.
- **Resource Layer**:
  - Expose Osiris artifacts as MCP resources at canonical `osiris://mcp/` URIs.
  - Provide a formal JSON Schema for OML v0.1.0 to enable client-side validation.

### CLI-First Adapter Architecture

The MCP server employs a CLI-first adapter approach, where MCP server tools delegate to the existing Osiris CLI for operations that require environment variables or secrets. This design leverages a CLI Bridge component that routes commands such as `osiris connections list` and `osiris oml validate` internally, ensuring that all sensitive information and environment-specific configurations remain managed by the CLI environment.

This architecture guarantees that no secrets are handled directly by the MCP server, preserving parity and consistency with the CLI's behavior. By reusing the established CLI logic for core operations, the MCP server maintains a clean separation of concerns while providing a unified interface for clients via the official SDK.

### CLI Integration

The MCP server is exposed via a multi-command CLI interface:

- **Primary Command**: `osiris mcp run` starts the server via stdio transport
- **Self-Test**: `osiris mcp run --selftest` validates server health in <2 seconds
- **Debug Mode**: `osiris mcp run --debug` enables verbose logging to stderr
- **Configuration Discovery**: `osiris mcp clients` outputs auto-detected Claude Desktop config with resolved paths
- **Tool Inspection**: `osiris mcp tools` lists all registered tools for debugging
- **Help Safety**: `osiris mcp --help` displays help **without starting the server** (prevents accidental activation)

This design ensures `--help` is safe to invoke and provides additional utility commands for setup and debugging.

### Deprecation of Legacy Chat

- The websocket/chat controller is deprecated and will be removed in a future release.
- All clients must migrate to MCP tool calls via the official SDK interface.
- Documentation and onboarding materials will be updated to reflect MCP as the exclusive integration point.
- No support for legacy or hybrid chat/MCP paths will remain.

## Consequences

### Positive

- **Unified, official SDK-based interface**: Simplifies client integration and server maintenance.
- **Consistent safety and protocol guarantees**: Enforced centrally by the MCP server.
- **Improved automation and tooling**: Enables pipelines, CI, and agents to interact programmatically without conversational overhead.
- **Enhanced observability and reliability**: Structured telemetry and selftests ensure operational confidence.
- **Future-proofing**: Aligns Osiris with the broader MCP ecosystem and industry standards.
- **Environment flexibility**: OSIRIS_HOME integration supports production deployments and multi-environment configurations.
- **Enhanced tool discovery**: Additional connection, component, and schema tools complete the API surface.

### Negative

- **Client migration effort**: Existing chat-based clients must be updated to use MCP SDK calls.
- **Increased responsibility for MCP server maintenance**: Requires ongoing upkeep of SDK integration and protocol compliance.
- **Removal of chat fallback**: No legacy fallback path may impact clients not yet migrated.

## Adoption Plan

1. Implement MCP server using the official `modelcontextprotocol` Python SDK, pinning protocol version and tool schema.
2. Mirror ADR-0019 telemetry via MCP events and add selftest endpoints.
3. Update clients (CLI, web UI, IDE extensions) to consume MCP tool APIs exclusively.
4. Deprecate and remove websocket/chat controller after MCP adoption verification.
5. Revise documentation to emphasize MCP as the sole integration method and mark ADR-0019 as superseded. See [`docs/mcp/overview.md`](../mcp/overview.md) and [`docs/migration/chat-to-mcp.md`](../migration/chat-to-mcp.md) for the maintained runbook.

## Non-Goals

- Redesign of the OML compiler, scheduler, or execution semantics (covered by ADR-0015, ADR-0031).
- Introduction of multi-turn agent loops beyond the bounded regeneration defined in ADR-0019/ADR-0030.
- Support for non-OML tooling or alternative MCP implementations.

## Related ADRs

- ADR-0019: Chat State Machine and OML Synthesis (superseded)
- ADR-0030: Agentic OML Generation (informs future agent loop enhancements)
- ADR-0013: Chat Retry Policy (policy reused as MCP regeneration guard)
- ADR-0014: OML v0.1.0 Scope and Schema (contract enforced by MCP tools)
- ADR-0035: Compiler Secret Detection (continues to gate compilation tool)

## Open Questions

- What additional observability metrics and selftest coverage are needed for robust MCP server operation?
- How should client capability negotiation be handled to support partial tool sets or restricted users?
- What is the best approach to expose long-running compile/run progress within MCP (streaming events vs. polling resources)?

## Decision Drivers

- Desire for a clean, maintainable MCP server implemented with the official SDK.
- Need to pin protocol version and tool surface to ensure stability and compatibility.
- Requirement for consistent safety, observability, and selftest support.
- Alignment with MCP ecosystem and elimination of legacy chat complexity.
