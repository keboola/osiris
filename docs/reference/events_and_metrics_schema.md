# Events and Metrics Schema Documentation

## Event Schema

All events follow a common structure defined in `schemas/events.schema.json`:

### Base Fields (Required)
- `ts` (string, ISO 8601): Timestamp with timezone
- `session` (string): Session identifier matching pattern `run_[0-9]+`
- `event` (string): Event type from enumerated list

### Event Types and Additional Fields

#### Pipeline Lifecycle Events
- `run_start`: Pipeline execution begins
  - Additional: `session_id`, `pipeline`, `file_type`
- `run_complete` / `run_end`: Pipeline execution ends
  - Additional: `exit_code`, `duration`

#### Step Execution Events
- `step_start`: Step begins execution
  - Required: `step_id` (string), `driver` (string)
- `step_complete`: Step finished successfully
  - Required: `step_id` (string), `rows_processed` (number ≥ 0), `duration_ms` (number ≥ 0)
- `step_failed`: Step encountered error
  - Required: `step_id`, `error`, `error_type`, `traceback`

#### Configuration Events
- `cfg_materialized`: Config file written to disk
  - Required: `path` (string), `sha256` (64-char hex), `size_bytes` (number ≥ 0)
- `cfg_opened`: Config loaded for step execution
  - Required: `path`, `sha256`, `keys` (array of strings)
- `config_meta_stripped`: Meta keys removed from config
  - Required: `step_id`, `keys_removed` (array)

#### Artifact Events
- `artifacts_dir_created`: Step artifacts directory created
  - Required: `step_id`, `relative_path`
- `artifact_created`: Artifact file written
  - Required: `step_id`, `artifact_type`, `path`

#### Connection Events
- `connection_resolve_start`: Beginning connection resolution
  - Required: `step_id`, `family`, `alias`
- `connection_resolve_complete`: Connection resolved
  - Required: `step_id`, `family`, `alias`, `ok` (boolean)

#### Driver Events
- `driver_registered`: Driver successfully registered
  - Required: `driver` (string), `status` (enum: "success", "success_after_install", "failed")
- `driver_registration_failed`: Registration failed
  - Required: `driver`, `error`
- `drivers_registered`: All drivers registered
  - Required: `drivers` (array of strings)

#### Dependency Events (E2B only)
- `dependency_check`: Dependency status check
  - Required: `missing` (array), `present` (array)
- `dependency_installed`: Packages installed
  - Required: `now_present` (array), `still_missing` (array)

## Metric Schema

All metrics follow structure defined in `schemas/metrics.schema.json`:

### Base Fields (Required)
- `ts` (string, ISO 8601): Timestamp with timezone
- `session` (string): Session identifier
- `metric` (string): Metric name from enumerated list
- `value` (number): Metric value

### Optional Fields
- `unit` (string): Unit of measurement (seconds, ms, bytes, files, rows, code)
- `tags` (object): Additional context, typically `{"step": "step_id"}`

### Metric Types

#### Step Metrics
- `steps_total`: Total pipeline steps (emitted once at start)
- `steps_completed`: Running count of completed steps
- `step_duration_ms`: Step execution time
  - Tags: `{"step": "step_id"}`

#### Data Flow Metrics
- `rows_processed`: Generic row count for any operation
  - Tags: `{"step": "step_id"}`
- `rows_read`: Rows read by extractors
  - Tags: `{"step": "step_id"}`
- `rows_written`: Rows written by writers
  - Tags: `{"step": "step_id"}`
  - Unit: "rows"

#### Execution Timing
- `execution_duration`: Total pipeline execution time
  - Unit: "seconds"
- `adapter_execution_duration`: Adapter-specific time
  - Unit: "seconds"
- `session_duration_seconds`: Complete session duration
- `e2b_overhead_ms`: Sandbox creation overhead (E2B only)
  - Unit: "ms"
- `artifacts_copy_ms`: Artifact download time (E2B only)
  - Unit: "ms"

#### Artifact Metrics
- `artifacts_bytes_total`: Total size of artifacts
  - Unit: "bytes"
- `artifacts_files_total`: Number of artifact files
  - Unit: "files"

