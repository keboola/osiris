# Milestone: Filesystem Contract v1 — Implementation Plan (single-PR)

## 1. Scope & Non-Goals

- Intentional Breaking change
- Implement Filesystem Contract v1 end-to-end for local workflows on branch `feature/filesystem-contract`.
- Replace every read/write of legacy `./logs/**` with the new `build/`, `run_logs/`, `aiop/`, `.osiris/{sessions,cache,index}` layout from ADR-0028.
- Introduce configurable filesystem, profile, ID, naming, and retention behavior driven by `osiris.yaml`.
- Wire compile/run/CLI/index/retention flows to the new contract; ensure the install story is `uv tool install osiris`.
- Explicit non-goals: no dual-write to legacy paths, no support for legacy log readers, no remote storage, no autopilot/PR automation changes.

## 2. Module-level Design

### Contract Layout & Invariants

```
project_root/
├── pipelines/        # OML sources (human + AI authored)
├── build/            # deterministic, versionable artifacts (never pruned)
├── aiop/             # per-run AI observability packs (append-only)
├── run_logs/         # human-readable per-run logs & temp artifacts (retained/pruned)
└── .osiris/          # hidden internals (sessions, cache, index)
    ├── sessions/
    ├── cache/
    └── index/       # runs.jsonl, by_pipeline/*.jsonl, latest/*.txt, counters.sqlite
```

- `build/`, `aiop/`, and `run_logs/` insert `{profile}/` segments when profiles are enabled; default profile is mandatory when enabled.
- Deterministic build artifacts are commit-friendly; `run_logs/` and `aiop/**/annex/` are subject to retention only.
- `.osiris/index` is the sole source of truth for run discovery (no extra pointers under `logs/`).

### Services & Components

- Typed config loader (`osiris/core/fs_config.py`, new): define models for `FilesystemConfig`, `ProfilesConfig`, `IdsConfig`, `NamingConfig`, `RetentionConfig`. `load_osiris_config()` wraps `osiris/core/config.py:28`, produces typed config + raw dict, normalizes `base_path`, ensures relative directories resolve against project root, enforces defaults.
- Path resolution service (`osiris/core/fs_paths.py`, new): `FilesystemContract` consumes typed config and exposes `manifest_paths()`, `run_log_paths()`, `aiop_paths()`, `index_paths()`. Internally uses `TokenRenderer` to substitute naming tokens, insert profile segments, collapse duplicate separators, and optionally pre-create directories for callers.
- Token renderer: `TokenRenderer.render(tokens: dict[str, str]) -> str` tolerates missing tokens (renders as empty string) and runs `slugify_token()` for filesystem safety. Shared across compile, run, AIOP, and index flows.
- Run ID + counters (`osiris/core/run_ids.py`, new): `RunIdGenerator` loads `IdsConfig.run_id_format` (string or `list[str]`), composes supported tokens (`incremental`, `ulid`, `iso_ulid`, `uuidv4`, `snowflake`). `incremental` relies on `.osiris/index/counters.sqlite` guarded by SQLite `BEGIN IMMEDIATE` + WAL for multi-process safety. Returns `(run_id, issued_at_ts)` for downstream use.
  - PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;
  - Use BEGIN IMMEDIATE during increments to ensure atomicity.
