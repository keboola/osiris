# LLM Contract: Drivers

**Purpose**: AI patterns for implementing driver protocol and execution logic.

**Audience**: AI agents, LLMs generating driver code

---

## Driver Protocol

### DRV-001: Keyword-Only Arguments

**Statement**: `run()` MUST use keyword-only arguments (`*`).

**Signature**:
```python
def run(self, *, step_id: str, config: dict, inputs: dict, ctx: Any = None) -> dict:
    """Execute driver logic.

    Args:
        step_id: Unique step identifier
        config: Step configuration (includes resolved_connection if applicable)
        inputs: Outputs from previous steps (keyed by step_id)
        ctx: Execution context (logger, metrics, telemetry)

    Returns:
        dict with 'data' key (pandas DataFrame or dict)
    """
```

**Why**: Prevents positional argument errors, improves clarity.

---

### DRV-002: Return Structure

**Statement**: `run()` MUST return dict with `data` key.

**Extractor Return**:
```python
return {
    "data": df  # pandas.DataFrame
}
```

**Writer Return**:
```python
return {
    "data": {"rows_written": 1000, "status": "success"}
}
```

**Processor Return**:
```python
return {
    "data": transformed_df  # pandas.DataFrame
}
```

---

### DRV-003: Exception Handling

**Statement**: Drivers MUST raise exceptions for unrecoverable errors.

**Pattern**:
```python
def run(self, *, step_id, config, inputs, ctx):
    try:
        # Driver logic
        result = self._extract_data(config)
        return {"data": result}

    except AuthenticationError as e:
        # Non-retryable error: raise immediately
        raise RuntimeError(f"Step {step_id}: Authentication failed: {e}") from e

    except requests.exceptions.Timeout as e:
        # Retryable error: runner will handle retry
        raise RuntimeError(f"Step {step_id}: Request timed out") from e

    except Exception as e:
        # Unknown error: log and raise
        if ctx and hasattr(ctx, "log_error"):
            ctx.log_error(f"Unexpected error: {e}")
        raise RuntimeError(f"Step {step_id}: {e}") from e
```

---

## Configuration Handling

### DRV-004: Connection Resolution

**Statement**: Driver MUST read from `config["resolved_connection"]`, NOT environment.

**Correct**:
```python
def run(self, *, step_id, config, inputs, ctx):
    conn_info = config.get("resolved_connection", {})
    if not conn_info:
        raise ValueError(f"Step {step_id}: 'resolved_connection' is required")

    api_key = conn_info.get("api_key")
    base_url = conn_info.get("base_url")
```

**Wrong**:
```python
import os

def run(self, *, step_id, config, inputs, ctx):
    api_key = os.environ.get("API_KEY")  # ❌ Don't read from environment
```

---

### DRV-005: Config Validation

**Statement**: Driver MUST validate required config fields.

**Implementation**:
```python
def run(self, *, step_id, config, inputs, ctx):
    # Validate required fields
    required = ["query", "connection"]
    for field in required:
        if field not in config:
            raise ValueError(f"Step {step_id}: config field '{field}' is required")

    # Validate connection
    conn_info = config.get("resolved_connection", {})
    if not conn_info:
        raise ValueError(f"Step {step_id}: 'resolved_connection' is required")
```

---

### DRV-006: Default Values

**Statement**: Driver SHOULD provide sensible defaults for optional config.

**Implementation**:
```python
def run(self, *, step_id, config, inputs, ctx):
    # Required fields
    resource = config["resource"]

    # Optional fields with defaults
    limit = config.get("limit", 1000)
    timeout = config.get("timeout", 30)
    batch_size = config.get("batch_size", 100)
```

---

## Input Handling

### DRV-007: Input Access

**Statement**: Driver MUST access inputs via `inputs` dict.

**Pattern**:
```python
def run(self, *, step_id, config, inputs, ctx):
    # Access output from previous step
    if "extract_users" in inputs:
        users_df = inputs["extract_users"]["data"]
    else:
        raise ValueError(f"Step {step_id}: Missing required input 'extract_users'")
```

