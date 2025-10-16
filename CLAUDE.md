# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Osiris MVP is an **LLM-first conversational ETL pipeline generator**. It uses AI conversation to understand user intent, discover database schemas, generate SQL, and create YAML pipelines. This is an **agentic AI system** that replaces traditional template-based approaches with intelligent conversation.

### Project Status (October 2025)
- **✅ v0.3.1 Released**: M2a AIOP Complete - **PRODUCTION READY**
- **✅ Core Features**: E2B Integration (full parity, <1% overhead), Component Registry, Rich CLI
- **✅ AIOP System**: AI Operation Package exports structured, LLM-consumable data after every run
  - Evidence, Semantic, Narrative, and Metadata layers
  - Automatic secret redaction and size-controlled exports
  - Delta analysis and intent discovery
- **📊 Implementation**: 35 ADRs documenting design decisions, milestones M0-M2a complete
- **🧪 Testing**: 1177+ tests passing, 43 skipped (E2B live tests)
  - Split-run test strategy for Supabase isolation (917 non-Supabase + 54 Supabase)
  - 202 MCP-specific tests (all passing, +8 new concurrent tests)
  - Stateless driver pattern eliminates test cross-contamination
  - Test suite runtime: ~50 seconds (Supabase suite <1 second)
- **✅ MCP v0.5.0 Phase 1 Complete** - CLI-First Security Architecture (2025-10-16)
  - Zero secret access in MCP process via CLI delegation pattern
  - Spec-aware secret masking using ComponentRegistry x-secret declarations
  - Resource URI system fully functional (discovery, memory, OML drafts)
  - Config-driven filesystem paths (no hardcoded directories)
  - 10 CLI subcommands for MCP tools across 7 domains
  - Comprehensive test coverage and CI security guards
- **✅ P0 Critical Bug Fixes Complete** (2025-10-16)
  - Fixed 14 critical bugs causing data corruption and security vulnerabilities
  - Eliminated race conditions in audit logging and telemetry (50-70% data loss fixed)
  - Fixed cache system (now persists correctly across restarts)
  - Eliminated all credential leaks in driver logging
  - Fixed resource leaks (900 connections per 100 ops → 0 leaks)
  - All fixes verified with 202/202 tests passing (100% success rate)
  - See: `docs/security/P0_FIXES_COMPLETE_2025-10-16.md` and `docs/security/MASS_BUG_SEARCH_2025-10-16.md`
- **🚀 Next**: P1 bug fixes (26 high-priority), MCP Phase 2 (Functional Parity), M2b (Real-time AIOP streaming)

## Quick Setup

1. **Create and activate virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Initialize configuration:**
   ```bash
   # Always activate venv first!
   source .venv/bin/activate

   # Initialize Osiris configuration (automatically sets base_path to current directory)
   cd testing_env   # Or your desired project directory
   python ../osiris.py init

   # Creates osiris.yaml with base_path set to absolute path of current directory
   # Example: base_path: "/Users/padak/github/osiris/testing_env"
   ```

## Common Commands

### Running Osiris
**IMPORTANT**: Always activate virtual environment first: `source .venv/bin/activate`

**RECOMMENDED**: Use Makefile commands to run from `testing_env/` and isolate artifacts:

```bash
# Main conversational interface
make chat

# Initialize and validate configuration
make init
make validate

# Session log management
osiris logs list           # List all sessions
osiris logs show --session <id>  # Show session details
osiris logs aiop --last    # Export latest run as AIOP for LLM analysis

# Run pipeline in E2B cloud sandbox
osiris run pipeline.yaml --e2b

# Pro mode: Custom LLM prompts (make dump-prompts, edit, then make chat-pro)
```

**Direct usage** (from project root): `python osiris.py [command]`

### Development Commands
```bash
# Always activate venv first: source .venv/bin/activate

# Modern development workflow (RECOMMENDED)
make dev                    # Full dev setup: install deps + pre-commit
make fmt                    # Auto-format code (Black, isort, Ruff --fix)
make lint                  # Strict lint checks (no auto-fix)
make security              # Run Bandit security checks
make test                  # Run tests
make type-check            # Type check (mypy)
make clean                 # Clean build artifacts

# Pre-commit hooks (automatically run on git commit)
make pre-commit-install    # Install pre-commit hooks
make precommit             # Install, update, and run all hooks
make pre-commit-run        # Run hooks on staged files
make pre-commit-all        # Run hooks on all files

# Quick commit helpers
make commit-wip msg="..."  # Commit with WIP, skip slower checks
make commit-emergency msg="..."  # Emergency commit, skip ALL checks

# Traditional commands (still supported)
python -m pytest tests/
black --line-length=120 osiris/
ruff check osiris/
python osiris.py --help
```

