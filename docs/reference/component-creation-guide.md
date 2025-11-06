# Component Creation Guide

Complete walkthrough for creating new Osiris components from start to finish.

## Step 1: Decide Component Type & Complexity

```
Type Options:
- extractor  (reads from external source)
- writer     (writes to external destination)
- processor  (transforms in-memory data)
- discovery  (mode for schema introspection)

Complexity Level:
- Tier 1: Simple (no auth, <10 fields)
- Tier 2: Medium (DB/API auth, 10-20 fields)
- Tier 3: Complex (multi-auth, 20+ fields, advanced features)
```

**Choose a reference exemplar:**
- Tier 1: `/components/filesystem.csv_writer/spec.yaml`
- Tier 2: `/components/mysql.extractor/spec.yaml`
- Tier 3: `/components/graphql.extractor/spec.yaml`

## Step 2: Create Component Directory

```bash
mkdir -p /components/{namespace}.{type}
```

Examples:
- `/components/bigquery.extractor/`
- `/components/snowflake.writer/`
- `/components/slack.action/` (new type)

## Step 3: Write spec.yaml

### 3a. Header Section (Required)
```yaml
# {ServiceName} {Type} Component Specification
name: namespace.type                    # e.g., bigquery.extractor
version: 1.0.0
title: Human Readable Title
description: |
  Multi-line description of component purpose.
  Explain what it does and primary use case.
```

### 3b. Operational Configuration
```yaml
modes:
  - extract                             # At least one: extract, write, discover, transform

capabilities:
  discover: false
  adHocAnalytics: false
  inMemoryMove: false
  streaming: false
  bulkOperations: true
  transactions: false
  partitioning: false
  customTransforms: false
```

### 3c. Configuration Schema
```yaml
configSchema:
  type: object
  properties:
    # Group 1: Connection/Authentication
    host:
      type: string
      description: "Service hostname"
      default: "localhost"
    api_key:
      type: string
      description: "API key for authentication"
      minLength: 20
    
    # Group 2: Required Operational
    query:
      type: string
      description: "SQL or API query"
      minLength: 1
    
    # Group 3: Optional with Defaults
    batch_size:
      type: integer
      description: "Rows per batch"
      default: 10000
      minimum: 100
      maximum: 100000
  
  required:
    - api_key
    - query
  
  additionalProperties: false             # CRITICAL: prevent typos
```

### 3d. Security Configuration
```yaml
secrets:
  - /api_key
  - /password

x-secret:
  - /api_key
  - /password
  - /resolved_connection/api_key

x-connection-fields:
  - name: api_key
    override: forbidden                  # Can't override secrets
  - name: host
    override: allowed                    # OK to override endpoints

redaction:
  strategy: mask
  mask: "****"
  extras:
    - /host
    - /api_key
```

### 3e. Validation Rules
```yaml
constraints:
  required:
    - when: {mode: upsert}
      must: {upsert_keys: {minItems: 1}}
      error: "upsert_keys required when mode='upsert'"
```

### 3f. Examples (2+ required)
```yaml
examples:
  - title: "Basic usage"
    config:
      host: localhost
      api_key: "your_key_here"          # pragma: allowlist secret
      query: "SELECT * FROM table"
    notes: "Simplest case with defaults"
  
  - title: "Advanced usage"
    config:
      host: db.prod.company.com
      api_key: "prod_key"               # pragma: allowlist secret
      query: |
        SELECT id, name FROM users
        WHERE created_at >= '2024-01-01'
      batch_size: 50000
    notes: "Production scenario"
```

