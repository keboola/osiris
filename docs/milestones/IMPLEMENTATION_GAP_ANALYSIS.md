# Filesystem Contract v1 - Implementation Gap Analysis

**Branch**: `feature/filesystem-contract`
**Milestone**: `docs/milestones/filesystem-contract.md`
**ADR**: `docs/adr/0028-filesystem-contract.md`
**Date**: 2025-10-07

## Executive Summary

**Completion Status: ~25% (Foundation Only)**

The implementation delivered **only the foundation layer** (new modules and basic tests) but **missed all integration work** required to make the filesystem contract functional. The system cannot actually use the new directory structure because:

1. ❌ CLI commands still write to legacy `logs/` (not updated)
2. ❌ Compiler still writes to old `compiled/` directory (not updated)
3. ❌ No way to generate config with filesystem contract (`osiris init` broken)
4. ❌ No new CLI commands (`osiris runs`, `osiris maintenance`, etc.)
5. ❌ No integration tests to validate the contract works end-to-end

## What Was Requested (Milestone Specification)

### Phase 1: Foundation ✅ (DELIVERED - 80%)
- [x] `osiris/core/fs_config.py` - Typed config models
- [x] `osiris/core/fs_paths.py` - FilesystemContract and TokenRenderer
- [x] `osiris/core/run_ids.py` - RunIdGenerator with CounterStore
- [ ] **MISSING**: Update `create_sample_config()` to include filesystem contract

### Phase 2: Core Services ⚠️ (PARTIAL - 40%)
- [x] `osiris/core/run_index.py` - RunIndexWriter/Reader
- [ ] **MISSING**: Update `osiris/core/compiler_v0.py` to use FilesystemContract
- [ ] **MISSING**: Add `load_raw_config()` to `osiris/core/config.py`

### Phase 3: Runtime & AIOP ❌ (NOT STARTED - 0%)
- [x] `osiris/core/retention.py` - RetentionPlan (created but not integrated)
- [ ] **MISSING**: Update `osiris/core/session_logging.py` for contract paths
- [ ] **MISSING**: Update `osiris/core/aiop_export.py` to use contract paths
- [ ] **MISSING**: Update `osiris/core/runner_v0.py` to use FilesystemContract
- [ ] **MISSING**: Update `osiris/core/run_export_v2.py` for new build paths
- [ ] **MISSING**: Rename `logs_serialize.py` → `run_logs_serializer.py`
- [ ] **MISSING**: Rename `session_reader.py` → `run_logs_reader.py`

### Phase 4: CLI Integration ❌ (NOT STARTED - 0%)
- [ ] **MISSING**: Update `osiris/cli/compile.py` to instantiate FilesystemContract
- [ ] **MISSING**: Update `osiris/cli/run.py` to use contract and run IDs
- [ ] **MISSING**: Create `osiris/cli/runs.py` for `osiris runs list/show`
- [ ] **MISSING**: Create `osiris/cli/aiop.py` for `osiris aiop list/show`
- [ ] **MISSING**: Create `osiris/cli/maintenance.py` for `osiris maintenance clean`
- [ ] **MISSING**: Update `osiris/cli/logs.py` to use `run_logs/` directory
- [ ] **MISSING**: Update `osiris/cli/main.py` to register new commands

### Phase 5: Testing ⚠️ (PARTIAL - 30%)
**Unit Tests (Delivered)**:
- [x] `tests/core/test_fs_config.py` - 19 tests ✅
- [x] `tests/core/test_fs_paths.py` - 27 tests ✅
- [x] `tests/core/test_run_ids.py` - 11 tests ✅
- [x] `tests/regression/test_no_legacy_logs.py` - Regression guard ✅

**Missing Tests**:
- [ ] `tests/core/test_run_index.py` - Index writer/reader unit tests
- [ ] `tests/core/test_retention.py` - Retention plan unit tests
- [ ] `tests/golden/build_dev_orders/` - Golden build tree snapshot
- [ ] `tests/golden/run_logs_dev_orders/` - Golden run logs layout
- [ ] `tests/golden/aiop_orders_run/` - Golden AIOP structure
- [ ] `tests/integration/test_compile_run_profiles.py` - E2E compile+run with profiles
- [ ] `tests/integration/test_runs_cli.py` - CLI runs command testing
- [ ] `tests/integration/test_retention_cli.py` - Retention command testing
- [ ] `tests/integration/test_last_manifest_pointer.py` - Latest pointer resolution
- [ ] `tests/integration/test_e2b_parity.py` - E2B vs local parity (update existing)

