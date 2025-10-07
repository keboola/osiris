# Deep Research and Remediation Plan for Remaining Test Failures

## 1. Summary
`make test` currently fails on 16 targets clustered around RunnerV0 telemetry and Supabase writer behaviour. The common pattern is state that leaks across the full suite: module-level patches of `log_event` and `SupabaseClient` persist long enough to break later tests that expect clean instrumentation. Offline guards in `osiris/drivers/supabase_writer_driver.py` also short-circuit real mocks, so DDL/IPv6 tests never exercise the intended branches. The plan below maps each failure to its root cause hypothesis, evidence, and the minimal fixes needed to restore deterministic, offline-friendly tests without regressing production code paths.

## 2. Failure-by-failure analysis

### 2.1 tests/runtime/test_local_inputs_resolved_events.py::test_runner_emits_inputs_resolved_for_memory_inputs
- **A. Fast triage** – During a full run the test sees `[]` for captured events (`len(input_events) == 0`). Local reproduction with `PYTEST_ADDOPTS='--maxfail=1 -vv' make test` shows the failure after CLI suites, while standalone `pytest -q` passes. `_emit_inputs_resolved` is invoked at `osiris/core/runner_v0.py:406-416`.
- **B. Root cause hypotheses & verification**
  1. `log_event` already patched to a `MagicMock` by earlier suites (e.g. CLI validation error stack in the same run) so the test’s `monkeypatch.setattr("osiris.core.runner_v0.log_event", capture_event)` is skipped. Evidence: inspect global with `python - <<'PY'` snippet printing `osiris.core.runner_v0.log_event` before and after the monkeypatch; in failing run it shows a mock with `call_args_list` seeded from CLI tests.
  2. `RunnerV0._log_event` still appends to `runner.events` (verified by `rg -n "self.events.append" osiris/core/runner_v0.py`), so the event exists but the collection path differs.
  3. Confirm by adding a temporary `print(runner.events)` in the test via `pytest -k inputs_resolved --maxfail=1 --pdb` inside the failing session – the event appears in `runner.events` even when `capture_event` misses it.
- **C. Proposed fix path** – Keep production code unchanged; harden the test to inspect `runner.events` (via `next(event for event in runner.events if event["type"] == "inputs_resolved")`) as a fallback. Supplement with a `assert capture_event in log_event.__wrapped__` style sanity check to ensure we still exercise the logging helper.

### 2.2 tests/test_driver_auto_registration.py::{test_driver_registry_registers_from_specs, test_driver_registration_handles_import_errors}
- **A. Fast triage** – Both failures report `mock_registry.load_specs` unused (call_count == 0) and, for the second test, missing `"bad.component"`. Standalone runs pass. `_build_driver_registry` is at `osiris/core/runner_v0.py:46-69` and `DriverRegistry.load_specs` at `osiris/core/driver.py:73-96`.
- **B. Root cause hypotheses & verification**
  1. A prior suite instantiates `RunnerV0` without patching `ComponentRegistry`, leaving a cached `DriverRegistry` singletons on the class that the tests reuse. Verify by `pytest -q tests/e2b/test_driver_parity.py && pytest -q tests/test_driver_auto_registration.py` – the second invocation reproduces the failure because `ComponentRegistry` was already constructed, and `DriverRegistry.load_specs` now sees `_loaded_specs` populated.
  2. `DriverRegistry.load_specs` should not short-circuit, but the class retains `_loaded_specs` per instance. In the failing run `RunnerV0.__init__` instantiates once at module import, so later tests replace `self.driver_registry` manually yet still hit the cached specs.
  3. Confirm by logging inside `_build_driver_registry` (`print(id(registry))`) via temporary patch: repeated instantiations share the same registry object when tests reuse `RunnerV0.driver_registry` monkeypatches.
- **C. Proposed fix path** – Production tweak: in `_build_driver_registry`, call `component_registry.load_specs()` directly and pass the mapping to `DriverRegistry.populate_from_component_specs`, bypassing the internal cache. Alternatively, add `registry.reset()` helper (clears `_loaded_specs`) and invoke it before populating. Update tests to assert on `registry.load_specs_call_count` rather than the mock. Preference: small production change so deterministic behaviour matches runtime expectation (always re-read specs when building a fresh runner).

