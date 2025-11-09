# PostHog Osiris Driver - Quick Start Guide

Get the driver up and running in 5 minutes.

## Prerequisites

- Python 3.9+
- PostHog account with API access
- API key from PostHog project settings
- Project ID (numeric)

## Installation

```bash
# Clone repository
git clone https://github.com/e2b-tereza/extractors.git
cd extractors/posthog-osiris

# Install dependencies
pip install -r requirements.txt

# Verify installation
python3 -c "from driver import discover, doctor, run; print('✓ Ready')"
```

## Get Your PostHog Credentials

1. Go to **PostHog → Settings → Personal API Keys**
2. Copy your API key (format: `phc_xxxxx`)
3. Find your **Project ID** in the URL: `posthog.com/project/{PROJECT_ID}`

Example:
```
API Key:    phc_xXxXxXxXxXxXxXxXx
Project ID: 12345
Region:     us (or eu, or self_hosted)
```

## Create Configuration File

Save as `config.yaml`:

```yaml
# PostHog API credentials
resolved_connection:
  api_key: "phc_YOUR_API_KEY_HERE"
  project_id: "12345"
  region: "us"  # us, eu, or self_hosted
  # custom_base_url: "https://posthog.example.com"  # Only for self_hosted

# Extraction configuration
data_type: "events"                # events or persons
lookback_window_minutes: 15        # 5-60 min
page_size: 1000                    # 100-10000 rows per page
deduplication_enabled: true        # UUID-based dedup
initial_since: null                # First run: null = 30 days ago
# event_types:                     # Optional: filter specific events
#   - "$pageview"
#   - "$click"
#   - "user_signup"
```

## Test Connection

```bash
python3 -c "
from driver import doctor
import yaml
from unittest.mock import Mock

with open('config.yaml') as f:
    config = yaml.safe_load(f)

ctx = Mock()
ctx.log = print

healthy, info = doctor(config=config, ctx=ctx)
if healthy:
    print(f'✓ Healthy: {info[\"message\"]}')
else:
    print(f'✗ Error: {info[\"message\"]} (category: {info[\"category\"]})')
"
```

Expected output:
```
✓ Healthy: Successfully connected to PostHog project 12345
```

## Discover Data Types

```bash
python3 -c "
from driver import discover
from unittest.mock import Mock
import json

ctx = Mock()
ctx.log = print

result = discover(config={}, ctx=ctx)
print('Available resources:')
print(json.dumps(result['resources'], indent=2))
print(f'Fingerprint: {result[\"fingerprint\"]}')
"
```

Expected output:
```
Available resources:
[
  {
    "name": "events",
    "type": "table",
    "description": "PostHog events with properties"
  },
  {
    "name": "persons",
    "type": "table",
    "description": "PostHog persons (user profiles)"
  }
]
Fingerprint: abc123def456...
```

## Run Extraction

```bash
python3 << 'EOF'
import yaml
import pandas as pd
from driver import run
from datetime import datetime
from unittest.mock import Mock

# Load config
with open('config.yaml') as f:
    config = yaml.safe_load(f)

# Mock context
ctx = Mock()
ctx.log = lambda msg, level="info": print(f"[{level.upper()}] {msg}")
ctx.log_metric = lambda name, value: print(f"[METRIC] {name}={value}")
ctx.base_path = "."

# Run extraction
print("Starting extraction...")
result = run(
    step_id="test-run-1",
    config=config,
    inputs={"state": {}},
    ctx=ctx
)

# Check results
df = result["df"]
state = result["state"]

print(f"\nExtraction Complete!")
print(f"Rows: {len(df)}")
print(f"Columns: {len(df.columns)}")
print(f"\nFirst few rows:")
print(df.head())
print(f"\nState for next run:")
print({k: v if k != "recent_uuids" else f"[{len(v)} UUIDs]" for k, v in state.items()})
EOF
```

