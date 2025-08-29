# Context-Aware SQL Safety Model

**Version:** 2.0
**Date:** 2025-08-28
**Purpose:** Context-specific SQL validation for different execution environments

## Overview

SQL safety requirements vary dramatically based on execution context. What's dangerous when querying production MySQL is perfectly safe in local DuckDB transforms. This specification provides context-aware SQL validation that adapts to each execution environment.

## Execution Contexts

### 1. Extract Context (External Data Sources)

**Environment:** Production databases (MySQL, PostgreSQL, Snowflake, etc.)
**Risk Level:** HIGH
**Access Mode:** STRICTLY READ-ONLY

```python
class ExtractContextRules:
    """Rules for external data source queries"""

    # EVERYTHING that modifies data is forbidden
    FORBIDDEN_OPERATIONS = [
        # DDL - Schema modifications
        'CREATE', 'ALTER', 'DROP', 'RENAME', 'TRUNCATE',

        # DML - Data modifications
        'INSERT', 'UPDATE', 'DELETE', 'REPLACE', 'MERGE',

        # DCL - Permission changes
        'GRANT', 'REVOKE',

        # TCL - Transaction control (in extraction)
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

    VALIDATION_RULES = {
        'require_read_only_connection': True,
        'max_query_complexity': 100,  # Prevent cartesian joins
        'timeout_seconds': 30,
        'row_limit': 1000000,
        'forbid_wildcards': False,  # SELECT * is OK for discovery
        'require_schema_prefix': False
    }
```

**Example Validations:**

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

### 2. Transform Context (Local DuckDB)

**Environment:** Local DuckDB instance (sandboxed)
**Risk Level:** LOW
**Access Mode:** FULL LOCAL CONTROL

```python
class TransformContextRules:
    """Rules for local DuckDB transformations"""

    # Only prevent system-level destruction
    FORBIDDEN_OPERATIONS = [
        # Database-level operations
        'DROP DATABASE', 'CREATE DATABASE', 'ALTER DATABASE',

        # System modifications
        'INSTALL', 'LOAD EXTENSION',  # Unless explicitly allowed

        # File system access (unless configured)
        'COPY FROM', 'COPY TO',  # Without explicit paths
        'EXPORT DATABASE', 'IMPORT DATABASE',

        # Connection to external systems
        'ATTACH',  # Unless to allowed paths
    ]

    # These are EXPLICITLY ALLOWED in transforms
    ALLOWED_OPERATIONS = [
        # Temp table operations
        'CREATE TEMP TABLE', 'CREATE TEMPORARY TABLE',
        'CREATE OR REPLACE TEMP TABLE',

        # CTEs and Views
        'WITH', 'CREATE VIEW', 'CREATE OR REPLACE VIEW',

        # Data modifications (local only)
        'INSERT', 'UPDATE', 'DELETE', 'MERGE',

        # Table operations (non-system)
        'CREATE TABLE', 'DROP TABLE', 'ALTER TABLE',

        # Indexes for performance
        'CREATE INDEX', 'DROP INDEX',

        # All SELECT operations
        'SELECT', 'JOIN', 'UNION', 'GROUP BY', 'WINDOW',

        # Transactions (local)
        'BEGIN', 'COMMIT', 'ROLLBACK'
    ]

    VALIDATION_RULES = {
        'allow_temp_tables': True,
        'allow_data_mutations': True,
        'allow_schema_creation': True,
        'max_memory_gb': 4,
        'timeout_seconds': 300,
        'sandbox_mode': True,
        'file_access': 'restricted',  # Only .osiris paths
    }
```

**Example Validations:**

```sql
-- ✅ ALLOWED in Transform (DuckDB)
CREATE TEMP TABLE movie_stats AS
SELECT movie_id, AVG(rating) as avg_rating
FROM input_data
GROUP BY movie_id;

INSERT INTO results
SELECT m.*, s.avg_rating
FROM movies m
JOIN movie_stats s ON m.movie_id = s.movie_id;

UPDATE results
SET category = 'High Rated'
WHERE avg_rating > 8.0;

CREATE INDEX idx_movie_rating ON results(avg_rating);

-- ❌ FORBIDDEN in Transform
DROP DATABASE osiris;  -- System level
INSTALL httpfs;  -- Extension loading
COPY results TO '/etc/passwd';  -- Dangerous file access
ATTACH 'prod_database.db';  -- External connection
```

