# Metrics & Events Contract

**Purpose**: Machine-verifiable telemetry requirements.

**Scope**: All driver implementations

---

## Required Metrics by Component Type

| Component Type | Metric Name | Unit | Tags | When |
|----------------|-------------|------|------|------|
| **Extractor** | `rows_read` | `rows` | `{"step": step_id}` | After extraction |
| **Writer** | `rows_written` | `rows` | `{"step": step_id}` | After write |
| **Processor** | `rows_processed` | `rows` | `{"step": step_id}` | After transform |

---

## MUST Rules: Metrics

### MET-001: Required Metric Emitted

**Statement**: Component MUST emit its required metric.

**Implementation**:
```python
if ctx and hasattr(ctx, "log_metric"):
    ctx.log_metric("rows_read", len(df), unit="rows", tags={"step": step_id})
```

**Validation**:
```bash
# Check metrics.jsonl contains required metric
cat logs/run_XXX/metrics.jsonl | jq 'select(.metric == "rows_read")'
```

**Failure**: `❌ Missing required metric 'rows_read' for extractor`

---

### MET-002: Unit Specified

**Statement**: All metrics MUST specify unit.

**Valid Units**: `rows`, `ms`, `bytes`, `seconds`, `files`, `code`, `calls`

**Validation**:
```python
assert metric["unit"] in ["rows", "ms", "bytes", "seconds", "files", "code", "calls"]
```

**Failure**: `❌ Metric 'rows_read' missing unit. Expected: 'rows'`

---

### MET-003: Tags Include Step ID

**Statement**: Step metrics MUST include `step` tag.

**Example**:
```json
{
  "metric": "rows_read",
  "value": 1000,
  "unit": "rows",
  "tags": {"step": "extract_users"}
}
```

**Failure**: `❌ Metric missing step tag`

---

## Auto-Emitted Events (Runner)

These events are emitted by the runner, NOT the driver:

| Event | When | Required Fields |
|-------|------|-----------------|
| `step_start` | Before `driver.run()` | `step_id`, `driver` |
| `step_complete` | After success | `step_id`, `rows_processed`, `duration_ms` |
| `step_failed` | On exception | `step_id`, `error`, `error_type` |
| `connection_resolve_complete` | After resolution | `step_id`, `family`, `alias`, `ok` |

**Drivers do NOT emit these.**

---

## CLI Output Format

### Metrics Query

```bash
osiris logs metrics --session run_XXX --metric rows_read --json
```

**Output**:
```json
[
  {
    "ts": "2025-09-30T12:00:00.000Z",
    "metric": "rows_read",
    "value": 1000,
    "unit": "rows",
    "tags": {"step": "extract_users"}
  }
]
```

---

### Events Query

```bash
osiris logs events --session run_XXX --event step_complete --json
```

**Output**:
```json
[
  {
    "ts": "2025-09-30T12:00:01.500Z",
    "event": "step_complete",
    "step_id": "extract_users",
    "rows_processed": 1000,
    "duration_ms": 1500
  }
]
```

---

## Schemas

- **Events**: `../schemas/events.schema.json`
- **Metrics**: `../schemas/metrics.schema.json`

---

## See Also

- **Overview**: `../llms/overview.md`
- **Driver Contract**: `../llms/drivers.md`
- **Full Checklist**: `COMPONENT_AI_CHECKLIST.md`
