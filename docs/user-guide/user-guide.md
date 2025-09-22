# Osiris User Guide

This guide covers the essential features of Osiris v0.2.0 for running data pipelines.

## 1. Connections & Secrets

Osiris separates connection configuration from secrets for security and flexibility.

### Connection Configuration

Define your database connections in `osiris_connections.yaml`:

```yaml
# osiris_connections.yaml
connections:
  mysql:
    default:
      host: ${MYSQL_HOST:-localhost}
      port: ${MYSQL_PORT:-3306}
      database: ${MYSQL_DATABASE}
      username: ${MYSQL_USER:-root}
      password: ${MYSQL_PASSWORD}

  supabase:
    main:
      url: ${SUPABASE_URL}
      key: ${SUPABASE_SERVICE_ROLE_KEY}
```

### Using Connection Aliases

Reference connections in your pipelines using the `@family.alias` format:

```yaml
steps:
  - id: "extract_customers"
    component: "mysql.extractor"
    mode: "read"
    config:
      connection: "@mysql.default"  # References mysql.default connection
      query: "SELECT * FROM customers"
```

### Environment Variables

Store secrets in a `.env` file that's never committed to version control:

```bash
# .env
MYSQL_PASSWORD=your-secret-password
MYSQL_DATABASE=mydb
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
```

Environment variables are resolved at runtime using `${VAR_NAME}` syntax. You can provide defaults with `${VAR_NAME:-default_value}`.

## 2. Running Pipelines

Osiris provides a two-step process: compile your OML pipeline into a manifest, then run the manifest.

### Compilation

Convert an OML pipeline to an executable manifest:

```bash
# Compile OML to manifest
osiris compile pipeline.oml

# Output is saved to logs/<session_id>/compile_<timestamp>/
# The manifest.yaml contains resolved configurations
```

### Local Execution

Run a compiled pipeline on your local machine:

```bash
# Run the last compiled manifest
osiris run --last-compile

# Or run a specific manifest
osiris run logs/run_123/compile_456/manifest.yaml
```

Local execution uses your machine's resources and installed dependencies. Data flows through memory between pipeline steps.

### E2B Cloud Execution

Run pipelines in isolated cloud sandboxes using E2B:

```bash
# Run in E2B sandbox
osiris run --last-compile --e2b

# With custom resources
osiris run --last-compile --e2b --e2b-cpu 4 --e2b-mem 8

# Auto-install missing Python packages
osiris run --last-compile --e2b --e2b-install-deps
```

E2B execution provides complete isolation and consistent environments. The transparent proxy architecture ensures identical behavior between local and E2B runs, with less than 1% performance overhead. E2B sandboxes are automatically provisioned with your pipeline code and cleaned up after execution.

### Example Workflow

Here's a typical development workflow:

```bash
# 1. Write or generate your pipeline
osiris chat  # Interactive pipeline creation

# 2. Compile the OML
osiris compile output/pipeline.oml

# 3. Test locally with small data
osiris run --last-compile

# 4. Run at scale in E2B
osiris run --last-compile --e2b --e2b-timeout 3600
```

## 3. Observability

Every pipeline execution generates comprehensive logs for debugging and analysis.

### Session Structure

Each run creates a session directory with structured logs:

```
logs/
└── run_<timestamp>/
    ├── events.jsonl       # Structured execution events
    ├── metrics.jsonl      # Performance metrics
    ├── osiris.log         # Traditional text log
    └── artifacts/         # Output files per step
        └── <step_id>/
            └── output.csv
```

### Events & Metrics

**events.jsonl** contains structured events tracking execution flow:
- `run_start` / `run_end` - Pipeline boundaries
- `step_start` / `step_complete` - Step execution with row counts
- `connection_resolve_complete` - Connection resolution details
- `error` - Error events with stack traces

**metrics.jsonl** contains performance measurements:
- `rows_read` - Input row counts per step
- `rows_written` - Output row counts per step
- `execution_time_ms` - Step execution duration
- `memory_usage_mb` - Memory consumption

### HTML Reports

Generate interactive HTML reports for comprehensive analysis:

```bash
# Generate and open HTML report
osiris logs html --open

# Generate for specific session
osiris logs html --session run_1234567890 --open

# Output to custom directory
osiris logs html --output reports/
```

The HTML report provides:
- **Session overview**: Pipeline name, duration, row counts
- **Execution timeline**: Visual flow of all steps
- **Connection details**: Resolved database connections
- **Metrics dashboard**: Performance charts and statistics
- **Artifact browser**: Inspect generated files

### E2B-Specific Metrics

When running in E2B, additional metrics are captured:

- **Bootstrap time**: Time to provision and initialize the sandbox (typically 800-1200ms)
- **E2B badge**: Orange "E2B" indicator in the HTML report header
- **Remote artifacts**: Files downloaded from sandbox to `logs/<session>/remote/`
- **Sandbox events**: Worker initialization and RPC communication events

The HTML report automatically detects E2B sessions and displays the appropriate metrics and badges. Bootstrap time appears in the overview section, showing the one-time overhead of sandbox provisioning.

### Viewing Logs

Quick commands for log inspection:

```bash
# List all sessions
osiris logs list

# Show recent sessions with details
osiris logs list --recent 5

# View specific session
osiris logs show --session run_1234567890

# Clean up old sessions
osiris logs gc --keep-recent 10
```
