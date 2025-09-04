# Osiris MVP Repository Structure

## Root Level Files

**`osiris.py`** - Main development entry point
- CLI interface for all Osiris commands (`chat`, `init`, `validate`, `run`, `dump-prompts`)
- Renamed from `run_osiris.py` for cleaner command syntax
- **Usage**: `python osiris.py chat` (after activating venv)

**`README.md`** - Project overview and quick start guide
- LLM-first conversational ETL pipeline generator introduction
- Pro mode custom LLM prompts feature documentation
- Setup instructions and basic usage examples

**`CHANGELOG.md`** - Version history and release notes
- Follows Keep a Changelog format with semantic versioning
- Documents all notable changes, additions, and improvements
- Current version: v0.1.0 (initial MVP release)

**`CLAUDE.md`** - AI assistant project instructions
- Claude Code guidance for working with this repository
- Architecture principles, common commands, MVP status warnings
- Pro mode and Rich terminal UI features documented
- Critical for maintaining project consistency

**`requirements.txt`** - Python dependencies
- Core system: `duckdb`, `click`, `pyyaml`, `rich`
- Database connectors: `pymysql`, `sqlalchemy`, `supabase`
- LLM providers: `openai`, `anthropic`, `google-generativeai`

**`Makefile`** - Build and task automation
- Development commands: `make chat`, `make init`, `make validate`
- Testing workflows: `make test`, `make lint`
- Environment management: `make setup`, `make clean`

**`pyproject.toml`** - Modern Python project configuration
- Project metadata, dependencies, build settings
- Tool configuration for black, mypy, pytest
- Replaces traditional setup.py for modern Python packaging

**`setup.py`** - Legacy Python package setup
- Traditional setuptools configuration
- Maintained for backward compatibility with older tools

**`.gitignore`** - Git ignore patterns
- Excludes generated files, caches, and sensitive data
- Testing environment artifacts and virtual environments
- Code quality tool caches (mypy, ruff, pytest)

**`.pre-commit-config.yaml`** - Pre-commit hooks configuration
- Code quality checks: black, isort, ruff, mypy
- Security scanning: detect-secrets, bandit
- File validation: YAML, JSON, TOML syntax checks
- Automated on every git commit

**`.secrets.baseline`** - Detect-secrets baseline file
- Known false positives and approved "secrets"
- Prevents detect-secrets from flagging legitimate patterns
- Maintains consistent secret detection across team

## Documentation (`docs/`)

**`docs/architecture.md`** - Core technical documentation
- System overview, component relationships, data flow
- Progressive discovery process, conversation management
- **Status**: MVP proof-of-concept with warning at top

**`docs/pipeline-format.md`** - OML (Osiris Markup Language) specification
- YAML pipeline format definition (v1.0-MVP)
- Extract/transform/load section structure
- Supabase and MySQL connection examples

**`docs/sql-safety.md`** - SQL injection prevention guide
- Security measures for LLM-generated SQL
- Validation strategies and safety checks

**`docs/archive/`** - Development artifacts
- `component-interfaces.md` - Interface design documentation
- **Purpose**: Historical reference, not user-facing

## Scripts (`scripts/`)

**`scripts/README.md`** - Development and testing scripts guide
- Comprehensive documentation for test_manual_transfer.py
- Usage instructions, configuration options, troubleshooting

**`scripts/test_manual_transfer.py`** - MySQL to Supabase transfer test
- Direct API usage without YAML pipelines
- Auto table detection and creation helper
- Clean SQL generation with `--create-tables` flag
- Enhanced with `auto_create_table` configuration option

**`docs/examples/`** - Example pipelines and usage guide
- **`README.md`** - Example usage instructions
- **`sample_pipeline.yaml`** - Basic pipeline template  
- **`top_customers_revenue.yaml`** - Revenue analysis pipeline

## Testing Environment (`testing_env/`)

**`testing_env/README.md`** - Testing environment guide
- Isolated workspace documentation
- Setup and usage instructions for development testing

**`testing_env/osiris.yaml`** - Development configuration
- Local configuration file for testing
- Database connections and LLM provider settings (git ignored)

