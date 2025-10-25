# Component Specs Analysis Report
## Osiris Component Architecture Patterns & Best Practices

**Analysis Date:** October 25, 2025  
**Components Analyzed:** 7 (filesystem.csv_writer, mysql.extractor, mysql.writer, supabase.extractor, supabase.writer, duckdb.processor, graphql.extractor)

---

## 1. Component Structure Overview

### Directory Structure
Each component lives in `/components/{namespace}.{type}/` and contains:
- `spec.yaml` - Complete component specification
- `driver_*.py` - Implementation in `/osiris/drivers/`

### Example Path
```
/components/mysql.extractor/spec.yaml
→ Driver: osiris.drivers.mysql_extractor_driver.MySQLExtractorDriver
```

---

## 2. Required vs Optional Spec Fields

### Top-Level Required Fields
| Field | Type | Purpose |
|-------|------|---------|
| `name` | string | Namespace.type identifier (e.g., `mysql.extractor`) |
| `version` | string | Semver format (e.g., `1.0.0`) |
| `title` | string | Human-readable name |
| `description` | string | What the component does |
| `modes` | array | Operational modes: `extract`, `write`, `discover`, `transform` |
| `capabilities` | object | Boolean feature flags |
| `configSchema` | object | JSON Schema for configuration validation |
| `x-runtime` | object | Driver class path and requirements |

### Top-Level Optional But Highly Recommended
| Field | Type | When to Use |
|-------|------|------------|
| `secrets` | array | List of secret paths (e.g., `/password`) |
| `x-secret` | array | Extended secret paths including resolved connections |
| `x-connection-fields` | array | Define per-field override policies |
| `redaction` | object | Masking strategy for sensitive data |
| `constraints` | object | Conditional validation rules |
| `examples` | array | Configuration examples with descriptions |
| `compatibility` | object | Python version, dependencies, platforms |
| `llmHints` | object | Input aliases, guidance, YAML snippets for LLM |
| `loggingPolicy` | object | Sensitive paths, events, metrics |
| `limits` | object | Performance boundaries (maxRows, maxSizeMB, etc.) |

### configSchema.properties Structure
```yaml
configSchema:
  type: object
  properties:
    field_name:
      type: [string|integer|boolean|array|object]
      description: "Clear description"
      default: value                    # Optional
      minLength/minimum: N              # Validation
      maxLength/maximum: N              # Validation
      enum: [val1, val2]               # Restricted values
      pattern: "regex"                 # String validation
      required: [field1, field2]       # At root level
  additionalProperties: false          # Strict schema
```

### Key Patterns

1. **No field-level `required`** - Use `configSchema.required` array instead
2. **Always use `additionalProperties: false`** - Prevent typos from silently failing
3. **Default values** - Specify defaults in property definitions
4. **Validation** - Use min/max, enum, pattern, minLength/maxLength

---

## 3. Three Exemplar Components by Complexity

### TIER 1: Simple Component
**`filesystem.csv_writer`** - Simplicity Rating: 1/5

**Key Characteristics:**
- No secrets or authentication
- Minimal configuration (path + optional formatting)
- Single output type (file write)
- No conditional logic needed
- No discovery capability

**Spec Highlights:**
```yaml
modes: [write]
configSchema:
  required: [path]           # Only required field
  properties:
    path: string
    delimiter: string (default: ",")
    header: boolean (default: true)
    encoding: enum (default: "utf-8")
    # ... 6 more optional fields

constraints:
  required: [when, must] # Single constraint: tab delimiter needs minimal quoting
```

**Driver Pattern:**
- Method signature: `run(*, step_id, config, inputs, ctx) → dict`
- Input: `inputs["df"]` (DataFrame)
- Output: `{}` (empty dict for writers)
- Path handling: `Path.cwd() / relative_path`

---

### TIER 2: Medium Complexity
**`mysql.extractor`** - Complexity Rating: 3/5

**Key Characteristics:**
- Database authentication (host, user, password)
- Dual-mode: `extract` and `discover`
- Connection pooling configuration
- Either-or fields: `table` XOR `query`
- Multiple secret and redaction rules

