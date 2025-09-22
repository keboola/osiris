# Osiris User Guide

This guide covers the essential features of Osiris v0.2.0 for running data pipelines.

## Quick Start Checklist

Before running pipelines:
- [ ] Set up `.env` file with database passwords
- [ ] Create `osiris_connections.yaml` with connection details
- [ ] Test connections with `osiris connections doctor`
- [ ] Compile pipeline with `osiris compile pipeline.yaml`
- [ ] Run with `osiris run --last-compile`

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

### Understanding Log Files

#### events.jsonl - Execution Timeline
Each line is a JSON event showing what happened and when:

```json
{"ts": "2025-01-20T10:00:00Z", "session": "run_123", "event": "run_start"}
{"ts": "2025-01-20T10:00:01Z", "session": "run_123", "event": "step_start", "step_id": "extract_users", "driver": "mysql.extractor"}
{"ts": "2025-01-20T10:00:03Z", "session": "run_123", "event": "step_complete", "step_id": "extract_users", "rows_processed": 1500, "duration_ms": 2000}
```

**Key events to look for:**
- `run_start` / `run_complete` - Pipeline execution boundaries
- `step_start` / `step_complete` - Individual step execution
- `step_failed` - Step encountered error (includes error message and traceback)
- `connection_resolve_complete` - Connection successfully resolved
- `cleanup_complete` - Final event with total rows processed

#### metrics.jsonl - Performance Data
Performance metrics for monitoring and optimization:

```json
{"ts": "2025-01-20T10:00:03Z", "session": "run_123", "metric": "rows_read", "value": 1500, "tags": {"step": "extract_users"}}
{"ts": "2025-01-20T10:00:05Z", "session": "run_123", "metric": "rows_written", "value": 1500, "tags": {"step": "save_csv"}}
{"ts": "2025-01-20T10:00:06Z", "session": "run_123", "metric": "execution_duration", "value": 6.2, "unit": "seconds"}
```

**Important metrics:**
- `rows_read` - Rows extracted from source
- `rows_written` - Rows written to destination
- `step_duration_ms` - Time taken by each step
- `execution_duration` - Total pipeline runtime

### Troubleshooting with Logs

#### Pipeline Failed to Start
Look for early events in `events.jsonl`:
```bash
# Check for compilation errors
grep "compilation_failed" logs/run_*/events.jsonl

# Check for connection issues
grep "connection_failed" logs/run_*/events.jsonl
```

#### Step Failed During Execution
Find the failed step:
```bash
# Find failed steps
grep "step_failed" logs/run_*/events.jsonl | jq .

# View the error details
jq 'select(.event == "step_failed")' logs/run_*/events.jsonl
```

#### Performance Issues
Analyze metrics:
```bash
# Find slow steps (>5000ms)
jq 'select(.metric == "step_duration_ms" and .value > 5000)' logs/run_*/metrics.jsonl

# Check data volumes
jq 'select(.metric == "rows_read" or .metric == "rows_written")' logs/run_*/metrics.jsonl
```

#### No Data Processed
Check row counts:
```bash
# Look for zero rows
grep "rows_processed.*0" logs/run_*/events.jsonl

# Check SQL queries in artifacts
cat logs/run_*/artifacts/steps/*/config.json | jq '.query'
```

### Common Log Patterns

#### Successful Pipeline
```
run_start → step_start → step_complete → ... → cleanup_complete → run_complete
```

#### Failed Pipeline
```
run_start → step_start → step_failed → cleanup_complete → run_complete (exit_code: 1)
```

#### E2B Execution
```
adapter_selected (e2b) → sandbox_created → worker_started → [normal execution] → artifacts_downloaded
```

## 4. Using AI Assistants

Osiris pipelines can be created with help from AI assistants like ChatGPT, Claude, or other LLMs. We provide a specialized guide to ensure your AI assistant generates correct pipeline code.

### How to Use the LLM Guide

1. **Find the guide**: Located at `docs/user-guide/llms.txt`
2. **Share with your AI**: Copy the entire contents and paste it into your conversation with the AI assistant
3. **Ask for pipelines**: Request pipeline creation with specific requirements

### Example Workflow

```bash
# 1. View the LLM guide
cat docs/user-guide/llms.txt

# 2. Copy its contents to your AI assistant chat

# 3. Ask your AI assistant:
"Using the Osiris guide I just shared, create a pipeline that extracts
all customers from MySQL and saves them to a CSV file"

# 4. Save the generated pipeline
# The AI will create valid OML v0.1.0 YAML that you can save and run
```

### What the Guide Contains

The LLM guide provides your AI assistant with:
- **Essential rules**: OML version requirements, forbidden keys, correct syntax
- **Component list**: Available extractors and writers with their configurations
- **Connection patterns**: How to reference connections using @family.alias
- **Common examples**: Typical pipeline patterns and use cases
- **Troubleshooting tips**: How to fix common issues

### Tips for Best Results

1. **Be specific**: Tell the AI exactly what data you want and where it should go
2. **Mention connections**: Specify which connection alias to use (e.g., "@mysql.default")
3. **Request validation**: Ask the AI to "validate this follows OML v0.1.0"
4. **Test locally first**: Run pipelines locally before using E2B cloud