**`testing_env/sample_pipeline.yaml`** - Generated test pipeline
- Example output from conversation sessions
- Used for testing pipeline execution

**`testing_env/osiris.log`** - Application logs
- Runtime logs from development sessions
- Debug information and error tracking (git ignored)

## Core Package (`osiris/`)

### Main Package
**`osiris/__init__.py`** - Package exports
- Version info (`1.0.0-mvp`), author, description
- Public API exports (interfaces, implementations, connectors)

### CLI Module (`osiris/cli/`)
**`osiris/cli/__init__.py`** - CLI package exports
**`osiris/cli/main.py`** - Command routing and CLI framework
- Click-based command definitions
- Routes to chat, init, validate, run commands

**`osiris/cli/chat.py`** - Interactive conversational interface
- Main user interaction point
- Manages conversation sessions and AI agent

### Database Connectors (`osiris/connectors/`)

#### MySQL Connector (`osiris/connectors/mysql/`)
**`mysql/__init__.py`** - MySQL connector exports
**`mysql/client.py`** - MySQL connection management
- Connection pooling, credential handling
**`mysql/extractor.py`** - MySQL data extraction
- Table discovery, schema profiling, query execution
**`mysql/writer.py`** - MySQL data loading  
- Insert, upsert, table replacement operations

#### Supabase Connector (`osiris/connectors/supabase/`)
**`supabase/__init__.py`** - Supabase connector exports
**`supabase/client.py`** - Supabase connection management
- Cloud PostgreSQL client wrapper
**`supabase/extractor.py`** - Supabase data extraction
- Remote table discovery and data sampling
**`supabase/writer.py`** - Supabase data loading
- Cloud PostgreSQL write operations
- Enhanced with `auto_create_table` functionality and schema inference
- Automatic timestamp serialization for pandas DataFrames

### Core Engine (`osiris/core/`)

**`osiris/core/__init__.py`** - Core module exports

**`osiris/core/interfaces.py`** - Abstract base classes
- `IStateStore`, `IDiscovery`, `IExtractor`, `ITransformer`, `ILoader`
- `TableInfo`, `Pipeline` data structures
- Enables swappable implementations and easy testing

**`osiris/core/conversational_agent.py`** - Main AI conversation engine
- LLM-powered conversation management
- Intent understanding, database discovery coordination
- Pipeline generation and validation

**`osiris/core/llm_adapter.py`** - Multi-provider LLM interface
- OpenAI GPT-4o, Claude-3 Sonnet, Google Gemini support
- Unified API across different LLM providers
- Provider switching and fallback handling

**`osiris/core/discovery.py`** - Database schema discovery
- Progressive table profiling and schema exploration
- `ExtractorFactory`, `WriterFactory` for connector management
- Intelligent sampling and metadata collection

**`osiris/core/state_store.py`** - Session state management
- SQLite-based conversation state persistence
- Session continuity across chat interactions
- `SQLiteStateStore` implementation

**`osiris/core/config.py`** - Configuration management
- Environment variable handling
- Database connection configuration
- LLM provider settings

**`osiris/core/prompt_manager.py`** - LLM prompt management
- Pro mode custom prompt system
- System prompt export and import functionality
- Template management for conversation, SQL generation, and user context

## Test Suite (`tests/`)

**`tests/__init__.py`** - Test package marker

**`tests/cli/`** - CLI component tests
- `test_chat.py` - Chat interface testing

**`tests/connectors/`** - Database connector tests
- `test_mysql.py` - MySQL connector testing

**`tests/core/`** - Core functionality tests
- `test_conversational_agent.py` - AI conversation engine testing
- `test_discovery.py` - Database discovery testing
- `test_llm_adapter.py` - LLM provider testing
- `test_state_store.py` - State management testing

## Key Architecture Notes

1. **LLM-First Design**: AI drives discovery, SQL generation, and pipeline creation
2. **Modular Connectors**: Easy addition of new database sources
3. **Stateful Sessions**: Conversation context preserved across interactions  
4. **Human Validation**: Expert approval required before pipeline execution
5. **MVP Status**: Working prototype suitable for proof-of-concept usage
