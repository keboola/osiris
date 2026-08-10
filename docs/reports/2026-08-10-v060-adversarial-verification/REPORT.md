# Adversarial verification of the v0.6.0 walking skeleton

**Date:** 2026-08-10
**Method:** five independent agents, each instructed to REFUTE one guarantee by attacking the
implementation rather than reading the tests, defaulting to "refuted" when uncertain.
**Result:** all five claims refuted. `ruff`, `black` and `bandit` pass clean; every defect below
is invisible to the lint gate.

# Adversarial verification: Osiris v0.6.0 walking skeleton

## Verdict per claim

**1. `freeze()` produces a manifest_hash that depends only on the plan's meaning** — **REFUTED.** A `set` anywhere in the draft makes the hash *and* the written `manifest.yaml` PYTHONHASHSEED-dependent: 8 processes, one draft, 8 distinct hashes.

**2. An edited build/ artifact is detected and `osiris run` refuses it** — **REFUTED.** The integrity check is an unkeyed checksum stored next to the thing it protects, and only `fingerprints["plan"]` is ever verified. Two lines using the repo's own public API recompute it; tampered SQL then executes with exit 0.

**3. When a pinned tool's contract has changed, the runner aborts before any cf-ng call** — **REFUTED.** Adding an `outputSchema` after freeze raises no drift and no warning (the guard is `want.output is not None`), while *removing* one correctly aborts — an asymmetry, not a policy. The mainstream path does hold, and the repo's tests are non-vacuous for it (mutation testing killed 3 tests).

**4. A `cfng_` token never reaches disk in any evidence file** — **REFUTED, four independent ways.** `runs.jsonl` records the raw exception string while `events.jsonl` redacts the identical sentence — the redaction seam exists and `RunIndex` simply doesn't call it.

**5. The v0.6.0 package is self-contained, no dead code, nothing imports the deleted v0.5.4 tree** — **REFUTED.** Five tracked files under `scripts/` crash with `ModuleNotFoundError` on import, and `verify_fingerprint` has no production caller — the exact anti-pattern its own module docstring says the rebuild eliminated. The shipped wheel, though, is genuinely clean: 27 modules, e2e works from an unrelated cwd.

---

## Real defects

### 1. Tampered artifacts execute with exit 0, and the ledger records the pre-tamper hash (HIGH)

Not one bug but a chain. `_load_plan` verifies only `fingerprints["plan"]`. `fingerprints["manifest"]` and `["pins"]` are written and never read. There is no keyed integrity anywhere (`grep -rniE 'hmac|signature|ed25519' osiris/` → empty).

```
query -> SELECT * FROM (VALUES (1),(2),(3),(4),(5)) t(pwned)
fingerprints.json["plan"] recomputed via compute_fingerprint(Plan(**data).canonical_without_fingerprints())
osiris run -> exit 0, "success run_20260810T161206Z_f1071e", shape: 5 rows
ledger manifest_hash == ORIGINAL (pre-tamper) hash?  True
build dir still named after original hash?           True
evidence events mentioning fingerprint/tamper:       NONE
```

The ledger lie is the worse half: `runs.jsonl.manifest_hash` is read from the manifest's *own* `fingerprints:` block, which is excluded from the hash and never verified. The audit trail actively certifies something that did not run. `osiris/run/steps/sql.py` carries the comment "The artifact is trusted input: it is fingerprinted at freeze time and verified before the run starts" — that assumption is false.

A free fix was left on the table: `manifest_fp == sha256(plan_fp + pins_fp)` would have caught this attack with zero crypto. The values disagree (`7630e89d…` vs `8a1c126e…`) and nobody looks.

Credit where due: the checker is not vacuous. 9 semantic edits refused, 6 benign reformattings (JSON rewrite, flow style, comments, forced quoting) allowed. Canonicalization tolerance is real. It just doesn't survive an attacker who read the source.

### 2. Four live token leaks to disk, with a green test suite (HIGH)

Driven end-to-end against a real fake cf-ng with `CFNG_TOKEN=cfng_LiVeT0ken…`, then byte-grepping every file under base_path.