- Index writer/reader (`osiris/core/run_index.py`, new): `RunIndexWriter.append()` writes NDJSON records to `.osiris/index/runs.jsonl`, mirrors them to `.osiris/index/by_pipeline/<slug>.jsonl`, and maintains `.osiris/index/latest/<slug>.txt`. Uses file-level locks (fcntl) and fsync to ensure durable writes. `RunIndexReader` backs new CLI list/show flows.
- Compiler outputs (`osiris/core/compiler_v0.py:38`): refactor `CompilerV0` to accept `FilesystemContract` + pipeline/profile context. `_write_outputs` delegates to `BuildArtifactWriter` housed in `fs_paths.py` to place deterministic artifacts under `build/pipelines[/profile]/{pipeline_slug}/{manifest_short}-{manifest_hash}/`. Manifest metadata persists `manifest_hash` + `manifest_short`.
- Runner logging (`osiris/core/session_logging.py:36`): extend `SessionContext` to accept contract, `run_id`, `pipeline_slug`, `profile`, `manifest_hash`. Base directory becomes `contract.run_logs_root(profile, pipeline_slug)`; session directory uses naming template `run_dir`. Provide `emit_manifest_snapshot()` so compile/run flows can copy canonical `manifest.yaml` into run logs without recomputation.
- AIOP exporter (`osiris/core/aiop_export.py:20`): pivot to contract-driven paths (`aiop/[profile/]<slug>/<manifest_short>-<manifest_hash>/<run_id>/`). Persist `summary.json`, `run-card.md`, optional annex shards; surface resolved paths back to the caller for indexing.
- Retention command (`osiris/core/retention.py`, new): implement selectors for `run_logs/` and `aiop/.../annex`. `RetentionPlan.compute()` builds action list; `apply(dry_run: bool)` executes or prints it. Exposed through new CLI module `osiris/cli/maintenance.py` (`osiris maintenance clean`).
- CLI wiring (`osiris/cli/*.py`):
  - `main.py:150` registers `runs`, `logs`, `aiop`, `maintenance`, `pipelines tag`; help text highlights new directories and contract invariants.
  - `compile.py:245` and `run.py:454` obtain `FilesystemContract`, `RunIdGenerator`, `RunIndexWriter` through shared helper to orchestrate compile/run flows with the new paths.
  - `logs` command splits into `run_logs` (per-run artifacts) and `runs` (index-backed listing) modules; both rely on the contract + index readers.
  - New `aiop` subcommands list/show per-run observability packs using contract paths.
  - `pipelines tag` updates run metadata (tags) via index writer without introducing new path segments.

## 3. Exact File/Function Checklist

All file/line references are approximate and may drift after refactors; treat them as pointers.

### New Modules

- **`osiris/core/fs_config.py`**: typed config models, `load_osiris_config()` factory.
- **`osiris/core/fs_paths.py`**: `TokenRenderer`, `FilesystemContract`, helpers (`resolve_build_artifacts`, `resolve_run_logs`, `resolve_aiop`, `resolve_index_paths`, `ensure_dir`, `slugify_token`, `compute_manifest_hash`).
- **`osiris/core/run_ids.py`**: `RunIdGenerator`, `CounterStore`, tests for concurrency.
- **`osiris/core/run_index.py`**: `RunRecord` dataclass, `RunIndexWriter`, `RunIndexReader`, `latest_manifest_path()` helper.
- **`osiris/core/retention.py`**: `RetentionPlan`, `RetentionAction`, selection/pruning logic, CLI integration hooks.
- **`osiris/cli/runs.py`**, **`osiris/cli/aiop.py`**, **`osiris/cli/maintenance.py`**, **`osiris/cli/pipelines.py`**: new CLI entry modules as described.

### Modified Core Modules

- `osiris/core/config.py`: add `load_raw_config()`, integrate filesystem contract defaults, retire `render_path()` in favor of `FilesystemContract`.
- `osiris/core/session_logging.py`: update constructor signature, directory derivation, metadata capture, and provide `emit_manifest_snapshot()`.
- `osiris/core/compiler_v0.py`: accept contract + pipeline/profile context, call `resolve_build_artifacts()`, compute manifest hash via shared helper, drop writes to `logs/`.
- `osiris/core/runner_v0.py`: accept `FilesystemContract`, use contract paths for artifacts, emit run metadata into index via `RunIndexWriter` in conjunction with CLI layer.
- `osiris/core/aiop_export.py`: replace direct path formatting with contract-based resolution; ensure exported structures match schemas in §4.
- `osiris/core/run_export_v2.py`: update manifest references and evidence links to new build paths.
- `osiris/core/logs_serialize.py` & `osiris/core/session_reader.py`: rename to `run_logs_serializer.py` / `run_logs_reader.py`, update to read from `run_logs/` with optional profile segments.

### Call-site Integration in Existing Flows

- `osiris/cli/compile.py:compile_command`
  - Instantiate `FilesystemContract` + `RunIdGenerator` via helper `load_contract_and_ids()`.
  - Pass contract + pipeline/profile context into `CompilerV0`.
  - After successful compile, call `RunIndexWriter.write_latest_manifest(pipeline_slug, profile, manifest_path, manifest_hash)` and remove writes to `logs/.last_compile.json`.
- `osiris/cli/run.py:run_command`
  - Instantiate contract + run ID generator at start; generate run ID before session creation.
  - Create `SessionContext` with contract-derived run log path, injecting `run_id`, `pipeline_slug`, `profile`, `manifest_hash` (set after compile/manifest load).
  - After run completion, collect metrics (duration, status, tags) and call `RunIndexWriter.append()` with resolved `run_logs_path`, `aiop_path`, `build_manifest_path`.
  - Update `find_last_compile_manifest()` to read `.osiris/index/latest/<pipeline>.txt` instead of `logs/.last_compile.json`.
