Context
• Repository: osiris_pipeline
• Base branch: feature/mcp-server (create new working branch feature/mcp-server-codex)
• Goal: Implement the MVP MCP server that replaces chat (ADR-0036). Focus on OML authoring only (no compile/run).
• Determinism: All tools must be stateless, idempotent (same input + same idempotency_key ⇒ same output), and return structured errors.

MCP SDK Choice
• Use the official Anthropic Model Context Protocol Python SDK (stdio JSON-RPC). If a wrapper lib is unavailable in the repo, implement a thin stdio JSON-RPC bootstrap but keep the server/tool/resource APIs compatible.

⸻

1. Tooling Surface (MVP)

Implement these MCP tools: 1. connections.list 2. connections.doctor 3. components.list 4. discovery.request (returns discovery_id, caches artifacts) 5. usecases.list (loads dummy catalog) 6. oml.schema.get (serves /schemas/oml/v0.1.0.json) 7. oml.validate (wraps osiris/core/oml_validator.py) 8. oml.save (persists draft OML) 9. generate_oml (stateless synthesis, see API below) 10. guide.start (LLM onboarding guidance) 11. memory.capture (long-term memory append with consent + PII redaction)

Multi-turn dialogue and orchestration stay client-side. Server executes single-shot calls only.

⸻

2. Resource Layer (read-only URIs)

Expose via MCP resources.read:
• /schemas/oml/v0.1.0.json → schemas/oml/v0.1.0.json (immutable)
• /usecases/dummy_catalog.yaml → resources/usecases/dummy_catalog.yaml (immutable)
• /discovery/results/{disc_id}/overview.json|tables.json|samples.json → in-memory TTL cache (24h)
• /oml/drafts/{session}.json → persisted drafts (append/update)
• /prompts/oml_authoring_guide.md → resources/prompts/oml_authoring_guide.md (immutable)
• /memory/sessions/{session}.jsonl → memory/sessions/{session}.jsonl (append-only JSONL; default retention 365d)

Payload limit: enforce a max size (configurable); paging is documented but deferred.

⸻

3. Error Taxonomy & Shape

Create osiris/mcp/errors.py and enforce across all tools:
• Families: SCHEMA/_, SEMANTIC/_, DISCOVERY/_, LINT/_, POLICY/\*
• Shape: { "code": str, "path": str|list, "message": str, "suggest": str|null }

Protocol errors (transport, unknown tool) are left to the MCP SDK.

⸻

4. File / Module Layout (create these)

```
osiris/
  mcp/
    server.py
    errors.py
    cache.py
    audit.py
    resources/
      schema_loader.py
    storage/
      memory_store.py
    prompts/
      generate_oml.md
      oml_authoring_guide.md
    tools/
      __init__.py
      connections.py
      components.py
      discovery.py
      usecases.py
      oml.py          # schema.get, validate, save
      generate.py     # generate_oml implementation
      guide.py        # guide.start
      memory.py       # memory.capture
schemas/
  oml/v0.1.0.json
resources/
  usecases/dummy_catalog.yaml
  prompts/oml_authoring_guide.md
osiris/cli/
  mcp_entrypoint.py
```

Notes
• server.py: stdio bootstrap, tool registration, resource resolver, manifest with per-tool version.
• cache.py: simple TTL LRU for discovery artifacts.
• audit.py: emit_tool_event(tool, status, ms, bytes_in, bytes_out) for mcp.tool.invoke.
• memory_store.py: append-only JSONL writer + retention trimming.

⸻

5. Tool API Details

5.1 generate_oml (core)

Request

```
{
  "intent": "string",
  "usecase_id": "string|null",
  "discovery_uris": [".../overview.json", ".../tables.json"],
  "schema_uri": "/schemas/oml/v0.1.0.json",
  "previous_oml": { "oml_version":"0.1.0","name":"...","steps":[...] } | null,
  "error_report": { "errors":[{"code":"...","path":"...","message":"..."}] } | null,
  "constraints": { "naming":"kebab-case","modes":["read","transform","write"] },
  "idempotency_key": "uuid"
}
```

Behavior
• Single LLM call (prefer Claude; fallback configurable).
• Prompt from osiris/mcp/prompts/generate_oml.md.
• Deterministic: hash fingerprint from (idempotency_key, intent, discovery_hash, usecase_id, previous_oml?, error_report?, constraints?).
• No hidden retries. If validation would fail, return {ok:false, errors:[…]}.

Response (success)

```
{
  "ok": true,
  "oml": { "oml_version":"0.1.0","name":"...","steps":[...] },
  "oml_draft_uri": "/oml/drafts/<session>.json",
  "fingerprint": "sha256:...",
  "warnings": []
}
```

