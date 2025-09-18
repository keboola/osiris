# E2B vs Local Run Parity Implementation Plan

## Changelog (This Revision)

- **File-only execution**: Removed hybrid inline+files approach. All execution driven by file-based configs only.
- **Host-side connection resolution**: Connections resolved on host before copying to sandbox.
- **Symbolic input references**: Inputs reference upstream outputs, no JSON-serialized DataFrames.
- **Per-step driver lifecycle**: Fresh driver instantiation per step, no reuse.
- **Events parity 1:1**: All ProxyWorker events forwarded to host with identical schema.
- **Status.json guarantee**: Always written via finally blocks with host fallback.
- **New sections**: ExecStep Inputs Contract, Driver Lifecycle, Scoping/Non-goals.

## 1. Config Passing Fix

### 1.1 Current Bug Location

**File:** `osiris/remote/e2b_transparent_proxy.py`
**Method:** `_generate_commands_file()` (lines 449-505)

The current implementation incorrectly attempts to pass config inline and uses an undefined variable.

### 1.2 File-Only Contract

**Commands must NOT contain inline configs.** Each exec_step command must follow this schema:

```json
{
  "cmd": "exec_step",
  "step_id": "extract-actors",
  "driver": "mysql.extractor",
  "cfg_path": "cfg/extract-actors.json",
  "inputs": {
    "df": {
      "from_step": "previous-step-id",
      "key": "df"
    }
  }
}
```

The `_generate_commands_file()` method must:
1. NOT embed configs in commands
2. Only set `cfg_path` pointing to the file location
3. Include symbolic `inputs` references (see Section 7)

### 1.3 Host-Side Connection Resolution

Before copying cfg files to sandbox, the host must resolve all connection references:

```python
# In _generate_commands_file() or new _prepare_configs() method:

1. Load ConnectionResolver (same as LocalAdapter)
2. For each step config:
   a. Check for "@family.alias" connection references
   b. Resolve using ConnectionResolver.resolve(family, alias)
   c. Replace connection ref with resolved_connection dict
   d. Write resolved config to cfg/<step-id>.json
3. Copy resolved configs to sandbox
```

The sandbox receives configs that are **ready-to-run** with no further resolution needed.

### 1.4 Materializing Manifest and Config Files

These files are the **execution source of truth**, not just for debugging:

```python
async def _materialize_execution_files(self, prepared: PreparedRun, context: ExecutionContext):
    """Materialize manifest and configs as the execution source of truth."""
    
    # 1. Create cfg directory
    cfg_dir = context.logs_dir / "cfg"
    cfg_dir.mkdir(exist_ok=True)
    
    # 2. Resolve and write each config
    from osiris.core.connection_resolver import ConnectionResolver
    resolver = ConnectionResolver()
    
    for step in prepared.plan.get("steps", []):
        step_id = step.get("id")
        step_config = step.get("config", {})
        
        # Resolve connection if present
        if "connection" in step_config and step_config["connection"].startswith("@"):
            conn_ref = step_config["connection"]
            family, alias = conn_ref[1:].split(".", 1) if "." in conn_ref else (conn_ref[1:], None)
            resolved = resolver.resolve(family, alias)
            if resolved:
                step_config["resolved_connection"] = resolved
                del step_config["connection"]  # Remove the reference
        
        # Write resolved config
        cfg_file = cfg_dir / f"{step_id}.json"
        with open(cfg_file, 'w') as f:
            json.dump(step_config, f, indent=2)
        
        # Calculate SHA256 for verification
        sha256 = hashlib.sha256(json.dumps(step_config, sort_keys=True).encode()).hexdigest()
        
        # Log materialization event
        self.log_event("cfg_materialized", 
                      path=f"cfg/{step_id}.json",
                      size=cfg_file.stat().st_size,
                      sha256=sha256)
    
    # 3. Write manifest.yaml
    manifest_path = context.logs_dir / "manifest.yaml"
    with open(manifest_path, 'w') as f:
        yaml.dump(prepared.plan, f, default_flow_style=False)
    
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    self.log_event("manifest_materialized",
                  path="manifest.yaml",
                  size=manifest_path.stat().st_size,
                  sha256=manifest_sha256)
    
    # 4. Upload to sandbox (resolved configs only)
    await self._upload_configs_to_sandbox(cfg_dir, manifest_path)
```

## 2. Event Parity Solution

### 2.1 ProxyWorker Standardized Events

ProxyWorker must emit these events matching local names exactly:
- `cfg_materialized` - when config files are verified
- `step_start` - before driver execution
- `step_complete` - after successful execution
- `step_failed` - on driver error
- `rows_read` - data extraction metric
- `rows_written` - data write metric
- `step_duration_ms` - execution time metric