- `osiris/cli/logs.py` (becomes `run_logs.py`): adjust default base path to `FilesystemContract.resolve_run_logs_root()`, support `--profile` filters, remove legacy assumptions about `logs/` root.
- `osiris/cli/main.py`: import new command modules, wire parser help to highlight contract tokens, ensure `--profile` option defaults to config default.
- `osiris/core/aiop_export.py`: request manifest metadata from `CompilerV0` output or `RunContext`, feed `RunIndexWriter` with resulting paths.
- `osiris/core/config.py:resolve_aiop_config()`: update to consume filesystem contract naming rather than `render_path()`.
- `docs/guides` & CLI help text: update to new directory names.

### Tests & Tooling Updates

- Add unit/integration tests enumerated in §9; relocate fixtures to new contract layout under `tests/golden/`.
- Create `tests/regression/test_no_legacy_logs.py` ensuring `logs/` writes are banned.
- Update `Makefile` targets to reference `osiris maintenance clean` where pertinent.

## 4. Data Structures & Schemas

- `.osiris/index/runs.jsonl` (append-only NDJSON):
  ```json
  {
    "run_id": "run-000123_01J9Z8KQ8R1",
    "pipeline_slug": "orders_etl",
    "profile": "prod",
    "manifest_hash": "3f92ac1b6b0e...",
    "manifest_short": "3f92ac1",
    "run_ts": "2025-02-11T18-42-33Z",
    "status": "success",
    "duration_ms": 183245,
    "run_logs_path": "run_logs/prod/orders_etl/20250211T184233Z_run-000123_01J9Z8KQ8R1-3f92ac1",
    "aiop_path": "aiop/prod/orders_etl/3f92ac1-3f92ac1b6b0e/run-000123_01J9Z8KQ8R1",
    "build_manifest_path": "build/pipelines/prod/orders_etl/3f92ac1-3f92ac1b6b0e/manifest.yaml",
    "tags": ["billing", "ml"],
    "branch": "feature/filesystem-contract"
  }
  ```
  - Additional optional fields: `user`, `git_commit`, `runtime_env` (extendable metadata map).
- `.osiris/index/by_pipeline/<pipeline_slug>.jsonl`: same schema, pipeline-filtered, newest-first.
- `.osiris/index/latest/<pipeline_slug>.txt`: three lines — manifest path, manifest hash, active profile.
- `.osiris/index/counters.sqlite` schema:
  ```sql
  CREATE TABLE IF NOT EXISTS counters (
      pipeline_slug TEXT PRIMARY KEY,
      last_value INTEGER NOT NULL,
      updated_at TEXT NOT NULL
  );
  ```
  Use `INSERT INTO counters(...) VALUES(...) ON CONFLICT(pipeline_slug)
DO UPDATE SET last_value = last_value + 1, updated_at = excluded.updated_at;`.
- `aiop/.../<run_id>/summary.json`:
  ```json
  {
    "run_id": "run-000123_01J9Z8KQ8R1",
    "pipeline_slug": "orders_etl",
    "profile": "prod",
    "manifest_hash": "3f92ac1b6b0e...",
    "manifest_short": "3f92ac1",
    "started_at": "2025-02-11T18:42:33Z",
    "completed_at": "2025-02-11T18:45:36Z",
    "status": "success",
    "rows_in": 123456,
    "rows_out": 123450,
    "duration_ms": 183245,
    "tags": ["billing", "ml"]
  }
  ```
- `TokenContext` dataclasses provide source data for naming: `pipeline_slug`, `profile`, `manifest_hash`, `manifest_short`, `run_id`, `run_ts`, `status`, `branch`, `user`, `tags`, `manifest_version`, etc.

## 5. Config Resolution Rules

- `filesystem.base_path`: when non-empty, treat as absolute root; otherwise default to directory containing `osiris.yaml`. All relative paths resolve against `base_path`.
- `profiles.enabled`:
  - `False`: `profile` token renders as empty string, profile segment omitted.
  - `True`: enforce `profiles.values` (list of allowed names) and `profiles.default`; CLI fails fast on unknown profile.
