# Code Templates for Osiris Components

Quick-reference templates for common component patterns.

## Minimal spec.yaml Template

```yaml
name: "provider.component_type"
version: "1.0.0"
description: "Brief description of what this component does"
author: "Your Name"
license: "Apache-2.0"

modes:
  - extract  # or: write, transform, discover

capabilities:
  discover: true
  adHocAnalytics: false
  inMemoryMove: false
  streaming: false
  bulkOperations: true
  transactions: false
  partitioning: false
  customTransforms: false

configSchema:
  type: object
  properties:
    # Your config fields here
    table:
      type: string
      description: "Table or resource to extract"
  required: ["table"]

connectionSchema:
  type: object
  properties:
    host:
      type: string
      description: "API or database host"
    api_key:
      type: string
      description: "Authentication key"
  required: ["host", "api_key"]

secrets:
  - "/api_key"

x-connection-fields:
  - field: host
    override: allowed
  - field: api_key
    override: forbidden

examples:
  - name: "Basic usage"
    config:
      table: "events"
    connection:
      host: "https://api.example.com"
      api_key: "$API_KEY"
```

## Minimal Driver Template

```python
"""Driver for provider.component_type component."""
from typing import Any
import pandas as pd


class ProviderComponentDriver:
    """Driver implementation."""

    def run(self, *, step_id: str, config: dict, inputs: dict | None = None, ctx: Any = None) -> dict:
        """Execute operation. CRITICAL: Use keyword-only params with *."""
        try:
            # 1. Get and validate connection
            connection = config.get("resolved_connection", {})
            if not connection:
                raise ValueError("No connection configuration provided")

            for field in ["api_key"]:
                if field not in connection:
                    raise ValueError(f"Missing required field: {field}")

            # 2. Perform operation
            df = self._perform_operation(connection, config)

            # 3. Emit metrics
            if ctx and hasattr(ctx, "log_metric"):
                ctx.log_metric(
                    name="rows_read",  # or rows_written, rows_processed
                    value=len(df),
                    unit="rows",
                    tags={"step": step_id}
                )

            # 4. Return result
            return {"df": df}

        finally:
            # Cleanup resources
            pass

    def _perform_operation(self, connection: dict, config: dict) -> pd.DataFrame:
        """Implement your logic here."""
        # Your implementation
        return pd.DataFrame()

    def discover(self, connection: dict, timeout: float = 10.0) -> dict:
        """Discover available resources."""
        import hashlib
        import json
        from datetime import datetime

        resources = []  # Your discovery logic

        # CRITICAL: Sort for determinism
        resources = sorted(resources, key=lambda x: x["name"])

        # Calculate fingerprint
        content = json.dumps(resources, sort_keys=True)
        fingerprint = hashlib.sha256(content.encode()).hexdigest()

        return {
            "discovered_at": datetime.utcnow().isoformat() + "Z",
            "resources": resources,
            "fingerprint": fingerprint
        }

    def doctor(self, connection: dict, timeout: float = 2.0) -> tuple[bool, dict]:
        """Health check."""
        import time

        start = time.time()
        try:
            # Test connection
            # Your health check logic
            latency_ms = (time.time() - start) * 1000

            return True, {
                "status": "ok",
                "latency_ms": latency_ms,
                "message": "Connection successful"
            }
        except Exception as e:
            # Never leak secrets
            return False, {
                "status": "unknown",
                "message": str(e).replace(connection.get("api_key", ""), "***")
            }
```

## __init__.py Template

```python
"""Component package."""
from pathlib import Path
import yaml


def load_spec():
    """Load component specification."""
    spec_path = Path(__file__).parent / "spec.yaml"
    with open(spec_path, "r") as f:
        return yaml.safe_load(f)
```

## pyproject.toml Template

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "osiris-your-component"
version = "1.0.0"
description = "Your component description"
authors = [{name = "Your Name", email = "you@example.com"}]
license = {text = "Apache-2.0"}
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "osiris>=0.5.4",
    "pandas>=2.0.0",
    # Add your dependencies
]

[project.optional-dependencies]
test = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0"
]

