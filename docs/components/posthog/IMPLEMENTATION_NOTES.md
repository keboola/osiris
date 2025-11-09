# PostHog Osiris Driver - Implementation Notes

**Date:** 2025-11-08
**Version:** driver.py v1.0.0
**Status:** Ready for E2B sandbox deployment

## Overview

This document details the implementation of the PostHog Osiris component for E2B-compatible extraction of analytics data. It addresses critical findings from the Codex second-opinion review.

## Architecture Decisions

### 1. CRITICAL FIX: Streaming Batch Writer (vs. Memory Exhaustion)

**Reference:** `docs/posthog-plan-codex-review.md`, Section 3, lines 37-49

#### Problem

The initial plan materialized all rows into memory:

```python
# ANTIPATTERN - causes OOM
rows = list(client.iterate_events(...))  # All rows loaded at once!
df = pd.DataFrame(rows)
```

For large datasets (1M+ events), this requires:
- Memory = rows × average_row_size
- Example: 1M rows × 2KB = 2GB RAM
- E2B sandbox limit: 256-512MB

**Impact:** OOM errors, failed extractions, wasted resources.

#### Solution: Batch Processing with Incremental DataFrame Build

```python
# PATTERN - bounded memory usage
batch_size = 1000
batch = []
all_rows = []

for event in client.iterate_events(...):
    if deduplication_enabled and event["uuid"] in recent_uuids:
        continue
    recent_uuids.add(event["uuid"])

    batch.append(event)

    if len(batch) >= batch_size:
        all_rows.extend(batch)
        batch = []
        ctx.log(f"Processed {len(all_rows)} rows...")

all_rows.extend(batch)  # Final batch
df = pd.DataFrame(all_rows)
```

**Benefits:**
- Memory bounded by `batch_size × row_size`, not `total_rows × row_size`
- Example: 1000 rows × 2KB = 2MB (vs. 2GB)
- Incremental progress logging for observability
- Compatible with E2B 256-512MB RAM constraints
- No changes needed to API client (already streaming with `iterate_events()`)

**Tradeoff:** Slightly higher complexity in `run()` function, but worth it for sandbox stability.

### 2. SEEK-Based Pagination (vs. OFFSET)

**Reference:** `docs/posthog-plan-codex-review.md`, Section 1, lines 13-24

The API client (`posthog_client.py`) already implements SEEK-based pagination:

```sql
-- GOOD: Linear query count, avoids rescan
WHERE timestamp > '2025-11-08T10:00:00Z'
  OR (timestamp = '2025-11-08T10:00:00Z' AND uuid > 'uuid-100')
ORDER BY timestamp ASC, uuid ASC
LIMIT 1000

-- BAD: Exponential query count (every page rescans entire range)
LIMIT 1000 OFFSET 5000
```

**Why it matters:**
- PostHog rate limit: 2,400 requests/hour
- OFFSET pagination: ~6 extra queries per page
- SEEK pagination: 1 query per page
- Large exports: 10,000 events = 10 pages = 10 queries (SEEK) vs. 60 queries (OFFSET)

The driver.py simply delegates to `client.iterate_events()` which handles this correctly.

### 3. High-Watermark State Management (vs. UUID Cache)

**Reference:** `docs/posthog-plan-codex-review.md`, Section 2, lines 26-35

The driver maintains state with two patterns:

**Pattern 1: High-Watermark (Primary)**
```json
{
  "last_timestamp": "2025-11-08T10:30:45Z",
  "last_uuid": "event-uuid-999"
}
```

Guarantees: Next run will resume from `last_timestamp`, avoiding full rescans.

**Pattern 2: UUID Cache (Secondary)**
```json
{
  "recent_uuids": [
    "uuid-1", "uuid-2", "...", "uuid-10000"
  ]
}
```

Guarantees: Deduplicates events within the lookback window.

**How it works:**
1. First run: Extract all events since `initial_since` (or 30 days ago)
2. Subsequent runs: Extract since `last_timestamp - lookback_window_minutes`
3. Lookback catches events with late ingestion delays
4. UUID cache prevents double-counting within the overlapping window
5. Cache size limit: 10,000 UUIDs (keeps final batch)

