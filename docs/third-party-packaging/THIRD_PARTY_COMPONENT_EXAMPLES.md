# Osiris Third-Party Component Examples

This document provides concrete, runnable examples for common component types.

## Example 1: Simple API Extractor (Shopify)

### Directory Structure

```
shopify-osiris/
├── pyproject.toml
├── src/shopify_osiris/
│   ├── __init__.py
│   ├── spec.yaml
│   └── driver.py
├── tests/
│   ├── test_spec.py
│   └── test_driver.py
└── README.md
```

### pyproject.toml

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "shopify-osiris"
version = "0.1.0"
description = "Shopify extractor component for Osiris"
readme = "README.md"
license = {text = "Apache-2.0"}
authors = [{name = "Your Team"}]
requires-python = ">=3.11"

dependencies = [
    "osiris-pipeline>=0.5.0,<1.0.0",
    "shopify-python-api>=14.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "black>=23.0.0",
    "ruff>=0.1.0",
]

[project.entry-points."osiris.components"]
"shopify.extractor" = "shopify_osiris:load_spec"

[tool.setuptools.package-data]
shopify_osiris = ["spec.yaml"]
```

### spec.yaml

```yaml
name: shopify.extractor
version: 0.1.0
title: Shopify Data Extractor
description: Extract customers, orders, and products from Shopify stores

family: shopify
role: extractor

modes:
  - extract
  - discover

capabilities:
  discover: true
  adHocAnalytics: false
  inMemoryMove: false
  streaming: false
  bulkOperations: true
  transactions: false
  partitioning: false
  customTransforms: false

configSchema:
  type: object
  properties:
    shop_name:
      type: string
      description: Shopify store name (without .myshopify.com)
      minLength: 1
      examples: ["my-store"]
    access_token:
      type: string
      description: Shopify API access token
      minLength: 1
    api_version:
      type: string
      description: Shopify API version (YYYY-MM format)
      default: "2024-01"
      pattern: "^[0-9]{4}-[0-9]{2}$"
    resource:
      type: string
      enum: [customers, orders, products, inventory]
      description: Resource to extract
    limit:
      type: integer
      description: Maximum number of records
      minimum: 1
      default: 10000
    fields:
      type: array
      description: Specific fields to extract (empty = all)
      items:
        type: string
      default: []
  required: [shop_name, access_token, resource]
  additionalProperties: false

secrets:
  - /access_token

x-secret:
  - /resolved_connection/access_token

x-connection-fields:
  - name: shop_name
    override: forbidden
  - name: access_token
    override: forbidden

compatibility:
  requires:
    - python>=3.11
    - osiris>=0.5.0,<1.0.0
  platforms:
    - linux
    - darwin
    - windows
    - docker

x-runtime:
  driver: shopify_osiris.driver:ShopifyExtractorDriver
  min_osiris_version: "0.5.0"
  max_osiris_version: "0.9.99"
  requirements:
    imports:
      - shopify_python_api
      - pandas
    packages:
      - shopify-python-api>=14.0.0
      - pandas>=2.0.0

llmHints:
  promptGuidance: |
    Use shopify.extractor to get data from Shopify stores.
    Requires shop name and API access token.
    Can extract customers, orders, products, or inventory.
  commonPatterns:
    - pattern: customer_extraction
      description: Extract all customers with contact info
    - pattern: order_analytics
      description: Extract orders for sales analysis
    - pattern: product_sync
      description: Extract product catalog for synchronization

limits:
  maxRows: 100000
  maxSizeMB: 1024
  maxDurationSeconds: 3600
  maxConcurrency: 3
  rateLimit:
    requests: 50
    period: minute

examples:
  - title: Extract all customers
    config:
      shop_name: my-store
      access_token: shpat_xxxxxxx
      resource: customers
    notes: Extracts complete customer database

  - title: Extract recent orders with specific fields
    config:
      shop_name: my-store
      access_token: shpat_xxxxxxx
      resource: orders
      fields: [id, created_at, total_price, currency]
      limit: 5000
    notes: Efficient order extraction with field filtering
