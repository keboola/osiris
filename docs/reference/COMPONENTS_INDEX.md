# Osiris Component Documentation Index

**Purpose**: Navigation guide to all component-related documentation  
**Updated**: 2025-11-07

---

## Quick Navigation

### For Component Developers (Getting Started)
1. **Start here**: [COMPONENT_CAPABILITIES_SUMMARY.md](COMPONENT_CAPABILITIES_SUMMARY.md) (10 min read)
2. **Deep dive**: [COMPONENT_CAPABILITIES_DEEP_DIVE.md](COMPONENT_CAPABILITIES_DEEP_DIVE.md) (30 min reference)
3. **Reference examples**: 
   - `/docs/developer-guide/human/examples/shopify.extractor/`
   - `/components/mysql.extractor/spec.yaml`
   - `/components/supabase.writer/spec.yaml`

### For Component Reviewers
1. **Checklist**: [COMPONENT_AI_CHECKLIST.md](../developer-guide/ai/checklists/COMPONENT_AI_CHECKLIST.md) (57 rules)
2. **Contract details**: [COMPONENT_CAPABILITIES_DEEP_DIVE.md](COMPONENT_CAPABILITIES_DEEP_DIVE.md) (all contracts)
3. **Validation**: `osiris components validate <name> --level strict`

### For LLM-Driven Generation
1. **Discovery**: [discovery_contract.md](../developer-guide/ai/checklists/discovery_contract.md)
2. **OML Validation**: [oml-validation.md](oml-validation.md)
3. **Connection Fields**: [x-connection-fields.md](x-connection-fields.md)

---

## Document Map

### Core Capability Documentation

| Document | Purpose | Audience | Length |
|----------|---------|----------|--------|
| [COMPONENT_CAPABILITIES_SUMMARY.md](COMPONENT_CAPABILITIES_SUMMARY.md) | Quick reference (one-page cheat sheet) | All developers, team leads | 360 lines |
| [COMPONENT_CAPABILITIES_DEEP_DIVE.md](COMPONENT_CAPABILITIES_DEEP_DIVE.md) | Comprehensive deep dive with all requirements | Component developers, reviewers | 1,727 lines |
| [COMPONENT_AI_CHECKLIST.md](../developer-guide/ai/checklists/COMPONENT_AI_CHECKLIST.md) | 57 machine-verifiable rules (MUST/SHOULD) | CI systems, AI agents, reviewers | 576 lines |

### Capability-Specific Contracts

| Document | Scope | Rules |
|----------|-------|-------|
| [discovery_contract.md](../developer-guide/ai/checklists/discovery_contract.md) | Discovery mode introspection | DISC-001 to DISC-006 |
| [connections_doctor_contract.md](../developer-guide/ai/checklists/connections_doctor_contract.md) | Connection resolution & health checks | CONN-001 to CONN-002, DOC-001 to DOC-003 |
| [metrics_events_contract.md](../developer-guide/ai/checklists/metrics_events_contract.md) | Telemetry and observability | MET-001 to MET-003 |

### OML & Validation

| Document | Purpose |
|----------|---------|
| [oml-validation.md](oml-validation.md) | 3-layer OML validation architecture (schema, semantic, runtime) |
| [x-connection-fields.md](x-connection-fields.md) | Connection field override control (allowed/forbidden/warning policies) |
| [pipeline-format.md](pipeline-format.md) | OML v0.1.0 syntax reference |
| [oml-v0.1.0-spec.md](../adr/0014-OML_v0.1.0-scope-and-schema.md) | Complete OML specification |

### Component Specification Reference

| Document | Purpose |
|----------|---------|
| [components-spec.md](components-spec.md) | Component spec.yaml format and validation |
| [component-spec-quickref.md](component-spec-quickref.md) | Quick reference for spec.yaml fields |
| [component-creation-guide.md](component-creation-guide.md) | Step-by-step guide for building components |

### Architecture & Design

