# x-connection-fields Specification

## Overview

The `x-connection-fields` field in component specifications declares which configuration fields can be provided by a connection reference instead of inline in the pipeline step config. This enables secure credential management, reusable connection definitions, and fine-grained control over field overrides.

## Purpose

When a pipeline step uses a connection reference (e.g., `connection: "@mysql.prod"`), certain fields like credentials, endpoints, and connection parameters are resolved from the connection definition rather than the step config. The `x-connection-fields` specification tells the OML validator which fields are expected from the connection and whether they can be overridden in the step config.

## Key Benefits

1. **Security**: Prevents accidental credential leakage by forbidding overrides of sensitive fields
2. **Reusability**: Connection configurations can be shared across multiple pipeline steps
3. **Flexibility**: Infrastructure fields (host, port) can be overridden for testing while keeping credentials secure
4. **Validation**: Clear contract between component specs and connection definitions

## Format

Supports two formats: simple array and advanced object format with override control.

### Simple Array Format

```yaml
x-connection-fields:
  - endpoint
  - auth_token
  - auth_username
```

All fields are overridable by default (policy: `allowed`).

### Advanced Format with Override Control

```yaml
x-connection-fields:
  - name: endpoint
    override: allowed
  - name: auth_token
    override: forbidden
  - name: password
    override: forbidden
```

## Override Policies

| Policy | Behavior | Use Case | Validation |
|--------|----------|----------|------------|
| `allowed` | Step config can override connection value | Infrastructure fields (host, port) | No error or warning |
| `forbidden` | Step config cannot override connection value | Security fields (password, token, key) | Validation error |
| `warning` | Step config can override but emits warning | Headers, uncertain cases | Warning emitted |

### Policy Details

#### allowed
- **Purpose**: Permits testing and environment-specific overrides
- **Common Fields**: `host`, `port`, `database`, `endpoint`, `schema`
- **Example**: Override production host with staging host for testing
- **Risk**: Low - infrastructure parameters are generally safe to override

#### forbidden
- **Purpose**: Enforces security by preventing credential overrides
- **Common Fields**: `password`, `api_key`, `token`, `secret`, `private_key`
- **Example**: Prevents hardcoding credentials in pipeline YAML
- **Risk**: High - allowing overrides could expose secrets

#### warning
- **Purpose**: Allows overrides but alerts developer to potential risks
- **Common Fields**: `headers`, `options`, `custom_auth`, `connection_string`
- **Example**: Custom headers that might contain authorization
- **Risk**: Medium - field may contain sensitive data depending on usage

## Examples

### MySQL Extractor

```yaml
name: mysql.extractor
version: 1.0.0

configSchema:
  type: object
  properties:
    host:
      type: string
    port:
      type: integer
    database:
      type: string
    user:
      type: string
    password:
      type: string
    table:
      type: string
  required:
    - host
    - database
    - user
    - password

secrets:
  - /password

x-connection-fields:
  - name: host
    override: allowed      # Can use different host for testing
  - name: port
    override: allowed      # Can use different port for testing
  - name: database
    override: forbidden    # Security: cannot change database
  - name: user
    override: forbidden    # Security: cannot change user
  - name: password
    override: forbidden    # Security: cannot override password
```

### GraphQL Extractor

```yaml
name: graphql.extractor
version: 1.0.0

configSchema:
  type: object
  properties:
    endpoint:
      type: string
    auth_token:
      type: string
    headers:
      type: object
    query:
      type: string
  required:
    - endpoint
    - auth_token

secrets:
  - /auth_token

x-connection-fields:
  - name: endpoint
    override: allowed      # Can point to different endpoint (staging/prod)
  - name: auth_token
    override: forbidden    # Security: token cannot be overridden
  - name: headers
    override: warning      # Allow but warn (might contain auth)
```

### Supabase Writer

