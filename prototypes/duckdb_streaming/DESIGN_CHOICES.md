# CSV Streaming Writer - Design Choices

**Created:** 2025-11-10
**Component:** CSV Writer (DuckDB → CSV)
**Status:** Prototype

## Overview

This document explains the key design decisions made in the CSV Streaming Writer prototype, including rationale and trade-offs.

## Design Choices

### 1. Shared DuckDB Connection (via ctx.get_db_connection())

**Choice:** Get connection from execution context instead of creating new connection.

```python
con = ctx.get_db_connection()
```

**Rationale:**
- All pipeline steps share same DuckDB database
- Database file: `<session_dir>/pipeline_data.duckdb`
- Each step's output is a table in this shared database
- Context manages connection lifecycle

**Alternative Rejected:**
```python
# Would require passing database path in inputs
db_path = inputs["duckdb_path"]
con = duckdb.connect(str(db_path))
```

**Why Rejected:** Increases coupling, requires passing paths between steps, complicates error handling.

---

### 2. Table Name Input (not DataFrame)

**Choice:** Accept table name in inputs, not DataFrame.

```python
inputs = {"table": "extract_customers"}
```

**Rationale:**
- Aligns with DuckDB streaming architecture
- Table already exists in shared database
- Created by upstream extractor or processor
- No DataFrame serialization/deserialization

**Alternative Rejected:**
```python
# Old approach - DataFrame passing
inputs = {"df_extract_customers": dataframe}
```

**Why Rejected:** Requires holding entire dataset in memory between steps, needs spilling logic in E2B, doesn't scale to large datasets.

---

### 3. Alphabetical Column Sorting

**Choice:** Sort columns alphabetically before writing CSV.

```python
columns_result = con.execute(
    f"SELECT column_name FROM information_schema.columns
     WHERE table_name = '{table_name}'
     ORDER BY column_name"
).fetchall()
sorted_columns = [col[0] for col in columns_result]
```

**Rationale:**
- Maintains compatibility with current `FilesystemCsvWriterDriver`
- Provides deterministic output (same data → same CSV structure)
- Helps with testing and validation

**Alternative Rejected:**
```python
# Use DuckDB's default column order
con.execute(f"SELECT * FROM {table_name}")
```

**Why Rejected:** Non-deterministic output makes testing harder, breaks compatibility with existing driver behavior.

---

### 4. Hybrid Approach (DuckDB Query + pandas Write)

**Choice:** Query DuckDB with sorted columns, then write via pandas.

```python
# Build SELECT with sorted columns
columns_sql = ", ".join([f'"{col}"' for col in sorted_columns])
query = f"SELECT {columns_sql} FROM {table_name}"
df = con.execute(query).df()

# Write via pandas for control over formatting
df.to_csv(output_path, sep=delimiter, encoding=encoding, ...)
```

**Rationale:**
- DuckDB COPY TO doesn't support custom column ordering
- Need full control over CSV formatting (line endings, delimiters, etc.)
- pandas provides reliable CSV writing with all options

**Alternative Rejected:**
```python
# Pure DuckDB approach
con.execute(f"COPY {table_name} TO '{output_path}' (FORMAT CSV, HEADER TRUE)")
```

**Why Rejected:**
- No column ordering support
- Limited control over CSV format options
- Would break compatibility with current driver

**Future Enhancement:** Contribute column ordering feature to DuckDB COPY command.

---

### 5. Memory Trade-off (Load DataFrame for Final Write)

**Choice:** Accept loading full dataset into memory for CSV write.

```python
df = con.execute(query).df()  # Loads full dataset
df.to_csv(output_path, ...)
```

**Rationale:**
- Writers are final steps (no downstream consumers)
- CSV output implies dataset fits on disk
- **Critical:** Upstream steps (extractors, processors) never loaded full dataset
- Only egress point materializes data

**Trade-off:**
- **Cost:** Memory usage at final step
- **Benefit:** Upstream pipeline stays memory-efficient, E2B doesn't need spilling

**Alternative Considered:**
```python
# Chunked writing
for chunk in con.execute(query).fetch_df_chunk(1000):
    chunk.to_csv(output_path, mode='a', header=(first_chunk))
```