---

### DRV-008: Input Validation

**Statement**: Driver MUST validate input types and structure.

**Implementation**:
```python
import pandas as pd

def run(self, *, step_id, config, inputs, ctx):
    # Validate input exists
    input_step = config.get("input_step")
    if input_step not in inputs:
        raise ValueError(f"Step {step_id}: Missing input '{input_step}'")

    # Validate input type
    data = inputs[input_step]["data"]
    if not isinstance(data, pd.DataFrame):
        raise TypeError(f"Step {step_id}: Expected DataFrame, got {type(data)}")

    # Validate required columns
    required_cols = ["id", "email"]
    missing = set(required_cols) - set(data.columns)
    if missing:
        raise ValueError(f"Step {step_id}: Missing columns: {missing}")
```

---

## Telemetry

### DRV-009: Metrics Emission

**Statement**: Driver MUST emit required metrics via context.

**Required Metrics**:
- Extractor: `rows_read`
- Writer: `rows_written`
- Processor: `rows_processed`

**Implementation**:
```python
def run(self, *, step_id, config, inputs, ctx):
    # Extract data
    df = self._extract_data(config)

    # Emit metric
    if ctx and hasattr(ctx, "log_metric"):
        ctx.log_metric("rows_read", len(df), unit="rows", tags={"step": step_id})

    return {"data": df}
```

---

### DRV-010: Custom Metrics

**Statement**: Driver MAY emit custom metrics for observability.

**Implementation**:
```python
def run(self, *, step_id, config, inputs, ctx):
    start = time.time()

    # Emit custom metrics
    if ctx and hasattr(ctx, "log_metric"):
        ctx.log_metric("api_calls", api_call_count, unit="calls", tags={"step": step_id})
        ctx.log_metric("cache_hits", cache_hits, unit="code", tags={"step": step_id})
        ctx.log_metric("duration_ms", (time.time() - start) * 1000, unit="ms", tags={"step": step_id})
```

---

### DRV-011: Logging

**Statement**: Driver SHOULD use context logger for structured logging.

**Implementation**:
```python
def run(self, *, step_id, config, inputs, ctx):
    if ctx and hasattr(ctx, "log_info"):
        ctx.log_info(f"Starting extraction for resource: {config['resource']}")

    # ... driver logic ...

    if ctx and hasattr(ctx, "log_info"):
        ctx.log_info(f"Extraction complete: {len(df)} rows")
```

---

## Pagination

### DRV-012: Cursor-Based Pagination

**Statement**: Extractors SHOULD implement pagination for large datasets.

**Pattern**:
```python
def _extract_paginated(self, config: dict, ctx) -> pd.DataFrame:
    """Extract data with pagination."""
    all_data = []
    cursor = None

    while True:
        # Fetch page
        response = self._fetch_page(config, cursor)
        page_data = response["data"]

        if not page_data:
            break

        all_data.extend(page_data)

        # Check for next page
        cursor = response.get("next_cursor")
        if not cursor:
            break

        # Log progress
        if ctx and hasattr(ctx, "log_info"):
            ctx.log_info(f"Fetched {len(all_data)} rows so far...")

    return pd.DataFrame(all_data)
```

---

### DRV-013: Page Size Configuration

**Statement**: Pagination SHOULD respect configurable page size.

**Implementation**:
```python
def run(self, *, step_id, config, inputs, ctx):
    page_size = config.get("page_size", 1000)  # Default: 1000

    # Use page_size in API request
    response = requests.get(
        url,
        params={"limit": page_size, "offset": offset}
    )
```

---

### DRV-014: Progress Reporting

**Statement**: Long-running operations SHOULD report progress.

**Implementation**:
```python
def _extract_paginated(self, config: dict, ctx) -> pd.DataFrame:
    total_pages = self._estimate_pages(config)
    all_data = []

    for page in range(total_pages):
        page_data = self._fetch_page(config, page)
        all_data.extend(page_data)

        # Report progress
        if ctx and hasattr(ctx, "log_info"):
            progress = (page + 1) / total_pages * 100
            ctx.log_info(f"Progress: {progress:.1f}% ({page + 1}/{total_pages} pages)")

    return pd.DataFrame(all_data)
```