### 3. Load Context (Target Systems)

**Environment:** Data warehouses, lakes, or APIs
**Risk Level:** MEDIUM
**Access Mode:** CONTROLLED WRITE

```python
class LoadContextRules:
    """Rules for loading data to targets"""

    # Mode-specific permissions
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
        ],
        'merge': [
            'DROP', 'TRUNCATE'
            # Complex MERGE operations allowed
        ]
    }

    ALLOWED_BY_MODE = {
        'append': ['INSERT'],
        'overwrite': ['TRUNCATE', 'INSERT', 'CREATE TABLE'],
        'upsert': ['INSERT', 'UPDATE', 'MERGE'],
        'merge': ['MERGE', 'INSERT', 'UPDATE', 'DELETE']
    }

    VALIDATION_RULES = {
        'require_writer_connection': True,
        'require_explicit_target': True,
        'transaction_mode': 'required',
        'rollback_on_error': True,
        'max_batch_size': 100000,
        'validate_schema': True
    }
```

**Example Validations:**

```sql
-- ✅ ALLOWED in Load (mode: overwrite)
TRUNCATE TABLE analytics.movie_rankings;
INSERT INTO analytics.movie_rankings
SELECT * FROM transform_output;

-- ✅ ALLOWED in Load (mode: upsert)
MERGE INTO target_table t
USING source_data s
ON t.id = s.id
WHEN MATCHED THEN UPDATE SET t.value = s.value
WHEN NOT MATCHED THEN INSERT VALUES (s.*);

-- ❌ FORBIDDEN in Load (any mode)
DROP DATABASE analytics;
GRANT ALL ON analytics TO public;
```

### 4. Simulate Context (Pre-execution Testing)

**Environment:** Ephemeral test environment
**Risk Level:** NONE
**Access Mode:** ISOLATED SANDBOX

```python
class SimulateContextRules:
    """Rules for simulation/testing"""

    # Almost everything allowed in isolated sandbox
    FORBIDDEN_OPERATIONS = [
        # Only prevent infinite loops or resource exhaustion
        'WHILE TRUE',
        'RECURSIVE WITH',  # Without termination
    ]

    ALLOWED_OPERATIONS = ['*']  # Everything else

    VALIDATION_RULES = {
        'use_sample_data': True,
        'max_rows': 1000,
        'timeout_seconds': 5,
        'memory_limit_mb': 100,
        'isolated_database': True,
        'ephemeral': True  # Destroyed after simulation
    }
```

## Implementation

### Context-Aware Validator