[project.entry-points."osiris.components"]
your_component = "your_package:load_spec"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
"*" = ["*.yaml"]
```

## Common Patterns

### REST API Extractor

```python
def _extract_data(self, connection: dict, config: dict) -> pd.DataFrame:
    """Extract data from REST API."""
    import requests

    url = f"{connection['host']}/api/{config['endpoint']}"
    headers = {"Authorization": f"Bearer {connection['api_key']}"}
    params = {"limit": config.get("limit", 1000)}

    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()

    data = response.json()
    return pd.DataFrame(data.get("results", []))
```

### REST API with Pagination (Cursor)

```python
def _extract_with_pagination(self, connection: dict, config: dict) -> pd.DataFrame:
    """Extract data with cursor pagination."""
    import requests

    all_data = []
    next_cursor = None

    while True:
        params = {"limit": 100}
        if next_cursor:
            params["cursor"] = next_cursor

        response = requests.get(
            f"{connection['host']}/api/{config['endpoint']}",
            headers={"Authorization": f"Bearer {connection['api_key']}"},
            params=params
        )
        response.raise_for_status()

        data = response.json()
        all_data.extend(data["results"])

        next_cursor = data.get("next_cursor")
        if not next_cursor or len(all_data) >= config.get("limit", float("inf")):
            break

    return pd.DataFrame(all_data)
```

### REST API with Pagination (Offset)

```python
def _extract_with_offset(self, connection: dict, config: dict) -> pd.DataFrame:
    """Extract data with offset pagination."""
    import requests

    all_data = []
    offset = 0
    page_size = 100

    while True:
        response = requests.get(
            f"{connection['host']}/api/{config['endpoint']}",
            headers={"Authorization": f"Bearer {connection['api_key']}"},
            params={"limit": page_size, "offset": offset}
        )
        response.raise_for_status()

        data = response.json()
        results = data.get("results", [])

        if not results:
            break

        all_data.extend(results)
        offset += page_size

        if len(all_data) >= config.get("limit", float("inf")):
            break

    return pd.DataFrame(all_data)
```

### Database Extractor (SQL)

```python
def _extract_from_database(self, connection: dict, config: dict) -> pd.DataFrame:
    """Extract from SQL database."""
    from sqlalchemy import create_engine
    import pandas as pd

    # Build connection string
    conn_string = (
        f"{connection['dialect']}://{connection['user']}:{connection['password']}"
        f"@{connection['host']}:{connection.get('port', 5432)}"
        f"/{connection['database']}"
    )

    engine = create_engine(conn_string)

    # Execute query or read table
    if config.get("query"):
        df = pd.read_sql_query(config["query"], engine)
    else:
        df = pd.read_sql_table(config["table"], engine)

    return df
```

### Database Writer

```python
def _write_to_database(self, connection: dict, config: dict, df: pd.DataFrame) -> int:
    """Write to SQL database."""
    from sqlalchemy import create_engine

    conn_string = (
        f"{connection['dialect']}://{connection['user']}:{connection['password']}"
        f"@{connection['host']}:{connection.get('port', 5432)}"
        f"/{connection['database']}"
    )

    engine = create_engine(conn_string)

    rows = df.to_sql(
        config["table"],
        engine,
        if_exists=config.get("mode", "append"),  # append, replace, fail
        index=False
    )

    return rows
```

### CSV Writer

```python
def _write_csv(self, config: dict, df: pd.DataFrame, ctx: Any = None) -> dict:
    """Write DataFrame to CSV."""
    from pathlib import Path

    # Use ctx.base_path for E2B compatibility
    if ctx and hasattr(ctx, "base_path"):
        output_dir = Path(ctx.base_path) / "output"
    else:
        output_dir = Path("output")

    output_dir.mkdir(parents=True, exist_ok=True)

    file_path = output_dir / config["filename"]
    df.to_csv(file_path, index=False)

    return {"file_path": str(file_path), "rows_written": len(df)}
```

### GraphQL Query

```python
def _query_graphql(self, connection: dict, config: dict) -> pd.DataFrame:
    """Query GraphQL API."""
    import requests

    query = config["query"]
    variables = config.get("variables", {})

    response = requests.post(
        f"{connection['host']}/graphql",
        json={"query": query, "variables": variables},
        headers={
            "Authorization": f"Bearer {connection['api_key']}",
            "Content-Type": "application/json"
        }
    )
    response.raise_for_status()

    data = response.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")

    # Extract data from GraphQL response
    results = data["data"][config.get("result_key", "results")]
    return pd.DataFrame(results)
