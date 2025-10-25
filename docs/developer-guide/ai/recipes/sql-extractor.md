# SQL Database Extractor Recipe

## Use Case
Building an extractor for SQL databases (MySQL, PostgreSQL, SQLite, SQL Server, etc.) with discovery, connection pooling, and batch extraction.

## Prerequisites
- Database connection details (host, port, database, credentials)
- SQL dialect (MySQL, PostgreSQL, etc.)
- Understanding of connection pooling
- Basic SQL knowledge

## Component Structure

### 1. spec.yaml Template

```yaml
name: mysql.extractor
version: 1.0.0
title: MySQL Data Extractor
description: Extract data from MySQL databases with support for discovery, sampling, and bulk extraction

modes:
  - extract
  - discover

capabilities:
  discover: true
  adHocAnalytics: true  # execute_query method
  inMemoryMove: false   # returns DataFrame but no direct move API
  streaming: false      # no streaming support
  bulkOperations: true  # batch_size supported
  transactions: false   # extractor doesn't use transactions
  partitioning: false   # no partitioning support
  customTransforms: false  # no custom transforms

configSchema:
  type: object
  properties:
    host:
      type: string
      description: Database server hostname or IP address
      default: localhost
    port:
      type: integer
      description: Database server port
      default: 3306
      minimum: 1
      maximum: 65535
    database:
      type: string
      description: Database name to connect to
      minLength: 1
    user:
      type: string
      description: Database username for authentication
      minLength: 1
    password:
      type: string
      description: Database password for authentication
    table:
      type: string
      description: Table name to extract data from
      minLength: 1
    schema:
      type: string
      description: Database schema (if different from database)
      default: null
    query:
      type: string
      description: Custom SQL query for extraction (overrides table)
    columns:
      type: array
      description: Specific columns to extract (default all)
      items:
        type: string
    limit:
      type: integer
      description: Maximum number of rows to extract
      minimum: 1
    offset:
      type: integer
      description: Number of rows to skip
      minimum: 0
      default: 0
    batch_size:
      type: integer
      description: Number of rows per batch for extraction
      default: 10000
      minimum: 100
      maximum: 100000
    pool_size:
      type: integer
      description: Connection pool size
      default: 5
      minimum: 1
      maximum: 20
    pool_recycle:
      type: integer
      description: Pool recycle time in seconds
      default: 3600
      minimum: 60
    echo:
      type: boolean
      description: Enable SQL query logging
      default: false
  required:
    - host
    - database
    - user
    - password
  additionalProperties: false

secrets:
  - /password

x-secret:
  - /password
  - /resolved_connection/password

x-connection-fields:
  - name: host
    override: allowed
  - name: port
    override: allowed
  - name: database
    override: forbidden  # Security: cannot change DB
  - name: user
    override: forbidden  # Security: cannot change user
  - name: password
    override: forbidden  # Security: cannot override password
  - name: schema
    override: allowed

redaction:
  strategy: mask
  mask: "****"
  extras:
    - /host
    - /user

x-runtime:
  driver: osiris.drivers.mysql_extractor_driver.MySQLExtractorDriver
  requirements:
    imports:
      - pandas
      - sqlalchemy
      - pymysql
    packages:
      - pandas
      - sqlalchemy
      - pymysql

examples:
  - title: Basic MySQL extraction
    config:
      host: localhost
      port: 3306
      database: mydb
      user: reader
      password: secret123  # pragma: allowlist secret
      table: customers
    notes: Extract all data from customers table

  - title: Custom query with filtering
    config:
      host: db.prod.example.com
      port: 3306
      database: analytics
      user: analyst
      password: secure_pass  # pragma: allowlist secret
      query: |
        SELECT id, name, revenue
        FROM customers
        WHERE created_at >= '2024-01-01'
        ORDER BY revenue DESC
      batch_size: 50000
      pool_size: 10
    notes: Extract filtered data using custom SQL
```

### 2. Driver Implementation

File: `osiris/drivers/mysql_extractor_driver.py`

