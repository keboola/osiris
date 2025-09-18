# Deep-Dive Runtime Comparison: Local vs E2B Execution

## 1. LOCAL RUN WORKFLOW

### 1.1 Time-Sequenced Execution Flow

```
1. CLI Invocation (osiris/cli/main.py:run_command)
   ├─ Parse arguments: --last-compile flag
   ├─ Load environment variables from .env
   └─ Initialize SessionContext (logs/run_<timestamp>/)

2. Plan Loading (osiris/cli/run.py:_run_with_adapter)
   ├─ Locate last compiled manifest: logs/compile_*/compiled/manifest.yaml
   ├─ Load manifest JSON
   └─ Validate manifest structure

3. Adapter Selection (osiris/core/adapter_factory.py:create_adapter)
   ├─ Check --e2b flag: False
   ├─ Create LocalAdapter instance
   └─ Pass AdapterConfig

4. Prepare Phase (osiris/core/local_adapter.py:prepare)
   ├─ Create PreparedRun object
   ├─ Process manifest steps
   ├─ Build cfg_index from compiled cfg/*.json
   ├─ Define IO layout (logs/, artifacts/, events.jsonl, metrics.jsonl)
   └─ Return PreparedRun with plan and metadata

5. Execute Phase (osiris/core/local_adapter.py:execute)
   ├─ Create execution context
   ├─ Preflight validation
   │   ├─ Verify all cfg/*.json files exist
   │   └─ Log: "preflight_validation_success"
   ├─ Materialize configs
   │   ├─ Copy cfg/*.json → logs/run_*/cfg/
   │   └─ Log: "cfg_materialized" for each file
   ├─ Copy manifest.yaml → logs/run_*/
   ├─ Initialize DriverRegistry
   │   ├─ Register mysql.extractor → MySQLExtractorDriver
   │   ├─ Register filesystem.csv_writer → FilesystemCsvWriterDriver
   │   └─ Register supabase.writer → SupabaseWriterDriver (if available)
   └─ Execute steps sequentially
       For each step:
       ├─ Log: "step_start" event
       ├─ Load step config from cfg/<step-id>.json
       ├─ Resolve connection references (@mysql.db_movies)
       ├─ Get driver from registry
       ├─ Call driver.run(step_id, config, inputs, ctx)
       │   ├─ MySQL extractor: execute query, return {"df": DataFrame}
       │   └─ CSV writer: write DataFrame to artifacts/<step-id>/output.csv
       ├─ Log: "step_complete" event
       ├─ Log metrics: "rows_read", "rows_written"
       └─ Cache outputs for downstream steps

6. Collect Phase (osiris/core/local_adapter.py:collect)
   ├─ Verify artifacts exist
   ├─ Write status.json
   │   └─ {"ok": true, "steps_completed": 10, "exit_code": 0}
   └─ Return CollectedArtifacts

7. Cleanup & Session Close
   ├─ Log: "run_complete" event
   ├─ Log: "session_duration_seconds" metric
   └─ Close SessionContext
```

### 1.2 Component Call Stack

```python
# Main entry point
osiris.py:main()
└─ cli/main.py:cli()
    └─ cli/main.py:run_command()
        └─ cli/run.py:execute_run()
            └─ cli/run.py:_run_with_adapter()
                ├─ core/adapter_factory.py:create_adapter() → LocalAdapter
                ├─ local_adapter.prepare(plan, context)
                ├─ local_adapter.execute(prepared, context)
                │   └─ For each step:
                │       └─ driver.run(step_id, config, inputs, ctx)
                │           ├─ MySQLExtractorDriver.run()
                │           └─ FilesystemCsvWriterDriver.run()
                └─ local_adapter.collect(prepared, context)
```

### 1.3 I/O Flow - Local

