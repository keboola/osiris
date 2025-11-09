# Filesystem Connections Guide

This guide explains how to use filesystem connections in Osiris for portable, environment-aware data pipelines.

## Overview

Filesystem connections provide a structured way to reference directories for file-based data operations (CSV, JSON, Parquet, etc.). Instead of hardcoding absolute paths in your pipelines, you define connection profiles in `osiris_connections.yaml` that specify base directories.

**Benefits:**
- **Portability**: Pipelines work across different environments (dev, staging, production)
- **Environment Separation**: Separate input/output locations with different profiles
- **Discovery Support**: Scan directories to find available files automatically
- **Maintainability**: Change paths in one place (connections config) instead of updating all pipelines

## Configuration

### Basic Setup

In `osiris_connections.yaml`:

```yaml
version: 1
connections:
  filesystem:
    local:
      base_dir: ./output      # Output directory for generated files
    exports:
      base_dir: ./data        # Input directory for reading files
    archive:
      base_dir: /mnt/archive  # Absolute path for archived data
```

**Key Fields:**
- `base_dir`: Root directory for all file operations using this connection
  - Can be relative (to current working directory) or absolute
  - Paths in pipeline steps are resolved relative to this directory

### Multiple Profiles

You can define multiple filesystem connection profiles for different purposes:

| Profile | Purpose | Example base_dir |
|---------|---------|-----------------|
| `local` | Local development output | `./output` |
| `exports` | Data exports/imports | `./data/exports` |
| `staging` | Staging environment | `/var/osiris/staging` |
| `production` | Production data | `/mnt/data/production` |
| `archive` | Long-term storage | `/mnt/archive` |

## Discovery Workflow

Discovery mode scans a filesystem connection's `base_dir` to find available files and their schemas.

### Step 1: Configure Connection

```yaml
# osiris_connections.yaml
connections:
  filesystem:
    exports:
      base_dir: ./data/exports
```

### Step 2: Run Discovery

```bash
# Discover CSV files in ./data/exports
osiris mcp discovery run \
  --connection "@filesystem.exports" \
  --component "filesystem.csv_extractor" \
  --samples 5 \
  --json
```

### Step 3: Review Results

Discovery output includes:
- List of all CSV files found in `base_dir`
- File sizes and column counts
- Sample rows from each file (5 rows in this example)
- Inferred column types and schemas

Example output structure:

```json
{
  "discovery_id": "disc_20240315_143022",
  "status": "success",
  "summary": {
    "file_count": 12,
    "total_size_mb": 45.6,
    "discovered_files": [
      {
        "path": "customers.csv",
        "size_kb": 1024,
        "columns": ["id", "name", "email", "created_at"],
        "sample_rows": 5,
        "inferred_types": {
          "id": "int64",
          "name": "string",
          "email": "string",
          "created_at": "datetime"
        }
      }
    ]
  }
}
```

### Step 4: Create Pipeline

Use discovered file paths in your OML pipeline:

```yaml
oml_version: "0.1.0"
name: process-exports
steps:
  - id: extract-customers
    component: filesystem.csv_extractor
    mode: read
    config:
      connection: "@filesystem.exports"
      path: customers.csv          # Resolved as ./data/exports/customers.csv
      parse_dates: ["created_at"]

  - id: extract-orders
    component: filesystem.csv_extractor
    mode: read
    config:
      connection: "@filesystem.exports"
      path: orders.csv             # Resolved as ./data/exports/orders.csv
```

## Extraction Examples

### Example 1: Read CSV with Connection

```yaml
steps:
  - id: extract-data
    component: filesystem.csv_extractor
    mode: read
    config:
      connection: "@filesystem.exports"
      path: customers.csv           # Relative to base_dir
      delimiter: ","
      header: true
      encoding: "utf-8"
```

**Path Resolution:**
- Connection `@filesystem.exports` has `base_dir: ./data`
- File path `customers.csv` is relative
- Final path: `./data/customers.csv`

### Example 2: Read CSV without Connection

```yaml
steps:
  - id: extract-data
    component: filesystem.csv_extractor
    mode: read
    config:
      path: /absolute/path/to/customers.csv  # Absolute path
      delimiter: ","
      header: true
```

**When to use absolute paths:**
- One-off pipelines for specific files
- Testing or debugging
- Files outside your project structure

**When to use connections:**
- Reusable pipelines across environments
- Files organized in consistent directory structures
- When you need discovery support

### Example 3: Write CSV with Connection

```yaml
steps:
  - id: extract-movies
    component: mysql.extractor
    mode: read
    config:
      connection: "@mysql.default"
      query: "SELECT * FROM movies"

  - id: write-movies-csv
    component: filesystem.csv_writer
    mode: write
    inputs:
      df: "@extract-movies"
    config:
      connection: "@filesystem.local"
      path: movies.csv              # Resolved as ./output/movies.csv
      write_mode: replace
      create_if_missing: true
      delimiter: ","
      header: true
```

