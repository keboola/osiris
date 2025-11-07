# Osiris Component Capabilities: Quick Reference Summary

**Purpose**: One-page summary of all component capabilities and their contracts  
**For**: Component developers, reviewers, third-party integrators

---

## 5 Core Component Capabilities

### 1. Discovery Mode (DISC-001 to DISC-006)

**What it is**: Components introspect available resources (tables, endpoints, schemas) without manual enumeration.

**MUST Have**:
- `modes: ["discover"]` + `capabilities.discover: true`
- Deterministic, sorted output (alphabetically)
- SHA-256 fingerprint of output
- ISO 8601 UTC timestamps

**SHOULD Have**:
- Cache results by connection fingerprint (TTL: 24h)
- Include `estimated_row_count` for each resource
- Include field types, nullability, primary_key

**CLI Test**:
```bash
osiris components discover <name> --connection @alias --json
```

**Real Examples**: MySQL (tables), Shopify (resources), Supabase (schemas)

---

### 2. Connection Resolution (CONN-001, CONN-002)

**What it is**: Components receive credentials from `osiris_connections.yaml` via `config["resolved_connection"]`.

**MUST Have**:
- Read from `config["resolved_connection"]`, NOT `os.environ`
- Validate required connection fields at runtime
- No hardcoded credentials

**Example Pattern**:
```python
conn_info = config.get("resolved_connection", {})
if not conn_info or not conn_info.get("api_key"):
    raise ValueError("api_key required")
```

**File Format**:
```yaml
connections:
  shopify:
    default:
      shop_domain: mystore.myshopify.com
      access_token: ${SHOPIFY_TOKEN}
```

---

### 3. Doctor/Healthcheck (DOC-001 to DOC-003)

**What it is**: Optional method to test connection health before pipeline execution.

**SHOULD Have**:
- `doctor(connection: dict, timeout: float = 2.0) -> tuple[bool, dict]`
- Standard error categories: auth, network, permission, timeout, ok, unknown
- No secrets in output

**CLI Test**:
```bash
osiris connections doctor --family <family> --alias <alias> --json
```

**Example Return**:
```python
# Success
return True, {
    "latency_ms": 45.2,
    "category": "ok",
    "message": "Connection successful"
}

# Failure
return False, {
    "latency_ms": None,
    "category": "auth",
    "message": "Invalid token"  # Generic, no secrets!
}
```

---

### 4. Metrics & Events (MET-001 to MET-003)

**What it is**: Components emit data flow metrics; runner emits lifecycle events.

**MUST Have** (by component type):
- **Extractor**: `rows_read` metric
- **Writer**: `rows_written` metric
- **Processor**: `rows_processed` metric

**Pattern**:
```python
if ctx and hasattr(ctx, "log_metric"):
    ctx.log_metric("rows_read", 1000, unit="rows", tags={"step": step_id})
```

**Requirements**:
- Unit parameter: `rows`, `ms`, `bytes`, `seconds`, `files`, `code`, `calls`
- Tags parameter: `{"step": step_id}`
- Check context availability before calling

**CLI Query**:
```bash
osiris logs metrics --session run_XXX --metric rows_read --json
```

---

### 5. Connection Field Override Control (x-connection-fields)

**What it is**: Specification of which config fields come from connections and whether they can be overridden.

**Three Policies**:

| Policy | Use Case | Example | Validation |
|--------|----------|---------|------------|
| `allowed` | Infrastructure | `host`, `port` | No error/warning |
| `forbidden` | Security | `password`, `api_key` | Error if overridden |
| `warning` | Ambiguous | `headers`, `options` | Warning if overridden |

**Spec Example**:
```yaml
x-connection-fields:
  - name: host
    override: allowed        # Test with localhost OK
  - name: password
    override: forbidden      # Cannot override in pipeline
  - name: headers
    override: warning        # Allow but warn user
```

