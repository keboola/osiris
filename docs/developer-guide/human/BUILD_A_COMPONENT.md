# Building an Osiris Component: Step-by-Step Guide

**Purpose**: Practical walkthrough for creating a new Osiris component from scratch.

**Prerequisites**: Read [`CONCEPTS.md`](CONCEPTS.md) to understand Component, Driver, Connector, Registry, and Runner.

---

## Overview

Building a component involves 9 steps:

1. **Understand concepts** - Core abstractions
2. **Draft spec.yaml** - Component specification
3. **Implement driver** - Runtime execution logic
4. **Define connections** - Connection resolution and healthcheck
5. **Emit telemetry** - Logs, events, and metrics
6. **Register component** - Make it discoverable
7. **Validate locally** - Test the component
8. **Write tests** - Unit and integration tests
9. **Submit PR** - Quality checklist

---

## Step 1: Understand Concepts

Before building, understand these core concepts:

- **Component** (`spec.yaml`): Declarative specification of what your component does
- **Driver** (Python class): Imperative implementation of how it executes
- **Connector** (optional): Reusable connection management shared across components
- **Registry**: Catalog that validates and serves component metadata
- **Runner**: Orchestrator that executes your driver

**Read**: [`CONCEPTS.md`](CONCEPTS.md) for detailed explanations with diagrams.

**Key Principle**: Component spec = What, Driver = How, Connector = Where

---

## Step 2: Draft spec.yaml

### Create Component Directory

```bash
mkdir -p components/mycomponent
cd components/mycomponent
```

### Minimal spec.yaml

```yaml
name: mycomponent.extractor
version: 1.0.0

modes:
  - extract
  - discover

capabilities:
  discover: true
  streaming: false
  bulkOperations: true

configSchema:
  type: object
  properties:
    connection:
      type: string
      description: Connection alias (e.g., @mydb.default)
    resource:
      type: string
      description: Resource to extract (e.g., table name, endpoint)
  required:
    - connection
    - resource

secrets:
  - /api_key  # If your component needs auth

x-runtime:
  driver: osiris.drivers.mycomponent_extractor_driver.MyComponentExtractorDriver
  requirements:
    packages:
      - pandas
      - requests
```

### Validation

```bash
osiris components validate mycomponent.extractor --level strict
```

**See**: [`modules/components.md`](modules/components.md) for full spec format.

**AI Checklist**: [`../../ai/checklists/COMPONENT_AI_CHECKLIST.md`](../../ai/checklists/COMPONENT_AI_CHECKLIST.md) for validation rules.

---

## Step 3: Implement Driver Skeleton

### Create Driver File

```bash
touch osiris/drivers/mycomponent_extractor_driver.py
```

### Driver Skeleton

```python
"""MyComponent Extractor Driver."""
import logging
import pandas as pd

logger = logging.getLogger(__name__)

class MyComponentExtractorDriver:
    """Extract data from MyComponent API/Database."""

    def run(
        self,
        *,
        step_id: str,
        config: dict,
        inputs: dict | None = None,
        ctx: Any = None,
    ) -> dict:
        """Execute extraction.

        Args:
            step_id: Step identifier
            config: Configuration with resolved_connection
            inputs: Not used for extractors
            ctx: Execution context for metrics

        Returns:
            {"df": pandas.DataFrame}
        """
        # 1. Validate config
        resource = config.get("resource")
        if not resource:
            raise ValueError(f"Step {step_id}: 'resource' is required")

        conn_info = config.get("resolved_connection", {})
        if not conn_info:
            raise ValueError(f"Step {step_id}: 'resolved_connection' is required")

        # 2. Extract connection details
        api_key = conn_info.get("api_key")
        base_url = conn_info.get("base_url", "https://api.example.com")

        # 3. Execute extraction (TODO: implement)
        df = self._extract_data(base_url, api_key, resource)

        # 4. Emit metrics
        rows_read = len(df)
        logger.info(f"Step {step_id}: Read {rows_read} rows")

        if ctx and hasattr(ctx, "log_metric"):
            ctx.log_metric("rows_read", rows_read, unit="rows", tags={"step": step_id})

        # 5. Return output
        return {"df": df}

    def _extract_data(self, base_url: str, api_key: str, resource: str) -> pd.DataFrame:
        """Extract data from API."""
        # TODO: Implement API call
        # - Add authentication
        # - Handle pagination
        # - Implement rate limiting
        # - Handle errors
        raise NotImplementedError("Implement _extract_data")
```

**See**: [`modules/drivers.md`](modules/drivers.md) for driver protocol details.

---

## Step 4: Define Connections & Doctor

### Connection Schema

Add to `spec.yaml`:

```yaml
connections:
  required_fields:
    - api_key
    - base_url
  optional_fields:
    - rate_limit_per_second
    - timeout_seconds

redaction:
  strategy: mask
  mask: "****"
  extras:
    - /api_key
    - /base_url
```

### Healthcheck (Optional)

Implement `doctor()` method in your connector:

```python
def doctor(self, connection: dict, timeout: float = 2.0) -> tuple[bool, dict]:
    """Test connection health."""
    try:
        # Test API connectivity
        response = requests.get(
            f"{connection['base_url']}/health",
            headers={"Authorization": f"Bearer {connection['api_key']}"},
            timeout=timeout
        )
        latency = response.elapsed.total_seconds() * 1000

        return True, {
            "latency_ms": latency,
            "category": "ok",
            "message": "Connection successful"
        }
    except requests.exceptions.Timeout:
        return False, {
            "latency_ms": None,
            "category": "timeout",
            "message": "Request timed out"
        }
    except requests.exceptions.ConnectionError as e:
        return False, {
            "latency_ms": None,
            "category": "network",
            "message": str(e)
        }
```

**See**: [`modules/connectors.md`](modules/connectors.md) for connection management patterns.

**AI Contract**: [`../../ai/checklists/connections_doctor_contract.md`](../../ai/checklists/connections_doctor_contract.md)

---

## Step 5: Emit Telemetry

### Required Metrics

| Component Type | Required Metric | Unit | Tags |
|----------------|-----------------|------|------|
| Extractor | `rows_read` | rows | `{"step": step_id}` |
| Writer | `rows_written` | rows | `{"step": step_id}` |
| Processor | `rows_processed` | rows | `{"step": step_id}` |

### Emission Pattern

```python
if ctx and hasattr(ctx, "log_metric"):
    ctx.log_metric("rows_read", len(df), unit="rows", tags={"step": step_id})
```

### Events (Auto-emitted by Runner)

The runner automatically emits:
- `step_start` - Before driver execution
- `step_complete` - After success
- `step_failed` - On exception
- `connection_resolve_complete` - After connection resolution

**You don't need to emit these manually.**

**See**: [`../../reference/events_and_metrics_schema.md`](../../reference/events_and_metrics_schema.md)

**AI Contract**: [`../../ai/checklists/metrics_events_contract.md`](../../ai/checklists/metrics_events_contract.md)

---

## Step 6: Register Component

### File Layout

```
components/
└── mycomponent.extractor/
    └── spec.yaml

osiris/
└── drivers/
    └── mycomponent_extractor_driver.py
```

### Verify Registration

```bash
# List all components
osiris components list

# Show your component
osiris components show mycomponent.extractor

# List runnable components
osiris components list --runnable
```

**See**: [`modules/components.md`](modules/components.md) for registry details.

---

## Step 7: Validate Locally

### Validate Spec

```bash
# Basic validation
osiris components validate mycomponent.extractor --level basic

# Enhanced validation (includes examples)
osiris components validate mycomponent.extractor --level enhanced

# Strict validation (semantic checks)
osiris components validate mycomponent.extractor --level strict --verbose
```

### Test Connection

Create `osiris_connections.yaml`:

```yaml
connections:
  mycomponent:
    default:
      api_key: ${MYCOMPONENT_API_KEY}
      base_url: https://api.example.com
```

Test connectivity:

```bash
export MYCOMPONENT_API_KEY="your-key-here"  # pragma: allowlist secret
osiris connections doctor
```

### Test Pipeline Execution

```bash
cd testing_env

# Create test pipeline
cat > test_mycomponent.yaml <<EOF
oml_version: "0.1.0"
name: "test_mycomponent"
steps:
  - id: extract_data
    component: mycomponent.extractor
    mode: extract
    config:
      connection: "@mycomponent.default"
      resource: "users"
EOF

# Compile
python ../osiris.py compile test_mycomponent.yaml

# Run locally
python ../osiris.py run --last-compile --verbose

# Run in E2B (if E2B_API_KEY set)
python ../osiris.py run --last-compile --e2b --verbose
```

---

## Step 8: Write Tests

### Unit Tests

