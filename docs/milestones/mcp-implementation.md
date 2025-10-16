# MCP Implementation Checklist — Osiris v0.5.0

> This list captures the production hardening work we'll do **after** we confirm MCP server basic functionality (handshake + tools).
> Scope aligns with ADR-0036 and `docs/milestones/mcp-milestone.md`.

---

## 1) Config-first paths (no hardcoded envs)

- [ ] **Init writes config keys**
  - `osiris init` must ensure in `osiris.yaml`:
    - `filesystem.base_path: "<ABSOLUTE_PROJECT_PATH>"`
    - `filesystem.mcp_logs_dir: ".osiris/mcp/logs"` (relative to `base_path`)
  - Create `<base_path>/.osiris/mcp/logs` if missing.
- [ ] **Server reads from config**
  - `osiris/mcp/{server,telemetry,audit}.py` resolve paths via config loader:
    - `get_base_path()`, `get_mcp_logs_dir()`
  - Env overrides (`OSIRIS_LOG_LEVEL`, `OSIRIS_LOGS_DIR`) only as **soft fallback** with WARNING; config wins.

**Verification**

```bash
osiris init
rg -n "mcp_logs_dir|base_path" osiris.yaml
python osiris.py mcp run --selftest
ls -la "$(yq '.filesystem.base_path' osiris.yaml)/.osiris/mcp/logs"
```

---

## 2) Dogfood CLI in `mcp clients`

- [ ] `osiris mcp clients` outputs Claude Desktop snippet that launches via CLI:
  - `command: "/bin/bash"`
  - `args: ["-lc", "cd <base_path> && exec <venv_python> <base_path>/osiris.py mcp run"]`
  - `transport: { "type": "stdio" }`
  - **No** `OSIRIS_HOME` / `PYTHONPATH` by default.
- [ ] `--json` flag returns **only** the JSON snippet.

**Verification**

```bash
python osiris.py mcp clients --json | jq .
# Expect: osiris.py mcp run and cd <base_path>, no env block
```

---

## 3) Run-anywhere behavior

- [ ] Selftest & server must work from **any** CWD.
  - Selftest spawns server via the same CLI path (not direct module import).
  - Server locates config using `filesystem.base_path`.

**Verification**

```bash
(cd /tmp && python /abs/path/osiris/osiris.py mcp run --selftest)
```

---

## 4) Tests & CI guards

- [ ] Add tests:
  - `tests/cli/test_init_writes_mcp_logs_dir.py`
  - `tests/cli/test_mcp_clients_snippet.py`
  - `tests/mcp/test_server_uses_config_paths.py`
- [ ] CI: verify `osiris.yaml` has absolute `base_path` and `mcp_logs_dir`, and that `osiris mcp clients --json` contains `osiris.py mcp run`.

**Verification**

```bash
pytest -q tests/cli/test_init_writes_mcp_logs_dir.py
pytest -q tests/cli/test_mcp_clients_snippet.py
pytest -q tests/mcp/test_server_uses_config_paths.py
```

---

## 5) Docs

- [ ] Document `filesystem.mcp_logs_dir` in config reference.
- [ ] Update MCP quickstart to say: run `osiris init` first; then use `osiris mcp clients`.
- [ ] Note env fallback + deprecation warning behavior.

---

## 6) Packaging & release polish

- [ ] Ensure `requirements.txt` pins official MCP SDK only (no `fastmcp`).
- [ ] Bump version to **0.5.0** in package metadata.
- [ ] Generate CHANGELOG entry (deprecate `chat`, introduce MCP).
- [ ] Confirm `osiris mcp tools` reflects final tool names and schemas.

**Verification**

```bash
python osiris.py mcp tools --json | jq '.tools | length'
```

---

## 7) Safety & observability nits

- [ ] Telemetry/audit write under `mcp_logs_dir`; rotation/retention honors filesystem contract (if applicable).
- [ ] Log event includes `event_id`, `tool`, `duration_ms`, `bytes_in/out`, and correlation id with `mcp_` prefix.
- [ ] Error codes remain deterministic (sample payload sanity test).

