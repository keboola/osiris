# Component Specification Reference

## Overview

The Component Specification Schema enables Osiris components to be self-describing, providing configuration requirements, capabilities, and security metadata. This allows the LLM to generate valid pipeline configurations and enables automatic secrets masking in logs and artifacts.

## Schema Version

- **Schema Draft**: JSON Schema Draft 2020-12
- **Schema ID**: `https://osiris.ai/schemas/component-spec/v1.0.0`
- **Location**: `components/spec.schema.json`

## Core Fields

### Required Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `name` | string | Component identifier (pattern: `^[a-z0-9_.-]+$`) | `mysql.table` |
| `version` | string | Semantic version (semver) | `1.0.0` |
| `modes` | array | Supported operational modes | `["extract", "load"]` |
| `capabilities` | object | Component capability flags | See Capabilities section |
| `configSchema` | object | JSON Schema for component configuration | See ConfigSchema section |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Human-readable component title |
| `description` | string | Detailed component description |
| `secrets` | array | JSON Pointer paths to secret fields |
| `redaction` | object | Policy for redacting sensitive data |
| `constraints` | object | Cross-field validation rules |
| `examples` | array | Usage examples with config and OML |
| `compatibility` | object | Requirements and conflicts |
| `llmHints` | object | Hints for LLM-driven generation |
| `loggingPolicy` | object | Logging configuration |
| `limits` | object | Resource and operational limits |

## Field Details

### Modes

Available operational modes:
- `extract` - Read data from source
- `load` - Write data to destination
- `transform` - Transform data in-place
- `discover` - Discover schema/metadata
- `analyze` - Perform analytical queries
- `stream` - Stream processing

### Capabilities

Boolean flags indicating component capabilities:

```json
{
  "discover": true,          // Supports schema discovery
  "adHocAnalytics": false,   // Supports ad-hoc queries
  "inMemoryMove": true,      // Supports in-memory transfers
  "streaming": false,        // Supports streaming
  "bulkOperations": true,    // Supports bulk operations
  "transactions": true,      // Supports transactions
  "partitioning": false,     // Supports partitioned processing
  "customTransforms": false  // Supports custom transforms
}
```

### ConfigSchema

The `configSchema` field contains a nested JSON Schema defining the component's configuration:

```json
{
  "configSchema": {
    "type": "object",
    "properties": {
      "connection": {
        "type": "object",
        "properties": {
          "host": {"type": "string"},
          "password": {"type": "string"}
        }
      },
      "table": {"type": "string"}
    },
    "required": ["connection", "table"]
  }
}
```

### Secrets (JSON Pointers)

The `secrets` field uses JSON Pointer notation to identify sensitive fields:

```json
{
  "secrets": [
    "/connection/password",     // Points to connection.password
    "/auth/apiKey",            // Points to auth.apiKey
    "/credentials/privateKey"  // Points to credentials.privateKey
  ]
}
```

**JSON Pointer Syntax**:
- Always starts with `/`
- Path segments separated by `/`
- Array indices as numbers: `/items/0/secret`
- Special characters escaped: `~0` for `~`, `~1` for `/`

### Redaction Policy

Controls how sensitive data is handled in logs:

```json
{
  "redaction": {
    "strategy": "mask",        // mask, drop, or hash
    "mask": "***",             // Mask string (if strategy=mask)
    "extras": [                // Additional paths to redact
      "/connection/host"
    ]
  }
}
```

### Examples

Component usage examples with configuration and OML snippets:

```json
{
  "examples": [
    {
      "title": "Basic MySQL extraction",
      "config": {
        "connection": {
          "host": "localhost",
          "database": "mydb",
          "username": "user",
          "password": "secret"
        },
        "table": "customers"
      },
      "omlSnippet": "type: mysql.table\nconnection: @mysql\ntable: customers",
      "notes": "Requires read permissions"
    }
  ]
}
```

### LLM Hints

Guidance for LLM-driven pipeline generation:

```json
{
  "llmHints": {
    "inputAliases": {
      "table": ["table_name", "source_table"],
      "schema": ["database", "namespace"]
    },
    "promptGuidance": "Use for MySQL operations. Always specify connection and table.",
    "yamlSnippets": [
      "type: mysql.table\nconnection: @mysql"
    ],
    "commonPatterns": [
      {
        "pattern": "bulk_load",
        "description": "Use batchSize for efficiency"
      }
    ]
  }
}
```

### Logging Policy

Defines logging behavior and sensitive data handling:

```json
{
  "loggingPolicy": {
    "sensitivePaths": ["/connection/host"],
    "eventDefaults": ["discovery.start", "transfer.progress"],
    "metricsToCapture": ["rows_read", "rows_written", "duration_ms"]
  }
}
```

## Complete Example

### Minimal Component Spec

```yaml
# components/minimal.example/spec.yaml
name: minimal.example
version: 1.0.0
modes:
  - extract
capabilities:
  discover: true
  streaming: false
configSchema:
  type: object
  properties:
    connection:
      type: string
    source:
      type: string
  required:
    - connection
    - source
```

### Full-Featured Component Spec