#### Exit Status
- `adapter_exit_code`: Process exit code (0 = success)
  - Unit: "code"

## Validation

### JSON Schema Validation
Both event and metric streams can be validated using JSON Schema validators:

```python
import json
import jsonschema

# Load schemas
with open('schemas/events.schema.json') as f:
    event_schema = json.load(f)

with open('schemas/metrics.schema.json') as f:
    metric_schema = json.load(f)

# Validate events
with open('logs/run_XXX/events.jsonl') as f:
    for line in f:
        event = json.loads(line)
        jsonschema.validate(event, event_schema)

# Validate metrics
with open('logs/run_XXX/metrics.jsonl') as f:
    for line in f:
        metric = json.loads(line)
        jsonschema.validate(metric, metric_schema)
```

### Expected Counts for 10-Step Pipeline
- `step_start`: 10
- `step_complete`: 10
- `artifact_created`: 10
- `cfg_materialized`: 10
- `cfg_opened`: 10
- `artifacts_dir_created`: 10
- `config_meta_stripped`: 10
- `connection_resolve_start`: 10 (for connection-based steps)
- `connection_resolve_complete`: 10

### Parity Validation
Local and E2B runs should have:
- Same event types and counts (±5% for timing-sensitive events)
- Identical metric names and similar values
- Matching artifact structure
- Consistent error reporting

## Row Totals Normalization

### Single Source of Truth

For determining total rows processed in a pipeline run:

1. **Primary source**: `cleanup_complete.total_rows` event field
   - When present, this is the authoritative total for "Data Volume / Rows Processed"
   - UI tools and reports should always prefer this value

2. **Fallback logic** (for legacy sessions without `cleanup_complete.total_rows`):
   - Sum `rows_written` metrics from writer steps
   - If no writers exist, sum `rows_read` metrics from extractor steps

### Avoiding Double-Counting

**Important**: Don't sum both events and metrics for totals. The correct approach:

- Use `cleanup_complete.total_rows` when available (single source of truth)
- Only use metric summation as fallback for older sessions
- Never add `rows_read` and `rows_written` together (they represent the same data at different stages)

### Metric Clarification

- **`rows_read`**: Emitted by extractor components when reading from sources
  - Tagged with `step_id` for the specific extraction step
  - Represents input data volume

- **`rows_written`**: Emitted by writer components when writing to destinations
  - Tagged with `step_id` for the specific writer step
  - Represents output data volume

### Example Events

Extractor reading 20 rows:
```json
{"event": "step_complete", "step_id": "extract_customers", "rows_processed": 20}
{"metric": "rows_read", "value": 20, "tags": {"step": "extract_customers"}}
```

Writer writing 20 rows:
```json
{"event": "step_complete", "step_id": "write_customers", "rows_processed": 20}
{"metric": "rows_written", "value": 20, "tags": {"step": "write_customers"}}
```

Final cleanup with authoritative total:
```json
{"event": "cleanup_complete", "total_rows": 84, "duration_ms": 1234}
```

## Local vs E2B Execution Parity

Both local and E2B execution produce compatible events and metrics:

- **Same event types**: Both emit identical event types and structures
- **Same metrics**: Data flow metrics (`rows_read`, `rows_written`) are consistent
- **Adapter selection**: The `adapter_selected` event indicates execution mode ("local" or "e2b")
- **E2B additions**: E2B may emit additional bootstrap events (`worker_started`, RPC communication)

### E2B-Specific UI Elements

When displaying E2B execution results:

- **E2B Badge**: Orange "E2B" indicator in report headers
- **Bootstrap Time**: Time to provision and initialize sandbox (typically 800-1200ms)
  - Calculated from `adapter_execute_start` to first worker event
  - Displayed separately from pipeline execution time

## Best Practices

1. **Always emit paired events**: start/complete, start/failed
2. **Include step_id in all step-related events**
3. **Use consistent units for metrics**
4. **Mask sensitive data before emission**
5. **Emit metrics immediately after measurement**
6. **Use tags for additional context rather than new metric names**
7. **Prefer cleanup_complete.total_rows for row totals**