**Spec Highlights:**
```yaml
modes: [extract, discover]
configSchema:
  required: [host, database, user, password]
  properties:
    host: string (default: "localhost")
    port: integer (default: 3306, min: 1, max: 65535)
    password: string [SECRET]
    table: string (mutually exclusive with query)
    query: string (mutually exclusive with table)
    batch_size: integer (default: 10000, min: 100, max: 100000)
    pool_size: integer (default: 5, min: 1, max: 20)

secrets: [/password]
redaction:
  strategy: mask
  mask: "****"
  extras: [/host, /user]  # Additional sensitive fields

x-connection-fields:
  - name: host, override: allowed
  - name: database, override: forbidden  # Security boundary
  - name: password, override: forbidden  # Critical secret

constraints:
  - when: {query: null}
    must: {table: {minLength: 1}}
    error: "Either 'table' or 'query' must be specified"
```

**Driver Pattern:**
- Connection resolution via `config.get("resolved_connection", {})`
- SQLAlchemy engine creation with masked URL for logging
- DataFrame output: `return {"df": df}`
- Metrics logging: `ctx.log_metric(name, value)`

---

### TIER 3: Full-Featured Component
**`graphql.extractor`** - Complexity Rating: 5/5

**Key Characteristics:**
- Multiple authentication methods (bearer, basic, API key, custom headers)
- Complex pagination with cursor-based state tracking
- Nested data extraction via JSONPath
- 4 conditional constraints with interdependencies
- Comprehensive LLM hints for multiple authentication patterns
- 4 detailed real-world examples (GitHub, Shopify, Hasura, custom)

**Spec Highlights:**
```yaml
modes: [extract]
configSchema:
  required: [endpoint, query]
  properties:
    endpoint: string (URI format)
    query: string (GraphQL query)
    variables: object (additionalProperties: true)
    headers: object (additionalProperties: string)
    
    # Authentication (4 paths)
    auth_type: enum [none, bearer, basic, api_key]
    auth_token: string [SECRET]
    auth_username: string [SECRET]
    auth_header_name: string
    
    # Pagination (6 fields)
    pagination_enabled: boolean
    pagination_path: string (JSONPath)
    pagination_cursor_field: string
    pagination_has_next_field: string
    pagination_variable_name: string
    max_pages: integer
    
    # Response handling
    data_path: string (JSONPath)
    flatten_result: boolean
    
    # Network
    timeout: integer (default: 30)
    max_retries: integer (default: 3)
    retry_delay: number (default: 1.0)
    validate_ssl: boolean

secrets: [/auth_token, /auth_username, /headers]

x-connection-fields:
  - name: endpoint, override: allowed
  - name: auth_token, override: forbidden
  - name: headers, override: warning  # Allow but warn

redaction:
  strategy: mask
  mask: "***"
  extras:
    - /auth_token
    - /auth_username
    - /headers/Authorization
    - /headers/X-API-Key

constraints:
  - when: {auth_type: "basic"}
    must: {auth_username: {minLength: 1}, auth_token: {minLength: 1}}
  - when: {auth_type: "bearer"}
    must: {auth_token: {minLength: 1}}
  - when: {auth_type: "api_key"}
    must: {auth_token: {minLength: 1}}
  - when: {pagination_enabled: true}
    must: {pagination_path: {minLength: 1}, ...}

llmHints:
  inputAliases:
    endpoint: [url, api_url, graphql_url, graphql_endpoint]
    query: [graphql_query, gql_query, gql]
    variables: [query_variables, graphql_variables, params]
    auth_token: [token, api_key, access_token, bearer_token]
  promptGuidance: "Use graphql.extractor to query any GraphQL API..."
  yamlSnippets:
    - "type: graphql.extractor"
    - "endpoint: https://api.example.com/graphql"
  commonPatterns:
    - pattern: simple_query
    - pattern: authenticated_query
    - pattern: paginated_query
    - pattern: complex_nested_query

limits:
  maxRows: 1000000
  maxSizeMB: 1024
  maxDurationSeconds: 1800
  maxConcurrency: 3  # Rate limiting guidance

loggingPolicy:
  sensitivePaths:
    - /auth_token
    - /auth_username
    - /headers/Authorization
    - /headers/X-API-Key
  eventDefaults:
    - extraction.start
    - extraction.query
    - extraction.response
    - extraction.page
    - extraction.complete
    - extraction.error
  metricsToCapture:
    - rows_read
    - bytes_processed
    - duration_ms
```

**Example Count:** 4 real-world examples (GitHub, Shopify, Hasura, custom)

---

## 4. Common Patterns and Conventions

### Naming Conventions