| Document | Purpose |
|----------|---------|
| [component-specs-analysis.md](component-specs-analysis.md) | Analysis of production component specs |
| [connection-fields.md](connection-fields.md) | Connection field configuration |
| [events_and_metrics_schema.md](events_and_metrics_schema.md) | Metrics and events JSON schema |

---

## 5 Core Component Capabilities

### 1. Discovery Mode
**Document**: [discovery_contract.md](../developer-guide/ai/checklists/discovery_contract.md)

Components introspect available resources (tables, endpoints, schemas) without manual enumeration. This is critical for LLM-driven pipeline generation.

**Key Rules**:
- DISC-001: Mode declaration (modes: ["discover"])
- DISC-002: Deterministic, sorted output
- DISC-003: SHA-256 fingerprint
- DISC-004: Caching support (SHOULD)
- DISC-005: Estimated counts (SHOULD)
- DISC-006: Schema details (SHOULD)

**CLI**: `osiris components discover <name> --connection @alias --json`

---

### 2. Connection Resolution
**Document**: [connections_doctor_contract.md](../developer-guide/ai/checklists/connections_doctor_contract.md)

Components receive credentials from `osiris_connections.yaml` via `config["resolved_connection"]`. Never read from environment variables.

**Key Rules**:
- CONN-001: Use resolved_connection (MUST)
- CONN-002: Validate required fields (MUST)

**Pattern**:
```python
conn_info = config.get("resolved_connection", {})
if not conn_info.get("api_key"):
    raise ValueError("api_key required")
```

**File**: `osiris_connections.yaml` with structure:
```yaml
connections:
  shopify:
    default:
      shop_domain: mystore.myshopify.com
      access_token: ${SHOPIFY_TOKEN}
```

---

### 3. Doctor/Healthcheck
**Document**: [connections_doctor_contract.md](../developer-guide/ai/checklists/connections_doctor_contract.md)

Optional method to test connection health before pipeline execution.

**Key Rules**:
- DOC-001: Implement doctor() method (SHOULD)
- DOC-002: Standard error categories (MUST)
- DOC-003: Redaction-safe output (MUST)

**Signature**:
```python
def doctor(self, connection: dict, timeout: float = 2.0) -> tuple[bool, dict]:
    return (ok: bool, details: {latency_ms, category, message})
```

**Categories**: auth, network, permission, timeout, ok, unknown

**CLI**: `osiris connections doctor --family <family> --alias <alias> --json`

---

### 4. Metrics & Events
**Document**: [metrics_events_contract.md](../developer-guide/ai/checklists/metrics_events_contract.md)

Components emit data flow metrics; runner emits lifecycle events.

**Key Rules**:
- MET-001: Required metrics by type (MUST)
- MET-002: Unit specified (MUST)
- MET-003: Tags include step ID (MUST)

**Required Metrics**:
- Extractor: `rows_read` (unit: rows)
- Writer: `rows_written` (unit: rows)
- Processor: `rows_processed` (unit: rows)

**Pattern**:
```python
if ctx and hasattr(ctx, "log_metric"):
    ctx.log_metric("rows_read", 1000, unit="rows", tags={"step": step_id})
```

**CLI**: `osiris logs metrics --session run_XXX --metric rows_read --json`

---

### 5. Connection Field Override Control
**Document**: [x-connection-fields.md](x-connection-fields.md)

Declares which config fields come from connections and whether they can be overridden in step configs.

**Key Rules**:
- Three policies: `allowed`, `forbidden`, `warning`
- Enforced by OML validator (layer 2 semantic validation)

**Specification**:
```yaml
x-connection-fields:
  - name: host
    override: allowed        # Infrastructure
  - name: password
    override: forbidden      # Security
  - name: headers
    override: warning        # Ambiguous
```

**OML Validation Enforces**:
- Override forbidden → Error, pipeline blocked
- Override allowed → No error
- Override warning → Warning emitted, execution continues

---

