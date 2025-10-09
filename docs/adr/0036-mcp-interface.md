# ADR-0036: Replace Osiris Chat With MCP Interface

## Status

Proposed (supersedes ADR-0019 when accepted)

## Context

Osiris currently exposes "osiris chat" as the primary interaction pattern for synthesising OML pipelines. ADR-0019 rigidly defines a deterministic state machine to ensure the chat experience produces valid OML v0.1.0 and finishes discovery-to-generation flows without interminable clarification loops. The approach has worked for the web UI but presents mounting friction:

- **Client fragmentation**: Teams are adopting MCP-native surfaces such as Claude Desktop, Claude Code, Cursor, Gemini Code Assist, and Codex CLI. Each client implements MCP tooling, not bespoke websocket chat protocols.
- **Prompt drift and duplicated logic**: Every bespoke client (web, CLI, IDE) re-implements portions of the chat flow, resulting in divergent prompts and inconsistent enforcement of ADR-0019 guarantees.
- **Limited automation**: Automation pipelines and CI bots require direct tool access (generate, validate, compile, run) instead of conversational turn-management.
- **Missing interoperability**: MCP allows structured tools, resources, and prompts to be shared across heterogeneous LLM hosts. Staying on the legacy chat model isolates Osiris from an emerging ecosystem standard.

We must preserve ADR-0019's contract (OML schema guard, single regeneration attempt, logged state transitions) while modernising the transport and orchestration model so that any MCP client can interact with Osiris' capabilities.

### Resource Layer

The MCP interface exposes a lightweight "resource layer" that allows clients to access key Osiris artifacts via simple, structured URIs. Instead of requiring heavy JSON payloads or custom RPCs for each artifact, Osiris publishes essential resources—such as discovery results, OML schemas, OML drafts, and use-case snippets—at well-defined URIs. This enables efficient, language-agnostic access for both humans and tools.

The following resource URIs are supported:

- `osiris://discovery/<disc_id>/overview.json`
- `osiris://discovery/<disc_id>/tables.json`
- `osiris://oml/schema/v0.1.0.json`
- `osiris://oml/drafts/<oml_id>.json`
- `osiris://usecases/<id>/oml_snippet_v1.json`

These are read-only resources, accessed via the MCP `resources.read` method, and are backed by files maintained in the Osiris workspace.

Notably, `osiris://oml/schema/v0.1.0.json` will provide a formal JSON Schema for OML, derived from the Python-based validator in `osiris/core/oml_validator.py`. This allows IDEs and external MCP clients to validate OML documents without invoking Osiris code directly.

Internally, Osiris will host these resources under paths such as `/schemas/oml/v0.1.0.json` and map them to the above resource URIs through the MCP server.

## Decision

Expose Osiris' OML authoring capabilities through a first-class Model Context Protocol (MCP) server and deprecate the bespoke chat state machine. MCP becomes the single public interface for interactive and automated clients.

### MCP Server Responsibilities

- **Tool surface**: Provide typed tools that encapsulate the existing lifecycle:

  - `osiris.introspect_sources` → wraps discovery, returns metadata and optional samples.
  - `osiris.generate_oml` → synthesises OML drafts deterministically from user intent, discovery context, and use-case hints.
  - `osiris.validate_oml` → runs schema guard using the Python-based validator (`osiris/core/oml_validator.py`), returns diagnostics aligned with ADR-0019 regeneration hints.
  - `osiris.save_oml` → saves OML drafts.
  - `osiris.usecases_list` → enumerates business scenarios.

- **Prompt packages**: Ship canonical system / tool prompts as MCP resources so every client loads identical instructions, eliminating prompt drift.
- **Session contract**: Maintain deterministic sequencing rules from ADR-0019 by embedding them in tool preconditions:
  - Discovery tools tag their outputs with a session identifier.
  - `generate_oml` requires either a discovery summary resource or an explicit override flag to skip discovery.
  - Regeneration is bounded by server-side policy (one retry) regardless of client behaviour.
- **Authentication & tenancy**: MVP scope is single workspace per process, no token-based auth; requests inherit workspace scoping so that MCP tools operate against the correct registries, secrets, and memory store entries.

### Post-MVP Extensions

Future milestones will introduce additional tools such as osiris.compile_pipeline and osiris.execute_pipeline once the authoring layer is stable.

### Decommissioning Legacy Chat

- Mark the websocket/chat controller as deprecated and maintain read-only access during migration.
- Route web UI, CLI, and future IDE extensions through the MCP server via thin adapters.
- Retire bespoke prompt management once all clients consume MCP prompt resources.

## Consequences

### Positive

- **Unified integration surface**: Any MCP-compatible client gains immediate parity with the existing chat workflow without re-implementing the state machine.
- **Consistent guardrails**: Server-enforced sequencing and validation keep ADR-0019 guarantees intact even if the client is non-compliant.
- **Lower maintenance overhead**: Tool semantics live in one place, removing duplicated prompt logic across adapters.
- **Automation-friendly**: Pipelines, CI, and agent loops can invoke the same tools programmatically without conversational scaffolding.
- **Future-proofing**: Alignment with MCP positions Osiris within the broader agent ecosystem, easing collaboration with third-party hosts.

### Negative

- **Client rework**: Existing chat-oriented UI flows must adopt MCP tool calls and adapt to streaming/tool invocation patterns.
- **Protocol surface area**: MCP introduces additional complexity (tool schemas, resource negotiation) that the team must maintain.
- **Migration risk**: Bugs in the MCP server could temporarily break all clients if not phased carefully.

## Adoption Plan

1. **Create MCP server module**: Implement tool handlers backed by the current conversational services (intent parsing, discovery, OML synthesis, validation, compilation, execution).
2. **Mirror ADR-0019 telemetry**: Emit the same structured events via MCP resources/webhooks to preserve observability.
3. **Adapter rollout**:
   - Update Codex CLI to use MCP transport first (lowest UX impact).
   - Ship web UI updates that replace chat websocket calls with MCP tool invocations.
   - Coordinate with internal IDE extensions (Cursor/Gemini/Claude) to swap in the MCP endpoint.
4. **Deprecate chat API**: Announce timeline, monitor MCP adoption metrics, then remove chat-specific code paths once parity is confirmed.
5. **Update documentation**: Revise developer onboarding, SDK examples, and ADR-0019 references to point at the MCP interface; mark ADR-0019 as superseded.

## Non-Goals

- Redesigning the underlying OML compiler, scheduler, or execution semantics (covered by ADR-0015, ADR-0031).
- Introducing multi-turn agent loops beyond the bounded regeneration already defined in ADR-0019/ADR-0030.
- Providing generic MCP bridges for non-OML tooling (out of scope for this change).

## Related ADRs

- ADR-0019: Chat State Machine and OML Synthesis (superseded)
- ADR-0030: Agentic OML Generation (informs future agent loop enhancements)
- ADR-0013: Chat Retry Policy (policy reused as MCP regeneration guard)
- ADR-0014: OML v0.1.0 Scope and Schema (contract enforced by MCP tools)
- ADR-0035: Compiler Secret Detection (continues to gate compilation tool)

## Open Questions

- What MCP resource taxonomy best encodes discovery outputs and validation diagnostics for reuse across clients?
- Do we need per-client capability negotiation to support partial tool sets (e.g., read-only users)?
- How do we expose long-running compile/run progress within MCP (streaming events vs. polling resource)?

## Decision Drivers

- Rapid client proliferation that already speaks MCP
- Desire to keep OML generation guardrails centralised and deterministic
- Need for automation-friendly access paths without conversational overhead
- Reuse of existing validation, compilation, and execution services with minimal refactor