```yaml
# components/mysql.table/spec.yaml
name: mysql.table
version: 2.1.0
title: MySQL Table Connector
description: Connect to MySQL tables for ETL operations
modes:
  - extract
  - load
  - discover
  - analyze
capabilities:
  discover: true
  adHocAnalytics: true
  inMemoryMove: false
  streaming: true
  bulkOperations: true
  transactions: true
configSchema:
  type: object
  properties:
    connection:
      type: object
      properties:
        host:
          type: string
        port:
          type: integer
          default: 3306
        database:
          type: string
        username:
          type: string
        password:
          type: string
      required:
        - host
        - database
        - username
        - password
    table:
      type: string
    schema:
      type: string
      default: public
    options:
      type: object
      properties:
        batchSize:
          type: integer
          default: 1000
        timeout:
          type: integer
          default: 30
  required:
    - connection
    - table
secrets:
  - /connection/password
  - /connection/username
redaction:
  strategy: mask
  mask: "****"
  extras:
    - /connection/host
constraints:
  required:
    - when:
        mode: load
      must:
        options:
          batchSize:
            minimum: 1
      error: batchSize must be at least 1 for load mode
  environment:
    python: ">=3.10"
    memory: 512MB
examples:
  - title: Extract from MySQL
    config:
      connection:
        host: localhost
        port: 3306
        database: mydb
        username: reader
        password: secret123
      table: customers
      schema: public
    omlSnippet: |
      type: mysql.table
      connection: @mysql
      table: customers
      schema: public
    notes: Requires SELECT permissions
  - title: Load to MySQL with batching
    config:
      connection:
        host: db.example.com
        database: warehouse
        username: writer
        password: secret456
      table: orders
      options:
        batchSize: 5000
        timeout: 60
    omlSnippet: |
      type: mysql.table
      connection: @mysql_prod
      table: orders
      options:
        batchSize: 5000
compatibility:
  requires:
    - python>=3.10
    - mysql>=8.0
  conflicts:
    - postgres
  platforms:
    - linux
    - darwin
    - docker
llmHints:
  inputAliases:
    table:
      - table_name
      - source_table
      - target_table
    schema:
      - database
      - namespace
      - db
  promptGuidance: |
    Use mysql.table for MySQL database operations.
    Always specify both connection and table.
    For bulk operations, set appropriate batchSize in options.
  yamlSnippets:
    - "type: mysql.table"
    - "connection: @mysql"
    - "table: {{ table_name }}"
    - "schema: {{ schema_name }}"
  commonPatterns:
    - pattern: bulk_extract
      description: Use batchSize for efficient extraction
    - pattern: upsert
      description: Use merge mode with appropriate keys
loggingPolicy:
  sensitivePaths:
    - /connection/host
    - /connection/port
  eventDefaults:
    - discovery.start
    - discovery.complete
    - transfer.start
    - transfer.progress
    - transfer.complete
  metricsToCapture:
    - rows_read
    - rows_written
    - bytes_processed
    - duration_ms
limits:
  maxRows: 1000000
  maxSizeMB: 1024
  maxDurationSeconds: 3600
  maxConcurrency: 10
  rateLimit:
    requests: 100
    period: minute
```

## Integration with Osiris

### Registry Usage (M1a.3)

The Component Registry will use these specifications to:
1. **Validate configurations** against `configSchema`
2. **Apply secrets masking** using `secrets` and `redaction` fields
3. **Generate LLM context** from `llmHints` and examples
4. **Enforce limits** during execution
5. **Configure logging** based on `loggingPolicy`

### Helper Functions (TODO)

Integration helpers to be implemented in `osiris/components/utils.py`:

```python
def collect_secret_paths(spec: dict) -> set[str]:
    """Collect all secret paths from spec"""
    paths = set(spec.get("secrets", []))
    if "redaction" in spec:
        paths.update(spec["redaction"].get("extras", []))
    if "loggingPolicy" in spec:
        paths.update(spec["loggingPolicy"].get("sensitivePaths", []))
    return paths

def redaction_policy(spec: dict) -> RedactionPolicy:
    """Extract redaction policy from spec"""
    policy = spec.get("redaction", {})
    return RedactionPolicy(
        strategy=policy.get("strategy", "mask"),
        mask=policy.get("mask", "***"),
        paths=collect_secret_paths(spec)
    )
```

## Validation

All component specifications must:
1. Pass JSON Schema validation against `spec.schema.json`
2. Have unique component names
3. Use valid semantic versioning
4. Provide valid JSON Pointers for secrets
5. Include at least one operational mode
6. Define required capabilities

## Best Practices

1. **Secrets**: Always use JSON Pointers for secret fields
2. **Examples**: Provide 1-2 clear, working examples
3. **LLM Hints**: Keep `promptGuidance` concise (≤500 chars)
4. **Constraints**: Document cross-field dependencies clearly
5. **Versioning**: Follow semantic versioning strictly
6. **Documentation**: Use `title` and `description` for clarity

## Migration Notes

When updating component specifications:
1. Increment version following semver
2. Maintain backward compatibility when possible
3. Document breaking changes in constraints
4. Update examples to reflect changes
5. Test with existing pipelines before deployment
