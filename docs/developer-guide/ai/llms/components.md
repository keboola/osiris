# LLM Contract: Component Specs

**Purpose**: AI patterns for generating and validating component specifications.

**Audience**: AI agents, LLMs generating Osiris components

---

## Component Spec Structure

```yaml
name: <family>.<type>         # e.g., mysql.extractor
version: 1.0.0                # SemVer
description: Human-readable description
modes: [extract, write, discover]  # At least one
capabilities:
  discover: true              # Optional
  bulkOperations: true        # Optional
  doctor: true                # Optional (if healthcheck implemented)
configSchema:
  type: object
  required: [query]           # Required config fields
  properties:
    query:
      type: string
      description: SQL query to execute
secrets:
  - /connection/password      # JSON Pointer notation
  - /connection/api_key
```

---

## Naming Conventions

### COMP-001: Family.Type Pattern

**Statement**: Component name MUST follow `<family>.<type>` pattern.

**Pattern**: `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`

**Examples**:
```yaml
# ✓ Correct
name: mysql.extractor
name: shopify.extractor
name: csv.writer
name: duckdb.processor

# ✗ Wrong
name: MySQLExtractor        # No family
name: mysql-extractor       # Wrong separator
name: MySQL.Extractor       # Capital letters
```

---

### COMP-002: Type Vocabulary

**Statement**: Type MUST be from standard vocabulary.

**Standard Types**:
- `extractor` - Reads data from source
- `writer` - Writes data to destination
- `processor` - Transforms data (SQL, DuckDB)
- `loader` - Combines extract + write
- `validator` - Data quality checks
- `monitor` - Observability components

**Custom Types**: Allowed but discouraged unless truly necessary.

---

## Mode Definitions

### COMP-003: Mode-Capability Alignment

**Statement**: If `capabilities.discover: true`, then `modes` MUST include `"discover"`.

**Correct**:
```yaml
modes: [extract, discover]
capabilities:
  discover: true
```

**Wrong**:
```yaml
modes: [extract]
capabilities:
  discover: true  # ❌ Mismatch: discover capability requires discover mode
```

---

### COMP-004: Mode Descriptions

**Statement**: Each mode should have clear semantics.

**Mode Semantics**:
- `extract` - Fetch data from external source, return DataFrame/dict
- `write` - Persist data to external destination
- `discover` - Introspect available resources (tables, endpoints)
- `validate` - Check data quality, return validation report
- `transform` - Modify data structure (DuckDB SQL)

---

## Config Schema Generation

### COMP-005: JSON Schema Compatibility

**Statement**: `configSchema` MUST be valid JSON Schema Draft 7.

**Example**:
```yaml
configSchema:
  type: object
  required: [resource, date_from]
  properties:
    resource:
      type: string
      enum: [customers, orders, products]
      description: Shopify resource to extract
    date_from:
      type: string
      format: date
      description: Start date for extraction (ISO 8601)
    limit:
      type: integer
      minimum: 1
      maximum: 10000
      default: 1000
      description: Max records per request
```

---

### COMP-006: Connection Reference

**Statement**: If component uses connections, `configSchema` MUST declare `connection` field.

**Pattern**:
```yaml
configSchema:
  type: object
  required: [connection, query]
  properties:
    connection:
      type: string
      pattern: "^@[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$"
      description: Connection alias (@family.alias)
    query:
      type: string
      description: SQL query to execute
```

**Usage in Pipeline**:
```yaml
steps:
  - id: extract_users
    driver: mysql.extractor
    config:
      connection: "@mysql.default"
      query: "SELECT * FROM users"
```

---

### COMP-007: Enum Validation

**Statement**: Use `enum` for closed sets, avoid open-ended strings.

**Correct**:
```yaml
properties:
  resource:
    enum: [customers, orders, products]  # ✓ Finite set
```

**Wrong**:
```yaml
properties:
  resource:
    type: string  # ❌ Too broad, allows typos
```

---

## Secrets Declaration

### COMP-008: JSON Pointer Notation

**Statement**: Secrets MUST use JSON Pointer notation (RFC 6901).

**Syntax**: `/path/to/field`

**Examples**:
```yaml
secrets:
  - /connection/password           # config["connection"]["password"]
  - /connection/api_key            # config["connection"]["api_key"]
  - /auth/token                    # config["auth"]["token"]
  - /credentials/service_account   # config["credentials"]["service_account"]
```

**Array Access**:
```yaml
secrets:
  - /hosts/0/password  # config["hosts"][0]["password"]
```