### 2.2 Event Forwarding Implementation

All ProxyWorker events must be forwarded to host events.jsonl with **identical schema** to local:

```python
def _forward_event_to_host(self, event_msg: EventMessage):
    """Forward ProxyWorker event with 1:1 parity to local schema."""
    
    # Normalize timestamp to ISO format (same as local)
    if hasattr(event_msg, 'timestamp'):
        ts = datetime.fromtimestamp(event_msg.timestamp, tz=timezone.utc).isoformat()
    else:
        ts = datetime.now(timezone.utc).isoformat()
    
    # Build event matching LocalAdapter schema exactly
    event_dict = {
        "ts": ts,
        "session": self.session_id,
        "event": event_msg.name,
        **event_msg.data  # All event data preserved
    }
    
    # Write to host events.jsonl
    events_file = self.context.logs_dir / "events.jsonl"
    with open(events_file, 'a') as f:
        f.write(json.dumps(event_dict) + '\n')
```

### 2.3 Event Mapping Table

| ProxyWorker Event | Host Event Name | Required Fields |
|-------------------|-----------------|-----------------|
| `step_start` | `step_start` | `step_id`, `driver` |
| `step_complete` | `step_complete` | `step_id`, `driver`, `output_dir`, `duration` |
| `step_failed` | `step_failed` | `step_id`, `driver`, `error`, `traceback` |
| `cfg_materialized` | `cfg_materialized` | `path`, `size`, `sha256` |
| `rows_read` | Metric: `rows_read` | `value` |
| `rows_written` | Metric: `rows_written` | `value` |
| `step_duration_ms` | Metric: `step_duration_ms` | `value` |

## 3. Critical Files Materialization

### 3.1 Must-Exist Contract

After ANY E2B run (success or failure), these files MUST exist in `logs/run_<id>/`:
- `manifest.yaml` - Execution plan
- `cfg/` - Directory with all step configs
- `events.jsonl` - All events (host + forwarded worker events)
- `metrics.jsonl` - Performance and data flow metrics
- `status.json` - Execution status
- `osiris.log` - Main log
- `debug.log` - Debug log
- `artifacts/` - Output data (may be empty on failure)

### 3.2 Worker Responsibility (ProxyWorker)

```python
def handle_cleanup(self, cmd: CleanupCommand) -> CleanupResponse:
    """Cleanup with guaranteed file writes."""
    try:
        # ... existing cleanup ...
    finally:
        # ALWAYS write status.json
        self._write_status_json()
        
        # ALWAYS ensure metrics.jsonl exists
        if not self.metrics_file.exists():
            # Touch with initial metric
            with open(self.metrics_file, 'w') as f:
                f.write(json.dumps({
                    "name": "session_initialized",
                    "value": 1,
                    "timestamp": time.time()
                }) + '\n')
```

### 3.3 Host Safety Net (E2BTransparentProxy)

```python
async def _execute_async(self, prepared: PreparedRun, context: ExecutionContext):
    try:
        # ... execution ...
    finally:
        # Try to fetch status.json from sandbox
        status_fetched = await self._fetch_status_from_sandbox()
        
        if not status_fetched:
            # CONTRACT VIOLATION: Worker didn't write status.json
            self.log_event("status_contract_violation",
                          reason="Worker failed to write status.json")
            
            # Create fallback status with last stderr
            last_stderr = self._get_last_stderr_lines(20)
            self._write_fallback_status(context, last_stderr)
```

## 4. Error Propagation

### 4.1 Enhanced Error Fields

ExecStepResponse must include:
- `error` - Error message
- `error_type` - Exception class name
- `traceback` - Full stack trace

### 4.2 Error Event Mirroring

All error details must be mirrored to host events.jsonl:

```python
# In ProxyWorker.handle_exec_step() on error:
self.send_event("step_failed",
               step_id=step_id,
               driver=driver_name,
               error=str(e),
               error_type=type(e).__name__,
               traceback=traceback.format_exc())

# In E2BTransparentProxy._forward_event_to_host():
# This event gets forwarded to host events.jsonl with all fields preserved
```

## 5. Parity Testing Checklist

### 5.1 File Structure Parity

Both local and E2B runs must produce identical structure:
```
logs/run_<id>/
├── events.jsonl       ✓ Must exist
├── metrics.jsonl      ✓ Must exist
├── status.json        ✓ Must exist
├── manifest.yaml      ✓ Must exist
├── osiris.log         ✓ Must exist
├── debug.log          ✓ Must exist
├── cfg/               ✓ Must exist with all configs
│   └── *.json
└── artifacts/         ✓ Must exist (may be empty)
    └── <step-id>/
```

