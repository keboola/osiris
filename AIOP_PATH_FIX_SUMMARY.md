# AIOP Path Mismatch Fix - Summary

**Branch**: `feature/filesystem-contract`
**Date**: 2025-10-08
**Issue**: Manifest hash source mismatch causing AIOP path inconsistencies

---

## Problem Statement

The AIOP (AI Operation Package) path resolution was broken due to:

1. **Incorrect hash source**: `run.py` was reading `manifest_hash` from `pipeline.fingerprints.manifest_fp` instead of `meta.manifest_hash`
2. **No validation**: Index writer accepted hashes with algorithm prefixes (e.g., `sha256:abc123`)
3. **Path resolution issues**: `logs.py` commands didn't use stored `aiop_path` from index, causing path mismatches

Per **ADR-0028** and **FilesystemContract v1**, `manifest_hash` must be:
- Pure hex (no algorithm prefix)
- Stored in `manifest.meta.manifest_hash`
- Used consistently across all path resolutions

---

## Changes Implemented

### 1. Fixed Hash Source in `run.py`

**Files Modified**: `osiris/cli/run.py`

**Changes**:
- Line 659: Extract from `meta.manifest_hash` instead of `pipeline.fingerprints.manifest_fp`
- Lines 585-589: Derive `manifest_short` from `meta.manifest_short` or `meta.manifest_hash[:7]`
- Lines 796-802: AIOP export uses correct hash source with proper fallback

**Before**:
```python
manifest_hash = manifest_data.get("pipeline", {}).get("fingerprints", {}).get("manifest_fp", "")
```

**After**:
```python
manifest_hash = manifest_data.get("meta", {}).get("manifest_hash", "")
manifest_short = manifest_data.get("meta", {}).get("manifest_short") or (
    manifest_hash[:7] if manifest_hash else ""
)
```

---

### 2. Added Validation in `run_index.py`

**Files Modified**: `osiris/core/run_index.py`

**Changes**:
- Added validation in `RunIndexWriter.append()` to reject prefixed hashes
- Raises `ValueError` if `manifest_hash` contains `:`

**Implementation**:
```python
def append(self, record: RunRecord) -> None:
    # Validate manifest_hash is pure hex (no algorithm prefix)
    if ":" in record.manifest_hash:
        raise ValueError(f"manifest_hash must be pure hex (no algorithm prefix): {record.manifest_hash}")

    # ... rest of append logic
```

---

### 3. Added Hash Normalization Helper

**Files Modified**: `osiris/core/fs_paths.py`

**New Function**: `normalize_manifest_hash(hash_str: str) -> str`

Handles edge cases during migration:
- `sha256:abc123` → `abc123`
- `sha256abc123` → `abc123`
- `abc123` → `abc123`

**Usage**:
```python
from osiris.core.fs_paths import normalize_manifest_hash

clean_hash = normalize_manifest_hash("sha256:abc123def456")  # pragma: allowlist secret
# Returns: "abc123def456"  # pragma: allowlist secret
```

---

### 4. Updated `logs.py` to Prefer Index Paths

**Files Modified**: `osiris/cli/logs.py`

**Changes** (lines 1294-1310, 1404-1420):
- `aiop_list`: Prefer `run.aiop_path` from index; fallback to `FilesystemContract` with normalized hash
- `aiop_show`: Same path resolution strategy

**Implementation**:
```python
if run.aiop_path:
    # Use stored path from index
    summary_path = Path(run.aiop_path) / "summary.json"
else:
    # Fallback: compute with FilesystemContract (normalize hash if needed)
    from osiris.core.fs_paths import normalize_manifest_hash

    normalized_hash = normalize_manifest_hash(run.manifest_hash)
    aiop_paths = contract.aiop_paths(
        pipeline_slug=run.pipeline_slug,
        manifest_hash=normalized_hash,
        manifest_short=run.manifest_short,
        run_id=run.run_id,
        profile=run.profile or None,
    )
    summary_path = aiop_paths["summary"]
```

---

### 5. Created Migration Script

**New File**: `scripts/migrate_index_manifest_hash.py`

**Features**:
- Strips algorithm prefixes from `manifest_hash` in all index files
- Processes `.osiris/index/runs.jsonl` and per-pipeline indexes
- Creates `.bak` backups before modifying
- Dry-run mode by default (use `--apply` to commit changes)

**Usage**:
```bash
# Dry run (preview changes)
python scripts/migrate_index_manifest_hash.py

# Apply changes
python scripts/migrate_index_manifest_hash.py --apply

# Custom index directory
python scripts/migrate_index_manifest_hash.py --index-dir /path/to/.osiris/index --apply
```

---

## Tests Added

### Unit Tests

1. **`tests/core/test_run_index_validation.py`** (6 tests)
   - ✅ Rejects `sha256:` prefix
   - ✅ Rejects custom prefixes
   - ✅ Accepts pure hex (64 chars)
   - ✅ Allows empty hash (edge case)
   - ✅ Rejects colon anywhere in hash

