# OML Pipeline Format Specification

This document specifies OML v0.1.0 used by Osiris v0.2.0.

## Top-Level Structure

OML files must contain exactly these top-level keys:

- **`oml_version`** (required): Must equal `"0.1.0"` exactly
- **`name`** (required): String identifier for the pipeline
- **`steps`** (required): Non-empty array of step objects

Keys explicitly **not allowed**: `version`, `connectors`, `tasks`, `outputs`

## Step Object Fields

Each step in the `steps` array must contain:

- **`id`** (string): Unique identifier within the pipeline
- **`component`** (string): Component reference (e.g., `mysql.extractor`, `filesystem.csv_writer`, `supabase.writer`)
- **`mode`** (string): Execution mode (`read`, `write`, or component-specific)
- **`config`** (object): Component-specific configuration
- **`inputs`** (object, optional): Input mappings from upstream steps

## Connection References

Connections are referenced using the `@family.alias` syntax:

- `@mysql.default` - References the MySQL connection with alias "default"
- `@supabase.main` - References the Supabase connection with alias "main"

Connections are defined in `osiris_connections.yaml` and secrets are resolved via environment variables:

```yaml
# osiris_connections.yaml
connections:
  mysql:
    default:
      host: ${MYSQL_HOST:-localhost}
      port: ${MYSQL_PORT:-3306}
      database: ${MYSQL_DATABASE}
      username: ${MYSQL_USER:-root}
      password: ${MYSQL_PASSWORD}
```

## Examples

### Single-Step Pipeline

Extract from MySQL and write to CSV:

```yaml
oml_version: "0.1.0"
name: "mysql_to_csv"
steps:
  - id: "extract_movies"
    component: "mysql.extractor"
    mode: "read"
    config:
      connection: "@mysql.default"
      query: |
        SELECT id, title, year
        FROM movies
        WHERE year >= 2000
  - id: "write_movies_csv"
    component: "filesystem.csv_writer"
    mode: "write"
    inputs:
      df: "${extract_movies.df}"
    config:
      path: "output/movies.csv"
      write_mode: "overwrite"
```

### Multi-Source Pipeline

Extract from multiple tables and write to Supabase:

```yaml
oml_version: "0.1.0"
name: "consolidate_data"
steps:
  - id: "extract_customers"
    component: "mysql.extractor"
    mode: "read"
    config:
      connection: "@mysql.primary"
      query: "SELECT * FROM customers"

  - id: "extract_orders"
    component: "mysql.extractor"
    mode: "read"
    config:
      connection: "@mysql.primary"
      query: "SELECT * FROM orders WHERE created_at >= '2024-01-01'"

  - id: "write_customers"
    component: "supabase.writer"
    mode: "write"
    inputs:
      df: "${extract_customers.df}"
    config:
      connection: "@supabase.main"
      table: "customers"
      write_mode: "upsert"
      primary_key: "id"
      batch_size: 500

  - id: "write_orders"
    component: "supabase.writer"
    mode: "write"
    inputs:
      df: "${extract_orders.df}"
    config:
      connection: "@supabase.main"
      table: "orders"
      write_mode: "append"
      batch_size: 1000
```

## Validation Rules

1. **Required keys present**: `oml_version`, `name`, `steps` must exist
2. **Forbidden keys absent**: `version`, `connectors`, `tasks`, `outputs` must not exist
3. **Version match**: `oml_version` must equal `"0.1.0"` exactly
4. **Step uniqueness**: All step `id` values must be unique
5. **Component existence**: Referenced components must exist in the registry at compile time
6. **Non-empty steps**: The `steps` array must contain at least one step

## Component Reference

### Extractors
- `mysql.extractor` - Reads data from MySQL/MariaDB
- `supabase.extractor` - Reads data from Supabase (PostgreSQL)

### Writers
- `filesystem.csv_writer` - Writes data to CSV files
- `supabase.writer` - Writes data to Supabase tables
- `mysql.writer` - Writes data to MySQL/MariaDB tables

### Transformers
- `duckdb.transform` - Performs SQL transformations using DuckDB

## Write Modes

Writers support different modes for handling existing data:

- **`append`**: Add new rows to existing data
- **`overwrite`**: Replace all existing data
- **`upsert`**: Insert or update based on primary key
- **`replace`**: Delete existing rows then insert (Supabase-specific)

## Compilation

OML files are compiled into deterministic manifests:

```bash
# Compile OML to manifest
osiris compile pipeline.oml

# The manifest is saved to logs/<session>/compile_<timestamp>/manifest.yaml
```

The compiled manifest contains:
- Resolved configurations (with connection references resolved)
- Step dependencies
- Execution metadata
- Fingerprints for deterministic execution

All secrets are resolved at runtime, never stored in compiled artifacts.
