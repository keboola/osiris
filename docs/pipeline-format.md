# MVP OML Specification - Simplified ETL Format

**Version:** 1.0-MVP
**Date:** 2025-08-28
**Scope:** Basic ETL pipelines only

## Overview

Simplified Osiris Markup Language (OML) for MVP implementation. Focuses on essential ETL operations with minimal complexity.

## Format

```yaml
version: "1.0"
pipeline: <pipeline_name>

extract:
  - id: <unique_id>
    source: <mysql|supabase|csv>
    table: <table_name>  # for databases
    path: <file_path>    # for files
    connection: <connection_name>  # for databases

transform:
  - id: <unique_id>
    engine: duckdb
    inputs: [<extract_id>, ...]
    sql: |
      <DuckDB SQL query>

load:
  - id: <unique_id>
    from: <transform_id>
    to: <csv|parquet|json|mysql|supabase>
    path: <output_path>      # for files
    table: <table_name>      # for databases
    connection: <connection_name>  # for databases
    mode: <overwrite|append>  # optional, default: overwrite
```

## Supported Components (MVP)

### Extract Sources

- `mysql` - MySQL/MariaDB databases
- `supabase` - Supabase (PostgreSQL-compatible) databases
- `csv` - CSV files

### Transform Engine

- `duckdb` - Local DuckDB engine only

### Load Destinations

- `csv` - CSV files
- `parquet` - Parquet files
- `json` - JSON files
- `mysql` - MySQL/MariaDB databases
- `supabase` - Supabase (PostgreSQL-compatible) databases

## Example Pipeline

```yaml
version: "1.0"
pipeline: movie_analysis

extract:
  - id: get_movies
    source: supabase
    table: movies
    connection: main_db

  - id: get_ratings
    source: supabase
    table: ratings
    connection: main_db

transform:
  - id: analyze_top_movies
    engine: duckdb
    inputs: [get_movies, get_ratings]
    sql: |
      SELECT
        m.title,
        m.year,
        AVG(r.rating) as avg_rating,
        COUNT(r.rating) as num_ratings
      FROM get_movies m
      JOIN get_ratings r ON m.id = r.movie_id
      WHERE m.year >= 2020
      GROUP BY m.title, m.year
      HAVING COUNT(r.rating) >= 100
      ORDER BY avg_rating DESC
      LIMIT 10

load:
  - id: save_results
    from: analyze_top_movies
    to: csv
    path: output/top_movies_2020s.csv

  - id: save_to_db
    from: analyze_top_movies
    to: supabase
    table: top_movies_analysis
    connection: main_db
    mode: overwrite
```

## Key Rules

### 1. Table References in SQL

- Use extract IDs as table names in SQL
- Example: `SELECT * FROM get_movies` where `get_movies` is the extract ID

### 2. Linear Dependencies

- Extract → Transform → Load
- Transform inputs must reference extract IDs
- Load `from` must reference transform ID

### 3. DuckDB Context

- All transforms run in local DuckDB
- Can use CREATE TEMP TABLE, INSERT, UPDATE, DELETE
- No external database modifications
- Full DuckDB SQL syntax supported

### 4. File Paths

- Relative paths resolved from pipeline file location
- Absolute paths supported
- Output directories created automatically

## Validation Rules

### Required Fields

**Pipeline Level:**

- `version`: Must be "1.0"
- `pipeline`: Pipeline name (alphanumeric + underscore)

**Extract:**

- `id`: Unique identifier
- `source`: One of [mysql, supabase, csv]
- `table` (for databases) OR `path` (for files)
- `connection`: Connection name (for databases)

**Transform:**

- `id`: Unique identifier
- `engine`: Must be "duckdb"
- `inputs`: List of extract IDs
- `sql`: Valid DuckDB SQL

**Load:**

- `id`: Unique identifier
- `from`: Transform ID
- `to`: One of [csv, parquet, json, mysql, supabase]
- `path`: Output file path (for files)
- `table`: Table name (for databases)
- `connection`: Connection name (for databases)

### Naming Conventions

- IDs: lowercase, underscore separated (e.g., `get_users`, `calc_revenue`)
- Pipeline names: descriptive, underscore separated
- No spaces or special characters in IDs

## Excluded from MVP

These features are NOT supported in MVP:

- Multiple transform engines (only DuckDB)
- Complex orchestration (dependencies, scheduling)
- Streaming/incremental processing
- Schema validation
- Data quality checks
- Error recovery configuration
- Parallel execution hints
- Caching directives
- Metadata/documentation sections

## Environment Variables

Database connections use environment variables:

**MySQL:**

- `MYSQL_HOST`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_DATABASE`
- `MYSQL_PORT` (optional, default: 3306)

**Supabase:**

- `SUPABASE_URL`
- `SUPABASE_KEY`

## Execution

```bash
# Generate pipeline through conversation
osiris chat

# Run generated pipeline
osiris run pipeline.yaml

# Run with dry-run to validate pipeline syntax
osiris run pipeline.yaml --dry-run

# Validate Osiris configuration
osiris validate
```

## Migration Path

This MVP format is designed to be forward-compatible with the full OML v2.0 specification. Future versions will add:

- Additional transform engines
- Complex orchestration
- Schema validation
- Data quality rules
- Advanced error handling

For now, focus on simple, working ETL pipelines.
