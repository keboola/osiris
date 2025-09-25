# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Osiris MVP is an **LLM-first conversational ETL pipeline generator**. It uses AI conversation to understand user intent, discover database schemas, generate SQL, and create YAML pipelines. This is an **agentic AI system** that replaces traditional template-based approaches with intelligent conversation.

### Project Status (January 2025)
- **✅ v0.2.0 Released**: Complete M1 implementation with all features production-ready
- **✅ E2B Integration**: Full parity with local execution, <1% overhead
- **✅ Component Registry**: Self-describing components with JSON Schema validation
- **✅ Rich CLI**: Beautiful terminal output with tables, colors, and progress indicators
- **✅ Documentation**: Fully comprehensive with no TODOs remaining
  - Complete user guide with troubleshooting and best practices
  - Developer guide covering all 7 core modules
  - LLM contracts for AI-assisted development
  - Architecture diagrams with layered detail levels
- **✅ M2a AIOP Complete**: AI Operation Package for LLM consumption
  - Evidence, Semantic, Narrative, and Metadata layers
  - JSON and Markdown export formats
  - Truncation and annex policies for large runs
  - Secret redaction and deterministic output
- **📊 Implementation**: 33 ADRs documenting all design decisions
- **🧪 Testing**: 700+ tests passing (including AIOP integration tests)
- **🚀 Next**: M2 (Scheduling), M3 (Scale), M4 (DWH Agent)

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
   
   # Initialize Osiris configuration
   python osiris.py init
   ```

## Common Commands

### Running Osiris
**IMPORTANT**: Always activate virtual environment first: `source .venv/bin/activate`

**RECOMMENDED**: Use Makefile commands to run from `testing_env/` and isolate artifacts:

```bash
# Main conversational interface (recommended)
make chat

# Initialize configuration
make init

# Validate configuration
make validate

# Session log management  
osiris logs list           # List all sessions
osiris logs show --session <id>  # Show session details
osiris logs gc             # Cleanup old sessions

# Run sample pipeline
make run-sample

# Run pipeline in E2B cloud sandbox
osiris run pipeline.yaml --e2b
osiris run pipeline.yaml --target e2b --timeout 1200

# Export system prompts for customization (pro mode)
make dump-prompts

# Use custom prompts
make chat-pro
```

**Direct usage** (creates artifacts in current directory):
```bash
# Main conversational interface (direct)
python osiris.py chat

# Initialize configuration
python osiris.py init

# Validate configuration
python osiris.py validate

# Session log management
python osiris.py logs list              # List all sessions  
python osiris.py logs show --session <id>  # Show session details
python osiris.py logs gc                # Cleanup old sessions

# Export system prompts for customization (pro mode)
python osiris.py dump-prompts --export

# Use custom prompts
python osiris.py chat --pro-mode
```

### Development Commands
```bash
# Always activate venv first: source .venv/bin/activate

# Modern development workflow (RECOMMENDED)
make dev                    # Full dev setup: install deps + pre-commit
make pre-commit            # Run all quality checks
make test                  # Run tests
make format                # Format code (black + isort)
make lint                  # Lint code (ruff)
make type-check            # Type check (mypy)
make secrets-check         # Check for secrets
make clean                 # Clean build artifacts

# Pre-commit hooks (automatically run on git commit)
make pre-commit-install    # Install pre-commit hooks
make pre-commit-run        # Run hooks manually
make pre-commit-all        # Run hooks on all files

# Traditional commands (still supported)
python -m pytest tests/
black osiris/
mypy osiris/
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

### Architecture Decisions
- **`docs/adr/`** - 33 Architecture Decision Records
- **`docs/roadmap/`** - Future milestones (M2, M3, M4)
- **`docs/examples/`** - Sample pipelines

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

### Key Principles

1. **LLM-First**: AI handles discovery, SQL generation, and pipeline creation
2. **Conversational**: Natural language interaction guides the entire process
3. **Human Validation**: Expert approval required before pipeline execution
4. **Progressive Discovery**: AI explores database schema intelligently
5. **Stateful Sessions**: Context preserved across conversation turns

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
export MYSQL_PASSWORD="your-password"
osiris run pipeline.yaml

# Option 2: Use .env file
echo "MYSQL_PASSWORD=your-password" > .env
osiris run pipeline.yaml

# Option 3: Inline for single command
MYSQL_PASSWORD="your-password" osiris run pipeline.yaml
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