### 3g. Remaining Sections
```yaml
compatibility:
  requires:
    - python>=3.10
    - sqlalchemy>=2.0
  platforms:
    - linux
    - darwin
    - windows
    - docker

llmHints:
  inputAliases:
    api_key:
      - api_token
      - access_key
  promptGuidance: |
    Use namespace.type to [action].
    Requires [required_fields].
    Supports [key_features].
  yamlSnippets:
    - "type: namespace.type"
    - "api_key: '{{ api_key }}'"
  commonPatterns:
    - pattern: basic_usage
      description: "Simple query without filters"

loggingPolicy:
  sensitivePaths:
    - /api_key
    - /password
  eventDefaults:
    - operation.start
    - operation.complete
  metricsToCapture:
    - rows_read
    - bytes_processed
    - duration_ms

limits:
  maxRows: 10000000
  maxSizeMB: 10240
  maxDurationSeconds: 3600
  maxConcurrency: 5

x-runtime:
  driver: osiris.drivers.namespace_type_driver.DriverClassName
  requirements:
    imports:
      - pandas
      - sqlalchemy
    packages:
      - pandas
      - sqlalchemy
```

## Step 4: Implement Driver Class

### 4a. Create driver file
```bash
touch /osiris/drivers/{namespace}_{type}_driver.py
```

### 4b. Implement run() method
```python
"""Namespace {Type} driver implementation."""

import logging
from typing import Any
import pandas as pd

logger = logging.getLogger(__name__)


class NamespaceTypeDriver:
    """Driver for {component description}."""

    def run(
        self,
        *,
        step_id: str,
        config: dict,
        inputs: dict | None = None,
        ctx: Any = None,
    ) -> dict:
        """Execute component operation.

        Args:
            step_id: Pipeline step identifier
            config: Merged component + user configuration
            inputs: Data from previous pipeline steps
            ctx: Execution context for logging

        Returns:
            Extractors: {"df": DataFrame}
            Writers: {}
            Processors: {"df": transformed_df}
        """
        # 1. Validate inputs
        if mode == "extract":
            if not config.get("query"):
                raise ValueError(f"Step {step_id}: 'query' required")
        
        # 2. Get configuration
        api_key = config.get("api_key")
        query = config.get("query")
        batch_size = config.get("batch_size", 10000)
        
        # 3. Execute operation
        try:
            logger.info(f"Step {step_id}: Executing operation")
            # ... implementation ...
            df = pd.DataFrame(...)
        except Exception as e:
            logger.error(f"Step {step_id}: Operation failed: {e}")
            raise
        
        # 4. Log metrics
        rows_processed = len(df) if "df" in locals() else 0
        logger.info(f"Step {step_id}: Processed {rows_processed} rows")
        
        if ctx and hasattr(ctx, "log_metric"):
            ctx.log_metric("rows_processed", rows_processed)
        
        # 5. Return result
        return {"df": df} if "df" in locals() else {}
```

**Key Patterns:**
- Always use `config.get(field, default)` for optional fields
- Log important operations for observability
- Use masked URLs in logs (never real credentials)
- Call `ctx.log_metric()` for pipeline metrics
- Return `{"df": ...}` for extractors, `{}` for writers

## Step 5: Create Tests

```bash
touch /tests/test_namespace_type.py
```

```python
"""Tests for namespace.type component."""

import pytest
from osiris.drivers.namespace_type_driver import NamespaceTypeDriver


class TestNamespaceTypeDriver:
    """Test namespace.type driver."""

    def test_basic_extraction(self):
        """Test basic extraction with minimal config."""
        driver = NamespaceTypeDriver()
        config = {
            "api_key": "test_key",  # pragma: allowlist secret
            "query": "SELECT * FROM table",
        }
        result = driver.run(step_id="test_step", config=config)
        assert "df" in result
        assert len(result["df"]) > 0

    def test_missing_required_field(self):
        """Test error handling for missing required field."""
        driver = NamespaceTypeDriver()
        config = {
            "api_key": "test_key",  # pragma: allowlist secret
            # Missing: query
        }
        with pytest.raises(ValueError, match="'query' required"):
            driver.run(step_id="test_step", config=config)

    def test_with_batch_size(self):
        """Test custom batch_size option."""
        driver = NamespaceTypeDriver()
        config = {
            "api_key": "test_key",    # pragma: allowlist secret
            "query": "SELECT * FROM table",
            "batch_size": 5000,
        }
        result = driver.run(step_id="test_step", config=config)
        assert "df" in result
```

