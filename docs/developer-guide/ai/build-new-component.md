# Osiris Component Builder: AI Prompt Template

**Purpose**: One-shot AI prompt template for generating production-ready Osiris components.

**Usage**: Copy this template, replace placeholders (`<COMPONENT_NAME>`, `<API_OR_RESOURCE>`, `<connection_fields>`), and provide to an LLM like Claude.

---

## Goal

Build a new `<COMPONENT_NAME>` component that extracts data from `<API_OR_RESOURCE>`. The component must be a complete, production-ready Osiris extractor with spec, driver, tests, examples, and full compliance with Osiris contracts.

---

## Inputs (Fill These)

**Component Metadata:**
- `<COMPONENT_NAME>`: Component name in `family.type` format (e.g., `shopify.extractor`, `stripe.extractor`)
- `<API_OR_RESOURCE>`: Target API or data source (e.g., Shopify REST API, Stripe API)
- `<connection_fields>`: Required connection fields (e.g., `shop_domain`, `access_token`, `api_version`)

**API Details:**
- Authentication method (API key, OAuth, Basic Auth)
- Base URL or endpoint pattern
- Pagination strategy (cursor, offset, page number)
- Rate limiting (requests per second, retry-after headers)
- Available resources/endpoints to extract from

**Data Schema:**
- Expected fields and types from API responses
- Nested objects or arrays requiring flattening
- Resource types available for discovery mode

---

## MUST Requirements (Osiris Contracts)

### Spec Validation (SPEC-*)
**MUST** validate spec against [`docs/reference/components-spec.md`](../../reference/components-spec.md):
- Name follows `family.type` pattern (SPEC-001)
- Version is valid SemVer (SPEC-002)
- Modes include `extract` and `discover` (SPEC-003, MODES-001)
- Capabilities declare `discover: true` and `doctor: true` (SPEC-004)
- ConfigSchema is valid JSON Schema Draft 7 (SPEC-005)
- Secrets declared using JSON Pointer notation (SPEC-006)

### Discovery Mode (DISC-*)
**MUST** comply with [`checklists/discovery_contract.md`](checklists/discovery_contract.md):
- Implement `discover()` method returning deterministic output (DISC-001, DISC-002)
- Include SHA-256 fingerprint of discovery output (DISC-003)
- Sort resources and fields alphabetically (DISC-002)
- Match schema in [`schemas/discovery_output.schema.json`](schemas/discovery_output.schema.json) (DISC-001)
- Use ISO 8601 UTC timestamps (DISC-002)

### Connection & Healthcheck (CONN-*, DOC-*)
**MUST** comply with [`checklists/connections_doctor_contract.md`](checklists/connections_doctor_contract.md):
- Read from `config["resolved_connection"]`, NOT environment (CONN-001)
- Validate required connection fields (CONN-002)
- Implement `doctor()` method with standard signature (DOC-001)
- Use standard error categories: `auth`, `network`, `permission`, `timeout`, `ok`, `unknown` (DOC-002)
- Return redaction-safe output (no secrets in messages) (DOC-003)

### Driver Protocol (DRV-*)
**MUST** comply with [`llms/drivers.md`](llms/drivers.md):
- Use keyword-only arguments in `run()` signature (DRV-001)
- Return dict with `data` key containing pandas DataFrame (DRV-002)
- Raise exceptions for unrecoverable errors (DRV-003)
- Validate required config fields (DRV-005)

### Telemetry (MET-*)
**MUST** comply with [`checklists/metrics_events_contract.md`](checklists/metrics_events_contract.md):
- Emit `rows_read` metric with unit `rows` (MET-001)
- Specify unit for all metrics (MET-002)
- Include `step` tag in all metrics (MET-003)

### Component Registry (AI-*)
**MUST** comply with [`checklists/COMPONENT_AI_CHECKLIST.md`](checklists/COMPONENT_AI_CHECKLIST.md):
- Pass basic validation (required fields, JSON Schema) (AI-001)
- Pass enhanced validation (driver exists, examples runnable) (AI-002)
- Include at least one runnable example (AI-003)
- Register component in Registry (AI-004)

---

## SHOULD Guidelines (Best Practices)

### Code Patterns
**SHOULD** follow patterns in [`../human/examples/shopify.extractor/`](../human/examples/shopify.extractor/):
- Pagination with cursor/offset tracking
- Rate limiting with exponential backoff
- Error classification (auth, network, timeout, validation)
- Connection pooling for efficiency
- Dry-run mode for testing

