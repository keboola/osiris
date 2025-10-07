# Deep-Dive Remediation Plan (Failing & Slow Tests)

## 1. Summary
Full `make test` runs still trip over Supabase writer smoke tests and local-runner telemetry assertions. The failing buckets all stem from state leakage across modules (env vars read before fixtures run, monkeypatched clients not restored) and from tests relying on patched globals (`log_event`, `ComponentRegistry`) that other suites invalidate. The plan below documents, for each failing target, the root cause, evidence within the codebase (with line numbers), and the minimal test-centric fixes required. Only if absolutely necessary do we suggest tiny prod hooks gated by `OSIRIS_TEST_*` envs.

## 2. Failure Buckets & Fix Plans

### 2.1 `tests/writers/test_supabase_ipv6_fallback.py::TestSupabaseIPv6Fallback::test_ipv6_failure_triggers_fallback`
- **Observed behaviour**
  - Logs still show `Waiting 3s for PostgREST schema cache refresh...` (`osiris/drivers/supabase_writer_driver.py:239-240`), proving the `time.sleep(3)` call survived. The current per-test fixture patches `osiris.drivers.supabase_writer_driver.time.sleep`, but the driver module is reloaded later (via other fixtures), reinstating the original function before `driver.run()` executes.
  - Regressed tests also hit real HTTP timeouts because `client.table(...).insert(...).execute()` is no longer mocked after the reload—`_prepare_records` flows directly into REST writes (same block at `:242-259`).
  - Import-time env ordering: the autouse fixtures live *inside the test module*, so they run **after** `from osiris.drivers.supabase_writer_driver import SupabaseWriterDriver` executes. Any env flag consumed once during module import (e.g. `_OfflineSupabaseClient` deciding what behaviour to mimic) ignores those late patches. `_OfflineSupabaseClient` is defined at import (file bottom), and once the module was imported earlier by other suites, the later `monkeypatch.setenv` never triggers a reload, leaving the stale MagicMock-based client in place.
  - Mock target mismatch: `_connect_psycopg2` imports `psycopg2` inside the function (`osiris/drivers/supabase_writer_driver.py:595-720`). Patching `psycopg2.connect` at the top-level (`patch("psycopg2.connect")`) misses the alias created inside the module after reload; the correct target is `osiris.drivers.supabase_writer_driver.psycopg2.connect`.

- **Fix (test-scoped) – implement in `tests/writers/conftest.py` & test file**
  1. **Pre-import guard**: Create a new module-level `tests/writers/conftest.py` that executes before any `tests/writers/*` module. Within it:
     ```python
     # tests/writers/conftest.py:1-35
     import importlib
     import os

     os.environ.setdefault("OSIRIS_TEST_SUPABASE_OFFLINE", "1")
     os.environ.setdefault("RETRY_MAX_ATTEMPTS", "1")
     os.environ.setdefault("RETRY_BASE_SLEEP", "0")

     import osiris.drivers.supabase_writer_driver as swd
     importlib.reload(swd)  # ensure env-driven defaults re-evaluated

     import pytest

     @pytest.fixture(autouse=True)
     def writers_supabase_setup(monkeypatch):
         monkeypatch.setenv("OSIRIS_TEST_SUPABASE_OFFLINE", "1")
         monkeypatch.setenv("RETRY_MAX_ATTEMPTS", "1")
         monkeypatch.setenv("RETRY_BASE_SLEEP", "0")
         # Reload to reapply env + wipe MagicMock leaks
         import importlib
         import osiris.drivers.supabase_writer_driver as swd
         importlib.reload(swd)
         # Short-circuit schema-refresh wait
         monkeypatch.setattr("osiris.drivers.supabase_writer_driver.time.sleep", lambda *_a, **_kw: None)
         yield
     ```
     This guarantees the env + reload happens before test modules import the driver.
  2. **Tighten the test** (`tests/writers/test_supabase_ipv6_fallback.py:16-115`):
     - Add `@pytest.mark.timeout(3)` atop `test_ipv6_failure_triggers_fallback`.
     - Inside the nested patches, replace `with patch("psycopg2.connect")` by `with patch("osiris.drivers.supabase_writer_driver.psycopg2.connect") as mock_connect:`.
     - Mock the REST writes explicitly to prevent httpx timeouts:
       ```python
       mock_table.insert.return_value.execute.return_value = None
       mock_table.upsert.return_value.execute.return_value = None
       ```
       and/or stub the driver helper: `monkeypatch.setattr(driver, "_execute_http_sql", MagicMock())`.
  3. **Retry clamp**: While the conftest fixture sets the env, keep a defensive function-scoped fixture to assert the env is actually applied (`assert os.getenv("RETRY_MAX_ATTEMPTS") == "1"`).

Result: sleep suppressed (patched after every reload), REST operations fully mocked, psycopg2 mock hits the correct symbol, test duration < 1s.