### Quick Checklist for AI

When working with an AI assistant, paste this checklist along with the guide:

```
OSIRIS PIPELINE REQUIREMENTS:
1. Always use oml_version: "0.1.0" (exactly this value)
2. Never include passwords or API keys in the pipeline
3. Use connection aliases like @mysql.default or @supabase.main
4. Use "mode: write" for output steps (not "mode: load")
5. Only use these top-level keys: oml_version, name, steps
6. Never use these forbidden keys: version, connectors, tasks, outputs
7. Each step needs: id, component, mode, config
8. Writers need inputs: {df: "${previous_step.df}"}
```

### Common AI Prompts

Try these prompts with your AI assistant after sharing the guide:

- "Create an Osiris pipeline that copies the 'orders' table from MySQL to Supabase"
- "Generate an Osiris OML pipeline that extracts products where price > 100 and writes to CSV"
- "Build a pipeline that reads all tables from MySQL and saves each to a separate CSV file"
- "Create a pipeline that extracts customer data from MySQL and uploads to Supabase with upsert mode"

The AI assistant will generate valid OML v0.1.0 pipelines that you can immediately compile and run with Osiris.

## 5. Common Issues and Solutions

### Connection Problems

#### "Connection refused" or "Can't connect to MySQL"
```bash
# Check if credentials are set
env | grep MYSQL

# Test connection
osiris connections doctor

# Common fixes:
# 1. Check host and port in osiris_connections.yaml
# 2. Verify database name is correct
# 3. Ensure user has permissions
# 4. Check firewall/network settings
```

#### "Access denied for user"
```bash
# Password is likely wrong or not set
# Check .env file has correct password
cat .env | grep PASSWORD

# Ensure no quotes around password in .env
MYSQL_PASSWORD=mypassword  # Correct
MYSQL_PASSWORD="mypassword"  # Wrong - quotes included
```

### Pipeline Execution Issues

#### "Component not found"
```yaml
# Check component name spelling
# Valid components:
- mysql.extractor
- supabase.extractor
- filesystem.csv_writer
- supabase.writer
```

#### "Missing required field in config"
```yaml
# Each component has required fields:
# Extractors need:
config:
  connection: "@mysql.default"  # Required
  query: "SELECT * FROM table"  # Required

# Writers need:
inputs:
  df: "${previous_step.df}"  # Required
config:
  path: "output/file.csv"  # Required for CSV writer
```

#### "Operation INSERT not allowed in Extract context"
```sql
-- Extractors can only use SELECT queries
-- ❌ Wrong:
INSERT INTO table VALUES (...)
DELETE FROM table WHERE ...

-- ✅ Correct:
SELECT * FROM table WHERE ...
```

### E2B Execution Issues

#### "E2B quota exceeded"
```bash
# Check your E2B usage at https://e2b.dev
# Reduce resource usage:
osiris run --e2b --e2b-cpu 1 --e2b-mem 2
```

#### "Sandbox creation timeout"
```bash
# Increase timeout:
osiris run --e2b --e2b-timeout 600  # 10 minutes
```

#### "Missing dependencies in E2B"
```bash
# Enable auto-install:
osiris run --e2b --e2b-install-deps
```

### Log Analysis Issues

#### HTML report won't open
```bash
# Generate report manually:
osiris logs html --session run_XXX --output report.html

# Open in browser:
open report.html  # macOS
xdg-open report.html  # Linux
```

#### Can't find session logs
```bash
# List all sessions:
osiris logs list

# Find recent sessions:
osiris logs list --recent 10

# Logs are in:
ls logs/run_*
```

### Environment Issues

#### "Environment variable not found"
```bash
# Check if .env is loaded:
osiris run --verbose  # Shows environment loading

# Manually export:
export MYSQL_PASSWORD="mypassword"
osiris run pipeline.yaml
```

#### Multiple .env files confusion
```bash
# Osiris searches in order:
# 1. Current directory .env
# 2. Project root .env
# 3. testing_env/.env (if in testing_env)

# Check which is loaded:
pwd  # See current directory
ls -la .env  # Check if exists here
```

## 6. Best Practices

### Security
1. **Never commit `.env` files** - Add to `.gitignore`
2. **Use read-only database users** for extraction
3. **Mask secrets in logs** - Osiris does this automatically
4. **Rotate credentials regularly**

### Performance
1. **Use LIMIT in SQL** during development
2. **Test with small datasets first**
3. **Monitor memory usage** for large datasets
4. **Use batch_size for writers** with large data

### Development Workflow
1. **Start with `osiris chat`** to generate pipelines
2. **Test connections first** with `osiris connections doctor`
3. **Compile before running** to catch errors early
4. **Use HTML reports** for debugging
5. **Keep logs** for troubleshooting (use `osiris logs gc` to clean old ones)

### Pipeline Design
1. **One responsibility per step** - Extract OR transform OR write
2. **Use meaningful step IDs** - `extract_customers` not `step1`
3. **Add comments** in YAML for complex queries
4. **Version control pipelines** - Keep OML files in git