**Component Name Format**
```
{namespace}.{type}
namespace = {service|tool|domain} (mysql, supabase, filesystem, graphql, duckdb)
type = {extractor|writer|processor|connection}
```

**Field Naming**
```
- Snake_case for all fields: host, user_id, write_mode, api_key
- Connection fields: host, port, user, password, database, schema
- Authentication: auth_type, auth_token, auth_username, auth_header_name
- Mode fields: mode (MySQL), write_mode (Supabase)
- Pagination: pagination_enabled, pagination_path, pagination_cursor_field
```

### Capabilities Patterns

**By Component Type:**

| Type | discover | adHocAnalytics | inMemoryMove | streaming | transactions |
|------|----------|----------------|--------------|-----------|--------------|
| Extractor | true/false | true if query support | false | depends | false |
| Writer | true | false | false | depends | true if DB |
| Processor | false | depends | true | false | false |

**Standard Capability Flags:**
```yaml
capabilities:
  discover: [true|false]          # list_tables/list_schemas
  adHocAnalytics: [true|false]    # execute_query capability
  inMemoryMove: [true|false]      # DataFrame pass-through
  streaming: [true|false]         # Streaming mode support
  bulkOperations: [true|false]    # batch_size optimization
  transactions: [true|false]      # COMMIT/ROLLBACK
  partitioning: [false]           # Sharding/partitioning
  customTransforms: [true|false]  # SQL/transform support
```

### Modes Pattern

```yaml
modes:
  - extract      # Read from external source
  - write        # Write to external destination
  - discover     # Schema introspection
  - transform    # In-place data transformation
```

### Authentication Pattern

**Pattern 1: Simple API Key (Supabase)**
```yaml
configSchema:
  properties:
    key: string (minLength: 20)
secrets: [/key]
x-connection-fields:
  - name: key, override: forbidden
```

**Pattern 2: Multi-Method Auth (GraphQL)**
```yaml
configSchema:
  properties:
    auth_type: enum [none, bearer, basic, api_key]
    auth_token: string
    auth_username: string
    auth_header_name: string
    headers: object (additionalProperties: string)
secrets: [/auth_token, /auth_username, /headers]
x-connection-fields:
  - name: auth_token, override: forbidden
  - name: auth_username, override: forbidden
  - name: headers, override: warning
```

**Pattern 3: Database Credentials (MySQL)**
```yaml
configSchema:
  properties:
    host: string
    port: integer
    user: string
    password: string
    database: string
  required: [host, database, user, password]
secrets: [/password]
x-connection-fields:
  - name: password, override: forbidden
  - name: database, override: forbidden
  - name: user, override: forbidden
```

### x-connection-fields Override Policies

```yaml
x-connection-fields:
  - name: field_name
    override: [allowed | forbidden | warning]
```

**Semantics:**
- `allowed` - Safe to override in component config
- `forbidden` - Cannot override (security boundary)
- `warning` - Allow but warn (user responsibility)

**Security Patterns:**
- Critical secrets (`password`, `api_key`, `auth_token`) → `forbidden`
- Connection metadata (`host`, `port`, `url`) → `allowed`
- Sensitive user data (`username`) → `forbidden`

### Redaction Strategy

**Standard Pattern:**
```yaml
redaction:
  strategy: mask           # Only "mask" currently supported
  mask: "****"            # Or "***", "***REDACTED***"
  extras:
    - /host               # Additional sensitive paths
    - /user
    - /password
    - /api_key
```

**Secret Path Patterns:**
```
/password                  # Root-level field
/auth_token
/resolved_connection/password  # Nested from connection resolution
/headers/Authorization     # Specific header
/headers/X-API-Key
```

### Constraints Pattern

**Basic Conditional Required:**
```yaml
constraints:
  required:
    - when: {query: null}
      must: {table: {minLength: 1}}
      error: "Either 'table' or 'query' must be specified"
```

**Dependency Pattern:**
```yaml
constraints:
  required:
    - when: {write_mode: upsert}
      must: {upsert_keys: {minItems: 1}}
      error: "upsert_keys required for upsert mode"
```

**Multiple Auth Validation:**
```yaml
constraints:
  required:
    - when: {auth_type: "basic"}
      must: 
        auth_username: {minLength: 1}
        auth_token: {minLength: 1}
      error: "Basic auth requires username and password"
```

### Default Values Pattern

**Location in Schema:**
```yaml
configSchema:
  properties:
    field_name:
      type: string
      default: "value"     # Here in property definition
```