- `ids.run_id_format`: accept string or list. Empty string defaults to `["iso_ulid"]`. Validate tokens at load; raise `ConfigError` on unsupported values.
- Naming tokens map to runtime values; missing values render as empty string and `TokenRenderer` collapses duplicate separators. `run_ts_format` supports `iso_basic_z`, `epoch_ms`, or custom `strftime` pattern; unknown formats log warning and fall back to ISO Basic. `manifest_short_len` constrained to `3 ≤ n ≤ 16`.
- Retention config (`run_logs_days`, `aiop_keep_runs_per_pipeline`, `annex_keep_days`) must be non-negative ints; zero disables the rule.
- Environment overrides (highest precedence after CLI flags): `OSIRIS_PROFILE`, `OSIRIS_FILESYSTEM_BASE`, `OSIRIS_RUN_ID_FORMAT`, `OSIRIS_RETENTION_RUN_LOGS_DAYS`.

### Token Source Map

| Token              | Source                                              | Example             | Notes                                   |
| ------------------ | --------------------------------------------------- | ------------------- | --------------------------------------- |
| `{pipeline_slug}`  | Derived from OML filename or manifest `pipeline.id` | `orders_etl`        | Slugify to `[a-z0-9_-]`.                |
| `{profile}`        | Selected profile name                               | `prod`              | Empty if profiles disabled.             |
| `{manifest_hash}`  | `compute_manifest_hash(manifest, algo)`             | `3f92ac1b6b0e...`   | Deterministic per manifest/profile.     |
| `{manifest_short}` | Prefix of `manifest_hash`                           | `3f92ac1`           | Length from config.                     |
| `{run_id}`         | `RunIdGenerator.generate()`                         | `run-000123_01J...` | Composite segments joined by `_`.       |
| `{run_ts}`         | Run start timestamp                                 | `20250211T184233Z`  | Format from config; fallback ISO Basic. |
| `{status}`         | Final run status                                    | `success`           | Populated post-run.                     |
| `{branch}`         | `git rev-parse --abbrev-ref HEAD` (optional)        | `feature/x`         | Empty if git not available.             |
| `{user}`           | `getpass.getuser()`                                 | `padak`             | Optional.                               |
| `{tags}`           | CLI `--tags` normalized (`+` joined)                | `billing+ml`        | Optional.                               |

### Sample `osiris.yaml` (contract defaults)

```yaml
version: "2.0"

filesystem:
  base_path: ""
  pipelines_dir: "pipelines"
  build_dir: "build"
  aiop_dir: "aiop"
  run_logs_dir: "run_logs"
  sessions_dir: ".osiris/sessions"
  cache_dir: ".osiris/cache"
  index_dir: ".osiris/index"

  profiles:
    enabled: true
    values: ["dev", "staging", "prod", "ml", "finance", "incident_debug"]
    default: "dev"

  naming:
    manifest_dir: "{pipeline_slug}/{manifest_short}-{manifest_hash}"
    run_dir: "{pipeline_slug}/{run_ts}_{run_id}-{manifest_short}"
    aiop_run_dir: "{run_id}"
    run_ts_format: "iso_basic_z"
    manifest_short_len: 7

  artifacts:
    manifest: true
    plan: true
    fingerprints: true
    run_summary: true
    cfg: true
    save_events_tail: 0

  retention:
    run_logs_days: 7
    aiop_keep_runs_per_pipeline: 200
    annex_keep_days: 14

ids:
  run_id_format: ["incremental", "ulid"]
  manifest_hash_algo: "sha256_slug"

determinism:
  manifest_short_len: 7
  manifest_rehydration: true

retention:
  dry_run_default: true
  batch_size: 50
```

- `determinism`/`retention` extension blocks illustrate optional future knobs; implementation must tolerate unknown keys for forward compatibility.

## 6. Determinism & Hashing

- Manifest hash computed via `sha256` over canonical JSON of manifest payload concatenated with active profile. Algorithm name derived from `ids.manifest_hash_algo` (`sha256_slug` initial support). Result stored lowercase hex.
- `manifest_short = manifest_hash[:manifest_short_len]` with default length 7; enforce invariants in loader.
- Build directory layout: `build/pipelines/[profile/]pipeline_slug/manifest_short-manifest_hash/{manifest.yaml, plan.json, fingerprints.json, run_summary.json, cfg/...}`. Identical inputs yield identical paths.
- Shared helper `compute_manifest_hash(manifest: dict, algo: str)` lives in `fs_paths.py` and is the only place the hash is computed. `CompilerV0` adds `manifest_hash` + `manifest_short` into manifest metadata for downstream consumers.
- CLI `runs list` and `aiop show` trust manifest hash recorded in index; when regenerating, verify stored hash matches recomputed value to detect drift.

