# Milestone: ADR-0036 MCP Interface for OML Authoring

## Goal

Deliver the first MCP-based interaction surface for Osiris that fully replaces the chat interface (ADR-0019) for OML authoring. The milestone provides MCP tools for discovery, intent assistance, validation, and persistence of OML v0.1.0 artifacts, enabling Claude Desktop, Codex CLI, Cursor, Gemini Code Assist, and other MCP clients to author pipelines without relying on the deterministic chat state machine.

## Scope

- Implement an `osiris.mcp` server package that exposes the MVP tool set: `connections.list`, `connections.doctor`, `components.list`, `discovery.request`, `oml.schema.get`, `oml.validate`, `oml.save`, `usecases.list`, and `generate_oml`:
  - `generate_oml`: deterministic, stateless synthesis of OML drafts from `intent`, discovery context, and optional use-case hints; can also accept `previous_oml` and `error_report` for iterative repairs.
- Provide JSON schema resource at `/schemas/oml/v0.1.0.json` that mirrors the OML contract enforced in `osiris/core/oml_validator.py`.
- Introduce a dummy OML use-case catalog for early client integration at `resources/usecases/dummy_catalog.yaml`.
- Wrap existing discovery orchestration (`osiris/core/discovery.py`) and OML validation (`osiris/core/oml_validator.py`, `osiris/core/oml_validator.py`) within MCP tool handlers rather than reimplementing logic.
- Restrict scope to OML authoring flows; compilation/execution tooling is explicitly out-of-scope for this milestone.
- Multi-turn reasoning and dialogue occur in the client; the MCP server executes stateless, idempotent tool calls.
- Provide developer documentation, migration notes, and acceptance tests that cover MCP tool behaviour end-to-end.

## Deliverables

- **Code**
  - `osiris/mcp/server.py`: MCP server bootstrap, lifecycle management, and tool registration.
  - `osiris/mcp/tools/__init__.py` plus per-tool modules (`connections.py`, `components.py`, `discovery.py`, `oml.py`, `usecases.py`) implementing the MVP tool handlers.
  - `osiris/mcp/resources/schema_loader.py`: helper to serve `/schemas/oml/v0.1.0.json` and other resource descriptors.
  - `schemas/oml/v0.1.0.json`: canonical JSON schema for OML v0.1.0 (generated from the existing schema guard contract).
  - `resources/usecases/dummy_catalog.yaml`: sample catalog of OML authoring scenarios referenced by `usecases.list`.
  - `osiris/cli/mcp_entrypoint.py`: CLI shim to launch the MCP server for local developers and integration tests.
  - osiris/mcp_client/: lightweight reference client (Python) used by tests and CLI.
  - osiris/mcp/errors.py: shared error model and taxonomy constants (SCHEMA, SEMANTIC, DISCOVERY, LINT, POLICY).
  - osiris/mcp/cache.py: simple in-memory TTL cache for discovery results (used by resource layer).
  - osiris/mcp/audit.py: lightweight event logger emitting mcp.tool.invoke events.
  - `osiris/mcp/tools/generate.py`: handler implementing the generate_oml tool.
  - `osiris/mcp/prompts/generate_oml.md`: system prompt template used internally by the tool.
- **Tests**
  - `tests/mcp/test_connections_tools.py`: unit coverage for `connections.list` and `connections.doctor` (mocking connectors to ensure diagnostics are surfaced correctly).
  - `tests/mcp/test_discovery_tool.py`: verifies `discovery.request` reuses existing discovery orchestrators and emits session identifiers.
  - `tests/mcp/test_oml_tools.py`: validates `oml.schema.get`, `oml.validate`, and `oml.save` enforce the schema and persistence rules.
  - `tests/mcp/test_usecases_tool.py`: ensures `usecases.list` loads and filters the dummy catalog.
  - `tests/mcp/test_server_boot.py`: smoke test for MCP server registration and tool manifest shape.
  - tests/mcp/test_client_e2e.py: end-to-end test verifying client-server interactions.
  - tests/mcp/test_error_shape.py: ensures all tool responses follow {code, path, message, suggest?} schema.
  - tests/mcp/test_cache_ttl.py: verifies discovery results expire after TTL.
  - tests/mcp/test_audit_events.py: ensures tool invocations emit audit logs.
  - `tests/mcp/test_generate_tool.py`: ensures deterministic output for identical inputs and validation via oml.validate.
  - `tests/mcp/test_generate_repair.py`: validates iterative repair using previous_oml and error_report inputs.
