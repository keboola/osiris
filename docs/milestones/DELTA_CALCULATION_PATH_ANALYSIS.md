# Delta Calculation Path Analysis & Fix

## Critical Finding

**Status**: ❌ **HARDCODED PATH DETECTED**

The delta calculation function `_find_previous_run_by_manifest()` uses a **hardcoded legacy path** that violates FilesystemContract v1.

---

## Location of Issue

**File**: `osiris/core/run_export_v2.py:2066`

**Function**: `_find_previous_run_by_manifest()`

### Current Implementation (BROKEN)

```python
def _find_previous_run_by_manifest(manifest_hash: str, current_session_id: str = None) -> dict | None:
    """Find the most recent previous run with the same manifest hash.

    Args:
        manifest_hash: Hash of the manifest to look up
        current_session_id: Current session ID to exclude from results

    Returns:
        Previous run record or None if not found
    """
    if not manifest_hash or manifest_hash == "unknown":
        return None

    # Look up in by_pipeline index
    index_path = Path("logs/aiop/index/by_pipeline") / f"{manifest_hash}.jsonl"  # ← HARDCODED!
    if not index_path.exists():
        return None

    # Read all runs for this pipeline, get the most recent completed one
    runs = []
    try:
        with open(index_path) as f:
            for line in f:
                if line.strip():
                    run_data = json.loads(line)
                    # Skip the current run
                    if current_session_id and run_data.get("session_id") == current_session_id:
                        continue
                    # Only consider completed runs
                    if run_data.get("status") in ["completed", "success"]:
                        runs.append(run_data)
    except Exception:
        return None

    if not runs:
        return None

    # Sort by started_at timestamp (most recent first), fallback to ended_at
    runs.sort(key=lambda r: r.get("started_at") or r.get("ended_at", ""), reverse=True)

    # Return the most recent run (excluding current)
    return runs[0]
```

### Problem Analysis

**Line 2066**: `index_path = Path("logs/aiop/index/by_pipeline") / f"{manifest_hash}.jsonl"`

This hardcoded path has multiple issues:

1. ❌ **Uses legacy path**: `logs/aiop/index/by_pipeline` instead of contract-compliant `aiop/index/by_pipeline`
2. ❌ **Not configurable**: Ignores `osiris.yaml` AIOP index configuration
3. ❌ **No FilesystemContract routing**: Bypasses the entire path resolution system
4. ❌ **Breaks delta analysis**: Cannot find index files written to correct location

---

## Impact Assessment

### Symptoms

When this function fails to find the index file:
- ✅ First run: Correctly returns `None` → `first_run: true` ✓
- ❌ Second+ runs: **Still returns `None`** → `first_run: true` (WRONG!)
- ❌ Delta comparison: **Never executed** (always shows "first run")
- ❌ Run cards: Show "*First run with this configuration*" every time

### Call Chain

```
run_export_v2.build_aiop()
  → run_export_v2.calculate_delta()
    → run_export_v2._find_previous_run_by_manifest()  ← BROKEN HERE
      → Looks for: "logs/aiop/index/by_pipeline/90088f4....jsonl"
      → Actual file: "aiop/index/by_pipeline/90088f4....jsonl"
      → Result: File not found → Returns None
    → Returns: {"first_run": true}  ← WRONG for run #2+
```

### Where Index Actually Gets Written

**File**: `osiris/core/aiop_export.py:483-485`

```python
by_pipeline_dir = config.get("index", {}).get("by_pipeline_dir", "logs/aiop/index/by_pipeline")
Path(by_pipeline_dir).mkdir(parents=True, exist_ok=True)
pipeline_index = Path(by_pipeline_dir) / f"{manifest_hash}.jsonl"
```

**Default from config.py:751**: `"by_pipeline_dir": "aiop/index/by_pipeline"`

**Problem**: Writer uses config (correct), reader uses hardcoded path (wrong).

---

## Proposed Fix

### Option 1: Use AIOP Config (Recommended)

**Advantages**:
- ✅ Respects user configuration
- ✅ Consistent with writer path
- ✅ Minimal code change
- ✅ Backward compatible via config

**Implementation**:

```python
def _find_previous_run_by_manifest(manifest_hash: str, current_session_id: str = None, config: dict = None) -> dict | None:
    """Find the most recent previous run with the same manifest hash.

    Args:
        manifest_hash: Hash of the manifest to look up
        current_session_id: Current session ID to exclude from results
        config: Optional AIOP config (from resolve_aiop_config)

    Returns:
        Previous run record or None if not found
    """
    if not manifest_hash or manifest_hash == "unknown":
        return None

    # Use config or load default
    if config is None:
        from osiris.core.config import resolve_aiop_config
        config, _ = resolve_aiop_config()

    # Get by_pipeline directory from config (matches where writes go)
    by_pipeline_dir = config.get("index", {}).get("by_pipeline_dir", "aiop/index/by_pipeline")
    index_path = Path(by_pipeline_dir) / f"{manifest_hash}.jsonl"

    # Try legacy location as fallback for backward compatibility
    if not index_path.exists():
        legacy_path = Path("logs/aiop/index/by_pipeline") / f"{manifest_hash}.jsonl"
        if legacy_path.exists():
            index_path = legacy_path

    if not index_path.exists():
        return None

    # Read all runs for this pipeline, get the most recent completed one
    runs = []
    try:
        with open(index_path) as f:
            for line in f:
                if line.strip():
                    run_data = json.loads(line)
                    # Skip the current run
                    if current_session_id and run_data.get("session_id") == current_session_id:
                        continue
                    # Only consider completed runs
                    if run_data.get("status") in ["completed", "success"]:
                        runs.append(run_data)
    except Exception:
        return None

    if not runs:
        return None

    # Sort by started_at timestamp (most recent first), fallback to ended_at
    runs.sort(key=lambda r: r.get("started_at") or r.get("ended_at", ""), reverse=True)

    # Return the most recent run (excluding current)
    return runs[0]
```

### Option 2: Use FilesystemContract (Future-Proof)

**Advantages**:
- ✅ Fully contract-compliant
- ✅ Type-safe
- ✅ Centralized path logic

**Disadvantages**:
- ⚠️ Requires passing contract through call chain
- ⚠️ More refactoring needed

**Implementation**:

```python
def _find_previous_run_by_manifest(
    manifest_hash: str,
    current_session_id: str = None,
    fs_contract = None
) -> dict | None:
    """Find the most recent previous run with the same manifest hash.

    Args:
        manifest_hash: Hash of the manifest to look up
        current_session_id: Current session ID to exclude from results
        fs_contract: Optional FilesystemContract instance

    Returns:
        Previous run record or None if not found
    """
    if not manifest_hash or manifest_hash == "unknown":
        return None

    # Get index path from contract
    if fs_contract is None:
        from osiris.core.fs_config import load_osiris_config
        from osiris.core.fs_paths import FilesystemContract

        fs_config, ids_config, _ = load_osiris_config()
        fs_contract = FilesystemContract(fs_config, ids_config)

    # Use contract to resolve index directory
    index_paths = fs_contract.index_paths()
    by_pipeline_dir = index_paths["base"] / "by_pipeline"
    index_path = by_pipeline_dir / f"{manifest_hash}.jsonl"

    # Try legacy location as fallback
    if not index_path.exists():
        legacy_path = Path("logs/aiop/index/by_pipeline") / f"{manifest_hash}.jsonl"
        if legacy_path.exists():
            index_path = legacy_path

    if not index_path.exists():
        return None

    # ... rest of function unchanged
```

---

## Recommended Approach

**Use Option 1** (AIOP Config) for this PR:

**Reasons**:
1. ✅ Minimal code change (5 lines modified)
2. ✅ No signature changes to `calculate_delta()`
3. ✅ Consistent with existing `aiop_export.py` writer
4. ✅ Includes backward compatibility fallback
5. ✅ Can migrate to Option 2 later if needed

---

## Exact Code Changes

### File: `osiris/core/run_export_v2.py`

**Lines to change**: 2062-2068

**Before**:
```python
def _find_previous_run_by_manifest(manifest_hash: str, current_session_id: str = None) -> dict | None:
    """Find the most recent previous run with the same manifest hash.

    Args:
        manifest_hash: Hash of the manifest to look up
        current_session_id: Current session ID to exclude from results

    Returns:
        Previous run record or None if not found
    """
    if not manifest_hash or manifest_hash == "unknown":
        return None

    # Look up in by_pipeline index
    index_path = Path("logs/aiop/index/by_pipeline") / f"{manifest_hash}.jsonl"
    if not index_path.exists():
        return None
```

**After**:
```python
def _find_previous_run_by_manifest(manifest_hash: str, current_session_id: str = None, config: dict = None) -> dict | None:
    """Find the most recent previous run with the same manifest hash.

    Args:
        manifest_hash: Hash of the manifest to look up
        current_session_id: Current session ID to exclude from results
        config: Optional AIOP config (from resolve_aiop_config)

    Returns:
        Previous run record or None if not found
    """
    if not manifest_hash or manifest_hash == "unknown":
        return None

    # Use config or load default
    if config is None:
        from osiris.core.config import resolve_aiop_config
        config, _ = resolve_aiop_config()

    # Get by_pipeline directory from config (matches where writes go)
    by_pipeline_dir = config.get("index", {}).get("by_pipeline_dir", "aiop/index/by_pipeline")
    index_path = Path(by_pipeline_dir) / f"{manifest_hash}.jsonl"

    # Try legacy location as fallback for backward compatibility
    if not index_path.exists():
        legacy_path = Path("logs/aiop/index/by_pipeline") / f"{manifest_hash}.jsonl"
        if legacy_path.exists():
            index_path = legacy_path

    if not index_path.exists():
        return None
```