## 3-Layer OML Validation

**Document**: [oml-validation.md](oml-validation.md)

### Layer 1: Schema Validation
Structure and types - document, steps, components, modes, connection refs, dependencies.

### Layer 2: Semantic Validation
Business logic rules - primary_key for replace/upsert, query XOR table, path required for filesystem.

### Layer 3: Runtime Validation
Execution readiness - secret resolution, connection resolution, config merging, driver instantiation.

**CLI**: `osiris oml validate pipeline.yaml`

---

## Component Specification (spec.yaml)

**Document**: [components-spec.md](components-spec.md)

**Required Fields**:
- `name`: Component identifier (e.g., `mysql.extractor`)
- `version`: Semantic version (e.g., `1.0.0`)
- `modes`: Array of supported modes (extract, write, transform, discover)
- `capabilities`: Object with boolean flags (discover, streaming, etc.)
- `configSchema`: JSON Schema Draft 2020-12

**Connection Fields**:
```yaml
x-connection-fields:
  - name: host
    override: allowed
  - name: password
    override: forbidden
```

**Secrets & Redaction**:
```yaml
secrets:
  - /password
  - /api_key

redaction:
  strategy: mask
  mask: "****"
  extras:
    - /host
```

**LLM Hints**:
```yaml
llmHints:
  inputAliases:
    host: [hostname, server, mysql_host]
  promptGuidance: Use mysql.extractor to read from MySQL...
  yamlSnippets:
    - "component: mysql.extractor"
    - "mode: read"
```

---

## Driver Implementation

**Document**: [COMPONENT_CAPABILITIES_DEEP_DIVE.md](COMPONENT_CAPABILITIES_DEEP_DIVE.md) (Driver Implementation Contract section)

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

**MUST Requirements**:
- All parameters keyword-only (use `*`)
- Read from `config["resolved_connection"]`
- Don't mutate `inputs`
- Check context before `ctx.log_metric()`
- Clean up resources in `finally`
- Emit required metric

**Return Values**:
- Extract/Transform: `{"df": DataFrame}`
- Write: `{}`

---

## Real Component Examples

### Shopify Extractor (Reference Implementation)
**Location**: `/docs/developer-guide/human/examples/shopify.extractor/`

Features:
- Pagination with cursor-based offset
- Rate limiting (2 req/sec)
- Doctor method for health checks
- Discovery mode
- Proper metric emission

**Files**:
- `spec.yaml`: Component specification
- `driver_skeleton.py`: Reference driver
- `discovery.sample.json`: Example discovery output
- `connections.example.yaml`: Connection configuration

### MySQL Extractor (Production)
**Location**: `/components/mysql.extractor/`

Features:
- Discovery mode (tables, columns, types)
- Custom SQL queries
- Pagination with batch_size
- Connection pooling
- Doctor method

### Supabase Writer (Production)
**Location**: `/components/supabase.writer/`

Features:
- Multiple write modes (append, replace, upsert)
- Semantic validation (primary_key required for upsert)
- Discovery mode
- REST API integration
- Batch operations

---

## Validation Tools

### Component Specification Validation
```bash
# Basic validation
osiris components validate <name> --level basic

# Enhanced validation (examples checked)
osiris components validate <name> --level enhanced

# Strict validation (all rules)
osiris components validate <name> --level strict --json
```

### Discovery Testing
```bash
osiris components discover <name> --connection @alias --json
```

### Doctor/Healthcheck Testing
```bash
# Test all connections
osiris connections doctor --json

# Test specific connection
osiris connections doctor --family <family> --alias <alias> --json
```

### OML Validation
```bash
osiris oml validate pipeline.yaml
```

### Metrics & Events Query
```bash
osiris logs metrics --session run_XXX --metric rows_read --json
osiris logs events --session run_XXX --event step_complete --json
```

---

## Common Patterns

