# E2B Runtime - DataFrame Lifecycle

## Overview

The E2B runtime provides transparent remote execution of Osiris pipelines in isolated cloud sandboxes. This document explains the DataFrame lifecycle, from driver output through caching, optional spilling, and resolution for downstream steps.

## Architecture

```
Local Orchestrator (E2BTransparentProxy)
    ↓ RPC over stdout/stderr
E2B Sandbox (ProxyWorker)
    ↓ Driver execution
DataFrame Output → Cache/Spill → Input Resolution
```

## DataFrame Lifecycle

### 1. Driver Produces DataFrame

When a driver (extractor, processor) returns a DataFrame:

```python
# Driver returns
result = {"df": DataFrame}
```

### 2. ProxyWorker Caches Result

The ProxyWorker stores the complete result including DataFrames:

```python
# Keep full result in cache
cached_output = result.copy() if result else {}
self.step_outputs[step_id] = cached_output
```

### 3. Optional Spilling to Disk

DataFrames can be spilled to disk based on:
- **Force spill**: `E2B_FORCE_SPILL=1` environment variable
- **Size threshold**: DataFrames exceeding `E2B_SPILL_THRESHOLD` rows (default: 100,000)

When spilling occurs:
1. DataFrame written to `artifacts/<step_id>/output.parquet`
2. Schema saved to `artifacts/<step_id>/schema.json` with row count, columns, dtypes
3. DataFrame removed from memory cache
4. `spilled=True` flag set in cached output

### 4. Input Resolution for Downstream Steps

When a step needs input from upstream:

```python
# Input specification from manifest
inputs = {"df": {"from_step": "extract-movies", "key": "df"}}
```

Resolution order:
1. **Prefer in-memory**: Check if DataFrame exists in `self.step_outputs[from_step]["df"]`
2. **Fallback to spill**: Load from parquet file if spilled
3. **Error if neither**: Clear error message indicating missing input

### 5. Events and Telemetry

Key events emitted:
- `rows_out`: When DataFrame produced (with row count)
- `inputs_resolved`: When input resolved (with source: memory/spill)
- `artifact_created`: When spilling parquet/schema files

## Parity with Local Execution

The E2B runtime maintains full parity with local execution:

| Aspect | Local | E2B |
|--------|-------|-----|
| DataFrame passing | In-memory via `self.results` | In-memory via `self.step_outputs` |
| Input mapping | Implicit from `needs` | Explicit via E2B proxy, then resolved |
| Spill support | No | Yes (optional) |
| Error handling | Python exceptions | Same + clear messages |

## Configuration

### Environment Variables

- `E2B_FORCE_SPILL`: Set to "1", "true", or "yes" to force all DataFrames to disk
- `E2B_SPILL_THRESHOLD`: Row count threshold for automatic spilling (default: 100000)

### Manifest Structure

The compiler generates manifests with `needs` dependencies:

```yaml
steps:
- id: extract-movies
  driver: mysql.extractor
  needs: []

- id: compute-stats
  driver: duckdb.processor
  needs: [extract-movies]  # Dependency
```

The E2B proxy converts `needs` to explicit `inputs` mapping for processors/writers.

## Run Card Diagnostics

The `run_card.json` provides DataFrame tracking per step:

```json
{
  "steps": [{
    "step_id": "extract-movies",
    "has_df_in_memory": true,
    "spill_used": false,
    "spill_paths": null,
    "rows_out": 14
  }]
}
```

## Debugging DataFrame Flow

### Check Events

```bash
# View inputs resolution
cat logs/run_*/events.jsonl | grep inputs_resolved

# View DataFrame production
cat logs/run_*/events.jsonl | grep rows_out
```

### Check Artifacts

```bash
# Check if DataFrame was spilled
ls -la logs/run_*/artifacts/*/output.parquet

# View schema information
cat logs/run_*/artifacts/*/schema.json
```

### Common Issues

1. **"input_df of type NoneType"**: DataFrame not found in upstream step
   - Check if upstream step completed successfully
   - Verify inputs mapping in E2B commands

2. **"Input 'df' not found"**: Resolution failed
   - Check memory cache and spill paths
   - Verify upstream step produced DataFrame

3. **Memory issues**: Large DataFrames
   - Enable spilling with `E2B_FORCE_SPILL=1`
   - Reduce `E2B_SPILL_THRESHOLD`

## Implementation Details

### No DataFrame Through RPC

DataFrames are never serialized through RPC to avoid:
- Serialization overhead
- Size limitations
- Type conversion issues

Instead, only metadata is returned in RPC responses:
- `rows_processed`: Row count
- Artifact paths for spilled data

### Explicit Inputs from Manifest

The system uses explicit input specifications from the E2B proxy:
- No heuristics or guessing
- Clear data lineage
- Predictable behavior

This ensures reproducible execution across environments.