---

### COMP-009: Pattern-Based Detection

**Statement**: If secret field name matches pattern, MUST be declared.

**Secret Patterns**:
```regex
password
token
key
secret
credential
api_key
service_account
private_key
```

**Auto-Detection**: Runner automatically redacts fields matching these patterns.

---

## Capabilities Declaration

### COMP-010: Discovery Capability

**Statement**: If component implements `discover()`, declare `capabilities.discover: true`.

**Implementation**:
```yaml
capabilities:
  discover: true
```

**Driver Implementation**:
```python
def discover(self, config: dict, ctx=None) -> dict:
    """Return discovery output matching schema."""
    return {
        "discovered_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "resources": [...],
        "fingerprint": f"sha256:{compute_fingerprint(...)}"
    }
```

---

### COMP-011: Doctor Capability

**Statement**: If component implements `doctor()`, declare `capabilities.doctor: true`.

**Implementation**:
```yaml
capabilities:
  doctor: true
```

**Driver Implementation**:
```python
def doctor(self, connection: dict, timeout: float = 2.0) -> tuple[bool, dict]:
    """Test connection health."""
    try:
        response = requests.get(health_url, timeout=timeout)
        response.raise_for_status()
        return True, {"latency_ms": 50, "category": "ok", "message": "Connected"}
    except requests.exceptions.Timeout:
        return False, {"latency_ms": None, "category": "timeout", "message": "Timed out"}
```

---

### COMP-012: Bulk Operations

**Statement**: If component supports bulk operations (e.g., GraphQL bulk queries), declare `capabilities.bulkOperations: true`.

**Use Case**: Shopify GraphQL bulk queries, BigQuery batch exports

**Implementation**:
```yaml
capabilities:
  bulkOperations: true
```

---

## Validation Levels

### COMP-013: Basic Validation

**Statement**: All specs MUST pass basic validation (required fields, JSON Schema).

**Command**:
```bash
osiris components validate <name> --level basic
```

**Checks**:
- Required fields present: `name`, `version`, `modes`, `capabilities`, `configSchema`
- Valid SemVer version
- `configSchema` is valid JSON Schema
- Secrets use JSON Pointer notation

---

### COMP-014: Enhanced Validation

**Statement**: Specs SHOULD pass enhanced validation (examples, driver existence).

**Command**:
```bash
osiris components validate <name> --level enhanced
```

**Checks**:
- Driver file exists at `osiris/drivers/<family>/<type>.py`
- Driver implements required methods for declared modes
- Examples in spec are runnable
- Connection family exists in `osiris_connections.yaml`

---

### COMP-015: Strict Validation

**Statement**: Production specs MUST pass strict validation (semantic checks).

**Command**:
```bash
osiris components validate <name> --level strict
```

**Checks**:
- Mode-capability alignment (COMP-003)
- Secrets declared for sensitive fields
- Description is meaningful (not placeholder)
- Version matches driver implementation
- Examples use valid connection aliases

---

## Example Generation

### COMP-016: Runnable Examples

**Statement**: Spec SHOULD include at least one runnable example.

**Structure**:
```yaml
examples:
  - name: Extract recent orders
    description: Fetch orders from last 30 days
    config:
      connection: "@shopify.default"
      resource: orders
      date_from: "2025-09-01"
      limit: 1000
```

**Usage**:
```bash
osiris components run <name> --example "Extract recent orders"
```

---

### COMP-017: Example Coverage

**Statement**: Examples SHOULD cover all major config permutations.

**Coverage Matrix**:
```yaml
examples:
  - name: Extract customers
    config:
      resource: customers
  - name: Extract orders
    config:
      resource: orders
  - name: Extract with date filter
    config:
      resource: orders
      date_from: "2025-09-01"
  - name: Extract with pagination
    config:
      resource: products
      limit: 500
```

---

## Registry Integration

### COMP-018: Registration

**Statement**: Component MUST be registered via `ComponentRegistry.register()`.

**Location**: `osiris/components/registry.py`

**Implementation**:
```python
from osiris.components.registry import ComponentRegistry

registry = ComponentRegistry()

# Register component
registry.register(
    name="shopify.extractor",
    spec_path="osiris/components/specs/shopify.extractor.yaml",
    driver_module="osiris.drivers.shopify.extractor"
)
```

---

### COMP-019: Discovery

**Statement**: Components MUST be discoverable via `osiris components list`.

**Command**:
```bash
osiris components list --json
```