### 2.2 `tests/runtime/test_local_inputs_resolved_events.py::test_runner_emits_inputs_resolved_for_memory_inputs`
- **Where emission happens**: `RunnerV0._run_with_driver` emits `inputs_resolved` at `osiris/core/runner_v0.py:400-416`. The helper funnels through `_log_event` (line `:118`), which writes to `self.events` *and* calls global `log_event`.
- **Why capture fails in suite**: Earlier CLI tests permanently monkeypatch `osiris.core.runner_v0.log_event` to a `MagicMock`. When this test runs later, `monkeypatch.setattr("osiris.core.runner_v0.log_event", capture_event)` becomes a no-op because `log_event` already points to a `MagicMock` (not the original function). As a result, the capture list never sees the emission, even though `runner.events` already contains it (`type == "inputs_resolved"`).
- **Proposed change (tests only)**:
  - Replace the patched logger with direct inspection of `runner.events`. Example patch (`tests/runtime/test_local_inputs_resolved_events.py:45-74`):
    ```diff
    -    input_events = [event for event in events if event["event"] == "inputs_resolved"]
    -    assert len(input_events) == 1
    -    inputs_event = input_events[0]
    -    assert inputs_event["step_id"] == "process-step"
    +    recorded = [evt for evt in runner.events if evt["type"] == "inputs_resolved"]
    +    assert len(recorded) == 1
    +    inputs_event = recorded[0]["data"]
    +    assert inputs_event["step_id"] == "process-step"
    ```
  - Optionally keep the capture list as a safety check (`assert any(e["event"] == "inputs_resolved" for e in events)`); if the global remains a mock, the fallback still validates.
  - No production change required—the event already fires before `driver.run` returns.

### 2.3 `tests/test_driver_auto_registration.py::{test_driver_registry_registers_from_specs, test_driver_registration_handles_import_errors}`
- **Registration flow today**:
  - `RunnerV0.__init__` calls `_build_driver_registry` (`osiris/core/runner_v0.py:46-69`).
  - `_build_driver_registry` instantiates a new `DriverRegistry` (`osiris/core/driver.py:61`) and immediately calls `registry.load_specs(component_registry)` (`:73-96`). The supplied `component_registry` is the object returned by `ComponentRegistry()`.
  - In isolated runs, patching `osiris.core.runner_v0.ComponentRegistry` works because `DriverRegistry.load_specs` invokes `component_registry.load_specs()` on that MagicMock.
- **Why the assertion fails in the full suite**:
  - Earlier tests (e.g. `tests/prompts/test_build_context_secrets.py`) import `RunnerV0` before the `with patch(...)` context here. They then reload `osiris.core.runner_v0` indirectly (via Supabase fixtures). When this test runs, the `ComponentRegistry` symbol resolves to a freshly re-imported class, *outside* the patch context (the patch attaches to the old module object—see `importlib.reload` in `tests/conftest.py:supabase_test_environment`).
  - Consequently, `_build_driver_registry` calls the real `ComponentRegistry`, bypassing the mock and never hitting `mock_registry.load_specs`.
- **Targeted fix (tests)**:
  1. Immediately before entering the `with patch(...)` block, reload the module so the patch targets the current instance:
     ```python
     import importlib
     import osiris.core import runner_v0 as runner_module
     importlib.reload(runner_module)
     with patch("osiris.core.runner_v0.ComponentRegistry") as MockRegistry:
         ...
         runner = runner_module.RunnerV0(...)
     ```
     Apply in both failing tests (`tests/test_driver_auto_registration.py:40` and `:87`).
  2. Alternatively, add a helper fixture in this file:
     ```python
     @pytest.fixture
     def fresh_runner_module():
         import importlib
         import osiris.core.runner_v0 as runner_module
         return importlib.reload(runner_module)
     ```
     Then inject it into the tests to guarantee the patch sticks.
  3. After this change, the existing `mock_registry.load_specs.assert_called_once()` assertions remain valid, and `"bad.component"` appears in `list_drivers()` because the registration uses the mocked spec mapping.

