# CSV Streaming Extractor - Architecture

## High-Level Flow

```
┌─────────────┐
│  CSV File   │
│  (any size) │
└──────┬──────┘
       │
       │ read_csv(chunksize=1000)
       ▼
┌─────────────────┐
│  Pandas Chunks  │  ← Only one chunk in memory at a time
│  (1000 rows)    │
└──────┬──────────┘
       │
       │ For each chunk:
       ▼
┌────────────────────────────────────────┐
│         First Chunk?                   │
│  ┌───────────────┬──────────────────┐  │
│  │     YES       │       NO         │  │
│  │               │                  │  │
│  ▼               ▼                  │  │
│  CREATE TABLE    INSERT INTO        │  │
│  FROM chunk_df   SELECT * FROM      │  │
│                  chunk_df           │  │
└────────────────┬───────────────────────┘
                 │
                 ▼
          ┌──────────────┐
          │ DuckDB Table │
          │  (columnar)  │
          └──────────────┘
```

## Detailed Component Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   CSVStreamingExtractor                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Input:                                                         │
│  ├─ step_id: str        → Used as table name                   │
│  ├─ config: dict                                               │
│  │  ├─ path: str        → CSV file path (required)             │
│  │  ├─ delimiter: str   → CSV delimiter (default: ",")         │
│  │  └─ batch_size: int  → Rows per chunk (default: 1000)       │
│  ├─ inputs: dict        → Not used (extractor has no inputs)   │
│  └─ ctx: Context        → Runtime context                      │
│                                                                 │
│  Processing:                                                    │
│  ┌────────────────────────────────────────────────────┐        │
│  │ 1. Validate config (path exists, required keys)   │        │
│  │ 2. Open CSV with chunked reader                    │        │
│  │ 3. For each chunk:                                 │        │
│  │    a. First chunk → CREATE TABLE                   │        │
│  │    b. Other chunks → INSERT INTO                   │        │
│  │    c. Track total_rows                             │        │
│  │ 4. Log metrics (rows_read)                         │        │
│  │ 5. Return result dict                              │        │
│  └────────────────────────────────────────────────────┘        │
│                                                                 │
│  Output:                                                        │
│  └─ {"table": step_id, "rows": total_rows}                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Context API Contract

```
┌──────────────────────────────────────────────────────┐
│                  Runtime Context                     │
├──────────────────────────────────────────────────────┤
│                                                      │
│  Methods Used:                                       │
│  ├─ get_db_connection() → DuckDB Connection         │
│  └─ log_metric(name, value, **kwargs) → None        │
│                                                      │
│  Methods NOT Used:                                   │
│  ├─ ctx.log() ✗ (doesn't exist!)                    │
│  └─ Use logging.getLogger(__name__) instead          │
│                                                      │
│  Properties:                                         │
│  └─ output_dir: Path (not used in this prototype)   │
│                                                      │
└──────────────────────────────────────────────────────┘
```

## Memory Profile

```
CSV File Size: 1 GB
Batch Size: 1000 rows
Row Width: ~1 KB

┌─────────────────────────────────────────────────────┐
│                Memory Usage Over Time                │
│                                                      │
│  20 MB ┤                                             │
│        │  ╭─╮    ╭─╮    ╭─╮    ╭─╮                  │
│  15 MB ┤  │ │    │ │    │ │    │ │                  │
│        │  │ │    │ │    │ │    │ │                  │
│  10 MB ┤  │ │    │ │    │ │    │ │                  │
│        │  │ │    │ │    │ │    │ │                  │
│   5 MB ┤  │ │    │ │    │ │    │ │                  │
│        │  │ │    │ │    │ │    │ │                  │
│   0 MB ┴──┴─┴────┴─┴────┴─┴────┴─┴──────────────   │
│          Chunk1  Chunk2  Chunk3  Chunk4 ...        │
│                                                      │
│  Peak Memory: ~20 MB (constant)                      │
│  - Batch DataFrame: ~1 MB (1000 × 1KB)              │
│  - DuckDB Buffer: ~10 MB                             │
│  - Python Overhead: ~5-10 MB                         │
│                                                      │
│  Traditional approach (load all): ~1000 MB           │
│  Memory savings: 98%                                 │
└─────────────────────────────────────────────────────┘
```

## Data Flow - First Chunk

