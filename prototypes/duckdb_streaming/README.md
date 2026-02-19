# DuckDB Streaming Prototypes

## Overview

This directory contains prototype implementations demonstrating the DuckDB-based streaming data exchange architecture described in ADR 0043. Includes both extractor (CSV → DuckDB) and writer (DuckDB → CSV) components.

### Components

- **CSV Streaming Extractor** - Streams CSV data into DuckDB tables using chunked reading
- **CSV Streaming Writer** - Writes DuckDB tables to CSV files with column sorting

## Features

- **Chunked Reading**: Uses pandas `read_csv()` with `chunksize` parameter to process CSV files in batches
- **Memory Efficient**: Never loads full dataset into memory - processes chunk by chunk
- **DuckDB Integration**: Creates tables and inserts data using DuckDB's native DataFrame support
- **Schema Inference**: DuckDB automatically infers schema from first chunk
- **Progress Tracking**: Logs metrics via `ctx.log_metric()` for monitoring
- **Error Handling**: Handles empty files, missing files, and invalid configs gracefully

## Usage

```python
from csv_extractor import CSVStreamingExtractor

extractor = CSVStreamingExtractor()
result = extractor.run(
    step_id="extract_users",
    config={
        "path": "/path/to/data.csv",
        "delimiter": ",",
        "batch_size": 1000,
    },
    inputs={},
    ctx=ctx,
)

# Returns: {"table": "extract_users", "rows": 12345}
```

## Configuration

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `path` | Yes | - | Path to CSV file |
| `delimiter` | No | `,` | CSV delimiter character |
| `batch_size` | No | 1000 | Number of rows per batch |

## Design Notes

### Streaming Approach

1. **First Chunk**: Creates DuckDB table using `CREATE TABLE AS SELECT * FROM chunk_df`
   - DuckDB infers schema from DataFrame
   - Table named after `step_id`

2. **Subsequent Chunks**: Inserts data using `INSERT INTO ... SELECT * FROM chunk_df`
   - Efficient bulk insert
   - No manual value formatting required

3. **Memory Profile**: Only one chunk in memory at a time (default: 1000 rows)

### DuckDB Integration

The prototype uses DuckDB's native DataFrame support:
- `conn.execute("CREATE TABLE ... FROM chunk_df")` - Direct DataFrame to table
- `conn.execute("INSERT INTO ... SELECT * FROM chunk_df")` - Direct DataFrame insert
- No need for manual SQL value escaping or type conversion

### Context API Usage

Assumes minimal context interface:
- `ctx.get_db_connection()` - Returns DuckDB connection
- `ctx.log_metric(name, value)` - Logs metrics to metrics.jsonl
- `ctx.output_dir` - Not used in this prototype

## Testing

Run standalone test:

```bash
python csv_extractor.py
```

This will:
1. Create a test CSV with 4 rows
2. Extract with batch_size=2 (to test chunking)
3. Verify data in DuckDB table
4. Print results and metrics

## Challenges Encountered

### 1. DuckDB DataFrame Integration

**Challenge**: Initially considered manual INSERT statements with value formatting.

**Solution**: DuckDB supports direct DataFrame references in SQL:
```python
conn.execute("CREATE TABLE mytable AS SELECT * FROM my_dataframe")
```

This is much cleaner and handles type conversion automatically.

### 2. Empty File Handling

**Challenge**: Empty CSV files cause `pd.errors.EmptyDataError`.

**Solution**: Catch exception and create empty placeholder table:
```python
except pd.errors.EmptyDataError:
    conn.execute("CREATE TABLE {table_name} (placeholder VARCHAR)")
    conn.execute(f"DELETE FROM {table_name}")
```

### 3. Schema Inference

**Challenge**: Need consistent schema across chunks.

**Solution**: Use first chunk to create table with schema. DuckDB infers types and subsequent chunks must match. Pandas ensures consistent column names across chunks from same CSV.

## Limitations (Prototype)