```python
"""MySQL extractor driver implementation."""

import logging
from typing import Any

import pandas as pd
import sqlalchemy as sa

logger = logging.getLogger(__name__)


class MySQLExtractorDriver:
    """Driver for extracting data from MySQL databases."""

    def run(
        self,
        *,
        step_id: str,
        config: dict,
        inputs: dict | None = None,  # noqa: ARG002
        ctx: Any = None,
    ) -> dict:
        """Extract data from MySQL using SQL query.

        Args:
            step_id: Step identifier
            config: Must contain 'query' and 'resolved_connection'
            inputs: Not used for extractors
            ctx: Execution context for logging metrics

        Returns:
            {"df": DataFrame} with query results
        """
        # Get query (either custom or generated from table)
        query = config.get("query")
        table = config.get("table")

        if not query and not table:
            raise ValueError(f"Step {step_id}: Either 'query' or 'table' is required in config")

        # Generate query from table if not provided
        if not query:
            columns = config.get("columns", ["*"])
            limit = config.get("limit")
            offset = config.get("offset", 0)

            # Build SELECT statement
            cols_str = ", ".join(f"`{col}`" if col != "*" else col for col in columns)
            query = f"SELECT {cols_str} FROM `{table}`"

            if limit:
                query += f" LIMIT {limit} OFFSET {offset}"

        # Get connection details
        conn_info = config.get("resolved_connection", {})
        if not conn_info:
            # Fallback to direct config
            conn_info = config

        # Build connection URL
        host = conn_info.get("host", "localhost")
        port = conn_info.get("port", 3306)
        database = conn_info.get("database")
        user = conn_info.get("user", "root")
        password = conn_info.get("password", "")

        if not database:
            raise ValueError(f"Step {step_id}: 'database' is required in connection")

        # Create engine with pool configuration
        pool_size = config.get("pool_size", 5)
        pool_recycle = config.get("pool_recycle", 3600)
        echo = config.get("echo", False)

        # Masked URL for logging (SAFE to log)
        masked_url = f"mysql+pymysql://{user}:***@{host}:{port}/{database}"  # noqa: F841
        # Real URL for connection ONLY (NEVER log this!)
        connection_url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"

        engine = sa.create_engine(
            connection_url,
            pool_size=pool_size,
            pool_recycle=pool_recycle,
            echo=echo,
        )

        try:
            # Test connection first
            logger.info(f"Step {step_id}: Testing MySQL connection to {user}@{host}:{port}/{database}")
            with engine.connect() as conn:
                # Test basic connection
                result = conn.execute(sa.text("SELECT 1 as test"))
                result.fetchone()

            # Execute query
            logger.info(f"Step {step_id}: Executing MySQL query")
            df = pd.read_sql_query(query, engine)

            # Log metrics
            rows_read = len(df)
            logger.info(f"Step {step_id}: Read {rows_read} rows from MySQL")

            if ctx and hasattr(ctx, "log_metric"):
                ctx.log_metric("rows_read", rows_read)

            return {"df": df}

        except sa.exc.OperationalError as e:
            # Connection/network issues
            error_msg = f"MySQL connection failed for step {step_id}"
            logger.error(error_msg)

            # Log details separately with masking
            from osiris.core.secrets_masking import mask_sensitive_string  # noqa: PLC0415

            logger.debug(f"Connection error details: {mask_sensitive_string(str(e))}")
            raise RuntimeError(error_msg) from e

        except sa.exc.ProgrammingError as e:
            # SQL syntax or permission issues
            error_msg = f"MySQL query failed: {str(e)}"
            logger.error(f"Step {step_id}: {error_msg}")
            raise RuntimeError(error_msg) from e

        except Exception as e:
            # Any other database errors
            error_msg = f"MySQL execution failed: {type(e).__name__}: {str(e)}"
            logger.error(f"Step {step_id}: {error_msg}")
            raise RuntimeError(error_msg) from e

        finally:
            engine.dispose()

    def discover(
        self,
        *,
        step_id: str,
        config: dict,
        ctx: Any = None,
    ) -> dict:
        """Discover tables and schemas in MySQL database.

        Args:
            step_id: Step identifier
            config: Connection configuration
            ctx: Execution context for logging

        Returns:
            {"tables": list of table info}
        """
        # Get connection details
        conn_info = config.get("resolved_connection", config)

        host = conn_info.get("host", "localhost")
        port = conn_info.get("port", 3306)
        database = conn_info.get("database")
        user = conn_info.get("user", "root")
        password = conn_info.get("password", "")

        if not database:
            raise ValueError(f"Step {step_id}: 'database' is required")

        # Build connection URL
        connection_url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
        engine = sa.create_engine(connection_url)

        try:
            logger.info(f"Step {step_id}: Discovering tables in MySQL database '{database}'")

            # Get table names
            with engine.connect() as conn:
                result = conn.execute(sa.text("SHOW TABLES"))
                tables = [row[0] for row in result]

            # Get details for each table
            table_info = []
            for table_name in tables:
                with engine.connect() as conn:
                    # Get column info
                    result = conn.execute(sa.text(f"DESCRIBE `{table_name}`"))  # nosec B608
                    columns = []
                    for row in result:
                        columns.append({
                            "name": row[0],
                            "type": row[1],
                            "nullable": row[2] == "YES",
                            "key": row[3],
                        })

                    # Get row count
                    result = conn.execute(sa.text(f"SELECT COUNT(*) FROM `{table_name}`"))  # nosec B608
                    row_count = result.scalar()

                table_info.append({
                    "name": table_name,
                    "columns": columns,
                    "row_count": row_count,
                })

            logger.info(f"Step {step_id}: Discovered {len(tables)} tables")

            if ctx and hasattr(ctx, "log_metric"):
                ctx.log_metric("tables_discovered", len(tables))

            return {"tables": table_info}

        except Exception as e:
            error_msg = f"Discovery failed: {type(e).__name__}: {str(e)}"
            logger.error(f"Step {step_id}: {error_msg}")
            raise RuntimeError(error_msg) from e

        finally:
            engine.dispose()
```

