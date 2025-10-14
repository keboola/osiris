# MCP TODO (post-verify checklist) — Osiris v0.5.0

> This list captures the production hardening work we’ll do **after** we confirm MCP server basic functionality (handshake + tools).  
> Scope aligns with ADR-0036 and `docs/milestones/mcp-final.md`.

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

## Definition of Done

- All checkboxes above are complete.
- `python osiris.py mcp run --selftest` passes in < 2s from any CWD.
- `pytest -q tests/mcp` green; new CLI tests green.
- `osiris mcp clients --json` produces a snippet that works copy/paste in Claude Desktop.
- Logs appear under `<base_path>/.osiris/mcp/logs` on first run (no manual setup).