**Lines changed**: ~15 lines modified
**New imports needed**: `from osiris.core.config import resolve_aiop_config` (already exists in file)

---

## Caller Updates

### File: `osiris/core/run_export_v2.py`

**Function**: `calculate_delta()` (line ~1845)

**Current call**:
```python
# Look up previous run by manifest hash in index
previous_run = _find_previous_run_by_manifest(manifest_hash, current_session_id)
```

**Updated call** (pass config through):
```python
# Look up previous run by manifest hash in index
previous_run = _find_previous_run_by_manifest(manifest_hash, current_session_id, config)
```

**Where to get config**: `calculate_delta()` is called from `build_aiop()` which has `config` parameter.

**Trace**:
```python
build_aiop(..., config=config, ...)  # Line ~2096
  → calculate_delta(current_run, manifest_hash, session_id)  # Line ~2233
    → _find_previous_run_by_manifest(manifest_hash, session_id, config)  # Pass config!
```

---

## Testing Strategy

### Unit Test

**File**: `tests/core/test_aiop_delta_analysis.py` (add new test)

```python
def test_delta_lookup_uses_configured_path(tmp_path):
    """Verify delta lookup uses config.index.by_pipeline_dir."""
    from osiris.core.run_export_v2 import _find_previous_run_by_manifest

    manifest_hash = "abc123def456"  # pragma: allowlist secret
    custom_index_dir = tmp_path / "custom_aiop_index" / "by_pipeline"
    custom_index_dir.mkdir(parents=True)

    # Write a previous run to custom location
    index_file = custom_index_dir / f"{manifest_hash}.jsonl"
    with open(index_file, "w") as f:
        f.write(json.dumps({
            "session_id": "prev_run",
            "status": "completed",
            "total_rows": 100,
            "started_at": "2025-01-01T00:00:00Z"
        }) + "\n")

    # Create config pointing to custom location
    config = {
        "index": {
            "by_pipeline_dir": str(custom_index_dir.parent)
        }
    }

    # Should find the previous run
    prev_run = _find_previous_run_by_manifest(manifest_hash, config=config)
    assert prev_run is not None
    assert prev_run["total_rows"] == 100
```

### Integration Test

**Verification steps**:

1. Clean test environment
2. Run pipeline twice with same manifest
3. Check second run's `summary.json`:
   - `metadata.delta.first_run` should be `false`
   - `metadata.delta.rows.previous` should match run #1
   - `metadata.delta.delta_source` should be `"by_pipeline_index"`

---

## Migration Notes

### For Existing Installations

**Scenario**: User has index files in legacy `logs/aiop/index/by_pipeline/`

**Fix provides**:
✅ Automatic fallback to legacy location (backward compatible)
✅ Reads work from both old and new locations
✅ New writes go to correct location per config

**User action needed**:
❌ None - fallback handles it automatically

**Optional cleanup** (after verifying new path works):
```bash
# Move legacy indexes to new location
mkdir -p aiop/index/by_pipeline
mv logs/aiop/index/by_pipeline/*.jsonl aiop/index/by_pipeline/ 2>/dev/null || true
```

---

## Summary

### Current State ❌

- **Delta lookup**: Hardcoded `logs/aiop/index/by_pipeline`
- **Index writes**: Configurable, defaults to `aiop/index/by_pipeline`
- **Result**: Lookup fails, delta always shows "first run"

### After Fix ✅

- **Delta lookup**: Uses `config.index.by_pipeline_dir`
- **Index writes**: Same (already correct)
- **Result**: Lookup succeeds, delta correctly shows comparison

### Code Impact

| File | Lines Changed | Type |
|------|--------------|------|
| `osiris/core/run_export_v2.py` | ~20 | Modify `_find_previous_run_by_manifest()` |
| `osiris/core/run_export_v2.py` | ~2 | Update `calculate_delta()` call |
| **Total** | **~22** | **Single file** |

### Testing

- ✅ Add unit test for config-based lookup
- ✅ Add integration test for run×2 delta
- ✅ Verify backward compatibility with legacy path

**Estimated effort**: 30 minutes
**Risk level**: Low (fallback provides safety net)
