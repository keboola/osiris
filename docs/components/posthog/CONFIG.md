# Osiris PostHog Extractor - Configuration Guide

This document describes the configuration structure for running PostHog extractor in E2B sandbox environments using Osiris.

## Configuration File

**Location:** `config.yaml`

Complete YAML configuration for Osiris driver with inline comments and examples.

## Configuration Structure

```yaml
component_id: string              # Component identifier
resolved_connection: dict          # Pre-resolved API credentials
config: dict                       # Extraction parameters
inputs: dict                       # State from previous run
output: dict                       # Output specification
logging: dict                      # Logging configuration
performance: dict                  # Performance tuning
```

## Parameter Reference

### Component ID

Identifies the component in the E2B ecosystem.

```yaml
component_id: posthog/osiris
```

### Resolved Connection

Pre-resolved PostHog API authentication (resolved by Keboola before passing to Osiris).

| Parameter | Type | Required | Example | Description |
|-----------|------|----------|---------|-------------|
| `api_key` | string | Yes | `phc_xxxxx` | PostHog Personal API Key |
| `project_id` | string | Yes | `12345` | Numeric PostHog project ID |
| `region` | string | No | `us` | Region: `us`, `eu`, or `self_hosted` |
| `custom_base_url` | string | No | `https://posthog.company.com` | Custom URL for self-hosted |

**Example - US Cloud:**
```yaml
resolved_connection:
  api_key: "phc_xxxxxxxxxxxxxxxxxxxxx"
  project_id: "12345"
  region: "us"
  custom_base_url: null
```

**Example - EU Cloud:**
```yaml
resolved_connection:
  api_key: "phc_xxxxxxxxxxxxxxxxxxxxx"
  project_id: "12345"
  region: "eu"
  custom_base_url: null
```

**Example - Self-Hosted:**
```yaml
resolved_connection:
  api_key: "phc_xxxxxxxxxxxxxxxxxxxxx"
  project_id: "12345"
  region: "self_hosted"
  custom_base_url: "https://posthog.mycompany.com"
```

### Config - Source

Data extraction configuration.

| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| `data_type` | string | `events` | - | `events` or `persons` |
| `event_types` | array | `[]` | - | Filter event types (empty = all) |
| `lookback_window_minutes` | int | `15` | 5-60 | Minutes to look back before state |
| `initial_since` | string | `null` | - | ISO8601 timestamp for first run |
| `page_size` | int | `1000` | 100-10000 | Records per API request |
| `incremental_field` | string | `timestamp` | - | Field for incremental loading |

**Example - Extract All Events:**
```yaml
config:
  source:
    data_type: "events"
    event_types: []
    lookback_window_minutes: 15
    initial_since: null
    page_size: 1000
    incremental_field: "timestamp"
```

**Example - Extract Filtered Events:**
```yaml
config:
  source:
    data_type: "events"
    event_types: ["$pageview", "$identify"]
    lookback_window_minutes: 15
    page_size: 2000
    incremental_field: "timestamp"
```

**Example - Extract Persons:**
```yaml
config:
  source:
    data_type: "persons"
    lookback_window_minutes: 10
    page_size: 1500
    incremental_field: "created_at"
```

### Config - Destination

Output configuration.

| Parameter | Type | Description |
|-----------|------|-------------|
| `table_name` | string | Output table name (no spaces) |
| `primary_key` | array | Primary key columns for deduplication |

**Example - Events:**
```yaml
config:
  destination:
    table_name: "posthog_events"
    primary_key: ["uuid"]
```

**Example - Persons:**
```yaml
config:
  destination:
    table_name: "posthog_persons"
    primary_key: ["id"]
```

### Inputs - State

Incremental loading state from previous run.

On first run, state is empty. On subsequent runs, Osiris uses state to:
1. Resume from last extracted timestamp
2. Avoid re-extracting duplicate rows
3. Track schema changes

```yaml
inputs:
  state:
    posthog_events:
      # High-watermark timestamp from last run
      # Next extraction starts from this timestamp (after lookback window)
      last_timestamp: "2025-11-08T10:30:00Z"

      # Tie-breaker UUID for pagination
      # Used with last_timestamp to handle duplicate timestamps
      last_uuid: "abc-123-uuid"

      # Recent UUIDs from lookback window
      # Prevents processing duplicates when data overlaps
      recent_uuids:
        - "uuid-1"
        - "uuid-2"
        - "uuid-3"

      # Column names from last extraction
      # Maintains consistent CSV schema
      columns:
        - "uuid"
        - "event"
        - "timestamp"
        - "distinct_id"
        - "person_id"
        - "properties_$browser"
        - "properties_$pathname"
```

