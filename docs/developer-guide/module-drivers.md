# Drivers Module Documentation

## Overview
The Drivers module (`osiris/drivers/`) contains concrete implementations of data operation components that follow the Driver protocol.

## Module Structure
```
osiris/drivers/
├── mysql_extractor_driver.py      # MySQL data extraction
├── mysql_writer_driver.py          # MySQL data writing
├── supabase_extractor_driver.py   # Supabase extraction
├── supabase_writer_driver.py      # Supabase writing
├── filesystem_csv_writer_driver.py # CSV file writing
└── filesystem_parquet_writer_driver.py # Parquet writing
```

## Driver Protocol

All drivers must implement the core protocol defined in `osiris/core/driver.py`:

```python
def run(
    self,
    step_id: str,
    config: dict,
    inputs: dict | None,
    ctx: ExecutionContext
) -> dict:
    """
    Execute a pipeline step.

    Args:
        step_id: Unique identifier for this step
        config: Step configuration including resolved connections
        inputs: Input data from upstream steps (e.g., {"df": DataFrame})
        ctx: Execution context for logging metrics

    Returns:
        Output data dictionary (e.g., {"df": DataFrame} for extractors)
    """
```

## Driver Categories

### Extractors (mode: "read")
Extract data from external sources into DataFrames.

**Characteristics:**
- No required inputs
- Return `{"df": pandas.DataFrame}`
- Must log `rows_read` metric
- Enforce read-only SQL validation
- Support query timeout protection

### Writers (mode: "write")
Write DataFrames to destinations.

**Characteristics:**
- Require input `{"df": DataFrame}`
- Return empty dict `{}`
- Must log `rows_written` metric
- Support write modes (append, overwrite, upsert)
- Handle transaction management

### Transformers (mode: "transform")
Transform DataFrames (planned for M2).

**Characteristics:**
- Require input `{"df": DataFrame}`
- Return `{"df": DataFrame}`
- Must log `rows_processed` metric

## Implemented Drivers

### mysql_extractor_driver.py

Extracts data from MySQL/MariaDB databases.

**Configuration:**
```python
{
    "connection": "@mysql.default",  # Or resolved connection dict
    "query": "SELECT * FROM users WHERE active = 1",
    "timeout": 30,  # Optional, seconds
    "batch_size": 10000  # Optional, for large results
}
```

**Features:**
- SQL injection protection via read-only validation
- Connection pooling support
- Query timeout handling
- Large result set streaming

**Example:**
```python
from osiris.drivers.mysql_extractor_driver import MySQLExtractorDriver

driver = MySQLExtractorDriver()
result = driver.run(
    step_id="extract_users",
    config={
        "resolved_connection": {
            "host": "localhost",
            "database": "mydb",
            "username": "user",
            "password": "***"
        },
        "query": "SELECT * FROM users LIMIT 100"
    },
    inputs=None,
    ctx=execution_context
)
# result = {"df": DataFrame with 100 rows}
```

### filesystem_csv_writer_driver.py

Writes DataFrames to CSV files.

**Configuration:**
```python
{
    "path": "output/data.csv",
    "write_mode": "overwrite",  # or "append"
    "encoding": "utf-8",
    "separator": ",",
    "newline": "lf",  # or "crlf", "cr"
    "include_header": True,
    "compression": None  # or "gzip", "bz2", "zip"
}
```

**Features:**
- Deterministic output (sorted columns)
- Multiple compression formats
- Configurable delimiters and line endings
- Atomic writes with temp files

**Example:**
```python
driver = FilesystemCSVWriterDriver()
driver.run(
    step_id="save_csv",
    config={
        "path": "output/users.csv",
        "write_mode": "overwrite"
    },
    inputs={"df": users_dataframe},
    ctx=execution_context
)
```

### supabase_writer_driver.py

Writes DataFrames to Supabase PostgreSQL tables.

**Configuration:**
```python
{
    "connection": "@supabase.main",
    "table": "users",
    "write_mode": "upsert",  # or "append", "overwrite"
    "primary_key": "id",  # Required for upsert
    "batch_size": 500,
    "on_conflict": "update"  # or "ignore"
}
```

**Features:**
- Batch processing for large datasets
- Upsert with conflict resolution
- Schema validation before write
- Transaction management
- Automatic retry on transient failures

## Creating a New Driver

### Step 1: Define the Driver Class

```python
# osiris/drivers/my_new_driver.py
from osiris.core.driver import Driver
import pandas as pd

class MyNewDriver:
    """Driver for my data source."""

    def run(self, step_id: str, config: dict, inputs: dict | None, ctx) -> dict:
        # 1. Validate configuration
        self._validate_config(config)

        # 2. Get connection details
        conn = config.get("resolved_connection") or self._resolve_connection(config)

        # 3. Perform operation
        data = self._extract_data(conn, config)

        # 4. Log metrics
        ctx.log_metric("rows_read", len(data))

        # 5. Return result
        return {"df": pd.DataFrame(data)}

    def _validate_config(self, config: dict):
        required = ["connection", "query"]
        for field in required:
            if field not in config:
                raise ValueError(f"Missing required field: {field}")
```