- **Documentation**
  - `docs/mcp/overview.md`: overview of MCP architecture, tool catalogue, request/response shapes, and guidance for client integrators.
  - `docs/mcp/tool-reference.md`: detailed per-tool specification including input/output schemas and examples.
  - `docs/migration/chat-to-mcp.md`: migration guide mapping ADR-0019 chat flows to MCP tool calls for UI and automation consumers.
  - Update `docs/adr/0036-mcp-interface.md` cross-references to note milestone plan and documentation links.
- **Operational Assets**
  - Update `Makefile` target or add `scripts/run_mcp_server.sh` to simplify local execution.
  - Add MCP server configuration stanza to `.osiris/config.example.yaml` for environment configuration.

### generate_oml Tool API

Example request JSON:

```json
{
  "intent": "Create a pipeline to extract user data and join with purchase history",
  "usecase_id": "dummy_usecase_1",
  "discovery_uris": ["discovery/results/session123"],
  "schema_uri": "/schemas/oml/v0.1.0.json",
  "previous_oml": null,
  "error_report": null,
  "constraints": {
    "max_steps": 5,
    "allow_external_sources": false
  },
  "idempotency_key": "unique-request-12345"
}
```

Example response JSON (success):

```json
{
  "ok": true,
  "oml": {
    "pipeline": {
      "steps": [
        {
          "id": "step1",
          "type": "extract",
          "source": "user_data"
        },
        {
          "id": "step2",
          "type": "join",
          "inputs": ["step1", "purchase_history"]
        }
      ]
    }
  },
  "oml_draft_uri": "/oml/drafts/session123",
  "fingerprint": "abc123fingerprint",
  "warnings": []
}
```

Example response JSON (failure):

```json
{
  "ok": false,
  "errors": [
    {
      "code": "SCHEMA/INVALID",
      "path": ["pipeline", "steps", 1, "type"],
      "message": "Step type 'joinx' is not recognized",
      "suggest": "Use one of the supported step types: extract, join, transform"
    }
  ]
}
```

## Dependencies

- ADR-0036 acceptance and sign-off.
- Existing discovery infrastructure (`osiris/core/discovery.py`, connectors in `osiris/connectors/`) must remain stable; any pending refactors should land before MCP tool integration.
- Schema contract from ADR-0014 and validation logic in `osiris/core/oml_validator.py` must be up-to-date to accurately mint `/schemas/oml/v0.1.0.json`.
- Requires minimal runtime configuration parity with the current chat experience (credentials, component registry, memory store); configuration docs must be available before MCP server rollout.

## Risks

- **API Instability**: MCP tool request/response shapes may change if upstream clients (Claude, Cursor, etc.) require additional metadata; mitigate with beta release notes and versioned tool manifests.
- **Schema Drift**: Manually curated `/schemas/oml/v0.1.0.json` could diverge from code if not generated/validated as part of continuous integration; enforce through tests ensuring the JSON schema matches the guard.
- **Adoption Lag**: Downstream clients may take longer to migrate; provide chat-to-MCP compatibility adapters and clear migration guidance.
- **Operational Load**: MCP server introduces new deployment footprint; ensure observability hooks (logging, metrics) are in place to detect regressions early.
- Multi-turn orchestration and SQL correction remain client-side; the server only handles single-step synthesis and validation.

## Versioning and Compatibility

