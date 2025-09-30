# Discovery Mode Contract

**Purpose**: Machine-verifiable requirements for discovery mode implementation.

**Scope**: Components with `capabilities.discover: true`

---

## Overview

Discovery mode allows components to introspect available resources (tables, endpoints, schemas) without manual enumeration. This enables AI agents and users to explore data sources dynamically.

---

## MUST Requirements

### DISC-001: Mode Declaration

**Statement**: Component MUST declare `modes: ["discover"]` if `capabilities.discover: true`.

**Validation**:
```python
assert "discover" in spec["modes"]
assert spec["capabilities"]["discover"] is True
```

**Failure**: `❌ Discovery capability requires 'discover' in modes array`

---

### DISC-002: Deterministic Output

**Statement**: Discovery MUST produce sorted, deterministic output.

**Schema**:
```json
{
  "discovered_at": "2025-09-30T12:00:00.000Z",
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
  "fingerprint": "sha256:abc123..."
}
```

**Validation**:
```bash
# Run discovery twice
osiris components discover mycomponent --connection @default --out disc1.json
osiris components discover mycomponent --connection @default --out disc2.json

# Compare (should be identical)
diff disc1.json disc2.json
```

**Failure**: `❌ Discovery output non-deterministic. Sort resources and fields alphabetically.`

---

### DISC-003: Fingerprint Required

**Statement**: Discovery output MUST include SHA-256 fingerprint.

**Purpose**: Cache invalidation, change detection

**Computation**:
```python
import hashlib
import json

def compute_discovery_fingerprint(discovery: dict) -> str:
    """Compute deterministic fingerprint."""
    # Remove fingerprint field itself
    discovery_copy = discovery.copy()
    discovery_copy.pop("fingerprint", None)

    # Sort and hash
    canonical = json.dumps(discovery_copy, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()
```

**Validation**:
```python
discovery = load_discovery_output()
expected = compute_discovery_fingerprint(discovery)
assert discovery["fingerprint"] == f"sha256:{expected}"
```

**Failure**: `❌ Missing or invalid fingerprint. Use SHA-256 hash of sorted output.`

---

## SHOULD Requirements

### DISC-004: Cache Support

**Statement**: Components SHOULD cache discovery results keyed by connection fingerprint.

**Cache Location**: `.osiris_cache/discovery/<family>/<alias>/`

**Cache Entry**:
```json
{
  "cached_at": "2025-09-30T12:00:00.000Z",
  "ttl_seconds": 86400,
  "connection_fingerprint": "sha256:xyz789...",
  "discovery": { /* full discovery output */ }
}
```

**Invalidation**: When connection changes or TTL expires

---

### DISC-005: Estimated Counts

**Statement**: Discovery SHOULD include estimated row/record counts.

**Why**: Helps users and AI agents estimate extraction time and resource needs.

**Example**:
```json
{
  "name": "customers",
  "estimated_row_count": 1500000,
  "estimated_size_mb": 250
}
```

---

### DISC-006: Schema Details

**Statement**: Discovery SHOULD include field types and nullability.

**Why**: Enables type-aware pipeline generation.

**Example**:
```json
{
  "fields": [
    {
      "name": "id",
      "type": "integer",
      "nullable": false,
      "primary_key": true
    },
    {
      "name": "email",
      "type": "string",
      "nullable": true,
      "max_length": 255
    }
  ]
}
```

---

## Discovery Output Schema

**File**: `../schemas/discovery_output.schema.json`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["discovered_at", "resources", "fingerprint"],
  "properties": {
    "discovered_at": {
      "type": "string",
      "format": "date-time",
      "description": "ISO 8601 UTC timestamp"
    },
    "resources": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name", "type"],
        "properties": {
          "name": {"type": "string"},
          "type": {"enum": ["table", "view", "endpoint", "collection"]},
          "estimated_row_count": {"type": "integer", "minimum": 0},
          "fields": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["name", "type"],
              "properties": {
                "name": {"type": "string"},
                "type": {"type": "string"},
                "nullable": {"type": "boolean"},
                "primary_key": {"type": "boolean"}
              }
            }
          }
        }
      }
    },
    "fingerprint": {
      "type": "string",
      "pattern": "^sha256:[a-f0-9]{64}$"
    }
  }
}
```

---

## CLI Commands

### Trigger Discovery

```bash
osiris components discover <component_name> --connection <alias> [--json]
```

**Example**:
```bash
osiris components discover mysql.extractor --connection @mysql.default --json
```

**Expected Output**:
```json
{
  "discovered_at": "2025-09-30T12:00:00.000Z",
  "resources": [
    {"name": "customers", "type": "table", "estimated_row_count": 1000000},
    {"name": "orders", "type": "table", "estimated_row_count": 5000000}
  ],
  "fingerprint": "sha256:abc123..."
}
```

---

### Cache Operations

```bash
# Show cache
osiris cache list discovery

# Invalidate cache
osiris cache clear discovery --family mysql --alias default

# Force refresh
osiris components discover mysql.extractor --connection @mysql.default --refresh
```

---

## Implementation Example

```python
class MySQLExtractorDriver:
    def discover(self, config: dict, ctx: Any = None) -> dict:
        """Discover available tables and schemas."""
        conn_info = config.get("resolved_connection", {})

        # Query information_schema
        tables = self._query_tables(conn_info)

        # Build discovery output
        resources = []
        for table in sorted(tables, key=lambda t: t["name"]):
            fields = self._query_columns(conn_info, table["name"])
            resources.append({
                "name": table["name"],
                "type": "table",
                "estimated_row_count": table["row_count"],
                "fields": sorted(fields, key=lambda f: f["name"])
            })

        discovery = {
            "discovered_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "resources": resources,
            "fingerprint": None  # Will be computed
        }

        # Compute fingerprint
        discovery["fingerprint"] = f"sha256:{self._compute_fingerprint(discovery)}"

        return discovery
```

---

## Validation Checklist

- [ ] `modes` includes `"discover"`
- [ ] `capabilities.discover` is `true`
- [ ] Discovery output matches schema
- [ ] Resources sorted alphabetically
- [ ] Fields sorted alphabetically
- [ ] Fingerprint is SHA-256
- [ ] Timestamp is ISO 8601 UTC
- [ ] Output deterministic (run twice, compare)
- [ ] Cache location follows pattern
- [ ] CLI command works: `osiris components discover <name> --connection @alias --json`

---

## See Also

- **Overview**: `../llms/overview.md`
- **Component Contract**: `../llms/components.md`
- **Full Checklist**: `COMPONENT_AI_CHECKLIST.md`
- **Discovery Schema**: `../schemas/discovery_output.schema.json`