**Guard tests for absence of legacy artifacts:**
- [ ] NO `remote/` directory
- [ ] NO `payload.tgz` file
- [ ] NO nested `run_<id>/` directory

### 5.2 Config Parity

- [ ] SHA256 of every `cfg/*.json` matches between local and E2B
- [ ] SHA256 of `manifest.yaml` matches between local and E2B
- [ ] All connection references resolved identically

### 5.3 Events Parity

- [ ] Multiset of event names identical (ignore timestamps)
- [ ] Same count for each event type:
  - `step_start`: 10 (for sample pipeline)
  - `step_complete` or `step_failed`: 10
  - `cfg_materialized`: 10
- [ ] All ProxyWorker events present in host events.jsonl

### 5.4 Metrics Parity

- [ ] Same counts for `rows_read` and `rows_written`
- [ ] Same totals for data flow
- [ ] Duration metrics within ±20% tolerance

### 5.5 Artifacts Parity

- [ ] Same CSV file set in artifacts/
- [ ] Same row counts in each CSV (shape checksum)
- [ ] Column names and types match

## 6. ExecStep Inputs Contract

### 6.1 Symbolic Reference Schema

Inputs must use symbolic references only, no serialized data:

```json
{
  "inputs": {
    "df": {
      "from_step": "extract-actors",
      "key": "df"
    },
    "config": {
      "from_step": "transform-data",
      "key": "metadata"
    }
  }
}
```

### 6.2 Worker Resolution

ProxyWorker maintains step outputs in memory:

```python
# In ProxyWorker:
self.step_outputs = {}  # Dict[step_id, Dict[key, value]]

# After successful step execution:
self.step_outputs[step_id] = result  # e.g., {"df": DataFrame}

# When processing inputs for next step:
def _resolve_inputs(self, inputs_spec):
    resolved = {}
    for input_key, ref in inputs_spec.items():
        from_step = ref["from_step"]
        from_key = ref["key"]
        if from_step in self.step_outputs:
            if from_key in self.step_outputs[from_step]:
                resolved[input_key] = self.step_outputs[from_step][from_key]
    return resolved
```

### 6.3 Memory Management Note

Large outputs may require future "spill to artifacts" strategy (out of scope for current parity work).

## 7. Driver Lifecycle

### 7.1 Per-Step Instantiation

**Drivers must be instantiated fresh for each step, with no cross-step reuse.**

```python
# In ProxyWorker.handle_exec_step():
# DO NOT cache driver instances
driver_class = self.driver_registry.get(driver_name)
driver = driver_class()  # Fresh instance every time
result = driver.run(step_id, config, inputs, ctx)
# Driver goes out of scope after step
```

This mirrors LocalAdapter behavior exactly and prevents state leakage between steps.

### 7.2 Driver State Isolation

- No driver instance variables persist between steps
- Connection pools managed at module level if needed
- Each step starts with clean driver state

## 8. Scoping / Non-Goals

### 8.1 In Scope

- File-based config execution
- Host-side connection resolution
- 1:1 event parity
- Symbolic input references
- Per-step driver lifecycle
- Critical file guarantees

### 8.2 Out of Scope

- ❌ Inline config passing
- ❌ Mailbox communication
- ❌ Stdin/stdout RPC
- ❌ Agentic resolution in sandbox
- ❌ DataFrame serialization to JSON
- ❌ Driver instance reuse
- ❌ Legacy pack&run artifacts

## Implementation Sequence

### Phase 1: Config and Inputs (Priority 1)
1. Fix `_generate_commands_file()` to use file-only contract
2. Implement host-side connection resolution
3. Add symbolic inputs resolution in ProxyWorker
4. Test queries execute successfully

### Phase 2: Event Forwarding (Priority 2)
1. Standardize ProxyWorker event names
2. Implement `_forward_event_to_host()` with schema parity
3. Verify all events in host events.jsonl
4. Add event count validation

### Phase 3: File Guarantees (Priority 3)
1. Add `_materialize_execution_files()` with SHA256
2. Implement finally blocks in Worker and Host
3. Add fallback status.json creation
4. Test files exist even on failure

### Phase 4: Driver Lifecycle (Priority 4)
1. Remove any driver caching in ProxyWorker
2. Ensure fresh instantiation per step
3. Verify no state leakage between steps

### Phase 5: Validation (Priority 5)
1. Run full parity checklist
2. Compare SHA256 of all configs
3. Validate event multisets
4. Document any remaining divergences
