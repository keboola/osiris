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
- **Version**: v0.5.0 PRODUCTION READY (October 2025)
- **Testing**: 1577+ tests passing (98.1% pass rate)
- **Coverage**: 78.4% overall (85.1% adjusted)
- **Features**: E2B Integration, Component Registry, Rich CLI, AIOP System, MCP v0.5.0

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

# MCP operations (v0.5.0+)
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

## Architecture

### Core Modules
- **`osiris/core/`** - LLM-first functionality (agent, discovery, state, AIOP)
- **`osiris/connectors/`** - Database adapters (MySQL, Supabase)
- **`osiris/drivers/`** - Runtime implementations
- **`osiris/remote/`** - E2B cloud execution
- **`osiris/cli/`** - Rich-powered CLI with helpers for code reuse
- **`osiris/mcp/`** - Model Context Protocol server with CLI-first security

### Key Principles
1. **LLM-First**: AI handles discovery, SQL generation, pipeline creation
2. **Security-First**: MCP zero-secret access via CLI delegation
3. **DRY Code**: Shared helpers eliminate duplication
4. **Progressive Discovery**: Intelligent schema exploration
5. **Human Validation**: Expert approval required

## MCP Security Architecture

```
MCP Server (NO SECRETS) → CLI Bridge → CLI Subcommands (HAS SECRETS)
```

### Critical Rules
- **Code Reuse**: MCP commands MUST reuse CLI logic via `osiris/cli/helpers/`
- **Secret Masking**: Use `mask_connection_for_display()` with spec-aware detection
- **Delegation Pattern**: MCP tools call CLI via `run_cli_json()`
- **Filesystem Contract**: All paths MUST be config-driven, never hardcoded (`Path.home()` forbidden)

Example:
```python
# Shared helper (single source)
from osiris.cli.helpers.connection_helpers import mask_connection_for_display
result = mask_connection_for_display(config, family=family)  # Spec-aware
```

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
- **Reference**: `docs/reference/` - Stable specifications
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
1. Current directory
2. Project root
3. testing_env/ (when CWD)

# Setting secrets:
export MYSQL_PASSWORD="value"         # Option 1: Export
echo "MYSQL_PASSWORD=value" > .env    # Option 2: File
MYSQL_PASSWORD="value" osiris run ... # Option 3: Inline
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
- Current: v0.5.0 (Production Ready)
- Model: Opus 4.1 (claude-opus-4-1-20250805)
- Python: 3.8+ required
- Test Suite: ~196 seconds full run

For detailed information, see documentation in `docs/`.