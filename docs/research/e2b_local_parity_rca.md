# E2B vs Local Execution Parity Root Cause Analysis

## Executive Summary

The MySQL → DuckDB → Supabase pipeline executes successfully locally but fails in E2B with "input_df of type NoneType" error. The root cause is that ProxyWorker excludes DataFrames from its in-memory cache when storing step outputs, preventing downstream steps from accessing the data. The DataFrame gets written to a parquet file, but the resolution logic fails because the parquet file is never created for extractors - a critical bug in the caching implementation at line 456 of proxy_worker.py.

## Reproduction Steps

### Commands Executed
```bash
# From testing_env/
# 1. Compile pipeline
python ../osiris.py compile ../docs/examples/mysql_duckdb_supabase_demo.yaml
# Session: logs/compile_1759170381659/

# 2. Local execution (SUCCESS)
python ../osiris.py run --last-compile --verbose
# Session: logs/run_1759170567795/
# Result: ✓ Pipeline completed (local) - 10 rows written

# 3. E2B execution (FAILURE)
python ../osiris.py run --last-compile --e2b --e2b-install-deps --verbose
# Session: logs/run_1759170586030/
# Result: ❌ Pipeline execution failed - DuckDB step error
```

## Evidence

### A) Compile Artifacts

**Manifest Structure** (`logs/compile_1759170381659/compiled/manifest.yaml`):
```yaml
steps:
- id: extract-movies
  driver: mysql.extractor
  cfg_path: cfg/extract-movies.json
  needs: []
- id: compute-director-stats
  driver: duckdb.processor
  cfg_path: cfg/compute-director-stats.json
  needs: [extract-movies]
- id: write-director-stats
  driver: supabase.writer
  cfg_path: cfg/write-director-stats.json
  needs: [compute-director-stats]
```

**Config Files**:
- `cfg/extract-movies.json`: Contains query, connection reference - no inputs field
- `cfg/compute-director-stats.json`: Contains query with `FROM input_df` - no inputs field
- `cfg/write-director-stats.json`: Contains table, write_mode - no inputs field

### B) Component Spec Analysis

**DuckDB Processor Spec** (`components/duckdb.processor/spec.yaml`):
- No `x-runtime.inputs` or `x-runtime.outputs` declared
- Driver: `osiris.drivers.duckdb_processor_driver.DuckDBProcessorDriver`
- Capabilities include `inMemoryMove: true` and `customTransforms: true`

### C) Local Execution (Success)

**Local Runner Behavior** (`osiris/core/runner_v0.py:344-354`):
```python
# Prepare inputs based on step dependencies
inputs = None
if "needs" in step and step["needs"]:
    # Collect inputs from upstream steps
    inputs = {}
    for upstream_id in step["needs"]:
        if upstream_id in self.results:
            upstream_result = self.results[upstream_id]
            if "df" in upstream_result:
                inputs["df"] = upstream_result["df"]
```
- Implicitly maps upstream DataFrame outputs to inputs based on `needs`
- Maintains `self.results` dictionary with step outputs including DataFrames

### D) E2B Execution (Failure)

**E2B Proxy Preparation** (`osiris/remote/e2b_transparent_proxy.py:891-905`):
```python
if needs:
    if "writer" in driver or "transform" in driver or "processor" in driver:
        for need in needs:
            for prev_step in manifest_data.get("steps", []):
                if prev_step["id"] == need:
                    prev_driver = prev_step.get("driver", "")
                    if "extractor" in prev_driver or "transform" in prev_driver:
                        inputs = {"df": {"from_step": need, "key": "df"}}
```
- Correctly generates input mapping for DuckDB step
- Command sent: `{"cmd": "exec_step", "step_id": "compute-director-stats", "inputs": {"df": {"from_step": "extract-movies", "key": "df"}}}`

### E) ProxyWorker Dataflow Bug

**Critical Bug Location** (`osiris/remote/proxy_worker.py:456`):
```python
# Line 456 - THE BUG:
cached_output = {k: v for k, v in result.items() if k != "df"}
```

**Complete Flow**:
1. MySQL extractor returns: `{"df": DataFrame}` (line 77 of mysql_extractor_driver.py)
2. ProxyWorker caches: `{}` (empty dict after excluding "df")
3. Parquet spill code (lines 467-476) only runs if "df" in result, creates df_path
4. But df_path is added to cached_output which already excluded the DataFrame
5. When DuckDB step resolves inputs, it finds empty cache for extract-movies
6. No df_path exists to fall back to because cached_output was already created empty

**Input Resolution Logic** (`osiris/remote/proxy_worker.py:1152-1171`):
```python
if from_key == "df" and isinstance(step_output, dict):
    if "df" in step_output:  # Never true due to line 456
        resolved[input_key] = df
    elif step_output.get("df_path"):  # Also never true for extractors
        df = pd.read_parquet(df_path)
```

### F) Uploader Parity

All required files are correctly uploaded to E2B:
- Manifest and cfg files match exactly (verified by SHA256)
- Component specs and drivers are uploaded
- No stripping or modification of configs during upload

## Root Cause Decision

**G4: Step output not cached/spilled for extract-movies**

**Proof**:
1. Line 456 excludes DataFrames from cached_output BEFORE parquet spilling logic
2. Lines 467-476 add df_path to cached_output, but cached_output is already created without "df"
3. The final cached_output for extractors is effectively empty `{}`
4. No artifacts/extract-movies/output.parquet file exists (verified in filesystem)
5. Input resolution fails because there's neither in-memory DataFrame nor parquet file

## Minimal Fix Options

### Option 1: Include DataFrame in cached_output (RECOMMENDED)
- **Files**: osiris/remote/proxy_worker.py
- **Change**: Remove line 456, replace with `cached_output = result.copy() if result else {}`
- **Description**: Keep DataFrames in memory cache for downstream steps
- **Risk**: Higher memory usage for large DataFrames
- **Validation**: Run E2B test, verify "inputs_resolved" event shows "from_memory: true"

### Option 2: Always spill DataFrames to parquet
- **Files**: osiris/remote/proxy_worker.py
- **Change**: Move parquet spilling logic before cached_output creation, ensure df_path is set
- **Description**: Always write DataFrames to disk, never keep in memory
- **Risk**: Performance impact from disk I/O, but consistent memory usage
- **Validation**: Run E2B test, verify output.parquet exists in extract-movies artifacts

### Option 3: Hybrid approach with smart spilling
- **Files**: osiris/remote/proxy_worker.py
- **Change**: Keep DataFrames in memory up to size threshold, spill large ones
- **Description**: Balance memory and performance based on DataFrame size
- **Risk**: More complex logic, requires testing various DataFrame sizes
- **Validation**: Test with small and large datasets, verify both paths work

## Proposed Next Action

Implement **Option 1** (include DataFrame in cached_output) as it's the simplest fix that maintains parity with local execution. The local runner keeps DataFrames in memory via self.results, so E2B should do the same for consistency. Memory concerns can be addressed later with Option 3 if needed.