- MCP tools follow SemVer with the package versioning scheme `osiris.mcp@0.y`, enabling fast iteration during the MVP phase.
- The OML authoring version `v0.1.0` corresponds directly to the schema version served at `/schemas/oml/v0.1.0.json`.
- Each MCP tool declares its version explicitly in its manifest to support compatibility checks and graceful client upgrades.

## Error Taxonomy

- Standardized error code families are defined as follows:
  - `SCHEMA/*`: errors related to JSON schema validation failures.
  - `SEMANTIC/*`: semantic validation errors beyond schema conformance.
  - `DISCOVERY/*`: errors arising during discovery orchestration.
  - `LINT/*`: style and best-practice warnings or errors.
  - `POLICY/*`: errors related to permissions, configuration, or policy violations.
- All MCP tool responses must use a consistent error shape: `{code, path, message, suggest?}`.
- Integration tests will verify coverage of this error taxonomy across all tools.

## Resource Mapping

| Resource URI                   | Local File Path                         | MIME Type            | Retention / TTL                 |
| ------------------------------ | --------------------------------------- | -------------------- | ------------------------------- |
| `/schemas/oml/v0.1.0.json`     | `schemas/oml/v0.1.0.json`               | `application/json`   | Immutable, permanent            |
| `/usecases/dummy_catalog.yaml` | `resources/usecases/dummy_catalog.yaml` | `application/x-yaml` | Immutable, permanent            |
| `/discovery/results/{session}` | In-memory cache                         | `application/json`   | 24 hours                        |
| `/oml/drafts/{session}`        | Persistent storage (session logs)       | `application/json`   | Unlimited until explicit delete |

For MVP: implement only in-memory cache with TTL; paging and size enforcement are documented but deferred to a later milestone.

## Security and Permissions

- Default policy allows read-only tools unrestricted access.
- Discovery tool requires explicit opt-in to run due to its resource-intensive nature.
- Sensitive sample fields may be masked using regex patterns to protect PII and confidential information.
- All MCP tool invocations are logged as `mcp.tool.invoke` events for audit and monitoring purposes.

For MVP: only audit logging via mcp.tool.invoke events is implemented. Policy gating and masking are deferred for a later milestone.

## Deprecation Plan: Chat Interface Sunset

- The deterministic chat interface (ADR-0019) will be phased out in a controlled manner:
  - **v0.4**: Mark chat interface as deprecated; emit warnings on usage.
  - **v0.5**: Remove chat end-to-end tests; maintain a thin compatibility layer redirecting calls to MCP tools.
  - **v0.6**: Fully remove chat state machine and related assets.
- Migration reference mapping:

| Chat Intent            | MCP Tool                                     |
| ---------------------- | -------------------------------------------- |
| OML authoring          | `oml.schema.get`, `oml.validate`, `oml.save` |
| Discovery requests     | `discovery.request`                          |
| Connection diagnostics | `connections.list`, `connections.doctor`     |
| Use case browsing      | `usecases.list`                              |

## Reference MCP Client and CLI

- A lightweight Python-based reference client is provided to run the Osiris MCP server locally without requiring Claude Desktop.
- Implemented under the module `osiris/mcp_client/`, it offers a helper API for interacting with MCP tools.
- CLI commands include:
  - `osiris mcp connections list`
  - `osiris mcp discovery request`
  - `osiris mcp oml validate`
  - `osiris mcp usecases list`
- This client serves as a self-test tool, CI harness, and developer example for integrating MCP.

## Acceptance Criteria

- All MVP tools respond according to documented schemas when invoked via an MCP-compliant client stub (automated by integration tests).
- `oml.schema.get` serves the canonical `/schemas/oml/v0.1.0.json` and matches validator expectations (validated in `tests/mcp/test_oml_tools.py`).
- `oml.validate` reuses existing validation logic and produces identical pass/fail results compared to the chat pipeline for a shared fixture set.
- `oml.save` persists generated OML artifacts to the same storage path used by chat (`osiris/core/session_logging.py`) and associates them with MCP session IDs.
- Documentation and migration notes are present, reviewed, and linked from ADR-0036 to guide client adoption.
- Legacy chat integration tests for OML authoring are updated or replaced to cover MCP pathways, with the chat state machine marked as deprecated in release notes.