---

## 8) Backward-compat cleanup

- [ ] Ensure legacy envs (`OSIRIS_HOME`, `OSIRIS_LOGS_DIR`) are not required anywhere; emit WARNING when used.
- [ ] Confirm docs have **no** `osiris chat` references (already removed; keep guard in CI).

---

---

## 9) CLI‑first adapter for secrets & connections (no secrets in MCP)

### Problem (current)

- MCP server runs in a sandboxed stdio context (Claude Desktop etc.) without a shell‑loaded `.env`, so environment variable substitution like `${MYSQL_PASSWORD}` in `osiris_connections.yaml` is not resolved.
- Current MCP tools attempt to access connections directly via loaders that expect resolved env vars → empty/broken connection configs and failing `connections_doctor`/`discovery_request`.
- Separately, some tool invocations write logs into ad‑hoc session folders (e.g., `<OSIRIS_HOME>/logs/connections_*`), which violates the filesystem contract centered on config‑driven paths.

### Decision

- **Osiris remains CLI‑first.** MCP is a **thin adapter** that delegates to CLI subcommands for any operation that needs resolved secrets or project configuration.
- **No secrets flow through MCP.** MCP tools **never** require secret values, nor do they read `.env` directly. Resolution happens inside the CLI process.
- **Single source of truth for paths.** MCP server and tools derive all writable locations from `osiris.yaml` `filesystem.*` keys; env variables only act as soft fallbacks with a WARNING.

### Design (high level)

1. **Tool delegation to CLI**

   - `connections_list` → `osiris connections list --json`
   - `connections_doctor` → `osiris connections doctor <id> --json`
   - `discovery_request` → `osiris discovery request --connection <id> --component <id> [--samples N] --json`
   - `oml_validate` / `oml_save` remain in‑process (no secrets); others may remain native where safe.
   - All delegates launched via `subprocess` with:
     - `cwd = <filesystem.base_path>` (from `osiris.yaml`) to ensure stable path resolution,
     - inherited environment so `.env`/shell init (if any) is honored by the CLI process,
     - bounded timeouts and payload size guards.

2. **Error & result bridging**

   - Standardize a bridge layer that maps CLI JSON outputs to MCP result shapes and maps CLI error codes/messages to deterministic MCP error families (`SCHEMA/…`, `DISCOVERY/…`, `POLICY/…`).
   - Include `correlation_id` (prefix `mcp_`), `duration_ms`, `bytes_in/out` in audit.

3. **Filesystem contract compliance**
   - Extend `osiris init` to populate:
     - `filesystem.base_path: "<ABSOLUTE_PROJECT_PATH>"`
     - `filesystem.mcp_logs_dir: ".osiris/mcp/logs"`
   - Ensure MCP server and tools **only** write under `<base_path>/.osiris/mcp/logs/{server.log,audit/,telemetry/,cache/}` (created on first run).
   - Keep current Sections **1) Config-first paths** and **2) Dogfood CLI in `mcp clients`** as prerequisites.

### Implementation plan

- **MCP server**

  - Add `mcp/cli_bridge.py` with helpers: `run_cli_json(args, timeout_s)`, `ensure_base_path()`.
  - Update tools:
    - `connections.py`: implement `list_via_cli()`, `doctor_via_cli(connection_id)`.
    - `discovery.py`: add `request_via_cli(connection_id, component_id, samples)`.
  - Centralize logging path resolution through `MCPFilesystemConfig.from_config()` (uses `osiris.yaml`; env fallback with WARNING).

- **CLI**

  - No changes to secrets handling; continue to source `.env` via user’s shell or project conventions.
  - Add `osiris connections doctor --json` stability checks if missing.

- **Tests**

  - `tests/mcp/test_cli_bridge_connections.py`
    - Mocks `subprocess.run` to return golden JSON for `list`/`doctor`.
    - Verifies mapping to MCP result schema and deterministic error codes.
  - `tests/mcp/test_cli_bridge_discovery.py`
    - Verifies delegation arguments and timeout handling.
  - `tests/mcp/test_filesystem_contract_mcp.py`
    - Asserts server/audit/telemetry write under `<base_path>/.osiris/mcp/logs`.
  - Update existing self‑test to include one delegated tool call (e.g., `connections_list`) and still complete &lt; 2s.

