# Root Cause Analysis: "First run with this configuration" Bug

**Issue**: All runs show "*First run with this configuration*" in run-card.md, even when multiple runs of the same manifest exist.

**Branch**: `feature/filesystem-contract`
**Date**: 2025-10-08
**Reporter**: User testing in `testing_env/`
**Severity**: **High** - Delta analysis completely broken

---

## Executive Summary

The delta analysis system that detects repetitive executions is **completely broken** due to a **hash format mismatch** between:
1. **AIOP Index Writer**: Stores hash with `sha256:` prefix
2. **Delta Calculator**: Looks up hash without prefix (pure hex)

This causes `calculate_delta()` to **never find previous runs**, resulting in all runs being incorrectly marked as "first run".

---

## Evidence

### 1. Manifest Hash (Ground Truth)

**File**: `build/pipelines/dev/mysql-duckdb-supabase-demo/.../manifest.yaml`

```yaml
meta:
  generated_at: '2025-10-08T18:32:33.408733Z'
  manifest_hash: 5d80d8792b017a252e19f8fda780f5ab75fdb551a1538d90a2c2d5400ba59893  # ← Pure hex
  manifest_short: 5d80d87
```

✅ **Correct**: Pure hex (no algorithm prefix) per ADR-0028

---

### 2. AIOP Index (Broken)

**File**: `aiop/index/by_pipeline/sha256:90088f4cc182ab9a7f0025d5758c395e5fe23b6dbdfc49ad5778d7ac8e607a28.jsonl`

❌ **Problem 1**: Filename uses `sha256:` prefixed hash
❌ **Problem 2**: Different hash value than manifest!

**Index Record Content**:
```json
{
  "session_id": "run_1759948333656",
  "manifest_hash": "sha256:90088f4cc182ab9a7f0025d5758c395e5fe23b6dbdfc49ad5778d7ac8e607a28",
  // ↑ Prefixed hash (wrong)
  "status": "completed",
  "duration_ms": 0,
  "total_rows": 10
}
```

**Expected Filename**: `5d80d8792b017a252e19f8fda780f5ab75fdb551a1538d90a2c2d5400ba59893.jsonl`
**Actual Filename**: `sha256:90088f4cc182ab9a7f0025d5758c395e5fe23b6dbdfc49ad5778d7ac8e607a28.jsonl`

---

### 3. Delta Calculation (Looking in Wrong Place)

**File**: `osiris/core/run_export_v2.py:2060`

```python
def _find_previous_run_by_manifest(manifest_hash: str, current_session_id: str = None) -> dict | None:
    # Look up in by_pipeline index
    index_path = Path("logs/aiop/index/by_pipeline") / f"{manifest_hash}.jsonl"
    # ↑ Expects pure hex: 5d80d8792b017a252e19f8fda780f5ab75fdb551a1538d90a2c2d5400ba59893.jsonl

    if not index_path.exists():
        return None  # ← ALWAYS returns None because filename has prefix!
```

**What it's looking for**: `logs/aiop/index/by_pipeline/5d80d87...93.jsonl`
**What actually exists**: `aiop/index/by_pipeline/sha256:90088f4...28.jsonl`

Result: **File not found** → Returns `None` → Delta shows `first_run: true`

---

### 4. AIOP Summary Delta (Broken)

**File**: `aiop/dev/mysql-duckdb-supabase-demo/.../run-000002-01k72hhh5kkj7yb50yz3evepsc/summary.json`

```json
{
  "metadata": {
    "delta": {
      "first_run": true,           // ← WRONG (this is 2nd run!)
      "delta_source": "by_pipeline_index"
    }
  }
}
```

