# Component Error Patterns & Troubleshooting

## How to Use This Guide

1. Find your error message below
2. Identify root cause
3. Apply the fix
4. Validate with component doctor

## Validation Errors

### Error: "Invalid spec: [] is valid under each of..."

**Symptom:** Component doesn't appear in `osiris components list`

**Root Cause:** Empty x-connection-fields array is ambiguous (matches both oneOf schemas)

**Fix:**
- Remove `x-connection-fields: []` line entirely
- Or use `x-connection-fields: null`

**Example:**
```yaml
# ❌ WRONG
x-connection-fields: []

# ✅ CORRECT (omit entirely)
# No x-connection-fields key
```

### Error: "Missing required field 'primary_key'"

**Symptom:** OML validates but compilation fails

**Root Cause:** write_mode=replace/upsert requires primary_key

**Fix:**
```yaml
config:
  write_mode: replace
  primary_key: id  # ✅ Add this
```

### Error: "Unknown component: 'myservice.extractor'"

**Symptom:** Component not found in registry

**Root Causes:**
1. spec.yaml has validation errors
2. Wrong directory structure
3. Registry cache issue

**Fixes:**
1. Check `osiris components list` for warnings
2. Verify structure: `components/myservice.extractor/spec.yaml`
3. Restart Python process (clears cache)

### Error: "Additional properties are not allowed"

**Symptom:** Component spec fails schema validation

**Root Cause:** Unknown field in spec.yaml (typo or wrong location)

**Fix:**
```yaml
# ❌ WRONG: Typo in field name
x-conection-fields:  # Missing 'n'

# ✅ CORRECT
x-connection-fields:

# ❌ WRONG: Field in wrong place
config:
  type: object
  x-runtime:  # Should be at root level
    driver: ...

# ✅ CORRECT
config:
  type: object
x-runtime:  # At root level
  driver: ...
```

### Error: "spec.yaml not found"

**Symptom:** Component directory exists but not recognized

**Root Causes:**
1. File named incorrectly (e.g., `spec.yml` instead of `spec.yaml`)
2. Wrong directory structure
3. File in subdirectory instead of root

**Fixes:**
1. Rename to `spec.yaml` (not .yml)
2. Structure: `components/component.type/spec.yaml` (not `components/spec.yaml`)
3. Move spec.yaml to component root directory

## Discovery Errors

### Error: "Non-deterministic discovery output"

**Symptom:** DISC-001 validation fails

**Root Cause:** Discovery returns different order on repeated calls

**Fix:**
```python
# ❌ WRONG: No sorting
results = cursor.fetchall()

# ✅ CORRECT: Deterministic order
results = sorted(cursor.fetchall(), key=lambda x: x["table_name"])
```

### Error: "Missing discovered_at timestamp"

**Root Cause:** Discovery response missing metadata

**Fix:**
```python
return {
    "tables": [...],
    "discovered_at": datetime.utcnow().isoformat() + "Z",  # ✅ Add this
}
```

### Error: "Discovery returns empty results"

**Symptom:** `osiris discover` returns no tables but database has data

**Root Causes:**
1. Wrong schema/database filter
2. Insufficient permissions
3. Connection configuration incorrect

**Fixes:**
```python
# 1. Check filters
discovery = self.discover(
    connection=conn,
    schema="public"  # ✅ Verify schema name
)

# 2. Test permissions
cursor.execute("SHOW TABLES")  # MySQL
cursor.execute("SELECT * FROM information_schema.tables")  # PostgreSQL

# 3. Verify connection
logger.debug(f"Connected to database: {conn.config.get('database')}")
```

## Connection Errors

### Error: "Connection failed: Authentication error"

**Root Causes:**
1. Wrong credentials in connection
2. Password field not in secrets array
3. Connection reference incorrect

**Fixes:**
1. Test: `osiris connections doctor <connection-name>`
2. Verify secrets in spec.yaml:
   ```yaml
   secrets:
     - /config/password  # ✅ Add if missing
   ```