```python
# tests/drivers/test_mycomponent_extractor_driver.py
import pytest
from osiris.drivers.mycomponent_extractor_driver import MyComponentExtractorDriver

class TestMyComponentExtractorDriver:
    def test_successful_extraction(self):
        """Test happy path extraction."""
        driver = MyComponentExtractorDriver()
        config = {
            "resource": "users",
            "resolved_connection": {
                "api_key": "test-key",  # pragma: allowlist secret
                "base_url": "https://api.example.com"
            }
        }
        ctx = MockContext()

        result = driver.run(step_id="test_1", config=config, inputs=None, ctx=ctx)

        assert "df" in result
        assert len(result["df"]) > 0
        assert ctx.metrics["rows_read"] > 0

    def test_missing_resource(self):
        """Test validation error."""
        driver = MyComponentExtractorDriver()
        config = {"resolved_connection": {}}

        with pytest.raises(ValueError, match="resource.*required"):
            driver.run(step_id="test_2", config=config, inputs=None, ctx=None)

    def test_connection_failure(self):
        """Test network error handling."""
        driver = MyComponentExtractorDriver()
        config = {
            "resource": "users",
            "resolved_connection": {
                "api_key": "invalid",  # pragma: allowlist secret
                "base_url": "https://invalid.example.com"
            }
        }

        with pytest.raises(RuntimeError, match="connection failed"):
            driver.run(step_id="test_3", config=config, inputs=None, ctx=None)
```

### Run Tests

```bash
# Run all tests
make test

# Run specific driver tests
pytest tests/drivers/test_mycomponent_extractor_driver.py -v

# Run with coverage
pytest tests/drivers/test_mycomponent_extractor_driver.py --cov=osiris.drivers -v
```

**See**: [`../../developer-guide/llms-testing.txt`](../llms-testing.txt) for test patterns.

---

## Step 9: Submit PR

### Pre-PR Checklist

**Specification**:
- [ ] `spec.yaml` passes `osiris components validate --level strict`
- [ ] All required fields present (`name`, `version`, `modes`, `capabilities`, `configSchema`)
- [ ] Secrets declared using JSON Pointers
- [ ] Examples validate against `configSchema`
- [ ] `x-runtime.driver` points to correct Python class

**Driver Implementation**:
- [ ] Implements `Driver` protocol: `run(*, step_id, config, inputs, ctx) -> dict`
- [ ] Uses `config["resolved_connection"]` (not environment variables)
- [ ] Emits required metrics (`rows_read`/`rows_written`/`rows_processed`)
- [ ] Handles errors gracefully (connection, validation, runtime)
- [ ] Cleans up resources in `finally` block

**Testing**:
- [ ] Unit tests for happy path
- [ ] Unit tests for error cases (bad config, connection failure, validation)
- [ ] Integration tests with real connections (can skip in CI)
- [ ] Metric emission verified
- [ ] Local and E2B runs produce identical results

**Documentation**:
- [ ] Examples in `spec.yaml` cover common use cases
- [ ] `llmHints` provide guidance for LLM-driven generation
- [ ] Inline code comments for complex logic

**Security**:
- [ ] Secrets never logged (use `# pragma: allowlist secret` in tests)
- [ ] Connection strings redacted in all outputs
- [ ] No SQL injection vulnerabilities (if applicable)

### Quality Commands

```bash
# Format code
make fmt

# Run linters
make lint

# Security scan
make security

# Run tests
make test

# Validate component
osiris components validate mycomponent.extractor --level strict
```

### Create PR

```bash
git add components/mycomponent.extractor/
git add osiris/drivers/mycomponent_extractor_driver.py
git add tests/drivers/test_mycomponent_extractor_driver.py

git commit -m "feat: Add mycomponent.extractor component

- Add mycomponent.extractor spec with discovery capability
- Implement MyComponentExtractorDriver with pagination
- Add connection doctor for health checks
- Include unit and integration tests

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"

git push origin feature/mycomponent-extractor
```

---

## Quick Reference

### File Checklist

```
✓ components/mycomponent.extractor/spec.yaml
✓ osiris/drivers/mycomponent_extractor_driver.py
✓ tests/drivers/test_mycomponent_extractor_driver.py
✓ osiris_connections.yaml (local testing)
```

### Command Checklist

```bash
✓ osiris components validate mycomponent.extractor --level strict
✓ osiris connections doctor
✓ make test
✓ make fmt
✓ make lint
✓ osiris run --last-compile --verbose
```

---

## Next Steps

- **Enhance Discovery**: Implement schema discovery for `discover` mode
- **Add Pagination**: Handle large datasets with cursor-based pagination
- **Optimize Performance**: Implement connection pooling and batch requests
- **Add Retries**: Implement exponential backoff for transient failures

---

## Resources

- **Concepts**: [`CONCEPTS.md`](CONCEPTS.md)
- **Modules**: [`modules/`](modules/) directory
- **Examples**: [`examples/shopify.extractor/`](examples/shopify.extractor/)
- **AI Checklists**: [`../../ai/checklists/`](../../ai/checklists/)
- **Reference**: [`../../reference/components-spec.md`](../../reference/components-spec.md)

---

**Need Help?** See [`README.md`](README.md) for navigation and common tasks.
