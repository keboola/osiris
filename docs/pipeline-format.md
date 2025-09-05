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

---

## Compiled Manifest Format (M1c)

### Overview

The compiler transforms OML documents into deterministic, secret-free execution artifacts. The primary artifact is the `manifest.yaml` which contains all information needed for execution.

### Manifest Structure

```yaml
# manifest.yaml - Canonical execution plan
version: "0.1.0"  # Manifest format version

pipeline:
  id: <pipeline_id>
  name: <human_readable_name>
  oml_version: "0.1.0"
  fingerprints:
    oml_fp: <sha256_hex>        # OML document fingerprint
    registry_fp: <sha256_hex>    # Component registry fingerprint
    compiler_fp: <sha256_hex>    # Compiler version fingerprint
    params_fp: <sha256_hex>      # Parameters fingerprint
    manifest_fp: <sha256_hex>    # This manifest's fingerprint

steps:
  - id: <step_id>
    driver: <component_name>@<version>  # e.g., mysql.extractor@1.0.0
    mode: <read|write|transform>
    cfg_path: cfg/<step_id>.json       # Path to step configuration
    needs: [<dependency_ids>]          # Step dependencies
    retry:
      max: <int>
      backoff: <none|linear|exp>
      delay_ms: <int>
    timeout: <duration>                # e.g., "30s", "5m"
    idempotency_key: <string>          # Optional
    artifacts:
      out: [<artifact_names>]          # Expected outputs
    metrics: [<metric_names>]          # Tracked metrics
    privacy: <standard|strict>         # Privacy level
    resources:                         # Resource hints
      cpu: <float>
      memory: <string>                 # e.g., "2GB"

meta:
  profile: <active_profile>            # e.g., "dev", "prod"
  run_id: <external_run_id>           # If provided
  generated_at: <iso8601_timestamp>
  toolchain:
    compiler:
      version: <semver>
      build: <build_id>
    registry:
      version: <semver>
      endpoint: <url>
```

### Per-Step Configuration

```json
// cfg/{step_id}.json - Minimal step configuration
{
  "component": "mysql.extractor",
  "mode": "read",
  "config": {
    "connection": "@mysql_default",  // Symbolic reference, no secrets
    "table": "users",
    "query": "SELECT * FROM users WHERE active = true",
    "batch_size": 1000
  },
  "inputs": ["upstream_data"],
  "outputs": ["user_data"]
}
```

### Metadata File

```json
// meta.json - Provenance and fingerprints
{
  "fingerprints": {
    "oml_fp": "sha256:abc123...",
    "registry_fp": "sha256:def456...",
    "compiler_fp": "sha256:ghi789...",
    "params_fp": "sha256:jkl012...",
    "manifest_fp": "sha256:mno345..."
  },
  "compilation": {
    "timestamp": "2025-01-04T12:34:56Z",
    "duration_ms": 250,
    "cache_hit": false,
    "compiler_version": "0.1.0",
    "oml_version": "0.1.0"
  },
  "provenance": {
    "source_file": "pipelines/example.yaml",
    "profile": "dev",
    "parameters_used": ["region", "batch_size"]
  }
}
```

### Effective Configuration

```json
// effective_config.json - Resolved parameters
{
  "params": {
    "region": "us-west",
    "batch_size": 1000,
    "enable_cache": true
  },
  "profile": "dev",
  "profile_overrides": {
    "batch_size": 1000  // Overridden from default 500
  },
  "resolution_order": [
    "cli",
    "env",
    "profile",
    "defaults"
  ]
}
```

### Artifact Directory Structure

```
compiled/                         # Compilation outputs
├── manifest.yaml                 # Canonical execution plan
├── cfg/
│   ├── extract-users.json      # Per-step configurations
│   ├── transform-aggregate.json
│   └── load-results.json
├── meta.json                    # Provenance & fingerprints
└── effective_config.json        # Resolved parameters

_artifacts/                      # Runtime outputs
├── extract-users/
│   └── output.parquet
├── transform-aggregate/
│   └── results.csv
└── load-results/
    └── summary.json
```

### Key Properties

1. **Deterministic**: Same inputs always produce byte-identical manifests
2. **Secret-Free**: No credentials or sensitive data in any artifact
3. **Self-Contained**: Manifest contains all information needed for execution
4. **Fingerprinted**: Every input contributes to cache key computation
5. **Canonical**: Stable ordering, formatting, and serialization

### Cache Key Computation

```
cache_key = SHA256(
  oml_fp || 
  registry_fp || 
  compiler_fp || 
  params_fp || 
  profile
)
```

Where `||` represents concatenation of the hex-encoded fingerprints.
