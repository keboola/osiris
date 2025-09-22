# Osiris SQL Safety (v0.2.0)

**Status**: Extract and Load contexts are implemented in v0.2.0. Transform and Simulate contexts are planned for M2+.

**Version:** 0.2.0
**Date:** 2025-09-22
**Purpose:** Context-specific SQL validation for different execution environments

## Overview

SQL safety requirements vary dramatically based on execution context. What's dangerous when querying production MySQL is perfectly safe in local DuckDB transforms. This specification provides context-aware SQL validation that adapts to each execution environment.

## Implemented Contexts (v0.2.0)

### 1. Extract Context (External Data Sources)

**Environment:** Production databases (MySQL, PostgreSQL, Supabase)
**Risk Level:** HIGH
**Access Mode:** STRICTLY READ-ONLY
**Status:** ✅ Implemented

#### Validation Rules

```python
# FORBIDDEN in Extract Context
FORBIDDEN_OPERATIONS = [
    # DDL - Schema modifications
    'CREATE', 'ALTER', 'DROP', 'RENAME', 'TRUNCATE',

    # DML - Data modifications
    'INSERT', 'UPDATE', 'DELETE', 'REPLACE', 'MERGE',

    # DCL - Permission changes
    'GRANT', 'REVOKE',

    # TCL - Transaction control
    'COMMIT', 'ROLLBACK', 'SAVEPOINT',

    # Dangerous functions
    'LOAD_FILE', 'INTO OUTFILE', 'INTO DUMPFILE',

    # System commands
    'EXEC', 'EXECUTE', 'CALL', 'SP_',

    # Admin operations
    'SHUTDOWN', 'KILL', 'SET GLOBAL'
]

ALLOWED_OPERATIONS = [
    'SELECT', 'WITH', 'FROM', 'JOIN', 'WHERE',
    'GROUP BY', 'HAVING', 'ORDER BY', 'LIMIT',
    'UNION', 'INTERSECT', 'EXCEPT'
]
```

#### OML v0.1.0 Example

```yaml
oml_version: "0.1.0"
name: "extract_movies"
steps:
  - id: "get_movies"
    component: "mysql.extractor"
    mode: "read"
    config:
      connection: "@mysql.default"  # Connection alias, no inline secrets
      query: |
        SELECT * FROM movies
        WHERE release_year >= 2020
        LIMIT 1000
```

#### Validation Examples

```sql
-- ❌ FORBIDDEN in Extract
DELETE FROM users WHERE id = 1;
UPDATE orders SET status = 'processed';
DROP TABLE temp_data;
CREATE INDEX idx_user ON users(email);

-- ✅ ALLOWED in Extract
SELECT * FROM users WHERE created_at > '2024-01-01';
WITH recent_orders AS (SELECT * FROM orders)
SELECT * FROM recent_orders LIMIT 1000;
```

### 2. Load Context (Target Systems)

**Environment:** Data warehouses, databases (MySQL, Supabase)
**Risk Level:** MEDIUM
**Access Mode:** CONTROLLED WRITE
**Status:** ✅ Implemented

#### Mode-Specific Permissions

```python
# Load Context Rules by Write Mode
FORBIDDEN_BY_MODE = {
    'append': [
        'DROP', 'TRUNCATE', 'DELETE', 'ALTER'
    ],
    'overwrite': [
        'DROP DATABASE', 'ALTER DATABASE'
        # TRUNCATE is allowed for overwrite
    ],
    'upsert': [
        'DROP', 'TRUNCATE', 'ALTER'
        # UPDATE and INSERT are required
    ]
}

ALLOWED_BY_MODE = {
    'append': ['INSERT'],
    'overwrite': ['TRUNCATE', 'INSERT', 'CREATE TABLE'],
    'upsert': ['INSERT', 'UPDATE', 'MERGE']
}
```

#### OML v0.1.0 Example