```python
from enum import Enum
from typing import Dict, List, Optional, Set
import re
import sqlparse
from sqlglot import parse_one, exp

class ExecutionContext(Enum):
    EXTRACT = "extract"      # External data sources
    TRANSFORM = "transform"  # Local DuckDB
    LOAD = "load"           # Target systems
    SIMULATE = "simulate"   # Testing environment

class ContextAwareSQLValidator:
    """SQL validator that adapts to execution context"""

    def __init__(self):
        self.rules = {
            ExecutionContext.EXTRACT: ExtractContextRules(),
            ExecutionContext.TRANSFORM: TransformContextRules(),
            ExecutionContext.LOAD: LoadContextRules(),
            ExecutionContext.SIMULATE: SimulateContextRules(),
        }

    def validate(
        self,
        sql: str,
        context: ExecutionContext,
        dialect: str,
        mode: Optional[str] = None,  # For load context
        connection_type: Optional[str] = None
    ) -> ValidationResult:
        """Validate SQL based on execution context"""

        # Get context-specific rules
        rules = self.rules[context]

        # Parse SQL
        try:
            parsed = parse_one(sql, read=dialect)
        except Exception as e:
            return ValidationResult(
                valid=False,
                errors=[f"SQL parse error: {e}"],
                context=context
            )

        errors = []
        warnings = []

        # Check forbidden operations for this context
        errors.extend(
            self._check_forbidden_operations(sql, parsed, rules, mode)
        )

        # Check required permissions
        if context == ExecutionContext.EXTRACT:
            errors.extend(self._validate_extract_safety(sql, parsed))
        elif context == ExecutionContext.TRANSFORM:
            warnings.extend(self._validate_transform_safety(sql, parsed))
        elif context == ExecutionContext.LOAD:
            errors.extend(self._validate_load_safety(sql, parsed, mode))

        # Apply context-specific limits
        errors.extend(
            self._check_resource_limits(sql, rules.VALIDATION_RULES)
        )

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            context=context,
            applied_rules=rules.__class__.__name__
        )

    def _check_forbidden_operations(
        self,
        sql: str,
        parsed: Any,
        rules: Any,
        mode: Optional[str] = None
    ) -> List[str]:
        """Check for context-specific forbidden operations"""

        errors = []
        sql_upper = sql.upper()

        # Get forbidden operations based on context and mode
        if hasattr(rules, 'FORBIDDEN_BY_MODE') and mode:
            forbidden = rules.FORBIDDEN_BY_MODE.get(mode, [])
        else:
            forbidden = getattr(rules, 'FORBIDDEN_OPERATIONS', [])

        # Check each forbidden operation
        for op in forbidden:
            pattern = rf'\b{op}\b'
            if re.search(pattern, sql_upper):
                errors.append(
                    f"Operation '{op}' is forbidden in {rules.__class__.__name__}"
                )

        return errors

    def _validate_extract_safety(self, sql: str, parsed: Any) -> List[str]:
        """Additional validation for extract context"""

        errors = []

        # Ensure no mutation operations
        mutation_keywords = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE']
        for keyword in mutation_keywords:
            if keyword in sql.upper():
                errors.append(
                    f"Mutation operation '{keyword}' not allowed in Extract context"
                )

        # Check for system tables access
        if re.search(r'information_schema|mysql\.|pg_', sql, re.IGNORECASE):
            errors.append(
                "System table access requires explicit permission"
            )

        return errors

    def _validate_transform_safety(self, sql: str, parsed: Any) -> List[str]:
        """Additional validation for transform context"""

        warnings = []

        # Check for unbounded operations
        if 'CROSS JOIN' in sql.upper():
            warnings.append(
                "CROSS JOIN detected - ensure this is intentional"
            )

        # Check for large intermediate results
        if not re.search(r'\bLIMIT\b', sql.upper()) and 'CREATE TABLE' in sql.upper():
            warnings.append(
                "CREATE TABLE without LIMIT may consume excessive memory"
            )

        return warnings

    def _validate_load_safety(
        self,
        sql: str,
        parsed: Any,
        mode: Optional[str]
    ) -> List[str]:
        """Additional validation for load context"""

        errors = []

        # Ensure mode is specified
        if not mode:
            errors.append("Load mode must be specified (append/overwrite/upsert/merge)")
            return errors

        # Check mode-specific requirements
        if mode == 'upsert':
            if 'ON CONFLICT' not in sql.upper() and 'MERGE' not in sql.upper():
                errors.append(
                    "Upsert mode requires ON CONFLICT or MERGE clause"
                )

        if mode == 'append':
            if any(word in sql.upper() for word in ['TRUNCATE', 'DELETE', 'DROP']):
                errors.append(
                    "Destructive operations not allowed in append mode"
                )

        return errors
```

### Integration with OML Pipeline

```yaml
# OML v2.0 with context-aware SQL safety
stages:
  extract:
    - id: get_movies
      context: extract  # Enforces read-only
      connection: mysql_prod
      sql: |
        SELECT * FROM movies
        WHERE release_year >= 2020
      validation:
        context: extract
        enforce: strict

  transform:
    - id: calculate_rankings
      context: transform  # Allows mutations
      dialect: duckdb
      sql: |
        -- This is ALLOWED in transform context
        CREATE TEMP TABLE movie_scores AS
        WITH ratings AS (
          SELECT movie_id, AVG(rating) as avg_rating
          FROM input_data
          GROUP BY movie_id
        )
        INSERT INTO movie_scores
        SELECT * FROM ratings;

        -- Also ALLOWED: Update for categorization
        UPDATE movie_scores
        SET category = CASE
          WHEN avg_rating >= 8 THEN 'Excellent'
          WHEN avg_rating >= 6 THEN 'Good'
          ELSE 'Average'
        END;

        SELECT * FROM movie_scores;
      validation:
        context: transform
        allow_temp_tables: true
        allow_mutations: true

  load:
    - id: save_rankings
      context: load
      mode: overwrite  # Determines allowed operations
      target: analytics_warehouse
      sql: |
        -- ALLOWED in load with overwrite mode
        TRUNCATE TABLE movie_rankings;
        INSERT INTO movie_rankings
        SELECT * FROM transform_output;
      validation:
        context: load
        mode: overwrite
        enforce: strict
```

