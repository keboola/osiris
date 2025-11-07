# Osiris Component Capabilities & Contracts: Complete Deep Dive

**Date**: 2025-11-07  
**Audience**: Third-party component developers, integration engineers, component reviewers  
**Scope**: All component capabilities and their formal contracts

---

## Executive Summary

Osiris defines **5 major capability categories** with formal contracts (machine-verifiable rules) that third-party components must implement. Each capability is backed by:

1. **Contract documents** (discovery, connections, metrics, validation)
2. **57 machine-verifiable rules** in the AI Checklist
3. **Real examples** (MySQL extractor, Supabase writer, Shopify extractor)
4. **JSON schemas** for validation
5. **CLI commands** for testing

This guide synthesizes all contracts into actionable requirements for component developers.

---

## Table of Contents

1. [Discovery Mode Contract](#discovery-mode-contract)
2. [Connection & Doctor Contract](#connection--doctor-contract)
3. [Metrics & Events Contract](#metrics--events-contract)
4. [OML Validation Requirements](#oml-validation-requirements)
5. [Connection Field Override Control](#connection-field-override-control)
6. [Component Specification Rules](#component-specification-rules)
7. [Driver Implementation Contract](#driver-implementation-contract)
8. [Real Implementation Examples](#real-implementation-examples)

---

## Discovery Mode Contract

**Scope**: Components declaring `capabilities.discover: true`

### Overview

Discovery mode allows components to introspect available resources (tables, endpoints, schemas) without manual enumeration. This is critical for LLM-driven pipeline generation where the AI agent needs to understand what data sources exist.

### MUST Requirements

#### DISC-001: Mode Declaration
- Component MUST declare `modes: ["discover"]` if `capabilities.discover: true`
- Validation: `assert "discover" in spec["modes"]` AND `assert spec["capabilities"]["discover"] is True`
- Failure: `❌ Discovery capability requires 'discover' in modes array`

#### DISC-002: Deterministic Output
- Discovery MUST produce sorted, deterministic output
- Sorting applies to: resources array AND fields array within each resource
- Rationale: Enables caching, fingerprinting, and consistent LLM input
- Validation: Run discovery twice, compare outputs (must be byte-identical)

**Discovery Output Schema**:
```json
{
  "discovered_at": "2025-09-30T12:00:00.000Z",  // ISO 8601 UTC
  "resources": [
    {
      "name": "customers",  // Alphabetically sorted in array
      "type": "table|view|endpoint|collection",
      "estimated_row_count": 1000000,  // Optional but recommended
      "fields": [  // Alphabetically sorted
        {
          "name": "id",
          "type": "integer",
          "nullable": false,
          "primary_key": true  // Optional
        },
        {
          "name": "email",
          "type": "string",
          "nullable": true
        }
      ]
    }
  ],
  "fingerprint": "sha256:abc123..."  // SHA-256 of sorted content (excluding fingerprint field itself)
}
```

#### DISC-003: Fingerprint Required
- Discovery output MUST include SHA-256 fingerprint
- Purpose: Cache invalidation, change detection
- Computation: Sort entire output (excluding fingerprint field), hash with SHA-256
- Format: `sha256:<64-hex-chars>`

**Fingerprint Computation Example**:
```python
import hashlib
import json

def compute_discovery_fingerprint(discovery: dict) -> str:
    discovery_copy = discovery.copy()
    discovery_copy.pop("fingerprint", None)
    canonical = json.dumps(discovery_copy, sort_keys=True)
    return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"
```

### SHOULD Requirements

#### DISC-004: Cache Support
- Components SHOULD cache discovery results keyed by connection fingerprint
- Cache location: `.osiris_cache/discovery/<family>/<alias>/`
- Cache entry includes:
  - `cached_at` (ISO 8601 timestamp)
  - `ttl_seconds` (default: 86400 = 24 hours)
  - `connection_fingerprint` (SHA-256 of connection credentials)
  - `discovery` (full discovery output)
- Invalidation: When connection changes or TTL expires

#### DISC-005: Estimated Counts
- SHOULD include `estimated_row_count` for each resource
- Why: Helps AI agents estimate extraction time and resource needs
- Real example from Shopify:
  ```json
  {
    "name": "customers",
    "estimated_row_count": 15000,
    "estimated_size_mb": 25
  }
  ```

#### DISC-006: Schema Details
- SHOULD include field types and nullability
- SHOULD include `primary_key` indicator
- SHOULD include `max_length` for string fields
- Enables type-aware pipeline generation by LLMs

### CLI Commands

```bash
# Trigger discovery
osiris components discover <component_name> --connection <alias> [--json]

# Example
osiris components discover mysql.extractor --connection @mysql.default --json

# Output
{
  "discovered_at": "2025-09-30T12:00:00.000Z",
  "resources": [
    {"name": "customers", "type": "table", "estimated_row_count": 1000000},
    {"name": "orders", "type": "table", "estimated_row_count": 5000000}
  ],
  "fingerprint": "sha256:abc123..."
}

# Cache operations
osiris cache list discovery
osiris cache clear discovery --family mysql --alias default
osiris components discover mysql.extractor --connection @mysql.default --refresh
```

### Implementation Pattern

**From Shopify Example**:
```python
class ShopifyExtractorDriver:
    def discover(self, config: dict, ctx: Any = None) -> dict:
        """Discover available Shopify resources."""
        conn_info = config.get("resolved_connection", {})
        
        # Query API for available resources
        resources = []
        for resource_name in ["customers", "orders", "products", "inventory_items"]:
            fields = self._query_resource_schema(conn_info, resource_name)
            resources.append({
                "name": resource_name,
                "type": "table",
                "estimated_row_count": self._get_estimated_count(conn_info, resource_name),
                "fields": sorted(fields, key=lambda f: f["name"])  # Sort alphabetically
            })
        
        # Build discovery output with sorted resources
        discovery = {
            "discovered_at": datetime.utcnow().isoformat().replace("+00:00", "Z"),
            "resources": sorted(resources, key=lambda r: r["name"]),
            "fingerprint": None  # Computed below
        }
        
        # Compute SHA-256 fingerprint
        discovery["fingerprint"] = f"sha256:{self._compute_fingerprint(discovery)}"
        
        return discovery
```

### Validation Checklist

- [ ] `modes` includes `"discover"`
- [ ] `capabilities.discover` is `true`
- [ ] Discovery output matches schema (ISO 8601 date, resources array, fingerprint)
- [ ] Resources sorted alphabetically by name
- [ ] Fields within each resource sorted alphabetically
- [ ] Fingerprint is SHA-256 format (`sha256:[64 hex chars]`)
- [ ] Output deterministic (run twice, compare)
- [ ] CLI command works: `osiris components discover <name> --connection @alias --json`

---

## Connection & Doctor Contract

**Scope**: All components using connections

### Overview

Osiris implements a **connection resolution system** where credentials and configuration are managed centrally in `osiris_connections.yaml` and resolved at runtime. Components receive credentials via `config["resolved_connection"]`, NOT environment variables or direct file access.

### MUST Requirements

#### CONN-001: Use Resolved Connection
- Driver MUST read from `config["resolved_connection"]`, NOT from environment
- Failure path: Driver reads `os.environ.get("API_KEY")` → **❌ FAIL**
- Success path: Driver reads `config.get("resolved_connection", {}).get("api_key")` → **✓ PASS**

**Correct Pattern**:
```python
def run(self, *, step_id: str, config: dict, inputs: dict | None, ctx: Any = None) -> dict:
    # ✓ Correct: Use resolved_connection
    conn_info = config.get("resolved_connection", {})
    api_key = conn_info.get("api_key")
    
    # ✓ Correct: Connection resolution handled by runner
    if not conn_info:
        raise ValueError(f"Step {step_id}: 'resolved_connection' is required")
    
    # ... rest of driver code
```

**Wrong Pattern**:
```python
def run(self, *, step_id: str, config: dict, inputs: dict | None, ctx: Any = None) -> dict:
    # ❌ Wrong: Direct environment variable access
    import os
    api_key = os.environ.get("API_KEY")
    
    # ❌ Wrong: Hardcoded credentials
    api_key = "sk_test_abc123"
```

**Why This Matters**:
- **Security**: MCP process has zero access to secrets (secrets stay in CLI process)
- **Multi-connection support**: Same component can reference different credentials
- **Connection resolution**: Runner handles `@alias` → actual credentials mapping
- **Auditability**: All connections logged with masked credentials

#### CONN-002: Validate Required Fields
- Driver MUST validate required connection fields at runtime
- Validation happens AFTER connection resolution (at runtime)
- OML validator also validates at compile time (layer 2 validation)

**Implementation**:
```python
conn_info = config.get("resolved_connection", {})
if not conn_info:
    raise ValueError(f"Step {step_id}: 'resolved_connection' is required")

required_fields = ["api_key", "base_url"]
for field in required_fields:
    if not conn_info.get(field):
        raise ValueError(f"Step {step_id}: connection field '{field}' is required")
```

### SHOULD Requirements

#### DOC-001: Implement doctor() Healthcheck
- Components SHOULD implement `doctor()` method for connection health testing
- Signature: `def doctor(self, connection: dict, timeout: float = 2.0) -> tuple[bool, dict]`
- Called by: `osiris connections doctor --family <family> --alias <alias>`
- Purpose: Quick health check before pipeline execution

**Doctor Method Signature**:
```python
def doctor(self, connection: dict, timeout: float = 2.0) -> tuple[bool, dict]:
    """Test connection health.
    
    Args:
        connection: Connection config dict
        timeout: Request timeout in seconds (default: 2.0)
    
    Returns:
        (ok: bool, details: dict) where details contains:
        - latency_ms (float | None): Round-trip time
        - category (str): auth|network|permission|timeout|ok|unknown
        - message (str): Non-sensitive, user-friendly message
    """
```

#### DOC-002: Standard Error Categories
- Doctor must use standard error categories for classification

| Category | Use Case | HTTP Example |
|----------|----------|--------------|
| `auth` | Authentication failure | 401 Unauthorized |
| `network` | Network/connectivity issue | ConnectionError, timeout |
| `permission` | Authorization failure | 403 Forbidden |
| `timeout` | Request timeout | Timeout exception |
| `ok` | Successful connection | 200 OK |
| `unknown` | Uncategorized error | Other errors |

**Implementation Example**:
```python
def doctor(self, connection: dict, timeout: float = 2.0) -> tuple[bool, dict]:
    try:
        start = time.time()
        response = requests.get(health_url, timeout=timeout)
        response.raise_for_status()
        latency_ms = (time.time() - start) * 1000
        
        return True, {
            "latency_ms": latency_ms,
            "category": "ok",
            "message": "Connected"
        }
    
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            return False, {
                "latency_ms": None,
                "category": "auth",
                "message": "Invalid credentials"  # Generic!
            }
        elif e.response.status_code == 403:
            return False, {
                "latency_ms": None,
                "category": "permission",
                "message": "Access denied"
            }
    
    except requests.exceptions.Timeout:
        return False, {
            "latency_ms": None,
            "category": "timeout",
            "message": "Timed out"
        }
    
    except requests.exceptions.ConnectionError as e:
        return False, {
            "latency_ms": None,
            "category": "network",
            "message": str(e)
        }
```

#### DOC-003: Redaction-Safe Output
- Doctor output MUST NOT contain secrets
- Generic messages only: "Invalid token" not "Invalid token: sk_test_abc123"
- All connection parameters are redacted before returning

**Correct**:
```python
return False, {
    "category": "auth",
    "message": "Invalid token"  # ✓ Generic
}
```

**Wrong**:
```python
return False, {
    "message": f"Token {api_key} is invalid"  # ❌ Leaks secret
}
```

### CLI Commands

```bash
# Test all connections
osiris connections doctor --json

# Output
{
  "connections": [
    {
      "family": "mysql",
      "alias": "default",
      "ok": true,
      "latency_ms": 12.5,
      "category": "ok",
      "message": "Connection successful"
    },
    {
      "family": "shopify",
      "alias": "main",
      "ok": false,
      "latency_ms": null,
      "category": "auth",
      "message": "Invalid access token"
    }
  ]
}

# Test specific connection
osiris connections doctor --family mysql --alias default --json

# Output
{
  "family": "mysql",
  "alias": "default",
  "ok": true,
  "latency_ms": 12.5,
  "category": "ok",
  "message": "Connection successful",
  "details": {
    "server_version": "8.0.35"
  }
}
```

### Connection File Format

**File**: `osiris_connections.yaml`

```yaml
version: 1
connections:
  mysql:
    default:
      host: localhost
      port: 3306
      database: mydb
      user: admin
      password: ${MYSQL_PASSWORD}  # Environment variable substitution
      default: true  # Use when no alias specified

  shopify:
    main:
      shop_domain: mystore.myshopify.com
      access_token: ${SHOPIFY_TOKEN}
      api_version: "2024-01"
```

### Validation Checklist

- [ ] Driver reads from `config["resolved_connection"]`
- [ ] Driver validates required connection fields
- [ ] Component spec declares `capabilities.doctor: true` if `doctor()` implemented
- [ ] `doctor()` returns `tuple[bool, dict]` with required keys
- [ ] `doctor()` timeout defaults to 2.0 seconds
- [ ] Error categories use standard values (auth, network, permission, timeout, ok, unknown)
- [ ] `doctor()` output contains no secrets
- [ ] CLI command works: `osiris connections doctor --json`

---

## Metrics & Events Contract

**Scope**: All driver implementations

### Overview

Osiris implements a **deterministic metrics and events system** for observability and auditing. Drivers emit metrics (data flow, performance), while the runner emits events (lifecycle, config, artifacts).

### MUST Requirements

#### MET-001: Required Metrics by Component Type

| Component Type | Metric Name | Unit | Tags | When |
|---|---|---|---|---|
| **Extractor** | `rows_read` | `rows` | `{"step": step_id}` | After successful extraction |
| **Writer** | `rows_written` | `rows` | `{"step": step_id}` | After successful write |
| **Processor** | `rows_processed` | `rows` | `{"step": step_id}` | After successful processing |

**Implementation Pattern**:
```python
def run(self, *, step_id: str, config: dict, inputs: dict | None, ctx: Any = None) -> dict:
    # ... extraction logic ...
    
    rows_read = len(df)
    
    # MUST emit metric
    if ctx and hasattr(ctx, "log_metric"):
        ctx.log_metric("rows_read", rows_read, unit="rows", tags={"step": step_id})
    
    return {"df": df}
```

#### MET-002: Unit Specified
- All metrics MUST specify unit
- Valid units: `rows`, `ms`, `bytes`, `seconds`, `files`, `code`, `calls`

**Correct**:
```python
ctx.log_metric("rows_read", 1000, unit="rows", tags={"step": step_id})
ctx.log_metric("duration_ms", 1234, unit="ms", tags={"step": step_id})
ctx.log_metric("api_calls_made", 5, unit="calls", tags={"step": step_id})
```

**Wrong**:
```python
ctx.log_metric("rows_read", 1000)  # ❌ Missing unit
ctx.log_metric("rows_read", 1000, tags={"step": step_id})  # ❌ Missing unit
```

#### MET-003: Tags Include Step ID
- All step-level metrics MUST include `tags={"step": step_id}`
- Purpose: Correlate metrics with specific pipeline steps
- Format: `tags={"step": "<step_id>"}`

### Events Emitted by Runner (NOT Driver)

The runner emits these automatically; drivers should NOT emit them:

| Event | When | Required Fields |
|---|---|---|
| `step_start` | Before `driver.run()` | `step_id`, `driver` |
| `step_complete` | After success | `step_id`, `rows_processed`, `duration_ms` |
| `step_failed` | On exception | `step_id`, `error`, `error_type` |
| `connection_resolve_complete` | After connection resolution | `step_id`, `family`, `alias`, `ok` |

**Drivers should NOT emit these.**

### CLI Commands for Metrics

```bash
# Query metrics from run
osiris logs metrics --session run_XXX --metric rows_read --json

# Output
[
  {
    "ts": "2025-09-30T12:00:00.000Z",
    "metric": "rows_read",
    "value": 1000,
    "unit": "rows",
    "tags": {"step": "extract_users"}
  }
]

# Query events
osiris logs events --session run_XXX --event step_complete --json

# Output
[
  {
    "ts": "2025-09-30T12:00:01.500Z",
    "event": "step_complete",
    "step_id": "extract_users",
    "rows_processed": 1000,
    "duration_ms": 1500
  }
]
```

### Validation Checklist

- [ ] Extractor emits `rows_read` metric
- [ ] Writer emits `rows_written` metric
- [ ] Processor emits `rows_processed` metric
- [ ] All metrics include `unit` parameter
- [ ] All metrics include `tags={"step": step_id}`
- [ ] Context null-check before logging: `if ctx and hasattr(ctx, "log_metric")`
- [ ] Metrics are emitted AFTER operation completes (not estimated beforehand)

---

## OML Validation Requirements

**Scope**: OML (Osiris Markup Language) pipelines

### Overview

Osiris validates OML pipelines through a **3-layer architecture**:
1. **Schema validation**: Structure, types, required fields
2. **Semantic validation**: Business logic rules (e.g., primary_key for replace mode)
3. **Runtime validation**: Secret resolution, config merging, driver availability

### Layer 1: Schema Validation

**Checks**:
- Document structure (dict with `oml_version`, `name`, `steps`)
- Step structure (each has `id`, `component`, `mode`)
- Component compatibility (mode supported by component)
- Config keys match component schema
- Connection references format: `@family.alias`

**Example Failures**:
```yaml
# ❌ Missing oml_version
name: my-pipeline
steps: []

# ❌ Invalid mode
steps:
  - id: extract
    component: mysql.extractor
    mode: invalid_mode  # Must be: read, write, transform

# ❌ Unknown component
steps:
  - id: extract
    component: unknown.extractor  # Not in registry
    mode: read
```

### Layer 2: Semantic Validation (CRITICAL)

#### Writer Rule: primary_key Required for replace/upsert

**Business Rule**: Writers using `replace` or `upsert` modes MUST specify `primary_key`.

**Correct**:
```yaml
steps:
  - id: write
    component: supabase.writer
    mode: write
    config:
      connection: "@supabase.db"
      table: users
      write_mode: upsert
      primary_key: [id]  # ✓ Required for upsert
```

**Wrong**:
```yaml
steps:
  - id: write
    component: supabase.writer
    mode: write
    config:
      connection: "@supabase.db"
      table: users
      write_mode: upsert
      # ❌ Missing primary_key
```

**Error**: `❌ Step 'write': primary_key is required when write_mode is 'upsert'`

#### Extractor Rule: query OR table (mutually exclusive)

**Business Rule**: Extractors MUST specify EITHER `query` OR `table`, not both.

**Correct (query)**:
```yaml
steps:
  - id: extract
    component: mysql.extractor
    mode: read
    config:
      connection: "@mysql.db"
      query: SELECT * FROM users WHERE active = 1
```

**Correct (table)**:
```yaml
steps:
  - id: extract
    component: mysql.extractor
    mode: read
    config:
      connection: "@mysql.db"
      table: users
```

**Wrong (both)**:
```yaml
steps:
  - id: extract
    component: mysql.extractor
    mode: read
    config:
      connection: "@mysql.db"
      query: SELECT * FROM users
      table: users  # ❌ Conflict!
```

**Error**: `❌ Step 'extract': Cannot specify both 'query' and 'table'`

#### Filesystem Rule: path Required

**Business Rule**: Filesystem readers/writers MUST specify `path`.

```yaml
# ❌ Wrong
steps:
  - id: write_csv
    component: filesystem.csv_writer
    mode: write
    config:
      delimiter: ","  # Not enough!

# ✓ Correct
steps:
  - id: write_csv
    component: filesystem.csv_writer
    mode: write
    config:
      path: /tmp/output.csv
      delimiter: ","
      encoding: utf-8
```

### Layer 3: Runtime Validation

Performed during compilation and execution:
- Secret resolution (env vars exist)
- Connection resolution (@alias → actual credentials)
- Config merging (connection + step config)
- Driver availability (can instantiate driver)
- Write mode validation (redundant check with layer 2)

### CLI Commands

```bash
# Validate OML file
osiris oml validate pipeline.yaml

# Output (on success)
{
  "valid": true,
  "errors": [],
  "warnings": []
}

# Output (on failure)
{
  "valid": false,
  "errors": [
    {
      "type": "missing_config_field",
      "message": "Step 'write': primary_key is required when write_mode is 'upsert'",
      "location": "steps[0].config"
    }
  ],
  "warnings": []
}
```

### Validation Rules Summary

| Component Type | Rule | Error | Severity |
|---|---|---|---|
| All writers | `write_mode` ∈ {append, replace, upsert} | Error | MUST |
| Writers (replace/upsert) | `primary_key` required | Error | MUST |
| Database extractors | `query` XOR `table` required | Error | MUST |
| Filesystem | `path` required | Error | MUST |
| Connection refs | `@family.alias` format | Error | MUST |
| Dependency refs | `needs` references valid step IDs | Error | MUST |

### Validation Checklist

- [ ] OML version is `"0.1.0"`
- [ ] Top-level keys: `oml_version`, `name`, `steps` (required)
- [ ] No legacy keys: `version`, `connectors`, `tasks` (forbidden)
- [ ] All steps have: `id`, `component`, `mode` (required)
- [ ] Step IDs are unique
- [ ] Step modes ∈ {read, write, transform}
- [ ] Component exists in registry
- [ ] Mode is supported by component
- [ ] Writers with replace/upsert have `primary_key`
- [ ] Extractors have `query` XOR `table`
- [ ] Filesystem components have `path`
- [ ] Connection references use `@family.alias` format
- [ ] Dependency references (`needs`) are valid

---

## Connection Field Override Control

**Scope**: Components using connection references

### Overview

The `x-connection-fields` specification declares which config fields come from connections and controls whether they can be overridden in step configs. This enforces security (passwords cannot be overridden) while allowing flexibility (hosts can be for testing).

### Three Override Policies

#### Policy: allowed
- **Use for**: Infrastructure fields
- **Examples**: `host`, `port`, `endpoint`, `schema`, `database`, `timeout`
- **Behavior**: Step config can override connection value
- **Validation**: No error or warning
- **Why**: Enables testing against different environments/hosts

**Example**:
```yaml
x-connection-fields:
  - name: host
    override: allowed  # Can test with localhost

# Pipeline can do:
steps:
  - id: extract
    config:
      connection: "@mysql.prod"
      host: "localhost"  # ✓ OK: override allowed
      table: users
```

#### Policy: forbidden
- **Use for**: Security/credential fields
- **Examples**: `password`, `api_key`, `token`, `secret`, `private_key`, `user`, `database`
- **Behavior**: Step config CANNOT override connection value
- **Validation**: Validation ERROR, execution blocked
- **Why**: Prevents credential leakage in pipeline YAML

**Example**:
```yaml
x-connection-fields:
  - name: password
    override: forbidden  # Cannot override

# Pipeline doing this:
steps:
  - id: extract
    config:
      connection: "@mysql.prod"
      password: "hacked!"  # ❌ ERROR: forbidden override
      table: users

# Error:
# ValidationError: Cannot override connection field 'password'
# Location: steps[0].config.password
# Policy: forbidden
```

#### Policy: warning
- **Use for**: Ambiguous fields that might contain secrets
- **Examples**: `headers`, `options`, `connection_string`, `custom_auth`
- **Behavior**: Step config can override, but warning emitted
- **Validation**: Warning message (execution proceeds)
- **Why**: Field might contain auth headers or secrets

**Example**:
```yaml
x-connection-fields:
  - name: headers
    override: warning  # Allow but warn

# Pipeline:
steps:
  - id: extract
    config:
      connection: "@graphql.api"
      headers:  # ⚠️  WARNING emitted
        X-Custom-Auth: "bearer token"
      query: "{ users { id } }"

# Warning:
# ValidationWarning: Overriding connection field 'headers' (policy: warning)
# This field may contain sensitive data.
```

### Complete Specification Format

```yaml
# Minimal format (all default to allowed)
x-connection-fields:
  - endpoint
  - auth_token

# Advanced format with policies
x-connection-fields:
  - name: host
    override: allowed      # Infrastructure
  - name: port
    override: allowed      # Infrastructure
  - name: database
    override: forbidden    # Security
  - name: user
    override: forbidden    # Security
  - name: password
    override: forbidden    # Security
  - name: headers
    override: warning      # Ambiguous
```

### Merge Strategy

Values are applied in this order (last wins):
1. **Component defaults** (from `configSchema.properties.*.default`)
2. **Connection values** (from `osiris_connections.yaml`)
3. **Step config overrides** (if policy allows)

**Example**:
```yaml
# Component spec defaults
configSchema:
  properties:
    port:
      type: integer
      default: 3306
    schema:
      type: string
      default: public

# Connection definition
connections:
  mysql:
    prod:
      host: db.prod.example.com
      port: 3307        # Overrides default 3306
      database: warehouse
      user: etl_user
      password: secret

# Step config
steps:
  - id: extract
    config:
      connection: "@mysql.prod"
      schema: analytics  # Overrides default "public"
      # Final values:
      # - host: db.prod.example.com (from connection)
      # - port: 3307 (from connection, overrides default)
      # - database: warehouse (from connection)
      # - user: etl_user (from connection)
      # - password: secret (from connection, forbidden override)
      # - schema: analytics (from step config, overrides default)
```

### Real Component Examples

#### MySQL Extractor (Production)
```yaml
x-connection-fields:
  - name: host
    override: allowed
  - name: port
    override: allowed
  - name: database
    override: forbidden  # Security: cannot change DB
  - name: user
    override: forbidden  # Security: cannot change user
  - name: password
    override: forbidden  # Security: cannot override password
  - name: schema
    override: allowed
```

#### GraphQL Extractor
```yaml
x-connection-fields:
  - name: endpoint
    override: allowed      # Can point to staging/prod
  - name: auth_token
    override: forbidden    # Token cannot be overridden
  - name: headers
    override: warning      # Allow but warn (might contain auth)
```

#### Shopify Extractor (Reference)
```yaml
# From spec.yaml
connections:
  required_fields:
    - shop_domain    # e.g., "mystore.myshopify.com"
    - access_token   # Admin API token
  optional_fields:
    - api_version    # e.g., "2024-01"
    - rate_limit     # requests per second
```

### Backward Compatibility

Components without explicit `x-connection-fields` fall back to `secrets`:
- Fields in `secrets` array treated as connection-provided
- Override policy defaults to `forbidden` for secret fields
- Non-secret fields default to `allowed`

**Migration Example**:
```yaml
# Before (implicit)
name: mysql.extractor
secrets:
  - /password

# After (explicit, recommended)
name: mysql.extractor
secrets:
  - /password

x-connection-fields:
  - name: host
    override: allowed
  - name: port
    override: allowed
  - name: database
    override: forbidden
  - name: user
    override: forbidden
  - name: password
    override: forbidden
```

### Validation Checklist

- [ ] All connection-provided fields listed in `x-connection-fields`
- [ ] Security fields have `override: forbidden`
- [ ] Infrastructure fields have `override: allowed`
- [ ] Ambiguous fields have `override: warning`
- [ ] Component spec declares all required fields in `configSchema.required`
- [ ] OML validator enforces override policies
- [ ] CLI validation shows errors for forbidden overrides
- [ ] CLI validation shows warnings for warning overrides

---

## Component Specification Rules

**Scope**: Component spec.yaml files

### Core Rules (SPEC Domain)

#### SPEC-001: Required Fields Present
- Component spec MUST contain: `name`, `version`, `modes`, `capabilities`, `configSchema`
- Validation: `osiris components validate <name> --level basic`
- Missing field error: `❌ Missing required field: <field>. Component specs must include: name, version, modes, capabilities, configSchema.`

#### SPEC-002: Name Pattern Valid
- Format: `^[a-z0-9_.-]+$` (lowercase, dots, dashes, underscores only)
- Examples: `mysql.extractor`, `shopify-api.writer`, `duckdb_processor`
- Error: `❌ Invalid component name '<name>'. Use lowercase letters, numbers, dots, dashes, underscores only.`

#### SPEC-003: Semantic Version Valid
- Format: `major.minor.patch` (e.g., `1.0.0`, `2.3.4`)
- Error: `❌ Invalid version '<version>'. Expected format: major.minor.patch (e.g., 1.0.0).`

#### SPEC-004: Modes Non-Empty
- At least one mode required
- Valid modes: `extract`, `write`, `transform`, `discover`, `analyze`, `stream`
- Error: `❌ At least one mode required. Valid modes: extract, write, transform, discover, analyze, stream.`

#### SPEC-005: Capabilities Object Present
- Object with boolean values
- Example: `capabilities: {discover: true, streaming: false}`

#### SPEC-006: ConfigSchema Valid JSON Schema
- Must be valid JSON Schema Draft 2020-12
- Validated with: `Draft202012Validator.check_schema(config_schema)`
- Error: `❌ Invalid configSchema: <error>`

#### SPEC-007: Examples Validate Against ConfigSchema
- All `examples[].config` MUST validate against `configSchema`
- Run: `osiris components validate <name> --level enhanced`

#### SPEC-008: Secrets Use JSON Pointers
- All `secrets` entries MUST be valid JSON Pointers starting with `/`
- Format: `/fieldname` (top-level) or `/nested/field` (nested)
- Error: `❌ Secret path '<path>' must start with '/' (JSON Pointer format).`

### Capabilities Rules (CAP Domain)

#### CAP-001: Discover Capability Consistency
- If `modes` includes `"discover"`, then `capabilities.discover` MUST be `true`
- Error: `❌ Component declares 'discover' mode but capabilities.discover is false.`

#### CAP-002: Mode-Specific I/O Contracts
- **Extractor** (mode: extract): MUST return `{"df": DataFrame}`
- **Writer** (mode: write): MUST accept `inputs: {"df": DataFrame}` and return `{}`
- **Processor** (mode: transform): MUST accept `inputs: {"df": DataFrame}` and return `{"df": DataFrame}`

**Signatures**:
```python
# Extractor
def run(self, *, step_id: str, config: dict, inputs: None, ctx: Any) -> dict:
    # inputs is None for extractors (no upstream)
    return {"df": df}

# Writer
def run(self, *, step_id: str, config: dict, inputs: dict, ctx: Any) -> dict:
    df = inputs["df"]
    # Write df to destination
    return {}  # No output

# Processor
def run(self, *, step_id: str, config: dict, inputs: dict, ctx: Any) -> dict:
    df = inputs["df"]
    # Transform df
    return {"df": transformed_df}
```

#### CAP-003: Deprecated Load Mode
- Use `"write"` mode instead of `"load"`. `"load"` is deprecated.
- Warning: `⚠️  Mode 'load' is deprecated. Use 'write' instead.`

#### CAP-004: Streaming Not Yet Supported
- MUST NOT declare `capabilities.streaming: true` in M1 (v0.5.x)
- Error: `❌ Streaming capability not supported in M1. Set capabilities.streaming: false.`

### Example Spec Structure

```yaml
# Component specification
name: mysql.extractor
version: 1.0.0
title: MySQL Data Extractor
description: Extract data from MySQL databases

modes:
  - extract
  - discover

capabilities:
  discover: true
  adHocAnalytics: true
  streaming: false

configSchema:
  type: object
  properties:
    host:
      type: string
      description: MySQL hostname
      default: localhost
    port:
      type: integer
      default: 3306
    database:
      type: string
    user:
      type: string
    password:
      type: string
    table:
      type: string
    query:
      type: string
  required:
    - host
    - database
    - user
    - password
  additionalProperties: false

secrets:
  - /password

x-connection-fields:
  - name: host
    override: allowed
  - name: port
    override: allowed
  - name: database
    override: forbidden
  - name: user
    override: forbidden
  - name: password
    override: forbidden

redaction:
  strategy: mask
  mask: "****"
  extras:
    - /host
    - /user

examples:
  - title: Basic extraction
    config:
      connection: "@mysql.default"
      table: customers
    notes: Extract all data from customers table

llmHints:
  inputAliases:
    host:
      - hostname
      - server
    database:
      - db
      - db_name
    table:
      - table_name
      - source_table
  promptGuidance: |
    Use mysql.extractor to read from MySQL.
    Requires: host, database, user, password.
    Use 'table' or 'query' for data selection.
  yamlSnippets:
    - "component: mysql.extractor"
    - "mode: read"
    - "table: {{ table_name }}"

loggingPolicy:
  sensitivePaths:
    - /password
    - /host
    - /user
  metricsToCapture:
    - rows_read
    - bytes_processed
    - duration_ms

x-runtime:
  driver: osiris.drivers.mysql_extractor_driver.MySQLExtractorDriver
  requirements:
    imports:
      - pandas
      - sqlalchemy
      - pymysql
    packages:
      - pandas
      - sqlalchemy
      - pymysql
```

---

## Driver Implementation Contract

**Scope**: Python driver classes that implement extraction/writing/processing

### Core Driver Protocol

#### DRIVER-001: Driver Protocol Implemented
- Driver class MUST implement: `run(*, step_id, config, inputs, ctx) -> dict`
- All parameters MUST be keyword-only (use `*` separator)
- Signature:
  ```python
  def run(
      self,
      *,
      step_id: str,
      config: dict,
      inputs: dict | None,
      ctx: Any
  ) -> dict:
  ```

#### DRIVER-002: Keyword-Only Arguments
- ALL parameters after `self` MUST be keyword-only
- Enforced with `*` separator
- This prevents positional argument mistakes at call sites

**Correct**:
```python
def run(self, *, step_id: str, config: dict, inputs: dict | None, ctx: Any) -> dict:
```

**Wrong**:
```python
def run(self, step_id: str, config: dict, inputs: dict | None, ctx: Any) -> dict:
    # ❌ Missing * separator
```

#### DRIVER-003: Input Immutability
- Driver MUST NOT mutate `inputs` dict or DataFrames within it
- Mutation breaks downstream steps that share data
- Solution: Create copies if modifications needed

**Correct**:
```python
def run(self, *, step_id: str, config: dict, inputs: dict | None, ctx: Any) -> dict:
    # ✓ Create copy before modifying
    df = inputs["df"].copy()
    df["new_col"] = df["col1"] + df["col2"]
    return {"df": df}
```

**Wrong**:
```python
def run(self, *, step_id: str, config: dict, inputs: dict | None, ctx: Any) -> dict:
    # ❌ Mutates input
    df = inputs["df"]
    df["new_col"] = df["col1"] + df["col2"]
    return {"df": df}
```

### Resource Management

#### DRIVER-004: Resource Cleanup
- Driver SHOULD clean up resources (connections, file handles) in `finally` block
- Prevents resource leaks and connection pool exhaustion

**Pattern**:
```python
def run(self, *, step_id: str, config: dict, inputs: dict | None, ctx: Any) -> dict:
    engine = None
    try:
        # Create connection
        engine = create_engine(connection_string)
        
        # Use connection
        df = pd.read_sql("SELECT * FROM table", engine)
        
        return {"df": df}
    
    finally:
        # ✓ Always cleanup
        if engine:
            engine.dispose()
```

#### DRIVER-005: Context Null Check
- Driver MUST check `if ctx and hasattr(ctx, "log_metric")` before calling `ctx.log_metric()`
- Context can be None in some execution modes
- `hasattr` check guards against missing methods

**Correct**:
```python
if ctx and hasattr(ctx, "log_metric"):
    ctx.log_metric("rows_read", 1000, unit="rows", tags={"step": step_id})
```

**Wrong**:
```python
ctx.log_metric("rows_read", 1000, unit="rows", tags={"step": step_id})
# ❌ Will crash if ctx is None
```

#### DRIVER-006: Error Re-raising
- Driver SHOULD catch specific exceptions, add context, and re-raise as `RuntimeError`
- Improves error messages with step-specific context

**Pattern**:
```python
try:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
except requests.exceptions.HTTPError as e:
    error_msg = f"API error: {e.response.status_code} - {e.response.text}"
    logger.error(f"Step {step_id}: {error_msg}")
    raise RuntimeError(error_msg) from e

except requests.exceptions.Timeout:
    error_msg = "API request timed out"
    logger.error(f"Step {step_id}: {error_msg}")
    raise RuntimeError(error_msg) from e

except Exception as e:
    error_msg = f"Unexpected error: {type(e).__name__}: {str(e)}"
    logger.error(f"Step {step_id}: {error_msg}")
    raise RuntimeError(error_msg) from e
```

### Logging and Metrics

**All components should**:
1. Use `logging.getLogger(__name__)` for debug/info/error logging
2. Emit required metrics via `ctx.log_metric()`
3. Check context availability before metric emission
4. Include step_id in log messages for traceability

### Validation Checklist

- [ ] Driver implements `run(*, step_id, config, inputs, ctx)` signature
- [ ] All parameters are keyword-only (use `*` separator)
- [ ] Driver does not mutate `inputs` dict or DataFrames
- [ ] Resources cleaned up in `finally` block
- [ ] Context null-check before `ctx.log_metric()` calls
- [ ] Exceptions caught and re-raised as `RuntimeError` with context
- [ ] Step ID included in all log messages
- [ ] Correct metric emitted for component type (rows_read, rows_written, rows_processed)
- [ ] Metrics include unit and step tag

---

## Real Implementation Examples

### Example 1: Shopify Extractor (Reference Implementation)

**File**: `/Users/padak/github/osiris/docs/developer-guide/human/examples/shopify.extractor/spec.yaml`

**Key Features**:
- Discovery mode with resource introspection
- Pagination with cursor-based offset
- Rate limiting (2 req/sec Shopify tier)
- Doctor method for health checks
- Proper metric emission
- LLM hints for pipeline generation

**Driver Snippet**:
```python
class ShopifyExtractorDriver:
    RATE_LIMIT_DELAY = 0.5  # seconds between requests
    
    def run(self, *, step_id: str, config: dict, inputs: dict | None = None, ctx: Any = None) -> dict:
        # Validate config
        resource = config.get("resource")
        if not resource:
            raise ValueError(f"Step {step_id}: 'resource' is required")
        
        # Extract connection (from resolved_connection, not environment)
        conn_info = config.get("resolved_connection", {})
        if not conn_info:
            raise ValueError(f"Step {step_id}: 'resolved_connection' is required")
        
        shop_domain = conn_info.get("shop_domain")
        access_token = conn_info.get("access_token")
        if not shop_domain or not access_token:
            raise ValueError(f"Step {step_id}: shop_domain and access_token required")
        
        # Build API client
        client = ShopifyAPIClient(
            shop_domain=shop_domain,
            access_token=access_token,
            api_version=conn_info.get("api_version", "2024-01")
        )
        
        try:
            # Paginate through all records
            all_records = []
            since_id = config.get("since_id", 0)
            limit = config.get("limit", 250)
            api_calls = 0
            
            while True:
                response = client.get_resource(resource, since_id=since_id, limit=limit)
                records = response.get(resource, [])
                
                if not records:
                    break
                
                all_records.extend(records)
                api_calls += 1
                
                # Update pagination cursor
                last_id = records[-1].get("id")
                if last_id:
                    since_id = last_id
                else:
                    break
                
                # Last page check
                if len(records) < limit:
                    break
            
            # Convert to DataFrame
            df = pd.DataFrame(all_records)
            
            # Emit metrics
            rows_read = len(df)
            if ctx and hasattr(ctx, "log_metric"):
                ctx.log_metric("rows_read", rows_read, unit="rows", tags={"step": step_id})
                ctx.log_metric("api_calls_made", api_calls, unit="calls", tags={"step": step_id})
            
            return {"df": df}
        
        except requests.exceptions.HTTPError as e:
            error_msg = f"Shopify API error: {e.response.status_code} - {e.response.text}"
            raise RuntimeError(error_msg) from e
        
        except Exception as e:
            error_msg = f"Extraction failed: {type(e).__name__}: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def doctor(self, connection: dict, timeout: float = 2.0) -> tuple[bool, dict]:
        """Test connection health."""
        try:
            start = time.time()
            url = f"https://{connection['shop_domain']}/admin/api/{connection.get('api_version', '2024-01')}/shop.json"
            headers = {"X-Shopify-Access-Token": connection["access_token"]}
            
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            
            latency = (time.time() - start) * 1000
            
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
        
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                return False, {
                    "latency_ms": None,
                    "category": "auth",
                    "message": "Invalid access token"  # Generic!
                }
            # ... more categories
        
        except requests.exceptions.ConnectionError as e:
            return False, {
                "latency_ms": None,
                "category": "network",
                "message": str(e)
            }
```

**Discovery Output**:
```json
{
  "discovered_at": "2025-09-30T12:00:00.000Z",
  "resources": [
    {
      "name": "customers",
      "endpoint": "/admin/api/2024-01/customers.json",
      "estimated_count": 15000,
      "supports_pagination": true,
      "fields": [
        {"name": "id", "type": "integer", "nullable": false, "primary_key": true},
        {"name": "email", "type": "string", "nullable": true},
        {"name": "created_at", "type": "datetime", "nullable": false}
      ]
    },
    {
      "name": "orders",
      "endpoint": "/admin/api/2024-01/orders.json",
      "estimated_count": 50000,
      "fields": [
        {"name": "id", "type": "integer", "nullable": false, "primary_key": true},
        {"name": "customer_id", "type": "integer", "nullable": true},
        {"name": "total_price", "type": "decimal", "nullable": false}
      ]
    }
  ],
  "fingerprint": "sha256:a3f5e7d9c2b1a8f4e6d3c9b5a7f2e8d4..."
}
```

**Connection Configuration**:
```yaml
connections:
  shopify:
    default:
      shop_domain: "mystore.myshopify.com"
      access_token: "${SHOPIFY_ACCESS_TOKEN}"
      api_version: "2024-01"
      rate_limit: 2  # requests per second
```

### Example 2: MySQL Extractor (Production Component)

**From spec.yaml**:
- Modes: `extract`, `discover`
- Capabilities: `discover: true`, `adHocAnalytics: true`
- Required fields: `host`, `database`, `user`, `password`
- Optional: `query`, `table`, `limit`, `offset`, `batch_size`

**Key Contract Elements**:
```yaml
configSchema:
  required:
    - host
    - database
    - user
    - password

x-connection-fields:
  - name: host
    override: allowed        # Can use different host for testing
  - name: port
    override: allowed
  - name: database
    override: forbidden      # Cannot change DB
  - name: user
    override: forbidden      # Cannot change user
  - name: password
    override: forbidden      # Cannot override password

secrets:
  - /password

loggingPolicy:
  sensitivePaths:
    - /password
    - /host
    - /user
  metricsToCapture:
    - rows_read
    - bytes_processed
    - duration_ms
```

### Example 3: Supabase Writer (Production Component)

**Key Contract Elements**:
```yaml
modes:
  - write
  - discover

capabilities:
  discover: true

configSchema:
  required:
    - key
    - table

constraints:
  required:
    - when:
        write_mode: upsert
      must:
        primary_key:
          minLength: 1
      error: primary_key required when write_mode is 'upsert'

x-connection-fields:
  - name: url
    override: allowed
  - name: project_id
    override: allowed
  - name: key
    override: forbidden    # API key cannot be overridden
```

**OML Validation (Semantic Layer)**:
```python
# This OML fails semantic validation (layer 2)
oml = {
    "oml_version": "0.1.0",
    "name": "my-pipeline",
    "steps": [{
        "id": "write",
        "component": "supabase.writer",
        "mode": "write",
        "config": {
            "connection": "@supabase.db",
            "table": "users",
            "write_mode": "upsert"
            # ❌ Missing primary_key - validation error!
        }
    }]
}

# Error:
# "Step 'write': primary_key is required when write_mode is 'upsert'"
```

---

## Summary: Component Capability Matrix

| Capability | Contract Docs | Rules | Real Examples | CLI Command |
|---|---|---|---|---|
| **Discovery** | `discovery_contract.md` | DISC-001 to DISC-006 | MySQL, Supabase, Shopify | `osiris components discover <name> --connection @alias` |
| **Doctor/Health** | `connections_doctor_contract.md` | DOC-001 to DOC-003 | Shopify example | `osiris connections doctor --family <f> --alias <a>` |
| **Metrics/Events** | `metrics_events_contract.md` | MET-001 to MET-003 | All components | `osiris logs metrics --session run_XXX` |
| **Connection Fields** | `x-connection-fields.md` | CONN-001, CONN-002 + policies | MySQL, Supabase, Shopify | `osiris oml validate pipeline.yaml` |
| **OML Validation** | `oml-validation.md` | Layer 1, 2, 3 rules | All pipelines | `osiris oml validate pipeline.yaml` |
| **Component Spec** | `COMPONENT_AI_CHECKLIST.md` | SPEC-001 to SPEC-010 | All specs | `osiris components validate <name> --level strict` |
| **Driver Protocol** | `COMPONENT_AI_CHECKLIST.md` | DRIVER-001 to DRIVER-006 | All drivers | Code review + runtime |

---

## Checklist: Building a Compliant Component

Use this checklist when developing a new component:

### Specification (spec.yaml)
- [ ] Required fields present: `name`, `version`, `modes`, `capabilities`, `configSchema`
- [ ] Name matches pattern: `^[a-z0-9_.-]+$`
- [ ] Version follows semantic versioning
- [ ] Modes list contains valid modes
- [ ] ConfigSchema is valid JSON Schema Draft 2020-12
- [ ] All `secrets` use JSON Pointer format
- [ ] `x-connection-fields` declared for all connection-provided fields
- [ ] Override policies correct: security→forbidden, infra→allowed, ambiguous→warning
- [ ] Examples validate against configSchema
- [ ] `x-runtime.driver` points to valid Python class
- [ ] LLM hints provided for AI-driven generation

### Connection Handling
- [ ] Driver reads from `config["resolved_connection"]`, not environment
- [ ] Driver validates required connection fields
- [ ] Doctor method implemented if `capabilities.doctor: true` declared
- [ ] Doctor returns `tuple[bool, dict]` with required keys
- [ ] Doctor categories use standard values
- [ ] Doctor output contains no secrets

### Discovery (if applicable)
- [ ] `capabilities.discover: true` declared
- [ ] `modes` includes `"discover"`
- [ ] Discovery output matches schema (discovered_at, resources, fingerprint)
- [ ] Resources sorted alphabetically
- [ ] Fields within resources sorted alphabetically
- [ ] Fingerprint is SHA-256
- [ ] Output deterministic (run twice, compare)

### Metrics & Events
- [ ] Correct metric emitted for component type
- [ ] Metric includes `unit` parameter
- [ ] Metric includes `tags={"step": step_id}`
- [ ] Context null-check before `ctx.log_metric()`

### OML Validation
- [ ] Component-specific validation rules understood
- [ ] Writers with replace/upsert require `primary_key`
- [ ] Extractors require `query` XOR `table`
- [ ] Filesystem components require `path`

### Driver Implementation
- [ ] Driver class implements `run(*, step_id, config, inputs, ctx)` signature
- [ ] All parameters are keyword-only
- [ ] No mutation of inputs
- [ ] Resources cleaned up in `finally` block
- [ ] Exceptions caught and re-raised with context
- [ ] Step ID included in log messages

### Testing
- [ ] CLI validation passes: `osiris components validate <name> --level strict`
- [ ] Discovery mode works: `osiris components discover <name> --connection @alias`
- [ ] Doctor method works: `osiris connections doctor --family <f> --alias <a>`
- [ ] Example pipelines validate: `osiris oml validate pipeline.yaml`
- [ ] All tests pass

---

## Quick Reference: Error Messages

| Error | Root Cause | Fix |
|---|---|---|
| `❌ Discovery capability requires 'discover' in modes array` | modes missing "discover" | Add "discover" to modes |
| `❌ Discovery output non-deterministic` | Resources or fields not sorted | Use `sorted()` on lists |
| `❌ Missing or invalid fingerprint` | No SHA-256 fingerprint | Compute with `hashlib.sha256()` |
| `❌ Driver reads from environment instead of resolved_connection` | Direct env var access | Use `config["resolved_connection"]` |
| `❌ Missing required metric 'rows_read' for extractor` | No metric emitted | Add `ctx.log_metric("rows_read", ...)` |
| `❌ Metric missing unit` | Unit parameter not specified | Add `unit="rows"` parameter |
| `❌ Must check ctx availability before calling ctx.log_metric()` | No null check | Add `if ctx and hasattr(ctx, "log_metric")` |
| `❌ Step 'write': primary_key is required when write_mode is 'upsert'` | Missing primary_key in upsert | Add `primary_key` field in config |
| `❌ Cannot specify both 'query' and 'table'` | Ambiguous extractor config | Use only `query` OR `table` |
| `❌ Cannot override connection field 'password'` | Forbidden override attempt | Remove override from step config |
| `❌ Invalid component name '<name>'` | Name pattern violation | Use lowercase, dots, dashes, underscores |
| `❌ Invalid version '<version>'` | Semantic version violation | Use `major.minor.patch` format |

---

**Document Version**: 1.0  
**Created**: 2025-11-07  
**Osiris Version**: v0.5.5  
**Status**: Production Ready