---

## Rate Limiting

### DRV-015: Rate Limit Handling

**Statement**: Drivers SHOULD respect API rate limits.

**Implementation**:
```python
import time

class ShopifyExtractorDriver:
    RATE_LIMIT_DELAY = 0.5  # 500ms between requests

    def _fetch_with_rate_limit(self, url: str) -> dict:
        """Fetch with rate limiting."""
        response = requests.get(url)

        # Check rate limit headers
        if "X-Shopify-Shop-Api-Call-Limit" in response.headers:
            limit = response.headers["X-Shopify-Shop-Api-Call-Limit"]
            current, max_calls = map(int, limit.split("/"))

            # Back off if approaching limit
            if current / max_calls > 0.8:
                time.sleep(self.RATE_LIMIT_DELAY * 2)
            else:
                time.sleep(self.RATE_LIMIT_DELAY)

        return response.json()
```

---

### DRV-016: Retry on Rate Limit

**Statement**: Drivers SHOULD retry on 429 (Too Many Requests).

**Implementation**:
```python
def _fetch_with_retry(self, url: str, max_retries: int = 3) -> dict:
    """Fetch with exponential backoff on rate limit."""
    for attempt in range(max_retries):
        response = requests.get(url)

        if response.status_code == 200:
            return response.json()

        elif response.status_code == 429:
            # Rate limited: exponential backoff
            retry_after = int(response.headers.get("Retry-After", 2 ** attempt))
            time.sleep(retry_after)

        else:
            response.raise_for_status()

    raise RuntimeError(f"Failed after {max_retries} retries")
```

---

## Error Handling

### DRV-017: Error Classification

**Statement**: Drivers SHOULD classify errors for retry logic.

**Categories**:
- `auth` - Authentication failure (no retry)
- `network` - Network issue (retry with backoff)
- `permission` - Authorization failure (no retry)
- `timeout` - Request timeout (retry with backoff)
- `validation` - Input validation error (no retry)
- `unknown` - Uncategorized error (no retry)

**Implementation**:
```python
def _classify_error(self, exception: Exception) -> str:
    """Classify error for retry logic."""
    if isinstance(exception, AuthenticationError):
        return "auth"
    elif isinstance(exception, requests.exceptions.Timeout):
        return "timeout"
    elif isinstance(exception, requests.exceptions.ConnectionError):
        return "network"
    elif isinstance(exception, PermissionError):
        return "permission"
    elif isinstance(exception, ValueError):
        return "validation"
    else:
        return "unknown"
```

---

### DRV-018: Error Messages

**Statement**: Error messages MUST be actionable and NOT contain secrets.

**Correct**:
```python
raise RuntimeError(
    f"Step {step_id}: Failed to connect to mysql://***@localhost/mydb. "
    "Check connection settings in osiris_connections.yaml"
)
```

**Wrong**:
```python
# ❌ Leaks password
raise RuntimeError(f"Failed to connect with password: {password}")

# ❌ Not actionable
raise RuntimeError("Something went wrong")
```

---

## Discovery Mode

### DRV-019: Discovery Implementation

**Statement**: If component declares `capabilities.discover: true`, driver MUST implement `discover()`.

**Signature**:
```python
def discover(self, config: dict, ctx: Any = None) -> dict:
    """Discover available resources.

    Args:
        config: Config with resolved_connection
        ctx: Execution context

    Returns:
        Discovery output matching schema
    """
```

---

### DRV-020: Discovery Output

**Statement**: Discovery output MUST match schema.

**Schema**:
```python
{
    "discovered_at": "2025-09-30T12:00:00.000Z",  # ISO 8601 UTC
    "resources": [
        {
            "name": "customers",
            "type": "table",
            "estimated_row_count": 1000000,
            "fields": [
                {"name": "id", "type": "integer", "nullable": false},
                {"name": "email", "type": "string", "nullable": true}
            ]
        }
    ],
    "fingerprint": "sha256:abc123..."  # SHA-256 hash
}
```