## Context Detection

### Automatic Context Detection

```python
class ContextDetector:
    """Automatically detect execution context from pipeline structure"""

    @staticmethod
    def detect_context(stage: Dict) -> ExecutionContext:
        """Detect context from stage configuration"""

        # Explicit context
        if 'context' in stage:
            return ExecutionContext[stage['context'].upper()]

        # Infer from stage type
        if 'connection' in stage and 'table' in stage:
            return ExecutionContext.EXTRACT

        if 'inputs' in stage and 'sql' in stage:
            # Check if using DuckDB
            dialect = stage.get('dialect', '').lower()
            if dialect in ['duckdb', 'duck', 'local']:
                return ExecutionContext.TRANSFORM
            else:
                return ExecutionContext.EXTRACT  # Remote transform

        if 'target' in stage or 'mode' in stage:
            return ExecutionContext.LOAD

        if 'simulate' in stage or 'test' in stage:
            return ExecutionContext.SIMULATE

        # Default to most restrictive
        return ExecutionContext.EXTRACT
```

## Configuration

### Context-Specific Configuration

```yaml
# osiris/config/sql_safety_contexts.yml
sql_safety:
  contexts:
    extract:
      enforce: strict
      connection_type: read_only
      timeout_s: 30
      max_rows: 1000000
      forbidden_operations:
        - INSERT
        - UPDATE
        - DELETE
        - DROP
        - CREATE

    transform:
      enforce: normal
      engine: duckdb
      sandbox: true
      timeout_s: 300
      max_memory_gb: 4
      allowed_operations:
        - CREATE TEMP TABLE
        - INSERT
        - UPDATE
        - DELETE
      forbidden_operations:
        - DROP DATABASE
        - INSTALL

    load:
      enforce: strict
      connection_type: writer
      transaction: required
      rollback_on_error: true
      mode_specific:
        append:
          allowed: [INSERT]
          forbidden: [DELETE, TRUNCATE]
        overwrite:
          allowed: [TRUNCATE, INSERT]
          forbidden: [DROP DATABASE]
        upsert:
          allowed: [INSERT, UPDATE, MERGE]
          forbidden: [TRUNCATE, DROP]

    simulate:
      enforce: relaxed
      sandbox: ephemeral
      timeout_s: 5
      max_rows: 1000
      allow_all: true
```

## Testing

### Context Validation Tests

```python
import pytest
from osiris.safety import ContextAwareSQLValidator, ExecutionContext

class TestContextAwareSafety:

    def setup_method(self):
        self.validator = ContextAwareSQLValidator()

    def test_extract_context_blocks_mutations(self):
        """Extract context should block all mutations"""

        forbidden_queries = [
            "INSERT INTO users VALUES (1, 'test')",
            "UPDATE users SET name = 'test'",
            "DELETE FROM users WHERE id = 1",
            "DROP TABLE users",
            "CREATE TABLE temp (id INT)"
        ]

        for sql in forbidden_queries:
            result = self.validator.validate(
                sql,
                ExecutionContext.EXTRACT,
                dialect='mysql'
            )
            assert not result.valid, f"Should block: {sql}"

    def test_transform_context_allows_temp_tables(self):
        """Transform context should allow temp table operations"""

        allowed_queries = [
            "CREATE TEMP TABLE stats AS SELECT * FROM input_data",
            "INSERT INTO results SELECT * FROM stats",
            "UPDATE results SET flag = true WHERE score > 100",
            "CREATE INDEX idx_score ON results(score)",
        ]

        for sql in allowed_queries:
            result = self.validator.validate(
                sql,
                ExecutionContext.TRANSFORM,
                dialect='duckdb'
            )
            assert result.valid, f"Should allow: {sql}"

    def test_load_context_respects_mode(self):
        """Load context should respect mode restrictions"""

        # Append mode shouldn't allow TRUNCATE
        result = self.validator.validate(
            "TRUNCATE TABLE target; INSERT INTO target VALUES (1)",
            ExecutionContext.LOAD,
            dialect='postgres',
            mode='append'
        )
        assert not result.valid

        # Overwrite mode should allow TRUNCATE
        result = self.validator.validate(
            "TRUNCATE TABLE target; INSERT INTO target VALUES (1)",
            ExecutionContext.LOAD,
            dialect='postgres',
            mode='overwrite'
        )
        assert result.valid

    def test_simulate_context_allows_everything(self):
        """Simulate context should be permissive"""

        crazy_sql = """
        DROP TABLE IF EXISTS test;
        CREATE TABLE test AS SELECT * FROM movies;
        UPDATE test SET rating = 10;
        DELETE FROM test WHERE id < 100;
        """

        result = self.validator.validate(
            crazy_sql,
            ExecutionContext.SIMULATE,
            dialect='duckdb'
        )
        assert result.valid
```