```yaml
name: supabase.writer
version: 1.0.0

configSchema:
  type: object
  properties:
    url:
      type: string
    key:
      type: string
    schema:
      type: string
      default: public
    table:
      type: string
  required:
    - url
    - key

secrets:
  - /key

x-connection-fields:
  - name: url
    override: allowed      # Can point to different project
  - name: key
    override: forbidden    # Security: API key cannot be overridden
  - name: schema
    override: allowed      # Can use different schema for testing
```

## Validation Behavior

### With Connection Reference

```yaml
# osiris_connections.yaml
connections:
  mysql:
    prod:
      host: db.prod.example.com
      port: 3306
      database: warehouse
      user: etl_user
      password: ${MYSQL_PASSWORD}
      default: true

# pipeline.yaml
oml_version: "0.1.0"
name: extract-customers
steps:
  - id: extract
    component: mysql.extractor
    mode: read
    config:
      connection: "@mysql.prod"  # host, port, database, user, password from connection
      table: "customers"          # Only table specified in config
```

**Validator Behavior**:
- Skips validation of connection-provided required fields (`host`, `port`, `database`, `user`, `password`)
- Only validates step-specific fields (`table`)
- Connection resolution happens at runtime

### With Valid Override

```yaml
steps:
  - id: extract
    component: mysql.extractor
    mode: read
    config:
      connection: "@mysql.prod"
      host: "localhost"    # OK: override allowed for testing
      table: "customers"
```

**Validator Behavior**:
- Accepts override of `host` (policy: `allowed`)
- Uses connection values for `port`, `database`, `user`, `password`
- No errors or warnings

### With Forbidden Override

```yaml
steps:
  - id: extract
    component: mysql.extractor
    mode: read
    config:
      connection: "@mysql.prod"
      password: "hacked!"  # ERROR: forbidden override
      table: "customers"
```

**Validator Behavior**:
- Emits error: `Cannot override connection field 'password' (policy: forbidden)`
- Pipeline validation fails
- Execution is blocked

### With Warning Override

```yaml
steps:
  - id: extract
    component: graphql.extractor
    mode: read
    config:
      connection: "@graphql.api"
      headers:              # WARNING: override has warning policy
        X-Custom-Auth: "bearer token"
      query: "{ users { id name } }"
```

**Validator Behavior**:
- Emits warning: `Overriding connection field 'headers' (policy: warning) - may contain sensitive data`
- Pipeline validation succeeds
- Execution proceeds with warning logged

## Merge Strategy

Values are merged in this order (last wins):

1. **Component defaults** (from `configSchema.properties.*.default`)
2. **Connection values** (from `@ref` resolution in `osiris_connections.yaml`)
3. **Step config overrides** (if override policy allows)

### Example Merge

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
      port: 3307  # Overrides default 3306
      database: warehouse

# Step config
steps:
  - id: extract
    config:
      connection: "@mysql.prod"
      schema: "analytics"  # Overrides default "public"
      # port uses connection value: 3307
      # host uses connection value: db.prod.example.com
```

**Final merged config**:
```yaml
host: db.prod.example.com  # from connection
port: 3307                 # from connection (overrides default)
database: warehouse        # from connection
schema: analytics          # from step config (overrides default)
```

## Backward Compatibility

Components without `x-connection-fields` fall back to the `secrets` field:
- All secret fields (declared in `secrets: ["/password", "/key"]`) are treated as connection-provided
- Override policy defaults to `forbidden` for secret fields
- Non-secret fields default to `allowed`

### Migration Example

```yaml
# Before (implicit)
name: mysql.extractor
secrets:
  - /password

# After (explicit - recommended)
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

## Best Practices

### 1. Security Fields Should Be Forbidden

Always use `override: forbidden` for:
- Passwords (`password`, `passwd`, `pwd`)
- API keys (`api_key`, `key`, `apikey`)
- Tokens (`token`, `auth_token`, `bearer_token`)
- Secrets (`secret`, `client_secret`)
- Private keys (`private_key`, `ssh_key`)
- Credentials (`credentials`, `credential`)