---

### DRV-021: Deterministic Discovery

**Statement**: Discovery output MUST be deterministic (sorted).

**Implementation**:
```python
def discover(self, config: dict, ctx=None) -> dict:
    conn_info = config.get("resolved_connection", {})

    # Query resources
    resources = self._query_resources(conn_info)

    # Sort resources and fields
    resources.sort(key=lambda r: r["name"])
    for resource in resources:
        if "fields" in resource:
            resource["fields"].sort(key=lambda f: f["name"])

    # Build discovery output
    discovery = {
        "discovered_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "resources": resources,
        "fingerprint": None  # Will be computed
    }

    # Compute fingerprint
    discovery_copy = discovery.copy()
    discovery_copy.pop("fingerprint")
    canonical = json.dumps(discovery_copy, sort_keys=True)
    fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
    discovery["fingerprint"] = f"sha256:{fingerprint}"

    return discovery
```

---

## Healthcheck (Doctor)

### DRV-022: Doctor Implementation

**Statement**: If component declares `capabilities.doctor: true`, driver MUST implement `doctor()`.

**Signature**:
```python
def doctor(self, connection: dict, timeout: float = 2.0) -> tuple[bool, dict]:
    """Test connection health.

    Args:
        connection: Resolved connection dict
        timeout: Maximum seconds to wait

    Returns:
        (ok, details) where details = {
            "latency_ms": float | None,
            "category": "auth"|"network"|"permission"|"timeout"|"ok"|"unknown",
            "message": str  # Non-sensitive, redacted
        }
    """
```

---

### DRV-023: Doctor Error Handling

**Statement**: Doctor MUST catch all exceptions and return structured output.

**Implementation**:
```python
def doctor(self, connection: dict, timeout: float = 2.0) -> tuple[bool, dict]:
    try:
        start = time.time()
        client = self._create_client(connection)
        client.ping(timeout=timeout)
        latency = (time.time() - start) * 1000

        return True, {
            "latency_ms": round(latency, 2),
            "category": "ok",
            "message": "Connection successful"
        }

    except AuthenticationError:
        return False, {
            "latency_ms": None,
            "category": "auth",
            "message": "Invalid credentials"
        }

    except PermissionError:
        return False, {
            "latency_ms": None,
            "category": "permission",
            "message": "Access denied"
        }

    except socket.timeout:
        return False, {
            "latency_ms": None,
            "category": "timeout",
            "message": f"Timed out after {timeout}s"
        }

    except (socket.error, ConnectionError) as e:
        return False, {
            "latency_ms": None,
            "category": "network",
            "message": f"Network error: {type(e).__name__}"
        }

    except Exception as e:
        return False, {
            "latency_ms": None,
            "category": "unknown",
            "message": f"Error: {type(e).__name__}"
        }
```

---

## Data Types

### DRV-024: Pandas DataFrame

**Statement**: Extractors and processors SHOULD return pandas.DataFrame.

**Why**: Standard data structure for tabular data, integrates with DuckDB.

**Implementation**:
```python
import pandas as pd

def run(self, *, step_id, config, inputs, ctx):
    # Extract data
    rows = self._fetch_data(config)

    # Convert to DataFrame
    df = pd.DataFrame(rows)

    return {"data": df}
```

---

### DRV-025: Type Inference

**Statement**: Drivers SHOULD infer column types correctly.

**Implementation**:
```python
import pandas as pd

def run(self, *, step_id, config, inputs, ctx):
    rows = self._fetch_data(config)
    df = pd.DataFrame(rows)

    # Infer types
    df["id"] = df["id"].astype("int64")
    df["created_at"] = pd.to_datetime(df["created_at"])
    df["amount"] = df["amount"].astype("float64")

    return {"data": df}
```

---

## Testing Hooks

