# Product Strategy Clarification (Read First)

This plan intentionally separates near-term stabilization of the MVP from the longer-term evolution beyond pure data pipelines. Read this before the questions below.

## Near-term (focus now – MVP hardening):
	•	Stabilize the current conversational pipeline generator.
	•	Introduce Component Specs that publish config schema + capabilities (minimal JSON Schema, light constraints).
	•	Export a small LLM context from those specs to eliminate schema mismatch and reduce hallucinations.
	•	Ship osiris compile → canonical Run Manifest → osiris run (local + e2b) with JSONL logs & artifacts.

## Later (after MVP is reliable):
	•	Expand component capabilities (discovery, ad-hoc analytics, in-memory movement) as discrete iterations.
	•	Add light multi-agent plumbing only if needed (envelope/bus/DLQ). Start in-proc; externalize later.
	•	Extend from data pipelines toward process-oriented workflows incrementally (notifications, tickets, approvals) – not in the first passes.

## Backward compatibility & migration:
	•	Keep the current YAML shape; treat OML as “Osiris YAML dialect” (no new filetype). Existing YAMLs remain valid; the compiler normalizes them into the manifest.
	•	Provide osiris upgrade command for schema renames/defaults in future minor versions (idempotent transforms).

## Non-Goals for v0.1.x:
	•	No distributed event bus, no external queueing infra, no heavy DSL for constraints.
	•	No attempt to replace Airflow/Prefect; we focus on deterministic generation + simple execution.

## Security & secrets (MVP posture):
	• Secrets are **referenced, not inlined** in OML (use `connection_ref` like `@supabase`).
	• **Spec-driven redaction (new):** each component spec declares a `secrets` map (JSON Pointers to secret-bearing fields if ever present in inline config) and an optional `redaction` policy. The runtime uses the **registry-provided secret map** to mask logs/artifacts. Static regex fallback remains; **.env-driven masking is deferred** until specs exist for all components.
	• Resolution: runners read secrets from `--secrets-file` or ENV at run start; long-running sessions re-read on retry.
	• Manifests/logs/artifacts must never contain secret values; only `connection_ref` or masked placeholders.

## Performance & caching:
	•	Cache component specs and built LLM context on disk; invalidate on spec mtime change.
	•	Compiler and validator are pure functions; memoize per pipeline hash.

## Why not full multi-agent now?
	•	The envelope/bus/DLQ design is future-proofing. We start with direct calls in a single process and append-only artifacts. If/when concurrency and isolation become necessary, we’ll enable the same contracts over a bus.



# Osiris — Implementation Brief (for Claude Code Max)

## Executive Intent

We are evolving Osiris into a contract-backed pipeline system with:
	1.	Component Registry (components are self-describing: config schema, capabilities, constraints, examples),
	2.	LLM Context Builder feeding the chat agent with machine-readable context to generate valid OML,
	3.	osiris run MVP that compiles OML → canonical Run Manifest → executes locally and via e2b.

This plan must align with the existing repo layout under osiris/ (CLI, core, connectors) and keep our pitch deck’s guarantees: one YAML, one manifest, audit-ready logs & artifacts.  ￼

⸻

## Ground Truth Inputs & Constraints
	•	Language: Python (primary).
	•	Current entrypoint: osiris.py + osiris/cli/ (we can add subcommands under osiris/cli/main.py).
	•	Repo layout: see tree.txt (use existing osiris/core, osiris/connectors/mysql|supabase).  ￼
	•	Component specs: none yet (we will introduce them).
	•	Secrets: currently .env — we will add a light secrets loader supporting ENV and --secrets-file.
	•	e2b: use Python SDK for remote execution (minimal adapter).
	•	Docs: none — we’ll scaffold MkDocs + mike later.

⸻

## Milestones Overview (Do in order)

### M1 — Component Registry (specs + capabilities)

Goal: Every component ships a spec card describing how to configure and use it.

#### Deliverables
	•	Schema for spec cards: components/spec.schema.json
	•	**Add secret semantics to spec schema:** support `secrets` (array of JSON Pointers into `configSchema` for secret-bearing fields) and optional `redaction` { strategy: "fixed"|"hash", mask: "***" }.
	•	Two spec cards: components/mysql.table/spec.yaml, components/supabase.table/spec.yaml
	•	Loader + validator: osiris/components/registry.py
	•	CLI:
	•	osiris components list
	•	osiris components spec <type> --format=json|yaml
	• Registry exposes `get_secret_map(component_type)` for runtime redaction.

File Layout
    components/
      spec.schema.json
      mysql.table/
        spec.yaml
      supabase.table/
        spec.yaml
    osiris/components/
      __init__.py
      registry.py
    osiris/cli/
      components_cmd.py

Spec Schema (sample)
    {
      "$schema": "https://json-schema.org/draft/2020-12/schema",
      "title": "Osiris ComponentSpec",
      "type": "object",
      "required": ["name","version","modes","capabilities","configSchema"],
      "properties": {
        "apiVersion": { "type": "string", "const": "osiris.v1" },
        "kind": { "type": "string", "const": "ComponentSpec" },
        "name": { "type": "string" },
        "title": { "type": "string" },
        "description": { "type": "string" },
        "version": { "type": "string" },
        "modes": { "type": "array", "items": { "enum": ["read","write","transform"] } },
        "capabilities": { "type": "array", "items": { "type": "string" } },
        "configSchema": { "type": "object" },
        "constraints": { "type": "array", "items": { "type": "object" } },
        "examples": { "type": "array", "items": { "type": "object" } },
        "secrets": { "type": "array", "items": { "type": "string", "description": "JSON Pointer to secret-bearing field in configSchema (if present)" } },
        "redaction": { "type": "object", "properties": { "strategy": { "type": "string", "enum": ["fixed","hash"] }, "mask": { "type": "string", "default": "***" } }, "additionalProperties": false }
      }
    }

