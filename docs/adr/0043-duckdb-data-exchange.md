# ADR 0043: DuckDB-Based Data Exchange Between Pipeline Steps

## Status
Proposed

## Context

Osiris currently passes data between pipeline steps using in-memory pandas DataFrames. While simple and functional, this approach has several limitations:

### Current Limitations

1. **Memory pressure**: Large datasets (>1GB) consume significant RAM, especially in E2B sandboxes
2. **Spilling complexity**: ProxyWorker must detect memory pressure and spill DataFrames to Parquet
3. **Serialization overhead**: DataFrames are pickled or converted to Parquet for inter-process communication
4. **No query pushdown**: Processors must load entire DataFrames into memory to operate on them
5. **Type preservation issues**: Parquet spilling can lose pandas-specific type information

### E2B Spilling Logic

The current E2B ProxyWorker includes complex spilling logic (proxy_worker.py:534-572):
- Forces spilling with `E2B_FORCE_SPILL=1` environment variable
- Writes DataFrames to Parquet when memory is tight
- Reloads DataFrames from Parquet for downstream steps
- Tracks both in-memory and spilled state

This is a workaround for memory limitations, not a fundamental design choice.

### Driver Contract Complexity

Drivers must handle two input key formats for E2B/LOCAL parity:
- LOCAL: `df_<step_id>` (e.g., `df_extract_actors`)
- E2B: `df` (plain key)

This dual-format requirement exists solely to support in-memory DataFrame passing.

## Decision

We will replace in-memory DataFrame passing with **DuckDB file-based streaming** between pipeline steps.

### Key Changes (Updated Based on Prototype Learnings)

1. **Streaming Writes**: Drivers stream data directly to DuckDB in batches
   - No pandas intermediate step (memory-efficient)
   - Use DuckDB native batch insert: `con.executemany("INSERT INTO ...", batches)`
   - Extractors fetch data in chunks (e.g., MySQL cursor, PostHog pagination)

2. **Shared Database File**: All steps write to same `.duckdb` file
   - Single file per session: `<session_dir>/pipeline_data.duckdb`
   - Each step creates its own table: `<step_id>`
   - Example: `extract_actors`, `transform_actors`, `extract_movies` tables

3. **Driver Contract**: Drivers return/accept table names in shared database
   - Extractors: Return `{"table": "<step_id>", "rows": int}`
   - Processors: Accept `{"table": "<input_step_id>"}`, write to new table
   - Writers: Accept `{"table": "<step_id>"}`, read from shared database

4. **Runtime Adapters**: Track table names instead of DataFrames
   - LocalAdapter: Store `{"table": step_id, "rows": count}` in step_outputs
   - ProxyWorker: Remove spilling logic entirely - data always in DuckDB
   - Context provides database connection: `ctx.get_db_connection()`

5. **Session Layout**: Single shared DuckDB file
   ```
   .osiris_sessions/<session_id>/
   ├── pipeline_data.duckdb      # NEW: Shared database (all tables)
   │   ├── extract_actors        # Table (step output)
   │   ├── transform_actors      # Table (step output)
   │   └── extract_movies        # Table (step output)
   ├── artifacts/                # Unchanged
   ├── logs/                     # Unchanged
   └── manifest.yaml
   ```

6. **Required Dependency**: DuckDB is core dependency
   - No fallback to DataFrames
   - Simpler code, unified behavior across all environments

7. **Uniform Performance**: Same code path for all dataset sizes
   - DuckDB optimizes internally (small vs. large datasets)
   - No special handling or heuristics needed

## Consequences

### Positive

1. **Memory efficiency**: Data stays on disk, loaded only when needed
2. **Query pushdown**: Processors can run SQL directly on DuckDB without loading full DataFrame
3. **Simpler E2B**: No spilling logic needed - always file-based
4. **Zero-copy sharing**: Multiple steps can read same DuckDB file without duplication
5. **Schema preservation**: DuckDB natively preserves types (timestamps, decimals, etc.)
6. **Unified approach**: Same behavior in LOCAL and E2B environments