### 3. Tests

File: `tests/drivers/test_mysql_extractor_driver.py`

```python
"""Tests for MySQL Extractor Driver."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
from osiris.drivers.mysql_extractor_driver import MySQLExtractorDriver


@pytest.fixture
def driver():
    """Create driver instance."""
    return MySQLExtractorDriver()


@pytest.fixture
def mock_ctx():
    """Create mock execution context."""
    ctx = Mock()
    ctx.log_metric = Mock()
    return ctx


@pytest.fixture
def base_config():
    """Base configuration for tests."""
    return {
        "host": "localhost",
        "port": 3306,
        "database": "testdb",
        "user": "testuser",
        "password": "testpass",  # pragma: allowlist secret
    }


@patch("sqlalchemy.create_engine")
@patch("pandas.read_sql_query")
def test_extract_with_query(mock_read_sql, mock_engine, driver, mock_ctx, base_config):
    """Test extraction with custom SQL query."""
    # Mock engine and connection
    mock_conn = MagicMock()
    mock_engine_instance = MagicMock()
    mock_engine_instance.connect.return_value.__enter__.return_value = mock_conn
    mock_engine.return_value = mock_engine_instance

    # Mock query result
    mock_result = Mock()
    mock_result.fetchone.return_value = (1,)
    mock_conn.execute.return_value = mock_result

    # Mock DataFrame
    test_df = pd.DataFrame([
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ])
    mock_read_sql.return_value = test_df

    config = base_config.copy()
    config["query"] = "SELECT id, name FROM users"

    result = driver.run(step_id="test_step", config=config, ctx=mock_ctx)

    assert "df" in result
    assert len(result["df"]) == 2
    assert result["df"].iloc[0]["name"] == "Alice"
    mock_ctx.log_metric.assert_called_with("rows_read", 2)


@patch("sqlalchemy.create_engine")
@patch("pandas.read_sql_query")
def test_extract_with_table(mock_read_sql, mock_engine, driver, mock_ctx, base_config):
    """Test extraction with table name (auto-generates query)."""
    # Mock engine and connection
    mock_conn = MagicMock()
    mock_engine_instance = MagicMock()
    mock_engine_instance.connect.return_value.__enter__.return_value = mock_conn
    mock_engine.return_value = mock_engine_instance

    # Mock test connection
    mock_result = Mock()
    mock_result.fetchone.return_value = (1,)
    mock_conn.execute.return_value = mock_result

    # Mock DataFrame
    test_df = pd.DataFrame([{"id": 1}, {"id": 2}, {"id": 3}])
    mock_read_sql.return_value = test_df

    config = base_config.copy()
    config["table"] = "customers"
    config["limit"] = 10

    result = driver.run(step_id="test_step", config=config, ctx=mock_ctx)

    assert "df" in result
    assert len(result["df"]) == 3
    # Verify query was generated
    call_args = mock_read_sql.call_args
    query = call_args[0][0]
    assert "SELECT * FROM `customers`" in query
    assert "LIMIT 10" in query


@patch("sqlalchemy.create_engine")
@patch("pandas.read_sql_query")
def test_extract_with_columns(mock_read_sql, mock_engine, driver, mock_ctx, base_config):
    """Test extraction with specific columns."""
    # Mock engine and connection
    mock_conn = MagicMock()
    mock_engine_instance = MagicMock()
    mock_engine_instance.connect.return_value.__enter__.return_value = mock_conn
    mock_engine.return_value = mock_engine_instance

    mock_result = Mock()
    mock_result.fetchone.return_value = (1,)
    mock_conn.execute.return_value = mock_result

    test_df = pd.DataFrame([{"id": 1, "name": "Alice"}])
    mock_read_sql.return_value = test_df

    config = base_config.copy()
    config["table"] = "users"
    config["columns"] = ["id", "name"]

    result = driver.run(step_id="test_step", config=config, ctx=mock_ctx)

    assert "df" in result
    # Verify columns in generated query
    call_args = mock_read_sql.call_args
    query = call_args[0][0]
    assert "`id`, `name`" in query


@patch("sqlalchemy.create_engine")
def test_connection_error(mock_engine, driver, mock_ctx, base_config):
    """Test handling of connection errors."""
    import sqlalchemy as sa

    mock_engine_instance = MagicMock()
    mock_engine.return_value = mock_engine_instance

    # Simulate connection error
    mock_engine_instance.connect.side_effect = sa.exc.OperationalError(
        "statement", "params", "orig"
    )

    config = base_config.copy()
    config["query"] = "SELECT * FROM test"

    with pytest.raises(RuntimeError, match="MySQL connection failed"):
        driver.run(step_id="test_step", config=config, ctx=mock_ctx)


@patch("sqlalchemy.create_engine")
def test_query_syntax_error(mock_engine, driver, mock_ctx, base_config):
    """Test handling of SQL syntax errors."""
    import sqlalchemy as sa

    mock_conn = MagicMock()
    mock_engine_instance = MagicMock()
    mock_engine_instance.connect.return_value.__enter__.return_value = mock_conn
    mock_engine.return_value = mock_engine_instance

    # Test connection succeeds
    mock_result = Mock()
    mock_result.fetchone.return_value = (1,)
    mock_conn.execute.return_value = mock_result

    # But query fails with syntax error
    with patch("pandas.read_sql_query") as mock_read_sql:
        mock_read_sql.side_effect = sa.exc.ProgrammingError(
            "statement", "params", "orig"
        )

        config = base_config.copy()
        config["query"] = "SELECT * FORM invalid"  # Typo: FORM instead of FROM

        with pytest.raises(RuntimeError, match="MySQL query failed"):
            driver.run(step_id="test_step", config=config, ctx=mock_ctx)


@patch("sqlalchemy.create_engine")
def test_discover_tables(mock_engine, driver, mock_ctx, base_config):
    """Test database discovery."""
    # Mock engine and connection
    mock_conn = MagicMock()
    mock_engine_instance = MagicMock()
    mock_engine_instance.connect.return_value.__enter__.return_value = mock_conn
    mock_engine.return_value = mock_engine_instance

    # Mock SHOW TABLES
    mock_tables_result = Mock()
    mock_tables_result.__iter__ = Mock(return_value=iter([("users",), ("orders",)]))

    # Mock DESCRIBE table
    mock_describe_result = Mock()
    mock_describe_result.__iter__ = Mock(
        return_value=iter([
            ("id", "int(11)", "NO", "PRI"),
            ("name", "varchar(255)", "YES", ""),
        ])
    )

    # Mock COUNT(*)
    mock_count_result = Mock()
    mock_count_result.scalar.return_value = 100

    # Setup execute to return different results based on query
    def execute_side_effect(query):
        query_str = str(query)
        if "SHOW TABLES" in query_str:
            return mock_tables_result
        elif "DESCRIBE" in query_str:
            return mock_describe_result
        elif "COUNT(*)" in query_str:
            return mock_count_result

    mock_conn.execute.side_effect = execute_side_effect

    result = driver.discover(step_id="test_step", config=base_config, ctx=mock_ctx)

    assert "tables" in result
    assert len(result["tables"]) == 2
    assert result["tables"][0]["name"] == "users"
    assert len(result["tables"][0]["columns"]) == 2
    assert result["tables"][0]["row_count"] == 100


def test_missing_database(driver, mock_ctx):
    """Test error when database is missing."""
    config = {
        "host": "localhost",
        "user": "root",
        "password": "pass",  # pragma: allowlist secret
        "query": "SELECT 1",
    }

    with pytest.raises(ValueError, match="'database' is required"):
        driver.run(step_id="test_step", config=config, ctx=mock_ctx)


def test_missing_query_and_table(driver, mock_ctx, base_config):
    """Test error when both query and table are missing."""
    with pytest.raises(ValueError, match="Either 'query' or 'table' is required"):
        driver.run(step_id="test_step", config=base_config, ctx=mock_ctx)
```