**Example - First Run (Empty State):**
```yaml
inputs:
  state:
    posthog_events:
      last_timestamp: null
      last_uuid: null
      recent_uuids: []
      columns: null
```

### Output

Output format specification.

```yaml
output:
  format: "jsonl"  # JSON Lines (one JSON object per line)
```

**Supported Formats:**
- `jsonl` - JSON Lines (default, best for streaming)
- `csv` - CSV format (if supported by driver version)
- `parquet` - Apache Parquet (if supported)

### Logging

Logging configuration for Osiris driver.

| Parameter | Type | Values | Description |
|-----------|------|--------|-------------|
| `level` | string | debug, info, warning, error | Log level |
| `verbose_http` | bool | true, false | Log HTTP requests/responses |

```yaml
logging:
  level: "info"
  verbose_http: false
```

### Performance

E2B sandbox performance tuning.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `batch_size` | int | `5000` | Max rows to buffer in memory |
| `request_timeout` | int | `30` | HTTP request timeout (seconds) |
| `pool_size` | int | `4` | Concurrent HTTP connections |
| `retries.max_attempts` | int | `3` | Max retry attempts |
| `retries.backoff_factor` | float | `1.0` | Exponential backoff factor |
| `retries.timeout_seconds` | int | `30` | Total retry timeout |

```yaml
performance:
  batch_size: 5000           # Lower for tight memory (E2B: 1-4GB)
  request_timeout: 30        # Seconds
  pool_size: 4              # Concurrent connections
  retries:
    max_attempts: 3
    backoff_factor: 1.0
    timeout_seconds: 30
```

**Tuning for E2B Sandboxes:**

```yaml
performance:
  # Low memory sandbox (512MB - 1GB)
  batch_size: 1000
  pool_size: 1
  request_timeout: 60

  # Medium memory sandbox (1GB - 2GB)
  batch_size: 3000
  pool_size: 2
  request_timeout: 45

  # High memory sandbox (2GB+)
  batch_size: 5000
  pool_size: 4
  request_timeout: 30
```

## Common Configurations

### Basic Events Extraction

```yaml
component_id: posthog/osiris

resolved_connection:
  api_key: "phc_xxxxx"
  project_id: "12345"
  region: "us"

config:
  source:
    data_type: "events"
    page_size: 1000
  destination:
    table_name: "posthog_events"
    primary_key: ["uuid"]

inputs:
  state:
    posthog_events:
      last_timestamp: null
      last_uuid: null
      recent_uuids: []
      columns: null

logging:
  level: "info"
```

### Filtered Events with State

```yaml
component_id: posthog/osiris

resolved_connection:
  api_key: "phc_xxxxx"
  project_id: "12345"
  region: "us"

config:
  source:
    data_type: "events"
    event_types: ["$pageview", "$identify"]
    lookback_window_minutes: 15
    page_size: 2000
  destination:
    table_name: "posthog_events_filtered"
    primary_key: ["uuid"]

inputs:
  state:
    posthog_events_filtered:
      last_timestamp: "2025-11-08T10:00:00Z"
      last_uuid: "evt-123"
      recent_uuids: ["uuid-1", "uuid-2", "uuid-3"]
      columns: ["uuid", "event", "timestamp"]

logging:
  level: "info"

performance:
  batch_size: 3000
  pool_size: 2
```

### Persons Extraction

```yaml
component_id: posthog/osiris

resolved_connection:
  api_key: "phc_xxxxx"
  project_id: "12345"
  region: "us"

config:
  source:
    data_type: "persons"
    page_size: 1500
    incremental_field: "created_at"
  destination:
    table_name: "posthog_persons"
    primary_key: ["id"]

inputs:
  state:
    posthog_persons:
      last_timestamp: null
      last_uuid: null
      recent_uuids: []
      columns: null

logging:
  level: "info"
```

### Constrained E2B Sandbox

For sandboxes with limited memory (E2B default: 1GB):

```yaml
component_id: posthog/osiris

resolved_connection:
  api_key: "phc_xxxxx"
  project_id: "12345"
  region: "us"

config:
  source:
    data_type: "events"
    page_size: 500         # Smaller batch
    lookback_window_minutes: 10
  destination:
    table_name: "posthog_events"
    primary_key: ["uuid"]

inputs:
  state:
    posthog_events:
      last_timestamp: null
      last_uuid: null
      recent_uuids: []
      columns: null

logging:
  level: "info"

performance:
  batch_size: 1000        # Keep memory usage low
  request_timeout: 60
  pool_size: 1           # Single connection
  retries:
    max_attempts: 2
    backoff_factor: 2.0
    timeout_seconds: 60
```

