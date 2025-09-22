


# Milestone M1d – Logs & CLI Unification

**Status:** Planned  
**Owner:** Osiris Core Team  
**Depends on:** M1c (compile & run MVP)  
**Deliverable:** Unified UX for run vs logs, HTML logs browser

## Links
- Implements: docs/adr/0025-cli-ux-unification.md
- Depends on: docs/milestones/m1c-compile-and-run-mvp.md

## Goals
- Unify CLI: `run` = action, `logs` = inspection.  
- Keep stable `session_id` and add `--label` as metadata.  
- Add quick inspection commands (`logs last`, `logs list`, `logs show`, `logs open`, `logs html`).  
- Ensure consistency between CLI outputs and HTML browser.  
- Deprecate `runs` commands.

## Scope
1. **CLI**
   - `osiris run -f pipeline.yaml --label mydemo [--meta k=v]`
   - `osiris logs last|list|show|open|html|tail`
   - Maintain `logs/index.json` upon session completion.
   - `metadata.json` in each session with keys: `session_id, labels[], status, started_at, finished_at, duration_ms, rows_in, rows_out, summary`.

2. **HTML Logs Browser**
   - Static report (`index.html` + JSON data).
   - Drill-down: session detail, timeline, filters.
   - Consistency with CLI JSON (`logs last --json`).

3. **Backward Compatibility**
   - Alias `osiris runs --last` → message “deprecated, use logs last”.
   - Remove in next minor version.

4. **Tests & Docs**
   - Snapshot tests for CLI JSON outputs.
   - E2E tests for `run --label` + `logs last`.
   - ADR update (CLI UX unification).
   - README + CLAUDE.md update.

## Acceptance Criteria
- `osiris run … --label demo` creates a session with ID + label in metadata.  
- `osiris logs last --json` returns digest matching the defined schema.  
- `osiris logs html --sessions 5 --open` opens a browser with the last sessions.  
- No renaming of session directories; optional symlinks under `./logs/@label/` allowed.  
- `runs` commands display deprecation notice.
- HTML Logs Browser loads overview page in < 2s on a repository with ≤ 50 sessions.
- `osiris logs last --json` conforms to the published JSON schema (validated in CI).
- All legacy `runs` commands print a deprecation notice with a migration hint to `logs` namespace.