### Documentation
**SHOULD** document:
- Rate limit handling strategy
- Retry logic with backoff parameters
- Healthcheck implementation details
- Discovery caching behavior
- Example connection configurations

### Testing
**SHOULD** include tests for:
- Schema validation
- Discovery determinism (run twice, compare outputs)
- Connection resolution and validation
- Error handling (auth failures, timeouts, network errors)
- Pagination (large datasets, edge cases)
- Retry logic with mocked failures

---

## Required Artifacts

**MUST** output the following files:

### 1. Component Spec
**Path**: `components/<COMPONENT_NAME>/spec.yaml`

**Contents**:
```yaml
name: <COMPONENT_NAME>
version: 1.0.0
description: Extract data from <API_OR_RESOURCE>
modes: [extract, discover]
capabilities:
  discover: true
  doctor: true
  bulkOperations: false  # Set true if API supports bulk queries
configSchema:
  type: object
  required: [connection, resource]
  properties:
    connection:
      type: string
      pattern: "^@[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$"
      description: Connection alias (@family.alias)
    resource:
      type: string
      enum: [<list_of_available_resources>]
      description: Resource to extract
    limit:
      type: integer
      minimum: 1
      maximum: 10000
      default: 1000
      description: Max records per request
secrets:
  - /connection/<secret_field_1>
  - /connection/<secret_field_2>
examples:
  - name: Extract recent records
    config:
      connection: "@<family>.default"
      resource: <primary_resource>
      limit: 1000
x-runtime:
  driver: osiris.drivers.<component_name>_driver.<DriverClass>
```

**Include inline comments** referencing rule IDs (SPEC-001, CONN-001, etc.).

---

### 2. Driver Implementation
**Path**: `osiris/connectors/<COMPONENT_NAME>/driver.py`

**Required Methods**:
```python
import pandas as pd
from datetime import datetime, timezone
import hashlib
import json

class <DriverClass>:
    """Driver for <API_OR_RESOURCE> extraction."""

    __version__ = "1.0.0"  # Must match spec version

    def run(self, *, step_id: str, config: dict, inputs: dict | None = None, ctx: Any = None) -> dict:
        """
        Extract data from <API_OR_RESOURCE>.

        Implements: DRV-001 (keyword-only args), DRV-002 (return structure)
        """
        # CONN-001: Read from resolved_connection
        conn_info = config.get("resolved_connection", {})
        if not conn_info:
            raise ValueError(f"Step {step_id}: 'resolved_connection' is required")

        # CONN-002: Validate required fields
        required = [<list_of_required_fields>]
        for field in required:
            if not conn_info.get(field):
                raise ValueError(f"Step {step_id}: connection field '{field}' is required")

        # DRV-005: Validate config
        resource = config.get("resource")
        if not resource:
            raise ValueError(f"Step {step_id}: config field 'resource' is required")

        # Extract data with pagination
        df = self._extract_paginated(conn_info, resource, config, ctx)

        # MET-001, MET-002, MET-003: Emit metric
        if ctx and hasattr(ctx, "log_metric"):
            ctx.log_metric("rows_read", len(df), unit="rows", tags={"step": step_id})

        # DRV-002: Return DataFrame
        return {"data": df}

    def discover(self, config: dict, ctx: Any = None) -> dict:
        """
        Discover available resources.

        Implements: DISC-001, DISC-002, DISC-003
        """
        conn_info = config.get("resolved_connection", {})

        # Query available resources
        resources = self._query_resources(conn_info)

        # DISC-002: Sort alphabetically
        resources.sort(key=lambda r: r["name"])
        for resource in resources:
            if "fields" in resource:
                resource["fields"].sort(key=lambda f: f["name"])

        # DISC-001: Build discovery output
        discovery = {
            "discovered_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "resources": resources,
            "fingerprint": None  # Will be computed
        }

        # DISC-003: Compute SHA-256 fingerprint
        discovery_copy = discovery.copy()
        discovery_copy.pop("fingerprint")
        canonical = json.dumps(discovery_copy, sort_keys=True)
        fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
        discovery["fingerprint"] = f"sha256:{fingerprint}"

        return discovery

    def doctor(self, connection: dict, timeout: float = 2.0) -> tuple[bool, dict]:
        """
        Test connection health.

        Implements: DOC-001, DOC-002, DOC-003
        """
        import time

        try:
            start = time.time()
            client = self._create_client(connection)

            # Perform health check (ping, list resources, etc.)
            self._health_check(client, timeout)

            latency_ms = (time.time() - start) * 1000

            # DOC-002: Use standard category
            return True, {
                "latency_ms": round(latency_ms, 2),
                "category": "ok",
                "message": "Connection successful"
            }

        except AuthenticationError:
            # DOC-002: Auth category
            return False, {
                "latency_ms": None,
                "category": "auth",
                "message": "Invalid credentials"  # DOC-003: No secrets
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

    def _extract_paginated(self, conn_info: dict, resource: str, config: dict, ctx) -> pd.DataFrame:
        """Extract data with pagination."""
        all_data = []
        cursor = None
        page_size = config.get("limit", 1000)

        while True:
            # Fetch page
            page_data, next_cursor = self._fetch_page(conn_info, resource, cursor, page_size)

            if not page_data:
                break

            all_data.extend(page_data)

            # Log progress
            if ctx and hasattr(ctx, "log_info"):
                ctx.log_info(f"Fetched {len(all_data)} rows so far...")

            cursor = next_cursor
            if not cursor:
                break

        return pd.DataFrame(all_data)

    def _fetch_page(self, conn_info: dict, resource: str, cursor: str | None, page_size: int):
        """Fetch single page with rate limiting."""
        # Implementation with rate limiting, retries, error handling
        pass

    def _query_resources(self, conn_info: dict) -> list[dict]:
        """Query available resources for discovery."""
        # Implementation
        pass

    def _create_client(self, connection: dict):
        """Create API client from connection info."""
        # Implementation
        pass

    def _health_check(self, client, timeout: float):
        """Perform health check on client."""
        # Implementation
        pass
```