- **Docs**
  - ADR‑0036 addendum: “MCP is a thin adapter; secrets remain in CLI scope.”
  - Config reference: document `filesystem.mcp_logs_dir`.
  - MCP quickstart: run `osiris init` first; then use `osiris mcp clients` (which calls `osiris mcp run`).

### Acceptance criteria

- No MCP tool requires secrets; delegated tools succeed when CLI succeeds with `.env` present.
- `osiris.py mcp run --selftest` passes from **any** CWD (&lt; 2s) and exercises at least one delegated tool.
- All MCP logs/audit/telemetry land under `<base_path>/.osiris/mcp/logs`.
- `osiris mcp clients --json` snippet launches MCP via `osiris.py mcp run` (no env block needed).

---

## 10) Add missing CLI commands for MCP delegation

### Required CLI commands that don't exist yet

These CLI commands need to be added to support MCP tool delegation:

- [ ] **`osiris discovery request`** (NEW)

  - `osiris discovery request --connection <id> --component <id> [--samples N] --json`
  - Returns discovered schema and sample data
  - Currently discovery is component-specific, needs unified interface

- [ ] **`osiris oml schema`** (NEW)

  - `osiris oml schema --json`
  - Returns OML v0.1.0 JSON schema
  - Currently schema is only available via MCP

- [ ] **`osiris guide start`** (NEW)

  - `osiris guide start --context <file> --json`
  - Returns guidance for next steps
  - Context file contains current state

- [ ] **`osiris memory capture`** (NEW)

  - `osiris memory capture --session <id> [--consent] --json`
  - Captures and returns session memory
  - Requires consent flag for PII handling

- [ ] **`osiris usecases list`** (NEW)
  - `osiris usecases list [--category <cat>] --json`
  - Returns available use case templates
  - Optional category filter

**Verification**

```bash
# Test each new command
osiris discovery request --help
osiris oml schema --json | jq '.version'
osiris guide start --context /tmp/ctx.json --json
osiris memory capture --session test123 --consent --json
osiris usecases list --json | jq '.[].name'
```

---

## 11) Test coverage for CLI bridge implementation

### Core test files needed

- [ ] **`tests/mcp/test_cli_bridge.py`**

  - Test `run_cli_json()` with mock subprocess
  - Test timeout handling
  - Test error code mapping
  - Test config path resolution

- [ ] **`tests/mcp/test_no_env_scenario.py`**

  - Run MCP server with no environment variables
  - Verify CLI delegation works without secrets
  - Test that connections are resolved by CLI layer

- [ ] **Update existing tool tests**
  - [ ] `tests/mcp/test_tools_connections.py` - Mock CLI calls
  - [ ] `tests/mcp/test_tools_discovery.py` - Mock discovery CLI
  - [ ] `tests/mcp/test_tools_oml.py` - Mock OML CLI commands
  - [ ] `tests/mcp/test_tools_guide.py` - Mock guide CLI
  - [ ] `tests/mcp/test_tools_memory.py` - Mock memory CLI

**Verification**

```bash
# Run bridge tests
pytest tests/mcp/test_cli_bridge.py -v

# Test without environment
unset MYSQL_PASSWORD SUPABASE_SERVICE_ROLE_KEY
pytest tests/mcp/test_no_env_scenario.py -v

# Full MCP test suite with mocked CLI
pytest tests/mcp/ -v
```

---

## Definition of Done

- All checkboxes above are complete.
- `python osiris.py mcp run --selftest` passes in < 2s from any CWD.
- `pytest -q tests/mcp` green; new CLI tests green.
- `osiris mcp clients --json` produces a snippet that works copy/paste in Claude Desktop.
- Logs appear under `<base_path>/.osiris/mcp/logs` on first run (no manual setup).
- **MCP works without environment variables** (secrets resolved by CLI layer).