supabase.table/spec.yaml (minimal example)
    apiVersion: osiris.v1
    kind: ComponentSpec
    name: supabase.table
    version: "0.1.0"
    modes: ["read","write"]
    capabilities: ["discovery","in_memory_move"]
    configSchema:
      type: object
      required: ["connection","mode","options"]
      properties:
        connection: { type: "string" } # "@supabase"
        mode: { type: "string", enum: ["read","write"] }
        options:
          type: object
          properties:
            schema: { type: "string" }
            table:  { type: "string" }
            write_mode: { type: "string", enum: ["append","merge"], default: "append" }
            merge_keys: { type: "array", items: { type: "string" } }
    constraints:
      - when: { "mode": "write", "options.write_mode": "merge" }
        must: { "options.merge_keys": { "minItems": 1 } }
        error: "merge_keys required for write_mode=merge"
    examples:
      - title: "Read orders"
        oml: { type: supabase.table, connection: "@supabase", mode: read, options: { schema: public, table: orders } }
    secrets:
      - "/connection/url"  # example if inline connection is ever allowed (not used in MVP)

#### Acceptance (DoD)
	•	osiris components list prints both components with their capabilities.
	•	Validating an OML step against supabase.table surfaces constraint errors (e.g., missing merge_keys).
	•	Unit tests cover positive/negative validation paths.

#### Acceptance (DoD) — Secrets & Redaction
	• Registry returns a secret map for components (even if empty for MVP connectors).
	• Log/event emission consults the registry’s secret map; values at those paths are masked.
	• Unit test verifies that when a fake inline secret is present, logs and artifacts contain masks, not plaintext.

⸻

### M2 — Chat Context Builder (LLM-first, but deterministic)

Goal: Export a small, machine-readable context from the registry so the conversational agent generates valid OML on first try.

#### Deliverables
	•	Context exporter: osiris/prompts/build_context.py
	•	CLI: osiris prompts build-context --out .osiris_prompts/context.json
	•	Include: component names, capabilities, reduced config schema (required fields, enums, defaults), and ≤2 examples per component.
	•	Wire into chat:
	•	Update osiris/core/prompt_manager.py to load the exported context.
	•	In osiris/cli/chat.py, validate the OML returned by the agent using ComponentRegistry.validate, and show actionable errors.

#### Acceptance
	•	3 guided chat prompts (Supabase→Supabase append/merge, MySQL→Supabase merge) produce valid OML without manual fixes.
	•	Invalid fields are blocked (agent cannot use fields not present in configSchema).

⸻

### M3 — osiris compile + osiris run (MVP)

Goal: Deterministic execution: OML → compiled per-step configs → canonical Run Manifest → run local / e2b.

#### Deliverables
	•	OML v0.0.1 (minimal):
	•	version, name, sources[0], sinks[0], optional params.
	•	Compiler: osiris/compile.py
	•	osiris compile pipeline.yaml --out cfg/ → emits:
	•	cfg/<step>.json (component-specific config from OML)
	•	cfg/manifest.yaml (canonical execution plan)
	•	Runner:
	•	osiris/run/runner.py — orchestrates steps
	•	Engines: osiris/run/engines/local.py, osiris/run/engines/e2b.py
	•	CLI: osiris run <pipeline.yaml> [--engine=local|e2b] [--secrets-file ...] [--param k=v]
	•	Secrets (MVP):
	•	Loader: `osiris/secrets.py` with precedence `--secrets-file` > ENV; provides resolved connection objects by `connection_ref`.
	•	No secrets in manifest/logs/artifacts; manifest only carries `connection_ref`.
	•	**Redaction:** runner uses the registry secret map + global fallback to mask any accidental inline secrets in step configs or logs.
	•	Tests: golden manifest asserts absence of secret values; log snapshot asserts masked placeholders.
	•	Telemetry/Artifacts:
	•	JSONL logs with run_id, step, rows_read/written.
	•	metrics.json (counts, duration), manifest.yaml as canonical state.

Run Manifest (example)
    apiVersion: osiris.v1
    kind: RunManifest
    pipeline: "mysql_to_supabase"
    steps:
      - id: "src"
        cfg: "cfg/src.json"
        produces: "tabular"
      - id: "dst"
        cfg: "cfg/dst.json"
        consumes: "tabular"
    execution:
      engine: "local"   # or "e2b"
      params: { chunk_size: 5000 }

#### Acceptance
	•	osiris compile generates cfg/*.json + cfg/manifest.yaml.
	•	osiris run (local) copies data (append/merge) using existing osiris/connectors/mysql|supabase.
	•	osiris run --engine=e2b uploads cfg/ + manifest.yaml, executes in sandbox via Python SDK, streams logs.
	•	Exit codes are correct; artifacts present.

⸻

### M4 — Light Multi-Agent Plumbing (keep it simple)

Goal: Minimal, debuggable coordination — no orchestration spaghetti.

#### Deliverables
	•	Message Envelope (osiris/core/envelope.py):
    @dataclass
    class Envelope:
        id: str
        correlation_id: str
        timestamp: str
        source: Literal["chat","generator","validator","runner"]
        type: Literal["INTENT","OML_DRAFT","VALIDATION_REPORT","RUN_MANIFEST","RUN_RESULT","ERROR"]
        schema_ref: str
        payload: dict
        context: dict  # e.g., {"user": "...", "session": "..."}

	•	In-proc Event Bus (osiris/core/bus.py):
	•	Topics: intent, oml.generated, validation.reports, run.events
	•	FIFO per correlation_id, retries with backoff
	•	DLQ folder: var/dlq/<topic>/<envelope-id>.json
	•	Supervisor (osiris/core/supervisor.py):
	•	Assign run_id, set correlation_id, state machine: NEW→GENERATED→VALIDATED→RUNNING→SUCCEEDED|FAILED
	•	CLI:
	•	osiris runs view <run_id> — show state + paths to artifacts

#### Acceptance
	•	Failing validator or runner produces DLQ item with the full envelope (replayable).
	•	runs view displays status and artifact links.

⸻

### M5 — Docs-as-Code (scaffold)

Goal: Avoid a “single giant doc”; adopt Diátaxis and auto-generate reference from component specs.

#### Deliverables
	•	MkDocs Material + mike (versioning): mkdocs.yml, docs/ structure:
    docs/
      index.md
      tutorials/quickstart.md
      concepts/{process-as-code.md, contracts-and-manifests.md}
      how-to/{run-locally.md, run-in-e2b.md}
      reference/cli/{osiris-components.md, osiris-compile.md, osiris-run.md}
      reference/components/  # GENERATED from spec.yaml
      adr/0001-canonical-run-manifest.md

	•	Generators:
	•	tools/gen_component_docs.py → renders reference/components/*.md from components/*/spec.yaml
	•	CI:
	•	build docs on PR, link-check, mike deploy on tag