### Negative

1. **New dependency**: DuckDB added to core dependencies (~50MB)
2. **Driver changes**: All drivers must be updated (11 files)
3. **I/O overhead**: Small datasets may see negligible slowdown from disk I/O
4. **Breaking change**: Existing drivers incompatible without update

### Neutral

1. **File storage**: DuckDB files consume similar disk space as Parquet
2. **Testing scope**: Similar test coverage needed as current approach

## Alternatives Considered

### Alternative 1: Optimize In-Memory Approach
**Rejected**: Doesn't solve fundamental memory pressure problem, only delays it.

### Alternative 2: Arrow IPC Format
**Rejected**: Doesn't enable query pushdown; similar benefits as Parquet but less familiar.

### Alternative 3: SQLite
**Rejected**: DuckDB is better optimized for analytical workloads (OLAP vs. OLTP).

### Alternative 4: Parquet + PyArrow
**Rejected**: Requires loading full files into memory; no query pushdown.

## Implementation Notes

### Driver Pattern: Extractor (Streaming)

```python
class MySQLExtractorDriver:
    def run(self, *, step_id: str, config: dict, inputs: dict, ctx) -> dict:
        query = config["query"]

        # Get shared DuckDB connection
        con = ctx.get_db_connection()

        # Create table with schema inference from first batch
        # Stream data in batches using MySQL cursor
        with engine.connect() as conn:
            result = conn.execution_options(stream_results=True).execute(sa.text(query))

            # Create table from first batch
            first_batch = result.fetchmany(1000)
            if first_batch:
                con.execute(f"CREATE TABLE {step_id} AS SELECT * FROM first_batch")

            # Stream remaining batches
            rows_written = len(first_batch)
            while True:
                batch = result.fetchmany(1000)
                if not batch:
                    break
                con.executemany(f"INSERT INTO {step_id} VALUES (...)", batch)
                rows_written += len(batch)

        ctx.log_metric("rows_read", rows_written)

        return {
            "table": step_id,
            "rows": len(df)
        }
```

### Driver Pattern: Processor

```python
class DuckDBProcessorDriver:
    def run(self, *, step_id: str, config: dict, inputs: dict, ctx) -> dict:
        input_path = inputs["duckdb_path"]
        output_path = ctx.get_data_path(step_id)

        con = duckdb.connect(str(output_path))
        con.execute(f"ATTACH '{input_path}' AS input_db")
        con.execute(f"CREATE TABLE main AS {config['query']}")
        rows = con.execute("SELECT COUNT(*) FROM main").fetchone()[0]
        con.close()

        return {"duckdb_path": output_path, "table": "main", "rows": rows}
```

### Driver Pattern: Writer

```python
class FilesystemCsvWriterDriver:
    def run(self, *, step_id: str, config: dict, inputs: dict, ctx) -> dict:
        duckdb_path = inputs["duckdb_path"]
        table = inputs.get("table", "main")

        con = duckdb.connect(str(duckdb_path), read_only=True)
        df = con.execute(f"SELECT * FROM {table}").df()
        con.close()

        # Write CSV (unchanged)
        df_sorted = df[sorted(df.columns)]
        df_sorted.to_csv(config["path"], index=False)
        return {}
```

## Related Decisions

- ADR 0042: Driver Context API Contract - Defines `ctx` interface
- ADR 0041: E2B PyPI-Based Execution - E2B runtime environment

## References

- DuckDB documentation: https://duckdb.org/docs/
- Current spilling logic: `osiris/remote/proxy_worker.py:534-572`
- Driver contract: `docs/developer-guide/ai/driver-development.md`
- Design doc: `docs/design/duckdb-data-exchange.md`
- Implementation checklist: `docs/design/duckdb-implementation-checklist.md`