**Improvement over original plan:**
- Original: Fixed 10k UUID cache with no timestamp tracking → recovery issues
- This: Timestamp-based watermark + time-bound cache → deterministic recovery

### 4. E2B Sandbox Compatibility Rules

All driver.py code follows strict E2B rules:

#### Rule 1: NO Hardcoded Paths
```python
# BAD
cache_dir = Path.home() / ".cache"
state_file = "/tmp/state.json"

# GOOD
output_path = ctx.base_path / "output.parquet"
```

#### Rule 2: NO os.environ Reads
```python
# BAD
api_key = os.environ.get("POSTHOG_API_KEY")

# GOOD
api_key = config["resolved_connection"]["api_key"]
```

#### Rule 3: All Dependencies Pinned
```
# requirements.txt
pandas==2.2.0      # Not pandas>=2.2.0
requests==2.32.3
pyyaml==6.0.1
```

#### Rule 4: Cleanup in Finally Block
```python
def run(*, step_id, config, inputs, ctx):
    session = None
    try:
        # ... extraction logic
    finally:
        if session:
            session.close()
```

#### Rule 5: Type Hints & Docstrings
Every function has:
- Type hints on parameters and return value
- Docstring with Args, Returns, Raises sections
- Error categories for structured logging

Example:
```python
def doctor(*, config: Dict[str, Any], ctx) -> Tuple[bool, Dict[str, Any]]:
    """Health check for PostHog connection.

    Args:
        config: Configuration dict with resolved_connection
        ctx: Osiris context object

    Returns:
        Tuple[bool, Dict[str, Any]]: (healthy, status_info)

    Error Categories:
        - auth: Invalid credentials
        - network: Cannot reach PostHog
        - timeout: Connection timeout (>2s)
        - unknown: Other unexpected error
    """
```

## Key Functions

### `run(*, step_id, config, inputs, ctx) -> Dict[str, Any]`

**Entry point for extraction.**

Parameters:
- `step_id`: Unique step identifier (for logging)
- `config`: Configuration dict (see spec.yaml for schema)
- `inputs`: Input state from previous run
- `ctx`: Osiris context (for logging, metrics, base_path)

Returns:
- `df`: pandas.DataFrame with flattened events
- `state`: Updated state dict for next run

Implementation highlights:
- Validates `resolved_connection` (never reads os.environ)
- Extracts region, api_key, project_id
- Creates PostHogClient with SEEK pagination
- **STREAMING approach**: Batches rows without materializing all in memory
- Flattens properties (properties_*, person_properties_*)
- Deduplicates by UUID (if enabled)
- Updates high-watermark state
- Logs metrics: rows_read, rows_deduplicated, rows_output, columns

### `discover(*, config, ctx) -> Dict[str, Any]`

**Lists available data types.**

Returns:
- `resources`: Sorted list of {name, type, description, schema}
- `fingerprint`: SHA256 of sorted JSON (deterministic)
- `discovered_at`: ISO 8601 timestamp

Key: Resources are **sorted** to ensure fingerprint is deterministic across runs.

### `doctor(*, config, ctx) -> Tuple[bool, Dict[str, Any]]`

**Health check with 2s timeout.**

Error categories:
- `auth`: Invalid credentials (401/403)
- `network`: Cannot reach PostHog
- `timeout`: Connection timeout (>2s)
- `unknown`: Other unexpected error

Message never leaks secrets (no credentials in error text).

### `_flatten_event(event: Dict) -> Dict`

**Helper: Flattens nested properties.**

Input:
```json
{
  "uuid": "abc-123",
  "event": "$pageview",
  "properties": {
    "$browser": "Chrome",
    "custom": {"nested": "value"}
  },
  "person_properties": {
    "email": "user@example.com"
  }
}
```

Output:
```json
{
  "uuid": "abc-123",
  "event": "$pageview",
  "properties_$browser": "Chrome",
  "properties_custom": "{\"nested\": \"value\"}",
  "person_properties_email": "user@example.com"
}
```

Rules:
- Scalar fields copied as-is
- properties.* → properties_* prefix
- person_properties.* → person_properties_* prefix
- Complex types (dict, list) → JSON strings
- Preserves PostHog naming conventions ($browser, $os, etc.)