### 2. Infrastructure Fields Can Be Allowed

Use `override: allowed` for:
- Hostnames (`host`, `hostname`, `server`)
- Ports (`port`)
- URLs (`url`, `endpoint`, `base_url`)
- Databases/schemas (`database`, `schema`, `namespace`)
- Timeouts (`timeout`, `connect_timeout`)

### 3. Ambiguous Fields Should Warn

Use `override: warning` for:
- Headers (`headers`, `custom_headers`)
- Options (`options`, `connection_options`)
- Custom authentication (`custom_auth`, `auth_config`)
- Connection strings (`dsn`, `connection_string`)

### 4. Always Declare Connection Fields Explicitly

Don't rely on fallback behavior. Explicitly declare all fields that come from connections:

```yaml
# Good
x-connection-fields:
  - name: host
    override: allowed
  - name: password
    override: forbidden

# Bad (relies on implicit behavior)
# x-connection-fields: []  # missing
```

### 5. Document Override Policies in Component Specs

Add comments explaining why certain fields have specific policies:

```yaml
x-connection-fields:
  - name: host
    override: allowed
    # Allows testing against localhost or staging environments
  - name: password
    override: forbidden
    # Security: prevents credential leakage in pipeline YAML
```

## Integration with Connection Resolution

The `x-connection-fields` specification works with the connection resolution system defined in ADR-0020.

### Resolution Flow

1. **Parse OML**: Validator identifies connection reference (`@mysql.prod`)
2. **Check Component Spec**: Reads `x-connection-fields` from component spec
3. **Validate Overrides**: Checks if step config attempts to override forbidden fields
4. **Resolve Connection**: Runtime resolves connection from `osiris_connections.yaml`
5. **Merge Values**: Applies merge strategy (defaults → connection → step overrides)
6. **Substitute Secrets**: Replaces `${ENV_VAR}` with environment variable values
7. **Execute Step**: Component receives fully resolved configuration

### Runtime Example

```python
# Pseudo-code for runtime resolution
def resolve_step_config(step, component_spec, connections_yaml):
    # 1. Get connection fields definition
    connection_fields = component_spec.get("x-connection-fields", [])

    # 2. Parse connection reference
    conn_ref = step["config"].get("connection")  # "@mysql.prod"
    family, alias = parse_connection_ref(conn_ref)  # "mysql", "prod"

    # 3. Resolve connection from YAML
    conn_values = connections_yaml["connections"][family][alias]

    # 4. Start with component defaults
    merged = get_component_defaults(component_spec)

    # 5. Merge connection values
    for field_def in connection_fields:
        field_name = field_def["name"]
        if field_name in conn_values:
            merged[field_name] = conn_values[field_name]

    # 6. Apply step config overrides (if allowed)
    for key, value in step["config"].items():
        if key == "connection":
            continue

        field_def = find_field_def(connection_fields, key)
        if field_def and field_def["override"] == "forbidden":
            raise ValidationError(f"Cannot override field '{key}'")
        elif field_def and field_def["override"] == "warning":
            log_warning(f"Overriding field '{key}' - may contain sensitive data")

        merged[key] = value

    # 7. Substitute environment variables
    merged = substitute_env_vars(merged)

    return merged
```

## Error Messages

### Forbidden Override Error

```
ValidationError: Cannot override connection field 'password'
  Location: steps[0].config.password
  Component: mysql.extractor
  Connection: @mysql.prod
  Policy: forbidden

  Connection fields with 'forbidden' policy cannot be overridden in step config.
  Remove the 'password' field from the step config.
```

### Warning Override Message

```
ValidationWarning: Overriding connection field 'headers'
  Location: steps[0].config.headers
  Component: graphql.extractor
  Connection: @graphql.api
  Policy: warning

  This field may contain sensitive data. Ensure the override value does not
  expose credentials or secrets.
```