**Benefits:**
- Output location controlled by connection config
- Easy to change output directory (dev vs prod)
- Pipeline code stays environment-agnostic

## Advanced Patterns

### Pattern 1: Environment-Specific Connections

**Development** (`osiris_connections.yaml`):
```yaml
connections:
  filesystem:
    exports:
      base_dir: ./local_data
```

**Production** (`osiris_connections.yaml`):
```yaml
connections:
  filesystem:
    exports:
      base_dir: /mnt/production/exports
```

Same pipeline works in both environments - only connection config changes.

### Pattern 2: Input/Output Separation

```yaml
connections:
  filesystem:
    raw_data:
      base_dir: /mnt/incoming      # Read-only input data
    processed:
      base_dir: /mnt/processed     # Processed output
    archive:
      base_dir: /mnt/archive       # Long-term storage
```

Pipeline:
```yaml
steps:
  - id: extract-raw
    component: filesystem.csv_extractor
    config:
      connection: "@filesystem.raw_data"
      path: daily_export.csv

  - id: write-processed
    component: filesystem.csv_writer
    inputs:
      df: "@extract-raw"
    config:
      connection: "@filesystem.processed"
      path: daily_export_clean.csv

  - id: write-archive
    component: filesystem.csv_writer
    inputs:
      df: "@extract-raw"
    config:
      connection: "@filesystem.archive"
      path: "archive/2024-03-15_daily_export.csv"
```

### Pattern 3: Discovery-Driven Pipelines

Use discovery to build dynamic pipelines:

```bash
# 1. Discover available files
DISCOVERY=$(osiris mcp discovery run \
  --connection "@filesystem.exports" \
  --component "filesystem.csv_extractor" \
  --json)

# 2. Extract file list
FILES=$(echo "$DISCOVERY" | jq -r '.summary.discovered_files[].path')

# 3. Generate pipeline dynamically (or use chat mode)
for file in $FILES; do
  echo "Processing $file..."
  # Generate OML steps for each file
done
```

## Connection vs No Connection

### With Connection (Recommended)

**Advantages:**
- Environment portability
- Centralized path management
- Discovery support
- Easy testing (swap connections)

**Example:**
```yaml
config:
  connection: "@filesystem.exports"
  path: data.csv    # ./data/exports/data.csv
```

### Without Connection

**Advantages:**
- Simpler for one-off tasks
- Direct control over paths
- No connection config needed

**Example:**
```yaml
config:
  path: /absolute/path/to/data.csv
```

## Troubleshooting

### Issue: File not found

**Error:**
```
FileNotFoundError: [Errno 2] No such file or directory: './data/customers.csv'
```

**Solutions:**
1. Check `base_dir` in connection config matches actual directory
2. Verify file path is correct relative to `base_dir`
3. Run discovery to see what files are available
4. Use absolute path temporarily to debug

### Issue: Connection not found

**Error:**
```
ConnectionError: Connection '@filesystem.exports' not found
```

**Solutions:**
1. Verify `osiris_connections.yaml` exists in working directory
2. Check connection family and alias match exactly (case-sensitive)
3. Run `osiris connections list` to see available connections

### Issue: Permission denied

**Error:**
```
PermissionError: [Errno 13] Permission denied: '/mnt/data/file.csv'
```

**Solutions:**
1. Check directory permissions: `ls -la /mnt/data`
2. Ensure user has read/write access
3. For production, configure appropriate filesystem permissions
4. Use connection with accessible `base_dir` for testing

## Component Compatibility

Filesystem connections work with these components:

| Component | Mode | Connection Support | Discovery |
|-----------|------|-------------------|-----------|
| `filesystem.csv_extractor` | read | Yes | Yes |
| `filesystem.csv_writer` | write | Yes | No |
| `filesystem.json_extractor` | read | Yes | Yes |
| `filesystem.json_writer` | write | Yes | No |
| `filesystem.parquet_extractor` | read | Yes | Yes |
| `filesystem.parquet_writer` | write | Yes | No |

Check component spec for specific `x-connection-fields` to see which fields come from connections.

## Best Practices

1. **Use connections for reusable pipelines**: Makes pipelines environment-agnostic
2. **Separate input/output with different profiles**: `raw_data`, `processed`, `archive`
3. **Run discovery before building pipelines**: Understand available data first
4. **Use relative paths in pipelines**: Let connections handle environment-specific prefixes
5. **Document your connection profiles**: Add comments explaining each profile's purpose
6. **Test with different connections**: Validate pipelines work across environments

## Related Documentation

- [Quickstart Guide](../quickstart.md) - Basic filesystem connection setup
- [MCP Tool Reference](../mcp/tool-reference.md) - Discovery API details
- [Component Specifications](../../components/README.md) - Component-specific connection fields
- [x-connection-fields Reference](../reference/x-connection-fields.md) - Connection field override policies