### Step 2: Register the Driver

```python
# osiris/drivers/__init__.py
from osiris.core.driver import DriverRegistry
from .my_new_driver import MyNewDriver

# Register at module import
DriverRegistry.register("mynew.extractor", MyNewDriver())
```

### Step 3: Create Component Spec

```yaml
# components/mynew/extractor/spec.yaml
name: "mynew.extractor"
version: "1.0.0"
description: "Extract data from MyNew source"

config_schema:
  type: object
  required: ["connection", "query"]
  properties:
    connection:
      type: string
      pattern: "^@[a-z]+\\.[a-z]+$"
    query:
      type: string

capabilities:
  modes: ["read"]
  features: ["batch"]
```

### Step 4: Add Tests

```python
# tests/drivers/test_my_new_driver.py
import pytest
from osiris.drivers.my_new_driver import MyNewDriver

def test_extraction():
    driver = MyNewDriver()
    ctx = MockContext()

    result = driver.run(
        step_id="test",
        config={
            "resolved_connection": {...},
            "query": "SELECT * FROM test"
        },
        inputs=None,
        ctx=ctx
    )

    assert "df" in result
    assert ctx.metrics["rows_read"] > 0
```

## Error Handling

### Standard Error Pattern

```python
def run(self, step_id: str, config: dict, inputs: dict | None, ctx) -> dict:
    try:
        # Main logic
        return self._execute(config, inputs, ctx)

    except ConnectionError as e:
        ctx.log_event("connection_failed", {
            "step_id": step_id,
            "error": str(e)
        })
        raise

    except Exception as e:
        ctx.log_event("step_failed", {
            "step_id": step_id,
            "error": str(e),
            "error_type": type(e).__name__
        })
        raise

    finally:
        # Cleanup resources
        self._cleanup()
```

## Metrics Requirements

### Extractors
- `rows_read` - Number of rows extracted
- `query_duration_ms` - Query execution time
- `bytes_read` - Data volume (optional)

### Writers
- `rows_written` - Number of rows written
- `write_duration_ms` - Write operation time
- `bytes_written` - Data volume (optional)

### Example Metric Emission

```python
start_time = time.time()
df = self._execute_query(query)
duration_ms = (time.time() - start_time) * 1000

ctx.log_metric("rows_read", len(df))
ctx.log_metric("query_duration_ms", duration_ms)
ctx.log_metric("bytes_read", df.memory_usage().sum())
```

## Security Considerations

### SQL Validation (Extractors)

```python
FORBIDDEN_OPERATIONS = [
    'INSERT', 'UPDATE', 'DELETE', 'DROP',
    'CREATE', 'ALTER', 'TRUNCATE'
]

def validate_read_only(query: str):
    query_upper = query.upper()
    for op in FORBIDDEN_OPERATIONS:
        if op in query_upper:
            raise ValueError(f"Operation {op} not allowed in read context")
```

### Connection Security
- Never log passwords or API keys
- Use `resolved_connection` from compiler
- Mask sensitive data in error messages
- Use connection pooling where possible

## Performance Optimization

### Batch Processing
```python
def process_in_batches(df: pd.DataFrame, batch_size: int):
    for i in range(0, len(df), batch_size):
        batch = df.iloc[i:i+batch_size]
        yield batch
```

### Connection Pooling
```python
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

engine = create_engine(
    connection_url,
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10
)
```

## Testing Drivers

### Unit Test Template
```python
class TestMyDriver:
    def test_successful_extraction(self):
        # Arrange
        driver = MyDriver()
        config = {...}
        ctx = MockContext()

        # Act
        result = driver.run("test", config, None, ctx)

        # Assert
        assert "df" in result
        assert isinstance(result["df"], pd.DataFrame)

    def test_missing_config(self):
        driver = MyDriver()
        with pytest.raises(ValueError, match="Missing required"):
            driver.run("test", {}, None, MockContext())
```

## Best Practices

1. **Validate configuration early** - Fail fast with clear errors
2. **Use type hints** - Improve code clarity and IDE support
3. **Log all operations** - Emit structured events for debugging
4. **Handle cleanup** - Use try/finally for resource management
5. **Test error conditions** - Not just happy paths
6. **Document configuration** - Clear examples in docstrings
7. **Follow naming conventions** - `{source}_{operation}_driver.py`

## Future Enhancements

- Streaming support for large datasets
- Async/await for concurrent operations
- Connection pool management
- Schema inference capabilities
- Data quality validation