Response (failure)

```
{ "ok": false, "errors":[ { "code":"SCHEMA/...","path":"$.steps[1]","message":"...","suggest":"..." } ] }
```

5.2 guide.start
• Input: { "intent": "string", "known_connections": [...], "has_discovery": bool, "has_previous_oml": bool, "has_error_report": bool }
• Output: objective summary, next step (one of: list_connections,run_discovery,generate_oml,validate_oml,save_oml,capture_memory), minimal input example for that tool, references to relevant URIs.

5.3 memory.capture
• Input: { "consent": true, "retention_days": 365, "session_id": "string", "actor_trace": [...], "intent": "string", "decisions": [...], "artifacts": ["uri", ...], "oml_uri": "uri|null", "error_report": {...}|null, "notes":"string" }
• Behavior: enforce consent:true, run basic PII redactors (email/phone/IDs), append to JSONL; return memory_uri.
• Errors: POLICY/CONSENT_REQUIRED if consent missing.

Other tools follow the request/response shapes already present in the milestone; keep them small and precise.

⸻

6. Security & Scope
   • MVP: single workspace per process, no token auth. Use existing Osiris config/credentials paths.
   • discovery.request requires explicit opt-in in config (document).
   • Audit: log every tool invocation via audit.py.

⸻

7. Tests (create and pass)

```
tests/mcp/test_server_boot.py
tests/mcp/test_connections_tools.py
tests/mcp/test_discovery_tool.py
tests/mcp/test_components_tool.py
tests/mcp/test_usecases_tool.py
tests/mcp/test_oml_tools.py          # schema.get, validate, save
tests/mcp/test_generate_tool.py      # determinism + validate pass
tests/mcp/test_generate_repair.py    # uses previous_oml + error_report
tests/mcp/test_error_shape.py        # enforces {code,path,message,suggest?}
tests/mcp/test_cache_ttl.py          # discovery TTL expiry
tests/mcp/test_audit_events.py       # audit logs presence
tests/mcp/test_guide_start.py
tests/mcp/test_memory_capture.py
tests/mcp/test_oml_schema_parity.py  # OML jsonschema vs oml_validator parity
```

    •	Provide fixtures for minimal OML, discovery outputs, and dummy use-cases.

⸻

8. Docs
   • docs/mcp/overview.md – architecture, tools, resources, examples
   • docs/mcp/tool-reference.md – per-tool I/O schemas
   • docs/migration/chat-to-mcp.md – chat intent → MCP tools mapping
   • Update ADR cross-refs where needed.

⸻

9. CLI & Dev UX
   • osiris/cli/mcp_entrypoint.py with a python -m osiris.cli.mcp_entrypoint entrypoint.
   • Makefile target mcp-run.
   • Reference client in osiris/mcp_client/ with simple commands:
   • osiris mcp connections list
   • osiris mcp discovery request --connection <id> --component <id> --samples 5
   • osiris mcp oml validate path/to/draft.json
   • osiris mcp usecases list
   • (optionally) osiris mcp generate --intent "..."
   • E2E test uses this client.

⸻

10. Definition of Done (must hold)
    • All MVP tools implemented, deterministic, stateless, with structured errors.
    • /schemas/oml/v0.1.0.json served and parity-checked vs oml_validator.
    • Discovery artifacts cached with TTL; resources readable.
    • generate_oml produces valid OML or returns structured errors (no hidden retries).
    • guide.start suggests next action with minimal request examples.
    • memory.capture persists JSONL with consent enforcement + basic redaction.
    • Audit events logged for every tool.
    • Docs present; migration guide added.
    • Legacy chat path emits deprecation warning.

Out of scope (deferred): compile/run, paging, cancel/timeout implementation, policy gating beyond audit, advanced PII/DLP.

⸻

11. Git Workflow (exact steps for Codex)
    1.  git checkout feature/mcp-server && git pull
    2.  git checkout -b feature/mcp-server-codex
    3.  Implement all changes above.
    4.  Run tests: pytest -q tests/mcp
    5.  Open PR to feature/mcp-server with title: MCP MVP (server+tools+resources): OML authoring layer
    6.  Include brief notes: scope, major modules, how to run server, and known deferrals.

To keep determinism: never cache LLM outputs beyond one call; the only cache is discovery artifacts. Any non-deterministic fields (timestamps, UUIDs) must be keyed to idempotency_key when producing fingerprints/URIs.

⸻

To Codex: please proceed with the full implementation as above, keeping the code minimal, tested, and aligned with ADR-0036 and the milestone. If an external MCP SDK causes friction, switch to a minimal stdio JSON-RPC shim but preserve the same public tool/resource contracts.
