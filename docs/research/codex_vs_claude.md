OUTPUT_FILE = docs/research/e2b_supabase_writer_parity_investigation_claude.md

# Research Task: E2B vs Local Parity — Supabase Writer Failure (Read-Only, No Code Changes)

Branch: debug/codex-test
Goal: Explain precisely why the E2B run fails while the local run passes. Produce a root-cause report and a step-by-step fix plan. **Do not modify any code.** You **must run both local and E2B runs and paste the full logs**. Inspect, compare, and document your findings thoroughly.

---

## Current Symptom (E2B)

From a fresh compile+run of `docs/examples/mysql_duckdb_supabase_demo.yaml`:

```
Supabase write failed: SupabaseWriterDriver._ddl_attempt() takes 1 positional argument but 6 were given
```

Recent context:
- DataFrame flow is OK in E2B (extract → duckdb → writer); inputs resolve via pickle artifacts.
- A static IPv4 was purchased for `db.nedklmkgzjsyvqfxbmve.supabase.co`; hostname now resolves to IPv4 (no IPv6 hurdle).
- Local runs are green (append & replace); E2B still fails at writer DDL stage.
- Previously seen import/upload gaps (components not uploaded) and caching issues have been fixed.
- Hypothesis: method signature mismatch between the file running inside the E2B sandbox and the local tree (stale upload, divergent file, or altered callsites).

---

## What to Deliver (Checklist)

You **must produce a Markdown report at the path specified by `OUTPUT_FILE`** containing the following sections:

### 1. Executive Summary (≤10 lines)
- Concisely summarize your findings and root cause.

### 2. Reproduction Logs (copy/paste)
- **Local run:**
  ```
  python osiris.py compile docs/examples/mysql_duckdb_supabase_demo.yaml
  python osiris.py run --last-compile --verbose
  ```
- **E2B run:**
  ```
  cd testing_env
  python ../osiris.py run --last-compile --e2b --e2b-install-deps --verbose
  ```
- Include the **exact failing stack trace from E2B (with timestamps).**

### 3. Call Graph & Signature Table for SupabaseWriterDriver
- Extract and list **all call sites** of `_ddl_attempt(...)` (file, line number, arguments passed).
- Extract the **definition** of `_ddl_attempt` (file, line number, signature).
- Show any overloads or wrappers and their signatures.
- Include a quick diff of these between `main` and `debug/codex-test` branches.

### 4. Sandbox vs Local File Integrity Check (suspected drift)
- Show how `ProxyWorker` uploads `osiris/drivers/supabase_writer_driver.py` into the sandbox.
- Compute SHA256 of the local file and the sandbox file:
  - Local:
    ```
    shasum -a 256 osiris/drivers/supabase_writer_driver.py
    ```
  - Sandbox:
    Emit SHA256 by having `ProxyWorker` dump it to an artifact (if helper exists) or via existing system artifacts.
    If not available, use whatever artifact or telemetry is already in place to prove the exact file path & size and compare with local.
- If SHA mismatch: identify which version the sandbox actually runs (print first/last 20 lines with the `_ddl_attempt` signature).

### 5. Upload Manifest Audit
- List which directories/files are uploaded by `e2b_transparent_proxy.py` (drivers/components/core).
- Confirm that the exact `supabase_writer_driver.py` used locally is included in the E2B upload.
- If it’s excluded or overwritten, show where and why.

### 6. Channel Flow Verification (DDL path only; no code changes)
- From logs, confirm which channel the writer attempts first (psycopg2 IPv4, http_sql, http_rest).
- Verify whether after the IPv4 purchase the writer still short-circuits with an IPv6 error or actually reaches IPv4 connect.
- Confirm whether the anti-delete / replace path invokes `_ddl_attempt` with 5 arguments (as per stack trace) and whether the target method signature expects fewer.

### 7. Parsers & Spec Inputs
- Check `components/*/spec.yaml` for the Supabase writer and confirm there isn’t a stale or divergent input schema causing wrong call style or argument mapping.

### 8. Artifacts to Attach (verbatim snippets with relative paths)
- `artifacts/_system/pip_install.log`
- `artifacts/_system/run_card.json`
- Any module list / sys.path artifacts emitted by `ProxyWorker` (e.g., `module_list.txt`, `sys_path.txt`).
- For the writer step, the exact `cleaned_config.json`.

### 9. Conclusions
- State the root cause crisply (e.g., “E2B uploads stale driver with old _ddl_attempt signature” or “call sites refactored, method signature not updated in E2B copy”).
- Explain why local vs E2B diverge (one-liners anchored to evidence).

### 10. Fix Plan (no edits now, just plan)
- Bullet list of concrete changes (file paths, lines to touch) to restore parity.
- Suggested unit/integration tests to prevent recurrence:
  - Test ensuring E2B upload contains the exact driver files (SHA compare).
  - Test asserting `_ddl_attempt` signature matches callsites.
  - Parity test that runs writer DDL path in a dummy environment (mock connect) in both adapters and asserts identical telemetry.

---

## Commands to Run (exact)

**Do not modify any code.** Only run, read logs/artifacts, and document.

**Local:**
```
python osiris.py compile docs/examples/mysql_duckdb_supabase_demo.yaml
python osiris.py run --last-compile --verbose
```

**E2B:**
```
cd testing_env
python ../osiris.py run --last-compile --e2b --e2b-install-deps --verbose
```

**File hashes (local):**
```
shasum -a 256 osiris/drivers/supabase_writer_driver.py
shasum -a 256 osiris/remote/proxy_worker.py
shasum -a 256 osiris/remote/e2b_transparent_proxy.py
```

**(If available) Sandbox file hashes:**
- Use existing `ProxyWorker`/system-artifacts functionality to dump SHA256 and first/last 20 lines of `/home/user/osiris/drivers/supabase_writer_driver.py` to `artifacts/_system/driver_probe.txt`.

---

## Specific Questions You Must Answer
1. Why does E2B call `_ddl_attempt(...)` with 5 arguments while the method definition appears to accept fewer? Provide exact definitions and callsites with line numbers.
2. Are E2B and local running the same bytes of `supabase_writer_driver.py`? Prove it (hashes or printed signatures).
3. Is the E2B upload excluding or overwriting the writer file? If yes, where?
4. Does the writer, after the IPv4 purchase, still try IPv6 or does it reach IPv4 and then fail due to the signature mismatch? Show logs that prove which path is used.
5. Is there any component spec or compiler mapping that could cause a wrong call format into `_ddl_attempt`? Show the relevant spec and the generated `cleaned_config.json`.

---

## Important Constraints
- Do **not** change any code. This is a read-only audit + real runs + documentation task.
- Prefer copy/paste of exact log snippets and line-numbered code context.
- Keep conclusions evidence-backed. No guesses without logs or code excerpts.
- If any of the requested sandbox file probes are impossible with current hooks, state exactly what’s missing and propose a minimal hook to add (but don’t add it now).

---

If anything is unclear, proceed with the investigation anyway using the best approximation, and document any limitations in the report.
