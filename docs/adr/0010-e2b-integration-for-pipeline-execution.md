

# 0010 E2B Integration for Pipeline Execution

## Status
Accepted

## Context
Osiris needs a deterministic, isolated, and observable execution environment for `osiris run`. Local execution is fine for development, but:
- We want **ephemeral sandboxes** for reproducible runs, short-lived credentials, and clean teardown.
- We need **uniform observability** (session-scoped logs, artifacts, metrics) across developer laptops and CI.
- We want **safe network boundaries** for connectors (e.g., allow-list to MySQL and Supabase only).
- We prefer a **managed, on-demand compute** to reduce “works-on-my-machine” drift and to simplify demos.

**E2B** (via its Python SDK) provides ephemeral, programmatically controlled environments that map well to our needs and to Osiris’ session-scoped logging & artifacts model.

## Decision
Adopt **E2B** as the primary remote execution backend for `osiris run`, with a pluggable runner interface that also supports a “local” backend.

### Key points
- **Runner abstraction:** `Runner` interface with at least two implementations:
  - `LocalRunner` (default for dev)  
  - `E2BRunner` (default for demos/CI)
- **Configuration:**
  - `osiris.yaml` → `runner.executor: local|e2b` (defaults to `local`)
  - Optional `runner.e2b` section for image, timeouts, resource limits, network policy.
  - CLI override: `osiris run --executor e2b` (precedence: CLI > ENV > YAML > defaults; see ADR-0004).
- **Session integration:**
  - Each run creates a **session directory** under `./logs/<session_id>/` (ADR-0003).
  - The runner **streams stdout/stderr** and writes **structured JSONL events** and **metrics** into the session directory.
  - The generated pipeline YAML and compiled runtime manifest (JSON) are persisted as **artifacts**.
- **Security & secrets:**
  - Secrets injected into the E2B environment as environment variables (or mounted secrets file), never printed in plaintext.
  - Masking performed at emit time (ADR-0009) and driven by component specs once available (ADR-0005/0007/0008).
  - Optional **network allow-list** (MySQL host, Supabase URL) and **egress timeout** to reduce risk.
- **Lifecycle:**
  - Sandbox created per `run`, configured, executed, and **destroyed** at the end; cleanup recorded in session logs.
  - In failure paths, bundle logs + artifacts for triage (`osiris logs bundle --session <id>`).
- **Cost & control:**
  - Configurable **max duration**, **max memory/cpu**, and **idle timeout** to avoid runaway costs.
  - Dry-run mode to compile and validate without starting a sandbox.

## Consequences
**Pros**
- Deterministic, isolated runs across developer machines and CI.
- Stronger demos and reproducibility (one command brings up a clean environment).
- Unified session-scoped observability (logs, metrics, artifacts) regardless of backend.
- Clear security model for secrets and network boundaries.

**Cons / Trade-offs**
- External dependency on E2B (mitigated by the runner abstraction and a robust LocalRunner).
- Additional effort to manage images, resource policies, and cost controls.
- Requires careful secrets handling to guarantee nothing leaks via stdout/stderr.

## Implementation Notes
- Add `Runner` interface and two implementations: `LocalRunner`, `E2BRunner`.
- Extend `osiris.yaml` with:
  - `runner.executor: local|e2b`
  - `runner.e2b.image`, `runner.e2b.timeout_seconds`, `runner.e2b.cpu`, `runner.e2b.memory_mb`
  - `runner.e2b.network.allow`, `runner.e2b.env_from_secrets: true|false`
- CLI: `osiris run [--executor local|e2b] [--timeout N] [--image X] ...`
- Session logging:
  - Log `run_start`, `run_prepare_env`, `run_submit`, `run_stdout`, `run_stderr`, `run_complete|run_failed`, `run_cleanup`.
  - Support `events: ["*"]` to capture all future event types by default (ADR-0001).
- Artifacts:
  - Persist: original pipeline YAML, compiled runtime JSON, stdout/stderr capture, timing/metrics.
- Tests:
  - Local: unit tests for the runner contract and compilation path.
  - E2B: integration tests behind a flag (skipped in CI unless E2B credentials present).

## Alternatives Considered
- **Local-only execution:** Simplest, but poor reproducibility and security isolation.
- **Kubernetes:** Powerful but heavy to operate for early OSS adoption; slower feedback loop.
- **Serverless (e.g., Cloud Run):** Good isolation, but requires vendor setup and routing; harder to keep OSS-first developer UX.
- **Self-hosted containers:** Similar to LocalRunner; maintenance burden shifts to users.

## Compatibility & Migration
- Default remains `LocalRunner`; projects without `runner` config continue to work.
- E2B is opt-in via `osiris.yaml` or CLI flag.
- Secrets masking remains as today, with a **migration path to component-spec–driven secrets** (ADR-0009, ADR-0007).

## Open Questions
- Should we support persistent volumes across `run`s for caching heavy downloads? (default: no; prefer ephemeral)
- Standard image vs. per-component images? (default: single curated image; revisit after M3)
- Do we need a "warm sandbox pool" for faster startup in CI?

## Implementation Status
Implementation tracked in **Milestone**: [docs/milestones/m1e-e2b-runner.md](../milestones/m1e-e2b-runner.md)