**Common Defaults:**
- Ports: 3306 (MySQL), 5432 (PostgreSQL)
- Batch sizes: 1000 (writers), 10000 (extractors)
- Timeouts: 30 seconds
- Booleans: false for dangerous operations (truncate, create_table)

### LLM Hints Pattern

**Purpose:** Help LLMs understand alternative field names, generate correct YAML snippets, and handle common use cases

```yaml
llmHints:
  inputAliases:
    field_name:
      - alias1
      - alias2
      - snake_case_variant
  promptGuidance: |
    Single paragraph explaining:
    - What the component does
    - Required fields
    - Common options
    - Example use case
  yamlSnippets:
    - "component: namespace.type"
    - "mode: extract"
    - "field: value"
    - "nested: { key: value }"
  commonPatterns:
    - pattern: pattern_name
      description: "When and why to use this pattern"
```

**Example:**
```yaml
llmHints:
  inputAliases:
    table:
      - table_name
      - source_table
      - from_table
  commonPatterns:
    - pattern: full_table_extract
      description: Extract entire table without filters
    - pattern: custom_sql_extract
      description: Use query field for complex SQL
```

### Limits and Performance Boundaries

```yaml
limits:
  maxRows: 10000000        # Safety limit
  maxSizeMB: 10240         # Data size cap
  maxDurationSeconds: 3600 # Timeout
  maxConcurrency: 5        # Parallel operations
  rateLimit:               # API limits
    requests: 100
    period: second
```

**Typical Values:**
- Database extractors: 10M rows, 10GB, 1 hour
- API extractors: 1-10M rows, 1GB, 30 min
- Writers: Same as extractors
- File writers: 100M rows, 10GB, 1 hour

### Examples Section

**Required Count:** At least 1 per component, 2+ for complex ones

**Example Structure:**
```yaml
examples:
  - title: "Descriptive title"
    config:
      # Complete, valid configuration
      field1: value1
    notes: "Context or why you'd use this pattern"
```

**Best Practices:**
- First example: Simplest case (defaults everything possible)
- Subsequent: Address specific features or combinations
- Real-world: Use realistic values (not "example123")
- Comments: Include `# pragma: allowlist secret` for test secrets

### Compatibility Section

```yaml
compatibility:
  requires:
    - python>=3.10           # Minimum version
    - sqlalchemy>=2.0        # Dependencies with versions
    - pymysql>=1.0
  platforms:
    - linux
    - darwin
    - windows
    - docker
```

### Logging Policy

```yaml
loggingPolicy:
  sensitivePaths:
    - /password              # Paths to redact in logs
    - /api_key
    - /headers/Authorization
  eventDefaults:
    - extraction.start       # Events always logged
    - extraction.complete
  metricsToCapture:
    - rows_read
    - bytes_processed
    - duration_ms
```

### x-runtime and Driver Configuration

```yaml
x-runtime:
  driver: osiris.drivers.module_name.ClassName  # Full path required
  requirements:
    imports:
      - pandas              # What to import for types
      - sqlalchemy
    packages:
      - pandas              # What pip install needs
      - sqlalchemy
```

**Driver Method Signature:**
```python
class DriverClass:
    def run(
        self,
        *,
        step_id: str,              # Pipeline step ID
        config: dict,              # Merged component + user config
        inputs: dict | None = None,  # From previous steps
        ctx: Any = None,           # Execution context for logging
    ) -> dict:
        """
        Extractors: return {"df": DataFrame}
        Writers: return {}
        """
```

---

## 5. Anti-Patterns to Avoid

### ANTI-PATTERN 1: Hardcoded Path Handling
**Wrong:**
```python
# In driver
path = Path.home() / ".osiris" / "data"
```
**Right:**
```python
# In spec.yaml
x-runtime:
  config_driven: true
# In driver - paths come from config, never hardcoded
output_path = config.get("path")
```

**Why:** Breaks in different environments (CI, Docker, E2B, user machines)

---

### ANTI-PATTERN 2: Secrets in configSchema Properties
**Wrong:**
```yaml
configSchema:
  properties:
    api_key:  # No indication this is secret!
      type: string
```
**Right:**
```yaml
configSchema:
  properties:
    api_key:
      type: string
secrets:
  - /api_key  # Explicit declaration
x-secret:
  - /api_key
  - /resolved_connection/api_key
redaction:
  strategy: mask
```

**Why:** Prevents accidental logging, enables secret masking in MCP