**Expected for 2nd run**:
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
      }
    }
  }
}
```

---

## Root Causes

### Primary Root Cause

**Location**: Where `manifest_hash` is passed to `_update_indexes()` in `aiop_export.py`

The hash being passed to the index writer has the `sha256:` prefix, causing:
1. Index file to be created with prefixed filename
2. Index records to contain prefixed hash values
3. Delta lookup to fail (searches for pure hex filename)

### Secondary Root Cause (Hash Value Mismatch)

There are **TWO DIFFERENT HASHES** in use:
1. **Manifest hash**: `5d80d8792b017a252e19f8fda780f5ab75fdb551a1538d90a2c2d5400ba59893`
2. **AIOP index hash**: `90088f4cc182ab9a7f0025d5758c395e5fe23b6dbdfc49ad5778d7ac8e607a28`

This suggests the AIOP export is receiving a **different hash** than what's in the manifest. Likely caused by:
- Reading hash from wrong location (e.g., `pipeline.fingerprints.manifest_fp` instead of `meta.manifest_hash`)
- This is the **EXACT BUG WE JUST FIXED** in the AIOP path mismatch work!

---

## Call Stack Analysis

### Where the Bug Originates

1. **`osiris/cli/run.py:804-816`** (Finally block - AIOP export)
   ```python
   export_success, export_error = export_aiop_auto(
       session_id=session_id,
       manifest_hash=manifest_hash,  # ← Where does this come from?
       status=final_status,
       end_time=datetime.utcnow(),
       ...
   )
   ```

2. **`osiris/cli/run.py:797`** (Hash extraction - JUST FIXED)
   ```python
   # Manifest hash is at meta.manifest_hash (pure hex, no algorithm prefix)
   manifest_hash = manifest_data.get("meta", {}).get("manifest_hash", "")
   ```

   ✅ **This was fixed** in our recent work, but the fix may not have been applied before the test runs.

3. **`osiris/core/aiop_export.py:244-260`** (Index update)
   ```python
   _update_indexes(
       session_id=session_id,
       manifest_hash=manifest_hash,  # ← Passed through from run.py
       status=status,
       ...
   )
   ```

4. **`osiris/core/aiop_export.py:478-483`** (Index writer)
   ```python
   if manifest_hash and manifest_hash != "unknown":
       by_pipeline_dir = config.get("index", {}).get("by_pipeline_dir", "logs/aiop/index/by_pipeline")
       Path(by_pipeline_dir).mkdir(parents=True, exist_ok=True)
       pipeline_index = Path(by_pipeline_dir) / f"{manifest_hash}.jsonl"  # ← Uses hash as-is!
       with open(pipeline_index, "a") as f:
           f.write(json.dumps(record) + "\n")
   ```

   ❌ **No validation** - accepts prefixed hash and uses it directly in filename

---

## Why Delta Analysis Fails

**Step-by-step execution flow**:

1. **Run #1**:
   - AIOP export receives: `manifest_hash = "sha256:90088f4..."`
   - Creates index: `aiop/index/by_pipeline/sha256:90088f4....jsonl`
   - Delta lookup searches for: `logs/aiop/index/by_pipeline/sha256:90088f4....jsonl`
   - File not found (wrong directory: `logs/` vs `./`)
   - Result: `first_run: true` ✓ (correct for first run)

2. **Run #2**:
   - AIOP export receives: `manifest_hash = "sha256:90088f4..."`
   - Appends to index: `aiop/index/by_pipeline/sha256:90088f4....jsonl`
   - Delta lookup searches for: `logs/aiop/index/by_pipeline/sha256:90088f4....jsonl`
   - File still not found (wrong directory)
   - Result: `first_run: true` ❌ (WRONG! Should be false)

3. **Run #3**:
   - Same as Run #2
   - Result: `first_run: true` ❌ (WRONG!)

**Even if the directory was correct**, the hash mismatch would still break it:
- Index has: `sha256:90088f4...` (wrong hash)
- Manifest has: `5d80d87...` (correct hash)
- These would never match!

---

## Compounding Issues

### Issue 1: Path Prefix Mismatch

**AIOP Index Writer** uses: `logs/aiop/index/by_pipeline/` (hardcoded default)
**Delta Lookup** uses: `logs/aiop/index/by_pipeline/` (same hardcoded path)
**Actual writes go to**: `aiop/index/by_pipeline/` (relative to cwd)

The config default of `"logs/aiop/index/by_pipeline"` doesn't match the actual FilesystemContract structure.

### Issue 2: Hash Source Bug (Fixed but Not Applied)

The bug where `run.py` reads hash from `pipeline.fingerprints.manifest_fp` instead of `meta.manifest_hash` was **just fixed** in our recent work, but these test runs used the **old code** before the fix.

---

## Impact Assessment

### User-Facing Impact

✅ **What works**:
- Pipelines execute successfully
- AIOP files are generated
- Run-cards are created
- Indexes are populated

❌ **What's broken**:
- **Delta analysis**: Always shows "first run"
- **Run comparison**: No comparison metrics (rows delta, duration delta)
- **Regression detection**: Cannot detect if runs are slower/faster than before
- **Anomaly detection**: Cannot identify unusual behavior vs previous runs
- **LLM analysis**: AI cannot understand run-to-run changes

### Severity Breakdown

| Component | Status | Impact |
|-----------|--------|--------|
| Pipeline execution | ✅ Works | None |
| AIOP generation | ✅ Works | None |
| Run-card generation | ✅ Works | None |
| Index creation | ⚠️ Partial | Wrong hash/location |
| **Delta analysis** | ❌ **Broken** | **Critical - Core feature lost** |
| Intent discovery | ✅ Works | None |
| Narrative generation | ⚠️ Degraded | Shows "first run" incorrectly |

---

## Fix Strategy

### Immediate Fixes Required

#### Fix 1: Apply Recent Hash Source Fix
Ensure the fix from `run.py:797` is actually being used:

```python
# CORRECT (from our recent fix):
manifest_hash = manifest_data.get("meta", {}).get("manifest_hash", "")

