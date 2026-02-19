# DuckDB Data Exchange - Request for Second Opinion

## Current State: In-Memory DataFrame Passing

### How It Works Now

1. **Extractor** executes SQL query → returns `{"df": pandas.DataFrame}`
2. **Runtime** stores DataFrame in memory: `step_outputs[step_id] = {"df": df}`
3. **Processor** receives DataFrame → transforms → returns new DataFrame
4. **Writer** receives DataFrame → writes to destination

```python
# Current driver pattern
class MySQLExtractorDriver:
    def run(self, *, step_id, config, inputs, ctx):
        df = pd.read_sql_query(query, engine)
        return {"df": df}  # DataFrame stays in memory

# Runtime stores it
step_outputs["extract_actors"] = {"df": df}  # 500MB in RAM

# Next step receives it
inputs = {"df": step_outputs["extract_actors"]["df"]}  # Still 500MB
```

### The Problems

#### 1. Memory Pressure (Main Issue)
- Large datasets (>1GB) consume significant RAM
- E2B sandboxes have memory limits
- Multiple steps = multiple DataFrames in memory simultaneously
- Example: 3-step pipeline with 500MB dataset = ~1.5GB RAM usage

#### 2. E2B Spilling Workaround
ProxyWorker has complex spilling logic (`proxy_worker.py:534-572`):
```python
force_spill = os.getenv("E2B_FORCE_SPILL", "").strip().lower() in {"1", "true", "yes"}
if force_spill:
    parquet_path = step_artifacts_dir / "output.parquet"
    df_value.to_parquet(parquet_path)
    cached_output["df_path"] = parquet_path
    cached_output["spilled"] = True
    result["df"] = None  # Drop from memory
else:
    cached_output["df"] = df_value  # Keep in memory
```

This is a **workaround**, not a design:
- Adds complexity (100+ lines of spilling logic)
- Requires manual memory management
- Inconsistent: sometimes in-memory, sometimes spilled
- Still needs to reload Parquet for next step

#### 3. No Query Pushdown
Processors must load entire DataFrame to operate:
```python
# Current: Must load all data into memory
df = inputs["df"]  # 1GB loaded
filtered = df[df["age"] > 18]  # Could be done in DB

# Desired: Query pushdown in DuckDB
con.execute("CREATE TABLE main AS SELECT * FROM input_db.main WHERE age > 18")
```

#### 4. Dual Input Format Requirement
Drivers handle two formats for E2B/LOCAL parity:
```python
# Every writer must check both formats
for key, value in inputs.items():
    if (key.startswith("df_") or key == "df") and isinstance(value, pd.DataFrame):
        df = value
        break
```

Why? Because LOCAL uses `df_extract_actors`, E2B uses `df`.

## Proposed Solution: DuckDB File-Based Exchange

### How It Will Work

1. **Extractor** executes query → writes to DuckDB file → returns path
2. **Runtime** stores file path: `step_outputs[step_id] = {"duckdb_path": Path(...)}`
3. **Processor** reads DuckDB file → transforms with SQL → writes new DuckDB file
4. **Writer** reads DuckDB file → loads DataFrame on-demand → writes destination

```python
# New driver pattern
class MySQLExtractorDriver:
    def run(self, *, step_id, config, inputs, ctx):
        df = pd.read_sql_query(query, engine)

        # Write to DuckDB file
        duckdb_path = ctx.get_data_path(step_id)  # data/extract_actors.duckdb
        con = duckdb.connect(str(duckdb_path))
        con.execute("CREATE TABLE main AS SELECT * FROM df")
        con.close()

        return {
            "duckdb_path": duckdb_path,
            "table": "main",
            "rows": len(df)
        }

# Runtime stores path, not DataFrame
step_outputs["extract_actors"] = {
    "duckdb_path": Path("data/extract_actors.duckdb"),
    "table": "main",
    "rows": 1000000
}  # ~0 bytes in RAM, 50MB on disk

# Next step receives path
inputs = {
    "duckdb_path": step_outputs["extract_actors"]["duckdb_path"],
    "table": "main"
}  # Still ~0 bytes in RAM
```

### Key Changes

#### 1. Driver Contract
**Before:**
```python
return {"df": pd.DataFrame}  # In memory
```

**After:**
```python
return {
    "duckdb_path": Path,  # On disk
    "table": "main",
    "rows": int
}
```

#### 2. Context API Extension
```python
class ExecutionContext:
    def get_data_path(self, step_id: str) -> Path:
        """Returns: <session_dir>/data/<step_id>.duckdb"""
        data_dir = self.base_path / ".osiris_sessions" / self.session_id / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / f"{step_id}.duckdb"
```