## Documentation Structure

The project has comprehensive documentation organized as follows:

### User Documentation
- **`docs/quickstart.md`** - 5-minute getting started guide
- **`docs/overview.md`** - Non-technical introduction with examples
- **`docs/user-guide/user-guide.md`** - Complete user manual with:
  - Connection setup and secrets management
  - Running pipelines (local and E2B)
  - Log interpretation and troubleshooting
  - Common issues and solutions
  - Best practices
- **`docs/user-guide/llms.txt`** - Guide for using AI assistants to generate pipelines

### Developer Documentation
- **`docs/architecture.md`** - Technical deep-dive with layered diagrams:
  - Conversational Agent architecture (7 focused diagrams)
  - Compilation and execution flows
  - State machine and component interactions
- **`docs/developer-guide/`** - Module documentation:
  - `module-cli.md` - CLI module with Rich framework
  - `module-core.md` - Core business logic and orchestration
  - `module-drivers.md` - Driver protocol and implementations
  - `module-connectors.md` - Database connection management
  - `module-remote.md` - E2B transparent proxy
  - `module-runtime.md` - Local execution adapter
  - `module-components.md` - Component registry system
- **LLM Contracts** - Machine-readable instructions for AI:
  - `llms.txt` - Main development contract
  - `llms-drivers.txt` - Driver-specific patterns
  - `llms-cli.txt` - CLI development patterns
  - `llms-testing.txt` - Test writing patterns

### Reference Documentation
- **`docs/reference/pipeline-format.md`** - OML v0.1.0 specification
- **`docs/reference/cli.md`** - Complete CLI command reference
- **`docs/reference/components-spec.md`** - Component specification format
- **`docs/reference/sql-safety.md`** - SQL validation rules by context
- **`docs/reference/events_and_metrics_schema.md`** - Log format and metrics

### AI-Assisted Development
- **`docs/developer-guide/ai/checklists/COMPONENT_AI_CHECKLIST.md`** - LLM-assisted component development guide
- **`docs/developer-guide/human/BUILD_A_COMPONENT.md`** - Human-friendly component building guide
- **`docs/archive/`** - Archived LLM contracts (llms.txt, llms-drivers.txt, etc.)

### Architecture Decisions
- **`docs/adr/`** - 35 Architecture Decision Records
  - ADR-0034: E2B Runtime Unification with Local Runner (proposed)
  - ADR-0035: Compiler Secret Detection via Specs and Connections (proposed)
  - ADR-0036: MCP CLI-First Security Architecture (accepted)
- **`docs/roadmap/`** - Future milestones (M2b, M3, M4)
- **`docs/examples/`** - Sample pipelines (MySQL, DuckDB, Supabase demos)

### Security & Quality Assurance
- **`docs/security/`** - Security audits and bug tracking
  - `MASS_BUG_SEARCH_2025-10-16.md` - 73 bugs found via parallel agent search
  - `P0_FIXES_COMPLETE_2025-10-16.md` - 14 critical bugs fixed (complete report)
  - `P0_FIX_PLAN_2025-10-16.md` - Detailed fix plan with code examples
  - `BUG_FIX_STATUS_2025-10-16.md` - **Current status**: 14/73 bugs fixed, 59 remaining
  - `AGENT_SEARCH_GUIDE.md` - Reusable bug detection methodology (v2.0)
  - Category-specific reports: race conditions, error handling, state management, configuration
  - **Status**: All P0 critical bugs eliminated, system production-ready

## Architecture

### Core Components

- **`osiris/core/`** - Core LLM-first functionality
  - `conversational_agent.py` - Main AI agent that handles conversations
  - `llm_adapter.py` - Multi-provider LLM interface (OpenAI, Claude, Gemini)
  - `discovery.py` - Database schema discovery and progressive profiling
  - `state_store.py` - SQLite-based session state management
  - `session_logging.py` - Session-scoped logging with structured events and metrics
  - `secrets_masking.py` - Automatic masking of sensitive data in logs
  - `config.py` - Configuration management and sample config generation
  - `execution_adapter.py` - Abstract base class for execution environments
  - `adapter_factory.py` - Factory for selecting local vs E2B execution
  - `run_export_v2.py` - AIOP export with Evidence, Semantic, Narrative, Metadata layers