- **`runs.jsonl`** — `osiris/cli.py:275` does `error=str(exc)`; `run_index.py:39` `json.dumps`es it with no `redact()`. A cf-ng 403 that echoes the presented credential lands in plaintext. The *same string* is `***` in `events.jsonl`.
- **`<run>/work/artifacts/*.ndjson` and `pipeline_data.duckdb`** — cf-ng tool results written verbatim, inside the directory the CLI prints as `evidence:`.
- **`build/*/manifest.yaml`** — the freeze-time secret guard is bypassed three ways: token as a dict *key* (`_walk_strings` recurses `value.values()` only), token in `plan.params`, token in `plan.metadata` (`_reject_secrets` iterates only `plan.steps`). The control case (token in a step value) is correctly rejected, so the guard works exactly where it looks and nowhere else.
- **stdout** — `console.print(f"[red]{exc}[/red]")`, so `osiris run > nightly.log` writes the token outside the evidence system entirely.

Why nobody noticed: `tests/test_cli.py:277 test_run_evidence_redacts_the_token` asserts `exit_code == 0` and greps only `run_logs/demo/**/events.jsonl` — the one file that is correctly redacted. `139 passed in 1.65s` with all four leaks live. This test is worse than no test; it creates confidence.

Also: `redact()` never redacts dict keys and its final `return value` passes tuples through untouched, which `json.dumps` then serializes as arrays. Both reachable through the real Relay with agent-supplied MCP arguments.

### 3. `set` in a draft → nondeterministic hash and nondeterministic artifact (HIGH)

```
params={"tags": {6 strings}}, 8 processes, only PYTHONHASHSEED varies:
cb482c8c… 8207f639… e66fd7a2… 1b3ab5b0… 96893f13… dc62efa2… dafe01be… 1698e26d…
```

`model_dump(mode="json")` flattens a set to a list in iteration order; nothing downstream restores it (`_normalize_value` correctly treats lists as order-significant). The written `manifest.yaml` differs too — `tags: alpha,beta,gamma,delta,epsilon` vs `alpha,epsilon,beta,delta,gamma`.

Today's `osiris freeze <file>` path is safe because `cli.py:205` uses `json.loads`, which cannot produce a set. The exposure is the library API: `freeze(draft: dict[str, Any])` and `Plan.params`/`metadata`/`Step.with_` are all `dict[str, Any]`, and `yaml.safe_load` on a `!!set` tag materializes a real set.

The determinism test cannot catch this by construction: `test_freeze_is_deterministic_across_invocations` calls freeze twice **in one process**, where set iteration order is fixed. Reproduced: the assertion is `True` in every process while the hash changes between them.

Baseline determinism is otherwise genuinely strong — 150 fuzzed JSON drafts, identical across processes, 150 distinct hashes, immune to clock/cwd/TZ/seed/base_path. The set case is the single crack.

### 4. `outputSchema` added after freeze → no drift, tool called (HIGH)

```
frozen pin: alpha__fetch_a: {input: sha256:df0cd751…, output: null}
cf-ng adds outputSchema {"type":"object","properties":{"total":{"type":"integer"}}}
osiris run -> exit 0, POST /tools/call, "call_a: 2 rows"
control (outputSchema REMOVED) -> exit 1, tools/call 0, "outputSchema changed since freeze"
```

`osiris/cfng/pins.py:74`: `elif want.output is not None and have.output != want.output`. A pin recording `output: null` can never drift on output. The docstring only claims prose fields are excluded, so this is a bug, not policy.

Two more holes in the same guarantee:

- **Pin-key collision.** Keys are `f"{connector}__{tool}"` (`freeze.py:85`, `runner.py:53`). A plan calling `(x, "y__z")` and `("x__y", "z")` produces **one** pin. Changing `x/y__z`'s inputSchema → exit 0, 2 tool calls, no warning.
- **Empty pins are indistinguishable from verified pins.** Hand-built build dir with `pins.tools={}`, fingerprints recomputed with the repo's own helper; server schemas fully replaced. Run: exit 0, only `GET /connectors/alpha/tools` + `POST /tools/call` — catalog never probed. `events.jsonl` has no pin event of any kind. `--dry-run` prints **"Pins verified."**

The mainstream path is real and tested: mutation testing (stub `_check_pins`, or move it after the first step) killed 3 tests both times. But `test_contract_drift_aborts_before_any_tool_call` uses a one-step plan with inputSchema-only drift — it would pass unchanged under both holes above.