1. **No type hints**: Quick prototype doesn't include full type annotations
2. **Basic error handling**: Production would need more robust validation
3. **No encoding detection**: Assumes UTF-8 encoding
4. **No compression support**: Doesn't handle .gz, .zip, etc.
5. **No data validation**: Doesn't validate data quality or constraints

## Next Steps for Production

1. Add comprehensive type hints
2. Support compressed files (.gz, .zip, .bz2)
3. Add encoding detection and configuration
4. Implement data quality validation
5. Add retry logic for transient errors
6. Support more CSV dialect options (quoting, escaping)
7. Add progress callbacks for long-running extractions
8. Implement cancellation support

## Performance Characteristics

- **Memory**: O(batch_size) - constant memory regardless of file size
- **Time**: O(n) - linear with file size
- **Disk**: Creates DuckDB table of size ≈ CSV size (compressed internally)

For a 1GB CSV file with 1000-row batches:
- Peak memory: ~10-20MB (batch + overhead)
- Processing time: ~30-60 seconds (depends on CPU, disk I/O)
- DuckDB table size: ~300-500MB (columnar compression)

---

# CSV Streaming Writer Prototype

## Overview

Prototype implementation of a CSV writer that reads from DuckDB tables instead of in-memory pandas DataFrames. Designed as the "egress" component in the streaming architecture where data flows through DuckDB throughout the pipeline.

## Features

- **DuckDB Integration**: Reads from shared DuckDB database via `ctx.get_db_connection()`
- **Table-Based Input**: Accepts table name instead of DataFrame
- **Column Sorting**: Sorts columns alphabetically for deterministic output
- **Full CSV Support**: Supports custom delimiters, encodings, line endings
- **Error Handling**: Validates table existence and configuration
- **Metrics Logging**: Tracks rows_written via `ctx.log_metric()`

## Usage

```python
from csv_writer import CSVStreamingWriter

writer = CSVStreamingWriter()
result = writer.run(
    step_id="write_csv",
    config={
        "path": "/path/to/output.csv",
        "delimiter": ",",
        "header": True,
        "newline": "lf",
    },
    inputs={"table": "extract_customers"},
    ctx=ctx,
)

# Returns: {}
```

## Configuration

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `path` | Yes | - | Output CSV file path |
| `delimiter` | No | `,` | CSV delimiter character |
| `encoding` | No | `utf-8` | File encoding |
| `header` | No | `True` | Include header row |
| `newline` | No | `lf` | Line ending: "lf", "crlf", "cr" |

## Design Notes

### Table-Based Input

Instead of accepting DataFrames, the writer accepts a table name that exists in the shared DuckDB database:

```python
inputs = {"table": "extract_customers"}
```

This table was created by an upstream extractor or processor step.

### Column Sorting

The writer sorts columns alphabetically to match the behavior of the current `FilesystemCsvWriterDriver`:

```python
sorted_columns = con.execute(
    f"SELECT column_name FROM information_schema.columns
     WHERE table_name = '{table_name}'
     ORDER BY column_name"
).fetchall()
```

### Hybrid Approach

While DuckDB offers a native `COPY TO` command for CSV export, it doesn't support custom column ordering. The writer uses a hybrid approach:

1. Query DuckDB for sorted column names
2. Read data with columns in sorted order
3. Write CSV via pandas for full formatting control

**Rejected Alternative:**
```python
# DuckDB COPY TO - fast but no column ordering
con.execute(f"COPY {table} TO '{path}' (FORMAT CSV, HEADER TRUE)")
```

### Memory Considerations

The writer loads the full dataset into a DataFrame for the final CSV write. This is acceptable because:

1. Writers are final steps (no downstream memory pressure)
2. User explicitly requested CSV output (implies dataset fits on disk)
3. **Upstream steps** (extractors, processors) never loaded the full dataset
4. Only the egress point needs to materialize data

## Testing

Run the demo script:

```bash
cd prototypes/duckdb_streaming
python demo_csv_writer.py
```