```

### Error Mapping to Standard Categories

```python
ERROR_MAPPING = {
    401: "auth",
    403: "permission",
    404: "not_found",
    408: "timeout",
    429: "rate_limit",
    500: "server_error",
    503: "unavailable"
}

def doctor(self, connection: dict, timeout: float = 2.0) -> tuple[bool, dict]:
    """Health check with proper error mapping."""
    import requests

    try:
        response = requests.get(
            f"{connection['host']}/health",
            headers={"Authorization": f"Bearer {connection['api_key']}"},
            timeout=timeout
        )

        if response.status_code == 200:
            return True, {"status": "ok", "message": "Connection successful"}
        else:
            status = ERROR_MAPPING.get(response.status_code, "unknown")
            return False, {
                "status": status,
                "message": f"HTTP {response.status_code}"
            }

    except requests.exceptions.Timeout:
        return False, {"status": "timeout", "message": f"Timeout after {timeout}s"}
    except requests.exceptions.ConnectionError:
        return False, {"status": "network", "message": "Cannot connect"}
    except Exception as e:
        # Never leak secrets
        message = str(e).replace(connection.get("api_key", ""), "***")
        return False, {"status": "unknown", "message": message}
```

### Secret Masking

```python
def _mask_secrets(self, message: str, connection: dict) -> str:
    """Mask all secrets in error messages."""
    masked = message

    # Mask all potential secret fields
    for field in ["api_key", "password", "token", "secret"]:
        if field in connection and connection[field]:
            masked = masked.replace(connection[field], "***")

    return masked
```

### Rate Limiting

```python
def _fetch_with_rate_limit(self, connection: dict, config: dict) -> pd.DataFrame:
    """Fetch data with rate limiting."""
    import time
    import requests

    rate_limit = config.get("rate_limit", 10)  # requests per second
    delay = 1.0 / rate_limit

    all_data = []

    for page in range(config.get("pages", 1)):
        time.sleep(delay)  # Rate limiting

        response = requests.get(
            f"{connection['host']}/api/data",
            headers={"Authorization": f"Bearer {connection['api_key']}"},
            params={"page": page}
        )
        response.raise_for_status()

        all_data.extend(response.json()["results"])

    return pd.DataFrame(all_data)
```

## Test Templates

### Basic Validation Test

```python
def test_component_validation():
    """Test component passes all validation."""
    from your_component import load_spec
    from your_component.driver import YourDriver
    import inspect

    # Test spec loads
    spec = load_spec()
    assert "name" in spec
    assert "version" in spec
    assert "modes" in spec

    # Test driver signature
    driver = YourDriver()
    sig = inspect.signature(driver.run)
    params = list(sig.parameters.keys())
    assert params == ["step_id", "config", "inputs", "ctx"]

    # All params must be keyword-only
    for param in sig.parameters.values():
        assert param.kind == inspect.Parameter.KEYWORD_ONLY
```

### Discovery Determinism Test

```python
def test_discovery_determinism():
    """Test discovery is deterministic."""
    from your_component.driver import YourDriver

    driver = YourDriver()
    connection = {"api_key": "test", "host": "test"}  # pragma: allowlist secret

    result1 = driver.discover(connection)
    result2 = driver.discover(connection)

    assert result1["fingerprint"] == result2["fingerprint"]
    assert result1["resources"] == result2["resources"]
```

### E2B Compatibility Test

```python
def test_e2b_compatibility():
    """Test E2B compatibility."""
    from pathlib import Path

    src_dir = Path(__file__).parent.parent / "src"

    for py_file in src_dir.rglob("*.py"):
        content = py_file.read_text()

        # No hardcoded paths
        assert "Path.home()" not in content, f"Found Path.home() in {py_file}"
        assert "/Users/" not in content, f"Found hardcoded path in {py_file}"

        # No direct env access (except with noqa)
        if "os.environ" in content:
            assert "# noqa" in content or "# pragma" in content
```