---

### ANTI-PATTERN 3: Missing x-connection-fields
**Wrong:**
```yaml
# No definition = defaults to "allowed" for everything
configSchema:
  properties:
    password: string
    database: string
```
**Right:**
```yaml
x-connection-fields:
  - name: password
    override: forbidden  # Critical security boundary
  - name: database
    override: forbidden  # Cannot switch databases
  - name: host
    override: allowed    # OK to override
```

**Why:** Prevents users from accidentally overriding critical secrets

---

### ANTI-PATTERN 4: Insufficient Constraint Documentation
**Wrong:**
```yaml
constraints:
  required:
    - when: {mode: upsert}
      must: {keys: {minItems: 1}}
      # Missing error message!
```
**Right:**
```yaml
constraints:
  required:
    - when: {mode: upsert}
      must: {upsert_keys: {minItems: 1}}
      error: "upsert_keys must be specified when mode='upsert'"
```

**Why:** User-facing error messages must be clear and actionable

---

### ANTI-PATTERN 5: Missing LLM Hints for Multi-Auth
**Wrong:**
```yaml
# LLM doesn't know auth_type=basic requires username+password
configSchema:
  properties:
    auth_type: enum [none, bearer, basic]
```
**Right:**
```yaml
constraints:
  required:
    - when: {auth_type: "basic"}
      must: 
        auth_username: {minLength: 1}
        auth_token: {minLength: 1}
llmHints:
  inputAliases:
    auth_type: [auth_method, authentication_type]
  promptGuidance: |
    Supports three authentication methods:
    - "none": No authentication
    - "bearer": Requires auth_token
    - "basic": Requires auth_username and auth_token
```

**Why:** LLM needs to understand conditional logic to generate correct configs

---

### ANTI-PATTERN 6: Inconsistent Mode Field Names
**Wrong:**
```yaml
# mysql.writer uses "mode"
# supabase.writer uses "write_mode"
# graphql has no mode for auth
```
**Right:**
```yaml
# Pick naming convention and stick to it
# Database writers: "mode" (append, replace, upsert)
# API writers: "write_mode" (to distinguish from auth_type)
```

**Current State:** Minor inconsistency exists (fixable)

---

### ANTI-PATTERN 7: Unspecified Error Recovery
**Wrong:**
```yaml
# No indication what happens on connection failure
configSchema:
  properties:
    host: string
```
**Right:**
```yaml
llmHints:
  promptGuidance: |
    ...Connection will timeout after 30 seconds if host is unreachable...
limits:
  maxDurationSeconds: 3600
```

**Why:** Users need to know failure modes and timeouts

---

### ANTI-PATTERN 8: Missing Real-World Examples
**Wrong:**
```yaml
examples:
  - title: Example
    config:
      endpoint: "https://api.example.com"
```
**Right:**
```yaml
examples:
  - title: "GitHub API - Get repositories"
    config:
      endpoint: "https://api.github.com/graphql"
      query: |
        query GetRepositories($first: Int!) {
          viewer {
            repositories(first: $first) {
              nodes { name stargazerCount }
            }
          }
        }
      variables: {first: 20}
```

**Why:** Helps users understand actual usage, tests spec correctness

---

## 6. Template Structure for New Component Specs

