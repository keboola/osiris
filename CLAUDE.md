# CLAUDE.md

This file provides guidance to Claude Code when working with the Osiris repository.

## Project Overview

Osiris MVP is an **LLM-first conversational ETL pipeline generator** that uses AI to understand intent, discover schemas, generate SQL, and create YAML pipelines - replacing template-based approaches with intelligent conversation.

### How It Works
1. **User starts conversation**: `osiris chat`
2. **AI discovers database**: Profiles tables and schemas
3. **User describes intent**: Natural language request
4. **AI generates pipeline**: Creates YAML pipeline
5. **Human validates**: Reviews before execution
6. **Optional execution**: Approved pipelines run locally or in E2B cloud

### Current Status
- **Version**: v0.5.4 PRODUCTION READY (October 2025)
- **Testing**: 1577+ tests passing (98.1% pass rate)
- **Coverage**: 78.4% overall (85.1% adjusted)
- **Features**: E2B Integration, Component Registry, Rich CLI, AIOP System, MCP v0.5.4

## Quick Setup

```bash
# Create and activate environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Initialize (sets base_path to current directory)
cd testing_env
python ../osiris.py init
```

## Key Commands

```bash
# Core operations
make chat                      # Main conversational interface
osiris run pipeline.yaml --e2b # Run in E2B cloud sandbox
osiris logs aiop --last        # Export AIOP for LLM analysis

# MCP operations (v0.5.4+)
osiris mcp run --selftest      # Server self-test (<1.3s)
osiris mcp connections list --json
osiris mcp aiop list --json

# Development
make fmt                       # Auto-format code
make test                      # Run tests
make lint                      # Lint checks
make security                  # Security checks

# Pro Mode (custom LLM prompts)
osiris dump-prompts --export   # Export prompts
# Edit in .osiris_prompts/
osiris chat --pro-mode         # Use custom prompts
```

## Available Skills

Skills are specialized tools invoked via the Skill tool when needed:

- **codex**: Interact with OpenAI Codex CLI for second opinions, multi-model analysis, and structured output generation. Useful for code review from different AI perspective, architectural validation, or when you need structured JSON responses with schemas.

Usage: "Use the codex skill to [task]" or "Invoke codex skill"

## AI Component Development

For building new Osiris components with AI assistance:

**Entry Point:** `docs/developer-guide/ai/START-HERE.md`
- Task-based routing for component development
- Decision trees (API type, auth, pagination)
- Working recipes (REST, GraphQL, SQL)
- 57 validation rules (COMPONENT_AI_CHECKLIST.md)

**Key Documentation:**
- E2B compatibility: `docs/developer-guide/ai/e2b-compatibility.md` (792 lines, 100% coverage)
- Error patterns: `docs/developer-guide/ai/error-patterns.md` (18+ common errors with fixes)
- Dependencies: `docs/developer-guide/ai/dependency-management.md` (requirements.txt, venv, E2B)
- Recipes: `docs/developer-guide/ai/recipes/` (REST, GraphQL, SQL templates)

**Coverage:** 98% of critical topics (metrics, secrets, filesystem contract, data passing, E2B, dependencies)

## Architecture

### Core Modules
- **`osiris/core/`** - LLM-first functionality (agent, discovery, state, AIOP)
- **`osiris/connectors/`** - Database adapters (MySQL, Supabase)
- **`osiris/drivers/`** - Runtime implementations
- **`osiris/remote/`** - E2B cloud execution
- **`osiris/cli/`** - Rich-powered CLI with helpers for code reuse
- **`osiris/mcp/`** - Model Context Protocol server with CLI-first security
- **`components/`** - Component specs with x-connection-fields for override control

### Key Principles
1. **LLM-First**: AI handles discovery, SQL generation, pipeline creation
2. **Security-First**: MCP zero-secret access via CLI delegation, x-connection-fields prevent credential overrides
3. **DRY Code**: Shared helpers eliminate duplication
4. **Progressive Discovery**: Intelligent schema exploration
5. **Human Validation**: Expert approval required
6. **Agent-First Workflow**: When the work plan allows, prefer using sub-agents (Task tool) for complex, multi-step tasks. This enables parallel execution, specialized expertise, and better resource management. Use sub-agents for exploration, testing, documentation, and any task that can be delegated.

## MCP Security Architecture

```
MCP Server (NO SECRETS) → CLI Bridge → CLI Subcommands (HAS SECRETS)
```

### Critical Rules
- **Code Reuse**: MCP commands MUST reuse CLI logic via `osiris/cli/helpers/`
- **Secret Masking**: Use `mask_connection_for_display()` with spec-aware detection
- **Delegation Pattern**: MCP tools call CLI via `run_cli_json()`
- **Filesystem Contract**: All paths MUST be config-driven, never hardcoded (`Path.home()` forbidden)
- **Override Control**: Component specs use `x-connection-fields` to declare which fields can be overridden (see `docs/reference/x-connection-fields.md`)
- **Handshake Instructions**: MCP server provides usage instructions during initialize handshake, guiding LLMs on proper OML workflow and validation requirements

