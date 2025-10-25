# Component Spec Quick Reference

A condensed checklist for creating new component specs.

## Checklist: New Component Spec

### Required Top-Level Fields
- [ ] `name: namespace.type` (e.g., `bigquery.extractor`)
- [ ] `version: 1.0.0` (semver)
- [ ] `title: Human Readable Name`
- [ ] `description:` (1-3 sentences about purpose)
- [ ] `modes: [extract|write|discover|transform]` (at least one)
- [ ] `capabilities: {...}` (8 boolean flags)
- [ ] `configSchema: {...}` (JSON Schema for config)
- [ ] `x-runtime: {driver: ..., requirements: ...}`

### Security Configuration
- [ ] `secrets: [/field_names]` (what contains secrets)
- [ ] `x-secret: [...]` (extended paths including resolved_connection)
- [ ] `x-connection-fields: [...]` (per-field override policies)
- [ ] `redaction: {strategy, mask, extras}` (how to mask sensitive data)

### Validation & Clarity
- [ ] `constraints:` (conditional required fields)
- [ ] `examples: [...]` (at least 2, with pragmas for test secrets)
- [ ] `compatibility:` (Python version, dependencies)
- [ ] `llmHints:` (inputAliases, promptGuidance, yamlSnippets, commonPatterns)

### Operations
- [ ] `loggingPolicy:` (sensitivePaths, eventDefaults, metricsToCapture)
- [ ] `limits:` (maxRows, maxSizeMB, maxDurationSeconds, maxConcurrency)

## Naming Conventions

```
Component: {namespace}.{type}
  namespace: mysql, supabase, firebase, bigquery, duckdb, graphql, filesystem, etc.
  type: extractor, writer, processor, connection

Fields: snake_case
  Connections: host, port, user, password, database, schema, api_key
  Auth: auth_type, auth_token, auth_username, auth_header_name
  Modes: mode (MySQL) or write_mode (Supabase) for disambiguation
  Pagination: pagination_enabled, pagination_path, pagination_cursor_field
```

## Configuration Schema Pattern

```yaml
configSchema:
  type: object
  properties:
    required_field:
      type: string
      description: "Clear description"
      minLength: 1
    
    optional_with_default:
      type: integer
      description: "Description"
      default: 10000
      minimum: 100
      maximum: 100000
    
    enum_field:
      type: string
      enum: [value1, value2]
      default: value1
  
  required:
    - required_field
  
  additionalProperties: false  # Always prevent typos
```

## Security Field Settings

| Field Type | Secret? | Override | Redaction |
|------------|---------|----------|-----------|
| `password`, `api_key` | yes | forbidden | yes |
| `auth_token` | yes | forbidden | yes |
| `auth_username` | yes | forbidden | yes |
| `user` | maybe | forbidden | yes |
| `host`, `url` | maybe | allowed | maybe |
| `headers` | maybe | warning | yes |

## x-connection-fields Template

```yaml
x-connection-fields:
  - name: api_key
    override: forbidden          # Secrets: forbidden
  - name: host
    override: allowed            # Non-sensitive: allowed
  - name: headers
    override: warning            # Mixed sensitivity: warning
```

## Authentication Patterns

### Simple API Key
```yaml
configSchema:
  properties:
    api_key:
      type: string
      minLength: 20
secrets: [/api_key]
x-connection-fields:
  - name: api_key, override: forbidden
```

### Database Credentials
```yaml
configSchema:
  properties:
    host: string (default: localhost)
    port: integer (default: 5432)
    user: string
    password: string
    database: string
  required: [host, database, user, password]
secrets: [/password]
x-connection-fields:
  - {name: password, override: forbidden}
  - {name: database, override: forbidden}
  - {name: user, override: forbidden}
  - {name: host, override: allowed}
```

### Multi-Method (bearer, basic, api_key)
```yaml
configSchema:
  properties:
    auth_type: enum [none, bearer, basic, api_key]
    auth_token: string
    auth_username: string
    auth_header_name: string
    headers: object
secrets: [/auth_token, /auth_username, /headers]
constraints:
  required:
    - when: {auth_type: "basic"}
      must: {auth_username, auth_token}
      error: "Basic auth requires username and password"
```

## Constraints Pattern

```yaml
constraints:
  required:
    - when: {field: value}      # Condition
      must: {field: spec}       # What's then required
      error: "Message"          # User-facing error
```