```
INPUT FILES:
├─ .env (environment variables)
├─ logs/compile_*/compiled/manifest.yaml (plan)
└─ logs/compile_*/compiled/cfg/*.json (step configs)

OUTPUT FILES (logs/run_<id>/):
├─ events.jsonl (session events)
├─ metrics.jsonl (performance metrics)
├─ osiris.log (main log)
├─ debug.log (debug log)
├─ status.json (execution status)
├─ manifest.yaml (copied plan)
├─ cfg/
│   └─ *.json (materialized configs)
└─ artifacts/
    ├─ extract-actors/
    │   └─ output.csv
    ├─ write-actors-csv/
    │   └─ actors.csv
    └─ ... (10 total)
```

## 2. E2B RUN WORKFLOW

### 2.1 Time-Sequenced Execution Flow

```
1. CLI Invocation (same as local)
   └─ Additional flag: --e2b, --e2b-install-deps

2. Plan Loading (same as local)

3. Adapter Selection (osiris/core/adapter_factory.py:create_adapter)
   ├─ Check --e2b flag: True
   ├─ Create E2BTransparentProxy instance
   └─ Pass E2BConfig with API key

4. Prepare Phase (osiris/remote/e2b_transparent_proxy.py:prepare)
   └─ Same as LocalAdapter (returns PreparedRun)

5. Execute Phase (osiris/remote/e2b_transparent_proxy.py:execute)
   └─ Delegates to _execute_async()
       ├─ Create E2B Sandbox
       │   └─ AsyncSandbox.create(api_key, timeout, envs)
       ├─ Upload ProxyWorker
       │   ├─ Upload proxy_worker.py
       │   ├─ Upload proxy_worker_runner.py
       │   ├─ Upload rpc_protocol.py
       │   ├─ Upload osiris/core/*.py modules
       │   └─ Upload osiris/drivers/*.py
       ├─ Generate commands.jsonl
       │   ├─ PingCommand
       │   ├─ PrepareCommand(manifest, install_deps=True)
       │   ├─ ExecStepCommand for each step (BUT CONFIG IS MISSING!)
       │   └─ CleanupCommand
       ├─ Execute via proxy_worker_runner.py
       │   └─ PYTHONUNBUFFERED=1 python -u proxy_worker_runner.py <session_id>
       └─ Stream stdout/stderr
           ├─ Parse JSON lines
           ├─ Handle worker events
           └─ Show verbose output with [E2B] prefix

6. Inside E2B Sandbox (ProxyWorker execution)
   ├─ Read commands.jsonl
   ├─ Process PrepareCommand
   │   ├─ Create /home/user/session/<session_id>/
   │   ├─ Check/install dependencies (sqlalchemy, pymysql)
   │   ├─ Register drivers explicitly
   │   └─ Send: "session_initialized" event
   ├─ Process ExecStepCommand (FAILS!)
   │   ├─ ERROR: 'query' is required in config
   │   └─ Config not properly passed in command
   └─ Process CleanupCommand (if reached)
       ├─ Write status.json (NOT IMPLEMENTED for failures)
       └─ Touch metrics.jsonl if missing

7. Collect Phase (osiris/remote/e2b_transparent_proxy.py:collect)
   ├─ Check for artifacts (empty due to failures)
   └─ Return CollectedArtifacts (incomplete)
```

### 2.2 Component Call Stack - E2B

```python
# Host side
osiris.py:main()
└─ cli/main.py:run_command()
    └─ cli/run.py:_run_with_adapter()
        ├─ adapter_factory.create_adapter() → E2BTransparentProxy
        ├─ E2BTransparentProxy.prepare()
        ├─ E2BTransparentProxy.execute()
        │   └─ E2BTransparentProxy._execute_async()
        │       ├─ _create_sandbox()
        │       ├─ _upload_worker()
        │       ├─ _generate_commands_file() [BUG: configs not included]
        │       └─ _execute_batch_commands()
        │           └─ sandbox.commands.run("python proxy_worker_runner.py")
        └─ E2BTransparentProxy.collect()

# Sandbox side (E2B)
proxy_worker_runner.py:main()
└─ ProxyWorker.run()
    ├─ handle_prepare(PrepareCommand)
    │   └─ _register_drivers()
    ├─ handle_exec_step(ExecStepCommand) [FAILS: no config]
    │   └─ driver.run() [Never reached]
    └─ handle_cleanup(CleanupCommand)
        └─ _write_final_status() [Not called on failure]
```

