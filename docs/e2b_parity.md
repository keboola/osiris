# E2B Execution Parity Documentation

## Overview

The E2B (E2Build) runtime provides cloud-based execution of Osiris pipelines with complete parity to local execution. This document details the execution flow, artifacts management, events, and metrics.

## Execution Flow

### 1. Preparation Phase
- Host creates E2B sandbox with CPU/memory configuration
- Session directory mounted at `/home/user/session/{session_id}`
- ProxyWorker script uploaded to sandbox
- Pipeline configs materialized to `cfg/*.json` with resolved connections
- Commands batch file generated with all execution steps

### 2. Execution Phase
- ProxyWorker processes commands sequentially via JSON-RPC protocol
- Dependencies auto-installed if `--e2b-install-deps` flag is set
- Drivers registered dynamically (mysql.extractor, filesystem.csv_writer, supabase.writer)
- Each step:
  - Loads config from `cfg/{step_id}.json`
  - Resolves symbolic inputs from in-memory cache
  - Creates artifacts directory at `artifacts/{step_id}/`
  - Executes driver with context supporting metrics
  - Caches outputs (DataFrames) for downstream steps
  - Emits events and metrics in real-time

### 3. Collection Phase
- Artifacts downloaded from sandbox to host
- Status.json written with execution summary
- Sandbox terminated and resources cleaned up

## Artifacts Structure

Both local and E2B runs produce identical artifacts:

```
logs/run_{session_id}/
├── artifacts/
│   ├── extract-actors/
│   │   └── cleaned_config.json    # Config with masked secrets
│   ├── write-actors-supabase/
│   │   └── cleaned_config.json
│   └── ... (one per step)
├── cfg/                            # Materialized configs
├── commands.jsonl                  # E2B batch commands (E2B only)
├── events.jsonl                    # Structured event stream
├── metrics.jsonl                   # Performance metrics
├── manifest.yaml                   # Compiled pipeline
├── osiris.log                      # Application logs
└── status.json                     # Execution summary
```

## Events

### Core Pipeline Events
- `run_start` - Pipeline execution begins
- `step_start` - Step execution begins (includes step_id, driver)
- `step_complete` - Step finished (includes rows_processed, duration_ms)
- `step_failed` - Step encountered error
- `cleanup_start` / `cleanup_complete` - Final cleanup phase

### Configuration Events
- `cfg_materialized` - Config file written (includes path, sha256)
- `cfg_opened` - Config file loaded for execution
- `config_meta_stripped` - Meta keys removed before driver execution
- `manifest_materialized` - Manifest file written

### Artifact Events
- `artifacts_dir_created` - Step artifacts directory created
- `artifact_created` - Artifact file written (includes path, type)

### Connection Events
- `connection_resolve_start` - Connection resolution begins
- `connection_resolve_complete` - Connection resolved (includes family, alias, ok)

### Input/Output Events
- `inputs_resolved` - Step inputs resolved from upstream outputs
- `input_resolution_failed` - Failed to resolve symbolic reference

### Driver Events
- `driver_registered` - Driver successfully registered (includes status)
- `driver_registration_failed` - Driver registration failed
- `drivers_registered` - All drivers registered (includes list)

### Dependency Events (E2B only)
- `dependency_check` - Lists missing/present packages
- `dependency_installed` - Packages installed successfully

### Supabase-specific Events
- `table.exists_check` - Checking if table exists
- `table.ddl_planned` - DDL generated for missing table
- `table.ddl_executed` - Table created successfully
- `write.progress` - Progress update for large writes
- `write.complete` - Write operation finished

## Metrics

### Step Metrics
- `steps_total` - Total number of steps in pipeline
- `steps_completed` - Number of completed steps
- `step_duration_ms` - Time taken for each step (tagged with step_id)

### Data Metrics
- `rows_processed` - Rows handled by step (tagged with step_id)
- `rows_read` - Rows read by extractors (tagged with step_id)
- `rows_written` - Rows written by writers (tagged with step_id)

### Execution Metrics
- `execution_duration` - Total pipeline execution time (seconds)
- `adapter_execution_duration` - Adapter-specific execution time
- `adapter_exit_code` - Process exit code (0 for success)
- `session_duration_seconds` - Total session duration

### E2B-specific Metrics
- `e2b_overhead_ms` - Time to create and setup sandbox
- `artifacts_copy_ms` - Time to download artifacts from sandbox
- `artifacts_bytes_total` - Total size of downloaded artifacts
- `artifacts_files_total` - Number of artifact files

## Parity Guarantees

### Functional Parity
- Same pipeline steps execute in same order
- Identical data transformations applied
- Same output files generated
- Consistent error handling and retry logic

### Observability Parity
- All events present in both local and E2B runs
- Metrics match exactly (except E2B-specific overhead)
- Artifacts structure identical
- SHA-256 checksums for config integrity

### Security Parity
- Credentials resolved on host, never sent to sandbox
- Passwords masked as `***MASKED***` in artifacts
- Ephemeral sandboxes destroyed after execution
- No data persistence between runs

## Configuration

### E2B Flags
- `--e2b` - Enable E2B execution
- `--e2b-install-deps` - Auto-install missing Python packages
- `--verbose` - Show real-time progress

### Environment Variables
- `E2B_API_KEY` - E2B authentication key
- `OSIRIS_E2B_INSTALL_DEPS=1` - Enable auto-install by default

## Error Handling

### Retry Logic
- Supabase operations: 3 attempts with exponential backoff and jitter
- Initial delay: 1 second, max delay: 10 seconds
- Network operations wrapped in retry helper

### Failure Modes
1. **Missing Dependencies**: Clear error with actionable message if auto-install disabled
2. **Bad Credentials**: Masked error messages, cleanup still runs
3. **Network Issues**: Automatic retry with backoff
4. **Sandbox Timeout**: 600-second limit with graceful cleanup

## Performance Characteristics

### Expected Overheads
- Sandbox creation: 5-10 seconds (one-time)
- Dependency installation: 5-15 seconds (when needed)
- Artifact download: <1 second for typical pipelines
- Per-step overhead: <100ms vs local execution

### Optimization Tips
- Use `--e2b-install-deps` to avoid manual dependency management
- Batch multiple pipelines to amortize sandbox creation cost
- Keep artifacts small (<100MB) for fast downloads