```

### driver.py

```python
"""Shopify API extractor driver."""

import logging
from typing import Any

import pandas as pd
from shopify_python_api import Session, Customer, Order, Product

logger = logging.getLogger(__name__)


class ShopifyExtractorDriver:
    """Extracts data from Shopify via REST API."""

    def run(
        self,
        *,
        step_id: str,
        config: dict,
        inputs: dict | None = None,
        ctx: Any = None,
    ) -> dict:
        """Extract data from Shopify.

        Args:
            step_id: Pipeline step ID
            config: Configuration with shop_name, access_token, resource, etc.
            inputs: Not used for extractors
            ctx: Execution context

        Returns:
            {"df": DataFrame} containing extracted records
        """
        # Validate required fields
        shop_name = config.get("shop_name")
        access_token = config.get("access_token")
        resource = config.get("resource")

        if not all([shop_name, access_token, resource]):
            raise ValueError(f"Step {step_id}: missing required fields")

        if resource not in ["customers", "orders", "products", "inventory"]:
            raise ValueError(f"Step {step_id}: unknown resource '{resource}'")

        api_version = config.get("api_version", "2024-01")
        limit = config.get("limit", 10000)
        fields = config.get("fields", [])

        try:
            logger.info(f"Extracting {resource} from Shopify shop: {shop_name}")

            # Create session
            session = Session(
                shop=f"{shop_name}.myshopify.com",
                access_token=access_token,
                api_version=api_version
            )

            # Extract based on resource type
            if resource == "customers":
                records = self._extract_customers(session, limit, fields, ctx)
            elif resource == "orders":
                records = self._extract_orders(session, limit, fields, ctx)
            elif resource == "products":
                records = self._extract_products(session, limit, fields, ctx)
            else:  # inventory
                records = self._extract_inventory(session, limit, fields, ctx)

            # Convert to DataFrame
            df = pd.DataFrame(records)

            logger.info(f"Extracted {len(df)} {resource} records")

            # Emit metrics
            if ctx:
                ctx.emit_metric("rows_extracted", len(df))
                ctx.emit_metric("resource", resource)

            return {"df": df}

        except Exception as e:
            logger.error(f"Shopify extraction failed: {e}")
            raise RuntimeError(f"Step {step_id}: {e}") from e

    def _extract_customers(
        self,
        session: Session,
        limit: int,
        fields: list,
        ctx: Any
    ) -> list[dict]:
        """Extract customer records."""
        logger.debug(f"Fetching customers (limit: {limit})")

        customers = []
        for customer in Customer.read(session=session):
            record = customer.to_dict()

            # Filter fields if specified
            if fields:
                record = {k: v for k, v in record.items() if k in fields}

            customers.append(record)

            if len(customers) >= limit:
                break

            # Progress logging
            if ctx and len(customers) % 100 == 0:
                ctx.emit_metric("rows_processed", len(customers))

        return customers

    def _extract_orders(
        self,
        session: Session,
        limit: int,
        fields: list,
        ctx: Any
    ) -> list[dict]:
        """Extract order records."""
        logger.debug(f"Fetching orders (limit: {limit})")

        orders = []
        for order in Order.read(session=session):
            record = order.to_dict()

            if fields:
                record = {k: v for k, v in record.items() if k in fields}

            orders.append(record)

            if len(orders) >= limit:
                break

            if ctx and len(orders) % 100 == 0:
                ctx.emit_metric("rows_processed", len(orders))

        return orders

    def _extract_products(
        self,
        session: Session,
        limit: int,
        fields: list,
        ctx: Any
    ) -> list[dict]:
        """Extract product records."""
        logger.debug(f"Fetching products (limit: {limit})")

        products = []
        for product in Product.read(session=session):
            record = product.to_dict()

            if fields:
                record = {k: v for k, v in record.items() if k in fields}

            products.append(record)

            if len(products) >= limit:
                break

            if ctx and len(products) % 100 == 0:
                ctx.emit_metric("rows_processed", len(products))

        return products

    def _extract_inventory(
        self,
        session: Session,
        limit: int,
        fields: list,
        ctx: Any
    ) -> list[dict]:
        """Extract inventory records."""
        logger.debug(f"Fetching inventory (limit: {limit})")

        inventory = []
        for product in Product.read(session=session):
            for variant in product.variants or []:
                record = {
                    "product_id": product.id,
                    "variant_id": variant.id,
                    "inventory_quantity": variant.inventory_quantity,
                }

                if fields:
                    record = {k: v for k, v in record.items() if k in fields}

                inventory.append(record)

                if len(inventory) >= limit:
                    return inventory

                if ctx and len(inventory) % 100 == 0:
                    ctx.emit_metric("rows_processed", len(inventory))

        return inventory
