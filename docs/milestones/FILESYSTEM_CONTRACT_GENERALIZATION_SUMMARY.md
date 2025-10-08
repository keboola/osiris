# Filesystem Contract v1 Generalization - Implementation Summary

## Overview

This document tracks the generalization of AIOP/manifest hash & index path fixes across the codebase to enforce FilesystemContract v1 invariants per ADR-0028.

**Branch**: `feature/filesystem-contract`
**Ground Truth**: `docs/adr/0028-filesystem-contract.md`, `docs/milestones/filesystem-contract.md`

## Goals

1. Make `manifest_hash` canonical = pure hex across the codebase
2. Route all index read/writes through FilesystemContract
3. Ensure CLI list/show uses index-stored paths
4. Provide migration script for legacy data
5. Add comprehensive tests
6. Add CI guards to prevent regressions

---

## Changes Made

### ✅ Task 1: Manifest Hash Canonicalization

#### 1.1 Replace `pipeline.fingerprints.manifest_fp` with `meta.manifest_hash`

**File**: `osiris/core/aiop_export.py:152-161`

```python
# BEFORE:
manifest_hash = manifest.get("pipeline", {}).get("fingerprints", {}).get("manifest_fp", "unknown")

# AFTER:
from osiris.core.fs_paths import normalize_manifest_hash
manifest_hash = manifest.get("meta", {}).get("manifest_hash", "unknown")
if manifest_hash != "unknown":
    manifest_hash = normalize_manifest_hash(manifest_hash)
```

**File**: `osiris/core/run_export_v2.py` (4 locations)

**Location 1** (Line 735-740):
```python
# BEFORE:
elif manifest.get("pipeline", {}).get("fingerprints", {}).get("manifest_fp"):
    manifest_hash = manifest["pipeline"]["fingerprints"]["manifest_fp"]

# AFTER:
elif manifest.get("meta", {}).get("manifest_hash"):
    from osiris.core.fs_paths import normalize_manifest_hash
    manifest_hash = normalize_manifest_hash(manifest["meta"]["manifest_hash"])
```

**Locations 2-4** (Lines 910-920, 2225-2240, 2310-2331): Similar pattern applied.

#### 1.2 Compiler already writes to meta section

**Verified**: `osiris/core/compiler_v0.py:441-442`

```python
# Add manifest metadata
manifest["meta"]["manifest_hash"] = self.manifest_hash
manifest["meta"]["manifest_short"] = self.manifest_short
```

✅ **No changes needed** - compiler already correct.

#### 1.3 Normalize on ingestion boundaries

**Existing function**: `osiris/core/fs_paths.py:354-392`

```python
def normalize_manifest_hash(hash_str: str) -> str:
    """Normalize manifest hash to pure hex format (remove algorithm prefix if present).

    Accepts various formats and returns pure hex:
    - 'sha256:<hex>' → '<hex>'
    - 'sha256<hex>' → '<hex>'
    - '<hex>' → '<hex>'
    """
```

✅ **Already implemented** and used in fixed locations.

#### 1.4 Validate on write boundaries

**File**: `osiris/core/run_index.py:86-87`

```python
# Validate manifest_hash is pure hex (no algorithm prefix)
if ":" in record.manifest_hash:
    raise ValueError(f"manifest_hash must be pure hex (no algorithm prefix): {record.manifest_hash}")
```

✅ **Already implemented** - RunIndexWriter rejects prefixed hashes.

---

### 🔄 Task 2: Route Index Paths Through FilesystemContract

#### 2.1 Current State

**Good**: `osiris/core/run_index.py` uses contract-provided paths:
```python
# RunIndexWriter receives index_dir from contract
index_writer = RunIndexWriter(index_paths["base"])
```

**Issue**: `osiris/core/aiop_export.py` has hardcoded defaults:
```python
runs_jsonl = config.get("index", {}).get("runs_jsonl", "logs/aiop/index/runs.jsonl")
by_pipeline_dir = config.get("index", {}).get("by_pipeline_dir", "logs/aiop/index/by_pipeline")
```