**LLM Providers:**
- `openai` - GPT-4o, GPT-4 models
- `anthropic` - Claude-3.5 Sonnet  
- `google-generativeai` - Gemini models

## How It Works

1. **User starts conversation**: `python osiris.py chat` (creates session with structured logging)
2. **AI discovers database**: Automatically profiles tables and schemas (cached with fingerprinting)
3. **User describes intent**: "Show me top customers by revenue"
4. **AI generates pipeline**: Creates complete YAML pipeline displayed in terminal
5. **Pipeline saved**: Automatically saved to output/ directory and session artifacts
6. **Human validates**: Reviews pipeline YAML before execution
7. **Optional execution**: User can approve pipeline for execution

## Pro Mode - Custom LLM Prompts

Osiris includes a powerful **pro mode** that allows advanced users to customize the LLM system prompts. Features beautiful Rich terminal formatting with colors, tables, and progress indicators:

### Usage
```bash
# Export current system prompts for customization
python osiris.py dump-prompts --export

# Edit the exported prompts in .osiris_prompts/
# - conversation_system.txt    # Main LLM personality & behavior
# - sql_generation_system.txt  # SQL generation instructions
# - user_prompt_template.txt   # User context building template

# Use your custom prompts
python osiris.py chat --pro-mode
```

### Benefits
- **🎯 Domain Customization**: Adapt for finance, healthcare, retail, etc.
- **🧪 Experimentation**: Test different prompting strategies
- **🐛 Debugging**: See exact instructions sent to LLMs  
- **⚡ Performance**: Fine-tune for better response quality
- **🔧 Advanced Control**: Complete control over AI behavior

### Use Cases
- **Industry-specific terminology**: Customize prompts for your domain
- **Response style**: Make Osiris more technical, concise, or detailed
- **Workflow optimization**: Adjust for specific data analysis patterns
- **Multi-language support**: Adapt prompts for different languages

## Development Workflow & Branch Strategy

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
- All test artifacts must be cleaned up after test completion
- Use pytest's `tmp_path` fixture for temporary test directories
- For manual/interactive testing, use `testing_env/tmp/` directory
- Never create test artifacts in the main repository directory
- Integration tests should use `tempfile` or pytest fixtures

**IMPORTANT Testing Rules**:
- **Always run osiris.py commands from `testing_env/` directory**: This isolates artifacts and uses proper .env files
  ```bash
  cd testing_env
  python ../osiris.py compile ../docs/examples/mysql_to_supabase_all_tables.yaml
  python ../osiris.py run --last-compile --e2b
  ```
- **NEVER guess or make up secrets/passwords**: Always use actual values from .env files or environment
  - ❌ WRONG: `MYSQL_PASSWORD=test123 python osiris.py run`
  - ✅ RIGHT: Use actual password from `.env` file or export real value
- **Secrets must exist in environment**: Either via `.env` file in testing_env/ or exported variables

**Secret Scanning (Pre-commit)**:
- Tests with dummy credentials MUST include `# pragma: allowlist secret`
- Do **NOT** bypass detect-secrets via `--no-verify`
- Fix test secrets properly or add pragma comments
- Pre-commit hooks enforce: secrets detection, black formatting, ruff linting
- All hooks must pass before commit (no exceptions for production code)

## Version Management

**Current Version**: v0.2.0 (Milestone M1 - Component Registry and Runner)
**Branch**: milestone-m1 (ready to merge to main)