- **`osiris/connectors/`** - Database adapters
  - `mysql/` - MySQL extractor + writer with connection pooling
  - `supabase/` - Supabase extractor + writer for cloud PostgreSQL

- **`osiris/drivers/`** - Runtime driver implementations
  - `mysql_extractor_driver.py` - MySQL data extraction
  - `supabase_writer_driver.py` - Supabase/PostgreSQL writing with DDL generation
  - `duckdb_processor_driver.py` - In-memory SQL transformations
  - `filesystem_csv_writer_driver.py` - CSV file output
  - `graphql_extractor_driver.py` - Generic GraphQL API extraction (if merged)

- **`osiris/remote/`** - E2B cloud execution
  - `e2b_transparent_proxy.py` - Transparent proxy for E2B sandbox execution
  - `proxy_worker.py` - Worker process running inside E2B sandbox
  - `rpc_protocol.py` - RPC communication protocol between proxy and worker
  - `e2b_client.py` - E2B SDK wrapper for sandbox management

- **`osiris/runtime/`** - Local execution runtime
  - `local_adapter.py` - Local execution adapter with driver support

- **`osiris/cli/`** - Command-line interface (Rich-powered)
  - `chat.py` - Interactive conversational mode with Rich formatting
  - `main.py` - CLI entry point and command routing with Rich terminal output
  - `logs.py` - Session log management commands (list, show, cleanup, aiop export)
  - `connections_cmd.py` - Connection management (list, doctor) with spec-aware secret masking
  - `mcp_cmd.py` - MCP server entrypoint and subcommand router
  - `helpers/` - Shared helper functions to eliminate code duplication
    - `connection_helpers.py` - Spec-aware secret masking using component x-secret declarations
  - `mcp_subcommands/` - MCP CLI subcommands (delegate to CLI bridge)
    - `connections_cmds.py` - MCP connections tools (reuses spec-aware masking from shared helpers)
    - `discovery_cmds.py` - MCP discovery tools
    - `oml_cmds.py` - MCP OML validation tools

- **`osiris/mcp/`** - Model Context Protocol server
  - `cli_bridge.py` - CLI delegation via subprocess (security boundary)
  - `tools/` - MCP tool implementations (delegate to CLI subcommands)
  - `config.py` - MCP server configuration with filesystem contract
  - `cache.py` - Discovery cache management

### Key Principles

1. **LLM-First**: AI handles discovery, SQL generation, and pipeline creation
2. **Conversational**: Natural language interaction guides the entire process
3. **Human Validation**: Expert approval required before pipeline execution
4. **Progressive Discovery**: AI explores database schema intelligently
5. **Stateful Sessions**: Context preserved across conversation turns
6. **Security-First**: MCP process has zero access to secrets (CLI-first delegation pattern)
7. **DRY Code**: Shared helpers eliminate duplication between CLI and MCP commands

## File Structure

```
osiris_pipeline/
   osiris/                     # Core package
      cli/                    # Command-line interface
      connectors/             # Database connectors
      core/                   # Core functionality
      templates/              # Template library
   testing_env/               # Testing workspace (git ignored)
   requirements.txt           # Dependencies
   osiris.py             # Development runner
```

### Session Management
Osiris maintains conversation state and structured logging:
- `.osiris_sessions/` - Session data for conversation continuity
- `.osiris_cache/` - Database discovery cache
- `logs/` - Session-scoped logs with events.jsonl, metrics.jsonl, and artifacts
- `output/` - Generated pipeline files

## Environment & Secrets Management

### Environment Loading
Osiris uses a unified environment loading system that ensures consistent behavior across all commands:

**Search Order for .env files:**
1. Current working directory (`.env`)
2. Project root where `osiris.py` lives (`.env`)
3. `testing_env/.env` (only when CWD is `testing_env/`)

**Key Principles:**
- Exported environment variables always take precedence over `.env` files
- Empty strings (`""`) are treated as unset/missing
- All commands (`chat`, `compile`, `run`, `connections`) use the same loader
- Safe to call multiple times (idempotent)

**Setting Secrets:**
```bash
# Option 1: Export in shell
export MYSQL_PASSWORD="your-password"  # pragma: allowlist secret
osiris run pipeline.yaml

# Option 2: Use .env file
echo "MYSQL_PASSWORD=your-password" > .env  # pragma: allowlist secret
osiris run pipeline.yaml

# Option 3: Inline for single command
MYSQL_PASSWORD="your-password" osiris run pipeline.yaml  # pragma: allowlist secret
```

## Dependencies