**OML Validation**:
```yaml
steps:
  - id: extract
    config:
      connection: "@mysql.prod"
      host: "localhost"        # ✓ OK: allowed
      password: "hacked"       # ❌ ERROR: forbidden
      table: users
```

---

## 3-Layer OML Validation

### Layer 1: Schema
- Document structure: `oml_version`, `name`, `steps`
- Step structure: `id`, `component`, `mode`
- Component exists, mode supported
- Connection refs: `@family.alias` format

### Layer 2: Semantic (CRITICAL)
- **Writers**: `primary_key` required for `replace`/`upsert`
- **Extractors**: `query` XOR `table` (one or the other, not both)
- **Filesystem**: `path` required

### Layer 3: Runtime
- Secret resolution (env vars exist)
- Connection resolution (@alias → credentials)
- Config merging
- Driver instantiation

**CLI Test**:
```bash
osiris oml validate pipeline.yaml
```

---

## Driver Protocol Contract

**Signature**:
```python
def run(
    self,
    *,  # Keyword-only!
    step_id: str,
    config: dict,
    inputs: dict | None,
    ctx: Any
) -> dict:
```

**MUST**:
- All params keyword-only (use `*`)
- Read from `config["resolved_connection"]`
- Don't mutate inputs
- Check context before calling `ctx.log_metric()`
- Clean up resources in `finally`
- Emit required metric (rows_read/written/processed)

**SHOULD**:
- Log step_id in all messages
- Catch specific exceptions, re-raise as RuntimeError
- Include latency/duration metrics

---

## Component Spec Rules (57 Total)

### Critical (MUST) - 32 Rules

**SPEC Domain** (10):
- Required fields: name, version, modes, capabilities, configSchema
- Name pattern: `^[a-z0-9_.-]+$`
- Version: semantic `major.minor.patch`
- ConfigSchema: valid JSON Schema
- Examples validate against schema
- Secrets use JSON Pointers (`/field` format)

**Capabilities Domain** (4):
- discover mode requires `capabilities.discover: true`
- Mode-specific I/O: extract→df, write→df→{}, transform→df→df
- Don't use deprecated `load` mode
- No streaming support (M1)

**Discovery Domain** (3):
- Declare `discover` mode if capability enabled
- Output deterministic (sorted)
- Include SHA-256 fingerprint

**Connections Domain** (4):
- Use `config["resolved_connection"]`
- Validate required fields
- Doctor returns `tuple[bool, dict]`
- Categories: auth, network, permission, timeout, ok, unknown

**Logging Domain** (3):
- Emit required metric for component type
- Unit parameter required
- Include step tag: `{"step": step_id}`

**Driver Domain** (3):
- Implement `run(*, step_id, config, inputs, ctx)` signature
- No mutation of inputs
- Check context before logging

**Healthcheck Domain** (2):
- Declare capability if implemented
- Timeout defaults to 2.0s

---

### Advisory (SHOULD) - 25 Rules

- Cache discovery results (24h TTL)
- Include estimated counts
- Include field types/nullability
- Implement doctor() method
- Clean up resources
- Structured exception handling
- LLM hints provided
- Input aliases comprehensive
- YAML snippets provided
- Examples include OML snippets
- Deterministic artifacts
- Secret redaction
- Logging policy declared
- Backoff/retry logic
- Output validation

---

## Real Component Examples

### Shopify Extractor (Reference)
- **Modes**: extract, discover
- **Discovery**: Lists customers, orders, products, inventory_items
- **Doctor**: Tests shop API access
- **Metrics**: rows_read, api_calls_made
- **Pagination**: Cursor-based with rate limiting

### MySQL Extractor (Production)
- **Modes**: extract, discover
- **Discovery**: Tables with columns, types, constraints
- **Doctor**: Tests database connection
- **Metrics**: rows_read, bytes_processed
- **Config**: query OR table (mutually exclusive)

### Supabase Writer (Production)
- **Modes**: write, discover
- **Discovery**: Schemas and tables
- **Write Modes**: append, replace, upsert
- **Validation**: primary_key required for replace/upsert
- **Metrics**: rows_written