## Security Boundaries

### Context Isolation

```python
class ContextIsolation:
    """Ensure contexts can't escape their boundaries"""

    @staticmethod
    def create_extract_connection(config: Dict) -> Connection:
        """Create read-only connection for extraction"""
        return Connection(
            **config,
            read_only=True,
            autocommit=False,
            timeout=30,
            max_rows=1000000
        )

    @staticmethod
    def create_transform_sandbox() -> DuckDBConnection:
        """Create isolated DuckDB instance for transforms"""
        return duckdb.connect(
            ':memory:',  # In-memory only
            read_only=False,
            config={
                'max_memory': '4GB',
                'threads': 4,
                'enable_external_access': False,
                'allow_unsigned_extensions': False
            }
        )

    @staticmethod
    def create_load_connection(config: Dict, mode: str) -> Connection:
        """Create write connection with mode-specific permissions"""

        permissions = {
            'append': ['INSERT'],
            'overwrite': ['TRUNCATE', 'INSERT'],
            'upsert': ['INSERT', 'UPDATE'],
            'merge': ['MERGE']
        }

        return Connection(
            **config,
            read_only=False,
            allowed_operations=permissions[mode],
            transaction_mode='required',
            rollback_on_error=True
        )
```

## Monitoring and Audit

### Context-Aware Audit Logging

```python
class ContextAuditLogger:
    """Log SQL operations with context awareness"""

    def log_sql_execution(
        self,
        sql: str,
        context: ExecutionContext,
        validation_result: ValidationResult,
        execution_result: Optional[ExecutionResult] = None
    ):
        """Log with context-specific details"""

        entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'context': {
                'type': context.value,
                'rules_applied': validation_result.applied_rules,
                'enforcement_level': self._get_enforcement_level(context)
            },
            'sql': {
                'statement': self._redact_sensitive(sql, context),
                'operations': self._extract_operations(sql),
                'dialect': validation_result.dialect
            },
            'validation': {
                'valid': validation_result.valid,
                'errors': validation_result.errors,
                'warnings': validation_result.warnings
            },
            'risk_assessment': self._assess_risk(sql, context)
        }

        if execution_result:
            entry['execution'] = {
                'success': execution_result.success,
                'rows_affected': execution_result.rows_affected,
                'duration_ms': execution_result.duration_ms
            }

        self._write_log(entry)

    def _assess_risk(self, sql: str, context: ExecutionContext) -> str:
        """Assess risk level based on context and operations"""

        if context == ExecutionContext.EXTRACT:
            return 'HIGH' if 'JOIN' in sql else 'MEDIUM'
        elif context == ExecutionContext.TRANSFORM:
            return 'LOW'  # Local sandbox
        elif context == ExecutionContext.LOAD:
            return 'HIGH' if 'DELETE' in sql else 'MEDIUM'
        else:
            return 'NONE'  # Simulate
```

## Summary

This context-aware SQL safety model provides:

1. **Extract Context**: Strictly read-only for external data sources
2. **Transform Context**: Permissive local sandbox for DuckDB operations
3. **Load Context**: Mode-specific permissions for target systems
4. **Simulate Context**: Unrestricted testing environment

Key benefits:

- **Security**: Prevents data corruption in production systems
- **Flexibility**: Allows complex transformations in safe environments
- **Clarity**: Explicit context makes security boundaries obvious
- **Auditability**: Context-aware logging for compliance

The model adapts validation rules based on where and how SQL is executed, providing maximum safety without hampering legitimate data transformations.