## Step 6: Validation Checklist

### Spec Validation
- [ ] YAML syntax is valid
- [ ] `name` follows `namespace.type` format
- [ ] `version` is semver (e.g., 1.0.0)
- [ ] `configSchema` has `additionalProperties: false`
- [ ] All secrets in `secrets` AND `x-secret`
- [ ] All `x-connection-fields` defined with override policy
- [ ] At least 2 `examples` with `# pragma: allowlist secret`
- [ ] All conditional constraints have `error` message
- [ ] `llmHints` includes `promptGuidance` paragraph
- [ ] Driver class path matches reality in `x-runtime`

### Driver Validation
- [ ] `run()` method has correct signature
- [ ] Raises `ValueError` with step_id for input validation
- [ ] Never logs real credentials or DSNs
- [ ] Calls `ctx.log_metric()` for key metrics
- [ ] Returns correct format: `{"df": ...}` or `{}`
- [ ] Handles missing optional fields with defaults

### Testing Validation
- [ ] At least 3 test cases (basic, error, options)
- [ ] Secret comments include `# pragma: allowlist secret`
- [ ] Tests run: `pytest /tests/test_namespace_type.py`

## Step 7: Integration Checklist

### Pre-Commit
```bash
# Format code
make fmt

# Run tests
pytest /tests/test_namespace_type.py -v

# Run linting
make lint

# Security check
make security
```

### Create PR
1. Link to component spec analysis docs
2. Explain which exemplar tier was followed
3. List any deviations from pattern with rationale
4. Include test results

### Example PR Template
```markdown
## Summary
- Implements namespace.type component (Tier 2 complexity)
- Follows mysql.extractor pattern for dual-mode setup
- Adds 45 test cases covering auth methods and pagination

## Spec Highlights
- 22 configuration fields with conditional validation
- 3 authentication methods (bearer, basic, api_key)
- Cursor-based pagination support
- 4 real-world examples (GitHub, Shopify, Hasura, custom)

## Testing
- [x] Spec validation passes
- [x] All 45 tests pass
- [x] Security checks pass
- [x] 78% code coverage

## Compliance
- Follows component-specs-analysis.md patterns
- Exemplar: graphql.extractor (Tier 3)
- No hardcoded paths
- All secrets properly declared
```

## Quick Reference: Copy-Paste Templates

### Minimal Spec Template (Tier 1)
See `/docs/reference/component-spec-quickref.md` → "Template Structure for New Component Specs"

### Medium Complexity Spec (Tier 2)
Base: `/components/mysql.extractor/spec.yaml`

### Complex Spec (Tier 3)
Base: `/components/graphql.extractor/spec.yaml`

## Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| YAML syntax error | Use YAML validator: `yamllint spec.yaml` |
| Missing `additionalProperties: false` | Adds it to configSchema immediately |
| LLM generates wrong configs | Add more specific `constraints.error` messages |
| Secrets logged in tests | Add `# pragma: allowlist secret` comments |
| Path doesn't exist in different environments | Use config-driven paths only |
| Driver not found at runtime | Check `x-runtime.driver` class path matches file |

## Resources

- **Full Analysis:** `/docs/reference/component-specs-analysis.md` (1000+ lines)
- **Quick Reference:** `/docs/reference/component-spec-quickref.md` (330 lines)
- **Exemplars:** 
  - Simple: `/components/filesystem.csv_writer/spec.yaml`
  - Medium: `/components/mysql.extractor/spec.yaml`
  - Complex: `/components/graphql.extractor/spec.yaml`
- **Driver Examples:** `/osiris/drivers/*_driver.py`

---

**Last Updated:** October 25, 2025
**Status:** Production Ready
**Difficulty:** 2-3 hours for Tier 2, 4-6 hours for Tier 3
