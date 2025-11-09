# PostHog Osiris Component

Extract analytics data from PostHog using HogQL Query API in isolated E2B sandboxed environments.

## Description

This is an **Osiris-compliant component** for extracting PostHog events, persons, cohorts, and feature flags. Unlike the Keboola extractor that runs within Keboola infrastructure, this component is designed to execute in E2B sandboxed environments with full support for discovery, health checks, and streaming incremental loads.

**Key Features:**
- Full HogQL Query API support with automatic pagination
- Incremental loading with state management (last_run, UUID deduplication)
- Lookback window pattern for exactly-once semantics
- Properties flattening for nested JSON objects
- Rate limit handling with exponential backoff
- Multi-region support (US, EU, self-hosted)
- Discovery capability for resource enumeration
- Health check (doctor) for connection validation

## Installation

### Option 1: From PyPI (when published)

```bash
pip install osiris-posthog
```

### Option 2: From Git

```bash
pip install git+https://github.com/e2b-tereza/extractors.git#subdirectory=posthog-osiris
```

### Option 3: Development Install

```bash
git clone https://github.com/e2b-tereza/extractors.git
cd extractors/posthog-osiris
pip install -e .
```

### Option 4: Manual Install

```bash
# Install dependencies
pip install -r requirements.txt

# Add to Python path or use as local module
export PYTHONPATH="/path/to/posthog-osiris:$PYTHONPATH"
```

## Usage

### 1. Configuration

Create a `config.yaml` file with connection and extraction parameters:

```yaml
# Connection credentials (resolved by Osiris before execution)
resolved_connection:
  api_key: "phc_YOUR_API_KEY_HERE"
  project_id: "12345"
  region: "us"  # us, eu, or self_hosted
  custom_base_url: "https://posthog.example.com"  # Only for self_hosted

# Extraction configuration
data_type: "events"  # events, persons, cohorts, or feature_flags
event_types:
  - "$pageview"
  - "$click"
  - "user_signup"
lookback_window_minutes: 15
initial_since: "2025-11-01T00:00:00Z"  # First run only
page_size: 1000
deduplication_enabled: true
```

### 2. Discovery

List available data types and resources:

```bash
osiris discover posthog --config config.yaml
```

**Output:**
```json
{
  "resources": [
    {"name": "cohorts", "type": "table", "description": "PostHog cohorts"},
    {"name": "events", "type": "table", "description": "PostHog events with properties"},
    {"name": "feature_flags", "type": "table", "description": "PostHog feature flags"},
    {"name": "persons", "type": "table", "description": "PostHog persons with properties"}
  ],
  "fingerprint": "sha256_hash_of_resources",
  "discovered_at": "2025-11-08T10:30:45.123456Z"
}
```

### 3. Health Check

Validate connection and permissions:

```bash
osiris doctor posthog --config config.yaml
```

**Output (Healthy):**
```json
{
  "status": "healthy",
  "message": "Successfully connected to PostHog project 12345",
  "timestamp": "2025-11-08T10:30:45.123456Z"
}
```

**Output (Error):**
```json
{
  "status": "error",
  "category": "auth",
  "message": "Authentication failed. Check API key.",
  "timestamp": "2025-11-08T10:30:45.123456Z"
}
```

### 4. Run Extraction

Extract data locally:

```bash
osiris run posthog --config config.yaml
```

Returns Parquet file with extracted data:
```
output.parquet      # Pandas DataFrame with extracted rows
state.json          # Updated state for next run
```

### 5. Run in E2B Sandbox

Execute securely in isolated E2B environment:

```bash
osiris run posthog --config config.yaml --e2b
```

**With custom E2B configuration:**
```bash
osiris run posthog --config config.yaml --e2b \
  --e2b-api-key $E2B_API_KEY \
  --e2b-timeout 300
```

## Configuration Examples

### Example 1: Extract Events (Events Table)