2. **`tests/cli/test_manifest_hash_source.py`** (6 tests)
   - ✅ Extracts hash from `meta.manifest_hash`
   - ✅ Derives `manifest_short` correctly
   - ✅ AIOP export uses correct hash source
   - ✅ Handles missing `meta.manifest_hash` gracefully
   - ✅ `RunRecord` creation uses correct fields

### Regression Tests

3. **`tests/regression/test_index_hash_prefix.py`** (3 tests)
   - Scans all index files for prefixed hashes
   - Checks latest pointers for pure hex
   - Validates `normalize_manifest_hash` helper

### Integration Tests

4. **`tests/integration/test_aiop_list_show_e2e.py`** (2 tests)
   - E2E: compile → run × 2 → `aiop list` → `aiop show`
   - Verifies `aiop_path` from index is preferred over FilesystemContract fallback

---

## Test Results

All tests passing:

```bash
# Unit tests (12 tests)
pytest tests/core/test_run_index_validation.py -v        # 6 passed
pytest tests/cli/test_manifest_hash_source.py -v         # 6 passed

# Regression tests (3 tests)
pytest tests/regression/test_index_hash_prefix.py -v     # 1 passed, 2 skipped

# Integration tests (2 tests)
pytest tests/integration/test_aiop_list_show_e2e.py -v   # 1 passed, 1 skipped
```

**Total**: 13 tests passing, 3 skipped (expected when no index exists)

---

## Acceptance Criteria

Per task requirements:

✅ **1. Pure hex `manifest_hash`** everywhere (from `meta.manifest_hash`)
✅ **2. AIOP exporter and RunIndex** use FilesystemContract paths
✅ **3. `osiris logs aiop list/show`** prefer `aiop_path` from index
✅ **4. Validation + tests** added
✅ **5. Migration helper** provided

---

## Migration Path

### For Existing Users

1. **Update code** to this branch
2. **Run migration** (if you have existing runs):
   ```bash
   python scripts/migrate_index_manifest_hash.py --apply
   ```
3. **Verify** no prefixed hashes remain:
   ```bash
   pytest tests/regression/test_index_hash_prefix.py -v
   ```

### For New Users

No migration needed. All new runs will use pure hex hashes from `meta.manifest_hash`.

---

## Constraints Met

✅ No legacy `logs//compiled/` assumptions
✅ All paths via FilesystemContract or index `aiop_path`
✅ Minimal diffs (surgical changes)
✅ Correctness and determinism prioritized

---

## Smoke Test Commands

Run these commands in `testing_env/` to verify the fix:

```bash
# 1. Compile pipeline
python ../osiris.py compile ../docs/examples/mysql_duckdb_supabase_demo.yaml

# 2. Run twice to create 2 AIOP entries
python ../osiris.py run --last-compile
python ../osiris.py run --last-compile

# 3. List AIOP runs (should return ≥ 2)
python ../osiris.py logs aiop list --pipeline mysql-duckdb-supabase-demo --json | \
    python -c "import sys,json;print(len(json.load(sys.stdin)))"

# 4. Show specific run
RUN_ID=$(python ../osiris.py logs aiop list --pipeline mysql-duckdb-supabase-demo --json | \
    python -c "import sys,json;runs=json.load(sys.stdin);print(runs[0]['run_id'] if runs else '')")

python ../osiris.py logs aiop show --pipeline mysql-duckdb-supabase-demo --run "$RUN_ID" --json | head -n 30
```

---

## Files Changed

### Core Implementation (4 files)
- `osiris/cli/run.py` - Fixed hash source (3 locations)
- `osiris/core/run_index.py` - Added validation
- `osiris/core/fs_paths.py` - Added `normalize_manifest_hash()` helper
- `osiris/cli/logs.py` - Updated path resolution logic

### Tooling (1 file)
- `scripts/migrate_index_manifest_hash.py` - One-time migration helper

### Tests (4 files)
- `tests/core/test_run_index_validation.py` - Unit tests for validation
- `tests/cli/test_manifest_hash_source.py` - Unit tests for hash source
- `tests/regression/test_index_hash_prefix.py` - Regression tests
- `tests/integration/test_aiop_list_show_e2e.py` - E2E tests

**Total**: 9 files modified/added

---

## Next Steps

1. **Review** this PR for correctness
2. **Run full test suite** to ensure no regressions
3. **Test migration script** on a copy of production index
4. **Merge** to main after approval
5. **Tag release** with changelog entry

---

## References

- **ADR-0028**: Filesystem Contract v1 specification
- **Milestone Doc**: `docs/milestones/filesystem-contract.md`
- **Sample Config**: `docs/samples/osiris.filesystem.yaml`
- **Ground Truth**: `manifest.meta.manifest_hash` (pure hex, no prefix)