**Core System:**
- `duckdb` - Local SQL transformation engine
- `rich` - CLI framework with beautiful terminal output, tables, colors, and progress indicators
- `pyyaml` - YAML pipeline format
- `python-dotenv` - Environment variable loading from .env files

**Database Connectors:**
- `pymysql`, `sqlalchemy` - MySQL connectivity
- `supabase` - Cloud PostgreSQL client

**Data Processing:**
- `duckdb` - In-memory SQL transformation engine
- `pandas` - DataFrame processing and manipulation
- `requests` - HTTP client for API integrations
- `jsonpath-ng` - JSONPath extraction for GraphQL/REST APIs (if merged)

**LLM Providers:**
- `openai` - GPT-4o, GPT-4 models
- `anthropic` - Claude-3.5 Sonnet
- `google-generativeai` - Gemini models

## How It Works

1. **User starts conversation**: `python osiris.py chat`
2. **AI discovers database**: Automatically profiles tables and schemas
3. **User describes intent**: "Show me top customers by revenue"
4. **AI generates pipeline**: Creates YAML pipeline
5. **Human validates**: Reviews pipeline before execution
6. **Optional execution**: User can approve pipeline for execution

## Pro Mode
Advanced users can customize LLM system prompts: `python osiris.py dump-prompts --export`, edit prompts in `.osiris_prompts/`, then use `python osiris.py chat --pro-mode`

## Development Workflow & Branch Strategy

### Code Quality Standards

**Line Length**: Standardized to 120 characters across all tools (Black, isort, Ruff)

**VS Code Integration**:
- Auto-format on save configured (`.vscode/settings.json`)
- Black formatting with 120 char line length
- Auto-organize imports on save

