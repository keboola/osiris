# Context

- Repository: osiris_pipeline
- Base branch: main (create new working branch feature/mcp-server-final)
- Goal: Implement the MVP MCP server that replaces chat (ADR-0036). Focus on OML authoring only (no compile/run).
- Determinism: All tools must be stateless, idempotent (same input + same idempotency_key ⇒ same output), and return structured errors.

# MCP SDK Choice

- Use the official Anthropic Model Context Protocol Python SDK (stdio JSON-RPC). If a wrapper lib is unavailable in the repo, implement a thin stdio JSON-RPC bootstrap but keep the server/tool/resource APIs compatible.

---

## 1. Tooling Surface (MVP)

Implement these MCP tools:

1. connections.list
2. connections.doctor
3. components.list
4. discovery.request (returns discovery_id, caches artifacts)
5. usecases.list (loads dummy catalog)
6. oml.schema.get (serves /schemas/oml/v0.1.0.json)
7. oml.validate (wraps osiris/core/oml_validator.py)
8. oml.save (persists draft OML)
9. guide.start (LLM onboarding guidance)
10. memory.capture (long-term memory append with consent + PII redaction)

Multi-turn dialogue and orchestration stay client-side. Server executes single-shot calls only.

---

## 2. Resource Layer (read-only URIs)

Expose via MCP resources.read:

- osiris://mcp/schemas/oml/v0.1.0.json → schemas/oml/v0.1.0.json (immutable)
- osiris://mcp/usecases/dummy_catalog.yaml → resources/usecases/dummy_catalog.yaml (immutable)
- osiris://mcp/discovery/{disc_id}/overview.json|tables.json|samples.json → in-memory TTL cache (24h)
- osiris://mcp/drafts/oml/{session}.json → persisted drafts (append/update)
- osiris://mcp/prompts/oml_authoring_guide.md → resources/prompts/oml_authoring_guide.md (immutable)
- osiris://mcp/memory/sessions/{session}.jsonl → memory/sessions/{session}.jsonl (append-only JSONL; default retention 365d)

All MCP resources are consolidated under the `osiris://mcp/` namespace, resolved by a single resolver mapping to the corresponding folders under `osiris/mcp/data` (read-only) and `osiris/mcp/state` (runtime). This replaces the previous scattered paths and ensures predictable URIs, easier testing, and consistent mempack packaging.

Payload limit: enforce a max size (configurable); paging is documented but deferred.

---

## 3. Error Taxonomy & Shape

Create `osiris/mcp/errors.py` and enforce across all tools:

- Families: SCHEMA/_, SEMANTIC/_, DISCOVERY/_, LINT/_, POLICY/\*
- Shape: `{ "code": str, "path": str|list, "message": str, "suggest": str|null }`

Protocol errors (transport, unknown tool) are left to the MCP SDK.

---

## 4. File / Module Layout (create these)

```
osiris/
  mcp/
    data/                 # read-only resources
      schemas/
      prompts/
      usecases/
    state/                # writable, ephemeral
      discovery/cache/
      drafts/oml/
      memory/sessions/
    tools/
    server.py
    resolver.py
    errors.py
    cache.py
    audit.py
    storage/memory_store.py
```

The resolver.py module enforces namespace boundaries, ensuring that all URIs begin with `osiris://mcp/` and that read-only and mutable resources are separated cleanly between `data/` and `state/`.

---

## 5. Tool API Details

### 5.1 guide.start

- Input:

```json
{
  "intent": "string",
  "known_connections": [...],
  "has_discovery": bool,
  "has_previous_oml": bool,
  "has_error_report": bool
}
```

- Output: objective summary, next step (one of: list_connections, run_discovery, validate_oml, save_oml, capture_memory), minimal input example for that tool, references to relevant URIs.

### 5.2 memory.capture

- Input:

```json
{
  "consent": true,
  "retention_days": 365,
  "session_id": "string",
  "actor_trace": [...],
  "intent": "string",
  "decisions": [...],
  "artifacts": ["uri", ...],
  "oml_uri": "uri|null",
  "error_report": {...}|null,
  "notes": "string"
}
```

