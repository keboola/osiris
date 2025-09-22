# Osiris CLI Reference

Command-line interface for Osiris v0.2.0 pipeline system.

## Global Options

```bash
osiris [--help] [--version] <command> [options]
```

- `--help`: Show help message
- `--version`: Display Osiris version (v0.2.0)

## Core Commands

### init - Initialize Configuration

Initialize Osiris configuration files:

```bash
osiris init
```

Creates:
- `.env` file for secrets (if not exists)
- `osiris_connections.yaml` for connection definitions

### chat - Conversational Pipeline Creation

Start interactive conversation to create pipelines:

```bash
osiris chat [--pro-mode]
```

Options:
- `--pro-mode`: Use custom LLM prompts from `.osiris_prompts/`

### compile - Compile OML to Manifest

Compile an OML pipeline into an executable manifest:

```bash
osiris compile <pipeline.oml> [--output DIR] [--verbose]
```

Example:
```bash
osiris compile pipeline.oml
# Output: logs/run_<timestamp>/compile_<timestamp>/manifest.yaml
```

### run - Execute Pipeline

Execute a compiled manifest or OML file:

```bash
# Run the last compiled manifest
osiris run --last-compile

# Run specific manifest
osiris run manifest.yaml

# Run with E2B cloud execution
osiris run --last-compile --e2b

# E2B with custom resources
osiris run --last-compile --e2b --e2b-cpu 4 --e2b-mem 8

# E2B with auto-install dependencies
osiris run --last-compile --e2b --e2b-install-deps
```

Options:
- `--last-compile`: Use the most recently compiled manifest
- `--e2b`: Execute in E2B cloud sandbox
- `--e2b-cpu N`: Number of CPU cores (default: 2)
- `--e2b-mem GB`: Memory in GB (default: 4)
- `--e2b-timeout SECONDS`: Execution timeout (default: 900)
- `--e2b-install-deps`: Auto-install missing Python packages
- `--e2b-env KEY=VALUE`: Set environment variable in sandbox
- `--e2b-pass-env NAME`: Pass environment variable from current shell
- `--dry-run`: Show execution plan without running
- `--verbose`: Show detailed execution output

### validate - Validate Configuration

Check Osiris configuration for errors:

```bash
osiris validate [--mode MODE]
```

Options:
- `--mode`: Validation mode (`strict`, `warn`, `off`), default: `warn`

Environment override:
```bash
OSIRIS_VALIDATION=strict osiris validate
```

## Connection Commands

### connections list - List Connections

Display configured connections with masked secrets:

```bash
osiris connections list [--json]
```

Example output:
```
Osiris Connections
╭─────────┬───────────┬──────────────────┬─────────╮
│ Family  │ Alias     │ Host             │ Default │
├─────────┼───────────┼──────────────────┼─────────┤
│ mysql   │ default   │ localhost:3306   │ ✓       │
│ mysql   │ primary   │ db.example.com   │         │
│ supabase│ main      │ *.supabase.co    │ ✓       │
╰─────────┴───────────┴──────────────────┴─────────╯
```

Options:
- `--json`: Output in JSON format

### connections doctor - Test Connections

Validate connection configurations and test connectivity:

```bash
osiris connections doctor
```

Checks:
- Configuration syntax validity
- Required fields present
- Environment variables resolved
- Network connectivity (if possible)

## Log Commands

### logs list - List Sessions

Display all pipeline execution sessions:

```bash
osiris logs list [--recent N] [--verbose]
```

Options:
- `--recent N`: Show only N most recent sessions
- `--verbose`: Include detailed session information

### logs show - Display Session Details

Show events and metrics for a specific session:

```bash
osiris logs show --session <session_id> [--filter TYPE]
```

Options:
- `--session`: Session ID (e.g., `run_1234567890`)
- `--filter`: Filter by event type (e.g., "error", "step_complete")

### logs html - Generate HTML Report

Create interactive HTML report for session analysis:

```bash
# Generate and open report
osiris logs html --open

# Generate for specific session
osiris logs html --session <session_id> --open

# Output to custom directory
osiris logs html --output reports/
```

Options:
- `--session`: Specific session ID (default: most recent)
- `--output`: Output directory (default: `logs/`)
- `--open`: Open report in browser after generation

The HTML report includes:
- Session overview with pipeline metrics
- Execution timeline visualization
- Connection details (masked secrets)
- Performance metrics and charts
- Artifact browser
- E2B-specific metrics (bootstrap time, badges)

### logs gc - Garbage Collection

Clean up old session logs:

```bash
osiris logs gc [--keep-recent N] [--older-than DAYS]
```

Options:
- `--keep-recent N`: Keep N most recent sessions (default: 10)
- `--older-than DAYS`: Remove sessions older than DAYS

## Pro Mode Commands

### dump-prompts - Export LLM Prompts

Export system prompts for customization:

```bash
osiris dump-prompts --export
```

Creates `.osiris_prompts/` directory with:
- `conversation_system.txt` - Main AI personality
- `sql_generation_system.txt` - SQL generation rules
- `user_prompt_template.txt` - Context building template

Use with `osiris chat --pro-mode` to apply custom prompts.

## Example Workflows

### Standard Pipeline Development

```bash
# 1. Initialize configuration
osiris init

# 2. Set up connections and secrets
vi osiris_connections.yaml
vi .env

# 3. Create pipeline via conversation
osiris chat

# 4. Compile the generated OML
osiris compile output/pipeline.oml

# 5. Run locally
osiris run --last-compile

# 6. Generate report
osiris logs html --open
```

### E2B Cloud Execution

```bash
# Set E2B API key
export E2B_API_KEY="your-key-here"

# Compile pipeline
osiris compile pipeline.oml

# Run in E2B with custom resources
osiris run --last-compile --e2b \
  --e2b-cpu 4 \
  --e2b-mem 8 \
  --e2b-timeout 3600 \
  --e2b-install-deps

# View results
osiris logs html --open
```

### Connection Management

```bash
# List all connections
osiris connections list

# Test connectivity
osiris connections doctor

# View as JSON for scripting
osiris connections list --json | jq '.connections.mysql'
```

## Environment Variables

Key environment variables used by Osiris:

- `E2B_API_KEY`: API key for E2B cloud execution
- `OSIRIS_VALIDATION`: Override validation mode (strict/warn/off)
- `MYSQL_PASSWORD`, `MYSQL_DATABASE`: MySQL credentials
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`: Supabase credentials

## Output Locations

- **Compiled manifests**: `logs/<session_id>/compile_<timestamp>/`
- **Execution logs**: `logs/<session_id>/events.jsonl`, `metrics.jsonl`
- **Artifacts**: `logs/<session_id>/artifacts/<step_id>/`
- **HTML reports**: `logs/index.html` and session-specific reports
- **Generated pipelines**: `output/` directory