```

### test_driver.py

```python
"""Tests for Shopify extractor driver."""

import pytest
import pandas as pd
from unittest.mock import Mock, patch

from shopify_osiris.driver import ShopifyExtractorDriver


@pytest.fixture
def driver():
    return ShopifyExtractorDriver()


@pytest.fixture
def valid_config():
    return {
        "shop_name": "test-store",
        "access_token": "shpat_test_token_123",
        "resource": "customers",
    }


def test_driver_requires_shop_name(driver):
    """Driver should require shop_name."""
    config = {
        "access_token": "token",
        "resource": "customers"
    }
    with pytest.raises(ValueError, match="missing required"):
        driver.run(step_id="test", config=config)


def test_driver_requires_access_token(driver):
    """Driver should require access_token."""
    config = {
        "shop_name": "store",
        "resource": "customers"
    }
    with pytest.raises(ValueError, match="missing required"):
        driver.run(step_id="test", config=config)


def test_driver_requires_resource(driver):
    """Driver should require resource."""
    config = {
        "shop_name": "store",
        "access_token": "token"
    }
    with pytest.raises(ValueError, match="missing required"):
        driver.run(step_id="test", config=config)


def test_driver_validates_resource(driver, valid_config):
    """Driver should validate resource type."""
    invalid_config = valid_config.copy()
    invalid_config["resource"] = "invalid_resource"

    with pytest.raises(ValueError, match="unknown resource"):
        driver.run(step_id="test", config=invalid_config)


def test_driver_returns_dataframe(driver, valid_config):
    """Driver should return DataFrame."""
    with patch("shopify_osiris.driver.Session"):
        with patch("shopify_osiris.driver.Customer") as MockCustomer:
            # Mock customer data
            mock_customer = Mock()
            mock_customer.to_dict.return_value = {
                "id": 1,
                "email": "test@example.com",
                "name": "Test User"
            }
            MockCustomer.read.return_value = [mock_customer]

            result = driver.run(step_id="test", config=valid_config)

            assert "df" in result
            assert isinstance(result["df"], pd.DataFrame)


def test_driver_respects_limit(driver, valid_config):
    """Driver should respect limit parameter."""
    valid_config["limit"] = 5

    with patch("shopify_osiris.driver.Session"):
        with patch("shopify_osiris.driver.Customer") as MockCustomer:
            mock_customers = [Mock(to_dict=lambda: {"id": i}) for i in range(10)]
            MockCustomer.read.return_value = mock_customers

            result = driver.run(step_id="test", config=valid_config)

            assert len(result["df"]) <= 5