## Additional Acceptance Criteria

- Version consistency is enforced between MCP tool manifests and the OML schema version.
- JSON Schema validation and code-based validator produce matching results, verified by parity tests.
- Maximum payload size limits are enforced; paging is documented but deferred to post-MVP.
- Discovery tool documents cancel and timeout semantics; implementation is deferred (stretch goal).
- Deprecation notices are emitted by the chat interface path to inform users of migration timelines.

- Deprecation warning emitted when chat interface is used (required for MVP).
- Payload size limit checks enforced (required for MVP).
- Cancel and timeout semantics for discovery documented but not implemented (stretch goal).

- `generate_oml` returns consistent OML drafts for identical inputs and idempotency_key.
- Generated OML passes `oml.validate` or returns structured validation errors without hidden retries.

## Definition of Done (clarified)

The milestone is complete when the MCP server exposes all MVP tools with unified error formatting, validated OML schema, basic caching, audit logging, and chat deprecation warnings in place. Paging, cancel, masking, and policy gating are explicitly deferred to post-MVP iterations.

## Timeline

- **Phase 1 – Foundations**
  - Scaffold `osiris/mcp/server.py`, register empty tool handlers, and add CLI entrypoint.
  - Land `/schemas/oml/v0.1.0.json` and schema loader with CI guard comparing against `oml_validator` contract.
  - Draft `docs/mcp/overview.md` structure and circulate for feedback.
- **Phase 2 – Tool Implementation**
  - Implement `connections.list`, `connections.doctor`, and `components.list` with unit coverage.
  - Implement `discovery.request`, reusing `osiris/core/discovery.py`; add integration fixture verifying session tags.
  - Publish dummy use-case catalog and wire `usecases.list` tool.
- **Phase 3 – OML Authoring Flow**
  - Complete `oml.schema.get`, `oml.validate`, and `oml.save`; ensure persistence wiring and schema validation tests pass.
  - Finalise documentation (tool reference, migration guide) and update ADR-0036 cross-links.
  - Execute end-to-end MCP authoring test, update release notes, and obtain stakeholder sign-off to begin client migration.

## Frequently Asked Questions (FAQ)

**1. Which MCP SDK or library should be used?**

Use the official [Anthropic MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk), which implements the standard MCP protocol and supports stdio transport, resources, and tools.
If compatibility issues arise, fallback to a minimal in-house JSON-RPC implementation that exposes the same tool registration and resource mechanisms.

**2. Where is `osiris/core/oml_validator.py` located and how should it be used?**

The file `osiris/core/oml_validator.py` already exists in the repository and is the canonical validator for OML.
It replaces the former chat-based `conversational_agent.py` logic.
MCP tools such as `oml.validate` and schema generation (`/schemas/oml/v0.1.0.json`) must reference this module as the single source of truth.

**3. How is session ID management handled?**

Session IDs are generated by the MCP server whenever a discovery or OML authoring session begins (e.g., by `discovery.request`).
Format: `disc_<timestamp>_<uuid4-short>`.
Clients simply pass these IDs forward (e.g., to `generate_oml`) but do not create them manually.
The server caches discovery results in-memory with a 24-hour TTL.

**4. How should `generate_oml` be implemented for the MVP?**

`generate_oml` invokes a single LLM call (Claude preferred, OpenAI as fallback) using the prompt in `osiris/mcp/prompts/generate_oml.md`.
It must produce deterministic results: the same input and `idempotency_key` yield the same OML draft.
No conversational state or retries occur server-side—multi-turn reasoning happens in the client.

**5. How are protocol vs. application errors distinguished?**

Protocol-level errors (invalid JSON, unknown tool, transport issues) are handled directly by the MCP SDK.
Application-level errors (OML validation, discovery failures, semantic checks) follow the structured format `{code, path, message, suggest?}` and are emitted via the shared error model in `osiris/mcp/errors.py`.