### Discovery Implementation
```python
def discover(self, config: dict, ctx: Any = None) -> dict:
    conn_info = config.get("resolved_connection", {})
    resources = []
    for resource_name in [...]:
        fields = [...]
        resources.append({
            "name": resource_name,
            "type": "table",
            "estimated_row_count": ...,
            "fields": sorted(fields, key=lambda f: f["name"])
        })
    discovery = {
        "discovered_at": datetime.utcnow().isoformat().replace("+00:00", "Z"),
        "resources": sorted(resources, key=lambda r: r["name"]),
        "fingerprint": None
    }
    discovery["fingerprint"] = f"sha256:{compute_fingerprint(discovery)}"
    return discovery
```

### Connection Reading
```python
def run(self, *, step_id: str, config: dict, inputs: dict | None, ctx: Any = None) -> dict:
    conn_info = config.get("resolved_connection", {})
    if not conn_info:
        raise ValueError(f"Step {step_id}: resolved_connection required")
    
    # Extract connection fields
    host = conn_info.get("host")
    password = conn_info.get("password")
    # ... rest of implementation
```

### Metric Emission
```python
if ctx and hasattr(ctx, "log_metric"):
    ctx.log_metric("rows_read", len(df), unit="rows", tags={"step": step_id})
    ctx.log_metric("duration_ms", duration, unit="ms", tags={"step": step_id})
```

### Doctor Implementation
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
            "message": "Connection successful"
        }
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            return False, {
                "latency_ms": None,
                "category": "auth",
                "message": "Invalid credentials"
            }
        # ... more error categories
```

---

## Checklist: Building a Compliant Component

- [ ] Spec file with required fields (name, version, modes, capabilities, configSchema)
- [ ] Component name matches pattern `^[a-z0-9_.-]+$`
- [ ] Version follows semantic versioning
- [ ] All examples validate against configSchema
- [ ] Secrets declared as JSON Pointers
- [ ] x-connection-fields declared with override policies
- [ ] x-runtime.driver points to valid Python class
- [ ] Driver implements `run(*, step_id, config, inputs, ctx)` signature
- [ ] Driver reads from `config["resolved_connection"]`
- [ ] Required metric emitted with unit and step tag
- [ ] Context null-check before `ctx.log_metric()`
- [ ] Discovery mode implemented (if declared)
- [ ] Doctor method implemented (if declared)
- [ ] All resources/fields in discovery sorted alphabetically
- [ ] Discovery output includes SHA-256 fingerprint
- [ ] OML examples validate with `osiris oml validate`
- [ ] Component validates with `osiris components validate <name> --level strict`
- [ ] Tests pass

---

## Error Reference

| Error | Document Reference |
|-------|-------------------|
| `❌ Discovery capability requires 'discover' in modes array` | discovery_contract.md (DISC-001) |
| `❌ Discovery output non-deterministic` | discovery_contract.md (DISC-002) |
| `❌ Missing or invalid fingerprint` | discovery_contract.md (DISC-003) |
| `❌ Driver reads from environment` | connections_doctor_contract.md (CONN-001) |
| `❌ Missing required metric` | metrics_events_contract.md (MET-001) |
| `❌ primary_key required for upsert` | oml-validation.md (Layer 2 Semantic) |
| `❌ Cannot specify both query and table` | oml-validation.md (Layer 2 Semantic) |
| `❌ Cannot override forbidden field` | x-connection-fields.md (Override Policy) |
| `❌ Invalid component name` | COMPONENT_AI_CHECKLIST.md (SPEC-002) |

---

## Contact & Support

- **Documentation**: See `/docs/` directory
- **Examples**: See `/docs/developer-guide/human/examples/`
- **Component Registry**: See `/components/` directory
- **ADRs**: See `/docs/adr/` for architecture decisions
- **Developer Guide**: See `/docs/developer-guide/` for detailed guides

---

**Version**: 1.0  
**Last Updated**: 2025-11-07  
**Osiris Version**: v0.5.5  
**Status**: Production Ready