## 7. Retention Semantics

- Scope: only delete `run_logs/` per-run directories and `aiop/.../<run_id>/annex/**` shards. Never touch `build/`, `aiop/.../summary.json`, `aiop/.../run-card.md`, `.osiris/index/**`.
- Selection logic:

  ```python
  cutoff_logs = now - timedelta(days=config.retention.run_logs_days)
  for run_dir in contract.iter_run_logs():
      if run_dir.finished_at and run_dir.finished_at < cutoff_logs:
          if run_dir.run_id not in keep_active_runs:
              actions.delete(run_dir.path)

  for manifest_dir in contract.iter_aiop_manifests():
      runs = sort_runs_desc(manifest_dir)
      for idx, run in enumerate(runs):
          if idx >= config.retention.aiop_keep_runs_per_pipeline:
              actions.delete(run.path)
          else:
              prune_annex(run, cutoff=config.retention.annex_keep_days)
  ```

- `keep_active_runs` set combines entries referenced by `.osiris/index/latest/**/*.txt` and newest `aiop_keep_runs_per_pipeline` runs for each pipeline/profile.
- `RetentionPlan` supports dry-run and is idempotent; repeated execution after deletion yields empty action list. Provide structured output (JSON when `--json` combined with `--dry-run`).
- `osiris maintenance clean --dry-run` prints planned deletions; runtime overrides: `--logs-days`, `--keep-runs`, `--annex-days`, `--json`.

## 8. CLI UX

- **Global:** `osiris --json` and `--verbose` unchanged; global help copy references contract layout.
- **Compile:** `osiris compile pipelines/orders.yaml --profile prod`
  - Output includes build manifest path, manifest hash, and pointer update location `.osiris/index/latest/orders_etl.txt`.
  - `--out` copies artifacts from build path (without changing canonical location).
  - Unknown profile error: `ConfigError: Unknown profile 'qa'. Allowed profiles: dev, staging, prod (filesystem.profiles.values).`
- **Run:** `osiris run pipelines/orders.yaml -p prod --tags billing,ml`
  - Options: `--profile/-p`, `--tags`, `--run-id-format`, `--json`, `--dry-run` (planning), `--force-recompile`.
  - Success summary prints run logs path, aiop path, build manifest path, manifest hash, run duration.
  - Invalid run ID token error: `ConfigError: Unsupported run_id_format token 'ksuid'. Supported: incremental, ulid, iso_ulid, uuidv4, snowflake.`
- **Runs CLI:**
  - `osiris runs list [--pipeline orders_etl] [--profile prod] [--limit 20] [--json]` shows indexed runs.
  - `osiris runs show <run_id>` prints metadata + resolved paths; `--json` emits record from `.osiris/index/runs.jsonl`.
- **Logs CLI:** `osiris logs list` operates on `run_logs/`; supports filtering by pipeline/profile/run-id; `logs show --tail` follows `run_logs/.../osiris.log`.
- **AIOP CLI:** `osiris aiop list` enumerates contract directories, `osiris aiop show <run_id>` outputs `summary.json`. `aiop export` (if retained) writes zipped bundle in-place.
- **Maintenance CLI:** `osiris maintenance clean [--dry-run] [--keep-runs 100] [--logs-days 30] [--annex-days 7] [--json]` executes retention plan.
- **Pipelines CLI:** `osiris pipelines tag orders_etl --add billing --remove deprecated` updates tags stored in index records (no filesystem change).
- CLI help references environment variables: `OSIRIS_PROFILE`, `OSIRIS_BASE_PATH`, `OSIRIS_RETENTION_RUN_LOGS_DAYS`, `OSIRIS_RUN_ID_FORMAT`.

## 9. Testing Plan

- **Unit tests**
  - `tests/core/test_fs_config.py`: covers defaults, profile enforcement, invalid token handling.
  - `tests/core/test_token_renderer.py`: ensures missing tokens render empty strings, separators collapse, slugification works.
  - `tests/core/test_run_ids.py`: composite ID generation, SQLite concurrency stress (threads + multiprocessing).
  - `tests/core/test_run_index.py`: append semantics, crash-safe writes, latest pointer updates, metadata integrity.
  - `tests/core/test_retention.py`: retention plan selection, dry-run idempotency.
  - `tests/core/test_session_context.py`: verifies contract-based directory creation.