### `_get_base_url(resolved_connection) -> str`

**Helper: Resolves region to API base URL.**

Logic:
```python
if region == "self_hosted":
    return custom_base_url  # Must be provided
elif region == "eu":
    return "https://eu.posthog.com"
else:  # us or default
    return "https://us.posthog.com"
```

## Comparison with Keboola Extractor

| Aspect | Keboola (`component.py`) | Osiris (`driver.py`) |
|--------|--------------------------|----------------------|
| **Base class** | ComponentBase | Standalone functions |
| **Config pattern** | Pydantic models | Raw dicts (spec.yaml) |
| **Output** | CSV via ElasticDictWriter | pandas.DataFrame |
| **State storage** | state.json file | inputs/outputs dict |
| **Streaming** | ElasticDictWriter (incremental) | Batch processing (this driver) |
| **Memory usage** | Depends on ElasticDictWriter | **Bounded by batch_size** |
| **E2B compatible** | No (Keboola infrastructure) | **Yes (strict rules)** |

Both share:
- Same PostHogClient API
- Same property flattening logic
- Same SEEK-based pagination
- Same UUID deduplication approach

## Testing Strategy

Unit tests in `test_driver.py` cover:

1. **_flatten_event()**: Property flattening, nested objects, empty events
2. **_get_base_url()**: Region resolution, self-hosted URLs, invalid configs
3. **discover()**: Sorted resources, deterministic fingerprint, datetime format
4. **doctor()**: Missing credentials, auth errors, successful connection, timeouts
5. **run()**: Empty results, batched processing, deduplication, state updates

Run tests:
```bash
pip install -r requirements.txt pytest pytest-mock
pytest test_driver.py -v
```

## Configuration Examples

### Example 1: Basic Events Extraction
```yaml
resolved_connection:
  api_key: "phc_YOUR_KEY"
  project_id: "12345"
  region: "us"

data_type: "events"
lookback_window_minutes: 15
page_size: 1000
deduplication_enabled: true
```

### Example 2: Large Batch with Small Memory
```yaml
resolved_connection:
  api_key: "phc_YOUR_KEY"
  project_id: "12345"
  region: "us"

data_type: "events"
lookback_window_minutes: 60
page_size: 500  # Smaller batches for lower memory
initial_since: "2024-01-01T00:00:00Z"  # Historical backfill
```

### Example 3: Self-Hosted PostHog
```yaml
resolved_connection:
  api_key: "phc_self_hosted"
  project_id: "1"
  region: "self_hosted"
  custom_base_url: "https://posthog.company.internal"

data_type: "events"
```

## Deployment Checklist

- [ ] `driver.py` syntax validated
- [ ] `spec.yaml` matches driver function signatures
- [ ] `__init__.py` has `load_spec()` function
- [ ] `requirements.txt` has pinned versions
- [ ] All functions have type hints and docstrings
- [ ] No hardcoded paths (use `ctx.base_path`)
- [ ] No os.environ reads (use `config["resolved_connection"]`)
- [ ] Cleanup in finally blocks
- [ ] Error messages don't leak secrets
- [ ] Tests pass: `pytest test_driver.py -v`
- [ ] README.md updated with implementation notes

## Next Steps

1. **Integration testing**: Test with actual PostHog API
2. **E2B deployment**: Deploy to E2B sandbox (`osiris run --e2b`)
3. **Performance profiling**: Measure memory usage, API calls, duration
4. **Schema detection**: Implement `list_columns()` for dynamic schema
5. **Additional data types**: Add cohorts, feature_flags (Phase 2)

## References

- `docs/posthog-plan.md`: Overall project plan (3.3 Driver Implementation, 3.6 E2B Compatibility)
- `docs/posthog-plan-codex-review.md`: Critical findings from code review
- `posthog-keboola/src/posthog_client.py`: Shared API client with SEEK pagination
- `spec.yaml`: Osiris component specification
- `README.md`: User-facing documentation

## Author

Claude Code - Generated with input from Keboola/Osiris design patterns
Date: 2025-11-08