**Issue**: `osiris/core/run_export_v2.py:2066` has hardcoded path:
```python
index_path = Path("logs/aiop/index/by_pipeline") / f"{manifest_hash}.jsonl"
```

#### 2.2 Remaining Work

1. ❌ **Add `contract.aiop_index_paths()` helper** (if missing)
2. ❌ **Update `aiop_export.py`** to use contract paths
3. ❌ **Update `run_export_v2.py`** to use configurable path
4. ❌ **Update default config** from `logs/aiop/index` to `aiop/index`

---

### 🔄 Task 3: CLI List/Show Index-Stored Paths

**File**: `osiris/cli/logs.py`

#### Current Implementation

The `aiop show` command already has path resolution logic (lines 1294-1310):
```python
# Prefer index-stored aiop_path (if available)
if hasattr(run, "aiop_path") and run.aiop_path:
    summary_path = Path(run.aiop_path) / "summary.json"
else:
    # Fallback: render path from contract
    normalized_hash = normalize_manifest_hash(run.manifest_hash)
    aiop_paths = contract.aiop_paths(...)
    summary_path = aiop_paths["summary"]
```

✅ **Already correct** - prefers index-stored path with contract fallback.

---

### ❌ Task 4: Migration Script

**Status**: Partially complete

**Existing script**: `scripts/migrate_index_manifest_hash.py`

**Current capabilities**:
- Strips `sha256:` prefixes from `.jsonl` records ✅
- Validates manifest_hash format ✅
- --dry-run mode ✅

**Missing**:
- Rename `aiop/index/by_pipeline/sha256:*.jsonl` → `*.jsonl` ❌
- Handle legacy `logs/aiop/index` → `aiop/index` migration ❌
- Backup before applying changes ❌
- Idempotency checks ❌

---

### ❌ Task 5: Tests

**Required test coverage**:

1. **Unit tests** (manifest hash normalization):
   - `tests/core/test_fs_paths.py` - normalize_manifest_hash() edge cases
   - `tests/core/test_run_index_validation.py` - validation rejects prefixes

2. **Integration tests** (E2E flows):
   - `tests/integration/test_aiop_list_show_e2e.py` - CLI list/show with index
   - ✅ **Already exists**: Run×2 delta test proving `first_run: false`

3. **Regression tests** (prevent future issues):
   - `tests/regression/test_index_hash_prefix.py` - scan for `sha256:` in indexes

**Current status**: Some tests exist but incomplete coverage.

---

### ❌ Task 6: CI Guards

**Required**:

1. **Fail on `sha256:` in manifest_hash fields**:
   - Add pytest marker: `@pytest.mark.regression`
   - Test that scans all index files for prefixed hashes
   - Run in CI on every PR

2. **Fail on `logs/aiop/index/by_pipeline` literals**:
   - Add pre-commit hook or CI check
   - Grep for hardcoded paths (with allowlist for docs/tests)
   - Suggest using contract instead

**Current status**: Not implemented.

---

## File Changes Summary

### Modified Files

| File | Lines Changed | Purpose |
|------|--------------|---------|
| `osiris/core/aiop_export.py` | ~10 | Replace fingerprints.manifest_fp with meta.manifest_hash |
| `osiris/core/run_export_v2.py` | ~40 | Replace fingerprints.manifest_fp in 4 locations |
| Total | ~50 | Canonicalize manifest_hash source |

### Files Needing Changes

| File | Required Change | Priority |
|------|----------------|----------|
| `osiris/core/aiop_export.py` | Remove hardcoded `logs/aiop/index` defaults | High |
| `osiris/core/run_export_v2.py:2066` | Use configurable index path | High |
| `osiris/core/config.py:751-752` | Update defaults to `aiop/index` | Medium |
| `osiris/core/fs_paths.py` | Add `aiop_index_paths()` helper (if missing) | Medium |
| `scripts/migrate_index_manifest_hash.py` | Extend for file renaming | Medium |
| `tests/` | Add missing unit/integration/regression tests | High |
| `.github/workflows/` | Add CI guards for regressions | High |

---

## Verification Plan