- Behavior: enforce `consent:true`, run basic PII redactors (email/phone/IDs), append to JSONL; return memory_uri.
- Errors: POLICY/CONSENT_REQUIRED if consent missing.

Other tools follow the request/response shapes already present in the milestone; keep them small and precise.

---

## 6. Security & Scope

- MVP: single workspace per process, no token auth. Use existing Osiris config/credentials paths.
- discovery.request requires explicit opt-in in config (document).
- Audit: log every tool invocation via audit.py.

---

## 7. Tests (create and pass)

```
tests/mcp/test_server_boot.py
tests/mcp/test_connections_tools.py
tests/mcp/test_discovery_tool.py
tests/mcp/test_components_tool.py
tests/mcp/test_usecases_tool.py
tests/mcp/test_oml_tools.py          # schema.get, validate, save
tests/mcp/test_generate_repair.py    # uses previous_oml + error_report (if applicable)
tests/mcp/test_error_shape.py        # enforces {code,path,message,suggest?}
tests/mcp/test_cache_ttl.py          # discovery TTL expiry
tests/mcp/test_audit_events.py       # audit logs presence
tests/mcp/test_guide_start.py
tests/mcp/test_memory_capture.py
tests/mcp/test_oml_schema_parity.py  # OML jsonschema vs oml_validator parity
```

- Provide fixtures for minimal OML, discovery outputs, and dummy use-cases.

---

## 8. Docs

- `docs/mcp/overview.md` – architecture, tools, resources, examples
- `docs/mcp/tool-reference.md` – per-tool I/O schemas
- `docs/migration/chat-to-mcp.md` – chat intent → MCP tools mapping
- Update ADR cross-refs where needed.

---

## 9. CLI & Dev UX

- `osiris/cli/mcp_entrypoint.py` with a `python -m osiris.cli.mcp_entrypoint` entrypoint.
- Makefile target `mcp-run`.
- Reference client in `osiris/mcp_client/` with simple commands:
  - `osiris mcp connections list`
  - `osiris mcp discovery request --connection <id> --component <id> --samples 5`
  - `osiris mcp oml validate path/to/draft.json`
  - `osiris mcp usecases list`
  - (optionally) `osiris mcp save ...`
- E2E test uses this client.

---

## 10. Definition of Done (must hold)

- All MVP tools implemented, deterministic, stateless, with structured errors.
- `/schemas/oml/v0.1.0.json` served and parity-checked vs `oml_validator`.
- Discovery artifacts cached with TTL; resources readable.
- guide.start suggests next action with minimal request examples.
- memory.capture persists JSONL with consent enforcement + basic redaction.
- Audit events logged for every tool.
- Docs present; migration guide added.
- Legacy chat path emits deprecation warning.
- Align all work with ADR-0036 and new milestone `mcp-final.md`.
- Target Osiris v0.5.0 release for this functionality.

Out of scope (deferred): compile/run, paging, cancel/timeout implementation, policy gating beyond audit, advanced PII/DLP.

---

## 11. Git Workflow (exact steps for Codex)

1. `git checkout main && git pull`
2. `git checkout -b feature/mcp-server-final`
3. Implement all changes above.
4. Run tests: `pytest -q tests/mcp`
5. Open PR to `main` with title: **MCP MVP (server+tools+resources): OML authoring layer**
6. Include brief notes: scope, major modules, how to run server, and known deferrals.

---

To keep determinism: never cache LLM outputs beyond one call; the only cache is discovery artifacts. Any non-deterministic fields (timestamps, UUIDs) must be keyed to `idempotency_key` when producing fingerprints/URIs.

---

To Codex: please proceed with the full implementation as above, keeping the code minimal, tested, and aligned with ADR-0036 and the milestone `mcp-final.md`. If an external MCP SDK causes friction, switch to a minimal stdio JSON-RPC shim but preserve the same public tool/resource contracts.