---

## Validation Checklist

### Specification (spec.yaml)
- [ ] Required fields present
- [ ] Name/version valid
- [ ] Modes list populated
- [ ] ConfigSchema valid JSON Schema
- [ ] Examples validate
- [ ] Secrets use JSON Pointer format
- [ ] x-connection-fields declared (all connection fields)
- [ ] Override policies correct
- [ ] x-runtime.driver valid Python path

### Connection Handling
- [ ] Driver reads from resolved_connection
- [ ] Driver validates required fields
- [ ] Doctor declared if implemented
- [ ] Doctor categories standard
- [ ] Doctor output redacted

### Discovery
- [ ] modes includes "discover"
- [ ] Output matches schema
- [ ] Resources sorted alphabetically
- [ ] Fields sorted alphabetically
- [ ] Fingerprint is SHA-256
- [ ] Output deterministic

### Metrics
- [ ] Correct metric for component type
- [ ] Unit specified
- [ ] Step tag included
- [ ] Context null-check

### Driver
- [ ] Keyword-only parameters
- [ ] resolved_connection used
- [ ] No input mutation
- [ ] Resources cleaned up
- [ ] Exceptions handled

---

## Common Errors & Fixes

| Error | Fix |
|-------|-----|
| `❌ Discovery capability requires 'discover' in modes array` | Add "discover" to modes |
| `❌ Discovery output non-deterministic` | Sort resources and fields alphabetically |
| `❌ Driver reads from environment` | Use `config["resolved_connection"]` |
| `❌ Missing required metric 'rows_read'` | Add `ctx.log_metric("rows_read", ...)` |
| `❌ Metric missing unit` | Add `unit="rows"` parameter |
| `❌ Must check ctx availability` | Add `if ctx and hasattr(ctx, "log_metric")` |
| `❌ primary_key required for upsert` | Add `primary_key` field in config |
| `❌ Cannot specify both query and table` | Use only one |
| `❌ Cannot override forbidden field` | Remove override from step config |
| `❌ Invalid component name` | Use lowercase, dots, dashes, underscores |

---

## CLI Commands for Testing

```bash
# Validate component spec
osiris components validate <name> --level strict

# Test discovery
osiris components discover <name> --connection @alias --json

# Test doctor
osiris connections doctor --family <f> --alias <a> --json

# Validate OML pipeline
osiris oml validate pipeline.yaml

# Query metrics
osiris logs metrics --session run_XXX --metric rows_read --json
```

---

## Key Documents

| Document | Contains |
|----------|----------|
| `COMPONENT_AI_CHECKLIST.md` | 57 machine-verifiable rules (MUST/SHOULD) |
| `discovery_contract.md` | DISC-001 to DISC-006 requirements |
| `connections_doctor_contract.md` | CONN-001 to CONN-002, DOC-001 to DOC-003 |
| `metrics_events_contract.md` | MET-001 to MET-003 + event schemas |
| `x-connection-fields.md` | Override policy specification + examples |
| `oml-validation.md` | 3-layer validation architecture |
| `COMPONENT_CAPABILITIES_DEEP_DIVE.md` | Complete deep dive (this file's companion) |

---

## Quick Start: Building a Component

1. **Specification**: Copy existing component's `spec.yaml`, adapt for your API
2. **Driver**: Implement `run(*, step_id, config, inputs, ctx)` method
3. **Connection**: Use `config["resolved_connection"]`, not environment
4. **Metrics**: Emit rows_read/written/processed with unit and step tag
5. **Validation**: Run `osiris components validate <name> --level strict`
6. **Testing**: Create example pipelines, validate with `osiris oml validate`
7. **Discovery**: Implement `discover()` if introspection possible (SHOULD)
8. **Doctor**: Implement `doctor()` for health checks (SHOULD)

---

**Version**: 1.0  
**Osiris**: v0.5.5  
**Last Updated**: 2025-11-07  
**Status**: Production Ready