**Expected Output**:
```json
[
  {
    "name": "shopify.extractor",
    "version": "1.0.0",
    "modes": ["extract", "discover"],
    "capabilities": {"discover": true, "bulkOperations": true}
  }
]
```

---

## Version Management

### COMP-020: SemVer Compliance

**Statement**: Version MUST follow Semantic Versioning (SemVer 2.0.0).

**Pattern**: `^[0-9]+\.[0-9]+\.[0-9]+$`

**Rules**:
- MAJOR: Breaking changes to config schema or driver protocol
- MINOR: New capabilities, backward-compatible features
- PATCH: Bug fixes, no API changes

**Examples**:
```yaml
version: 1.0.0    # Initial release
version: 1.1.0    # Added discovery mode
version: 1.1.1    # Fixed pagination bug
version: 2.0.0    # Changed config schema (breaking)
```

---

### COMP-021: Version Synchronization

**Statement**: Spec version and driver version MUST match.

**Spec**:
```yaml
name: shopify.extractor
version: 1.2.0
```

**Driver**:
```python
class ShopifyExtractorDriver:
    __version__ = "1.2.0"  # Must match spec
```

---

## AI Generation Workflow

### Step 1: Understand Requirements

**Input**: User intent, data source documentation

**Output**: Draft spec with name, modes, capabilities

**Example**:
```markdown
User: "I need to extract Shopify orders and customers"

AI Analysis:
- Family: shopify
- Type: extractor
- Modes: extract, discover
- Capabilities: discover (Shopify API supports introspection), bulkOperations (GraphQL bulk)
- Secrets: api_key, access_token
```

---

### Step 2: Generate Config Schema

**Input**: API documentation, required/optional parameters

**Output**: JSON Schema with validation rules

**Example**:
```yaml
configSchema:
  type: object
  required: [connection, resource]
  properties:
    connection:
      type: string
      pattern: "^@shopify\\.[a-z0-9_]+$"
    resource:
      enum: [customers, orders, products, inventory_items]
    date_from:
      type: string
      format: date
    limit:
      type: integer
      minimum: 1
      maximum: 10000
      default: 1000
```

---

### Step 3: Declare Secrets

**Input**: Config schema, API documentation

**Output**: JSON Pointers for sensitive fields

**Pattern Matching**:
```python
sensitive_fields = ["password", "token", "key", "secret", "credential"]
for field in config_schema["properties"]:
    if any(pattern in field.lower() for pattern in sensitive_fields):
        secrets.append(f"/{field}")
```

**Example**:
```yaml
secrets:
  - /connection/access_token
  - /connection/api_key
```

---

### Step 4: Add Examples

**Input**: Spec, common use cases

**Output**: At least 2 runnable examples

**Example**:
```yaml
examples:
  - name: Extract recent orders
    config:
      connection: "@shopify.default"
      resource: orders
      date_from: "2025-09-01"
  - name: Extract all customers
    config:
      connection: "@shopify.default"
      resource: customers
```

---

### Step 5: Validate

**Input**: Generated spec

**Output**: Validation report

**Command**:
```bash
osiris components validate shopify.extractor --level strict
```

**Expected Output**:
```
✓ Required fields present
✓ Valid SemVer version
✓ Config schema valid
✓ Secrets declared
✓ Mode-capability alignment
✓ Examples runnable
```

---

## Common Pitfalls

### Pitfall 1: Missing Secrets

**Problem**: Sensitive fields not declared in `secrets`

**Detection**:
```bash
osiris components validate <name> --level strict
# ❌ Warning: Field 'api_key' looks sensitive but not in secrets array
```

**Fix**: Add to secrets array using JSON Pointer notation

---

### Pitfall 2: Invalid JSON Schema

**Problem**: `configSchema` not valid JSON Schema Draft 7

**Detection**:
```bash
osiris components validate <name> --level basic
# ❌ Error: configSchema.properties.limit.minimum: must be number
```

**Fix**: Ensure all JSON Schema keywords are valid

---

### Pitfall 3: Mode-Capability Mismatch

**Problem**: Declared capability without corresponding mode

**Detection**:
```bash
osiris components validate <name> --level strict
# ❌ Error: capabilities.discover=true but 'discover' not in modes
```

**Fix**: Add `discover` to `modes` array

---

## See Also

- **Overview**: `overview.md`
- **Driver Contract**: `drivers.md`
- **Connector Contract**: `connectors.md`
- **Full Checklist**: `../checklists/COMPONENT_AI_CHECKLIST.md`
- **Component Spec Schema**: `../schemas/component_spec.schema.json`