### 2.4 `tests/test_runner_config_cleaning.py` (three failures)
- **Expectation**: Cleaned configs and `config_meta_stripped` telemetry appear *even if* connection resolution fails.
- **Current code**: `_execute_step` strips meta keys and writes `cleaned_config.json` at `osiris/core/runner_v0.py:301-337` **before** `_resolve_step_connection` runs. The artifact creation uses `_write_cleaned_config_artifact` (`:167-184`), which masks secrets.
- **Failure mode**: In the full suite, global fixtures replace `osiris.core.runner_v0.log_event` with `MagicMock`. The test filters (`meta_stripped_calls = [...]`) rely on `mock_log_event.call_args_list` from the patched function. If another test already substituted `log_event` before this patch, the context manager wraps the mock rather than the real function, so the `call_args_list` never grows. Additionally, some pipelines patch `resolve_connection` to raise, which can exit `_execute_step` before the second artifact write; we just need the first write.
- **Minimal remedy**:
  - Like §2.2, switch assertions to inspect `runner.events` instead of the patched callable. For example (`tests/test_runner_config_cleaning.py:103-145`):
    ```diff
    - meta_stripped_calls = [
    -     call for call in mock_log_event.call_args_list if call[0][0] == "config_meta_stripped"
    - ]
    - assert len(meta_stripped_calls) == 1
    - event_data = meta_stripped_calls[0][1]
    + event_payloads = [evt["data"] for evt in runner.events if evt["type"] == "config_meta_stripped"]
    + assert len(event_payloads) == 1
    + event_data = event_payloads[0]
    ```
  - For artifact assertions, ensure the output directory exists by calling `runner.run()` (already done) and fall back to reading `runner.output_dir / step_id / "cleaned_config.json"` even if `resolve_connection` fails—since artifact write precedes failure, the file should exist.
  - No production change required; we simply stop depending on the patched logger state.

### 2.5 Supabase DDL tests (`tests/test_supabase_ddl_generation.py::*`, `tests/test_supabase_writer_driver.py::*`, `tests/writers/test_supabase_writer_ddl_signature.py::test_ddl_attempt_can_be_called_with_keywords`)
- **Symptoms**
  - DDL tests observe that rows are written immediately (plan-only path skipped), `psycopg2.connect` never called, and `table.ddl_planned` missing. Writer unit tests note zero insert/upsert call counts and missing metrics.
  - Root cause matches the IPv6 case: once `osiris.drivers.supabase_writer_driver` is reloaded by other fixtures, the MagicMock patch from an earlier test leaks into subsequent tests. Offline reload also removes the monkeypatched `time.sleep` and resets the Supabase client.
- **Test-scoped fixes**
  1. **Shared fixture** (`tests/test_supabase_ddl_generation.py` & `tests/test_supabase_writer_driver.py`): adopt the same `tests/writers/conftest.py` strategy—set env + reload before each test module runs. For these files, add a module-level fixture:
     ```python
     @pytest.fixture(autouse=True)
     def supabase_driver_reset(monkeypatch):
         monkeypatch.setenv("OSIRIS_TEST_SUPABASE_OFFLINE", "1")
         monkeypatch.setenv("RETRY_MAX_ATTEMPTS", "1")
         monkeypatch.setenv("RETRY_BASE_SLEEP", "0")
         import importlib
         import osiris.drivers.supabase_writer_driver as swd
         importlib.reload(swd)
         monkeypatch.setattr("osiris.drivers.supabase_writer_driver.time.sleep", lambda *_a, **_kw: None)
     ```
  2. **Force DDL branch** (per test): ensure `mock_table.select.return_value.limit.return_value.execute.side_effect` first raises `Exception("Table not found")` to trigger `_ensure_table_exists`, and confirm `mock_table.insert.return_value.execute.return_value` remains `None` to avoid real HTTP.
  3. **Patch `psycopg2.connect` in the correct namespace**: change to `with patch("osiris.drivers.supabase_writer_driver.psycopg2.connect") as mock_connect` in DDL tests.
  4. **Explicit plan-only flag**: set `monkeypatch.setenv("OSIRIS_TEST_FORCE_DDL", "1")` at the start of DDL tests to guarantee the plan path, and add `driver.run(..., config={..., "ddl_plan_only": True})` where appropriate.
  5. **`_ddl_attempt` spy** (`tests/writers/test_supabase_writer_ddl_signature.py:41-75`): before invoking `driver._ddl_attempt`, ensure the module was reloaded (via fixture) so spy attaches to the live method, preventing earlier redefinitions from being captured.

- **No production change needed**; the driver already supports offline mode and plan-only behaviour. Tests simply need deterministic module state.

## 3. Validation Checklist
After applying the targeted patches above:
1. `pytest -q tests/writers/test_supabase_ipv6_fallback.py::TestSupabaseIPv6Fallback::test_ipv6_failure_triggers_fallback`
2. `pytest -q tests/runtime/test_local_inputs_resolved_events.py`
3. `pytest -q tests/test_driver_auto_registration.py`
4. `pytest -q tests/test_runner_config_cleaning.py`
5. `pytest -q tests/test_supabase_ddl_generation.py`
6. `pytest -q tests/test_supabase_writer_driver.py`
7. `pytest -q tests/writers/test_supabase_writer_ddl_signature.py`
8. Full `PYTEST_ADDOPTS='--maxfail=1 -vv' make test`

Each command should complete in <1s per test group (IPv6 fallback bounded by the new timeout). Module reloads guarantee that later suites see pristine Supabase driver state, and telemetry assertions now read from Runner-owned buffers rather than global mocks.