# WRONG (old code):
manifest_hash = manifest_data.get("pipeline", {}).get("fingerprints", {}).get("manifest_fp", "")
```

#### Fix 2: Add Validation to Index Writer

**File**: `osiris/core/aiop_export.py:478`

```python
# Add validation before using hash
if manifest_hash and manifest_hash != "unknown":
    # Validate hash is pure hex (no algorithm prefix)
    if ":" in manifest_hash:
        # Strip prefix if present (defensive)
        from .fs_paths import normalize_manifest_hash
        manifest_hash = normalize_manifest_hash(manifest_hash)

    by_pipeline_dir = config.get("index", {}).get("by_pipeline_dir", "logs/aiop/index/by_pipeline")
    Path(by_pipeline_dir).mkdir(parents=True, exist_ok=True)
    pipeline_index = Path(by_pipeline_dir) / f"{manifest_hash}.jsonl"
```

#### Fix 3: Update Delta Lookup Path

**File**: `osiris/core/run_export_v2.py:2060`

The hardcoded path `"logs/aiop/index/by_pipeline"` should be configurable and respect the working directory:

```python
def _find_previous_run_by_manifest(manifest_hash: str, current_session_id: str = None, config: dict = None) -> dict | None:
    if not manifest_hash or manifest_hash == "unknown":
        return None

    # Use config or default to aiop/index/by_pipeline (matching where writes go)
    if config:
        by_pipeline_dir = config.get("index", {}).get("by_pipeline_dir", "aiop/index/by_pipeline")
    else:
        # Try both locations for backward compatibility
        by_pipeline_dir = "aiop/index/by_pipeline"
        if not Path(by_pipeline_dir).exists():
            by_pipeline_dir = "logs/aiop/index/by_pipeline"

    index_path = Path(by_pipeline_dir) / f"{manifest_hash}.jsonl"
```

### Migration for Existing Runs

Since the index files were created with prefixed hashes, we need to:

1. **Rename index files**: Strip `sha256:` prefix from filenames
2. **Update index records**: Strip prefix from `manifest_hash` field values
3. **Use migration script**: Extend our existing `migrate_index_manifest_hash.py` to handle AIOP indexes

---

## Test Plan

### Verification Steps

1. **Apply fixes** from above
2. **Clean test environment**:
   ```bash
   cd testing_env
   rm -rf aiop/index/by_pipeline/*
   rm -rf aiop/dev/*
   ```
3. **Run twice**:
   ```bash
   python ../osiris.py compile ../docs/examples/mysql_duckdb_supabase_demo.yaml
   python ../osiris.py run --last-compile  # Run 1
   python ../osiris.py run --last-compile  # Run 2
   ```
4. **Verify delta**:
   ```bash
   # Check run 2's delta
   cat aiop/dev/mysql-duckdb-supabase-demo/*/run-000002*/summary.json | \
       jq '.metadata.delta'

   # Expected output:
   {
     "first_run": false,
     "delta_source": "by_pipeline_index",
     "rows": { ... },
     "duration_ms": { ... }
   }
   ```
5. **Check run-card**:
   ```bash
   cat aiop/dev/mysql-duckdb-supabase-demo/*/run-000002*/run-card.md | head -20
   ```

   Should show delta comparison, NOT "*First run with this configuration*"

---

## Related Issues

### Connection to Recent Fix

This bug is **directly related** to the AIOP path mismatch fix we just completed:

**Files Changed in That Fix**:
- `osiris/cli/run.py:659, 796-802` - Fixed hash source
- `osiris/core/run_index.py:86-87` - Added hash validation
- `osiris/core/fs_paths.py:355-392` - Added `normalize_manifest_hash()`

**Status**: ✅ Fixed in code, ❌ Not yet applied to testing_env

**Action**: Need to rebuild/recompile with latest code before re-testing

---

## Recommendations

### Short-term (Fix the Bug)

1. ✅ **Verify recent fix is applied** - Check if `run.py` is using `meta.manifest_hash`
2. ✅ **Add defensive normalization** - Use `normalize_manifest_hash()` in index writer
3. ✅ **Fix delta lookup path** - Make configurable, try both locations
4. ✅ **Extend migration script** - Handle AIOP indexes in addition to run indexes

### Long-term (Prevent Recurrence)

1. **Add integration test** for delta analysis (compile → run × 2 → verify delta)
2. **Add assertion** in index writer to reject prefixed hashes
3. **Centralize path configuration** - Use FilesystemContract for AIOP paths
4. **Add validation** to ensure `manifest_hash` matches across all systems

---

## Conclusion

**Root Cause**: Hash format mismatch - AIOP index writer uses prefixed hash (`sha256:...`), delta lookup expects pure hex.

**Fix Complexity**: Low (defensive normalization + path fix)

**Test Impact**: High (completely broken delta analysis)

**Priority**: **P0** - Core AIOP feature is non-functional

**Estimated Fix Time**: 30 minutes

**Related Work**: This is a **direct continuation** of the AIOP path mismatch fix we just completed. The same normalization helper (`normalize_manifest_hash()`) can be reused here.