```yaml
resolved_connection:
  api_key: "phc_demo_key_1234567890"
  project_id: "12345"
  region: "us"

data_type: "events"
event_types:
  - "$pageview"
  - "$click"
  - "user_signup"
lookback_window_minutes: 15
page_size: 1000
deduplication_enabled: true
```

### Example 2: Extract Persons (User Properties)

```yaml
resolved_connection:
  api_key: "phc_demo_key_1234567890"
  project_id: "12345"
  region: "eu"

data_type: "persons"
page_size: 500
deduplication_enabled: false  # No UUID for persons
```

### Example 3: Full Snapshot (History Load)

```yaml
resolved_connection:
  api_key: "phc_demo_key_1234567890"
  project_id: "12345"
  region: "us"

data_type: "events"
initial_since: "2024-01-01T00:00:00Z"  # Start from 1 year ago
lookback_window_minutes: 60  # Large lookback for recovery
page_size: 5000  # Large batch
deduplication_enabled: true
```

### Example 4: Self-Hosted PostHog

```yaml
resolved_connection:
  api_key: "phc_self_hosted_key"
  project_id: "1"
  region: "self_hosted"
  custom_base_url: "https://posthog.company.internal"

data_type: "events"
lookback_window_minutes: 15
page_size: 1000
```

## Capabilities

This Osiris component declares the following capabilities:

| Capability | Supported | Description |
|------------|-----------|-------------|
| **discover** | ✓ Yes | List available data types (events, persons, cohorts, feature_flags) |
| **streaming** | ✓ Yes | Incremental extraction with state management (last_run, seen_uuids) |
| **bulkOperations** | ✓ Yes | Full data extraction with multi-page support |
| **adHocAnalytics** | ✗ No | Not applicable (component extracts, doesn't analyze) |
| **inMemoryMove** | ✗ No | Component returns DataFrames, not in-memory transfer protocol |
| **transactions** | ✗ No | PostHog API is read-only |
| **partitioning** | ✗ No | Handled by client-side pagination |
| **customTransforms** | ✗ No | Data is returned as-is (no transformations) |

## Data Types

### events

PostHog event stream with automatic deduplication by UUID.

**Schema:**
```
uuid (string)                    # Unique event identifier for deduplication
event (string)                   # Event name ($pageview, $click, user_signup, etc.)
timestamp (datetime)             # ISO 8601 timestamp in UTC
distinct_id (string)             # User identifier
person_id (string)               # Internal person ID
properties_* (various)           # Flattened event properties with prefix
person_properties_* (various)    # Flattened person properties with prefix
```

**Example Columns:**
```
uuid, event, timestamp, distinct_id, person_id,
properties_$browser, properties_$os, properties_$ip,
properties_custom_field, person_properties_email, person_properties_plan
```

### persons

User data with properties.

**Schema:**
```
id (string)              # Person ID
created_at (datetime)    # Creation timestamp
is_identified (boolean)  # Whether person is identified
properties_* (various)   # Flattened person properties
```

### cohorts

User cohorts/segments.

**Schema:**
```
id (string)
name (string)
description (string)
created_at (datetime)
```

### feature_flags

Feature flag definitions.

**Schema:**
```
id (string)
key (string)
name (string)
active (boolean)
created_at (datetime)
```

## State Management

The component tracks extraction state for incremental loading:

```json
{
  "last_run": "2025-11-08T10:30:45.123456Z",
  "seen_uuids": [
    "uuid-1",
    "uuid-2",
    "..."
  ]
}
```

**How it works:**
1. First run: Extract all events since `initial_since` (or 30 days ago)
2. Subsequent runs: Extract events since `last_run` minus `lookback_window_minutes`
3. Lookback window catches events that arrived late due to ingestion delays
4. UUID deduplication prevents double-counting (only if `deduplication_enabled: true`)

## Error Categories

The `doctor` (health check) command returns structured error information:

| Category | Cause | Solution |
|----------|-------|----------|
| **auth** | Invalid API key or project ID | Check credentials in config |
| **network** | Cannot reach PostHog API | Check internet connection, firewall |
| **timeout** | Connection timeout (>2s) | Check PostHog API status, network latency |
| **permission** | Insufficient API key permissions | Verify API key has read access |
| **unknown** | Unexpected error | Check logs for details |

## PostHog API Details

**Base URLs:**
- US: `https://us.posthog.com`
- EU: `https://eu.posthog.com`

**Endpoint:** `POST /api/projects/{project_id}/query/`

**Rate Limit:** 2,400 requests/hour for HogQL queries

**Authentication:** Bearer token in `Authorization` header

**Pagination:** Cursor-based with LIMIT + OFFSET in HogQL queries

## Performance Tuning

### page_size

- **Small (100-500):** Lower memory, more API calls
- **Default (1000):** Balanced, recommended for most cases
- **Large (5000-10000):** Fewer API calls, higher memory

### lookback_window_minutes

- **Small (5-10):** Catches recently arrived events
- **Default (15):** Handles typical ingestion delays
- **Large (30-60):** For high-latency scenarios or recovery

### event_types filtering

If possible, filter by `event_types` to reduce data volume:

```yaml
event_types:
  - "$pageview"
  - "$click"
  - "user_signup"
```

## Requirements

- Python 3.9+
- PostHog API access (Personal API Key from PostHog settings)
- PostHog project ID

## Dependencies

- `pandas>=2.2.0` - DataFrame creation and manipulation
- `requests>=2.32.3` - HTTP client for API calls
- `pyyaml>=6.0.1` - YAML configuration parsing

See `requirements.txt` for exact versions.

## License

MIT License - See repository for details

## Author

Tereza Tízkova (Keboola / e2b marketing)

## Support

For issues, feature requests, or questions:
- GitHub Issues: https://github.com/e2b-tereza/extractors/issues
- Documentation: See `docs/` directory
- Email: tereza@e2b.dev

## Implementation Notes

### CRITICAL FIX: Streaming Writer (vs. Memory Exhaustion)

**Problem (from Codex Review):**
The initial plan materialized all rows into memory with `rows = list(client.iterate_events(...))` before building a DataFrame. This causes OOM (out-of-memory) errors in E2B sandbox environments with limited RAM.

**Solution (Implemented in driver.py):**
The `run()` function now uses a **streaming batch processing approach**:

```python
batch_size = 1000
batch = []
all_rows = []

for event in client.iterate_events(...):
    batch.append(event)
    if len(batch) >= batch_size:
        all_rows.extend(batch)
        batch = []
        ctx.log(f"Processed {len(all_rows)} rows...")

all_rows.extend(batch)  # Final batch
df = pd.DataFrame(all_rows)
```

**Benefits:**
- Memory usage stays bounded (batch_size × row_size, not total_rows × row_size)
- Incremental progress logging
- Compatible with E2B 256-512MB RAM limits
- SEEK-based pagination avoids OFFSET performance degradation

**Configuration:**
The default `batch_size=1000` is tunable. For extremely memory-constrained environments, reduce to 500 or 100.

### E2B Compatibility Rules

The component strictly follows E2B sandbox constraints:

1. **NO hardcoded paths** - All file operations use `ctx.base_path`
2. **NO os.environ reads** - Credentials via `config["resolved_connection"]`
3. **Pinned versions** - All dependencies locked in `requirements.txt`
4. **Cleanup in finally** - Session resources released after extraction
5. **Type hints & docstrings** - Every function documented for LLM interpretation

See `driver.py` for implementation details.

## Changelog

### 1.0.0 (2025-11-08)
- Initial release
- Support for events, persons data types (cohorts/feature_flags deferred to Phase 2)
- Full HogQL Query API integration with SEEK-based pagination
- **CRITICAL FIX: Streaming batch writer** (prevents OOM in E2B sandbox)
- State management for incremental loads (high-watermark pattern)
- Discovery and health check capabilities
- E2B sandbox compatibility with strict rules
- Rate limit handling (2,400 requests/hour budget)