### 2.3 tests/test_runner_config_cleaning.py::{test_runner_strips_meta_keys, test_cleaned_config_artifact_saved, test_config_meta_stripped_event_logged}
- **A. Fast triage** – Failures show missing `cleaned_config.json` and absent `config_meta_stripped` events. `_execute_step` writes artifacts at `osiris/core/runner_v0.py:301-339` before resolving connections. Standalone runs succeed.
- **B. Root cause hypotheses & verification**
  1. Previous suites patch `resolve_connection` globally to raise early (see `osiris/core/runner_v0.py:236-266`), so `_write_cleaned_config_artifact` never executes. Use `rg -n "resolve_connection" tests` to locate offenders; the CLI sanity tests patch it at module scope without a context manager.
  2. `log_event` patch leakage mirrors §2.1; when the helper becomes a `MagicMock`, the test filter that counts `config_meta_stripped` never sees the call even though `_log_event` appended to `runner.events`.
  3. Reproduce by running `pytest tests/cli/test_chat.py && pytest tests/test_runner_config_cleaning.py`; observe that `log_event` equals a `MagicMock` (print inside the second test).
- **C. Proposed fix path** – Adjust the tests to read the underlying artifact (`runner.output_dir/.../cleaned_config.json`) and `runner.events` instead of relying on patched `log_event`. Production guard: wrap `_resolve_step_connection` call in try/except that logs the artifact creation even when connection resolution fails, ensuring idempotent writes.

### 2.4 tests/test_supabase_ddl_generation.py::{test_ddl_plan_saved_when_table_missing, test_ddl_execute_attempt_with_sql_channel, test_ddl_plan_only_without_sql_channel}
- **A. Fast triage** – Observed symptoms: `ddl_plan.sql` missing, `psycopg2.connect` not invoked, or `table.ddl_planned` absent. Offline fixtures set `OSIRIS_TEST_SUPABASE_OFFLINE=1` (see test file lines 27-53). `_ensure_table_exists` controls telemetry at `osiris/drivers/supabase_writer_driver.py:480-551`; `_build_supabase_client` handles offline stub at `osiris/drivers/supabase_writer_driver.py:586-593`.
- **B. Root cause hypotheses & verification**
  1. `_OfflineSupabaseClient` (lines `1018+`) makes `select().execute()` succeed, so when offline mode is active without per-test patch, `_table_exists` returns `True`, skipping DDL. Verify by `python - <<'PY'` invoking `_OfflineSupabaseClient().table("demo").select(...).execute()` – it returns data rather than raising.
  2. After earlier tests patch `SupabaseClient` to a `MagicMock`, subsequent tests inherit the same factory; `_build_supabase_client` sees `module_name == 'unittest.mock'` and returns the MagicMock instead of `_OfflineSupabaseClient`. Because the mock is reused, configured `side_effect`s are exhausted, leading to silent passes that skip the DDL branch. Inspect by printing `SupabaseClient` inside the failing test (via `--pdb`).
  3. Missing DDL plan arises because `plan_only_mode` resolves true when `has_sql_channel` and `has_http_channel` are both false (connection without DSN) and `OSIRIS_TEST_FORCE_DDL` default False; plan saved but test reads wrong path after an early `return {}`. Confirm by logging `output_dir` inside `_ensure_table_exists`.
- **C. Proposed fix path** – Production: enhance `_build_supabase_client` to always return `_OfflineSupabaseClient` when `OSIRIS_TEST_SUPABASE_OFFLINE=1` unless a new env `OSIRIS_TEST_SUPABASE_FORCE_REAL_CLIENT=1` is set, so tests that need custom behaviour can opt-in. Test adjustments: introduce a shared fixture (module-level) that resets `SupabaseWriterDriver.SupabaseClient` to the real class between tests using `importlib.reload(osiris.drivers.supabase_writer_driver)` or `monkeypatch.undo`. Update tests to assert via a helper that reads `output_dir / 'ddl_plan.sql'` only after verifying the env, preventing stale state.

### 2.5 tests/test_supabase_writer_driver.py::{test_mode_mapping, test_batch_processing, test_primary_key_normalization, test_metrics_logging, test_context_manager_usage}
- **A. Fast triage** – Failures report `MagicMock` call counts at zero (insert/upsert, metrics, context manager). Files rely on patching `SupabaseClient` per test (e.g., lines 125-207). Standalone runs succeed.
- **B. Root cause hypotheses & verification**
  1. `_build_supabase_client` returning `_OfflineSupabaseClient` despite the per-test patch means the real MagicMock-level assertions never fire. Evidence: print `type(driver._build_supabase_client(...))` inside failing run; it shows `_OfflineSupabaseClient`.
  2. Shared `OSIRIS_TEST_SUPABASE_OFFLINE` env persists between tests when suite-level fixtures set it without `monkeypatch` (check `tests/writers/test_supabase_replace_matrix.py` – uses `monkeypatch` correctly, but verifying that no other test does manual `os.environ`).
  3. `plan_only_mode` short-circuits at `osiris/drivers/supabase_writer_driver.py:502-549` returning early before data writes; after DDL tests run, the driver returns `{}` without hitting the REST path, so insert/upsert mocks remain untouched.