```
Step 1: Read First Chunk
┌────────────────┐
│ pandas.read_csv│
│ chunksize=1000 │
└───────┬────────┘
        │
        ▼
┌──────────────────┐
│ DataFrame (1000) │
│ ┌──┬─────┬─────┐ │
│ │id│name │value│ │
│ ├──┼─────┼─────┤ │
│ │1 │Alice│100  │ │
│ │2 │Bob  │200  │ │
│ │..│...  │...  │ │
│ └──┴─────┴─────┘ │
└───────┬──────────┘
        │
        ▼

Step 2: Create Table
┌────────────────────────────────┐
│ conn.execute(                  │
│   "CREATE TABLE extract_data   │
│    AS SELECT * FROM chunk_df"  │
│ )                              │
└───────┬────────────────────────┘
        │
        ▼

Step 3: DuckDB Infers Schema
┌─────────────────────────────────┐
│ DuckDB Table: extract_data      │
│ ┌──────────┬──────────────────┐ │
│ │ Column   │ Type             │ │
│ ├──────────┼──────────────────┤ │
│ │ id       │ BIGINT           │ │
│ │ name     │ VARCHAR          │ │
│ │ value    │ BIGINT           │ │
│ └──────────┴──────────────────┘ │
│                                 │
│ Data: 1000 rows                 │
└─────────────────────────────────┘
```

## Data Flow - Subsequent Chunks

```
Step 1: Read Next Chunk
┌────────────────┐
│ next(iterator) │
└───────┬────────┘
        │
        ▼
┌──────────────────┐
│ DataFrame (1000) │
│ ┌──┬─────┬─────┐ │
│ │id│name │value│ │
│ ├──┼─────┼─────┤ │
│ │..│...  │...  │ │
│ └──┴─────┴─────┘ │
└───────┬──────────┘
        │
        ▼

Step 2: Insert Into Existing Table
┌────────────────────────────────┐
│ conn.execute(                  │
│   "INSERT INTO extract_data    │
│    SELECT * FROM chunk_df"     │
│ )                              │
└───────┬────────────────────────┘
        │
        ▼

Step 3: Table Grows
┌─────────────────────────────────┐
│ DuckDB Table: extract_data      │
│                                 │
│ Data: 2000 rows (was 1000)      │
│                                 │
│ Memory: Still ~constant         │
│ (columnar compression)          │
└─────────────────────────────────┘
```

## Error Handling Flow

```
┌─────────────────────────────────────────────────────┐
│                   run() method                      │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
         ┌────────────────┐
         │ Validate config │
         └────────┬────────┘
                  │
         ┌────────▼──────────┐
         │ 'path' in config? │
         └─────┬──────────┬──┘
               │ NO       │ YES
               ▼          ▼
        ┌─────────────┐  ┌───────────┐
        │ ValueError  │  │ File exists?│
        │ "required"  │  └─────┬──────┘
        └─────────────┘        │
                      ┌────────▼──────┐
                      │ NO           │ YES
                      ▼              ▼
               ┌─────────────┐  ┌──────────────┐
               │ ValueError  │  │ Open CSV file │
               │ "not found" │  └──────┬────────┘
               └─────────────┘         │
                              ┌────────▼─────────┐
                              │ Empty file?      │
                              └─────┬──────────┬─┘
                                    │ YES      │ NO
                                    ▼          ▼
                           ┌──────────────┐  ┌──────────┐
                           │ EmptyDataError│  │ Process  │
                           └──────┬────────┘  │ chunks   │
                                  │           └──────────┘
                           ┌──────▼────────┐
                           │ Create empty  │
                           │ placeholder   │
                           │ return rows=0 │
                           └───────────────┘
```

## Performance Characteristics

### Time Complexity

```
Operation          | Complexity | Notes
-------------------|------------|--------------------------------
Read CSV           | O(n)       | Linear scan of file
Create Table       | O(b)       | b = batch_size (first chunk)
Insert Chunks      | O(c×b)     | c = num_chunks, b = batch_size
Total              | O(n)       | Dominated by CSV parsing

Where:
  n = total rows in file
  c = number of chunks = n / batch_size
  b = batch_size (default 1000)
```

### Space Complexity

