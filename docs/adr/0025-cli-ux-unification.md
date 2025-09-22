# ADR-0025: CLI UX Unification (Run vs Logs)

**Status:** Accepted  
**Date:** 2025-09-09  
**Authors:** Osiris Core Team

## Context
The current CLI interface splits commands into `run` (execute pipeline) and `runs` (inspect past runs). This leads to confusing UX: `run` vs `runs` are too similar, users mix them up, and the distinction is not obvious. In addition, inspection commands are not consistently grouped, even though all rely on the session logging subsystem (`./logs/`).

We want to simplify mental model:
- `run` = action (execute something).
- `logs` = inspection (view past sessions, results, artifacts).

## Decision
- Keep `osiris run` as the only entry point for executing a pipeline.
- Introduce `osiris logs` namespace for all inspection-related commands:
  - `osiris logs last [--json] [--label <name>]`
  - `osiris logs list [--limit N] [--label <name>] [--since ISO] [--status ok|error|running]`
  - `osiris logs show <session_id> [--json]`
  - `osiris logs open <session_id|last|--label <name>]`
  - `osiris logs html [--out dist/logs] [--open] [--label <name>] [--sessions N]`
  - `osiris logs tail <session_id>`
- Support labels (`--label`) and metadata (`--meta k=v`) on `run`. These do not replace `session_id` but are stored in `metadata.json`.
- Maintain `logs/index.json` as an append-only session index.
- Standardize `metadata.json` structure in each session (keys: session_id, labels[], status, started_at, finished_at, duration_ms, rows_in, rows_out, summary).
- Provide deprecation shim: `osiris runs …` prints deprecation warning and calls new `logs` command.

## Consequences
- Users get a simpler model: run pipelines with `run`, inspect results with `logs`.
- Backward compatibility preserved temporarily via alias with deprecation notice.
- Code structure cleaner: one namespace for execution (`run`) and one for inspection (`logs`).
- Tests and documentation must be updated to reflect new CLI structure.
- HTML logs browser consumes the same JSON schema as `logs last --json`.

## Alternatives Considered
- Keep `runs` namespace: rejected due to confusing similarity.
- Rename to `history`: rejected, would diverge from existing logs folder structure.

## References
- Milestone M1d – Logs & CLI Unification
- ADR-0003 Session-Scoped Logging
- Implementation tracked in Milestone: docs/milestones/m1d-logs-and-cli-unification.md

## Notes on Milestone M1

**Implementation Status**: Fully implemented in Milestone M1.

The CLI UX unification has been completed with Click library completely removed and Rich framework used exclusively:
- **Core implementation**: `osiris/cli/main.py` - Rich-only CLI implementation without Click dependency
- **Logs commands**: `osiris/cli/logs.py` - Full implementation of `osiris logs` namespace with list, show, gc, html commands
- **Test coverage**: `tests/cli/` - Comprehensive tests for all CLI commands

Key features delivered:
- Complete removal of Click library dependency
- Rich framework provides all CLI functionality with beautiful terminal output
- `osiris logs` namespace for all inspection commands:
  - `osiris logs list` - List sessions with wrapping, filtering, and status
  - `osiris logs show` - Display session details with metrics and events
  - `osiris logs gc` - Cleanup old sessions
  - `osiris logs html` - Generate HTML reports from sessions
- Unified `osiris run` command handles both OML and compiled manifests
- Session-scoped logging with structured JSONL events and metrics
- Beautiful Rich tables, colors, and progress indicators throughout
- Consistent JSON output support across all commands with `--json` flag