- **C. Proposed fix path** – Same production hook as §2.4 to control offline client selection. Additionally, tweak tests to set `monkeypatch.setenv("OSIRIS_TEST_SUPABASE_FORCE_REAL_CLIENT", "1")` when they want the mocked context manager to execute, and to explicitly clear `driver._ensure_table_exists` via `monkeypatch` to bypass plan-only early return.

### 2.6 tests/writers/test_supabase_ipv6_fallback.py::TestSupabaseIPv6Fallback::test_ipv6_failure_triggers_fallback
- **A. Fast triage** – In failing suite, `psycopg2.connect` call count is zero even though the test patches it with `side_effect`. Execution path sits in `_connect_psycopg2` (`osiris/drivers/supabase_writer_driver.py:595-720`).
- **B. Root cause hypotheses & verification**
  1. Because `_build_supabase_client` returned `_OfflineSupabaseClient`, `_table_exists` sees the table present immediately and never triggers DDL, so fallback logic (which forces `_connect_psycopg2`) is skipped. Evidence: insert breakpoint inside `_table_exists` to print `client` type.
  2. When DDL short-circuits, the test's patched `_execute_http_sql` receives no call, leaving fallback asserts unfulfilled.
  3. Confirm by running `pytest tests/writers/test_supabase_ipv6_fallback.py::TestSupabaseIPv6Fallback::test_ipv6_failure_triggers_fallback --lf` after a failing `make test`; inspect `mock_http_sql.call_count` – remains zero.
- **C. Proposed fix path** – Share the offline-client override from §2.4/2.5 and add a localized fixture that sets `monkeypatch.setenv("OSIRIS_TEST_SUPABASE_FORCE_REAL_CLIENT", "1")` so the MagicMock-based client is used and the DDL branch executes deterministically.

### 2.7 tests/writers/test_supabase_writer_ddl_signature.py::test_ddl_attempt_can_be_called_with_keywords
- **A. Fast triage** – Failure arises because `_ddl_attempt` spy never records a call. Code sits at `osiris/drivers/supabase_writer_driver.py:952-965`.
- **B. Root cause hypotheses & verification**
  1. Same plan-only shortcut: `_ensure_table_exists` exits before invoking `_ddl_attempt` when offline stub says the table already exists. The spy attaches to `_ddl_attempt`, but the method is never reached.
  2. Confirm by running the test with `--pdb` in the failing sequence and checking `driver._ddl_attempt` mock – not called.
  3. Inspect events log in `tests/testing_env/logs/.../events.jsonl` from prior E2B run (if available) to ensure `_ddl_attempt` is still wired for real runs, preventing production regression.
- **C. Proposed fix path** – Modify the test to explicitly force the DDL branch (set `monkeypatch.setenv("OSIRIS_TEST_SUPABASE_FORCE_REAL_CLIENT", "1")` and ensure `_table_exists` raises on first call). Optionally augment `_ensure_table_exists` to call `_ddl_attempt` even when skipping execution (flag `plan_only=True`), which keeps telemetry consistent and would satisfy both runtime and unit tests.

### 2.8 tests/test_supabase_ddl_generation.py::TestSupabaseSupabaseDDLGeneration::test_no_ddl_when_table_exists
- **A. Fast triage** – Expectation is zero DDL events; in failing run, `table.ddl_planned` log still appears because `_OfflineSupabaseClient` fakes the missing table.
- **B. Root cause hypotheses & verification**
  1. Because `_OfflineSupabaseClient.table().select().execute()` never raises, the driver believes DDL was planned even though the test wants a no-op. The leaked offline stub (without the test’s custom MagicMock) is the culprit.
  2. Confirm via `pytest --maxfail=1` inside the suite: check `mock_log_event.call_args_list` – contains the unexpected event.
- **C. Proposed fix path** – Reuse the fixture/override from §2.4 to guarantee deterministic client behaviour. Optionally configure `_OfflineSupabaseClient` to expose knobs (env-controlled) so tests can ask it to raise on existence checks or return `data=[]` to simulate missing/existing tables explicitly.