Example:
```python
# Shared helper (single source)
from osiris.cli.helpers.connection_helpers import mask_connection_for_display
result = mask_connection_for_display(config, family=family)  # Spec-aware
```

### Component Connection Fields (x-connection-fields)

Components declare which fields come from connections and control override policies:
- `override: allowed` - Infrastructure fields (host, port) can be overridden for testing
- `override: forbidden` - Security fields (password, token) cannot be overridden
- `override: warning` - Ambiguous fields (headers) can override but emit warning

See `docs/reference/x-connection-fields.md` for full specification.

## Testing Guidelines

### Rules
- **All tests in `tests/`** - Never create tests elsewhere
- **Run from `testing_env/`** - Isolates artifacts
- **Real credentials only** - Never use fake passwords
- **Use fixtures** - `tmp_path` for temp directories
- **Add suppressions** - `# noqa` for intentional violations

### Secret Suppression Patterns (Required for CI)
```python
# Test credentials (not real secrets)
config = {"password": "test123"}  # pragma: allowlist secret
conn_str = "mysql://user:pass@localhost"  # nosec B105

# Lazy imports for performance
import yaml  # noqa: PLC0415
from osiris.core import Config  # noqa: PLC0415, I001

# Required initialization order
setup_environment()
from osiris.mcp import Server  # noqa: E402

# Complex CLI routers (naturally verbose)
def handle_command(args):  # noqa: PLR0915
```

Key suppression codes:
- `pragma: allowlist secret` - detect-secrets suppression
- `nosec B105` - Bandit password false positives
- `PLC0415` - Import not at top-level (lazy imports)
- `E402` - Module import not at top (required order)
- `PLR0915` - Too many statements (>50 lines)

### OML Validation Architecture
- **3-Layer Validation**: Schema → Semantic → Runtime
- **Business Logic**: Validator enforces requirements (e.g., primary_key for replace/upsert modes)
- **Reference**: See `docs/reference/oml-validation.md` for complete validation architecture

### Common Issues
- ~43 tests skip without credentials (normal)
- Supabase isolation: `pytest -m "not supabase"`
- Format first: Run `make fmt` before committing

## Development Workflow

### Branch Strategy
- **main**: Protected, PR-only, always stable
- **feature branches**: All development work
- **No direct commits to main**

### Code Quality
- Line length: 120 chars
- Pre-commit: Black, isort, Ruff, detect-secrets
- CI: Strict checks without auto-fix
- Emergency: `make commit-wip` or `make commit-emergency`

### Documentation & Docs Governance

**Structure**:
- **ADRs**: `docs/adr/` - Short, immutable architecture decisions
- **Milestones**: `docs/milestones/<slug>/` - Initiative folders with:
  - `00-initiative.md` - Index, goal, DoD, KPIs
  - `10-plan.md` - Scope, risks, estimates
  - `20-execution.md` - Checklists, PR links
  - `30-verification.md` - Tests, metrics
  - `40-retrospective.md` - Learnings
  - `attachments/` - Reports, coverage data
- **Reference**: `docs/reference/` - Stable specifications (e.g., `oml-validation.md`, `x-connection-fields.md`)
- **AI Guides**: `docs/developer-guide/ai/` - AI-assisted component development
  - START-HERE.md - Entry point with task routing
  - Decision trees, recipes, error patterns, E2B guide
- **Design**: `docs/design/` - Work-in-progress technical designs
- **Reports**: `docs/reports/<date>-<topic>/` - One-off reports
- **Archive**: `docs/archive/<slug>-v<semver>/` - Completed initiatives

**Rules**:
- Every non-trivial ADR spawns an initiative folder
- Update initiative index when scope/DoD changes
- Link reports from initiative's `attachments/`
- Archive completed initiatives to keep active folders clean

## AIOP System

AI Operation Package for LLM-consumable debugging:
- **Multi-layered**: Evidence, Semantic, Narrative, Metadata
- **Deterministic**: Stable IDs and timestamps
- **Secret-free**: Automatic DSN redaction
- **Size-controlled**: ≤300KB packages

Critical: Never change core function signatures without review.

## Filesystem Contract & Configuration

### Base Path Configuration (Critical)
- `osiris init` automatically sets `filesystem.base_path` to absolute path of current directory
- Example: `cd testing_env && osiris init` → `base_path: "/Users/padak/github/osiris/testing_env"`
- **All paths MUST be config-driven** - Never use `Path.home()` or hardcode paths
- MCP logs structure: `<base_path>/.osiris/mcp/logs/{audit,cache,telemetry}/`
- Session artifacts: `<base_path>/{.osiris_sessions, .osiris_cache, logs, output}/`

## Environment Management