## Validation Checklist

Before committing:
- [ ] spec.yaml validates against schema
- [ ] All secrets declared in `secrets` array
- [ ] x-connection-fields has override policies
- [ ] Driver uses run() method with step_id, config, inputs, ctx
- [ ] Driver returns {"df": DataFrame}
- [ ] Tests include secret suppressions (`# pragma: allowlist secret`)
- [ ] Error handling wraps exceptions with RuntimeError
- [ ] Connection pooling configured
- [ ] Passwords masked in logs (use masked_url)
- [ ] Engine disposal in finally block
- [ ] Tests mock sqlalchemy.create_engine
- [ ] Discovery mode implemented and tested

## Connection Pooling Patterns

### Basic Pool
```python
engine = sa.create_engine(
    connection_url,
    pool_size=5,           # Max connections
    pool_recycle=3600,     # Recycle after 1 hour
)
```

### Pool with Overflow
```python
engine = sa.create_engine(
    connection_url,
    pool_size=5,
    max_overflow=10,       # Allow 15 total connections
    pool_timeout=30,       # Wait 30s for connection
)
```

### No Pool (for short-lived scripts)
```python
engine = sa.create_engine(
    connection_url,
    poolclass=sa.pool.NullPool,
)
```

## Database-Specific Notes

### PostgreSQL
Change driver to `postgresql+psycopg2`:
```python
connection_url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
```

### SQLite
```python
connection_url = f"sqlite:///{database_path}"
# No host/port needed
```

### SQL Server
```python
connection_url = f"mssql+pyodbc://{user}:{password}@{host}:{port}/{database}?driver=ODBC+Driver+17+for+SQL+Server"
```

## Next Steps

1. Replace "mysql" with your database type if different
2. Update connection URL format for your database
3. Test connection pooling settings
4. Implement discovery mode if needed
5. Test with real database credentials
6. Validate with: `pytest tests/drivers/test_mysql_extractor_driver.py -v`

## Related Recipes

- **rest-api-extractor.md** - REST API extraction patterns
- **graphql-extractor.md** - GraphQL API extraction
- **connection-pooling.md** - Advanced pooling strategies