**Why Not Chosen:** Adds complexity for uncommon case (CSV files that don't fit in memory). Can be added later if needed.

---

### 6. Error Handling Strategy

**Choice:** Validate early and fail fast.

```python
# Validate inputs
if not inputs or "table" not in inputs:
    raise ValueError(f"Step {step_id}: CSVStreamingWriter requires 'table' in inputs")

# Validate table exists
table_check = con.execute(
    f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = '{table_name}'"
).fetchone()[0]
if table_check == 0:
    raise ValueError(f"Step {step_id}: Table '{table_name}' does not exist in DuckDB")
```

**Rationale:**
- Clear error messages help debugging
- Fail before expensive operations
- Validate assumptions early

---

### 7. Path Handling

**Choice:** Support both absolute and relative paths, create directories automatically.

```python
output_path = Path(file_path)
if not output_path.is_absolute():
    output_path = Path.cwd() / output_path

output_path.parent.mkdir(parents=True, exist_ok=True)
```

**Rationale:**
- Matches current driver behavior
- Prevents confusing "directory not found" errors
- Relative paths resolve to current working directory

---

### 8. Configuration Compatibility

**Choice:** Support exact same config options as current driver.

```python
config = {
    "path": "...",           # Required
    "delimiter": ",",        # Default: ","
    "encoding": "utf-8",     # Default: "utf-8"
    "header": True,          # Default: True
    "newline": "lf",         # Default: "lf"
}
```

**Rationale:**
- Drop-in replacement for current driver
- No breaking changes to pipeline YAML
- Users familiar with current options

---

## Alignment with Streaming Vision

The design aligns with ADR 0043's streaming architecture:

```
Pipeline Flow:
┌─────────────┐     ┌──────────────┐     ┌────────────┐
│  Extractor  │────▶│  Processor   │────▶│   Writer   │
│             │     │              │     │            │
│ CSV → Table │     │ SQL → Table  │     │ Table → CSV│
└─────────────┘     └──────────────┘     └────────────┘

Data Storage:
pipeline_data.duckdb
├── extract_customers    ← Extractor creates table
├── transform_customers  ← Processor creates table
└── (Writer reads table)
```

**Key Properties:**
1. ✅ Data stays in DuckDB throughout pipeline
2. ✅ No DataFrame passing between steps
3. ✅ Memory-efficient (except final write)
4. ✅ Eliminates E2B spilling logic
5. ✅ Query pushdown possible in processors

---

## Rejected Design Alternatives

### Alternative A: Pure DuckDB Native Export

```python
con.execute(f"COPY {table_name} TO '{output_path}' (FORMAT CSV, HEADER TRUE)")
```

**Rejected because:**
- No column ordering support
- Limited CSV format options
- Would require DuckDB enhancement first

**When to reconsider:** If DuckDB adds column ordering to COPY command.

---

### Alternative B: Chunked Streaming Write

```python
batch_size = 10000
offset = 0
while True:
    chunk = con.execute(f"SELECT * FROM {table_name} LIMIT {batch_size} OFFSET {offset}").df()
    if len(chunk) == 0:
        break
    chunk.to_csv(output_path, mode='a', header=(offset == 0))
    offset += batch_size
```

**Rejected because:**
- Added complexity for uncommon case
- CSV files typically fit in memory
- Can add later if needed

**When to reconsider:** If users request support for massive CSV exports (>10GB).

---

### Alternative C: Separate Database Per Step

```python
# Each step writes to own .duckdb file
step_db = f"<session_dir>/{step_id}.duckdb"
```

**Rejected because:**
- Increases disk usage
- Complicates cleanup
- Harder to query across steps
- ADR 0043 explicitly chose shared database

---

## Open Questions

### Q1: Should we add chunked writing support?

**Current stance:** No, wait for user demand.

**Reconsider if:** Users report memory issues writing large CSVs.

**Implementation path:** Add `batch_size` config option, default to None (load all).

---

### Q2: Should we contribute column ordering to DuckDB?

**Current stance:** Yes, would simplify implementation.

**Proposal:**
```sql
COPY table_name TO 'output.csv' (FORMAT CSV, COLUMN_ORDER 'alphabetical')
```

**Benefits:** Eliminates hybrid approach, faster execution, simpler code.

---

### Q3: Should column sorting be optional?

**Current stance:** No, keep it simple.

**Reconsider if:** Performance-sensitive users request it.

**Implementation:**
```python
config = {
    "path": "output.csv",
    "sort_columns": False  # Skip sorting for speed
}
```

---

## Testing Coverage

Demo script (`demo_csv_writer.py`) covers:

- ✅ Basic CSV write from DuckDB table
- ✅ Custom delimiter (TSV example)
- ✅ Column sorting (alphabetical order)
- ✅ Metrics logging (`rows_written`)
- ✅ Path handling (relative, absolute, directory creation)
- ✅ Error handling (missing table, missing config, missing inputs)
- ✅ Multiple line ending styles

---

## Future Enhancements

1. **Chunked writing** - For massive datasets
2. **DuckDB COPY enhancement** - Contribute column ordering
3. **Optional sorting** - Performance optimization
4. **Compression support** - Write .csv.gz directly
5. **Progress callbacks** - For long-running writes

---

## Related Documentation

- **Implementation:** `csv_writer.py` - Prototype code
- **Demo:** `demo_csv_writer.py` - Usage examples
- **ADR:** `/docs/adr/0043-duckdb-data-exchange.md` - Architecture decision
- **Current Driver:** `/osiris/drivers/filesystem_csv_writer_driver.py` - Comparison baseline