**Pre-commit Hooks** (fast, auto-fixing):
- Black formatting
- isort import sorting
- Ruff with `--fix --exit-zero` (fixes what it can, won't block)
- detect-secrets baseline check
- NO Bandit locally (runs in CI only)
- If hooks keep re-formatting, run `make fmt` first, then commit

**CI Checks** (strict, no auto-fix):
- Ruff check (no fix)
- Black --check
- isort --check-only
- Bandit security scanning

**Quick Development Flow**:
1. Write code (VS Code auto-formats on save if configured)
2. `git add` your changes
3. `git commit` - pre-commit auto-fixes formatting
4. `git push` - CI runs strict checks

**Emergency Commits**:
- `make commit-wip msg="debugging"` - Skip slower checks
- `make commit-emergency msg="hotfix"` - Skip ALL checks (use sparingly)

**Troubleshooting Pre-commit**:
- If hooks keep modifying files in a loop: Run `make fmt` first, then commit
- If Ruff complains about unfixable issues: It now uses `--exit-zero` so it won't block
- If detect-secrets blocks legitimate code: Add `# pragma: allowlist secret` comment
- For persistent issues: Use `make commit-wip` to bypass Ruff/Bandit temporarily

### Branch Management
1. **Main Branch**
   - Always stable and release-ready
   - Contains only merged, tested milestones
   - Never commit WIP directly to main

2. **Milestone Branches**
   - Each milestone gets its own branch: `milestone-m0`, `milestone-m1`, etc.
   - All development for a milestone happens in its branch
   - Merge to main only after milestone is complete, tested, and documented

3. **Pull Request Requirements**
   - Must include updated CHANGELOG.md entry
   - Milestone document must be complete and validated
   - All tests must pass
   - ADRs must be linked and referenced

### Branch Protection Rules

**⚠️ CRITICAL: The `main` branch is protected - NO direct commits allowed!**
- All changes must go through pull requests
- This includes version bumps, documentation updates, and all code changes
- Only tags can be pushed directly: `git push origin v0.x.y`
- If you accidentally commit locally to main, create a new branch from your changes

### Documentation & Decision Making

#### Architecture Decision Records (ADRs)
**Location**: `docs/adr/`
**Rules**:
- Every architectural decision requires an ADR
- Numbered sequentially: `0001-title.md`, `0002-title.md`, etc.
- ADRs are immutable once accepted (create new ADRs for changes)
- Milestone documents must link to relevant ADRs
- **Format**: Status, Context, Decision, Consequences
- **Purpose**: Document why decisions were made, prevent re-litigation

#### Milestones
**Location**: `docs/milestones/`
**Structure**:
- Each milestone has a dedicated document
- Organized into phases: M1a, M1b, M1c, etc.
- Must define acceptance criteria and verification steps
- Must reference relevant ADRs
- **Workflow**: Design → ADRs → Implementation → Milestone Doc → CHANGELOG → PR

#### Documentation Workflow
1. **Design Phase**: Create/update ADRs for architectural decisions
2. **Implementation**: Work in milestone branch, update milestone doc
3. **Validation**: Ensure acceptance criteria met, tests pass
4. **Pre-merge**:
   - Complete milestone documentation
   - Generate CHANGELOG.md from milestone docs
   - Create PR with all updates
5. **Post-merge**: Tag release (v0.x.y), create GitHub Release

### Testing & Validation
**Requirements for Milestone Completion**:
- Automated test coverage >80% for new code
- Manual testing of all new features
- Integration tests for critical paths
- Performance benchmarks meet SLOs
- Security review for sensitive changes
- Documentation complete and reviewed

**Test Directory Guidelines**:
- **ALL tests MUST be in `tests/` directory** - Never create test files in `testing_env/tests/` or any other location
- All test artifacts must be cleaned up after test completion
- Use pytest's `tmp_path` fixture for temporary test directories
- For manual/interactive testing, use `testing_env/tmp/` directory
- Never create test artifacts in the main repository directory
- Integration tests should use `tempfile` or pytest fixtures

**Common Test Issues**:
- **cfg file format**: When tests create cfg files for runner, they should contain only the config portion (e.g., `{"query": "SELECT..."}`) not the full step definition
- **Always run tests**: After any code changes, run `make test` to ensure all tests pass (971+ tests should pass)
- **Skipped tests**: ~43 tests skip due to missing credentials (E2B_API_KEY, MYSQL_PASSWORD) - this is normal
- **Supabase test isolation**: Use `pytest -m supabase` to run only Supabase tests, or `pytest -m "not supabase"` for all others
  - The test suite uses a split-run strategy to prevent cross-contamination
  - Supabase tests complete in <1 second (fully mocked, no network calls)

**IMPORTANT Testing Rules**:
- **Always run osiris.py commands from `testing_env/` directory**: This isolates artifacts and uses proper .env files
  ```bash
  cd testing_env
  python ../osiris.py compile ../docs/examples/mysql_to_supabase_all_tables.yaml
  python ../osiris.py run --last-compile --e2b
  ```
- **NEVER guess or make up secrets/passwords**: Osiris has its own connection management system
  - ❌ WRONG: `MYSQL_PASSWORD=test123 python osiris.py run` (fake password)
  - ✅ RIGHT: Use actual credentials from `.env` file or let Osiris use its `osiris_connections.yaml`
  - Osiris automatically loads connections from `osiris_connections.yaml` and secrets from environment
  - The `testing_env/` directory has pre-configured connections that work with the test environment
- **Secrets must exist in environment**: Either via `.env` file in testing_env/ or exported variables
- **For dry runs**: Use `--dry-run` flag which skips actual database connections

**Secret Scanning (Pre-commit)**:
- Tests with dummy credentials MUST include `# pragma: allowlist secret`
- Do **NOT** bypass detect-secrets via `--no-verify`
- Fix test secrets properly or add pragma comments
- Pre-commit hooks enforce: Black (120 chars), isort, Ruff --exit-zero, detect-secrets
- Use `make commit-wip` to skip Ruff/Bandit for work-in-progress commits
- CI enforces strict checks: Ruff (no fix), Black --check, isort --check, Bandit

**Proactive Lint Suppression - Write Tests Right First Time**:

Add `# noqa` comments immediately when writing code that intentionally violates lint rules. This prevents CI failures and documents intent.

**Common Patterns to Suppress Immediately**:

```python
# 1. Lazy imports for performance (CLI modules, MCP tools)
def my_command():
    import yaml  # noqa: PLC0415  # Lazy import for CLI performance
    from osiris.core.config import load_config  # noqa: PLC0415, I001  # Lazy import

# 2. Imports after setup code (required order)
setup_environment()
from osiris.mcp.server import Server  # noqa: E402  # Must import after setup

# 3. Hardcoded test values (not actual secrets)
def test_connection():
    config = {"password": "test123"}  # pragma: allowlist secret
    conn_str = "mysql://user:pass@localhost"  # nosec B105  # Test fixture, not real password

# 4. Complex CLI router functions (naturally verbose)
def handle_command(args):  # noqa: PLR0915  # CLI router, naturally verbose
    # 60+ lines of argument parsing and delegation

# 5. Known false positives
if "primary" in key and secret == "key":  # nosec B105  # Comparing field name pattern
    pass
```

**When to Add Suppressions**:
- ✅ **While writing code** - If you know the pattern is intentional (lazy imports, test data)
- ✅ **After first lint run** - If Ruff/Bandit flags legitimate code
- ❌ **Don't suppress** - Real bugs, actual complexity that should be refactored

**Common Suppression Codes**:
- `PLC0415` - Import not at top-level (lazy imports)
- `I001` - Import block not sorted (lazy imports in functions)
- `E402` - Module import not at top of file (required initialization order)
- `PLR0915` - Too many statements (>50 lines in function)
- `B105` - Hardcoded password string (false positives on field name comparisons)
- `pragma: allowlist secret` - detect-secrets suppression for test data
- `nosec B105` - Bandit suppression for password false positives

**Pro Tip**: Run `ruff check --output-format=concise .` locally before committing to catch issues early!

**Updating secrets baseline**:
Only run `detect-secrets scan > .secrets.baseline` when:
- Adding test files with new dummy credentials
- Getting persistent false positives
- Before releases to ensure baseline is current
- After removing detected secrets from code

## Version Management

**Current Version**: v0.3.1 (Released 2025-09-27)
**Status**: Production-ready with AIOP for LLM-friendly debugging
**Next Version**: v0.4.0 (planned) - Test infrastructure improvements, DuckDB processor, GraphQL extractor

### Release Process
**⚠️ CRITICAL: The `main` branch is protected - NO direct commits allowed!**
1. Complete milestone in feature branch
2. Update version in pyproject.toml and CHANGELOG.md
3. Create PR to main with all changes
4. After merge: Tag release (`git push origin v0.x.y`) and create GitHub Release

### Current Development Branches
- **`feat/mcp-phase1-cli-bridge`** - MCP v0.5.0 Phase 1 + P0 Bug Fixes ✅ COMPLETE
  - ✅ CLI bridge implementation with subprocess delegation
  - ✅ 10 CLI subcommands for MCP tools
  - ✅ Tool refactoring to eliminate secret access from MCP process
  - ✅ Filesystem contract compliance
  - ✅ Shared helpers module to prevent code duplication
  - ✅ Security fix: Spec-aware secret masking using ComponentRegistry (replaces hardcoded lists)
  - ✅ Component x-secret declarations as single source of truth for secret detection
  - ✅ Resource URI system fully functional (discovery, memory, OML drafts)
  - ✅ **P0 Bug Fixes**: Fixed 14 critical bugs (race conditions, cache, leaks, secrets)
  - 📋 Status: Phase 1 complete + P0 bugs fixed (1177+ tests, 202 MCP tests passing), ready for Phase 2
  - 📦 Latest commit: `d87be06` - "fix(critical): eliminate 14 P0 bugs" (2025-10-16)
- **`debug/codex-test`** - Test infrastructure fixes, E2B parity improvements, DuckDB processor (24 commits, ready for review)
- **`feat/graphql-extractor-component`** - GraphQL API extractor component (1 commit, ready for merge)


## E2B Cloud Execution

Osiris supports transparent execution in E2B cloud sandboxes with full parity to local execution (<1% overhead).

**Basic usage**: `osiris run pipeline.yaml --e2b`

**Architecture**: `E2BTransparentProxy` communicates with `ProxyWorker` inside sandbox via RPC protocol. Auto-installs dependencies, streams verbose output, and collects artifacts.

**Performance**: ~820ms initialization overhead, <10ms per-step RPC overhead.

See `docs/developer-guide/module-remote.md` for detailed E2B architecture and `docs/developer-guide/module-drivers.md` for driver protocol.

## Working with AIOP (AI Operation Package)

AIOP exports structured, LLM-consumable data after every pipeline run (`osiris logs aiop --last`).

### Key Characteristics
- **Enabled by default**: `aiop.enabled: true`
- **Deterministic**: Same inputs → identical outputs
- **Secret-free**: Comprehensive DSN redaction (`scheme://***@host/path`)
- **Size-controlled**: ≤300KB core packages
- **Multi-layered**: Evidence, Semantic, Narrative, Metadata

### Critical Development Rules
1. **Function Signatures**: Never change `build_aiop()`, `export_aiop_auto()`, `calculate_delta()` signatures
2. **Determinism**: Sort JSON keys, use ISO 8601 UTC timestamps, stable evidence IDs: `ev.<type>.<step_id>.<name>.<timestamp_ms>`
3. **Redaction**: Never modify `_redact_connection_string()` without security review; test secrets need `# pragma: allowlist secret`
4. **Config Precedence**: CLI > ENV (`OSIRIS_AIOP_*`) > YAML > defaults
5. **Parity**: Local and E2B must produce identical AIOP structure

### Development Workflow
- Use `mempack.yaml` for AIOP dev work: `python ../osiris.py run --mempack ../tools/mempack/mempack.yaml`
- Test pattern: `python -m pytest tests/core/test_aiop_*.py -v`
- Verify determinism, redaction, and parity for all changes

See `docs/milestones/m2a-aiop.md` and ADR-0027 for complete AIOP specification.

## MCP (Model Context Protocol) Development

Osiris implements MCP v0.5.0 with a **CLI-first security architecture** (ADR-0036) to enable LLM tool integration without exposing secrets to the MCP process.

### Architecture Overview

**Security Model**: The MCP server process **never accesses secrets directly**. All operations requiring credentials delegate to CLI subprocesses via `run_cli_json()`.

```
┌─────────────────┐
│  Claude Desktop │
│   (MCP Client)  │
└────────┬────────┘
         │ stdio
         ▼
┌─────────────────────┐
│   MCP Server        │
│   (osiris/mcp/)     │  ◀── NO SECRET ACCESS
│                     │
│  • Tools delegate   │
│  • Uses CLI bridge  │
└─────────┬───────────┘
          │ subprocess
          ▼
┌─────────────────────┐
│  CLI Subcommands    │
│  (osiris mcp ...)   │  ◀── HAS SECRET ACCESS
│                     │      (inherits env vars)
│  • Connections      │
│  • Discovery        │
│  • OML validation   │
└─────────────────────┘
```

### Critical Development Rules

**1. Code Reuse - NO Duplication**
- MCP commands **MUST** reuse existing CLI logic via shared helpers
- **DO NOT** reimplement functionality in MCP subcommands
- Extract common logic to `osiris/cli/helpers/` modules
- Use thin adapters to transform output schemas when needed

**Example - CORRECT Pattern (Spec-Aware Masking)**:
```python
# osiris/cli/helpers/connection_helpers.py (single source of truth)
def mask_connection_for_display(connection: dict, family: str | None = None) -> dict:
    """Spec-aware masking using component x-secret declarations."""
    # Queries ComponentRegistry for secret fields from spec.yaml
    secret_fields = _get_secret_fields_for_family(family)  # Uses component specs!
    # Automatically detects any field declared in x-secret: [/cangaroo]

# osiris/cli/connections_cmd.py (original CLI command)
from osiris.cli.helpers.connection_helpers import mask_connection_for_display
# Pass family for spec-aware detection
result = mask_connection_for_display(config, family=family)

# osiris/cli/mcp_subcommands/connections_cmds.py (MCP command)
from osiris.cli.helpers.connection_helpers import mask_connection_for_display
# Reuses SAME helper with spec-aware detection
result = mask_connection_for_display(config, family=family)
```

**Example - INCORRECT Pattern** (creates security bugs):
```python
# ❌ WRONG: Hardcoded list, misses custom secret fields
def _sanitize_config(config):
    sensitive_keys = ["password", "secret", "token"]  # Missing "key"! BUG!

# ❌ WRONG: Duplicate implementation in MCP subcommand
def mask_connection(config):
    # Reimplements masking logic instead of using shared helper
```

**2. Secret Masking Requirements - Spec-Aware Approach**
- All connection output **MUST** use `mask_connection_for_display(config, family=family)` from shared helpers
- Secret detection reads `x-secret` declarations from component spec.yaml files (single source of truth)
- Falls back to `COMMON_SECRET_NAMES` for unknown families
- Test both `osiris connections` and `osiris mcp connections` produce identical masking
- Verify no secrets leak in JSON output: `jq '.connections[].config'`
- **How it works**: Component specs declare secrets via JSON pointers (e.g., `x-secret: [/key, /password]`)
- **Future-proof**: Adding `x-secret: [/cangaroo]` to a spec automatically masks that field
- Same pattern as `compiler_v0.py` for consistency across the codebase

**3. MCP Tool Implementation Pattern**
```python
# osiris/mcp/tools/connections.py
from osiris.mcp.cli_bridge import run_cli_json

async def list(self, args: Dict[str, Any]) -> Dict[str, Any]:
    # Delegate to CLI subprocess
    result = await run_cli_json(["mcp", "connections", "list"])
    return result  # CLI already returns MCP-compliant format
```

**4. CLI Subcommand Pattern**
```python
# osiris/cli/mcp_subcommands/connections_cmds.py
from osiris.cli.helpers.connection_helpers import mask_connection_for_display

def connections_list(json_output: bool = False) -> Dict[str, Any]:
    connections = load_connections_yaml()

    # Use shared helper for masking
    masked_config = mask_connection_for_display(config)

    # Format for MCP protocol
    return {
        "connections": formatted,  # Flat array with reference field
        "count": len(formatted),
        "status": "success"
    }
```

### Output Schema Differences

**Original CLI** (`osiris connections list --json`):
- Nested structure: `{session_id, connections: {family: {alias: config}}}`
- Includes session tracking
- Shows environment variable status
- Human-oriented metadata

**MCP Protocol** (`osiris mcp connections list --json`):
- Flat array: `{connections: [{family, alias, reference, config}], count, status}`
- No session_id (stateless)
- Explicit reference field (`@family.alias`)
- Machine-consumable format

Both formats **MUST** use identical secret masking via shared helpers.

### Testing MCP Commands

```bash
# Test both commands produce masked secrets
osiris connections list --json | jq '.connections.supabase.main.config.key'
# Expected: "***MASKED***"

osiris mcp connections list --json | jq '.connections[] | select(.family=="supabase") | .config.key'
# Expected: "***MASKED***"

# Verify no code duplication
grep -r "def mask_connection_for_display" osiris/cli/
# Expected: Only in helpers/connection_helpers.py

# Run MCP-specific tests
pytest tests/mcp/test_no_env_scenario.py -v
pytest tests/mcp/test_tools_connections.py -v
```

### Filesystem Contract

**Base Path Auto-Configuration:**
- `osiris init` automatically sets `filesystem.base_path` to the absolute path of the directory where it's run
- Example: Running `cd testing_env && osiris init` creates `base_path: "/Users/padak/github/osiris/testing_env"`
- This ensures predictable artifact isolation without manual configuration

**MCP Logs** use config-driven paths (not hardcoded):
- Logs: `<base_path>/.osiris/mcp/logs/`
- Audit: `<base_path>/.osiris/mcp/logs/audit/`
- Cache: `<base_path>/.osiris/mcp/logs/cache/`
- Telemetry: `<base_path>/.osiris/mcp/logs/telemetry/`

Configuration precedence: `osiris.yaml` > environment vars > defaults

**Resource URI Structure:**

MCP resources use nested directory structures that match their URI schemes:

- **Discovery Artifacts**: `<cache_dir>/<discovery_id>/overview.json|tables.json|samples.json`
  - URIs: `osiris://mcp/discovery/<discovery_id>/overview.json`
  - Example: `osiris://mcp/discovery/disc_a1b2c3d4e5f6g7h8/overview.json`
  - Resolver maps to: `<base_path>/.osiris/mcp/logs/cache/disc_a1b2c3d4e5f6g7h8/overview.json`
  - Generated by: `osiris mcp discovery run` command
  - Contains: Connection metadata, table schemas, sample data

- **Memory Captures**: `<memory_dir>/sessions/<session_id>.jsonl`
  - URIs: `osiris://mcp/memory/sessions/<session_id>.jsonl`
  - Example: `osiris://mcp/memory/sessions/chat_20251016_143022.jsonl`
  - Resolver maps to: `<base_path>/.osiris/mcp/logs/memory/sessions/chat_20251016_143022.jsonl`
  - Generated by: `osiris mcp memory capture` command
  - Contains: Session traces, decisions, artifacts with PII redaction

- **OML Drafts**: `<cache_dir>/drafts/oml/<filename>.yaml`
  - URIs: `osiris://mcp/drafts/oml/<filename>.yaml`
  - Resolver maps to: `<base_path>/.osiris/mcp/logs/cache/<filename>.yaml`
  - Generated by: `osiris mcp oml save` command
  - Contains: Pipeline YAML drafts

**Important**: File paths MUST match URI structure exactly. The `ResourceResolver._get_physical_path()` strips the `osiris://mcp/<type>/` prefix and appends the remaining path to the appropriate base directory. Mismatched structures will cause resource URIs to return 404 errors.

### Common Pitfalls

❌ **DON'T**: Duplicate secret masking logic
✅ **DO**: Extract to shared helpers

❌ **DON'T**: Import `resolve_connection()` in MCP tools
✅ **DO**: Delegate to CLI subcommands via `run_cli_json()`

❌ **DON'T**: Access environment variables in MCP process
✅ **DO**: Let CLI subprocesses inherit environment

❌ **DON'T**: Reimplement connection loading in MCP
✅ **DO**: Call existing CLI commands and transform output

See `docs/milestones/mcp-finish-plan.md` for complete implementation plan and `docs/adr/0036-mcp-interface.md` for architecture rationale.