```yaml
oml_version: "0.1.0"
name: "load_movies"
steps:
  - id: "save_to_supabase"
    component: "supabase.writer"
    mode: "write"
    inputs:
      df: "${extract_movies.df}"
    config:
      connection: "@supabase.main"  # Connection alias
      table: "movies_analytics"
      write_mode: "upsert"
      primary_key: "id"
      batch_size: 500
```

## Planned Contexts (M2+)

### 3. Transform Context (Local DuckDB) - FUTURE

**Environment:** Local DuckDB instance (sandboxed)
**Risk Level:** LOW
**Access Mode:** FULL LOCAL CONTROL
**Status:** 🚧 Planned for M2

When implemented, Transform context will allow:
- Creating temporary tables
- Data mutations in local sandbox
- Complex SQL transformations
- Index creation for performance

### 4. Simulate Context (Pre-execution Testing) - FUTURE

**Environment:** Ephemeral test environment
**Risk Level:** NONE
**Access Mode:** ISOLATED SANDBOX
**Status:** 🚧 Planned for M3

When implemented, Simulate context will provide:
- Unrestricted testing environment
- Sample data validation
- Query optimization testing
- Performance profiling

## Current Implementation (v0.2.0)

### SQL Validation in Drivers

Extract validation is enforced in extractor drivers:

```python
# osiris/drivers/mysql_extractor_driver.py
def validate_query(self, query: str) -> None:
    """Validate query is read-only"""
    forbidden = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER']
    query_upper = query.upper()

    for operation in forbidden:
        if operation in query_upper:
            raise ValueError(f"Operation {operation} not allowed in Extract context")
```

### Connection Safety

Connections enforce read-only access for extractors:

```yaml
# osiris_connections.yaml
connections:
  mysql:
    default:
      host: ${MYSQL_HOST}
      port: ${MYSQL_PORT:-3306}
      database: ${MYSQL_DATABASE}
      username: ${MYSQL_USER:-root}
      password: ${MYSQL_PASSWORD}
      # Driver enforces read-only for extractors
```

## Security Boundaries

### Extract Context Isolation

1. **Connection Level**: Read-only database users recommended
2. **Driver Level**: Query validation before execution
3. **Timeout Protection**: 30-second default timeout
4. **Row Limits**: Configurable max rows (default 1M)

### Load Context Protection

1. **Transaction Safety**: All writes in transactions
2. **Rollback on Error**: Automatic rollback on failure
3. **Mode Enforcement**: Write mode determines allowed operations
4. **Schema Validation**: Verify target schema before writes

## Monitoring and Audit

All SQL operations are logged with context awareness:

```json
{
  "event": "sql_execution",
  "context": "extract",
  "step_id": "get_movies",
  "query_hash": "sha256:abc123...",
  "operations": ["SELECT", "WHERE", "LIMIT"],
  "rows_affected": 1000,
  "duration_ms": 250,
  "validation": {
    "passed": true,
    "context": "extract",
    "rules_applied": "read_only"
  }
}
```

## Best Practices

### For Extract Operations

1. **Use specific columns** instead of `SELECT *` when possible
2. **Add LIMIT clauses** to prevent runaway queries
3. **Use read-only database users** for production connections
4. **Implement query timeouts** at connection level

### For Load Operations

1. **Choose appropriate write mode**:
   - `append`: For incremental loads
   - `overwrite`: For full refreshes
   - `upsert`: For updates with primary keys
2. **Use batching** for large datasets
3. **Validate schemas** before writing
4. **Test with small datasets** first

## Future Enhancements (M2+)

### Planned for M2
- Transform context with DuckDB sandbox
- Complex SQL transformations
- Temporary table support
- Local data mutations

### Planned for M3
- Simulate context for testing
- Query optimization hints
- Performance profiling
- Cost estimation

## Summary

Osiris v0.2.0 provides SQL safety for:

1. **Extract Context**: Strictly read-only access to external data sources
2. **Load Context**: Mode-specific write permissions for target systems

This ensures data safety in production environments while maintaining flexibility for legitimate data operations. Transform and Simulate contexts will be added in future milestones to enable local transformations and testing.