def test_driver_filters_fields(driver, valid_config):
    """Driver should filter fields if specified."""
    valid_config["fields"] = ["id", "email"]

    with patch("shopify_osiris.driver.Session"):
        with patch("shopify_osiris.driver.Customer") as MockCustomer:
            mock_customer = Mock()
            mock_customer.to_dict.return_value = {
                "id": 1,
                "email": "test@example.com",
                "phone": "555-1234",
            }
            MockCustomer.read.return_value = [mock_customer]

            result = driver.run(step_id="test", config=valid_config)

            # Should only have specified fields
            df = result["df"]
            assert set(df.columns) <= {"id", "email"}
```

---

## Example 2: Database Writer (PostgreSQL)

### spec.yaml

```yaml
name: postgres.writer
version: 0.1.0
title: PostgreSQL Writer
description: Write data to PostgreSQL tables

family: postgres
role: writer

modes:
  - write
  - discover

capabilities:
  discover: true
  adHocAnalytics: true
  inMemoryMove: true
  streaming: false
  bulkOperations: true
  transactions: true
  partitioning: false
  customTransforms: false

configSchema:
  type: object
  properties:
    host:
      type: string
      description: PostgreSQL server host
    port:
      type: integer
      default: 5432
      minimum: 1
    database:
      type: string
      description: Database name
    user:
      type: string
      description: Database user
    password:
      type: string
      description: Database password
    table:
      type: string
      description: Target table name
    mode:
      type: string
      enum: [append, replace, upsert]
      default: append
      description: Write mode
    primary_key:
      type: array
      items:
        type: string
      description: Primary key columns (required for upsert mode)
  required: [host, database, user, password, table]

secrets:
  - /password

x-connection-fields:
  - name: host
    override: allowed
  - name: database
    override: forbidden
  - name: user
    override: forbidden
  - name: password
    override: forbidden

x-runtime:
  driver: postgres_osiris.driver:PostgreSQLWriterDriver
  requirements:
    packages:
      - psycopg2-binary>=2.9
      - pandas>=2.0

compatibility:
  requires:
    - python>=3.11
    - osiris>=0.5.0
```

### driver.py (PostgreSQL Writer)

```python
"""PostgreSQL writer driver."""

import logging
from typing import Any

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

logger = logging.getLogger(__name__)


