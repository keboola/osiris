# ADR-0028: Filesystem Contract v1 & Minimal Git Helpers

## Status

Final
Version: v1 (shipped in Osiris 0.4.0)
Effective: 2025-10-09

## Context

Osiris users need a standard, **machine-friendly and human-readable** filesystem layout so that:

- a new machine can do `git pull` and have **everything essential**,
- teams can **version** deterministic artifacts with Git,
- external AI tools can **understand an Osiris project** from repo contents,
- runtime logs are easy to find for humans, while internal state is clearly isolated.

Pain points observed:

- Everything funneled into `./logs/` mixed deterministic artifacts with ephemeral logs.
- Compiler sometimes wrote to multiple locations, creating ambiguity (“what is the source of truth?”).
- AIOP (observability packs) could overwrite previous results.
- Hidden utility folders (`.osiris_*`) were scattered and unclear in purpose.

### Purpose of the Filesystem Contract

The Filesystem Contract provides a stable interface between local and remote storage backends (such as S3, GCS, etc.), ensuring a consistent layout across different repositories. This consistency facilitates reproducibility of pipeline runs and serves as a backward-compatible automation boundary, allowing tools and services to reliably interact with Osiris project files regardless of environment or deployment.

### Prerequisites & Package Model

Osiris will be distributed as an installable Python package. The preferred modern installation method will use [uv](https://github.com/astral-sh/uv):

```bash
uv tool install osiris
```

This approach provides an isolated, fast, and reproducible CLI environment (similar to `pipx`).
For now, Osiris can also be run from source or via Docker.

The packaging work (PyPI release and versioned tool distribution) will be completed in a later phase.
The `osiris init` command will scaffold new repositories using the installed package version, ensuring alignment between the Osiris toolchain and the filesystem contract.

## Decision

**Breaking Notice:** This ADR replaces the legacy `./logs/**` layout without dual-write or backward compatibility. Migration is required.

Adopt a **Filesystem Contract v1** that:

1. Defines a **clear directory layout** separating deterministic (versionable) artifacts, per-run observability, visible run logs, and hidden internal state.
2. Makes **all paths and naming rules configurable** in `osiris.yaml`.
3. Provide a unified scaffolding command `osiris init` for creating new Osiris projects.
   It initializes the canonical project structure and optionally sets up Git (`--git` flag).
   This replaces older ideas of `osiris repo init`.
4. Leaves **Git remotes** to the user/CI (no push/PR automation in v1). Osiris provides only **minimal helpers**:
   - `osiris repo ensureignore` – merge recommended ignore patterns
   - (optional) `osiris repo commit -m "..."` – local `git add/commit` convenience (no push)

Minimal Git helpers are retained (`osiris repo ensureignore`, `osiris repo commit -m "..."`) for convenience, but `osiris init` is the canonical entrypoint for new projects.

> Autopilot (PRs, shadow branches, CI-gated merges) is **out of scope** for this ADR and will be proposed separately (new ADR-XXXX).

## Canonical Project Layout (defaults)

```
project_root/
├── pipelines/        # AI/human-authored OML sources
├── build/            # deterministic compiled artifacts (versionable)
├── aiop/             # per-run AI Observability Packs (never overwritten)
├── run_logs/         # user-facing full runtime logs & per-run artifacts (retained)
└── .osiris/          # hidden internals (tooling only)
    ├── sessions/     # conversational agent state for Osiris chat
    ├── cache/        # discovery/profiling cache (schemas, samples)
    └── index/        # append-only run indexes & counters
```

## Path Semantics

- **Deterministic artifacts (commit to Git):** `build/`
  Compiled manifest, execution plan, fingerprints, compile metadata, per-step configs. Same inputs → same outputs.
- **Per-run AIOP (optional to commit):** `aiop/`
  One directory **per run**, never overwritten; includes `summary.json`, `run-card.md`, optional NDJSON annex.
- **User-facing logs (ephemeral):** `run_logs/`
  Full event/metric streams, debug and service logs, per-step temp artifacts; retained by policy.
- **Internal state (hidden):** `.osiris/{sessions,cache,index}`
  State for chat, discovery/cache, and append-only indexes over runs; not intended for Git.

## Profiles & Tags

- **Profiles** are first-class (e.g., `dev`, `staging`, `prod`, `finance`, `incident_debug`).
  When enabled, a `{profile}/` path segment is inserted under `build/`, `aiop/`, and `run_logs/`.
- **Tags** (e.g., `billing`, `ml`, `poc`) are tracked in indexes and metadata, not used as path segments (to avoid combinatorial explosion).

## Naming Tokens

Naming templates accept these tokens (safe for filenames):

- `{pipeline_slug}` e.g. `orders_etl`
- `{profile}` e.g. `prod` (empty if profiles disabled)
- `{manifest_hash}` full hex digest, e.g. `3f92ac1b6b0e...`
- `{manifest_short}` shortened hash (length configurable)
- `{run_id}` unique run identifier (format configurable)
- `{run_ts}` run start timestamp (format configurable; FS-safe)
- `{status}` `success|failed|skipped` (optional)
- `{branch}` current Git branch if detectable (optional)
- `{user}` launcher username (optional)
- `{tags}` normalized tags, e.g. `billing+critical` (optional)

Unavailable tokens resolve to an empty string without error.

## `osiris.yaml` Configuration (authoritative)

All paths and naming rules are configured in `osiris.yaml`. Defaults shown below; comments explain intent.

```yaml
# ---- Osiris Filesystem Contract v1 -----------------------------------------
# All paths resolve relative to `base_path`. If omitted, the project root is used.

filesystem:
  # Absolute root for all Osiris project files (useful for servers/CI).
  # Example: "/srv/osiris/acme" or leave empty to use the repo root.
  base_path: ""

  # Profiles: explicitly list allowed profile names and the default.
  # When enabled, Osiris injects a "{profile}/" path segment in build/aiop/run_logs.
  profiles:
    enabled: true
    values: ["dev", "staging", "prod", "ml", "finance", "incident_debug"]
    default: "dev"

  # Where AI/human-authored OML lives (pipeline sources).
  # With profiles enabled, you may mirror pipelines/<profile>/..., or keep a flat pipelines/.
  pipelines_dir: "pipelines"

  # Deterministic, versionable build artifacts:
  # build/pipelines/[{profile}/]<slug>/<manifest_short>-<manifest_hash>/{manifest.yaml, plan.json, fingerprints.json, run_summary.json, cfg/...}
  build_dir: "build"

  # Per-run AI Observability Packs (NEVER overwritten):
  # aiop/[{profile}/]<slug>/<manifest_short>-<manifest_hash>/<run_id>/{summary.json, run-card.md, annex/...}
  aiop_dir: "aiop"

  # User-facing full runtime logs by run (cleaned by retention):
  # run_logs/[{profile}/]<slug>/{run_ts}_{run_id}-{manifest_short}/{events.jsonl, metrics.jsonl, debug.log, osiris.log, artifacts/...}
  run_logs_dir: "run_logs"

  # Internal hidden state (advanced users rarely need to touch this):
  # sessions: conversational/chat session state for Osiris chat/agents
  # cache:    discovery/profiling cache (table schemas, sampled stats)
  # index:    append-only run indexes and counters for fast listing/queries
  sessions_dir: ".osiris/sessions"
  cache_dir: ".osiris/cache"
  index_dir: ".osiris/index"

  # Naming templates (human-friendly yet machine-stable).
  # Available tokens:
  #   {pipeline_slug} {profile} {manifest_hash} {manifest_short} {run_id} {run_ts} {status} {branch} {user} {tags}
  naming:
    # Build folder for a compiled manifest (relative to build_dir/pipelines[/profile]):
    manifest_dir: "{pipeline_slug}/{manifest_short}-{manifest_hash}"

    # Run folder under run_logs_dir[/profile]:
    run_dir: "{pipeline_slug}/{run_ts}_{run_id}-{manifest_short}"

    # Per-run folder name under aiop/.../<manifest>/:
    aiop_run_dir: "{run_id}"

    # Timestamp format for {run_ts} (no colons). Options: "iso_basic_z" -> YYYY-mm-ddTHH-MM-SSZ, or "none".
    run_ts_format: "iso_basic_z"

    # Number of characters used in {manifest_short}:
    manifest_short_len: 7

  # What to write into build/ (deterministic artifacts):
  artifacts:
    # Save compiled manifest (deterministic plan of execution).
    manifest: true
    # Save normalized DAG/execution plan (JSON).
    plan: true
    # Save SHA-256 fingerprints of inputs (for caching/consistency checks).
    fingerprints: true
    # Save compile-time metadata (compiler version, inputs, timestamps, profile, tags).
    run_summary: true
    # Save per-step effective configs (useful for diffs and debuggability).
    cfg: true
    # Optionally copy last N events to build/ for quick inspection (0 = disabled).
    save_events_tail: 0

  # Retention applies ONLY to run_logs_dir and aiop annex shards (build/ is permanent).
  # Execute retention via:
  #   - "osiris maintenance clean" (manual or scheduled), or
  #   - a library call from your own cron/systemd timer.
  retention:
    run_logs_days: 7 # delete run_logs older than N days
    aiop_keep_runs_per_pipeline: 200 # keep last N runs per pipeline in aiop/
    annex_keep_days: 14 # delete NDJSON annex shards older than N days

ids:
  # Run identifier format (choose one OR compose multiple; examples):
  # - "ulid"        -> 01J9Z8KQ8R1WQH6K9Z7Q2R1X7F
  # - "iso_ulid"    -> 2025-10-07T14-22-19Z_01J9Z8KQ8R1WQH6K9Z7Q2R1X7F
  # - "uuidv4"      -> 550e8400-e29b-41d4-a716-446655440000
  # - "snowflake"   -> 193514046488576000 (time-ordered 64-bit)
  # - "incremental" -> run-000123  (requires the indexer to maintain counters)
  #
  # You may also define a composite format, e.g. ["incremental", "ulid"]
  # which renders as "run-000124_01J9Z8KQ8R1..." (order matters).
  run_id_format: "iso_ulid" # can be a string OR a list for composite

  # Manifest fingerprint algorithm (used for build folder naming):
  # - "sha256_slug": hex sha256; {manifest_short} length controlled above
  manifest_hash_algo: "sha256_slug"
```

## Indexes

- `.osiris/index/runs.jsonl` (append-only) includes at least:
  `{ run_id, pipeline_slug, profile?, manifest_hash, ts_start, ts_end, status, tags[] }`
- Per-pipeline indexes: `.osiris/index/by_pipeline/<pipeline_slug>.jsonl`
- Optional `latest` pointers per pipeline may be provided as text files.

## CLI & Tooling Impact

- `osiris compile <pipelines/<slug>.yaml>` → writes into `build/pipelines[/profile]/<slug>/<short>-<hash>/…` and updates `LATEST`.
- `osiris run --pipeline <slug> [-p/--profile <name>]` → logs into `run_logs[/profile]/<slug>/<ts>_<runId>-<short>/…` and writes AIOP per-run.
- `osiris runs list [--pipeline <slug>] [--profile <name>]` → reads from `.osiris/index/…`.
- `osiris logs list [--pipeline <slug>] [--run <id>]` → reads from `run_logs/…`.
- Minimal Git helpers have been reduced to:
  - `osiris repo ensureignore` – merge recommended ignore patterns
  - (optional) `osiris repo commit -m "..."` – local add+commit only (no push)

## Migration

This ADR is a **breaking change** from legacy `./logs/` layouts and intentionally ships without dual-write.
Projects must move to the new directories. CLI and readers use only the new paths.

Recommended steps:

1. Upgrade Osiris to a version supporting Filesystem Contract v1.
2. Run `osiris repo ensureignore` to merge updated `.gitignore` patterns.
3. Adjust `osiris.yaml` to your desired paths and profiles.
4. Re-compile pipelines and run; verify artifacts appear in `build/`, logs in `run_logs/`, AIOP in `aiop/`.
5. (Optional) Commit `build/`/`aiop/` per your team policy.

## Consequences

### Positive

- Clear separation of concerns and predictable locations.
- Easy for humans to navigate; easy for tools to parse.
- Git-friendly: version only what matters; keep logs ephemeral.
- Profiles and tags enable large repos with many OML files.

### Negative

- One-time migration effort for existing projects.
- Users must learn the new structure and `osiris.yaml` config.

### Neutral

- Git remotes and PR workflows remain user/CI responsibility.

## Alternatives Considered

- Keep legacy `./logs/` mixed layout – rejected (ambiguous, poor UX).
- Build-in Git autopilot (PRs/merge automation) – deferred to a future ADR.

## References

- ADR-0020: Connection resolution (related)
- ADR-0029: Memory store (integration later)
- Previous ADR-0028 draft (Git Integration & Autopilot) – superseded by this Filesystem Contract v1 scope