## 3. Proposed changes (tests vs production)
- **Tests**
  - Update `tests/runtime/test_local_inputs_resolved_events.py` to validate against `runner.events` and to assert that `log_event` was monkeypatched, preventing silent skips.
  - Introduce a shared Supabase test fixture (likely in `tests/conftest.py`) that
    1. sets `OSIRIS_TEST_SUPABASE_OFFLINE=1` by default,
    2. resets `osiris.drivers.supabase_writer_driver.SupabaseClient` to the real class before each test,
    3. allows opting into the real client via `OSIRIS_TEST_SUPABASE_FORCE_REAL_CLIENT` for MagicMock-based assertions.
  - Adjust Supabase unit tests to use the new fixture/env toggle instead of ad-hoc patches, and explicitly drive the DDL branch (e.g., set `mock_table.select.return_value.limit.return_value.execute.side_effect`).
  - Where call-count assertions exist, assert against `driver.events` as a secondary signal so telemetry regressions surface even if mocks change.
- **Production**
  - In `osiris/core/runner_v0.py`, clear any cached driver specs before populating (e.g., `registry.reset()` or `registry.load_specs(ComponentRegistry())` + ignore `_loaded_specs`).
  - In `osiris/drivers/supabase_writer_driver.py`, add an env-guarded override:
    ```python
    force_real = os.getenv("OSIRIS_TEST_SUPABASE_FORCE_REAL_CLIENT", "").lower() in {"1", "true", "yes"}
    if offline_mode and not force_real:
        return _OfflineSupabaseClient()
    ```
    and ensure `_OfflineSupabaseClient` exposes switches for table-exists behaviour so tests can simulate missing/existing tables without MagicMocks.
  - Optionally have `_ensure_table_exists` emit `_ddl_attempt` telemetry even in plan-only mode, so the signature test remains valid regardless of execution branch.

## 4. Acceptance criteria per bucket
- `test_runner_emits_inputs_resolved_for_memory_inputs`: event found via `runner.events` and captured telemetry matches expected fields.
- Driver auto-registration tests: `ComponentRegistry.load_specs` observed exactly once per runner instantiation; `bad.component` present in `registry.list_drivers()`.
- Config cleaning trio: `cleaned_config.json` exists with masked secrets and `config_meta_stripped` event logged exactly once even when connection resolution fails.
- Supabase DDL trio: `ddl_plan.sql` written when the table is missing, `psycopg2.connect` invoked when SQL channel exists, and `table.ddl_planned` suppressed when no DDL needed.
- Supabase writer quintet: insert/upsert mocks called expected number of times, metrics/events recorded, context manager usage asserted.
- IPv6 fallback: `psycopg2.connect` called for each IPv4 candidate and `_execute_http_sql` invoked once.
- DDL signature: `_ddl_attempt` spy records exactly one keyword-only call.

## 5. Validation commands
- `PYTEST_ADDOPTS='--maxfail=1 -vv' make test` (ensures no regressions when the whole suite runs).
- `pytest -q tests/runtime/test_local_inputs_resolved_events.py::test_runner_emits_inputs_resolved_for_memory_inputs`
- `pytest -q tests/test_driver_auto_registration.py -vv`
- `pytest -q tests/test_runner_config_cleaning.py -vv`
- `OSIRIS_TEST_SUPABASE_FORCE_REAL_CLIENT=1 pytest -q tests/test_supabase_ddl_generation.py -vv`
- `OSIRIS_TEST_SUPABASE_FORCE_REAL_CLIENT=1 pytest -q tests/test_supabase_writer_driver.py -vv`
- `OSIRIS_TEST_SUPABASE_FORCE_REAL_CLIENT=1 pytest -q tests/writers/test_supabase_ipv6_fallback.py::TestSupabaseIPv6Fallback::test_ipv6_failure_triggers_fallback -vv`
- `pytest -q tests/writers/test_supabase_writer_ddl_signature.py::test_ddl_attempt_can_be_called_with_keywords`

## 6. Risks and mitigations
- Tightening `RunnerV0` spec loading may mask real caching bugs; mitigate by running `pytest tests/e2b/test_driver_parity.py` and `pytest tests/packaging/test_component_spec_packaging.py` after changes.
- Forcing `_OfflineSupabaseClient` could hide regressions in networked runs; gate the behaviour behind env flags and run `pytest tests/test_e2e_mysql_supabase.py::test_supabase_writer_ddl_plan_generation` with and without `OSIRIS_TEST_SUPABASE_FORCE_REAL_CLIENT` to confirm parity.
- Adding fixtures in `conftest.py` risks altering unrelated Supabase tests; document the fixture clearly and provide an opt-out flag per test to keep legacy expectations intact.
- Relying on `runner.events` in tests assumes `_log_event` continues to append; add assertions that fail loudly if the implementation stops recording events.
