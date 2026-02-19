# DuckDB-Based Data Exchange

## Status
Draft - Design Phase

## Context

Currently, Osiris passes data between pipeline steps using in-memory pandas DataFrames. This approach has limitations:

1. **Memory pressure**: Large datasets consume significant RAM
2. **E2B spilling**: ProxyWorker has to spill DataFrames to Parquet when memory is tight
3. **Serialization overhead**: DataFrames are pickled/unpickled or converted to Parquet
4. **No query pushdown**: Processors operate on full DataFrames in memory

## Current Architecture

### Data Flow (In-Memory)

```
Extractor → DataFrame → Processor → DataFrame → Writer
                ↓                      ↓
           (in memory)            (in memory)
```

### Key Components

1. **Drivers**: Return `{"df": pd.DataFrame}` from extractors
2. **LocalAdapter**: Stores DataFrames in `step_outputs` dict by step_id
3. **ProxyWorker**: Caches DataFrames, spills to Parquet if `E2B_FORCE_SPILL=1`
4. **Input Resolution**: Resolves `{"from_step": "foo", "key": "df"}` to actual DataFrame

### Input Key Compatibility

Drivers must accept both input formats for E2B/LOCAL parity:
- **LOCAL**: `df_<step_id>` (e.g., `df_extract_actors`)
- **E2B**: `df` (plain)

Example from `filesystem_csv_writer_driver.py:36`:
```python
for key, value in inputs.items():
    if (key.startswith("df_") or key == "df") and isinstance(value, pd.DataFrame):
        df = value
        break
```

## Proposed Architecture: DuckDB File Exchange

### Core Concept

Replace in-memory DataFrames with DuckDB database files for inter-step communication.

### Data Flow (DuckDB-Based)

```
Extractor → DuckDB file → Processor → DuckDB file → Writer
              ↓                          ↓
         (data.duckdb)              (transformed.duckdb)
```

### Benefits

1. **Memory efficiency**: Data stays on disk, loaded on-demand
2. **Query pushdown**: Processors can run SQL directly on DuckDB
3. **Unified format**: No more spilling logic - always file-based
4. **Zero-copy sharing**: Multiple steps can read same DuckDB file
5. **Schema preservation**: Native type preservation (timestamps, etc.)

### Design Options

#### Option A: DuckDB as Primary Format

**Pros:**
- Clean, unified approach
- Query pushdown capabilities
- Better memory management

**Cons:**
- Requires DuckDB dependency in all components
- Driver API changes needed

#### Option B: Hybrid Approach (DataFrame + DuckDB)

**Pros:**
- Backward compatible
- Gradual migration
- Drivers unchanged

**Cons:**
- Two code paths to maintain
- Complexity in runtime

## Recommended Approach: Option A (Pure DuckDB)

### Phase 1: Foundation (Research & Prototype)

1. **DuckDB Integration**
   - Add `duckdb` to core dependencies
   - Create `DuckDBContext` helper class
   - Define file naming convention: `<session_dir>/data/<step_id>.duckdb`

2. **Driver Contract Changes**
   - Extractors return: `{"duckdb_path": Path, "table": "main"}`
   - Writers accept: `inputs = {"duckdb_path": Path, "table": "main"}`
   - Processors: Read from DuckDB, write to new DuckDB file

3. **Runtime Adapter Changes**
   - LocalAdapter: Track DuckDB paths instead of DataFrames
   - ProxyWorker: Pass file paths, no spilling needed
   - Input resolution: Map step outputs to file paths

### Phase 2: Driver Migration

#### Extractor Pattern

```python
class MySQLExtractorDriver:
    def run(self, *, step_id: str, config: dict, inputs: dict, ctx) -> dict:
        # Execute query
        df = pd.read_sql_query(query, engine)

        # Write to DuckDB
        duckdb_path = ctx.get_data_path(step_id)  # e.g., data/extract_actors.duckdb
        con = duckdb.connect(str(duckdb_path))
        con.execute("CREATE TABLE main AS SELECT * FROM df")
        con.close()

        ctx.log_metric("rows_read", len(df))

        return {
            "duckdb_path": duckdb_path,
            "table": "main",
            "rows": len(df)
        }
```

#### Processor Pattern

```python
class DuckDBProcessorDriver:
    def run(self, *, step_id: str, config: dict, inputs: dict, ctx) -> dict:
        # Get input DuckDB path
        input_path = inputs.get("duckdb_path")
        input_table = inputs.get("table", "main")

        # Process with SQL
        output_path = ctx.get_data_path(step_id)
        con = duckdb.connect(str(output_path))

        # Attach input database
        con.execute(f"ATTACH '{input_path}' AS input_db")

        # Run transformation
        sql = config.get("query")
        con.execute(f"CREATE TABLE main AS {sql}")

        rows = con.execute("SELECT COUNT(*) FROM main").fetchone()[0]
        con.close()

        ctx.log_metric("rows_processed", rows)

        return {
            "duckdb_path": output_path,
            "table": "main",
            "rows": rows
        }
```