### 2.3 Sequence Diagram - E2B

```
Host                    E2BTransparentProxy         E2B Sandbox           ProxyWorker
 |                           |                           |                     |
 |--run --e2b--------------->|                           |                     |
 |                           |--Create Sandbox---------->|                     |
 |                           |                           |<-Sandbox Ready------|
 |                           |--Upload Worker Code------>|                     |
 |                           |--Write commands.jsonl---->|                     |
 |                           |--Run runner.py---------->|--Start ProxyWorker-->|
 |                           |                           |                     |
 |                           |<-stdout: worker_started--|<-Event: started-----|
 |                           |                           |                     |
 |                           |                           |--PrepareCommand---->|
 |                           |                           |<-Install deps-------|
 |                           |                           |<-Register drivers---|
 |                           |<-stdout: ready-----------|<-Response: ready----|
 |                           |                           |                     |
 |                           |                           |--ExecStepCommand--->|
 |                           |                           |  (missing config!)   |
 |                           |<-stdout: error-----------|<-Error: no query----|
 |                           |                           |                     |
 |                           |                           |--CleanupCommand---->|
 |                           |<-stdout: complete--------|<-Response: cleanup--|
 |                           |                           |                     |
 |                           |--Kill Sandbox------------>|                     |
 |<-Results (incomplete)-----|                           |                     |
```

## 3. COMPARISON TABLE

| Aspect | Local Execution | E2B Execution | Issue |
|--------|----------------|---------------|-------|
| **Config Handling** | | | |
| Config Location | `logs/compile_*/compiled/cfg/*.json` | Same source, but not passed to sandbox | ❌ E2B doesn't include config in ExecStepCommand |
| Config Materialization | Copied to `logs/run_*/cfg/` | Not copied | ❌ Missing cfg/ directory |
| Config Loading | Loaded from file for each step | Should be in command, but missing | ❌ BUG in _generate_commands_file() |
| **Event Flow** | | | |
| Event Count | ~90 events | ~13 events | ❌ Missing step-level events |
| Step Events | `step_start`, `step_complete` for each | Only high-level adapter events | ❌ ProxyWorker events not captured |
| Config Events | `cfg_materialized` for each file | None | ❌ No config copying |
| **Metrics** | | | |
| Data Metrics | `rows_read`, `rows_written` per step | Only duration metrics | ❌ Missing data flow metrics |
| Step Metrics | Duration per step | Aggregate duration only | ❌ No granular metrics |
| **File Structure** | | | |
| status.json | Always written | Not written on failure | ❌ _write_final_status() not called |
| manifest.yaml | Copied to session | Not copied | ❌ Missing for debugging |
| cfg/ | All configs copied | Directory doesn't exist | ❌ Not materialized |
| artifacts/ | 10 subdirs with CSVs | Empty | ❌ Execution failed early |
| **Driver Execution** | | | |
| Driver Registry | Loaded from COMPONENT_MAP | Explicitly registered in ProxyWorker | ✅ Working |
| Config Pass | Via file path + loading | Should be in command | ❌ Config not in ExecStepCommand |
| Connection Resolution | Before driver.run() | Not happening | ❌ Connection not resolved |
| **Error Handling** | | | |
| On Step Failure | Continue to next step | Fails but continues | ⚠️ Partial |
| Status on Error | status.json with error details | No status.json | ❌ Not implemented |
| Error Location | osiris.log + debug.log | debug.log only via [Batch Runner] | ⚠️ Less visible |

## 4. ROOT CAUSE ANALYSIS

The main issue is in `E2BTransparentProxy._generate_commands_file()`:

```python
# Current implementation (MISSING CONFIG!)
for step in manifest_data.get("steps", []):
    commands.append({
        "cmd": "exec_step",
        "step_id": step["id"], 
        "driver": step["driver"],
        "config": config,  # This is undefined/empty!
        "inputs": None
    })
```

**Should be:**
```python
for step in manifest_data.get("steps", []):
    step_config = step.get("config", {})
    # Need to resolve connection and include query
    resolved_config = self._resolve_step_config(step_config)
    commands.append({
        "cmd": "exec_step",
        "step_id": step["id"],
        "driver": step["driver"], 
        "config": resolved_config,  # Include actual config with query!
        "inputs": None
    })
```

## 5. REQUIRED FIXES

1. **Fix config passing**: Include actual step config in ExecStepCommand
2. **Capture ProxyWorker events**: Stream step-level events to host events.jsonl
3. **Write status.json always**: Even on failure, with error details
4. **Copy manifest/configs**: For debugging and parity
5. **Add connection resolution**: Resolve @mysql.db_movies references
6. **Improve error handling**: Write partial outputs, preserve state

## 6. FILE STRUCTURE COMPARISON

### Local Run (logs/run_<id>/)
```
logs/run_<id>/
├── events.jsonl         [SessionContext - 90+ events]
├── metrics.jsonl        [SessionContext - data + perf metrics]
├── osiris.log          [SessionContext - main log]
├── debug.log           [SessionContext - debug log]
├── status.json         [LocalAdapter - execution status]
├── manifest.yaml       [LocalAdapter - copied plan]
├── cfg/                [LocalAdapter - materialized configs]
│   ├── extract-actors.json
│   ├── write-actors-csv.json
│   └── ... (10 files)
└── artifacts/          [Drivers - output data]
    ├── extract-actors/
    │   └── output.csv
    ├── write-actors-csv/
    │   └── actors.csv
    └── ... (10 directories)
```

### E2B Run (logs/run_<id>/) - Current State
```
logs/run_<id>/
├── events.jsonl         [SessionContext - 13 events only]
├── metrics.jsonl        [SessionContext - duration only]
├── osiris.log          [SessionContext - main log]
├── debug.log           [SessionContext - includes [Batch Runner] output]
├── status.json         [MISSING - not written on failure]
├── manifest.yaml       [MISSING - not copied]
├── cfg/                [MISSING - directory not created]
└── artifacts/          [EMPTY - execution failed]
```

## 7. EVENT FLOW DETAILS

### Local Event Flow
```
Host Process
    └─ SessionContext.log_event()
        └─ events.jsonl (direct write)
            ├─ run_start
            ├─ preflight_validation_success
            ├─ cfg_materialized (×10)
            ├─ step_start (×10)
            ├─ step_complete (×10)
            └─ run_complete
```

### E2B Event Flow (Current)
```
Host Process                          E2B Sandbox
    ├─ SessionContext.log_event()         └─ ProxyWorker.send_event()
    │   └─ events.jsonl                       └─ stdout (JSON lines)
    │       ├─ run_start                           ├─ dependency_check
    │       ├─ adapter_selected                    ├─ session_initialized
    │       ├─ adapter_execute_start               ├─ step_start (×10)
    │       └─ run_complete                        └─ step_failed (×10)
    │                                                   ↓
    └─ E2BTransparentProxy._handle_batch_output()  [NOT CAPTURED IN events.jsonl]
        └─ Prints to console with [E2B] prefix
```

### E2B Event Flow (Should Be)
```
Host Process                          E2B Sandbox
    ├─ SessionContext.log_event()         └─ ProxyWorker.send_event()
    │   └─ events.jsonl                       └─ stdout (JSON lines)
    │       ├─ run_start                           ↓
    │       ├─ adapter_selected            E2BTransparentProxy._handle_event()
    │       ├─ ALL ProxyWorker events <────────────┘
    │       └─ run_complete                (forward to SessionContext)
```