### Examples
```yaml
# Either-or: table XOR query
- when: {query: null}
  must: {table: {minLength: 1}}
  error: "Either 'table' or 'query' must be specified"

# Dependency: upsert needs keys
- when: {write_mode: upsert}
  must: {upsert_keys: {minItems: 1}}
  error: "upsert_keys required for upsert mode"

# Multi-condition: basic auth
- when: {auth_type: "basic"}
  must: 
    auth_username: {minLength: 1}
    auth_token: {minLength: 1}
  error: "Basic auth requires both username and password"
```

## LLM Hints Template

```yaml
llmHints:
  inputAliases:
    field_name:
      - alias1
      - alias2
      - alternative_name
  
  promptGuidance: |
    Use namespace.type to [action].
    Requires [list of required fields].
    Supports [key features].
    Common patterns: [pattern names].
  
  yamlSnippets:
    - "component: namespace.type"
    - "mode: extract"
    - "api_key: '{{ api_key }}'"
  
  commonPatterns:
    - pattern: basic_usage
      description: "Simplest case with defaults"
    - pattern: advanced_usage
      description: "With custom batching"
```

## Examples Structure

```yaml
examples:
  - title: "Descriptive Title"
    config:
      # Complete, valid configuration
      field1: value1
      field2: value2
    notes: "When/why you'd use this pattern"
```

**Rules:**
- First example: Simplest case (maximize defaults)
- Real-world: Use realistic values, not "test123"
- Secrets: Include `# pragma: allowlist secret` comment
- 2+ examples recommended, 3+ for complex components

## Capabilities Flags

All components should include all 8 flags:

```yaml
capabilities:
  discover: false              # Can list tables/schemas?
  adHocAnalytics: false        # Can execute arbitrary queries?
  inMemoryMove: false          # Works with DataFrames?
  streaming: false             # Streaming mode support?
  bulkOperations: true         # Has batch_size optimization?
  transactions: false          # ACID transactions?
  partitioning: false          # Sharding/partitioning?
  customTransforms: false      # SQL/transform support?
```

## Limits Template

```yaml
limits:
  maxRows: 10000000           # Row count limit
  maxSizeMB: 10240            # Data size limit (GB)
  maxDurationSeconds: 3600    # Timeout (seconds)
  maxConcurrency: 5           # Parallel operations
  rateLimit:                  # Optional: API rate limits
    requests: 100
    period: second
```

## x-runtime Template

```yaml
x-runtime:
  driver: osiris.drivers.module_name.DriverClassName
  requirements:
    imports:          # For typing/inspection
      - pandas
      - sqlalchemy
    packages:         # For pip install
      - pandas
      - sqlalchemy
      - pymysql
```

## Complexity Tiers

### Tier 1: Simple (1/5)
- No secrets
- <10 fields
- Single mode
- No constraints
- Examples: filesystem.csv_writer

### Tier 2: Medium (3/5)
- 1 auth method
- 10-20 fields
- 2 modes (extract + discover)
- 1-2 constraints
- Examples: mysql.extractor, supabase.extractor

### Tier 3: Complex (5/5)
- Multiple auth methods
- 20+ fields
- Advanced features
- 3+ constraints
- 3+ real-world examples
- Examples: graphql.extractor, supabase.writer

## Common Mistakes

| Mistake | Impact | Fix |
|---------|--------|-----|
| Missing `additionalProperties: false` | Typos silently fail | Add to configSchema |
| Secrets without `x-secret` | Logged accidentally | Declare in x-secret array |
| Missing `x-connection-fields` | Users override secrets | Define override policies |
| No constraints for conditional logic | LLM generates wrong configs | Add constraints with errors |
| Missing examples | Unclear usage | Add 2+ real-world examples |
| No `llmHints.promptGuidance` | LLM confused by component | Add 3-4 sentence summary |
| Hardcoded paths in driver | Breaks in different environments | Use config-driven paths only |
| Inconsistent field naming | Confusing to users | Follow conventions |

## Files to Create

```
/components/{namespace}.{type}/
  spec.yaml              # This file ✓

/osiris/drivers/
  {name}_driver.py       # Implementation with run() method
  
/tests/
  test_{name}.py         # Component tests
```

## Validation Checklist Before Commit

- [ ] YAML is valid (no syntax errors)
- [ ] All required fields present
- [ ] `additionalProperties: false` on configSchema
- [ ] All secrets declared in `secrets` and `x-secret`
- [ ] All `x-connection-fields` defined
- [ ] At least 2 examples with `# pragma: allowlist secret` comments
- [ ] Constraints cover all conditional logic
- [ ] `llmHints.promptGuidance` is clear and complete
- [ ] Driver class path exists in x-runtime
- [ ] No hardcoded paths in driver
- [ ] Tests pass for component configuration

---

**Generated:** October 25, 2025