### Phase 6: Documentation ⚠️ (PARTIAL - 40%)
- [x] `.gitignore` updated with new patterns ✅
- [x] `CHANGELOG.md` entry with migration notes ✅
- [x] `docs/adr/0028-filesystem-contract.md` (Status: Accepted) ✅
- [x] `docs/milestones/filesystem-contract.md` ✅
- [ ] **MISSING**: `docs/samples/osiris.filesystem.yaml` - Sample config
- [ ] **MISSING**: CLI help text updates for new commands
- [ ] **MISSING**: Update user guides to reference new directories

## Critical Gaps (Blockers)

### 1. **Config Generation Broken** 🔴
**File**: `osiris/core/config.py:57` (`create_sample_config()`)
**Issue**: Function returns hardcoded YAML without `filesystem:` or `ids:` sections
**Impact**: `osiris init` generates incomplete config
**Milestone Ref**: Line 312 - "ship `docs/samples/osiris.filesystem.yaml` and reference it from `osiris init` scaffolder"

### 2. **Compiler Not Integrated** 🔴
**File**: `osiris/core/compiler_v0.py`
**Issue**: Still writes to `self.output_dir` (defaults to `compiled/`) instead of using FilesystemContract
**Impact**: Compiled artifacts go to wrong location
**Milestone Ref**: Lines 67-70 - "accept contract + pipeline/profile context, call `resolve_build_artifacts()`, compute manifest hash via shared helper, drop writes to `logs/`"

### 3. **CLI Commands Not Updated** 🔴
**Files**: `osiris/cli/compile.py`, `osiris/cli/run.py`, `osiris/cli/logs.py`
**Issue**: No FilesystemContract instantiation, still use legacy paths
**Impact**: All CLI operations use old directory structure
**Milestone Ref**: Lines 77-90 - Detailed CLI integration requirements

### 4. **New CLI Commands Missing** 🔴
**Files**: `osiris/cli/runs.py`, `osiris/cli/aiop.py`, `osiris/cli/maintenance.py`
**Issue**: Commands don't exist
**Impact**: Cannot use `osiris runs list`, `osiris maintenance clean`, etc.
**Milestone Ref**: Lines 275-281 - CLI UX specification

### 5. **Session Logging Not Updated** 🔴
**File**: `osiris/core/session_logging.py`
**Issue**: Creates session directories in legacy locations
**Impact**: Logs still written to `logs/` instead of `run_logs/`
**Milestone Ref**: Line 68 - "update constructor signature, directory derivation, metadata capture"

### 6. **AIOP Not Integrated** 🔴
**File**: `osiris/core/aiop_export.py`
**Issue**: Still uses old path formatting
**Impact**: AIOP written to legacy `logs/aiop/` instead of contract `aiop/` directory
**Milestone Ref**: Line 71 - "replace direct path formatting with contract-based resolution"

## Acceptance Criteria Status (Section 11)