```bash
# Search order for .env files:
1. $OSIRIS_HOME/.env (if OSIRIS_HOME is set) - HIGHEST PRIORITY
2. Current directory
3. Project root
4. testing_env/ (when CWD)

# Setting secrets:
export MYSQL_PASSWORD="value"         # Option 1: Export
echo "MYSQL_PASSWORD=value" > .env    # Option 2: File
MYSQL_PASSWORD="value" osiris run ... # Option 3: Inline

# Using OSIRIS_HOME:
export OSIRIS_HOME="/path/to/project" # Ensures .env is loaded from project directory
osiris run pipeline.yaml               # Works from any directory
```

## Common Pitfalls

❌ **DON'T**:
- Duplicate code between CLI and MCP
- Access secrets in MCP process
- Create tests outside `tests/`
- Use fake credentials
- Commit directly to main

✅ **DO**:
- Extract shared logic to helpers
- Delegate MCP to CLI subcommands
- Use pytest fixtures
- Run from `testing_env/`
- Create PRs for all changes
- Ensure validator checks business logic (e.g., primary_key for replace/upsert modes)
- For component development, start with `docs/developer-guide/ai/START-HERE.md`
- Test components with `--e2b` flag for cloud compatibility
- Follow 57 validation rules in COMPONENT_AI_CHECKLIST.md

## Driver Development Guidelines

### DuckDB-Based Data Exchange (ADR 0043)

Drivers use **DuckDB tables** for data exchange between pipeline steps. All data flows through a shared `pipeline_data.duckdb` file per session.

### Context API Contract

Drivers receive a `ctx` object with these methods:

**Available methods:**
- ✅ `ctx.get_db_connection()` - Get shared DuckDB connection for data exchange
- ✅ `ctx.log_metric(name, value, **kwargs)` - Log metrics to metrics.jsonl
- ✅ `ctx.output_dir` - Path to step's artifacts directory (Path object)

**NOT available:**
- ❌ `ctx.log()` - Does NOT exist! Use `logger.info()` instead

### Logging (REQUIRED)

ALWAYS use Python's standard logging module. Never use `ctx.log()`.

```python
import logging

logger = logging.getLogger(__name__)

def run(*, step_id: str, config: dict, inputs: dict, ctx):
    logger.info(f"[{step_id}] Starting extraction")
    logger.error(f"[{step_id}] Failed: {error}")

    # Metrics go via ctx
    ctx.log_metric("rows_read", 1000)
```

### Driver Patterns

#### Extractor Pattern (streams to DuckDB)
```python
def run(self, *, step_id: str, config: dict, inputs: dict, ctx) -> dict:
    conn = ctx.get_db_connection()
    table_name = step_id

    # Stream data in batches
    for i, batch_df in enumerate(fetch_batches()):
        if i == 0:
            conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM batch_df")
        else:
            conn.execute(f"INSERT INTO {table_name} SELECT * FROM batch_df")

    ctx.log_metric("rows_read", total_rows)
    return {"table": table_name, "rows": total_rows}
```

#### Processor Pattern (reads/writes DuckDB tables)
```python
def run(self, *, step_id: str, config: dict, inputs: dict, ctx) -> dict:
    conn = ctx.get_db_connection()
    input_table = inputs.get("table")  # From upstream step

    query = config["query"]  # SQL referencing input_table
    conn.execute(f"CREATE TABLE {step_id} AS {query}")

    row_count = conn.execute(f"SELECT COUNT(*) FROM {step_id}").fetchone()[0]
    return {"table": step_id, "rows": row_count}
```

#### Writer Pattern (reads from DuckDB)
```python
def run(self, *, step_id: str, config: dict, inputs: dict, ctx) -> dict:
    conn = ctx.get_db_connection()
    table_name = inputs["table"]  # From upstream step

    # Read data from DuckDB
    df = conn.execute(f"SELECT * FROM {table_name}").df()

    # Write to destination (API, file, etc.)
    write_to_destination(df, config)

    ctx.log_metric("rows_written", len(df))
    return {}  # Writers return empty dict
```

### Testing Requirements

ALWAYS test drivers in **both** environments before committing:

```bash
# 1. Local execution
osiris compile your_pipeline.yaml
osiris run --last-compile

# 2. E2B cloud execution
osiris run --last-compile --e2b --e2b-install-deps
```

Both environments use identical DuckDB-based data exchange - no special handling needed.

### Component Spec Requirements

Every component needs `x-runtime` dependencies declared:

```yaml
x-runtime:
  driver: osiris.drivers.your_driver.YourDriver
  requirements:
    imports:
      - pandas
      - requests
    packages:
      - pandas
      - requests>=2.0
```

## Project Structure

```
osiris/
├── cli/           # CLI with helpers/
├── connectors/    # Database connectors
├── core/          # Core functionality
├── drivers/       # Runtime drivers
├── mcp/          # MCP server
├── remote/       # E2B execution
└── runtime/      # Local execution
```

## Version Info
- Current: v0.5.4 (Production Ready)
- Model: Opus 4.1 (claude-opus-4-1-20250805)
- Python: 3.11+ required
- Test Suite: ~196 seconds full run

For detailed information, see documentation in `docs/`.