### DRV-026: Dry Run Support

**Statement**: Drivers SHOULD support dry-run mode for testing.

**Implementation**:
```python
def run(self, *, step_id, config, inputs, ctx):
    dry_run = config.get("dry_run", False)

    if dry_run:
        # Return sample data
        sample_df = pd.DataFrame({
            "id": [1, 2, 3],
            "email": ["user1@example.com", "user2@example.com", "user3@example.com"]
        })
        return {"data": sample_df}

    # Normal execution
    return {"data": self._extract_data(config)}
```

---

### DRV-027: Mockable Dependencies

**Statement**: Drivers SHOULD make external dependencies mockable.

**Pattern**:
```python
class ShopifyExtractorDriver:
    def __init__(self, client_factory=None):
        """Initialize driver with optional client factory."""
        self._client_factory = client_factory or self._default_client_factory

    def _default_client_factory(self, connection: dict):
        """Default client factory."""
        return shopify.GraphQL(...)

    def run(self, *, step_id, config, inputs, ctx):
        client = self._client_factory(config["resolved_connection"])
        # Use client...
```

**Test Usage**:
```python
# Mock client for testing
mock_client = MagicMock()
driver = ShopifyExtractorDriver(client_factory=lambda conn: mock_client)
```

---

## Performance

### DRV-028: Batch Operations

**Statement**: Writers SHOULD use batch operations for efficiency.

**Anti-Pattern**:
```python
# ❌ Slow: Insert row-by-row
for row in df.itertuples():
    cursor.execute("INSERT INTO users VALUES (?, ?)", (row.id, row.email))
```

**Correct Pattern**:
```python
# ✓ Fast: Batch insert
batch_size = 1000
for i in range(0, len(df), batch_size):
    batch = df.iloc[i:i+batch_size]
    cursor.executemany("INSERT INTO users VALUES (?, ?)", batch.values.tolist())
```

---

### DRV-029: Streaming

**Statement**: Drivers SHOULD stream large datasets to avoid memory exhaustion.

**Implementation**:
```python
def run(self, *, step_id, config, inputs, ctx):
    chunk_size = config.get("chunk_size", 10000)

    # Stream data in chunks
    for chunk in self._stream_data(config, chunk_size):
        yield {"data": chunk}  # Generator pattern
```

---

## Common Driver Patterns

### Extractor Template
```python
class MyExtractorDriver:
    def run(self, *, step_id, config, inputs, ctx):
        # 1. Validate config
        conn_info = config.get("resolved_connection", {})
        resource = config["resource"]

        # 2. Extract data
        df = self._extract_data(conn_info, resource)

        # 3. Emit metrics
        if ctx and hasattr(ctx, "log_metric"):
            ctx.log_metric("rows_read", len(df), unit="rows", tags={"step": step_id})

        return {"data": df}

    def discover(self, config: dict, ctx=None) -> dict:
        """Discover available resources."""
        # Implementation...

    def doctor(self, connection: dict, timeout: float = 2.0) -> tuple[bool, dict]:
        """Test connection health."""
        # Implementation...
```

### Writer Template
```python
class MyWriterDriver:
    def run(self, *, step_id, config, inputs, ctx):
        # 1. Validate input
        input_step = config["input_step"]
        df = inputs[input_step]["data"]

        # 2. Write data
        conn_info = config.get("resolved_connection", {})
        rows_written = self._write_data(conn_info, df)

        # 3. Emit metrics
        if ctx and hasattr(ctx, "log_metric"):
            ctx.log_metric("rows_written", rows_written, unit="rows", tags={"step": step_id})

        return {"data": {"rows_written": rows_written}}
```

---

## See Also

- **Overview**: `overview.md`
- **Component Contract**: `components.md`
- **Connector Contract**: `connectors.md`
- **Discovery Contract**: `../checklists/discovery_contract.md`
- **Metrics Contract**: `../checklists/metrics_events_contract.md`
- **Full Checklist**: `../checklists/COMPONENT_AI_CHECKLIST.md`