---

### 3. Unit Tests
**Path**: `tests/components/test_<component_name>.py`

**Required Test Cases**:
```python
import pytest
from osiris.connectors.<component_name>.driver import <DriverClass>

class Test<DriverClass>:
    """Unit tests for <COMPONENT_NAME> driver."""

    @pytest.fixture
    def driver(self):
        return <DriverClass>()

    @pytest.fixture
    def config(self):
        return {
            "resource": "primary_resource",
            "resolved_connection": {
                <connection_fields>: "test_value"  # pragma: allowlist secret
            }
        }

    def test_run_with_valid_config(self, driver, config):
        """Test driver execution with valid config."""
        result = driver.run(step_id="test", config=config, inputs={}, ctx=None)
        assert "data" in result
        assert isinstance(result["data"], pd.DataFrame)

    def test_run_with_missing_connection_raises_error(self, driver):
        """Test driver raises error when connection missing."""
        with pytest.raises(ValueError, match="resolved_connection"):
            driver.run(step_id="test", config={"resource": "test"}, inputs={}, ctx=None)

    def test_discover_returns_deterministic_output(self, driver, config):
        """Test discovery output is deterministic."""
        result1 = driver.discover(config)
        result2 = driver.discover(config)

        assert result1["fingerprint"] == result2["fingerprint"]
        assert result1["resources"] == result2["resources"]

    def test_doctor_with_valid_connection(self, driver, config):
        """Test healthcheck with valid connection."""
        ok, details = driver.doctor(config["resolved_connection"])

        assert ok is True
        assert details["category"] == "ok"
        assert "latency_ms" in details
```

---

### 4. Discovery Tests
**Path**: `tests/connectors/test_<component_name>_discovery.py`

**Required Test Cases**:
```python
def test_discovery_output_matches_schema(driver, config):
    """Test discovery output validates against JSON schema."""
    result = driver.discover(config)

    # Load schema
    with open("docs/developer-guide/ai/schemas/discovery_output.schema.json") as f:
        schema = json.load(f)

    # Validate
    jsonschema.validate(result, schema)

def test_discovery_is_deterministic(driver, config):
    """Test running discovery twice produces identical output."""
    result1 = driver.discover(config)
    result2 = driver.discover(config)

    assert json.dumps(result1, sort_keys=True) == json.dumps(result2, sort_keys=True)

def test_discovery_resources_sorted_alphabetically(driver, config):
    """Test resources are sorted by name."""
    result = driver.discover(config)

    resource_names = [r["name"] for r in result["resources"]]
    assert resource_names == sorted(resource_names)

def test_discovery_fields_sorted_alphabetically(driver, config):
    """Test fields within each resource are sorted."""
    result = driver.discover(config)

    for resource in result["resources"]:
        if "fields" in resource:
            field_names = [f["name"] for f in resource["fields"]]
            assert field_names == sorted(field_names)
```