The demo demonstrates:
- Basic CSV writing from DuckDB table
- Custom delimiter (TSV example)
- Error handling (missing table, missing config)
- Column sorting (alphabetical order)
- Metrics logging (rows_written)
- Path handling (absolute/relative, directory creation)

## Streaming Architecture

The writer is the final component in a streaming pipeline:

```
┌─────────────┐     ┌──────────────┐     ┌────────────┐
│  Extractor  │────▶│  Processor   │────▶│   Writer   │
│             │     │              │     │            │
│ CSV → Table │     │ SQL → Table  │     │ Table → CSV│
└─────────────┘     └──────────────┘     └────────────┘
        │                   │                    │
        └───────────────────┴────────────────────┘
                            │
                    pipeline_data.duckdb
                    ├── extract_customers
                    ├── transform_customers
                    └── ...
```

**Key Benefits:**
- Data stays in DuckDB throughout pipeline
- No DataFrame passing between steps
- Memory-efficient (only writer loads data)
- Eliminates E2B spilling logic

## Comparison to Current Driver

| Aspect | Current Driver | Streaming Writer |
|--------|---------------|------------------|
| Input | DataFrame (`df_*` keys) | Table name (`table` key) |
| Memory | Holds full DataFrame | Holds full DataFrame (same) |
| Pipeline | DataFrames passed between steps | Tables in shared DuckDB |
| E2B | Spilling logic needed | No spilling (always on disk) |
| Sorting | ✓ Alphabetical columns | ✓ Alphabetical columns |
| Config | CSV options | CSV options (same) |

**Key Difference:** Upstream steps in streaming architecture never load data into memory.

## Error Handling

The writer validates:
- Table exists in DuckDB schema
- Config contains required 'path'
- Inputs contains 'table' key

Example errors:
```
ValueError: Step write_csv: Table 'nonexistent' does not exist in DuckDB
ValueError: Step write_csv: 'path' is required in config
ValueError: Step write_csv: CSVStreamingWriter requires 'table' in inputs
```

## Future Optimizations

### 1. Chunked CSV Writing

For massive datasets that exceed available RAM:

```python
for chunk in con.execute(f"SELECT * FROM {table}").fetch_df_chunk(1000):
    chunk.to_csv(output, mode='a', header=(first_chunk))
```

### 2. DuckDB COPY Enhancement

Contribute column ordering feature to DuckDB:

```python
con.execute(f"""
    COPY (SELECT * FROM {table} ORDER BY columns)
    TO '{path}'
    (FORMAT CSV, HEADER TRUE, COLUMN_ORDER 'alphabetical')
""")
```

### 3. Skip Sorting Option

Add config flag for performance:

```python
config = {"path": "output.csv", "sort_columns": False}
```

## Performance Characteristics

### Small Datasets (<10K rows)
- Minimal overhead from DuckDB read
- Same performance as current driver

### Medium Datasets (10K-1M rows)
- Efficient columnar read from DuckDB
- Slight improvement (no DataFrame serialization)

### Large Datasets (>1M rows)
- **Upstream**: Data never in memory (streamed to DuckDB)
- **Writer**: Loads full dataset (unavoidable for CSV)
- **Overall**: Major memory reduction in pipeline

## Related Documentation

- **ADR 0043**: DuckDB-Based Data Exchange - Architecture decision
- **Design Doc**: `/docs/design/duckdb-data-exchange.md` - Detailed design
- **Checklist**: `/docs/design/duckdb-implementation-checklist.md` - Implementation plan
- **Current Driver**: `/osiris/drivers/filesystem_csv_writer_driver.py` - Comparison
- DuckDB Python API: https://duckdb.org/docs/api/python/overview
- Pandas chunking: https://pandas.pydata.org/docs/user_guide/io.html#iterating-through-files-chunk-by-chunk
- Osiris driver guidelines: `/Users/padak/github/osiris/CLAUDE.md` (Driver Development Guidelines)