#### 3. Session Layout
```
.osiris_sessions/<session_id>/
├── data/              # NEW: DuckDB files (step outputs)
│   ├── extract_actors.duckdb     # 50MB
│   ├── transform_actors.duckdb   # 45MB
│   └── extract_movies.duckdb     # 100MB
├── artifacts/         # Unchanged (configs, schemas)
├── logs/              # Unchanged (events, metrics)
└── manifest.yaml
```

#### 4. Remove Spilling Logic
Delete `proxy_worker.py:534-572` - no longer needed!

### Benefits

1. **Memory Efficiency**: Data on disk, loaded on-demand
   - 3-step pipeline: ~0MB RAM vs. ~1.5GB RAM currently

2. **Query Pushdown**: SQL operations in DuckDB
   ```python
   # Filter 1B rows to 1K rows without loading all data
   con.execute("""
       CREATE TABLE main AS
       SELECT * FROM input_db.main
       WHERE age > 18 AND country = 'US'
   """)
   ```

3. **Simpler E2B**: No spilling workaround needed
   - Remove 100+ lines of complex code
   - Consistent behavior: always file-based

4. **Zero-Copy Sharing**: Multiple steps read same file
   ```python
   # Two writers can read same extractor output
   inputs_writer1 = {"duckdb_path": "data/extract.duckdb"}
   inputs_writer2 = {"duckdb_path": "data/extract.duckdb"}  # Same file
   ```

5. **Type Preservation**: DuckDB natively handles timestamps, decimals, etc.

### Migration Path

**Option A: Pure DuckDB (Recommended)**
- All drivers switch immediately
- Remove spilling logic
- Cleaner codebase

**Option B: Hybrid (Fallback)**
- Support both DataFrame and DuckDB
- Gradual migration
- More complexity

We recommend **Option A** for simplicity.

## Questions for Codex

### 1. Architecture Validation
- Is DuckDB the right choice for inter-step data exchange?
- Are there better alternatives we haven't considered?
- Any hidden gotchas with DuckDB for this use case?

### 2. Performance Concerns
- Will small datasets (<10MB) suffer from disk I/O overhead?
- Is DuckDB fast enough for frequent create/read/delete cycles?
- Should we benchmark before committing?

### 3. Implementation Strategy
- Is "Pure DuckDB" (Option A) too aggressive?
- Should we keep DataFrame support as fallback?
- Any migration risks we're missing?

### 4. Edge Cases
- What if a step needs multiple outputs (e.g., actors + movies)?
  - Current plan: Multiple tables in same DuckDB file
  - Good idea or problematic?

- What about steps that don't produce DataFrames?
  - Example: A step that just downloads a file
  - Current plan: Return `{}` (empty dict) like today

- Concurrent reads from same DuckDB file?
  - DuckDB supports multiple readers, single writer
  - Safe for our use case?

### 5. Dependency Weight
- DuckDB adds ~50MB to dependencies
- Is this acceptable for core functionality?
- Any lightweight alternatives?

### 6. Code Complexity
- Are we trading memory complexity for I/O complexity?
- Is the driver API still intuitive?
- Any simplifications we're missing?

## Implementation Checklist Summary

**Estimated effort**: 52-72 hours (~1.5-2 weeks)

**Files to modify**: ~30 files
- Core: 3 (execution_adapter.py, duckdb_helpers.py NEW, requirements.txt)
- Runtime: 2 (local_adapter.py, proxy_worker.py)
- Drivers: 6 (all extractors/processors/writers)
- Tests: 12+
- Docs: 5+

**Phases**:
1. Foundation (dependencies, helpers, context API)
2. Runtime changes (LocalAdapter, ProxyWorker)
3. Driver migration (extractors → processors → writers)
4. Testing (unit, integration, E2B)
5. Documentation
6. Cleanup (remove spilling logic)

## Request

**Please review this proposal and provide feedback on:**
1. Overall architecture soundness
2. Potential problems we haven't thought of
3. Alternative approaches worth considering
4. Implementation risks
5. Any "red flags" in the design

We want to make sure we're not missing something obvious before starting implementation.

## References

- Design doc: `docs/design/duckdb-data-exchange.md`
- Implementation checklist: `docs/design/duckdb-implementation-checklist.md`
- ADR 0043: `docs/adr/0043-duckdb-data-exchange.md`
- Current spilling: `osiris/remote/proxy_worker.py:534-572`