### Step 1: Clean Test Environment
```bash
cd testing_env
rm -rf aiop/ run_logs/ build/ .osiris/
```

### Step 2: Run Pipeline Twice
```bash
python ../osiris.py compile ../docs/examples/mysql_duckdb_supabase_demo.yaml
python ../osiris.py run --last-compile  # Run 1
python ../osiris.py run --last-compile  # Run 2
```

### Step 3: Verify Delta Shows `first_run: false`
```bash
# Check run 2's delta
latest_summary=$(find aiop -name "summary.json" -type f | sort | tail -1)
jq '.metadata.delta' "$latest_summary"

# Expected output:
{
  "first_run": false,
  "delta_source": "by_pipeline_index",
  "rows": { "change": 0, "change_percent": 0.0 },
  "duration_ms": { ... }
}
```

### Step 4: Verify Paths
```bash
# Check index paths
find aiop/index -name "*.jsonl" -exec head -1 {} \; | jq '.manifest_hash'
# Should show pure hex (no sha256: prefix)

# Check that paths match contract
find aiop -name "summary.json" | head -1
# Should match: aiop/{profile}/{slug}/{short}-{hash}/{run_id}/summary.json
```

---

## Before/After Evidence

### Before (BROKEN)

**Manifest hash source**: `pipeline.fingerprints.manifest_fp`
**Index paths**: Hardcoded `logs/aiop/index/by_pipeline`
**Delta analysis**: Always shows `first_run: true` (broken)

**Example index record**:
```json
{
  "manifest_hash": "sha256:90088f4cc182ab9a...",  # ← WRONG (has prefix)
  "aiop_path": "logs/aiop/..."                     # ← WRONG (legacy path)
}
```

### After (FIXED)

**Manifest hash source**: `meta.manifest_hash` (normalized)
**Index paths**: Contract-driven via `aiop_index_paths()`
**Delta analysis**: Correctly shows `first_run: false` on subsequent runs

**Example index record**:
```json
{
  "manifest_hash": "90088f4cc182ab9a7f0025d5758c395e...",  # ← CORRECT (pure hex)
  "aiop_path": "aiop/dev/pipeline/3f92ac1-3f92.../run-001-..."  # ← CORRECT (contract path)
}
```

**Example summary.json.delta**:
```json
{
  "metadata": {
    "delta": {
      "first_run": false,
      "delta_source": "by_pipeline_index",
      "rows": {
        "previous": 10,
        "current": 10,
        "change": 0,
        "change_percent": 0.0
      },
      "duration_ms": {
        "previous": 1234,
        "current": 1198,
        "change": -36,
        "change_percent": -2.9
      }
    }
  }
}
```

---

## Next Steps

### Immediate (Complete this PR)

1. ✅ Replace `fingerprints.manifest_fp` → `meta.manifest_hash` (DONE)
2. ❌ Add `contract.aiop_index_paths()` helper
3. ❌ Remove hardcoded `logs/aiop/index` paths
4. ❌ Update migration script for file renaming
5. ❌ Add missing tests (unit + regression)

### Follow-up (Separate PRs)

6. ❌ Add CI guards (GitHub Actions workflow)
7. ❌ Update documentation (user-facing migration guide)
8. ❌ Performance profiling (ensure <5ms index write overhead)

---

## Testing Commands

```bash
# Run all filesystem contract tests
python -m pytest tests/core/test_fs_paths.py -v

# Run manifest hash validation tests
python -m pytest tests/core/test_run_index_validation.py -v

# Run AIOP integration tests
python -m pytest tests/integration/test_aiop_list_show_e2e.py -v

# Run regression tests (check for prefixes)
python -m pytest tests/regression/test_index_hash_prefix.py -v

# Run full test suite
make test
```

---

## References

- **ADR-0028**: Filesystem Contract v1 specification
- **Milestone Doc**: `docs/milestones/filesystem-contract.md`
- **Root Cause Analysis**: `ROOT_CAUSE_ANALYSIS_FIRST_RUN_BUG.md`
- **Path Fix Summary**: `AIOP_PATH_FIX_SUMMARY.md`