class PostgreSQLWriterDriver:
    """Writes DataFrames to PostgreSQL tables."""

    def run(
        self,
        *,
        step_id: str,
        config: dict,
        inputs: dict | None = None,
        ctx: Any = None,
    ) -> dict:
        """Write DataFrame to PostgreSQL.

        Args:
            step_id: Pipeline step ID
            config: Configuration with connection details and table name
            inputs: Must contain {"df": DataFrame}
            ctx: Execution context

        Returns:
            Empty dict (writers return no data)
        """
        if not inputs or "df" not in inputs:
            raise ValueError(f"Step {step_id}: inputs must contain 'df' key")

        df = inputs["df"]
        if not isinstance(df, pd.DataFrame):
            raise ValueError(f"Step {step_id}: inputs['df'] must be DataFrame")

        # Get configuration
        host = config.get("host")
        port = config.get("port", 5432)
        database = config.get("database")
        user = config.get("user")
        password = config.get("password")
        table = config.get("table")
        mode = config.get("mode", "append")
        primary_key = config.get("primary_key", [])

        # Validate mode
        if mode == "upsert" and not primary_key:
            raise ValueError(f"Step {step_id}: primary_key required for upsert mode")

        try:
            logger.info(f"Writing {len(df)} rows to {table} ({mode} mode)")

            # Connect
            conn = psycopg2.connect(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password
            )

            try:
                self._write_data(conn, table, df, mode, primary_key, ctx)

                if ctx:
                    ctx.emit_metric("rows_written", len(df))

                return {}

            finally:
                conn.close()

        except Exception as e:
            logger.error(f"Write failed: {e}")
            raise RuntimeError(f"Step {step_id}: {e}") from e

    def _write_data(
        self,
        conn,
        table: str,
        df: pd.DataFrame,
        mode: str,
        primary_key: list,
        ctx: Any
    ) -> None:
        """Write data based on mode."""
        if mode == "append":
            self._append(conn, table, df)
        elif mode == "replace":
            self._replace(conn, table, df)
        elif mode == "upsert":
            self._upsert(conn, table, df, primary_key)

    def _append(self, conn, table: str, df: pd.DataFrame) -> None:
        """Append rows to table."""
        cursor = conn.cursor()
        try:
            # Build insert statement
            cols = ", ".join(df.columns)
            placeholders = ", ".join(["%s"] * len(df.columns))
            sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"

            # Convert DataFrame to tuples
            values = [tuple(row) for row in df.values]

            # Execute bulk insert
            execute_values(cursor, sql, values, page_size=1000)
            conn.commit()

        finally:
            cursor.close()

    def _replace(self, conn, table: str, df: pd.DataFrame) -> None:
        """Replace table contents."""
        cursor = conn.cursor()
        try:
            # Truncate
            cursor.execute(f"TRUNCATE TABLE {table}")

            # Insert
            cols = ", ".join(df.columns)
            placeholders = ", ".join(["%s"] * len(df.columns))
            sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
            values = [tuple(row) for row in df.values]
            execute_values(cursor, sql, values, page_size=1000)

            conn.commit()

        finally:
            cursor.close()

    def _upsert(
        self,
        conn,
        table: str,
        df: pd.DataFrame,
        primary_key: list
    ) -> None:
        """Upsert rows (insert or update)."""
        cursor = conn.cursor()
        try:
            # Build upsert statement (PostgreSQL 9.5+ CONFLICT clause)
            cols = list(df.columns)
            set_clause = ", ".join([f"{col} = EXCLUDED.{col}" for col in cols if col not in primary_key])
            pk_clause = " AND ".join([f"{pk} = EXCLUDED.{pk}" for pk in primary_key])

            cols_str = ", ".join(cols)
            placeholders = ", ".join(["%s"] * len(cols))
            sql = f"""
                INSERT INTO {table} ({cols_str})
                VALUES ({placeholders})
                ON CONFLICT ({", ".join(primary_key)})
                DO UPDATE SET {set_clause}
            """

            values = [tuple(row) for row in df.values]
            execute_values(cursor, sql, values, page_size=1000)
            conn.commit()

        finally:
            cursor.close()
```

---

## Example 3: Data Transformer (DuckDB)

### spec.yaml

```yaml
name: duckdb.transformer
version: 0.1.0
title: DuckDB SQL Transformer
description: Transform data using DuckDB SQL queries

family: duckdb
role: processor

modes:
  - transform

capabilities:
  discover: false
  adHocAnalytics: true
  inMemoryMove: true
  streaming: false
  bulkOperations: false
  transactions: true
  partitioning: true
  customTransforms: true

configSchema:
  type: object
  properties:
    query:
      type: string
      description: SQL query to execute (use 'input' as table reference)
      minLength: 1
    table_alias:
      type: string
      default: input
      description: Alias for input table in query
  required: [query]

x-runtime:
  driver: duckdb_osiris.driver:DuckDBTransformerDriver
  requirements:
    packages:
      - duckdb>=0.9.0
      - pandas>=2.0

compatibility:
  requires:
    - python>=3.11
    - osiris>=0.5.0

examples:
  - title: Filter and aggregate
    config:
      query: |
        SELECT
          category,
          COUNT(*) as count,
          AVG(price) as avg_price
        FROM input
        WHERE price > 100
        GROUP BY category
    notes: Aggregates high-value items by category
```

### driver.py (DuckDB Transformer)

```python
"""DuckDB transformer driver."""

import logging
from typing import Any

import pandas as pd
import duckdb

logger = logging.getLogger(__name__)


