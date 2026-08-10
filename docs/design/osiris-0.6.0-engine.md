# Osiris v0.6.0 — Conversation Productization Engine

**Status:** Design (approved in brainstorming, not yet planned)
**Date:** 2026-08-10
**Supersedes in intent:** `docs/design/osiris-2.0.md`, `docs/design/osiris-kbagent-integration.md`, `docs/2026-update.md`
**Depends on:** [cf-ng](https://github.com/keboola/cf-ng)

---

## 1. Problem

You hold an exploratory conversation with an AI about your own environment — *which leads are in Salesforce, which opportunity moved through PoC fastest and which campaign brought it, how is headcount developing, what are the key processes my team delivers.* The conversation ends when you find the answer.

Then you want to automate what the answer taught you. Not the conversation itself — something adjacent, built on the knowledge the conversation produced. *"Now I know which films are well rated; I want a recurring digest of cinemas showing a well-rated new release."*

For something that runs every 15 minutes you do not want an LLM. It is mostly unnecessary, it is non-deterministic, and it costs money on every tick. And ideally the result is a **package you run in your own environment**.

Nothing today closes that loop. [cf-ng](https://github.com/keboola/cf-ng) makes ~700 third-party connectors callable by an agent in real time, with credential custody in the user's own Keboola project. It deliberately stops there: it has no run record, no run id, no observability beyond one stdout line, no idempotency, no orchestration, no scheduling, no result persistence, no packaging, no deployment artifact, no evaluation.

Osiris v0.6.0 is the layer that turns a cf-ng conversation into a **fingerprinted, replayable, explainable artifact**.

---

## 2. What changes from v0.5.4

v0.5.4 is an LLM-first conversational **ETL pipeline generator**. It owns its own connectors, its own chat, its own LLM adapter, and executes pipelines locally or in E2B sandboxes.

v0.6.0 keeps the goal — *AI designs once, the runtime executes deterministically* — and replaces the technology and the architecture:

| Concern | v0.5.4 | v0.6.0 |
|---|---|---|
| Third-party reach | 9 in-house connectors + drivers | cf-ng (~694 connectors) |
| Conversation | own chat FSM + own LLM adapter + own API keys | host agent (Claude Code); engine holds **no LLM keys** |
| Agent guidance | prompts + pro-mode | a plugin/skill served by the engine, mirroring cf-ng's `GET /skill` |
| Data plane | DuckDB bus — sound design, broken wiring (§2.1) | DuckDB bus, wiring fixed and proven first (§4.4) |
| Remote execution | E2B (4 ADRs, ~6.3k LOC) | Docker as a **packaging** format |
| Artifact | OML → manifest | Plan → manifest + pins + fingerprints |
| Determinism | fingerprints computed, **never verified** | pins + fingerprints verified on **every** run |

### 2.1 The honest starting position

Three independent recon passes plus a direct empirical check agree: **v0.5.4 cannot execute a pipeline.**

- `RunnerV0.RunnerContext` is defined *inline inside a method* (`osiris/core/runner_v0.py:457`) and exposes only `output_dir` and `log_metric`.
- `ProxyWorker.SimpleContext` (`osiris/remote/proxy_worker.py:515`) likewise lacks `get_db_connection`.
- **All 7 drivers** call `ctx.get_db_connection()` — `duckdb_processor`, `filesystem_csv_extractor`, `filesystem_csv_writer`, `graphql_extractor`, `mysql_extractor`, `posthog_extractor`, `supabase_writer`. Local and E2B execution raise `AttributeError` for every one.
- The integration tests that would catch this are `pytest.mark.skip` at **module** level.
- 2 of 9 component specs (`mysql.writer`, `supabase.extractor`) point `x-runtime.driver` at Python modules that do not exist; the registry accepts them because `verify_import=False`.
- `unittest.mock.MagicMock` is imported and constructed in a shipping driver (`osiris/drivers/supabase_writer_driver.py`).

`osiris compile` **does** work and is deterministic (verified: produced a manifest with hash `10e46e7`). The dividing line is exact: **the compilation spine lives, the execution layer is dead.** That is a favourable split — v0.6.0 harvests the living half.

---

## 3. Architecture

Three deployment units with three different lifetimes. None holds an LLM API key.

| Unit | Where it lives | Lifetime |
|---|---|---|
| `osiris serve` | developer machine, local MCP server | ephemeral — only while authoring |
| `build/<hash>/` artifact | git, registry, a directory | immutable, hash-addressed |
| `osiris run` | the customer's runtime (docker or pip) | every scheduled tick |

### 3.1 Phase 1 — Exploration (design time)

```
Claude Code ──MCP──> osiris serve ──HTTP──> cf-ng ──> third-party systems
                          │
                          └──> session store: args, result, schema hash, duration, outcome
```

The engine exposes an MCP endpoint that **relays** calls to cf-ng and records every one. This is the load-bearing choice: *the engine's differentiator is evidence and determinism; if it is not in the path, it cannot produce evidence — it can only accept claims.* It also fills cf-ng's missing run history for the exploration phase itself, before any pipeline exists.

The relay is a local process, not an operated service. cf-ng's `POST /tools/call` is synchronous and its tool descriptor is already MCP-shaped, so the relay is thin.

### 3.2 Phase 2 — Freeze

The host agent, guided by the engine's skill, calls `plan_freeze` with an authored plan. The engine validates it against both the recorded observations and cf-ng's live schemas, pins what it can, canonicalizes, fingerprints, and emits `build/<hash>/`.

### 3.3 Phase 3 — Runtime

```
your runtime ──> osiris run ──> cf-ng ──> the same third-party systems
                     │
                     └──> events.jsonl · run index · AIOP
```

**cf-ng is the same service in both phases, with the same tool contract.** A step in the artifact is literally the same `POST /tools/call` that ran during the conversation — not a translation into another execution model. This is the only reason "freeze" is credible; it is also why the in-house driver/connector layer is deleted rather than adapted.

### 3.4 Runtime dependency: hybrid with an eject seam

The frozen package calls cf-ng at runtime by default. Credentials stay encrypted in the customer's own Keboola project; the package carries no secret, only a `${CFNG_TOKEN}` reference.

A standalone "eject" mode — generating a package that calls a third-party API directly — is a **documented seam, not a second implementation**. v1 ships the cf-ng path only. Building both from the start risks finishing neither, and doubles the definition of "deterministic".

---

## 4. The artifact

### 4.1 Manifest

```yaml
apiVersion: osiris/v1
kind: Plan
metadata:
  name: cinema-listings-well-rated
  frozen_from_session: sess_01JQ...          # traceability back to the conversation
  engine_version: 0.6.0
pins:
  cfng:
    proxy: internal-research
    catalog_version: "sha256:9f3a…"
  tools:
    imdb__search_titles:  {input: "sha256:1a2b…", output: "sha256:3c4d…"}
    slack__post_message:  {input: "sha256:5e6f…", output: "sha256:7a8b…"}
policy:
  on_tool_contract_drift: fail
  on_catalog_drift: warn
  on_proxy_scope_drift: warn
params:
  min_rating: 7.5
steps:
  - id: fetch_releases
    uses: cfng_call
    with: {connector: imdb, tool: search_titles, args: {since: "${run.date - 7d}"}}
  - id: pick_good_ones
    uses: sql
    with: {query: "SELECT * FROM fetch_releases WHERE rating >= ${params.min_rating}"}
  - id: notify
    uses: cfng_call
    with: {connector: slack, tool: post_message, args: {text: "${steps.pick_good_ones.summary}"}}
fingerprints: {plan: "…", pins: "…", engine: "…", manifest: "…"}
```

The plan is a **linear sequence, not a DAG**. `RunnerV0` already executed strictly sequentially and used `needs` only for input wiring; ADR-0031 (control flow) is 0% implemented; the target use cases are fetch → filter → notify. A DAG is added when something demands it.

**Deliberately unspecified here:** the reference and templating model. The example uses `${run.date - 7d}`, `${params.min_rating}`, `${steps.pick_good_ones.summary}` and an implicit binding of step id `fetch_releases` to a SQL-addressable relation — all four are illustrative, not specified. This is the **first thing the implementation plan must pin down**, because it determines what can be canonicalized and therefore what can be fingerprinted. Constraints it must satisfy: total and side-effect-free (no arbitrary expression evaluation), canonically serializable, and resolvable without network access so that a plan's hash does not depend on when it was computed.

### 4.2 Determinism: four pin classes, four policies

Not all drift is equal. When cf-ng adds a connector, your pipeline is unaffected. When a tool's `inputSchema` changes, it breaks. These must not share a policy.

| Pin | Source | Default | Rationale |
|---|---|---|---|
| per-tool `input_schema` / `output_schema` hash | engine computes from `Tool.as_manifest()` | **fail** | The only drift that actually breaks the pipeline |
| `catalog_version` | cf-ng ETag (content hash over ~979 catalog entries) | **warn** | Changes on every catalog addition; failing on it would be unusable |
| proxy scope (connector set) | cf-ng proxy | **warn** | Scope growth is security-relevant, not a correctness break |
| connector version | **not reported by cf-ng today** | `unknown`, recorded in evidence | An honestly declared blind spot |

Crucially, the schema hashes require **no change in cf-ng** — `Tool.as_manifest()` already returns `inputSchema` and `outputSchema` (`cf-ng/src/connectors/base.py:45-46`). The one drift that matters is detectable today.

Policies are explicit manifest fields, not hardcoded assumptions, so the defaults tighten as the cf-ng dependencies land (§9).

### 4.3 Fingerprints must be verified

v0.5.4 computes fingerprints faithfully and **calls `verify_fingerprint()` nowhere at runtime**. The same class of defect appears twice more: `osiris/mcp/audit.py:_sanitize_arguments` exists and is never called, so `osiris/mcp/server.py:371` writes raw arguments to JSONL.

*A decorative guarantee is worse than none, because it is relied upon.*

**Rule for v0.6.0:** the runner verifies pins and the manifest fingerprint before the first call of every run. Every guarantee has a test that **violates** it and expects failure — a fingerprint test must feed a mutated manifest and assert the run aborts, not assert that a hash can be computed.

### 4.3.1 What the guarantees actually are

Two rounds of adversarial verification (`docs/reports/2026-08-10-v060-adversarial-verification/`) refuted every guarantee as originally worded. Most of the second round's refutations were defects; several were the wording. These are the bounded claims the implementation supports, and they are the ones to make in public:

| Claim | Holds | Bound |
|---|---|---|
| **Deterministic** | Verified across processes, working directories, timezones, locales, `PYTHONHASHSEED` and wall clock — 5 interpreters, 3 fake clocks, 120 fuzzed drafts, zero variance and zero collisions. | The hash covers the pins, so it is tied to the **cf-ng deployment it was frozen against**. Staging and production yield different hashes for the same draft. That is correct — the pins *are* part of the artifact — but it means the hash names a plan-against-an-environment, not a plan. |
| **Tamper-evident** | Every partial edit is caught: all three fingerprints, the internal relation `manifest == sha256(plan + pins)`, and the build directory name. 11 benign reformattings (BOM, CRLF, flow style, JSON rewrite, comments) correctly tolerated. | An **unkeyed checksum stored beside what it protects**. An attacker who rewrites every file *and* renames the directory produces a coherent artifact. Closing that needs a signature and a key-management story that does not exist yet. Tamper-evidence here means *against accident and casual edit*. |
| **Aborts on drift** | Real and ordering-correct: nothing is called, verified with a request-counting transport, including when the drifting tool belongs to the last step. | Conditional on `policy.on_tool_contract_drift`, which the plan author sets at freeze time. `warn` and `ignore` are legitimate settings that disable the abort; the evidence record must therefore say which policy was in force. |
| **Pins verified** | Before the first call of every run. | At **t0 only**. A contract that moves mid-run is not re-checked. Per-call re-verification is a real cost and is deferred. |
| **Secret-free evidence** | Redaction walks dict keys, values, lists, tuples, sets and bytes; rows are redacted before the artifact is written and the table is built from that file, so nothing enters the DuckDB pages. Verified by byte-grepping every file under the base path on both the success and the failure path, with a planted positive control. | Redaction is by known secret plus credential-shaped pattern. A credential in a shape nobody anticipated is not covered. This is mitigation, not proof. |

The general lesson, recorded because it outlived the specific bugs: **a green test is a claim, not evidence.** The round-1 leak test passed 5/5 while four leaks were live, because it greped one file — the only one already correct. Every guarantee test in this repo must fail when its guarantee is removed, and the sweep tests must carry a positive control proving the search itself works.

### 4.4 Data between steps: DuckDB, not memory

**Data must not be held in memory and volumes must not be assumed small.** Intermediate data flows through a per-run DuckDB file (`pipeline_data.duckdb`); each step reads and writes tables addressed by step id. This is ADR-0043's design, retained deliberately.

ADR-0043 is the most thoroughly measured decision in the repo — ~1.5M rows/s, 98% memory reduction, 67% disk saving, and it deleted ~1,500 lines of hand-rolled spilling logic. What is broken is not the design but the **wiring**: neither runtime context provides `get_db_connection()` while all 7 drivers call it (§2.1). v0.6.0 keeps the design and fixes the wiring, and proving that fix is the **first deliverable of phase 1** — a single shared, tested `RunContext` constructed once by the engine, replacing the two divergent inline classes.

DuckDB therefore serves two roles that must not be confused:

- **the data bus** — where step outputs live, on disk, spill-capable, unbounded by RAM;
- **a step type** (`uses: sql`) — declarative transformation over those tables.

**The bus has a single process owner.** Measured during implementation, not assumed: within one process, a second context opened on the same file is an *alias* — DuckDB's instance cache returns the same database instance, so both see each other's writes and neither is isolated. Across processes the file lock is exclusive and a second opener raises `IOException`; the lock releases cleanly on close. This constrains §3.3 and phase 4: a containerized run owns the file for its whole lifetime, and any future design that executes steps in a child process must either close the parent's connection before handing over the run directory, or route the child's data access through the parent. It cannot simply open the file on both sides.

v1 step types: `cfng_call`, `sql`, `assert`.

`assert` is first-class from v1: a step that checks a precondition (*more than 0 rows arrived*) and halts the run with a clear error. Without it, a silent upstream change surfaces as an empty digest every 15 minutes that nobody notices for a month.

### 4.5 Volume: the cf-ng shape is the constraint, not its limits

cf-ng's published limits are **environment-configurable deployment defaults**, not architectural ceilings — `AIRBYTE_READ_HARD_CAP=1000`, `AIRBYTE_READ_TIMEOUT_S=120`, `AIRBYTE_MAX_CONCURRENCY=4` (`airbyte-sidecar/server.py:50-52`), `CFNG_HTTP_TIMEOUT=30`, `CFNG_AIRBYTE_TIMEOUT=180` (`env.example:33,43`). They can be raised.

Raising them does not solve volume, because the limiting factor is the **shape**: `POST /tools/call` is synchronous and in-process, returns the payload inline, and has no queue, no job object and no streaming response. A cap of 1,000,000 means a synchronous HTTP call returning a multi-gigabyte JSON body — a worse failure than the cap.

Two mechanisms, in this order:

1. **Engine-side pagination (v1).** For extraction steps the engine issues repeated bounded `cfng_call`s with a cursor or offset and streams each page straight into DuckDB. This works within cf-ng's current shape and needs no cf-ng change, but depends on the connector exposing pagination — which is per-connector and not uniformly guaranteed. Every paginated read records page count and total rows in evidence, so a silently truncated extraction is visible rather than assumed complete.
2. **A bulk path in cf-ng (dependency).** For volumes where pagination over synchronous HTTP is the wrong tool, cf-ng needs either a streaming response (chunked NDJSON), an async job with polling, or a land-to-Storage path. The last already exists as [keboola/cf-ng#11](https://github.com/keboola/cf-ng/issues/11) (`store_records` / create-table-from-JSON), which lands agent-pulled data in the caller's own Keboola project. Tracked as a new dependency in §9.

**Keboola Storage is a destination, not the bus.** Writing a result to a Storage table is a writer step; it does not replace the local DuckDB file that carries data between steps in the customer's own runtime.

This is also where the eject seam (§3.4) stops being hypothetical: if a customer's extraction volume outgrows what cf-ng can carry synchronously and the bulk path has not landed, going direct to the source for that one step is the pressure valve. It remains out of v1 scope, but the artifact's step model must not make it impossible — which is why `uses:` is an open step-type field rather than a closed enum. (v0.5.4's component spec closed exactly this door: `modes` is a fixed enum with `additionalProperties: false`.)

---

## 5. Components

| Module | Responsibility | Origin |
|---|---|---|
| `relay` | MCP endpoint, forwards to cf-ng, records observations | **new** (~400 LOC) |
| `session` | observation store for the exploration phase | harvest: `session_logging` |
| `tools` | MCP tools for the host agent (`plan_*`, `run_*`, `session_*`) | harvest: handshake mechanism, `_meta` envelope, error taxonomy |
| `compile` | canonicalize, pin, fingerprint, emit `build/<hash>/` | harvest: `canonical.py` + `fingerprint.py` **verbatim**, `fs_paths` |
| `run` | execute plan, verify pins, write evidence | harvest: `ExecutionAdapter` seam, `run_ids` + `run_index` |
| `evidence` | events/metrics JSONL + AIOP export | harvest: AIOP **contract**; implementation rewritten (~500 LOC, was 2,438) |
| `package` | pip wheel / docker image | **new** (no Dockerfile exists in the repo today) |

Harvest is **by copy and adaptation, never by import**. No v0.6.0 module may import from the old tree; otherwise the debt flows back.

### 5.1 Harvested verbatim or near-verbatim

`canonical.py` (104) + `fingerprint.py` (73) — canonical UTF-8/LF/sorted-key emission and stable hashing, with `generated_at` excluded from the manifest hash (`fs_paths.py:394`). `fs_config.py` (364) + `fs_paths.py` (497) — the filesystem contract, all paths config-driven, no `Path.home()`. `run_ids.py` (251) + `run_index.py` (348) — run identity and an append-only ledger under `flock` + fsync. `session_logging.py` (496) — two append-only JSONL streams redacted **at write time**; fix the module-level `_current_session` global (`:453`) to a contextvar. `execution_adapter.py` (214) — the `prepare → execute → collect` seam, with the module-scope `import duckdb` excised.

### 5.2 Deleted

`osiris/drivers/` (4,129) · `osiris/connectors/` (2,108) · `osiris/remote/` (6,294, of which 2,642 is already dead production code) · chat stack ~3,140 (`conversational_agent.py` 1,206, `prompt_manager.py`, `cli/chat.py` — `osiris chat` already exits 1 at `cli/main.py:167`) · `llm_adapter.py` (589) · `cli/main.py` (1,970 of hand-rolled argparse) · `prototypes/e2b_proxy/` (637).

**~19,000 lines of production code**, plus the majority of the 52,500 lines of tests that exercise them. Deletion happens **inside this initiative**, not afterwards.

### 5.3 One redactor, not five

v0.5.4 has five independent secret redactors with divergent denylists: `core/redaction.py`, `run_export_v2.redact_secrets`, `core/secrets_masking.py`, `connection_helpers.mask_connection_for_display`, `proxy_worker._E2BLogSanitizer` — five different definitions of what is secret. v0.6.0 has one, driven by component-spec `x-secret` JSON pointers.

---

## 6. Error handling

**Contract drift** → fail at startup, before the first call. The error carries a **schema diff** and an `osiris replan <hash>` pointer that returns the user to the agent with that diff as context. The pipeline is not permanently broken; it requests a re-freeze.

**Step failure** → the whole run fails. No resume. For a pipeline running every 15 minutes, "it failed, it will run again shortly" is usually the right answer, and evidence carries everything needed to diagnose. Checkpoint/resume is YAGNI until a concrete expensive-or-irreversible step demands it.

**Opaque cf-ng error** → cf-ng raises `HTTPException(502, detail="Upstream provider error.")` as a fixed literal, discarding the original exception (`cf-ng/src/app.py:732,736`). The engine records connector, tool, arguments, duration and outcome regardless — already more than cf-ng retains. Tracked as [keboola/cf-ng#27](https://github.com/keboola/cf-ng/issues/27).

**Retry** must be conservative until cf-ng populates tool annotations. cf-ng has no idempotency key, no dedup and no request hash — two identical calls execute twice — and `Tool.annotations` is populated only for remote-MCP-sourced tools (`cf-ng/src/connectors/mcp/connector.py:53`), never for the 694 Keboola/Prismatic/Airbyte ones. `readOnlyHint`/`destructiveHint`/`idempotentHint` appear nowhere in cf-ng's `src/`. **Until [#26](https://github.com/keboola/cf-ng/issues/26) lands, the runner retries nothing automatically.** After it lands, read-only steps retry automatically and destructive ones require an explicit `idempotency_key`.

**Silent data change** → the `assert` step type (§4.4).

---

## 7. Testing strategy

v0.5.4's tests existed and still failed to catch a completely broken runtime. Four patterns caused it, and each gets a countermeasure:

| Failure pattern in v0.5.4 | Countermeasure |
|---|---|
| Integration tests skipped at **module** level, so they never run and nobody notices | No module-level skip. A test that cannot run in CI is marked and **counted** in the summary. |
| Registry accepts specs with `verify_import=False`, so two specs point at non-existent modules | Registration verifies imports and **fails loudly**; a spec pointing at a missing module is a hard error. |
| `MagicMock` imported and constructed in a production driver | CI lint rule: `unittest.mock` may not be imported outside `tests/`. |
| `verify_fingerprint()` and `_sanitize_arguments()` written and never called | Every guarantee has a **violation test**: mutate the artifact, expect abort. Dead-code detection on security- and determinism-critical functions. |

Two tests carry disproportionate weight:

1. **Determinism golden test** — compile the same plan twice, on different machines, with different `generated_at`: identical manifest hash.
2. **Live round-trip** — a plan actually executed against a running cf-ng instance, twice, comparing evidence. v0.5.4 never had this, which is precisely why it shipped broken.

---

## 8. Build phases

| # | Scope | Estimate | Done means |
|---|---|---|---|
| 0 | Commit the untracked strategic corpus; scaffold v0.6.0 package | 0.5 d | Prior analysis is in git |
| 1 | **Walking skeleton** — shared `RunContext` (§4.4), relay, session store, freeze, run | ~1 w | Conversation → artifact → run twice → identical evidence and matching fingerprint, with data passing between steps through DuckDB |
| 2 | Plugin/skill served by the engine; handshake instructions | ~3 d | A cold Claude installs the skill and completes the flow unaided |
| 3 | Step types (`sql`, `assert`), drift policies, retry, error taxonomy | ~1 w | Drift aborts a run with a diff and offers `replan` |
| 4 | Packaging — Dockerfile, wheel, containerized run | ~3 d | `docker run` of the artifact in a foreign environment |
| 5 | AIOP export, `run_diff` | ~1 w | Two runs can be compared and explained |

Deletion of the old tree (§5.2) is part of phase 1, not a follow-up.

---

## 9. Dependencies on cf-ng

Filed 2026-08-10, all `enhancement`:

- [#25 — Expose connector version in the tool descriptor](https://github.com/keboola/cf-ng/issues/25). Unblocks hard pinning. Without it, connector-version drift is undetectable, most acutely for Airbyte (`install_if_missing=True`, no pin, `airbyte-sidecar/server.py:111,123`).
- [#26 — Populate MCP tool annotations](https://github.com/keboola/cf-ng/issues/26). Unblocks automated retry for read-only steps.
- [#27 — Preserve structured upstream error information](https://github.com/keboola/cf-ng/issues/27). Unblocks retry classification and useful diagnostics.
- **A bulk read path** (§4.5) — streaming response, async job, or the land-to-Storage tool already proposed as [#11](https://github.com/keboola/cf-ng/issues/11). Not a v1 blocker, because engine-side pagination works within cf-ng's current shape, but it is the ceiling on how much data a frozen pipeline can move.

**Assumption, not a blocker:** the `cfng_` capability token caps at 90 days. A renewal mechanism belongs in cf-ng, which already owns identity; the engine must not duplicate it. Until then, `osiris doctor` checks token expiry and the runner fails with an explicit "token expired, re-mint" error rather than an opaque auth failure.

---

## 10. Non-goals

- **Scheduling.** The artifact is runnable; cron, GitHub Actions or Keboola orchestration runs it. v0.5.4 has three unfinished scheduling ADRs and empty roadmap stubs — do not continue them. This is a non-goal for the *engine*, not for the *product*: shipping worked examples of each host is in scope (§12), because "runnable" is not the same as "someone knows how to run it".
- **Its own LLM.** No API keys, no prompt management, no eval harness, no chat. The consumer brings the model.
- **Its own connectors.** cf-ng brings 694; v0.5.4's own count was 9, which its own modernization note called a losing position.
- **DAG / control flow.** Linear until something demands otherwise.
- **Checkpoint/resume.** See §6.
- **Standalone eject mode in v1.** A documented seam only (§3.4).

---

## 11. Positioning

Drop the tagline *"AI designs once, the runtime runs deterministically without AI."* It is table-stakes in 2026 — dlt, Airbyte, Fivetran, Dagster, Prefect, Airflow+MCP and Bruin all claim it — and it is still the headline of the README and `docs/2026-update.md`.

The defensible claim is narrower, and cf-ng sharpens it:

> **The only place where an agent's conversation with a third-party system becomes a fingerprinted, replayable, explainable artifact.**

*"Fingerprinted", not "signed".* A fingerprint is a content hash: it proves the artifact has not changed since it was frozen and that two builds of the same plan are identical. It does **not** prove who produced it, and because the hash is stored beside what it protects, it does not withstand an attacker who rewrites the whole directory. Cryptographic signing is a later addition, and the claim must not run ahead of the mechanism — that is exactly the failure mode of v0.5.4's unverified fingerprints (§4.3). The precise, defensible wording of each guarantee is in §4.3.1; use those, not the headline.

---

## 12. Worked examples

Scheduling is not the engine's job (§10), but *showing how it is done* is part of the product. Each of these ships as a runnable example.

### 13.1 The authoring loop

```
$ osiris serve --cfng https://cf-ng-43677805.hub.us-east4.gcp.keboola.com
  listening on stdio · relaying to cf-ng · session sess_01JQ7X…
```

Registered as an MCP server in Claude Code alongside cf-ng. The user explores normally — *which films released this week are well rated, which cinemas show them* — and every relayed call is recorded. When the answer is found:

```
> /osiris:freeze make this a 15-minute digest to #film-club

  plan_freeze → validating 4 steps against 3 recorded observations
    ✓ imdb__search_titles     input sha256:1a2b… output sha256:3c4d…
    ✓ cinemas__by_title       input sha256:9f01… output sha256:2e3d…
    ✓ slack__post_message     input sha256:5e6f… output sha256:7a8b…
    ! connector version unavailable for 3 tools (cf-ng#25) — recorded as unknown
  → build/cinema-listings-well-rated/a71f3c9/
```

### 13.2 Running it

**cron, on any host with Docker**

```cron
*/15 * * * * docker run --rm --env-file /etc/osiris/cfng.env \
  -v /var/lib/osiris:/data ghcr.io/keboola/osiris:0.6.0 \
  run /data/build/cinema-listings-well-rated/a71f3c9
```

**GitHub Actions**

```yaml
on:
  schedule: [{cron: "*/15 * * * *"}]
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pipx install osiris-engine==0.6.0
      - run: osiris run build/cinema-listings-well-rated/a71f3c9
        env: {CFNG_TOKEN: "${{ secrets.CFNG_TOKEN }}"}
```

**Keboola orchestration** — the artifact directory committed to the project, executed by a scheduled job; `CFNG_TOKEN` supplied from the project's own encrypted configuration, so the credential never leaves the tenant.

**Locally, while iterating**

```bash
osiris run build/cinema-listings-well-rated/a71f3c9 --dry-run   # verify pins, execute nothing
osiris run build/cinema-listings-well-rated/a71f3c9
osiris run diff --last 2                                        # what changed between runs
```

### 13.3 What a drift failure looks like

```
$ osiris run build/cinema-listings-well-rated/a71f3c9
  ✗ tool contract drift — aborting before first call

    cinemas__by_title  inputSchema changed since freeze
      - required: [title, city]
      + required: [title, city, region]

    policy: on_tool_contract_drift = fail
    → osiris replan a71f3c9   (reopens the plan in your agent with this diff)
```

Nothing was called. The failure is diagnosable without reading a log, and the fix path is a single command back into the conversation.

---

## 13. Evidence

Grounded in a 9-agent parallel recon of both repositories (2026-08-10) plus direct verification. Load-bearing facts:

- `osiris compile` runs and is deterministic — verified, manifest hash `10e46e7`.
- `RunnerContext` (`runner_v0.py:457`) lacks `get_db_connection`; all 7 drivers require it — verified by import and source inspection.
- cf-ng: no runs key in vault v4 (`project_store.py:43-46`); no run id in responses (`app.py:742-743`); telemetry is one stdout line without arguments, result, duration or outcome (`app.py:714-715`); `grep -rniE 'idempot|replay|run_id' src/` returns nothing.
- cf-ng `Tool.as_manifest()` emits `inputSchema`/`outputSchema` (`connectors/base.py:45-46`) — the basis for engine-side pinning with no cf-ng change.
- cf-ng `annotations` set only at `connectors/mcp/connector.py:53` and `mcp_gateway.py:332`; MCP hint keys absent from `src/`.
- cf-ng `Connector` ABC has no `version` attribute.
- E2B production footprint: 24 files / 308 lines in `osiris/`; SDK surface is 4 verbs (`files.write`, `commands.run`, `files.read`, `kill`) mapping 1:1 onto `docker cp` / `docker exec` / `docker rm`.
- Branch inventory: 8 of 10 named branches have zero commits outside `origin/main`; no unmerged work of consequence.
- cf-ng volume limits are env-configurable defaults, not ceilings: `AIRBYTE_READ_HARD_CAP=1000`, `AIRBYTE_READ_TIMEOUT_S=120`, `AIRBYTE_MAX_CONCURRENCY=4` (`airbyte-sidecar/server.py:50-52`); `CFNG_HTTP_TIMEOUT=30`, `CFNG_AIRBYTE_TIMEOUT=180` (`env.example:33,43`). The binding constraint is the synchronous inline-payload shape of `POST /tools/call`, which raising a cap does not change.
- ADR-0043 measurements (~1.5M rows/s, 98% memory reduction, 67% disk saving, ~1,500 LOC of spilling logic removed) make it the best-evidenced decision in the repo; its defect is wiring, not design.
