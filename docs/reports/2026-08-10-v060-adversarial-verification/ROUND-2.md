# Adversarial verification, round 2 (after the round-1 fixes)

**Date:** 2026-08-10
**Method:** the identical script from round 1, re-run against the fixed tree.
**Result:** all five claims refuted again — but on different, deeper defects. The round-1
defects are closed; the skeptics went past them.

## Verdict per claim

| Claim | Verdict | The one thing that matters |
|---|---|---|
| `freeze()` hash depends only on the plan's meaning | **REFUTED** | The hash is partly a function of the installed PyYAML emitter's line-wrapping (`canonical_yaml(..., width=120)` folds long scalars) — same plan, different wrap width, different `manifest_hash`. Redundant too: `plan_fp` already covers pins via fold-free JSON. |
| Edited build/ artifact is detected and `run` refuses | **REFUTED** | The five checks are unkeyed hashes; an 8-line script using the repo's *own public API* re-signed a tampered plan, redirected `search` → `delete_all` with `{"confirm": true}`, ran it for real, and got an `artifact_verified` event plus a `success` ledger row. Semantic tamper detection is otherwise strong (26/29 battery cases correct). |
| Runner aborts before ANY cf-ng call on contract drift | **REFUTED** | `policy.on_tool_contract_drift: warn\|ignore` is a plain, author-settable plan field that switches the abort off entirely — and under `ignore` the `pins_verified` event is byte-identical to a clean run (`warnings: 0`). The evidence record lies. |
| A `cfng_` token never reaches disk in any evidence file | **REFUTED** | Redaction is exact-substring against the single value in `$CFNG_TOKEN`. Any *other* `cfng_` token — including the `credentials` argument the cf-ng gateway injects into every tool schema by design — is written verbatim to `events.jsonl`, `runs.jsonl` and stdout, in the same sentence where the process's own token shows as `***`. |
| Package is self-contained, no dead code, nothing imports v0.5.4 | **REFUTED** | Three independent failures: the suite fails in a clean venv built from the package's own deps; `Relay.list_tools` and the `verify_pins` branch are provably dead; six CI/config files still reference the deleted tree — and no workflow can fail on the test suite anyway. |

The 265-green baseline is not a meaningful signal. It runs against a stale v0.5.4 `.venv` (e2b, supabase, openai, pandas…), and the only workflow that invokes `pytest tests/` is `continue-on-error` at job *and* step level with `|| true` and `exit 0`.

## Real defects

### 1. Secrets leak to disk — foreign `cfng_` tokens are never redacted (HIGH)
Redaction is keyed exclusively to `$CFNG_TOKEN`. The `credentials` argument that cf-ng injects into every tool's `inputSchema` (documented at `osiris/cfng/client.py:4-5`) goes to disk in the clear.
```
events.jsonl: {"event":"tool_call",...,"arguments":{"q":"dune",
  "credentials":{"api_token":"cfng_0THER_Ag3ntPastedTokenZZ99"}}}
runs.jsonl:   "error":"step 'fetch': token *** is not authorized
  (req={...\"api_token\":\"cfng_v1.0therCred3ntialForTheConnector\"}})"
```
Own token masked, foreign token in the clear, same string. There is no `cfng_` pattern rule at the evidence seam — only at freeze.

### 2. `freeze`'s secret guard is trivially regex-bypassable (HIGH)
`_SECRET_SHAPED = cfng_[A-Za-z0-9_\-]{8,}` misses any token containing `.`, `+`, `/` or `=` — i.e. the `cfng_v1.<base64>` shape.
```
BYPASS 'cfng_v1.9Xq2vB7tR4mN8pL3wZ6yK1sH0dF5gJ2a'  match=None
FREEZE_EXIT=0 → manifest.yaml: auth: cfng_v1.9Xq2vB7tR4mN8pL3wZ6yK1sH0dF5gJ2a
```
Also: `pins.cfng.catalog_version` is written from the cf-ng response *after* `_reject_secrets(plan)` and manifest.yaml is written with no redaction at all — a cf-ng that reflects the presented credential puts the live token on disk (`manifest.yaml:14: catalog_version: sha256:cfng_LiVeT0ken...`).