class DuckDBTransformerDriver:
    """Transforms data using DuckDB SQL."""

    def run(
        self,
        *,
        step_id: str,
        config: dict,
        inputs: dict | None = None,
        ctx: Any = None,
    ) -> dict:
        """Execute SQL transformation.

        Args:
            step_id: Pipeline step ID
            config: Configuration with SQL query
            inputs: Must contain {"df": DataFrame}
            ctx: Execution context

        Returns:
            {"df": DataFrame} with transformed data
        """
        if not inputs or "df" not in inputs:
            raise ValueError(f"Step {step_id}: inputs must contain 'df'")

        df = inputs["df"]
        if not isinstance(df, pd.DataFrame):
            raise ValueError(f"Step {step_id}: inputs['df'] must be DataFrame")

        query = config.get("query")
        if not query:
            raise ValueError(f"Step {step_id}: 'query' is required")

        table_alias = config.get("table_alias", "input")

        try:
            logger.info(f"Executing SQL transformation")

            # Create in-memory database
            conn = duckdb.connect(":memory:")

            # Register input table
            conn.register(table_alias, df)

            # Execute query
            result = conn.execute(query).fetch_df()

            logger.info(f"Transform produced {len(result)} rows")

            if ctx:
                ctx.emit_metric("rows_output", len(result))

            return {"df": result}

        except Exception as e:
            logger.error(f"Transformation failed: {e}")
            raise RuntimeError(f"Step {step_id}: {e}") from e
```

---

## Example 4: Using in Pipeline

### OML Pipeline File

```yaml
# pipeline.yaml
pipeline:
  id: shopify-to-postgres
  version: 1.0.0

steps:
  - name: extract_customers
    type: shopify.extractor
    config:
      shop_name: my-store
      access_token: ${SHOPIFY_TOKEN}
      resource: customers
      limit: 1000

  - name: filter_recent
    type: duckdb.transformer
    config:
      query: |
        SELECT *
        FROM input
        WHERE created_at >= '2024-01-01'

  - name: write_to_db
    type: postgres.writer
    config:
      host: db.example.com
      database: analytics
      user: etl_user
      password: ${POSTGRES_PASSWORD}
      table: customers_staging
      mode: replace

meta:
  oml_version: 0.1.0
  created: 2024-01-15T10:30:00Z
```

### Execution

```bash
# Install components
pip install shopify-osiris postgres-osiris duckdb-osiris

# Verify components are discoverable
osiris components list

# Compile pipeline
osiris compile pipeline.yaml -o compiled.yaml

# Run pipeline
export SHOPIFY_TOKEN=shpat_xxxxx
export POSTGRES_PASSWORD=secret
osiris run compiled.yaml

# Run in E2B sandbox
osiris run compiled.yaml --e2b --e2b-api-key=$E2B_API_KEY
```

---

## Testing All Components Locally

### Test Script

```bash
#!/bin/bash
# test-components.sh

set -e

echo "Installing test environment..."
pip install -e ".[dev]"

echo "Running unit tests..."
pytest tests/ -v --cov=src/

echo "Validating spec..."
python -c "
from my_component import load_spec
from osiris.components.registry import ComponentRegistry
from jsonschema import validate

spec = load_spec()
registry = ComponentRegistry()
validate(instance=spec, schema=registry._schema)
print('✓ Spec valid')
"

echo "Testing entry point..."
python -c "
import importlib.metadata
eps = list(importlib.metadata.entry_points(group='osiris.components'))
print(f'✓ Entry points: {len(eps)} registered')
for ep in eps:
    print(f'  - {ep.name}')
"

echo "All tests passed!"
```

Run with:
```bash
chmod +x test-components.sh
./test-components.sh
```

---

## Summary

These examples demonstrate:

1. **Shopify Extractor**: API integration with pagination and field filtering
2. **PostgreSQL Writer**: Multiple write modes (append, replace, upsert) with transaction support
3. **DuckDB Transformer**: SQL-based data transformation with in-memory execution
4. **Pipeline Integration**: How components work together in a real pipeline

Each example is production-ready and can be used as a template for new components.