### Release Process
1. **Complete milestone** in feature branch
2. **Update version** in README.md and pyproject.toml
3. **Update CHANGELOG.md** following [Keep a Changelog](https://keepachangelog.com) format
4. **Create PR** to main with all changes
5. **After merge**: Tag release (v0.x.y) and create GitHub Release
6. **Document** release notes from CHANGELOG in GitHub Release

## Project Version

**Current Version**: v0.2.0 (Released 2025-09-22)
**Status**: Production-ready for core features
**Branch**: main

## MVP Status

Osiris v0.2.0 is a **production-ready system** for LLM-first pipeline generation. Core conversational AI, database discovery, component registry, and both local/E2B execution are fully functional and tested.

## Current Development Context

### M2a AIOP Milestone (January 2025) - COMPLETED ✅
- **✅ AI Operation Package Implementation**:
  - PR1-PR2: Evidence Layer with timeline, metrics, errors, artifacts
  - PR3: Semantic/Ontology Layer with DAG, components, OML spec
  - PR4: Narrative Layer with natural language descriptions and citations
  - PR5: CLI Parity & Hardening with truncation, redaction, exit codes
  - PR6: Documentation & Polish with examples, tests, and optimizations
  - **Result**: Complete AIOP export functionality for AI debugging and analysis

- **✅ Key AIOP Features Delivered**:
  - Deterministic JSON-LD output with stable IDs
  - Automatic secret redaction (DSN masking with ***)
  - Size-controlled exports with object-level truncation markers
  - Annex policy for large runs with NDJSON shards
  - Configuration precedence: CLI > ENV > YAML > defaults
  - Markdown run-cards for human review
  - Rich progress indicators during export
  - LRU caching and streaming JSON for performance

### Documentation Completion (January 2025) - COMPLETED ✅
- **✅ Comprehensive Documentation Structure**:
  - Rewrote overview.md as non-technical introduction
  - Created quickstart.md for 5-minute onboarding
  - Consolidated user-guide.md with troubleshooting and best practices
  - Added log interpretation and common issues sections
  - Created 7 module documentation files for developers
  - Added 4 specialized LLM contracts for AI development
  - Moved technical diagrams to architecture.md
  - Created layered Conversational Agent diagrams (7 focused views)
  - Archived all historical/incomplete documentation
  - **Result**: Zero TODOs remaining in documentation

- **✅ ADR Status Normalization**:
  - 26 ADRs reviewed and status updated
  - 14 ADRs marked as Implemented
  - 7 ADRs marked as Accepted (partial implementation)
  - 4 ADRs remain Proposed
  - 1 ADR marked Superseded (ADR-0010 by ADR-0026)

- **✅ Future Planning Documentation**:
  - ADR-0027: Run Export Context for AI (AI-friendly analysis)
  - ADR-0028: Git Integration (reproducible environments)
  - ADR-0029: Memory Store (persistent knowledge base)
  - ADR-0030: Agentic OML Generation (improved LLM quality)
  - Milestone M2: Scheduling & Planning
  - Milestone M3: Technical Scale & Performance
  - Milestone M4: Data Warehouse Agent

### M1f Status (January 2025) - COMPLETED ✅
- **✅ E2B Transparent Proxy Architecture** (ADR-0026):
  - Complete redesign eliminating E2BPack in favor of transparent proxy approach
  - New `E2BTransparentProxy` class replacing legacy `E2BAdapter` and `PayloadBuilder`
  - `ProxyWorker` for remote execution in E2B sandbox environment
  - RPC protocol for bidirectional communication between proxy and worker
  - Full parity between local and E2B execution paths (<1% performance overhead)
  - Identical log structure and artifact layout across environments
  - Support for verbose output passthrough from E2B sandbox
  - Heartbeat mechanism for long-running operations

- **✅ ExecutionAdapter Pattern**:
  - Abstract base class defining three-phase execution: prepare() → execute() → collect()
  - `LocalAdapter` for local execution with native driver support
  - `E2BTransparentProxy` for remote execution maintaining full compatibility
  - Unified `ExecutionContext` for session and artifact management
  - `PreparedRun` dataclass for deterministic execution packages
  - Factory pattern (`get_execution_adapter`) for runtime adapter selection

- **✅ Test Suite Modernization**:
  - Fixed 91 failing tests → now 694 passing
  - Removed 18 obsolete test files for deleted components
  - Added comprehensive parity testing between local and E2B execution
  - Fixed mock directory pollution in repository root

### M1c Status (December 2024) - COMPLETED ✅
- **✅ Chat FSM & OML Rules** (ADR-0019):
  - Mandatory state machine: INIT → INTENT_CAPTURED → (optional) DISCOVERY → OML_SYNTHESIS → VALIDATE_OML → (optional) REGENERATE_ONCE → COMPILE → (optional) RUN → COMPLETE
  - After DISCOVERY: **NO open questions** - always synthesize OML immediately
  - OML v0.1.0 strict contract: required keys `{oml_version:"0.1.0", name, steps}`; forbidden `{version, connectors, tasks, outputs}`
  - Validation with one targeted regeneration attempt; fallback to concise HITL error
  - Never emit empty assistant messages; log structured events for each state transition

- **✅ Connections & Secrets** (ADR-0020):
  - Secrets kept out of OML - use `osiris_connections.yaml` for non-secrets
  - Environment variables for secrets: `${ENV_VAR}` substitution from `.env`
  - Optional OML reference: `config.connection: "@<family>.<alias>"`
  - Default selection precedence: `default:true` → alias named `default` → error
  - CLI commands (M1c): `osiris connections list`, `osiris connections doctor`
  - Connection wizard `connections add` deferred to M1d

- **✅ Golden Path Demo Ready**:
  - MySQL → Supabase pipeline (no scheduler)
  - Complete flow: chat → OML v0.1.0 → compile → run
  - E2B path functional with hardened Supabase writer

### Recent Improvements (v0.2.0)
- **✅ HTML Report Enhancements**: Visual badges (E2B orange, Local grey) for execution environment
- **✅ E2B Bootstrap Time**: New performance metric showing sandbox initialization overhead
- **✅ Data Volume Fix**: Single source of truth for row totals (cleanup_complete > writers > extractors)
- **✅ Total Step Time**: Fixed aggregation showing accurate execution metrics
- **✅ Scroll Indicator**: Visual UX improvement for overflowing content in Overview tab
- **✅ Connection Aliases**: E2B runs now correctly display connection references (@mysql.db_movies)
- **✅ Session Reader**: Fixed OML version and pipeline name extraction from events
- **✅ Verbose Streaming**: Local execution now streams events in real-time matching E2B behavior

### Previous Improvements (v0.1.2)
- **✅ Discovery cache fingerprinting**: SHA-256 fingerprinting eliminates stale cache reuse (M0 complete)
- **✅ Basic connection validation**: JSON Schema validation for connection configurations
- **✅ Validation modes**: `--mode warn|strict|off` with ENV override support (`OSIRIS_VALIDATION`)
- **✅ Cache invalidation**: Automatic cache refresh on options or spec changes
- **✅ Rollback mechanism**: `OSIRIS_VALIDATION=off` for emergency bypass
- **✅ Unified environment loading**: Consistent .env loading across all commands
- **✅ Runtime env resolution**: Clear errors for missing/empty environment variables

### Previous Release (v0.1.1)
- **✅ Session-scoped logging system**: Complete structured logging with events.jsonl, metrics.jsonl, and artifacts
- **✅ Pipeline generation bug fixes**: Fixed display and saving of generated YAML pipelines  
- **✅ Secrets masking**: Automatic detection and masking of sensitive data in logs
- **✅ Event filtering**: Configurable event logging with wildcard support (`"*"`)
- **✅ Configuration precedence**: Proper YAML → ENV → CLI override handling
- **✅ CLI log management**: `osiris logs list/show/gc` commands for session management

### Known Architecture Issues
- **Multi-database support**: Connection aliases partially address this (ADR-0020)
- **LLM error handling**: Improved with non-empty fallback messages (ADR-0019)
- **Component specs missing**: Need self-describing components for better validation

### Next Steps (v0.3.0+)
- **M2**: Scheduling & Planning Enhancements
  - OML schedule block with cron expressions
  - Pipeline metadata (owner, SLA, lineage)
  - Orchestrator integration (Airflow, Prefect)
  - Production validation framework
- **M3**: Technical Scale & Performance
  - Streaming IO with RowStream interface
  - DAG parallel execution
  - Observability integration (Datadog, OpenTelemetry)
  - Distributed execution support
- **M4**: Data Warehouse Agent & Persistence
  - Apache Iceberg writer
  - Intelligent DWH management agent
  - MotherDuck/Snowflake/BigQuery integration
  - Data versioning and time travel

### Milestone Guardrails (M1c)
**Golden Path Demo**:
- MySQL → Supabase (no scheduler)
- Complete flow: chat → OML v0.1.0 → compile → run
- Must work end-to-end without manual intervention

**Acceptance Criteria**:
- All tests green (`pytest -q`)
- `osiris connections list` shows aliases with masked secrets
- `osiris connections doctor` validates connectivity
- E2B path functional: compile + run produces expected outputs
- NO secrets in OML files or compilation artifacts
- Post-discovery: NO open questions to user

### Key Documentation
- `docs/overview.md` - System architecture and conceptual flow
- `docs/adr/` - Architecture Decision Records (30 ADRs documenting all design decisions)
- `docs/milestones/` - Implementation milestone documentation (M0-M4 planned)
- `docs/user-guide/` - User documentation (kickstart, how-to, crashcourse)
- `docs/developer-guide/` - Developer documentation (components, adapters, extending, discovery)
- `docs/developer-guide/llms.txt` - Machine-readable instructions for LLMs
- **Test credentials**: Use `# pragma: allowlist secret` to bypass pre-commit secret scanning for test-only credentials

## E2B Cloud Execution

Osiris supports transparent execution in E2B cloud sandboxes, providing identical behavior to local execution with added isolation and scalability.

### E2B Execution Features
- **Full Parity**: Identical execution behavior between local and E2B environments
- **Transparent Proxy**: Seamless communication between local orchestrator and remote sandbox
- **Auto-dependency Installation**: Missing Python packages installed automatically in sandbox
- **Verbose Output**: Real-time streaming of execution progress from sandbox
- **Artifact Collection**: Automatic retrieval of generated files and logs

### E2B Command Line Options
```bash
# Execute in E2B sandbox
osiris run pipeline.yaml --e2b

# With custom resources
osiris run pipeline.yaml --target e2b --cpu 4 --memory-gb 8 --timeout 1800

# Pass environment variables
osiris run pipeline.yaml --e2b \
  --e2b-env MYSQL_PASSWORD=secret \
  --e2b-pass-env SUPABASE_KEY

# Auto-install missing dependencies
osiris run pipeline.yaml --e2b --e2b-install-deps

# Dry run to see configuration
osiris run pipeline.yaml --e2b --dry-run
```

### E2B Architecture
1. **Local Orchestrator**: Manages execution lifecycle and prepares execution package
2. **E2BTransparentProxy**: Handles sandbox creation, communication, and artifact collection
3. **ProxyWorker**: Runs inside sandbox, executes pipeline steps using drivers
4. **RPC Protocol**: Ensures reliable bidirectional communication with heartbeats

### Performance Characteristics
- **Initialization**: ~820ms one-time sandbox creation overhead
- **Per-step overhead**: <10ms for RPC communication
- **Total impact**: <1% for typical pipelines
- **Memory usage**: Identical to local execution

## Runtime Driver Layer

Osiris uses a driver-based architecture for executing pipeline steps. This design provides clean separation between component specifications and runtime execution.

### Driver Interface
- **Location**: `osiris/core/driver.py`
- **Protocol**: `run(step_id: str, config: dict, inputs: dict | None, ctx: Any) -> dict`
  - `step_id`: Identifier of the step being executed
  - `config`: Step configuration including resolved connections
  - `inputs`: Input data from upstream steps (e.g., `{"df": DataFrame}`)
  - `ctx`: Execution context for logging metrics
  - Returns: Output data (`{"df": DataFrame}` for extractors/transforms, `{}` for writers)
- **Registry**: `DriverRegistry` manages driver registration and lookup
  - Single source of truth - **COMPONENT_MAP is completely removed**
  - Dynamic registration at runtime startup
  - Clear error messages for missing drivers

### Concrete Drivers
- **MySQL Extractor** (`osiris/drivers/mysql_extractor_driver.py`): 
  - Executes SQL queries via SQLAlchemy/pandas
  - Returns `{"df": DataFrame}`
  - Automatically logs `rows_read` metric
  - Uses `resolved_connection` from config for credentials
  
- **Filesystem CSV Writer** (`osiris/drivers/filesystem_csv_writer_driver.py`):
  - Writes DataFrames to CSV files with deterministic output
  - Sorts columns lexicographically for reproducibility
  - Expects `{"df": DataFrame}` in inputs (error if missing)
  - Automatically logs `rows_written` metric
  - Handles newline mappings: `lf`→`\n`, `crlf`→`\r\n`, `cr`→`\r`

### Canonical Modes
Mode aliasing ensures OML compatibility with driver implementations:
- **OML Mode** → **Component Mode**
- `read` → `extract`
- `write` → `write` 
- `transform` → `transform`

Aliasing is applied at compile time by the compiler, manifests contain canonical modes.

### Execution Flow
1. Runner builds DriverRegistry at startup with all available drivers
2. For each step in manifest, driver is retrieved by name (e.g., "mysql.extractor")
3. Connection resolution merges into config as `resolved_connection`
4. Driver executes with appropriate inputs from upstream steps (via in-memory cache)
5. Extract/transform results cached as `{"df": DataFrame}` for downstream consumption
6. Metrics (`rows_read`, `rows_written`) automatically logged to session events

### Key Design Decisions
- **No hardcoded mappings**: Component Registry is the single source of truth
- **Protocol-based**: Drivers follow a simple protocol, easy to extend
- **Metrics built-in**: Data flow metrics emitted automatically
- **Memory-efficient**: Foundation for future streaming IO (ADR-0022)
- **Deterministic**: CSV outputs are reproducible (sorted columns, consistent formatting)