```
Component              | Size       | Notes
-----------------------|------------|---------------------------
Input File             | O(n)       | Original CSV on disk
Pandas Chunk           | O(b)       | One batch in memory
DuckDB Table           | O(n×0.3)   | ~30% of CSV (compressed)
Peak Memory            | O(b)       | Constant, independent of n
```

### Benchmark Results

```
File Size    | Rows    | Batch Size | Time    | Throughput
-------------|---------|------------|---------|-------------
3.54 MB      | 100K    | 5,000      | 0.07s   | 1.52M rows/s
100 MB       | 3M      | 10,000     | ~2s     | 1.5M rows/s
1 GB         | 30M     | 10,000     | ~20s    | 1.5M rows/s

Environment: M1 Mac, 16GB RAM, SSD
```

## Integration with Osiris Pipeline

```
┌──────────────────────────────────────────────────────────┐
│                    Osiris Pipeline                       │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  steps:                                                  │
│    - id: extract_users                                   │
│      type: extractor                                     │
│      driver: csv_streaming                               │
│      config:                                             │
│        path: /data/users.csv                             │
│        batch_size: 5000                                  │
│                                                          │
│    - id: transform_users                                 │
│      type: processor                                     │
│      inputs:                                             │
│        - extract_users  ← DuckDB table available        │
│      config:                                             │
│        query: |                                          │
│          SELECT                                          │
│            user_id,                                      │
│            UPPER(name) as name,                          │
│            country                                       │
│          FROM extract_users                              │
│          WHERE active = true                             │
│                                                          │
└──────────────────────────────────────────────────────────┘

Execution Flow:
1. extract_users runs → Creates DuckDB table
2. transform_users runs → Queries DuckDB table
3. Both steps share same DuckDB connection (via ctx)
4. No DataFrame serialization needed
5. Streaming end-to-end
```

## Comparison with Alternatives

### Option 1: Load Full File (Traditional)
```python
df = pd.read_csv("data.csv")  # Load entire file
conn.execute("CREATE TABLE t AS SELECT * FROM df")

Pros: Simple code
Cons:
  - Memory = file size (OOM for large files)
  - Slow for large files (parsing + loading)
```

### Option 2: DuckDB Native CSV Reader
```python
conn.execute(f"CREATE TABLE t AS SELECT * FROM read_csv_auto('{path}')")

Pros:
  - Fastest (native C++)
  - Zero-copy when possible
Cons:
  - Less control over chunking
  - Harder to add custom preprocessing
```

### Option 3: This Prototype (Pandas Chunks)
```python
for chunk in pd.read_csv(path, chunksize=1000):
    conn.execute("INSERT INTO t SELECT * FROM chunk")

Pros:
  - Memory efficient (constant memory)
  - Flexible (can preprocess chunks)
  - Works with any CSV complexity
Cons:
  - Slower than native DuckDB reader
  - More code than alternatives
```

### Recommendation

- **Production**: Use DuckDB native reader (Option 2) for best performance
- **Complex CSVs**: Use this approach (Option 3) when preprocessing needed
- **Small files**: Any approach works, simplest is best

## Future Enhancements

### 1. Adaptive Batch Sizing
```python
# Adjust batch_size based on row width
row_width = estimate_row_width(first_chunk)
target_memory = 10 * 1024 * 1024  # 10 MB
batch_size = target_memory // row_width
```

### 2. Parallel Chunk Processing
```python
# Process chunks in parallel (requires ordered merge)
with ThreadPoolExecutor(max_workers=4) as executor:
    futures = [executor.submit(process_chunk, chunk)
               for chunk in chunks]
```

### 3. Progress Callbacks
```python
# Report progress to UI/monitoring
for i, chunk in enumerate(chunks):
    process_chunk(chunk)
    ctx.report_progress(processed=i*batch_size, total=estimated_total)
```

### 4. Schema Validation
```python
# Validate against expected schema
expected_schema = {"id": "int64", "name": "str", "value": "float64"}
validate_chunk_schema(chunk, expected_schema)
```

## References

- **DuckDB Python API**: https://duckdb.org/docs/api/python/overview
- **Pandas Chunking**: https://pandas.pydata.org/docs/user_guide/io.html#iterating-through-files-chunk-by-chunk
- **Osiris Driver Guidelines**: `/Users/padak/github/osiris/CLAUDE.md` (Driver Development Guidelines)
- **ADR 0043**: DuckDB-based streaming architecture