- **Golden tests**
  - `tests/golden/build_dev_orders/`: canonical build tree snapshot.
  - `tests/golden/run_logs_dev_orders/`: run logs layout & filenames.
  - `tests/golden/aiop_orders_run/`: summary/run-card/annex structure.
- **Integration tests**
  - `tests/integration/test_compile_run_profiles.py`: compile + run across profiles, verify outputs, manifest hash, index records.
  - `tests/integration/test_runs_cli.py`: end-to-end CLI listing with JSON output.
  - `tests/integration/test_retention_cli.py`: create aged runs, verify `maintenance clean` dry-run/apply behavior.
  - `tests/integration/test_last_manifest_pointer.py`: ensures `.osiris/index/latest/*.txt` resolves and `find_last_compile_manifest()` uses it.
- **Parity & security**
  - Extend `tests/integration/test_e2b_parity.py`: compare local vs E2B `build/`, `run_logs/`, `aiop/` trees (ignore annex timestamp differences).
  - Update `tests/core/test_redaction.py`: ensure secret masking persists in `run_logs` and `summary.json`.
- **Performance**
  - `tests/perf/test_index_append.py`: keep `RunIndexWriter.append()` under ~5 ms and confirm overhead <2% vs baseline.

## 10. Migration & Tooling

- CI guard: `tests/regression/test_no_legacy_logs.py` fails on writes to `logs/`; optional pre-commit `rg "logs/" osiris/` (allowlist contract modules).
- `.gitignore`: update root + `docs/templates/.gitignore` to ignore `run_logs/`, `aiop/**/annex/`, `.osiris/cache/`, `.osiris/index/counters.sqlite`; leave `build/` tracked per team policy.
- Sample config: ship `docs/samples/osiris.filesystem.yaml` (above snippet) and reference it from `osiris init` scaffolder.
- Developer tooling: update `osiris repo ensureignore` to merge new ignore patterns; refresh `Makefile` targets and docs to reference `uv tool install osiris`.
- Documentation: set `docs/adr/0028-filesystem-contract.md` status to **Accepted** and link to this milestone; add `docs/guides/filesystem_contract_v1.md` with CLI walkthrough.
- Migration helper: optional `scripts/migrate_logs_to_contract.py` to move `logs/**` into contract layout (document manual usage, do not run automatically).

## 11. Acceptance Criteria / DoD

- [ ] Compile/run commands write exclusively under `build/`, `run_logs/`, `aiop/`, `.osiris/**`.
- [ ] `.osiris/index/runs.jsonl` populated with new schema; `osiris runs list` shows correct metadata with profiles + tags.
- [ ] `.osiris/index/counters.sqlite` increments per pipeline safely under parallel runs (tests cover).
- [ ] `SessionContext` creates directories via naming templates; `osiris logs show` accesses run logs successfully.
- [ ] AIOP exporter writes `summary.json` and `run-card.md` at contract path.
- [ ] Retention command deletes only configured `run_logs`/annex targets; dry-run output verified.
- [ ] CI guard confirms no remaining references to legacy `logs/`.
- [ ] Sample `osiris.yaml` validated by unit/integration tests; invalid configs raise actionable errors.
- [ ] Integration suite shows local vs E2B filesystem parity.
- [ ] Documentation (CLI help, ADR, guides) updated to new layout and profiles guidance.

## 12. Risks & Rollback

- Risks:
  - Path resolver bugs directing CLI to wrong directories — mitigated with golden + integration tests.
  - Concurrent runs corrupting `runs.jsonl` or counters — mitigated via file/SQLite locking and stress coverage.
  - Downstream automation depending on `logs/` breaks — mitigated through release notes and migration helper script.
  - Config parsing regressions affecting legacy consumers — mitigated by exposing `load_raw_config()` and regression tests for callers expecting dicts.
- Rollback (single PR):
  - Revert PR via `git revert <merge_commit>` (no DB migrations).
  - If production issues arise, instruct teams to pin previous release, remove newly created directories, and temporarily restore legacy behavior while a patch is issued.
  - Maintain ADR/docs history to reinstate prior instructions quickly if rollback executed.
  - Rollout as a single PR; rollback via a single git revert <merge_commit>.
- Ensure module/file names match ADR references; if not, align ADR by referencing this milestone as the source of truth.