#### Acceptance
	•	Each component has a generated reference page.
	•	One ADR (Canonical Run Manifest) merged.
	•	Docs build passes in CI.

## Integration Points with Existing Code
	•	Reuse osiris/cli/main.py to register new subcommands (components, prompts build-context, compile, run, runs view). Repo already has cli/chat.py, cli/main.py; follow the established CLI pattern.  ￼
	•	Reuse osiris/connectors/mysql|supabase for runner engines (batch read/write).
	•	osiris/core/prompt_manager.py and osiris/core/llm_adapter.py will load the exported context.

⸻

## Tests & CI (minimum)
	•	Unit: registry validation (positive/negative), compiler manifest content, runner write modes (append/merge).
	•	Integration: docker-compose for MySQL + Supabase; seed → run → assert row counts.
	•	CLI E2E: compile + run (local + e2b mock).
	•	Docs: build + link check.
	•	Security: redaction tests (spec-declared pointers masked in logs/artifacts; no accidental leaks).


## PR Checklist (to paste into CONTRIBUTING.md or docs/README.md)

Use this checklist for every PR. It enforces our core guarantees (contract-backed execution, canonical manifest, audit-ready outputs) and keeps the repo tidy.  ￼

### Scope & Intent
	•	PR title is imperative and scoped (e.g., “Add Component Registry spec loader”).
	•	Linked issue(s) / roadmap item(s) referenced (e.g., Fixes #123).
	•	If this PR changes public contracts (OML fields, CLI flags, component config), an ADR is included/updated.

### Component Registry / OML
	•	New/changed components ship a components/<type>/spec.yaml that validates against components/spec.schema.json.
	•	osiris components list/spec reflect the change.
	•	OML samples added/updated in docs/examples or examples/.

### Canonical Build & Run
	•	osiris compile produces a Run Manifest that is the canonical state for execution. (No secrets inside; only connection_ref.)  ￼
	•	osiris run works locally and (if applicable) via e2b; exit codes are meaningful.
	•	Logs are JSONL with run_id, step, duration_ms, and counts (rows read/written).
	•	Artifacts (manifest.yaml, run.log.jsonl, metrics.json) are written to predictable locations.

### Secrets & Safety
	•	No secrets in code, logs, or manifest. Use ENV and/or --secrets-file.
	•	SQL/exec safety preserved (see docs/sql-safety.md).  ￼

### Chat / LLM Context
	•	If components/capabilities changed: LLM context exporter updated (osiris prompts build-context) and system prompt reads new fields.
	•	Post-generation validation enforced before any run.

### Tests
	•	Unit tests added/updated (registry validation + compiler + runner logic).
	•	If connectors are affected: integration test (docker-compose or stub) covers happy path + a failure case.
	•	CLI E2E: compile + run (local; e2b mocked if needed).

### Docs-as-Code
	•	Relevant docs updated under Diátaxis structure (concepts/, how-to/, reference/, tutorials/).
	•	Component reference generated from spec.yaml (don’t hand-edit generated files).
	•	ADR added/updated for architectural decisions (e.g., message envelope, manifest).

### CI / Hygiene
	•	All CI checks green (tests, docs build, link check).
	•	Changelog note in CHANGELOG.md (user-facing summary).
	•	No dead code / debug prints; type hints where feasible.

## Pull Request Template (save as .github/PULL_REQUEST_TEMPLATE.md)

## Summary
<!-- What does this PR change? Keep it concise and imperative. -->

## Why
<!-- Short rationale. If changing contracts/architecture, link the ADR. -->
<!-- Our deck commits us to contract-backed execution + canonical manifest + audit-ready outputs. -->

## Scope
- [ ] Feature
- [ ] Bug fix
- [ ] Docs
- [ ] Refactor
- [ ] Test/CI
- [ ] Other: ______

## Linked Issues
- Fixes #

## Changes
- **Components/Registry:** <!-- e.g., add supabase.table capability; new spec fields -->
- **OML/Compile/Run:** <!-- e.g., manifest shape, runner behavior -->
- **LLM/Chat:** <!-- e.g., context exporter, validation messages -->
- **Secrets/Safety:** <!-- e.g., no secrets in manifest/logs -->
- **Docs:** <!-- pages touched; generated refs updated -->
- **CI/Tests:** <!-- coverage, new checks -->

## Screenshots / Artifacts
- Logs sample (JSONL): 
    {“ts”:”…”,“agent”:“runner”,“run_id”:”…”,“step”:“dst”,“rows_written”:123}
- Manifest excerpt:
    apiVersion: osiris.v1
    kind: RunManifest
    pipeline: "..."
    steps:
      - id: "src"
        cfg: "cfg/src.json"
    execution: { engine: "local" }
    

## Checklist

### Contracts & Canonical State
	•	If public contracts changed: ADR added/updated and linked.
	•	osiris compile emits canonical Run Manifest (no secrets).
	•	osiris run OK locally; e2b path OK or mocked.

### Components & OML
	•	components/<type>/spec.yaml validates against components/spec.schema.json.
	•	osiris components list/spec output verified.
	•	OML examples updated.

### LLM Context
	•	Context exporter (osiris prompts build-context) updated if needed.
	•	Post-generation validation enforced.

### Security & Safety
	•	No secrets in code/logs/manifest; ENV/--secrets-file used.
	•	SQL safety preserved (docs/sql-safety.md).

### Tests & CI
	•	Unit tests cover new logic and edge cases.
	•	Integration/CLI tests updated; CI green.
	•	Docs build + link check pass; generated docs re-built.

### Changelog
	•	Entry added to CHANGELOG.md with user-facing summary.

### ADRs
	•	N/A
	•	Added: docs/adr/XXXX-title.md
	•	Updated: docs/adr/XXXX-title.md

## Notes on the “Why”

A short why belongs directly in the PR (the Why section). A more detailed rationale should go into an ADR (Architecture Decision Record). This way you maintain development speed while also keeping a record of decisions.


This aligns with the pitch deck’s message: from chaos to contract-backed execution; YAML/Manifest as the contract of record; audit-ready artifacts and logs.


## ADR Template (docs/adr/template.md)

# Title
Date: YYYY-MM-DD  
Status: Proposed / Accepted / Deprecated

## Context
(What problem are we solving?)

## Decision
(The decision we took.)

## Consequences
(Implications, trade-offs, future concerns.)


## CI Workflow Skeleton (.github/workflows/ci.yml)

name: CI
on: [push, pull_request]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pytest
      - run: mkdocs build --strict
      - run: markdown-link-check docs/**/*.md

⸻

## Critical Questions for Codex (Deep Architecture Review)

The "Product Strategy Clarification" above addresses many concerns by emphasizing MVP-first approach and backwards compatibility. These questions stress-test the remaining design decisions while acknowledging this improved scope:

### Author Clarifications (Live Notes)

**On “current discovery cache shape”:**
- *Meaning:* This asks what **keys and fields** we currently use to index and validate the **discovery cache** (the stored results of schema/table discovery). If the cache key is too coarse (e.g., only the `connection_ref`), then a later request for a **different schema/table/columns/options** may incorrectly reuse stale discovery results and cause mismatches.
- *What should be in the cache key (M0 decision):*
  - `component_type` (e.g., `mysql.table`),
  - `component_version` (from the spec card),
  - `connection_ref` (e.g., `@supabase`),
  - **input options fingerprint** (stable hash of `schema`, `table`, selected columns, filters, sampling settings),
  - **spec fingerprint** (hash of the component’s exported config schema for discovery). 
- *Invalidation rule:* On each discovery call, compute fingerprints. If either the **input options** or the **spec fingerprint** differs from what’s stored, **invalidate and refresh** the cache entry. Store the fingerprints alongside the cached payload for cheap equality checks.

**On LLM tooling cost vs simplicity:**
- *Decision (MVP):* Start **simple** with a **small static context blob** per session (exported from Component Specs) embedded in the system prompt. Accept slightly higher token costs initially; prefer shipping reliability over early micro‑optimizations.
- *Scope of the blob:* Only include the **active connectors** we use in MVP (e.g., `mysql.table`, `supabase.table`), and only **minimal fields**: names, requireds, enums, defaults, plus ≤2 tiny examples per component. No prose.
- *Upgrade path (later):* Add optional **on‑demand spec retrieval** (tool/function call) to fetch a single component’s schema when needed, and/or compress context further if token usage or latency exceed thresholds.

---

### **MVP Scope & Sequencing**
1. **Is M1-M3 truly minimal?** Even with MVP focus, we're still building component registry + context builder + compiler + runner. Could we achieve the core goal (fixing context mismatch) with just M2's context builder and basic validation, deferring M1's full registry?

2. **Component Registry necessity**: The constraint system (`when/must/error`) feels sophisticated for MVP. Why not start with simple JSON Schema validation using existing libraries (Pydantic/Cerberus) and add custom constraints later if needed?

3. **Compile step justification**: The OML → cfg/*.json → manifest.yaml compilation adds abstraction layers. Could we start with direct YAML → execution and add compilation when we actually need multi-step orchestration?

### **Core Problem Resolution**
4. **Context mismatch root cause**: The original issue was cached movie database conflicting with Supabase requests. Does M2's context builder definitively solve this, or could we fix it faster with targeted cache invalidation and schema checking?

5. **LLM validation timing**: Plan validates OML after LLM generation. Wouldn't it be better to feed component constraints directly into the LLM prompt to prevent invalid generation rather than catching errors after?

6. **Backwards compatibility reality**: Even with "existing YAMLs remain valid," won't new validation rules potentially break existing pipelines that worked before? How do we handle this transition gracefully?

### **Performance & User Experience**
7. **Registry overhead baseline**: What's current chat response time? Component discovery, context building, and validation on each request could add significant latency. Are we optimizing for correctness at the expense of conversational flow?

8. **Context builder token usage**: Exporting component specs to LLM context will consume tokens. With multiple components, this could approach prompt limits. How do we balance completeness vs. token efficiency?

9. **Error message quality**: Complex component validation can produce cryptic JSON Schema errors. How do we ensure validation failures translate to actionable user guidance?

### **Architecture Future-proofing**
10. **Multi-agent envelope design influence**: Even though M4 starts "in-proc," designing message envelopes upfront might over-engineer current simple functions. Could this premature abstraction constrain simpler solutions?

11. **Component capability enforcement**: Specs declare capabilities like "discovery" and "in_memory_move" but how do we actually enforce these at runtime? What prevents components from exceeding their declared capabilities?

12. **Registry extensibility**: As we add more connectors (BigQuery, Snowflake, etc.), will the component spec schema remain stable, or will we need breaking changes that invalidate existing specs?

### **Testing & Risk Management**
13. **Integration testing strategy**: How do we test the full pipeline (registry → context builder → LLM → validator → compiler → runner) without creating brittle tests that break on minor changes?

14. **Rollback plan**: If the new validation system causes widespread pipeline failures, what's our rollback strategy? Can we quickly disable component validation and fall back to current behavior?

15. **User migration communication**: How do we communicate changes to users whose pipelines might start failing due to new validation rules? What's our deprecation and migration timeline?

### **Alternative Implementation Paths**
16. **Incremental validation approach**: Instead of full component registry, could we start with:
    - Basic connection string validation
    - Required field checking  
    - Enum value validation
    - Add sophisticated constraints only after these prove insufficient?

17. **Hybrid compilation strategy**: Rather than always compiling to manifest, could we:
    - Execute simple pipelines directly (current behavior)
    - Only use compilation for complex multi-step workflows
    - This preserves current performance while enabling future complexity?

### **Success Metrics & Validation**
18. **MVP success criteria**: How do we measure if this MVP actually solves the original problem? What metrics prove the component registry reduces LLM hallucinations and context mismatches?

19. **User adoption path**: Will existing users naturally adopt new CLI commands (`osiris compile`, `osiris run`), or do we risk fracturing the user base between old and new approaches?

20. **Performance regression bounds**: What's the acceptable performance degradation for improved correctness? 2x slower? 5x? At what point do we prioritize speed over validation?

### **Recommended Minimal Alternative**
Given the MVP clarification, consider this even lighter first step:
```
Week 1-2: Context Mismatch Fix
- Add schema fingerprinting to cached discovery
- Invalidate cache when request schema differs from cached schema  
- This solves the original problem with minimal code changes

Week 3-4: Basic Validation  
- Add simple JSON Schema validation for connection configs
- Validate required fields (connection, table, mode) before execution
- Clear error messages for common mistakes

Week 5-8: Enhanced Context (if needed)
- Only if basic validation proves insufficient
- Simple context builder without full component registry
- Focus on preventing common LLM mistakes rather than comprehensive validation
```


**Core question: Should we first solve the original context mismatch with targeted fixes, then evaluate if the full component registry is still necessary?**


## Answers to Critical Questions (Author Responses)

1) Is M1–M3 truly minimal?
   • We will split M1 into M1a (JSON Schema only: required, enums, defaults) and M1b (constraints later). M2 (context builder) consumes M1a; M3 (compile/run) validates against M1a. This tightens scope while keeping determinism.

2) Do we need a custom constraint system now?
   • No. MVP uses pure JSON Schema (Draft 2020‑12). If/when gaps appear, we add a tiny rule adapter later (M1b). 

3) Why keep a compile step now?
   • It yields a canonical Run Manifest for reproducibility, audit, and e2b packaging. We’ll still allow a direct path: `osiris run pipeline.yaml` implicitly compiles and executes, but always emits the manifest as the record.

4) Does context builder fix the cache mismatch?
   • We address it in two layers: M0 hot‑fix (schema/options fingerprint in discovery cache; invalidate on change) + M2 (context constrains generation to valid fields). Together, they remove both stale‑cache and hallucination classes of errors.

5) Validation timing (prompt vs post‑gen)?
   • Both. Prompt‑time constraints reduce bad generations; post‑gen schema validation returns deterministic, actionable errors. Belt and suspenders.

6) Backwards compatibility when adding validation?
   • Default `--mode=warn` in v0.1.x; `--mode=strict` is opt‑in. Provide `osiris upgrade` (idempotent transforms) and a Migration Guide. Flip defaults only after a grace period.

7) Registry overhead for chat latency?
   • Cache a minimal, compiled context on disk; rebuild on spec mtime change. Lazy‑load only referenced components per turn. Target additional overhead ≤150 ms p50.

8) Token usage of context?
   • Keep context tiny: names, requireds, enums, defaults, ≤2 micro‑examples per component. No prose. Optional on‑demand spec retrieval can arrive later if usage exceeds budget.

9) JSON Schema errors are cryptic—how to fix?
   • Friendly error mapper: map jsonpath → human label; add Why/How‑to‑fix; link to component doc. Maintain a small error playbook for common mistakes.

10) Is the envelope premature?
   • We use the Envelope only as a logging/contract struct in‑proc; no external bus yet. This future‑proofs without over‑engineering runtime today.

11) Enforcing capabilities at runtime?
   • Runner checks `modes`/`capabilities` before invoking a component. Missing capability → fast fail with clear error. Unit tests include a deliberate violation case.

12) Will the spec schema survive new warehouses (BQ/Snowflake)?
   • Yes—via versioned `spec_version` and `x‑extensions` for vendor specifics. Deprecations go through ADR + `osiris upgrade`.

13) Integration testing without brittleness?
   • Pin on artifacts, not dialog: mock LLM; assert `compile → manifest → run` against golden manifests. Use docker‑compose for 1–2 end‑to‑end flows (happy + fail).

14) Rollback if validation breaks users?
   • Feature flag `OSIRIS_VALIDATION=off` (or CLI `--no-validate`) to bypass; default warn‑mode; keep last known compiler available to revert fast.

15) Communicating migration?
   • CHANGELOG badges, one Migration Guide page, CLI warnings with short tips + link to docs. Announce grace windows before strict mode.

16) Incremental validation instead of full registry?
   • Agreed: that’s exactly M1a—required/enums/defaults now; extra rules later only if needed.

17) Hybrid compilation strategy?
   • Agreed: direct execution for simple 1→1 while still emitting the manifest; use explicit compile for multi‑step.

18) MVP success metrics?
   • First‑try validity rate (+50–70% vs baseline), median time‑to‑first‑successful‑run, number of manual edits post‑chat (down), schema‑mismatch incidents (down), chat/compile latency & token budget (within SLOs).

19) Will new CLI fracture users?
   • Keep backward‑compatible aliases and show simple path first. Advanced docs expose manifest explicitly; existing workflows keep working.

20) Acceptable performance regression?
   • SLOs: chat p50 ≤3s E2E (incl. validation); validation+compile overhead ≤350 ms p50; simple run throughput within ≤2× of current baseline. If exceeded, profile and tune (cache, context size) before adding features.

21) Decision on the “Recommended Minimal Alternative”
   • Adopt its spirit as sequencing: 
     – M0 now: discovery cache fingerprinting + invalidation; basic JSON Schema for connections.
     – M1a: component spec cards with schema only + friendly error mapper.
     – M2: minimal context exporter; post‑gen validation enforced.
     – M3: compile→manifest→run (manifest always emitted, even for simple runs).
     – M1b later: only add targeted semantic rules where JSON Schema is insufficient.


## Implementation Notes (Concrete Slices)

### M0 — Discovery Cache Fingerprinting (hot‑fix)
- **Goal:** eliminate stale discovery reuse when input options or spec change.
- **Fingerprint inputs:** component_type, component_version, connection_ref, canonicalized input options, spec fingerprint.
- **Canonicalization rule:** JSON dump with stable key order + no whitespace; then SHA‑256.

Pseudocode (Python):

    def canonical_json(obj) -> str:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"))
    
    def sha256_hex(s: str) -> str:
        return hashlib.sha256(s.encode("utf-8")).hexdigest()
    
    def input_options_fingerprint(options: dict) -> str:
        return sha256_hex(canonical_json(options))
    
    def spec_fingerprint(spec_schema: dict) -> str:
        return sha256_hex(canonical_json(spec_schema))
    
    def discovery_cache_key(component_type: str, component_version: str, connection_ref: str, options_fp: str, spec_fp: str) -> str:
        parts = [component_type, component_version, connection_ref, options_fp, spec_fp]
        return ":".join(parts)

Cache entry shape:

    {
      "key": "mysql.table:0.1.0:@src:ab12..:cd34..",
      "created_at": "2025-09-01T10:00:00Z",
      "ttl_seconds": 86400,
      "inputs": {
        "component_type": "mysql.table",
        "component_version": "0.1.0",
        "connection_ref": "@src",
        "options_fp": "ab12..",
        "spec_fp": "cd34.."
      },
      "payload": { "columns": [...], "pk": ["id"], "row_count_sample": 10000 }
    }

On lookup:
- Recompute options_fp and spec_fp; if key mismatch or expired TTL → refresh.
- Store alongside payload for cheap equality checks.

### M1a — Friendly Error Mapper
- Map raw JSON Schema errors to actionable messages.
- Table‑driven mapping examples:

    {
      "path": "options.write_mode",
      "rule": "enum",
      "why": "Allowed values: append, merge",
      "fix": "Set options.write_mode to 'append' or 'merge'",
      "example": "options: { write_mode: merge, merge_keys: [id] }"
    }

Implementation sketch:
- Collect `ValidationError` objects; for each, compute jsonpath and look up mapping; fall back to generic message.
- Return structured report with `why`, `fix`, `example` and a short link to docs.

### Compiler Idempotence Contract
- Input OML + secrets references → deterministic manifest + cfg/*.json for the same inputs.
- Manifest must be stable across machines (only absolute paths differ if at all).
- Add golden‑file tests: serialize manifest and compare to baseline (allow list of non‑deterministic fields to ignore).

---

## CLI Flags & Environment Matrix (MVP)

- `osiris compile <pipeline.yaml> --out cfg/ --mode warn|strict|off`
- `osiris run <pipeline.yaml> --engine local|e2b --secrets-file secrets.yaml --param k=v --mode warn|strict|off`
- `osiris components list|spec <type> --format json|yaml`
- `osiris prompts build-context --out .osiris_prompts/context.json`

Environment variables (precedence: CLI flag > ENV > defaults):
- `OSIRIS_VALIDATION` = `warn|strict|off`
- `OSIRIS_E2B_API_KEY` (used by e2b engine)
- `OSIRIS_LOG_LEVEL` = `INFO|DEBUG`
- OSIRIS_REDACTION_STRATEGY = fixed|hash  (overrides spec `redaction.strategy` when set)

Exit codes:
- 0 success; 2 validation error; 3 compile error; 4 run error; 5 config/secrets missing.

---

## Secrets Handling (Examples)

Minimal `secrets.yaml` (checked in as example only; real files ignored via .gitignore):

    connections:
      @mysql:
        url: mysql+pymysql://user:pass@host:3306/db
      @supabase:
        url: postgres://user:pass@db.supabase.co:5432/postgres

ENV alternative (12‑factor):

    OSIRIS_CONN__MYSQL__URL=mysql+pymysql://user:pass@host:3306/db
    OSIRIS_CONN__SUPABASE__URL=postgres://user:pass@db.supabase.co:5432/postgres

Rules:
- Secrets never appear in manifest/logs; only `connection_ref` is present.
- Loader precedence: `--secrets-file` > ENV; fail with code 5 if missing.

---

## Run Manifest — Minimal JSON Schema (for reference)

    {
      "$schema": "https://json-schema.org/draft/2020-12/schema",
      "title": "Osiris RunManifest",
      "type": "object",
      "required": ["apiVersion","kind","pipeline","steps","execution"],
      "properties": {
        "apiVersion": { "type": "string", "const": "osiris.v1" },
        "kind": { "type": "string", "const": "RunManifest" },
        "pipeline": { "type": "string" },
        "steps": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["id","cfg"],
            "properties": {
              "id": { "type": "string" },
              "cfg": { "type": "string" },
              "produces": { "type": "string" },
              "consumes": { "type": "string" }
            }
          },
          "minItems": 1
        },
        "execution": {
          "type": "object",
          "required": ["engine"],
          "properties": {
            "engine": { "type": "string", "enum": ["local","e2b"] },
            "params": { "type": "object" }
          }
        }
      }
    }

---

## e2b Engine Adapter — Minimal Contract

Interface (Python):

    class E2BEngine:
        def __init__(self, api_key: str):
            ...
        def run(self, manifest_path: str, cfg_dir: str, env: dict) -> int:
            """Uploads cfg_dir + manifest, executes the job, streams logs.
            Returns process exit code."""

Behavior:
- Resolve API key from `OSIRIS_E2B_API_KEY` if not passed explicitly.
- Upload only cfg/ and manifest; secrets are injected from environment inside the sandbox.
- Stream logs line‑by‑line; prefix with `agent=runner engine=e2b`.

---

## Operational SLOs & Telemetry (MVP)

SLOs:
- Chat p50 ≤ 3s E2E (including validation)
- Validation + compile overhead ≤ 350 ms p50
- Simple run throughput within ≤ 2× of current baseline

Log fields (JSONL):

    {
      "ts": "2025-09-01T10:23:45.123Z",
      "run_id": "r_...",
      "correlation_id": "c_...",
      "agent": "runner",
      "engine": "local|e2b",
      "step": "src|dst",
      "event": "start|end|metrics|error",
      "rows_read": 10000,
      "rows_written": 10000,
      "duration_ms": 1234,
      "error": null
    }

Metrics file (`metrics.json`): aggregated counters, durations, exit code, component versions.

---

## Versioning & Deprecation Policy

- **SemVer** for OML and spec schemas: MAJOR = breaking, MINOR = additive, PATCH = fixes.
- Deprecations carry warnings for ≥1 MINOR release before removal.
- `osiris upgrade` performs idempotent transforms; print a diff summary.

---

## Security & Compliance (MVP Posture)

- PII‑safe logs: no secrets, no raw data payloads, no row samples by default.
- Optional redaction hook: component may emit field name lists to redact; runner enforces redaction in logs.
- Telemetry opt‑out via `OSIRIS_TELEMETRY=off`.
- License headers in generated artifacts; SPDX identifiers in source.

---

## Docs Additions (Scaffold Tasks)

- `docs/how-to/run-in-e2b.md`: minimal step‑by‑step.
- `docs/reference/oml/schema.md`: generated from OML JSON Schema.
- `docs/reference/components/*.md`: generated from spec cards.
- ADR 0001: Canonical Run Manifest (already planned).
- ADR 0002: Validation Modes (warn/strict/off) and Upgrade Strategy.

---

## Migration Guide (Skeleton)

Audience: users upgrading from 0.1.x without validation to 0.1.x with M1a/M2.

Structure:
- Symptoms you may see (new warnings, suggested defaults)
- What changed (validation modes, manifest emission)
- How to fix (common patterns with before/after OML snippets)
- Tools: `osiris upgrade`, `--mode warn`, feature flags
- Rollback: `OSIRIS_VALIDATION=off` and legacy path

---

## Work Breakdown for First Two PRs (Ready for Claude)

PR 1 (M0 + M1a skeleton):
	- Implement discovery cache fingerprinting + TTL.
	- Add JSON Schema for connection configs; integrate basic validation in `osiris run`.
	- Introduce `--mode warn|strict|off` and `OSIRIS_VALIDATION`.
	- Friendly error mapper (minimal rules for required/enum).
	- Unit tests + one integration test path.
	- Extend `components/spec.schema.json` with `secrets` and `redaction`; update examples.
	- Wire registry-driven redaction into logging (use masks for any paths listed in `secrets`).

PR 2 (M2 + compile shell):
	- Context exporter for active components (mysql.table, supabase.table).
	- Wire validation into chat flow (post‑gen enforcement).
	- `osiris compile` stub generating manifest + cfg for 1→1 pipelines.
	- Local runner consumes manifest; emits logs + metrics.
	- e2b adapter stub with API key resolution.
	- Add golden tests ensuring secrets never appear in manifest or logs; verify masking honors spec + env override.

## Final Critical Question for Codex

The implementation plan is excellent and addresses all architectural concerns. One remaining question on execution strategy:

**Component Spec Bootstrap Problem**: M1a requires component specs to exist before the context builder (M2) can export them, but we need to write those specs without existing validation. 

**Question**: Should we:

A) **Manual bootstrap**: Hand-write the first 2 component specs (mysql.table, supabase.table) based on existing code analysis, then use them to validate future specs?

B) **Code-first generation**: Write a one-time script that introspects existing `osiris/connectors/mysql` and `osiris/connectors/supabase` code to auto-generate initial spec.yaml files?

C) **Hybrid approach**: Start with minimal hand-written specs for MVP, then add auto-generation tooling later for new connectors?

**Context**: The current connectors likely have implicit schemas embedded in their Python code. We need to extract this into explicit YAML specs without circular dependencies.

**Recommendation**: Option A (manual bootstrap) seems cleanest for MVP - analyze existing connector code, hand-write 2 minimal specs, use those to bootstrap the system. Auto-generation can be added later as a developer productivity tool.


**Is this the right approach, or do you see a better bootstrap path?**

### Author Response (Decision)

**Decision: C) Hybrid, with a tight MVP slice.**

Rationale:
- **Speed & clarity now:** We hand‑craft two **minimal** spec cards (`mysql.table`, `supabase.table`) so M1a can ship immediately and unblock M2/M3.
- **Quality & scale later:** We then add a small **code‑assisted generator** that introspects connector modules to *suggest* spec scaffolds for future connectors. Human review remains the gate.

**What “minimal” means for the two bootstrap specs** (explicit acceptance for M1a):
- Fields only: `apiVersion`, `kind`, `name`, `version`, `modes`, `capabilities`, `configSchema.required`, `configSchema.properties` (with enums/defaults), and **≤2 examples**.
- No prose; no custom constraints beyond what JSON Schema can express today.

**Guardrails for correctness (so manual specs don’t drift):**
- Add a **spec linter** (`tools/spec_lint.py`) that checks: missing required fields, unknown keys, invalid enums, example validity against the JSON Schema.
- Add a **golden test** per component: parse spec, validate its examples, and snapshot a minimal **compiled context** extract used by the chat.

**Follow‑up: code‑assisted scaffold (post‑M1a, optional M1b task):**
- A small script `tools/gen_spec_from_code.py` that:
  - Imports `osiris/connectors/<name>` module,
  - Reads obvious constants (SUPPORTED_MODES, CAPABILITIES, DEFAULTS),
  - Reflects constructor signature / pydantic models (if present),
  - Emits a **draft** `spec.yaml` that passes the schema but still requires human edits for descriptions/examples.
- We keep it **best‑effort** and never a hard dependency of the build; it is a developer productivity tool.

**Work items (ready for Claude):**
- PR 0 (inside PR 1 if preferred):
  - Create `components/spec.schema.json` (as specified earlier in M1a).
  - Add hand‑written minimal specs:
        components/mysql.table/spec.yaml
        components/supabase.table/spec.yaml
  - Implement `tools/spec_lint.py` and a `make spec-lint` target (or `poetry run osiris spec-lint`).
  - Tests: validate examples; snapshot exporter’s context for these two components.
- Post‑M1a (optional):
  - Prototype `tools/gen_spec_from_code.py` for `mysql.table` to prove feasibility; document limitations and required manual review.

**Exit criteria for the bootstrap:**
- `osiris components list` shows both components with modes and capabilities.
- `osiris prompts build-context` outputs a compact JSON that includes only required/enums/defaults + tiny examples.
- `osiris compile` + `osiris run` succeed on the demo pipelines using the new specs, with validation in `--mode=warn`.

This balances **determinism today** with a clear path to **automation later**, without blocking M2/M3 or over‑engineering the generator.

</file>

## Appendix — Draft Skeletons (Copy‑Paste Ready)

These are minimal, copy‑paste skeletons to bootstrap M1a (spec schema + two component specs) and developer tooling stubs. Keep them intentionally small; enrich later as we learn.

### A) components/spec.schema.json (minimal)

    {
      "$schema": "https://json-schema.org/draft/2020-12/schema",
      "title": "Osiris ComponentSpec",
      "type": "object",
      "required": ["apiVersion","kind","name","version","modes","capabilities","configSchema"],
      "properties": {
        "apiVersion": { "type": "string", "const": "osiris.v1" },
        "kind": { "type": "string", "const": "ComponentSpec" },
        "name": { "type": "string" },
        "title": { "type": "string" },
        "description": { "type": "string" },
        "version": { "type": "string" },
        "modes": { "type": "array", "items": { "enum": ["read","write","transform"] } },
        "capabilities": { "type": "array", "items": { "type": "string" } },
        "configSchema": { "type": "object" },
        "constraints": { "type": "array", "items": { "type": "object" } },
        "examples": { "type": "array", "items": { "type": "object" } }
      },
      "additionalProperties": false
    }

### B) components/mysql.table/spec.yaml (bootstrap)

    apiVersion: osiris.v1
    kind: ComponentSpec
    name: mysql.table
    version: "0.1.0"
    title: "MySQL Table"
    description: "Read rows from a MySQL table; emit tabular stream."
    modes: ["read"]
    capabilities: ["discovery", "in_memory_move"]
    configSchema:
      type: object
      required: ["connection", "mode", "options"]
      properties:
        connection: { type: string, description: "@mysql connection reference" }
        mode: { type: string, enum: ["read"], default: "read" }
        options:
          type: object
          required: ["schema", "table"]
          properties:
            schema: { type: string }
            table: { type: string }
            columns:
              type: array
              items: { type: string }
            filters:
              type: array
              description: "Optional simple predicates; format TBD (M1b)."
              items: { type: string }
    examples:
      - title: "Read orders from MySQL"
        oml:
          type: mysql.table
          connection: "@mysql"
          mode: read
          options:
            schema: public
            table: orders
            columns: [id, customer_id, amount, created_at]

### C) components/supabase.table/spec.yaml (bootstrap)

    apiVersion: osiris.v1
    kind: ComponentSpec
    name: supabase.table
    version: "0.1.0"
    title: "Supabase Table"
    description: "Read or write rows to a Supabase Postgres table."
    modes: ["read", "write"]
    capabilities: ["discovery", "in_memory_move"]
    configSchema:
      type: object
      required: ["connection", "mode", "options"]
      properties:
        connection: { type: string, description: "@supabase connection reference" }
        mode: { type: string, enum: ["read", "write"] }
        options:
          type: object
          properties:
            schema: { type: string }
            table: { type: string }
            write_mode: { type: string, enum: ["append", "merge"], default: "append" }
            merge_keys:
              type: array
              items: { type: string }
    constraints:
      - when: { mode: "write", options.write_mode: "merge" }
        must: { options.merge_keys: { minItems: 1 } }
        error: "merge_keys required for write_mode=merge"
    examples:
      - title: "Append to Supabase"
        oml:
          type: supabase.table
          connection: "@supabase"
          mode: write
          options:
            schema: public
            table: orders
            write_mode: append
      - title: "Merge into Supabase by id"
        oml:
          type: supabase.table
          connection: "@supabase"
          mode: write
          options:
            schema: public
            table: orders
            write_mode: merge
            merge_keys: [id]

### D) tools/spec_lint.py (stub)

    """Lints component spec files against the spec.schema.json and basic conventions.
    Usage: python tools/spec_lint.py components/  # exits non‑zero on failures
    """
    import sys, json, pathlib
    from jsonschema import validate, Draft202012Validator

    def load_json(p: pathlib.Path):
        return json.loads(p.read_text())

    def load_yaml(p: pathlib.Path):
        import yaml
        return yaml.safe_load(p.read_text())

    def main(root: str):
        root = pathlib.Path(root)
        schema = load_json(root / "spec.schema.json") if (root / "spec.schema.json").exists() else load_json(pathlib.Path("components/spec.schema.json"))
        validator = Draft202012Validator(schema)
        failures = 0
        for spec in root.rglob("spec.yaml"):
            data = load_yaml(spec)
            errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
            for e in errors:
                print(f"ERROR {spec}: {'/'.join([str(x) for x in e.path])} → {e.message}")
                failures += 1
            # Simple conventions
            if "examples" in data and len(data["examples"]) > 2:
                print(f"WARN  {spec}: keep ≤2 examples for MVP context size")
        sys.exit(1 if failures else 0)

    if __name__ == "__main__":
        main(sys.argv[1] if len(sys.argv) > 1 else "components")

### E) tools/gen_spec_from_code.py (optional helper)

    """Best‑effort draft generator for spec.yaml from connector code.
    Not used in CI; developer tool only. Requires human review.
    """
    import importlib, inspect, json

    def draft_from_connector(module_name: str) -> dict:
        m = importlib.import_module(module_name)
        modes = getattr(m, "SUPPORTED_MODES", ["read"])  # heuristic
        caps = getattr(m, "CAPABILITIES", [])
        defaults = getattr(m, "DEFAULTS", {})
        cfg_props = {k: {"type": "string"} for k in getattr(m, "REQUIRED_OPTIONS", [])}
        cfg = {
            "type": "object",
            "required": ["connection", "mode", "options"],
            "properties": {
                "connection": {"type": "string"},
                "mode": {"type": "string", "enum": modes},
                "options": {"type": "object", "properties": cfg_props}
            }
        }
        return {
            "apiVersion": "osiris.v1",
            "kind": "ComponentSpec",
            "name": module_name.split(".")[-1] + ".table",
            "version": "0.1.0",
            "modes": modes,
            "capabilities": caps,
            "configSchema": cfg,
            "examples": []
        }

    if __name__ == "__main__":
        print(json.dumps(draft_from_connector("osiris.connectors.mysql"), indent=2))