```yaml
# ComponentName Specification
name: namespace.type               # e.g., "bigquery.extractor"
version: 1.0.0
title: Human Readable Title
description: |
  Multi-line description explaining:
  - What the component does
  - Primary use case
  - Key features

# OPERATIONAL CONFIGURATION
modes:
  - extract                        # One or more: extract, write, discover, transform

capabilities:
  discover: false                  # Can list available tables/schemas
  adHocAnalytics: false           # Can execute arbitrary queries
  inMemoryMove: false             # Works with DataFrames
  streaming: false                # Supports streaming mode
  bulkOperations: true            # Has batch_size optimization
  transactions: false             # Supports ACID transactions
  partitioning: false             # Supports sharding
  customTransforms: false         # Supports SQL/custom logic

# CONFIGURATION SCHEMA
configSchema:
  type: object
  properties:
    # Connection fields (if external service)
    host:
      type: string
      description: "Service hostname"
      default: "localhost"
    port:
      type: integer
      description: "Service port"
      default: 5432
      minimum: 1
      maximum: 65535
    
    # Authentication fields
    api_key:
      type: string
      description: "API key for authentication"
      minLength: 20
    
    # Required operational fields
    query:
      type: string
      description: "SQL or API query"
      minLength: 1
    
    # Optional operational fields with defaults
    batch_size:
      type: integer
      description: "Rows to process per batch"
      default: 10000
      minimum: 100
      maximum: 100000
    
    timeout:
      type: integer
      description: "Request timeout in seconds"
      default: 30
      minimum: 5
      maximum: 300
  
  required:
    - api_key        # Required fields only at root
    - query
  
  additionalProperties: false      # Reject unknown fields

# SECURITY CONFIGURATION
secrets:
  - /api_key         # Fields containing secrets
  - /password

x-secret:            # Extended secret paths
  - /api_key
  - /password
  - /resolved_connection/api_key

x-connection-fields:
  - name: api_key
    override: forbidden            # Cannot override secrets
  - name: host
    override: allowed              # OK to override endpoints

redaction:
  strategy: mask
  mask: "****"
  extras:            # Additional sensitive fields
    - /host
    - /api_key

# VALIDATION RULES
constraints:
  required:
    - when: {mode: upsert}
      must: {upsert_keys: {minItems: 1}}
      error: "upsert_keys required when mode='upsert'"

# EXAMPLES
examples:
  - title: "Basic extraction"
    config:
      host: localhost
      port: 5432
      api_key: "your_key_here"  # pragma: allowlist secret
      query: "SELECT * FROM table"
    notes: "Simplest case with defaults"
  
  - title: "Advanced extraction with batching"
    config:
      host: db.prod.company.com
      api_key: "prod_key"        # pragma: allowlist secret
      query: |
        SELECT id, name, created_at
        FROM table
        WHERE created_at >= '2024-01-01'
      batch_size: 50000
    notes: "Production scenario with custom batch size"

# COMPATIBILITY
compatibility:
  requires:
    - python>=3.10
    - sqlalchemy>=2.0
  platforms:
    - linux
    - darwin
    - windows
    - docker

# LLM GUIDANCE
llmHints:
  inputAliases:
    api_key:
      - api_token
      - access_key
      - token
  promptGuidance: |
    Use namespace.type to [action].
    Requires [required_fields].
    Supports [key_features].
    Common patterns: [pattern_names].
  yamlSnippets:
    - "type: namespace.type"
    - "mode: extract"
    - "api_key: '{{ api_key }}'"
  commonPatterns:
    - pattern: basic_extraction
      description: "Simple query without filters"
    - pattern: filtered_extraction
      description: "Extraction with WHERE conditions"
    - pattern: large_dataset
      description: "Large datasets with custom batch_size"

# OPERATION CONFIGURATION
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

# RUNTIME CONFIGURATION
x-runtime:
  driver: osiris.drivers.module_name.DriverClassName
  requirements:
    imports:
      - pandas
      - sqlalchemy
    packages:
      - pandas
      - sqlalchemy
```

---

## 7. Component Complexity Checklist

### Tier 1: Simple (filesystem.csv_writer)
- [ ] No secrets/authentication
- [ ] < 10 config fields
- [ ] Single mode (read or write, not both)
- [ ] No conditional logic (constraints)
- [ ] File-based or in-memory only

### Tier 2: Medium (mysql.extractor, supabase.extractor)
- [ ] Database/API authentication
- [ ] 10-20 config fields
- [ ] Dual modes (extract + discover)
- [ ] 1-2 conditional constraints
- [ ] Basic LLM hints

### Tier 3: Complex (graphql.extractor, supabase.writer)
- [ ] Multiple auth methods
- [ ] 20+ config fields
- [ ] Complex dependencies between fields
- [ ] 3+ conditional constraints
- [ ] Comprehensive real-world examples (3+)
- [ ] Detailed LLM hints with aliases and patterns
- [ ] Advanced features (pagination, nested extraction, etc.)

---

## 8. Key Takeaways

1. **Spec-First Design:** Components are defined by their YAML specs, drivers just implement
2. **Security by Default:** Secrets explicitly declared, connection fields restricted, redaction automatic
3. **LLM-Friendly:** Every spec includes hints to help AI understand and generate configs
4. **Validation-Complete:** Constraints, defaults, and examples reduce user errors
5. **Observable:** Logging policies and metrics built into specs
6. **Backward Compatible:** Version field present, no breaking changes without plan
7. **Well-Documented:** Examples, aliases, and prompt guidance for every component

---

**Generated:** October 25, 2025