### 5. Five tracked files import the deleted v0.5.4 tree (HIGH)

```
scripts/discovery/mysql_peek.py, mysql_tables.py  -> osiris.core.config
scripts/test_cache_invalidation.py                -> osiris.core.discovery, osiris.core.interfaces
scripts/test_chat_mysql_to_csv.py                 -> osiris.core.conversational_agent, llm_adapter, oml_schema_guard
scripts/test_manual_transfer.py                   -> osiris.connectors.mysql, supabase
$ .venv/bin/python scripts/test_manual_transfer.py
ModuleNotFoundError: No module named 'osiris.connectors'
```

`tests/test_package.py::test_no_deleted_packages_remain` only asserts the directories are absent under `osiris/`, so it passes while these remain. The 27-module import sweep is clean and the built wheel is genuinely self-contained (fresh venv, Python 3.14.3, unrelated cwd, full init/freeze/run/doctor → success) — the rot is confined to `scripts/`.

### 6. Dead code in the module that exists to prevent dead code (MEDIUM–HIGH)

Poisoning experiment against a 139-test baseline:

- `fingerprint_dict` (`determinism/fingerprint.py:32`) — poisoned, **zero** failures. No caller, no test.
- `PathsConfigError` (`fsc/config.py:42`) — deleted, **zero** failures. `grep` finds only its own definition. Its docstring promises "Raised when a resolved path would escape base_path"; `paths.py` enforces that structurally via `slugify()` and never raises it.
- `verify_fingerprint`, `combine_fingerprints` — only their own unit tests fail.

Full `init/freeze/run/doctor` succeeded with all four poisoned. The module docstring reads: *"v0.5.4 computed fingerprints and never verified them."* `verify_fingerprint` sits in that same file with no production caller.

(Checked and rejected as false positive: `Plan._validate_steps` is a pydantic `@model_validator`, reachable via decorator.)

### 7. CI cannot fail a PR on the test suite (MEDIUM)

`research.yml` is the only workflow running the 139 tests, and it is triple-guarded: job-level `continue-on-error: true  # Never fail the PR`, step-level `continue-on-error: true`, and `pytest … || true`. `lint-security.yml` runs no pytest. `ci-mcp.yml`, `mcp-phase1-guards.yml`, `e2b-tests.yml` are path-filtered on `osiris/mcp/**`, `osiris/core/config.py`, `osiris/cli/init.py`, `osiris/remote/**` — all deleted, so they can never trigger, and they reference `tests/mcp`, `tests/cli`, `tests/e2b` which no longer exist. `make ci` does run pytest locally; the gap is GitHub Actions. Combined with defects 2 and 4, nothing would have stopped any of this from merging.

### 8. `python-dotenv` declared, never imported — `.env` does not work (MEDIUM)

`grep -rn dotenv` finds only `pyproject.toml:47` and `requirements.txt:8`. Confirmed: valid `.env` present, env vars unset, `osiris doctor` → `fail CFNG_BASE_URL is not set / fail CFNG_TOKEN is not set`, exit 1. `.env.dist` is tracked at HEAD and documents only v0.5.4 variables (`OPENAI_API_KEY`, `MYSQL_*`, `SUPABASE_*`) for deleted subsystems.

### 9. The skip ban is evaded by three common spellings (MEDIUM)

`pytestmark = [pytest.mark.skip(...)]` (the standard list idiom), `@pytest.mark.skip` on a Test class, and `import pytest as pt`. In each case the guard reported `1 passed` while `pytest -q -rs` reported `3 skipped`, each hiding a test asserting `False`. The regex requires one exact spelling. rglob nesting itself is correct — a nested canonical offender was caught.

### 10. Unhandled exits with no evidence (MEDIUM)

`CfngError` from the pin probe escapes `Runner.execute`; the CLI catches only `(DriftError, StepError)`. Connector 404 and cf-ng unreachable both produce a raw traceback and — contradicting the CLI's own comment that "a failed run is recorded too" — **nothing** in `runs.jsonl`. Fails closed (no tool call), but the abort is unhandled and evidence-less. Same shape for malformed `fingerprints.json` (`TypeError`/`JSONDecodeError` instead of the `_fail` message).

### 11. NaN/Infinity silently collapse to null (MEDIUM)

