# Connection Configuration Fields Reference

This document lists all accepted fields for connection configurations in `osiris_connections.yaml`.

## MySQL Connections

### Required Fields

- `host`: Database server hostname or IP address
- `database`: Database/schema name
- `user`: Username for authentication
- `password`: Password (use `${ENV_VAR}` for secrets)

### Optional Fields

- `port`: Port number (default: 3306)
- `charset`: Character encoding (default: utf8mb4)
- `connect_timeout`: Connection timeout in seconds (default: 10)
- `read_timeout`: Read operation timeout in seconds (default: 10)
- `write_timeout`: Write operation timeout in seconds (default: 10)

### Connection Management Fields (ADR-0020)

- `default`: Boolean flag to mark as default connection for the family
- `alias`: Connection alias name (metadata only, not sent to drivers)

### Alternative Connection Methods

- `dsn`: Full DSN connection string as an alternative to individual fields

### Example

```yaml
connections:
  mysql:
    production:
      host: db.example.com
      port: 3306
      database: myapp
      user: appuser
      password: ${MYSQL_PASSWORD}
      default: true
      charset: utf8mb4
      connect_timeout: 30
```

## Supabase Connections

### Required Fields

- `url`: Supabase project URL (e.g., `https://project.supabase.co`)
- `key`: API key (anon or service role)

### Optional Fields

- `schema`: Database schema to use (default: public)

### Connection Management Fields (ADR-0020)

- `default`: Boolean flag to mark as default connection for the family
- `alias`: Connection alias name (metadata only)

### Alternative Connection Methods

- `pg_dsn`: PostgreSQL connection string for direct database access
- `service_role_key`: Service role key (alternative to `key`)
- `anon_key`: Anonymous/public key (alternative to `key`)
- `password`: Database password when using `pg_dsn`

### Example

```yaml
connections:
  supabase:
    main:
      url: https://myproject.supabase.co
      key: ${SUPABASE_SERVICE_ROLE_KEY}
      pg_dsn: postgresql://postgres:${SUPABASE_PASSWORD}@db.myproject.supabase.co:5432/postgres
      default: true
      schema: public
```

## DuckDB Connections

### Required Fields

- `path`: Path to the DuckDB database file

### Optional Fields

- `read_only`: Open database in read-only mode (default: false)
- `memory`: Use in-memory database (default: false)

### Connection Management Fields (ADR-0020)

- `default`: Boolean flag to mark as default connection for the family
- `alias`: Connection alias name (metadata only)

### Example

```yaml
connections:
  duckdb:
    local:
      path: ./data/local.duckdb
      default: true
    memory:
      memory: true
      alias: temp
```

## Environment Variable Substitution

Use `${VAR_NAME}` syntax to reference environment variables for sensitive values:

- Secrets are never stored in the YAML file
- Environment variables are resolved at runtime
- Missing variables cause validation errors

## Default Connection Selection

When no specific connection is specified, the system follows this precedence:

1. Connection with `default: true`
2. Connection with alias named "default"
3. Error if no default can be determined

## Validation Modes

Connection validation respects the `OSIRIS_VALIDATION` environment variable:

- `warn`: Invalid configs show warnings but don't block execution (default)
- `strict`: Invalid configs cause errors and block execution
- `off`: Skip validation entirely (not recommended)

## See Also

- [ADR-0020: Connection Resolution and Secrets](../adr/0020-connection-resolution-and-secrets.md)
- [User Guide: Managing Connections](../user-guide/user-guide.md#managing-connections)

## Notes for v0.3.x (ADR-0020)

Validation and connection handling are now driven by `osiris_connections.yaml`.
Environment variables are referenced in YAML as `${VAR}` and resolved at runtime.

**Minimal example:**

```yaml
mysql:
  db_movies:
    host: "${MYSQL_HOST}"
    user: "${MYSQL_USER}"
    password: "${MYSQL_PASSWORD}"
    database: "movies"

supabase:
  main:
    url: "${SUPABASE_URL}"
    service_role_key: "${SUPABASE_SERVICE_ROLE_KEY}"
    pg_dsn: "postgresql://postgres:${SUPABASE_PASSWORD}@db.test.supabase.co:5432/postgres"
```