3. Check OML: `connection: "@mysql.production"`

### Error: "Connection timeout after 30s"

**Root Cause:** Network latency or slow database

**Fix:**
```python
# Add timeout parameter
def run(self, *, config, ctx, timeout=60):  # ✅ Configurable
    ...
```

### Error: "KeyError: 'host' when accessing connection config"

**Root Cause:** Accessing connection fields without validation

**Fix:**
```python
# ❌ WRONG: Direct access
host = connection.config["host"]

# ✅ CORRECT: Safe access with defaults
host = connection.config.get("host", "localhost")

# ✅ BETTER: Validate required fields
required = ["host", "database", "user", "password"]
missing = [f for f in required if f not in connection.config]
if missing:
    raise ValueError(f"Missing required fields: {missing}")
```

### Error: "Connection reference '@mydb.prod' not found"

**Root Cause:** Connection not defined in config or wrong name

**Fixes:**
1. List connections: `osiris connections list`
2. Check config: `cat .osiris/config.yaml`
3. Verify reference syntax: `connection: "@mysql.production"` (include @)

## Runtime Errors

### Error: "TypeError: run() got an unexpected keyword argument"

**Root Cause:** Driver not using keyword-only args

**Fix:**
```python
# ❌ WRONG
def run(self, step_id, config, inputs, ctx):

# ✅ CORRECT
def run(self, *, step_id, config, inputs, ctx):  # Note the *
```

### Error: "KeyError: 'data' in inputs"

**Root Cause:** Accessing upstream step data incorrectly

**Fix:**
```python
# ❌ WRONG
df = inputs["previous_step"]

# ✅ CORRECT
df = inputs["previous_step"]["data"]

# ✅ SAFE: Handle missing inputs
if "previous_step" not in inputs:
    raise ValueError("Missing required input: previous_step")
df = inputs["previous_step"]["data"]
```

### Error: "Secret leaked in logs"

**Root Cause:** Logging connection string with password

**Fix:**
```python
# ❌ WRONG
logger.info(f"Connecting to {connection_string}")

# ✅ CORRECT
from osiris.cli.helpers.connection_helpers import mask_url
logger.info(f"Connecting to {mask_url(connection_string)}")

# For non-URL secrets
from osiris.cli.helpers.connection_helpers import mask_connection_for_display
safe_config = mask_connection_for_display(config)
logger.info(f"Config: {safe_config}")
```

### Error: "pandas.errors.EmptyDataError: No columns to parse"

**Root Cause:** Query returns no results or empty CSV

**Fix:**
```python
# ❌ WRONG: No validation
df = pd.read_sql(query, connection)

# ✅ CORRECT: Validate results
cursor.execute(query)
results = cursor.fetchall()
if not results:
    logger.warning("Query returned no results")
    return pd.DataFrame()  # Empty dataframe
df = pd.DataFrame(results)
```

### Error: "AttributeError: 'NoneType' object has no attribute 'config'"

**Root Cause:** Connection object not passed or is None

**Fix:**
```python
# ❌ WRONG: No validation
def run(self, *, config, ctx):
    connection = ctx.resolve_connection(config["connection"])
    host = connection.config["host"]  # Fails if connection is None

# ✅ CORRECT: Validate connection
def run(self, *, config, ctx):
    connection = ctx.resolve_connection(config["connection"])
    if not connection:
        raise ValueError(f"Connection not found: {config['connection']}")
    host = connection.config["host"]
```

## Compilation Errors

### Error: "Step reference 'extract' not found"

**Root Cause:** Using step ID that doesn't exist in pipeline

**Fix:**
```yaml
# ❌ WRONG: Referencing non-existent step
steps:
  - id: load
    inputs:
      - source: extract  # This step doesn't exist

# ✅ CORRECT: Use actual step ID
steps:
  - id: my_extract
    component: myservice.extractor
  - id: load
    inputs:
      - source: my_extract
```