Expected output:
```
[INFO] Starting extraction...
[INFO] [test-run-1] Starting PostHog extraction: data_type=events, page_size=1000, deduplication=True
[INFO] [test-run-1] Time range: 2025-10-09 10:30:45+00:00 to 2025-11-08 10:30:45+00:00
[INFO] [test-run-1] Processed 1000 rows...
[INFO] [test-run-1] Processed 2000 rows...
[METRIC] rows_read=2547
[METRIC] rows_deduplicated=0
[METRIC] rows_output=2547

Extraction Complete!
Rows: 2547
Columns: 12
        uuid             event  timestamp  distinct_id  ...  properties_$browser
0  abc-123-def  $pageview  2025-11-01T...  user-1      ...  Chrome

State for next run:
{'last_timestamp': '2025-11-08T10:30:45Z', 'last_uuid': 'xyz-999-abc', 'recent_uuids': '[2547 UUIDs]'}
```

## Run Again (Incremental)

The state from the previous run is used for incremental extraction:

```bash
python3 << 'EOF'
import yaml
from driver import run
from unittest.mock import Mock

with open('config.yaml') as f:
    config = yaml.safe_load(f)

# Load state from previous run (in production, this comes from Osiris)
previous_state = {
    "last_timestamp": "2025-11-08T10:30:45Z",
    "last_uuid": "xyz-999-abc",
    "recent_uuids": ["uuid-1", "uuid-2", "..."]  # Last 10k UUIDs
}

ctx = Mock()
ctx.log = lambda msg, level="info": print(f"[{level.upper()}] {msg}")
ctx.log_metric = lambda name, value: print(f"[METRIC] {name}={value}")
ctx.base_path = "."

print("Running incremental extraction...")
result = run(
    step_id="test-run-2",
    config=config,
    inputs={"state": previous_state},
    ctx=ctx
)

print(f"Extracted {len(result['df'])} new rows (with 15-minute lookback)")
print(f"Deduped {result['df'].shape[0]} rows")  # Would be 0 if no new events
EOF
```

## Advanced: Extract Large History

For extracting months of historical data:

```yaml
resolved_connection:
  api_key: "phc_YOUR_API_KEY"
  project_id: "12345"
  region: "us"

data_type: "events"
initial_since: "2024-01-01T00:00:00Z"  # Jan 1, 2024
lookback_window_minutes: 60             # Larger lookback for recovery
page_size: 5000                         # Bigger batches (more API calls, faster)
deduplication_enabled: true
```

**Memory usage:**
- batch_size (internal) = 1000 rows
- page_size = 5000 rows
- Peak memory ≈ max(1000, 5000) × 2KB = 10MB

Safe for E2B sandbox (256MB limit).

## Troubleshooting

### Error: "Missing resolved_connection"

**Cause:** config.yaml doesn't have `resolved_connection` dict

**Fix:** Make sure config.yaml includes:
```yaml
resolved_connection:
  api_key: "phc_..."
  project_id: "12345"
  region: "us"
```

### Error: "Authentication failed (401)"

**Cause:** Invalid API key

**Fix:**
1. Copy API key from PostHog again
2. Verify it starts with `phc_`
3. Check that key hasn't expired

### Error: "Project not found (404)"

**Cause:** Wrong project ID

**Fix:**
1. Go to PostHog → Settings → Copy project ID from URL
2. Verify it's numeric (e.g., `12345`, not `my-project`)

### Error: "Rate limit exceeded"

**Cause:** Too many requests to PostHog API (2,400/hour)

**Fix:**
- Reduce `page_size` (use 500 instead of 1000)
- Increase `lookback_window_minutes` to skip rapid reruns
- Wait 30 minutes and retry

### Error: "Memory exhaustion (OOM)"

**Cause:** Too many rows per batch in E2B

**Fix:**
- Reduce `page_size` to 100-500
- Reduce extraction time range (use smaller `initial_since`)
- Use `event_types` filter to reduce data volume

## Next Steps

1. **Read docs:**
   - `README.md` - Full feature documentation
   - `IMPLEMENTATION_NOTES.md` - Architecture details

2. **Run tests:**
   ```bash
   pip install pytest pytest-mock
   pytest test_driver.py -v
   ```

3. **Deploy to E2B:**
   ```bash
   osiris run posthog --config config.yaml --e2b
   ```

4. **Integrate with orchestration:**
   - Use Osiris CLI for discovery and execution
   - Return state for incremental runs
   - Monitor metrics and errors

## Support

- Issues: GitHub Issues
- Docs: See `docs/` directory
- Examples: See `examples/` directory (if present)