`tests/evidence/test_secret_leaks.py` passes 5/5 through all of this. It only greps for `$CFNG_TOKEN`.

### 3. Drift evidence is falsifiable by policy (HIGH)
`policy.on_tool_contract_drift` is inside the hashes (good — can't be flipped post-freeze), but the author sets it at freeze time and freeze accepts it silently.
```
fail   -> calls=0 ABORTED
warn   -> RAN, POST /tools/call issued
ignore -> RAN, POST /tools/call issued, no warning emitted
```
Worse, under `ignore` the drifted run emits `pins_verified {"tools_checked":1,"tool_calls_pinned":1,"warnings":0}` — byte-identical to a clean run. `runner.py`'s own comment says this event is "emitted only on the path that actually verified something". It isn't. A positive integrity assertion is being emitted for a run where integrity failed.

### 4. `tool_pin` doesn't hash the safety-relevant fields (HIGH)
Under **default fail policy**, all of these ran and issued a real call:
```
annotations destructiveHint false->true            -> calls=1 RAN
description "Search movies. Read-only." -> "DELETE movies..." -> calls=1 RAN
inputSchema {} -> removed / null / false           -> calls=1 RAN
```
`annotations` are machine-readable safety hints, not the "prose fields deliberately excluded" the docstring cites. And `manifest.get("inputSchema") or {}` (`pins.py:100`) collapses absent/`{}`/`null`/`false` into one fingerprint — including `{}` → `false`, which in JSON Schema flips a tool from "accepts anything" to "accepts nothing". `outputSchema` uses `is not None` and is correctly strict; the two halves of the same pin disagree about what "no schema" means.

### 5. `ToolPin` is the one un-sealed model, and it defeats freeze's own guard (HIGH)
`ToolPin.model_config` is `{}` — pydantic default `extra="ignore"` — while `Plan`/`Step`/`Policy`/`Pins`/`CfngPins` are all `extra="forbid"`. Anything added to a `pins.tools.<key>` entry after freezing is dropped on load, never reaches the hash, and the artifact passes all five checks.
```
100KB smuggled into a ToolPin -> exit=0, manifest 100910 bytes, still verifies
live cfng_ credential injected -> exit 0, "token still on disk in the verified artifact: True"
same literal at freeze time    -> exit 1 "a literal secret must never enter an artifact"
```
The gap is named in the comment at `model.py:124-126` and left open.

### 6. `mcp>=1.2.1` floor makes `osiris serve` DOA on a legal resolution (HIGH)
Code requires the mcp 2.x `Server(instructions=, on_list_tools=, on_call_tool=)` API. Installing the declared floor:
```
mcp 1.2.1: def __init__(self, name: str, version: str | None = None)
build_server FAILED -> TypeError: unexpected keyword argument 'instructions'
```
Nothing tests the declared floor. `anyio` is imported by tests and declared nowhere; `requests` (needed for `test_package` to pass) arrives only transitively via twine.

### 7. Six config files still point at the deleted v0.5.4 tree (HIGH)
`.github/CODEOWNERS`, `ci-mcp.yml`, `e2b-manual.yml`, `e2b-tests.yml`, `mcp-phase1-guards.yml`, `MANIFEST.in`. Every command they run is dead:
```
python -m osiris.cli.mcp_entrypoint --selftest -> ModuleNotFoundError
from osiris.mcp.server import ...              -> No module named 'osiris.mcp'
osiris.py chat / mcp run / init --force        -> No such command / option
```
`ci-mcp.yml` also matrixes Python 3.8–3.10 against `requires-python >=3.11`. `test_package.py` only scans tracked `*.py`, so YAML and CODEOWNERS are invisible to it. They never fire (path-filtered on directories that don't exist), so this is rot, not breakage — but it's rot that will be trusted.

### 8. Test suite is not self-contained; no gate can fail (HIGH, combined)
```
pip install -e "<repo>[dev]" into clean venv; pytest -q
FAILED tests/test_package.py::test_no_file_imports_a_module_that_does_not_exist
  imports that cannot resolve: {'docs/.../driver_skeleton.py': ['pandas']}
1 failed, 264 passed
```
Green only because `.venv` is stale v0.5.4. And `research.yml` — the only workflow running `pytest tests/` — is `continue-on-error: true` (job), `continue-on-error: true` (step), `-q || true`, `exit 0`. It is structurally incapable of failing.

### 9. Pin-key `__` flattening blinds both the hash and the runner (MEDIUM)
Two distinct `(connector, tool)` pairs — `("imdb","a__b")` and `("imdb__a","b")` — flatten to one key `imdb__a__b`. One pin survives, and the `manifest_hash` becomes entirely blind to a tool the plan actually calls:
```
pins recorded: {'imdb__a__b': {...}}   # one entry, two tools
s1 contract {"type":"object","v":1}                 -> d863ec5e...
s1 contract {"type":"string","required":[a,b,c]}    -> d863ec5e...  (unchanged)
```
`freeze()` never calls `detect_pin_key_collisions` — it's only referenced from `pins.py` and the runner. Related: when cf-ng lists two manifests for the same tool, `_live_tool_pins` takes the last one by list order, and `detect_pin_key_collisions` can't flag it because it dedupes identical pairs. Verdict decided by list ordering: `[drifted, pinned] -> RAN`, `[pinned, drifted] -> ABORTED`.

### 10. Check 2 (pins fingerprint) has zero test coverage (MEDIUM)
Mutation results: checks 1/3/4/5 each kill 1–2 tests. Deleting check 2 → **265 passed**. `test_run_refuses_an_artifact_whose_pins_were_edited` is actually killed by check 1. Check 2 is not redundant — the constructed input only it catches (pin falsified to a genuinely drifted live schema, plan+manifest fps recomputed, recorded pins fp left stale) flips from `exit 1 "does not match its recorded pins fingerprint"` to `exit 0 success` with real drift hidden. A refactor could delete this and CI would applaud.

### 11. Author-written pins are silently discarded (MEDIUM)
```
author pins catalog A / catalog B / no pins at all -> all three 49a0bd6d...955d83
```
No warning. `extra="forbid"` closed this for *unknown* fields but not for known-but-clobbered ones.

### 12. `manifest_hash` depends on the PyYAML emitter (MEDIUM)
Same frozen plan, only the emitter wrap width varied:
```
width=120 -> 6f17bcfc...   width=80 -> e955a831...   width=200 -> 9208e24f...
```
Reachable through the author-settable free-text `pins.cfng.proxy`. Fix is cheap: drop the YAML pass, `plan_fp` already covers pins via fold-free JSON.

### 13. Connector-id path/body split (MEDIUM)
The pin probe names the connector in a URL path (httpx normalizes `..`); the tool call sends the raw string in the JSON body.
```
connector='imdb/../tmdb'  probeGET=['/connectors/tmdb/tools']  callBody=['imdb/../tmdb'] -> RAN
```
Freeze accepts such a plan. Exploitability depends on cf-ng's resolution, but the verified contract is provably not the one named in the call.

### 14. Deleting the whole `fingerprints:` block passes verification (LOW)
Check 4 builds `declared` only from keys present in `plan.fingerprints`, so an empty block trivially agrees with `fingerprints.json`. A manifest can ship making no self-claim about its own identity and still run.

### 15. Dead code (LOW–MEDIUM)
- `Relay.list_tools` (`relay/server.py:73-74`) — no caller anywhere. Body never executes; deleting the method leaves 265 passing and all modules importing. This is exactly the pattern the rebuild claims to have eliminated.
- `cli.py:468` `getattr(runner_, "verify_pins", None) or runner_._check_pins` — `verify_pins` is defined nowhere; the left operand is permanently `None` (proven by flipping the assertion: `is not None` → 2 failures).
- `tests/conftest.py::cfng_base_url` fixture never requested; all 7 markers in `pytest.ini` unused; `pytest-timeout` not installed. The entire declared "live cf-ng testing" apparatus is wired to nothing.
- `engine_tools()`'s docstring justifies its SDK-free existence by citing callers ("tests, `osiris doctor`") that don't call it.

## Accepted limitations

- **Unkeyed hashes are not signatures.** `cli.py:191-195` says so explicitly. Tamper-*evidence* against accident and casual edit is the right phase-1 goal; keyed signing needs a key-management story that doesn't exist yet. *But the `artifact_verified` event and `success` ledger row asserting integrity that was never established is a defect, not a limitation — see fix list.*
- **TOCTOU on pins.** `_check_pins` runs once before the step loop, so a contract changing mid-run isn't re-checked. Inherent to a batch design; per-call re-verification is a real cost. It only bounds the *unconditional* wording of the claim.
- **`generated_at` unauthenticated.** Excluded from the hash by design (so identical plans hash identically — correct), written to the manifest, read by nothing at runtime. Consequence: same hash ≠ same artifact bytes, so byte-diffing two build dirs reports spurious differences. Fine for now; document it.
- **The hash is tied to the cf-ng deployment it was frozen against.** Staging vs prod, or a docs-only `inputSchema` edit, moves the hash. This is arguably correct — the pins *are* part of the frozen artifact — it just contradicts the claim as literally worded. Worth restating the claim rather than changing the code.
- **Check 5 validates only the leaf directory name**, not the plan-name parent, so a verified artifact can be moved under a different plan name. Minor; the layout just conveys less than it looks like it does.
- **Everything that should hold, holds.** Determinism across process/cwd/TZ/locale/`PYTHONHASHSEED`/clock is solid (5 interpreters + 3 fake clocks + 120 fuzzed drafts, zero variance, zero collisions). Semantic sensitivity is correct across 27 probes. Canonicalization tolerance is genuinely good (all 11 reformatting attacks correctly ignored, incl. BOM/CRLF/JSON-rewrite). `redact()`'s type-walk is sound. Fail-open probes all fail closed. The abort-before-first-call ordering guarantee is real and covered (mutants kill 8 and 12 tests). Don't let the refutations obscure that the core is well built.

## What to fix before phase 2

1. **Add a `cfng_`-shaped pattern rule at the evidence seam** (`redact()`), not just at freeze. Widen `_SECRET_SHAPED` to cover `.`/`+`/`/`/`=`. Redact `manifest.yaml` on write, and move the `catalog_version` assignment *before* `_reject_secrets`.
2. **Make the drift evidence honest.** `pins_verified` must carry the actual drift count and the effective policy, or not be emitted at all when drift was suppressed. Same for `artifact_verified` — never emit a positive integrity claim on a path that only verified unkeyed self-consistency.
3. **Set `extra="forbid"` on `ToolPin`.** One line. Closes the 100KB/secret smuggling channel and the comment at `model.py:124-126`.
4. **Fix `tool_pin`:** hash `annotations` (they're safety semantics, not prose); replace `manifest.get("inputSchema") or {}` with the `is not None` form used for `outputSchema`.
5. **Call `detect_pin_key_collisions` from `freeze()`**, and make `_live_tool_pins` reject duplicate `(connector, tool)` manifests instead of last-write-wins. Consider dropping the `__` flattening for a structured key.
6. **Make the mcp floor honest** (`mcp>=2.x`), declare `anyio`, and add a CI job that installs from the declared deps in a clean venv and runs the suite — with `continue-on-error` removed. Nothing else on this list matters if nothing can fail.
7. **Delete the v0.5.4 rot:** four workflows, CODEOWNERS, MANIFEST.in, and `docs/developer-guide/human/examples/shopify.extractor/`. Extend `test_package.py` to scan YAML and CODEOWNERS, not just tracked `*.py`.
8. **Delete the dead code:** `Relay.list_tools`, the `verify_pins` branch, the `cfng_base_url` fixture, the 7 unused markers.
9. **Write the test that kills check 2**, and drop the YAML pass from `pins_fp` (use `canonical_json`, which is fold-free).
10. **Decide on `policy.on_tool_contract_drift`.** Either reject `warn`/`ignore` at freeze time, or require an explicit justification field and surface it loudly in `run` output and the ledger. Right now it's a silent kill switch on the engine's central safety property.
---

# Disposition (2026-08-10, after round 2)

Round 3 was deliberately **not** run. Adversarial verification does not converge on its own — each
round reaches past the last one's fixes. The right stopping point for a walking skeleton is to fix
what is cheap and unambiguously wrong, then state the guarantees at the strength the implementation
actually supports. The bounded claims now live in `docs/design/osiris-0.6.0-engine.md` §4.3.1.

## Fixed (commit `52b3f01`)

| Defect | Fix |
|---|---|
| 1 — foreign `cfng_` tokens unredacted | Prefix-anchored shape rule at the `redact()` seam, applied before exact-value matching. Deliberately not entropy-based. |
| 2 — `_SECRET_SHAPED` bypass, guard ordering | One shared pattern; guard runs after every field is populated. Refuses rather than masking, because masked bytes no longer hash to the recorded fingerprint. |
| 3 — drift evidence falsifiable by policy | The event name is the assertion: `pins_verified` only when nothing drifted, `pins_drift_suppressed` otherwise, `drift_ignored` carries the diff. |
| 4 — `tool_pin` fidelity | `annotations` hashed; `inputSchema` uses the strict `is not None` form. **Changes every existing pin value.** |
| 5 — `ToolPin` un-sealed | `extra="forbid"`. |
| 6 — `mcp>=1.2.1` floor | Raised to `>=2.0.0`; `anyio` and `requests` declared. |

## Open, with cost

| Item | Why it is still open | Cost |
|---|---|---|
| **CI cannot fail a PR** — `research.yml` is `continue-on-error` at job and step level with `\|\| true`; four path-filtered workflows target deleted directories; `CODEOWNERS` and `MANIFEST.in` name the v0.5.4 tree | Workflow deletion was declined during execution and left to a human | ~1h. **Highest leverage item on this list** — without it nothing above stays fixed |
| Clean-venv run fails on `pandas` | A v0.5.4 shopify docs example is still tracked and `test_package` resolves its imports | ~10 min: delete the example |
| Keyed signing | Needs a key-management story that does not exist | Phase 3+ |
| Per-call pin re-verification (TOCTOU) | Pins are checked at t0 only; a contract moving mid-run is not re-checked | Real cost, deferred deliberately |
| `.env` loading not wired | `python-dotenv` was dropped rather than wired, since the CLI was owned by another agent at the time | ~15 min |
| `.env.dist` still documents v0.5.4 variables | `rm` on `.env*` was declined by a permission rule | ~5 min, needs a human |
| Pin-key format `{connector}__{tool}` is ambiguous | Changing it invalidates every frozen artifact, so only collision *detection* was added | `FOLLOW-UP(pin-key-format)` at `pins.py:17` names the three call sites that must move together |
| `Relay.list_tools`, the `verify_pins` branch | Dead until phase 2 wires `osiris_freeze` over MCP | Phase 2 |
| `RunContext` does not expose its `Session` | `cfng_call` reads `ctx._session` via `getattr` | ~10 min: add a `secrets` property |
| Integrity check 5 validates only the leaf directory name | A verified artifact can be moved under a different plan name | ~15 min |