### Error: "Circular dependency detected"

**Root Cause:** Step depends on itself directly or indirectly

**Fix:**
```yaml
# ❌ WRONG: Circular dependency
steps:
  - id: step_a
    inputs:
      - source: step_b
  - id: step_b
    inputs:
      - source: step_a

# ✅ CORRECT: Linear dependency
steps:
  - id: step_a
    # No inputs
  - id: step_b
    inputs:
      - source: step_a
```

### Error: "Invalid input reference format"

**Root Cause:** Wrong syntax for referencing upstream data

**Fix:**
```yaml
# ❌ WRONG: Missing 'source' key
inputs:
  - extract

# ✅ CORRECT: Use 'source' key
inputs:
  - source: extract
```

## Test Errors

### Error: "detect-secrets scan failed"

**Root Cause:** Test credentials not suppressed

**Fix:**
```python
# Add suppressions
config = {"api_key": "test_key"}  # pragma: allowlist secret
conn_str = "mysql://user:pass@localhost"  # nosec B105
password = "fake_password"  # pragma: allowlist secret
```

### Error: "Import error: No module named 'osiris.drivers...'"

**Root Cause:** Driver file not created or wrong path

**Fix:**
1. Verify file exists: `osiris/drivers/myservice_extractor_driver.py`
2. Check class name matches spec: `MyServiceExtractorDriver`
3. Verify x-runtime.driver path in spec.yaml:
   ```yaml
   x-runtime:
     driver: osiris.drivers.myservice_extractor_driver.MyServiceExtractorDriver
   ```

### Error: "pytest: command not found"

**Root Cause:** pytest not installed or virtual environment not activated

**Fix:**
```bash
# Activate environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Verify pytest
pytest --version
```

### Error: "Test failed: AssertionError: DataFrame.empty"

**Root Cause:** Test expects data but got empty result

**Fix:**
```python
# ❌ WRONG: No data validation
def test_extraction():
    result = driver.run(...)
    assert not result.empty  # Fails if no data

# ✅ CORRECT: Mock data or validate conditions
def test_extraction():
    # Option 1: Mock data source
    with patch("mysql.connector.connect") as mock_conn:
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [{"id": 1, "name": "test"}]
        mock_conn.return_value.cursor.return_value = mock_cursor
        result = driver.run(...)
        assert not result.empty

    # Option 2: Test empty case separately
    if result.empty:
        assert query_returned_no_results  # Verify expected behavior
```

## OML Errors

### Error: "Invalid OML: version field required"

**Root Cause:** Missing or incorrect version field

**Fix:**
```yaml
# ❌ WRONG: Missing version
name: my-pipeline
steps: [...]

# ✅ CORRECT: Include version
version: "1"
name: my-pipeline
steps: [...]
```

### Error: "Component not found in registry"

**Root Cause:** Component spec has errors or not loaded

**Fixes:**
```bash
# 1. Validate component
osiris components validate myservice.extractor

# 2. Check registry
osiris components list | grep myservice

# 3. Check for spec errors
cat components/myservice.extractor/spec.yaml

# 4. Restart to clear cache
# Exit Python, restart shell
```

### Error: "Invalid config for component: Additional properties not allowed"

**Root Cause:** Config contains fields not defined in component spec

**Fix:**
```yaml
# ❌ WRONG: Unknown field 'timeout'
- id: extract
  component: myservice.extractor
  config:
    query: "SELECT *"
    timeout: 30  # Not in spec

# ✅ CORRECT: Only use defined fields
- id: extract
  component: myservice.extractor
  config:
    query: "SELECT *"
```

## Debugging Checklist

When component fails:

1. ✅ Run validation: `osiris components validate myservice.extractor`
2. ✅ Check registry: `osiris components list | grep myservice`
3. ✅ Test connection: `osiris connections doctor <connection>`
4. ✅ Check logs: `osiris logs --last`
5. ✅ Verify tests: `pytest tests/drivers/test_myservice_*`
6. ✅ Run checklist: See COMPONENT_AI_CHECKLIST.md
7. ✅ Check driver path: Verify x-runtime.driver matches actual file
8. ✅ Test in isolation: Create minimal OML to test component alone
9. ✅ Check dependencies: Verify all required packages installed
10. ✅ Review AIOP: `osiris logs aiop --last` for detailed execution trace

## Common Patterns to Avoid

### Pattern: Hardcoded Paths

```python
# ❌ WRONG
output_path = Path.home() / ".osiris" / "output"

# ✅ CORRECT: Use config-driven paths
from osiris.core.config import Config
config = Config.load()
output_path = config.get_path("output")
```

### Pattern: Direct Secret Access in MCP

```python
# ❌ WRONG: MCP accessing secrets
def mcp_tool_handler(connection_name):
    conn = get_connection(connection_name)
    password = conn.config["password"]  # SECURITY VIOLATION

# ✅ CORRECT: Delegate to CLI
def mcp_tool_handler(connection_name):
    result = run_cli_json(["connections", "test", connection_name])
    return result  # CLI handles secrets
```

### Pattern: Non-Deterministic Output

```python
# ❌ WRONG: Dict iteration (order not guaranteed in Python <3.7)
for table, schema in tables.items():
    results.append(process(table, schema))

# ✅ CORRECT: Sort keys
for table in sorted(tables.keys()):
    results.append(process(table, tables[table]))
```

### Pattern: Missing Error Context

```python
# ❌ WRONG: Generic error
raise ValueError("Invalid configuration")

# ✅ CORRECT: Detailed context
raise ValueError(
    f"Invalid configuration for component '{component_id}': "
    f"Missing required field 'query'. "
    f"Available fields: {list(config.keys())}"
)
```

## Performance Issues

### Issue: Slow Component Discovery

**Symptom:** `osiris components list` takes >2 seconds

**Root Cause:** Complex schema validation on every call

**Fix:**
```python
# Registry caches validation results
# Just restart Python process to clear cache
# Or use lazy loading for tests
```

### Issue: Memory Error During Large Extraction

**Symptom:** OOM error with large datasets

**Root Cause:** Loading entire dataset into memory

**Fix:**
```python
# ❌ WRONG: Load all rows
cursor.execute(query)
all_rows = cursor.fetchall()  # OOM for large tables
df = pd.DataFrame(all_rows)

# ✅ CORRECT: Use chunking
chunk_size = 10000
for chunk in pd.read_sql(query, connection, chunksize=chunk_size):
    process_chunk(chunk)
```

### Issue: Slow Test Suite

**Symptom:** Tests take >5 minutes

**Root Causes:**
1. No test markers for slow tests
2. Real database connections in unit tests
3. No fixture reuse

**Fixes:**
```python
# 1. Mark slow tests
@pytest.mark.slow
def test_large_extraction():
    ...

# 2. Mock external dependencies
@patch("mysql.connector.connect")
def test_extraction(mock_connect):
    ...

# 3. Use session fixtures
@pytest.fixture(scope="session")
def shared_connection():
    return create_connection()
```

## Related Documentation

- COMPONENT_AI_CHECKLIST.md - All validation rules
- build-new-component.md - Correct implementation patterns
- components-spec.md - Schema reference
- START-HERE.md - Overview and quick start
- connection-doctor.md - Connection troubleshooting

## Emergency Debugging

If all else fails:

```bash
# 1. Enable debug logging
export OSIRIS_LOG_LEVEL=DEBUG
osiris run pipeline.yaml

# 2. Export full AIOP
osiris logs aiop --last --format json > debug.json

# 3. Validate everything
osiris components validate --all
osiris connections doctor --all

# 4. Clean slate
rm -rf .osiris_cache/
rm -rf .osiris_sessions/
osiris init

# 5. Check environment
python --version  # Should be 3.8+
pip list | grep osiris
env | grep OSIRIS
```