#### Writer Pattern

```python
class FilesystemCsvWriterDriver:
    def run(self, *, step_id: str, config: dict, inputs: dict, ctx) -> dict:
        # Get input DuckDB path
        duckdb_path = inputs.get("duckdb_path")
        table = inputs.get("table", "main")

        # Read from DuckDB
        con = duckdb.connect(str(duckdb_path), read_only=True)
        df = con.execute(f"SELECT * FROM {table}").df()
        con.close()

        # Sort and write CSV
        df_sorted = df[sorted(df.columns)]
        output_path = Path(config["path"])
        df_sorted.to_csv(output_path, index=False)

        ctx.log_metric("rows_written", len(df))

        return {}
```

### Phase 3: Runtime Changes

#### Context API Extension

```python
class ExecutionContext:
    def get_data_path(self, step_id: str) -> Path:
        """Get DuckDB file path for step data.

        Returns:
            Path to <session_dir>/data/<step_id>.duckdb
        """
        data_dir = self.base_path / ".osiris_sessions" / self.session_id / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / f"{step_id}.duckdb"
```

#### LocalAdapter Changes

```python
class LocalAdapter:
    def _execute_step(self, step, context):
        # Resolve inputs (DuckDB paths instead of DataFrames)
        resolved_inputs = {}
        for input_key, spec in step.get("inputs", {}).items():
            if "from_step" in spec:
                from_step = spec["from_step"]
                output = self.step_outputs[from_step]
                resolved_inputs["duckdb_path"] = output["duckdb_path"]
                resolved_inputs["table"] = output.get("table", "main")

        # Execute driver
        result = driver.run(
            step_id=step_id,
            config=config,
            inputs=resolved_inputs,
            ctx=context
        )

        # Store output for next step
        self.step_outputs[step_id] = result
```

#### ProxyWorker Changes

```python
class ProxyWorker:
    def handle_exec_step(self, cmd):
        # Upload DuckDB file if needed (for dependencies)
        # Execute step - driver will read/write DuckDB files
        result = driver.run(...)

        # No spilling needed - data already on disk
        # Just store metadata
        self.step_outputs[step_id] = {
            "duckdb_path": result["duckdb_path"],
            "table": result.get("table", "main"),
            "rows": result.get("rows", 0)
        }
```

### Phase 4: Migration Strategy

1. **Add DuckDB support alongside DataFrame**
   - Drivers check if `inputs["duckdb_path"]` exists, else use `inputs["df"]`
   - Return both formats temporarily

2. **Update runtime to prefer DuckDB**
   - LocalAdapter/ProxyWorker pass DuckDB paths when available
   - Fall back to DataFrame for legacy drivers

3. **Deprecate DataFrame path**
   - Remove DataFrame handling after all drivers migrated
   - Keep only DuckDB path

## File Layout

```
testing_env/
├── .osiris_sessions/
│   └── session_20250109_123456/
│       ├── data/                    # NEW: DuckDB files
│       │   ├── extract_actors.duckdb
│       │   ├── transform_actors.duckdb
│       │   └── extract_movies.duckdb
│       ├── artifacts/
│       │   ├── extract_actors/
│       │   │   └── cleaned_config.json
│       │   └── transform_actors/
│       │       └── cleaned_config.json
│       ├── logs/
│       │   ├── events.jsonl
│       │   └── metrics.jsonl
│       └── manifest.yaml
```

## Compatibility Considerations

### E2B Cloud
- DuckDB files in `data/` directory uploaded/downloaded same as artifacts
- No serialization needed - native file transfer

### Local Execution
- No memory pressure from large datasets
- Artifacts directory structure unchanged

### Testing
- Test both LOCAL and E2B with same DuckDB-based approach
- Verify query pushdown works in processors

## Questions & Decisions

### Q1: Table naming convention?
**Decision**: Use `"main"` as default table name in each DuckDB file. Simple and conventional.

### Q2: What about multiple outputs from one step?
**Decision**: Support multiple tables in same DuckDB file:
```python
return {
    "duckdb_path": path,
    "tables": {
        "actors": {"rows": 100},
        "movies": {"rows": 50}
    }
}
```

### Q3: Backward compatibility with existing pipelines?
**Decision**: Phase migration - support both formats during transition, then deprecate DataFrames.

### Q4: Performance impact?
**Decision**: Benchmark small vs. large datasets. Expected: better for >10MB datasets, negligible overhead for small ones.

## Next Steps

1. Create prototype with single extractor → processor → writer pipeline
2. Benchmark memory usage and performance vs. current approach
3. Update driver contract documentation
4. Create migration guide for component developers
5. Implement runtime changes in LocalAdapter and ProxyWorker
6. Test E2B compatibility with file-based exchange

## References

- Current driver patterns: `osiris/drivers/*_driver.py`
- ProxyWorker spilling: `osiris/remote/proxy_worker.py:534-572`
- Input resolution: `proxy_worker.py:_resolve_inputs()`
- LocalAdapter: `osiris/runtime/local_adapter.py`