`cli.py:205` uses `json.loads`, which accepts bare `NaN`/`Infinity` literals; pydantic `mode="json"` rewrites all of them to `null`. Four semantically distinct CLI-reachable drafts share hash `e2357a42…` while `0` gets `c5d6d6d4…`. No warning, no `FreezeError` — the plan's meaning is destroyed and the hash certifies the destroyed version.

---

## Accepted limitations

- **`manifest_hash` depends on live cf-ng state** (catalog_version, tool schemas). Freezing against staging vs production yields different hashes. Pinning is the entire point of freeze; the claim was worded too strongly, the behavior is right.
- **Pins verified once, before the first step.** A contract that moves mid-run is not re-checked (confirmed: fetch_b's schema flipped on the first `/tools/call`, run exited 0). TOCTOU-free execution needs per-call verification or a server-side pin token — out of scope for phase 1. Document the guarantee as "verified at t0".
- **Unknown fields silently dropped** (pydantic `extra="ignore"`), so a draft with `retries: 5` freezes to the same hash as one without. The manifest drops them too, so the artifact stays self-consistent — but it should be `extra="forbid"` eventually.
- **Non-JSON type coercions** (int keys ≡ str keys, tuple ≡ list, `datetime` ≡ its ISO string, `Decimal("1.0")` ≡ `"1.0"`, `b"x"` ≡ `"x"`). Verified the emitted manifests are byte-identical, so the hash still faithfully names the artifact. Only the `set` case is genuinely broken, because only its coercion is order-nondeterministic.
- **`catalog_version` errors fail open** (caught, `actual=None`). Catalog drift is WARN by default, so the blast radius is one lost warning.
- **`osiris freeze` accepts JSON only** and reports a raw JSON parser error on a YAML draft, in a tool that reads `osiris.yaml` as YAML. Cosmetic for phase 1, confusing for users.
- **`cli.py:245` reaches into a private `Runner` method for `--dry-run`**, with a TODO acknowledging it. Honest debt.
- **Stale `pyproject.toml`**: `include = ["components*"]` (no such directory), a dead `[tool.pytest.ini_options]` block (pytest.ini wins), `[tool.mypy] python_version = "3.9"` vs `requires-python = ">=3.11"`.

Also worth stating plainly: `ruff`, `black`, and `bandit` all pass clean. Every defect above is invisible to the lint gate.

---

## What to fix before phase 2

1. **Redact `runs.jsonl`, NDJSON artifacts, DuckDB writes, and stdout.** Route every disk write through one redaction seam instead of four ad-hoc ones. Fix `redact()` to walk dict keys and tuples. Then rewrite the redaction test to grep *every* file under base_path on both the success and failure paths.
2. **Fix the freeze secret guard** to walk keys, `plan.params`, and `plan.metadata` — the artifact it protects is the one currently leaking.
3. **Sign the artifact, or at minimum verify all three fingerprints plus the internal consistency `manifest_fp == sha256(plan_fp + pins_fp)`.** Read `manifest_hash` for the ledger from the *verified* fingerprint, never from the manifest's unhashed self-declaration, and cross-check the build directory name.
4. **Make CI blocking.** Delete the three dead path-filtered workflows, remove all three `continue-on-error`/`|| true` guards from the suite run. Without this, none of the above stays fixed.
5. **Fix `detect_tool_drift`'s output asymmetry** (`want.output is not None`) and make pin keys a tuple or length-prefixed instead of `__`-concatenated.
6. **Reject non-JSON-primitive types in `freeze()`** — sets, tuples, NaN/Infinity, non-str dict keys — with a `FreezeError` rather than silent coercion. This closes the determinism hole and the NaN collapse in one change.
7. **Run the determinism test across processes** (subprocess with varying `PYTHONHASHSEED`), and add drift tests for output-only change, multi-step ordering, and key collision. The current tests pass under four of the defects above.
8. **Delete `scripts/`'s five broken files, `fingerprint_dict`, `PathsConfigError`**, and either wire `verify_fingerprint` into `_load_plan` (see item 3 — that is its caller) or delete it.
9. **Refuse to run with empty `pins.tools`**, and stop printing "Pins verified." when nothing was verified. Emit a pin-verification event into `events.jsonl` so a verified run is distinguishable from an unverified one.
10. **Either import `python-dotenv` or drop it**, and delete the v0.5.4 `.env.dist`.