---

### 5. Integration Tests
**Path**: `tests/integration/test_<component_name>_pipeline.py`

**Required Test Cases**:
```python
@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("API_KEY"), reason="API_KEY not set")
def test_full_pipeline_with_real_api(tmp_path):
    """Integration test with real API."""
    # Create pipeline manifest
    manifest = {
        "steps": [
            {
                "id": "extract",
                "driver": "<COMPONENT_NAME>",
                "config": {
                    "connection": "@<family>.default",
                    "resource": "primary_resource"
                }
            }
        ]
    }

    # Execute pipeline
    runner = Runner(manifest)
    result = runner.execute()

    assert result["status"] == "success"
    assert len(result["artifacts"]) > 0
```

---

### 6. Example Scaffold
**Path**: `docs/developer-guide/human/examples/<COMPONENT_NAME>/`

**Required Files**:

#### `spec.yaml`
Production-quality spec with inline comments (see artifact #1)

#### `driver_skeleton.py`
Complete driver implementation (see artifact #2)

#### `connections.example.yaml`
```yaml
version: 1
connections:
  <family>:
    default:
      <connection_field_1>: ${ENV_VAR_1}
      <connection_field_2>: ${ENV_VAR_2}
      default: true

    production:
      <connection_field_1>: ${PROD_ENV_VAR_1}
      <connection_field_2>: ${PROD_ENV_VAR_2}
```

#### `discovery.sample.json`
Representative discovery output matching schema

#### `e2e_manifest.yaml`
```yaml
steps:
  - id: extract_data
    driver: <COMPONENT_NAME>
    config:
      connection: "@<family>.default"
      resource: primary_resource
      limit: 1000

  - id: write_csv
    driver: csv.writer
    config:
      input_step: extract_data
      output_path: output/data.csv
```

---

## Process (Step-by-Step)

### Step 1: Draft spec.yaml
1. Create `components/<COMPONENT_NAME>/spec.yaml`
2. Add inline comments referencing rule IDs:
   - `# SPEC-001: Name follows family.type pattern`
   - `# CONN-001: Connection uses resolved_connection`
   - `# DISC-001: Discovery mode declared`
3. Validate: `osiris components validate <COMPONENT_NAME> --level basic`

### Step 2: Implement driver.py
1. Create `osiris/connectors/<COMPONENT_NAME>/driver.py`
2. Implement required methods: `run()`, `discover()`, `doctor()`
3. Add inline comments referencing contracts:
   - `# DRV-001: Keyword-only args`
   - `# MET-001: Emit rows_read metric`
4. Handle pagination, rate limiting, retries
5. Test manually: `python -c "from osiris.connectors... import Driver; Driver().run(...)"`

### Step 3: Add comprehensive tests
1. Create unit tests (`tests/components/test_<name>.py`)
2. Create discovery tests (`tests/connectors/test_<name>_discovery.py`)
3. Create integration tests (`tests/integration/test_<name>_pipeline.py`)
4. Cover edge cases:
   - Empty results
   - Pagination boundaries
   - API errors (401, 403, 429, 500, timeout)
   - Network failures
   - Malformed responses
5. Run: `pytest tests/ -v -k <component_name>`

### Step 4: Create example scaffold
1. Create `docs/developer-guide/human/examples/<COMPONENT_NAME>/`
2. Add all 5 files (spec, driver, connections, discovery, manifest)
3. Document rate-limit handling, retries, healthcheck
4. Add usage instructions in comments

### Step 5: Validate compliance
Run all validation commands:

```bash
# Spec validation
osiris components validate <COMPONENT_NAME> --level strict --verbose

# Connection healthcheck
osiris connections doctor --family <family> --alias default --json

# Discovery determinism
osiris components discover <COMPONENT_NAME> --connection @<family>.default --out disc1.json
osiris components discover <COMPONENT_NAME> --connection @<family>.default --out disc2.json
diff disc1.json disc2.json  # Should be identical

# Test suite
pytest tests/ -v -k <component_name>

# Full pipeline
cd testing_env
python ../osiris.py compile ../docs/developer-guide/human/examples/<COMPONENT_NAME>/e2e_manifest.yaml
python ../osiris.py run --last-compile --verbose
```

---

## Expected Output

### File Tree
```
osiris_pipeline/
├── components/
│   └── <COMPONENT_NAME>/
│       └── spec.yaml                          [NEW] Complete spec with inline comments
│
├── osiris/
│   └── connectors/
│       └── <COMPONENT_NAME>/
│           └── driver.py                      [NEW] Complete driver implementation
│
├── tests/
│   ├── components/
│   │   └── test_<component_name>.py           [NEW] Unit tests
│   ├── connectors/
│   │   └── test_<component_name>_discovery.py [NEW] Discovery tests
│   └── integration/
│       └── test_<component_name>_pipeline.py  [NEW] Integration tests
│
└── docs/developer-guide/human/examples/
    └── <COMPONENT_NAME>/
        ├── spec.yaml                          [NEW] Production spec
        ├── driver_skeleton.py                 [NEW] Complete implementation
        ├── connections.example.yaml           [NEW] Connection examples
        ├── discovery.sample.json              [NEW] Sample discovery output
        └── e2e_manifest.yaml                  [NEW] End-to-end pipeline
```

### CLI Command Outputs (Machine-Parsable)

#### Component Validation
```bash
$ osiris components validate <COMPONENT_NAME> --level strict --json
```
```json
{
  "component": "<COMPONENT_NAME>",
  "is_valid": true,
  "checks": {
    "spec_format": "pass",
    "schema_valid": "pass",
    "secrets_declared": "pass",  # pragma: allowlist secret
    "driver_exists": "pass",
    "examples_valid": "pass"
  },
  "errors": []
}
```

#### Connection Doctor
```bash
$ osiris connections doctor --family <family> --alias default --json
```
```json
{
  "family": "<family>",
  "alias": "default",
  "ok": true,
  "latency_ms": 125.5,
  "category": "ok",
  "message": "Connection successful"
}
```

#### Discovery Output
```bash
$ osiris components discover <COMPONENT_NAME> --connection @<family>.default --json
```
```json
{
  "discovered_at": "2025-09-30T12:00:00.000Z",
  "resources": [
    {
      "name": "resource_1",
      "type": "table",
      "estimated_row_count": 1000000,
      "fields": [
        {"name": "id", "type": "integer", "nullable": false},
        {"name": "name", "type": "string", "nullable": true}
      ]
    }
  ],
  "fingerprint": "sha256:abc123..."
}
```

#### Test Results
```bash
$ pytest tests/ -v -k <component_name>
```
```
tests/components/test_<component_name>.py::test_run_with_valid_config PASSED
tests/components/test_<component_name>.py::test_discover_deterministic PASSED
tests/connectors/test_<component_name>_discovery.py::test_schema_valid PASSED
tests/integration/test_<component_name>_pipeline.py::test_full_pipeline PASSED

========== 4 passed in 2.5s ==========
```

---

## Validation Checklist

Before submitting, verify:

- [ ] Spec validates: `osiris components validate <NAME> --level strict`
- [ ] All tests pass: `pytest tests/ -k <NAME>`
- [ ] Discovery is deterministic (run twice, diff outputs)
- [ ] Connection doctor works: `osiris connections doctor --json`
- [ ] Example pipeline runs: `osiris run e2e_manifest.yaml`
- [ ] No secrets in logs/outputs (check artifacts)
- [ ] Code follows patterns in `human/examples/shopify.extractor/`
- [ ] All MUST rules from checklists are satisfied
- [ ] Inline comments reference rule IDs (SPEC-001, DRV-001, etc.)

---

## See Also

- **Human Guide**: [`../human/BUILD_A_COMPONENT.md`](../human/BUILD_A_COMPONENT.md)
- **AI Checklist**: [`checklists/COMPONENT_AI_CHECKLIST.md`](checklists/COMPONENT_AI_CHECKLIST.md)
- **LLM Contracts**: [`llms/overview.md`](llms/overview.md)
- **Reference Example**: [`../human/examples/shopify.extractor/`](../human/examples/shopify.extractor/)