| Criterion | Status | Notes |
|-----------|--------|-------|
| Compile/run write to build/, run_logs/, aiop/, .osiris/** | ❌ | Still writes to logs/ and compiled/ |
| .osiris/index/runs.jsonl populated | ❌ | Index writer exists but not called |
| .osiris/index/counters.sqlite increments safely | ✅ | Tested in unit tests |
| SessionContext uses naming templates | ❌ | SessionContext not updated |
| AIOP writes summary.json at contract path | ❌ | AIOP exporter not updated |
| Retention deletes run_logs/annex only | ⚠️ | RetentionPlan exists but no CLI integration |
| CI guard prevents logs/ writes | ✅ | Regression test exists |
| Sample osiris.yaml validated | ❌ | Sample config doesn't exist |
| E2B parity tests pass | ❌ | Tests not created |
| Documentation updated | ⚠️ | ADR done, CLI help missing |

**Score: 2/10 criteria met** ❌

## What Was Actually Delivered

### ✅ New Modules Created (Foundation)
1. `osiris/core/fs_config.py` (238 lines) - Config models and loading
2. `osiris/core/fs_paths.py` (334 lines) - Path resolution and token rendering
3. `osiris/core/run_ids.py` (197 lines) - Run ID generation
4. `osiris/core/run_index.py` (207 lines) - Index management
5. `osiris/core/retention.py` (273 lines) - Retention policy

**Total: ~1,249 lines of new code**

### ✅ Tests Created
1. `tests/core/test_fs_config.py` (19 tests)
2. `tests/core/test_fs_paths.py` (27 tests)
3. `tests/core/test_run_ids.py` (11 tests)
4. `tests/regression/test_no_legacy_logs.py` (3 tests)

**Total: 60 tests, all passing ✅**

### ✅ Documentation Updated
1. `.gitignore` - Added new directory patterns
2. `CHANGELOG.md` - Breaking changes entry with migration notes
3. `docs/adr/0028-filesystem-contract.md` - ADR document
4. `docs/milestones/filesystem-contract.md` - Milestone document

## Why Nothing Works

The implementation is **not usable** because:

1. **No entry point**: CLI commands (`osiris compile`, `osiris run`) don't use the new contract
2. **No config scaffolding**: Users can't generate the required config via `osiris init`
3. **No integration**: Core modules (compiler, runner, session_logging) unmodified
4. **No validation**: No integration tests to prove the contract works end-to-end

### Example: Running a Pipeline

**Expected behavior** (per milestone):
```bash
osiris compile pipelines/orders.yaml --profile prod
# Should write to: build/pipelines/prod/orders-etl/{hash}/manifest.yaml
# Should update: .osiris/index/latest/orders_etl.txt

osiris run --last-compile --profile prod
# Should write logs to: run_logs/prod/orders-etl/{ts}_{run_id}-{hash}/
# Should write AIOP to: aiop/prod/orders-etl/{hash}/{run_id}/
```

**Actual behavior** (current):
```bash
osiris compile pipelines/orders.yaml --profile prod
# ERROR: Unknown option --profile (not implemented)
# Writes to: compiled/ (old location)
# No index update

osiris run compiled/manifest.yaml
# Writes logs to: logs/{session_id}/ (old location)
# AIOP goes to: logs/aiop/ (old location)
```

## Estimated Remaining Work

| Phase | Files | Est. Hours | Complexity |
|-------|-------|------------|------------|
| Fix config generation | 1 file | 2h | Low |
| Update core modules | 6 files | 12h | Medium |
| Update CLI integration | 5 files | 16h | High |
| Create new CLI commands | 3 files | 12h | Medium |
| Integration tests | 6 test files | 10h | Medium |
| Golden tests | 3 test suites | 6h | Low |
| Documentation | 3 files | 4h | Low |
| **Total** | **24 files** | **62 hours** | **~8 days** |

## Risk Assessment

### High Risk Issues
1. **Breaking change deployed without migration**: Users upgrade and everything breaks
2. **Data loss**: Old logs/ directory deleted before migration to new structure
3. **E2B parity broken**: Remote execution may behave differently

### Mitigation Required
1. Mark this branch as **WIP/DRAFT** - not ready for merge
2. Complete all integration work before merging
3. Test with real pipelines in `testing_env/`
4. Add migration script for users with existing `logs/` data

## Recommended Next Steps

### Immediate (Critical Path)
1. **Fix `create_sample_config()`** - Add filesystem contract to generated YAML
2. **Update compiler** - Use FilesystemContract for output paths
3. **Update CLI compile/run** - Instantiate contract, generate run IDs
4. **Integration test** - One end-to-end test proving compile → run works

### Then (Essential)
5. Update session_logging, aiop_export, runner_v0
6. Create new CLI commands (runs, maintenance, aiop)
7. Add golden tests for directory structure
8. Update all integration tests

### Finally (Polish)
9. Create sample config file
10. Update user documentation
11. Migration script for legacy logs/

## Conclusion

**The implementation is incomplete (25% done).** What was delivered:
- ✅ Strong foundation with well-tested new modules
- ✅ Clear architecture and data models
- ✅ Good documentation of the design

What's missing:
- ❌ **All integration work** - the foundation isn't connected to anything
- ❌ **Config generation** - users can't bootstrap the new contract
- ❌ **CLI updates** - existing commands don't use the new system
- ❌ **New commands** - promised functionality doesn't exist
- ❌ **Integration tests** - no proof the system works end-to-end

**This branch should NOT be merged** until integration work is complete. The filesystem contract is currently non-functional.