## Incremental Loading

### How It Works

1. **First Run:**
   - State is empty
   - Extraction starts from `initial_since` or 30 days ago
   - All matching rows extracted

2. **Subsequent Runs:**
   - State contains `last_timestamp` (high-watermark)
   - Extraction applies `lookback_window_minutes`
   - Actual start = `last_timestamp - lookback_window_minutes`
   - Prevents missing late-arriving events

3. **State Update:**
   - After extraction, state updated with:
     - New `last_timestamp` (highest timestamp seen)
     - New `last_uuid` (tie-breaker for same timestamp)
     - Updated `recent_uuids` (for deduplication)

### Example State Flow

**Run 1 (First Run):**
```yaml
# Config: initial_since = 2025-11-01T00:00:00Z
inputs:
  state:
    events:
      last_timestamp: null
      recent_uuids: []

# After extraction:
# Output state updates to:
last_timestamp: 2025-11-08T10:00:00Z
last_uuid: "evt-999"
recent_uuids: ["uuid-900", "uuid-901", ..., "uuid-999"]
```

**Run 2 (Next Day, 24h later):**
```yaml
# State preserved from Run 1
inputs:
  state:
    events:
      last_timestamp: 2025-11-08T10:00:00Z
      last_uuid: "evt-999"
      recent_uuids: ["uuid-900", "uuid-901", ..., "uuid-999"]

# Actual extraction with lookback:
# Start = 2025-11-08T10:00:00Z - 15 min = 2025-11-08T09:45:00Z
# This overlaps with Run 1 data
# Deduplication prevents re-extracting UUIDs in recent_uuids
```

## Performance Tips

### For Large Datasets (100k+ events/day)

```yaml
config:
  source:
    page_size: 5000        # Larger pages = fewer requests
    lookback_window_minutes: 10

performance:
  batch_size: 10000       # Buffer more rows
  pool_size: 4           # More concurrent connections
  request_timeout: 45
```

### For Small Datasets (<1k events/day)

```yaml
config:
  source:
    page_size: 500         # Smaller pages = less memory
    lookback_window_minutes: 20

performance:
  batch_size: 1000
  pool_size: 1
  request_timeout: 60
```

### For High-Frequency Runs (Every Hour)

```yaml
config:
  source:
    lookback_window_minutes: 5    # Smaller window = less overlap

performance:
  batch_size: 2000
  pool_size: 2
  request_timeout: 30
```

### For Low-Frequency Runs (Daily)

```yaml
config:
  source:
    lookback_window_minutes: 30   # Larger window = more coverage

performance:
  batch_size: 5000
  pool_size: 4
  request_timeout: 45
```

## Troubleshooting

### State Not Updating

**Problem:** State remains null after extraction

**Cause:** Driver may not be persisting state correctly

**Solution:**
1. Check driver output for errors
2. Verify state file permissions
3. Ensure state is returned in driver output

### Duplicate Rows

**Problem:** Same row extracted multiple times

**Causes:**
1. State not being loaded
2. `recent_uuids` not being checked
3. Clock drift between runs

**Solutions:**
1. Verify state is persisted between runs
2. Check `lookback_window_minutes` settings
3. Ensure server clocks are synchronized

### Memory Issues

**Problem:** Driver crashes with OOM error

**Solutions:**
1. Reduce `batch_size`
2. Reduce `page_size`
3. Reduce `pool_size` (fewer concurrent connections)
4. Increase `lookback_window_minutes` to extract less data per run

### Rate Limit Errors

**Problem:** Driver hits PostHog rate limit (429)

**Solutions:**
1. Reduce `page_size`
2. Reduce `pool_size`
3. Increase `request_timeout`
4. Run extraction less frequently

## Integration with Keboola

Keboola automatically:
1. Resolves connection credentials
2. Passes configuration to Osiris
3. Persists state between runs
4. Schedules periodic extraction

From the Keboola component perspective:
- Configuration is passed as YAML file
- Credentials are pre-resolved
- State is managed by Keboola scheduler
- Output is captured as JSONL stream

## Related Files

- **Osiris Driver:** `driver.py`
- **Configuration Example:** `config.yaml`
- **Keboola Configuration:** `../posthog-keboola/data/config.json`
- **Testing:** `../scripts/quick_test.sh`

## API Documentation

- **PostHog API:** https://posthog.com/docs/api
- **E2B Osiris:** https://e2b.dev/docs
- **Keboola Connectors:** https://developers.keboola.com