### Missing Connection Field

```
ValidationError: Connection '@mysql.prod' missing required field 'password'
  Component: mysql.extractor
  Required by: x-connection-fields

  The connection definition must provide all fields declared in
  x-connection-fields with 'forbidden' or 'warning' policies.
```

## Troubleshooting

### Issue: Validation fails with "Cannot override connection field"

**Cause**: Step config attempts to override a field with `override: forbidden` policy.

**Solution**: Remove the field from step config or change it in the connection definition.

```yaml
# Wrong
steps:
  - id: extract
    config:
      connection: "@mysql.prod"
      password: "override"  # Forbidden

# Right
steps:
  - id: extract
    config:
      connection: "@mysql.prod"
      # password comes from connection
```

### Issue: Required field missing after using connection reference

**Cause**: Field not provided by connection and not declared in `x-connection-fields`.

**Solution**: Add field to connection definition or declare it as step-specific in component spec.

```yaml
# Option 1: Add to connection
connections:
  mysql:
    prod:
      host: db.example.com
      database: warehouse  # Add missing field

# Option 2: Specify in step config (if allowed)
steps:
  - id: extract
    config:
      connection: "@mysql.prod"
      database: warehouse  # Provide in step config
```

### Issue: Warning about overriding connection field

**Cause**: Step config overrides a field with `override: warning` policy.

**Solution**: Review the override to ensure it doesn't contain sensitive data. If safe, ignore the warning.

```yaml
# Review this carefully
steps:
  - id: extract
    config:
      connection: "@graphql.api"
      headers:  # Warning emitted
        X-Request-ID: "12345"  # Safe: not sensitive
        # Authorization: "Bearer token"  # Unsafe: would leak credentials
```

## Migration Guide

For existing components without `x-connection-fields`:

### Step 1: Identify Connection Fields

List all fields that come from connection definitions:

```yaml
# From connection definition
connections:
  mysql:
    prod:
      host: db.example.com
      port: 3306
      database: warehouse
      user: etl_user
      password: ${MYSQL_PASSWORD}

# These are connection fields: host, port, database, user, password
```

### Step 2: Classify Fields by Override Policy

Determine appropriate policy for each field:

- Security fields → `forbidden`
- Infrastructure fields → `allowed`
- Ambiguous fields → `warning`

### Step 3: Add x-connection-fields Section

```yaml
# Before
name: mysql.extractor
version: 1.0.0
secrets:
  - /password

# After
name: mysql.extractor
version: 1.0.0
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

### Step 4: Test with Connection References

```yaml
# Test pipeline
steps:
  - id: extract
    component: mysql.extractor
    mode: read
    config:
      connection: "@mysql.prod"
      table: "customers"
```

Run validation:
```bash
osiris validate pipeline.yaml --level strict
```

### Step 5: Update Documentation

Document the changes in component README and examples.

## See Also

- [ADR-0020: Connection Resolution and Secrets](../adr/0020-connection-resolution-and-secrets.md) - Connection resolution system
- [Component Specification Reference](./components-spec.md) - Full component spec documentation
- [Connection Fields Reference](./connection-fields.md) - Connection configuration fields
- [OML v0.1.0 Specification](../adr/0014-OML_v0.1.0-scope-and-schema.md) - Pipeline format specification

## Future Enhancements

### Conditional Override Policies

Future versions may support conditional policies based on environment or runtime context:

```yaml
x-connection-fields:
  - name: host
    override:
      production: forbidden
      staging: allowed
      development: allowed
```

### Field-Level Validation

Future versions may support field-level validation rules:

```yaml
x-connection-fields:
  - name: port
    override: allowed
    validation:
      minimum: 1
      maximum: 65535
```

### Inheritance

Future versions may support inheritance of connection field definitions:

```yaml
x-connection-fields:
  extends: mysql.extractor
  additional:
    - name: custom_param
      override: allowed
```
