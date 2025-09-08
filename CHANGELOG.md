# Changelog

All notable changes to the Osiris Pipeline project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Runtime Driver Layer** (M1c)
  - New `DriverRegistry` for dynamic driver registration and lookup
  - Concrete drivers: `MySQLExtractorDriver` and `FilesystemCsvWriterDriver`
  - Driver protocol: `run(step_id, config, inputs, ctx) -> dict`
  - Automatic metrics emission: `rows_read` and `rows_written`
  - In-memory result caching for DataFrame passing between steps
  - Foundation for future streaming IO implementation (ADR-0022)

### Changed
- **Component Registry as Single Source of Truth**
  - Removed legacy `COMPONENT_MAP` from compiler completely
  - Runtime exclusively uses ComponentRegistry for component resolution
  - Mode aliasing implemented at compile boundary (read→extract, write→write, transform→transform)
  - Compiler generates manifests with canonical driver names (`mysql.extractor`, `filesystem.csv_writer`)

### Fixed
- **Pipeline Execution Issues**
  - DataFrames now correctly passed between extract and write steps
  - CSV writer produces non-empty files with proper column ordering (lexicographic sort)
  - Manifest dependency ordering corrected - extract steps no longer depend on unrelated previous steps
  - Newline handling in CSV writer fixed (lf/crlf/cr mapping)
  - Connection resolution properly merges into step config as `resolved_connection`

### Added
- **Streaming IO and Spill** (ADR-0022)
  - Iterator-first RowStream interface for memory-safe data processing
  - Support for datasets of 10GB+ without loading into memory
  - Optional spill-to-disk capability with DuckDB temp tables or Parquet files
  - Backward compatibility via DataFrame adapters
  - Progressive data processing with estimated row counts
  - Unified streaming protocol across all extractors and writers

- **Remote Object Store Writers** (ADR-0023)
  - Direct writing to S3, Azure Blob Storage, and Google Cloud Storage
  - Multipart upload support for files >100MB
  - Deterministic CSV contract matching filesystem.csv_writer
  - Connection-based credential management (no secrets in OML)
  - Support for storage classes, tiers, and cloud-specific features
  - Resilient error handling with retry logic and resume capability
  - ADR-0023 now includes comparison table for filesystem vs. remote writers

- **Chat State Machine and OML Synthesis** (ADR-0019)
  - Mandatory FSM flow: INIT → INTENT_CAPTURED → DISCOVERY → OML_SYNTHESIS → VALIDATE_OML → COMPILE → RUN → COMPLETE
  - Hard rule: NO open questions after discovery phase - immediate OML synthesis
  - Strict OML v0.1.0 contract enforcement with required keys `{oml_version, name, steps}`
  - Forbidden legacy keys `{version, connectors, tasks, outputs}` with automatic detection
  - Single regeneration attempt on validation failure with targeted error messages
  - Non-empty assistant message fallback for better user experience
  - Structured event logging for each state transition
  - Post-discovery synthesis ensures deterministic pipeline generation

- **Connection Resolution and Secrets Management** (ADR-0020)
  - External `osiris_connections.yaml` for non-secret connection metadata
  - Environment variable substitution for secrets using `${ENV_VAR}` syntax
  - Connection alias model with family-based organization
  - Default selection precedence: `default:true` → alias named "default" → error
  - Optional OML reference syntax: `config.connection: "@family.alias"`
  - CLI commands: `osiris connections list` (show aliases with masked secrets)
  - CLI commands: `osiris connections doctor` (test connectivity)
  - Complete separation of secrets from pipeline definitions
  - Support for multiple connections per connector family

- CLI `osiris connections list` and `osiris connections doctor` commands with session logging and JSON output.
- Component-level `doctor()` capability (ADR-0021).
- Comprehensive driver unit tests and integration tests for MySQL→CSV pipeline.

- **Registry-First Component Resolution and Mode Aliasing**
  - Removed hardcoded COMPONENT_MAP - Component Registry is now single source of truth
  - Mode aliasing for OML v0.1.0 compatibility: `read` → `extract` at runtime
  - Component mode validation at compile time using registry specs
  - Clear error messages for unsupported modes with allowed alternatives
  - Support for both canonical OML modes {read, write, transform} and component modes
  - Unified environment loading across all commands via `env_loader.py`
  - Runtime safety: empty data from upstream steps triggers clear error
  - Metrics logging: `rows_read` for extractors, `rows_written` for writers
- **Runtime connection resolution integration** (ADR-0020):
  - Runner resolves connections using `resolve_connection()` at step execution
  - Components receive injected connection dicts - no direct ENV access
  - Per-step events: `connection_resolve_start` and `connection_resolve_complete`
  - Connection reference parsing with `@family.alias` format validation
  - Automatic family detection from component names (e.g., `mysql.extractor` → `mysql`)

### Changed
- Clarified ADR-0022: Spill to disk is implementation detail only
- **MySQL/Supabase/DuckDB connectors** now consume injected connections from runner
  - Removed direct environment variable access at runtime
  - All connection data passed via config dict
  - Backward compatibility maintained for testing

### Security
- **Enhanced secrets protection in runner path**:
  - Connection passwords/keys never logged in runner events
  - Automatic redaction of sensitive fields in connection dicts
  - No secrets written to manifest.yaml or config artifacts
  - Connection resolution events log only family and alias names

- **Unified run command with last-compile support**
  - Single `run` command handles both OML and compiled manifests
  - `--last-compile` flag runs most recently compiled manifest
  - `--last-compile-in DIR` finds latest compile in specified directory
  - Pointer files track successful compilations (`.last.json`, `.last_compile.json`)
  - Environment variable fallbacks: `OSIRIS_LAST_MANIFEST`, `OSIRIS_LAST_COMPILE_DIR`
  - Session-based execution with structured logs and artifacts

- **M1c Thin-Slice: Deterministic Compiler and Local Runner** 
  - Minimal OML v0.1.0 to manifest compiler with deterministic output
  - Canonical YAML/JSON serialization with stable key ordering
  - SHA-256 fingerprinting for all compilation inputs/outputs
  - Parameter resolution with precedence: defaults < ENV < profile < CLI
  - Strict no-secrets enforcement (compile error on inline secrets)
  - Local sequential runner for linear pipelines (Supabase → DuckDB → MySQL)
  - CLI commands: `osiris compile` and unified `osiris run`
  - Structured artifacts in session directories `logs/<session>/artifacts/`
  - Example pipeline: `docs/examples/supabase_to_mysql.yaml`
- **Post-generation validation with component spec checks** (M1b.3)
  - Automatic validation of LLM-generated pipelines against component specifications
  - Pipeline validator validates OML against registry specs
  - Friendly error messages using FriendlyErrorMapper from M1a.4
  - Validation events logged to session with attempt tracking
- **Configurable bounded retries, HITL escalation, retry trail artifacts & events**
  - Bounded retry mechanism with configurable attempts (0-5, default 2) per ADR-0013
  - HITL (Human-In-The-Loop) escalation when auto-retries fail, showing retry history
  - Retry counter resets after HITL input for fresh validation cycle
  - Retry trail artifacts saved to session directories for debugging
  - Comprehensive retry trail with events, artifacts, patches, and metrics
- **Validation test harness** (`osiris test validation`)
  - Automated end-to-end testing with scenario-based approach
  - Pre-defined scenarios: valid (passes first try), broken (fixed after retry), unfixable (fails after max attempts)
  - Exit codes: 0 for success scenarios, 1 for unfixable (CI/CD ready)
  - Output structure with result.json, retry_trail.json, and artifacts/ directory
  - Session creation for all test runs with proper event logging
  
### Changed
- **Unified CLI command structure**
  - `run` command now handles both OML compilation and manifest execution
  - All commands use consistent session directories (`logs/<type>_<timestamp>/`)
  - Stdout limited to progress and summary; detailed logs in session files
  - `osiris logs list` shows command type for each session
  - INFO/DEBUG logging redirected from stdout to `logs/<session>/osiris.log`
- **Redaction policy tuned**: Token counts + durations visible; secrets still masked
  - Operational metrics (prompt_tokens, response_tokens, duration_ms) preserved as integers
  - Fingerprints shortened to 8-char prefix
  - Paths converted to repo-relative format
- **CLI logging**: DEBUG to console only with `--log-level DEBUG`
  - Console shows clean output by default
  - DEBUG logs written to session log files
  - Validation error mapping warnings moved to DEBUG level
- Connection JSON output shape: now under `connections` with top-level `session_id`.
- Tests updated to align with the new JSON shape.
- **CLI Framework**: Completely removed Click library dependency, using only Rich framework for all CLI commands.

### Removed
- **`execute` command** - functionality merged into unified `run` command
- **Direct stdout INFO logging** - all detailed logs now in session files

### Fixed
- **Test Suite Improvements**
  - Fixed StateStore → SQLiteStateStore imports in all test files
  - Removed references to non-existent methods (_get_database_tables, context_manager)
  - Updated CLI test to check for --last-compile instead of deprecated --dry-run
  - Fixed session logging imports (get_session_context → get_current_session)
  - Added pragma comments for test-only credentials to pass secret scanning
  - All 27 tests now passing successfully

- **Over-masking of event names/session ids**
  - Session IDs and event names no longer masked in logs
  - Only actual secrets are redacted
  - STRUCTURAL_KEYS whitelist prevents operational data masking
- **Context builder console noise**
  - Clean output by default, verbose logging only with --log-level DEBUG
- **Test harness issues**
  - Exit codes now correctly return 1 for failed scenarios
  - --max-attempts parameter properly limits total attempts
  - Artifacts consistently saved to --out directory with proper structure
- Supabase health check avoids 404s, uses `/auth/v1/health` with fallback.
- Secrets redacted consistently in `connections` CLI outputs.

### Previously Added Features (M1a-M1b.2)
- Component Registry backend (`osiris/components/registry.py`) with mtime-based caching and three validation levels (basic/enhanced/strict)
- Session-aware `osiris components validate` command with structured event logging (run_start, component_validation_start/complete, run_end)
- CLI flags for component validation: `--session-id`, `--logs-dir`, `--log-level`, `--events`, `--level`, `--json`
- Session ID wrapping in `osiris logs list` for full copy/paste capability with `--no-wrap` flag for legacy behavior
- Component management CLI commands: `osiris components list`, `show`, `validate`, `config-example`, `discover`
- Component specification schema (JSON Schema Draft 2020-12) for self-describing components
- Bootstrap component specs for MySQL and Supabase extractors/writers
- Migration guide for 'load' to 'write' mode transition
- Comprehensive test suites for component specifications and registry (`tests/components/test_registry.py`, `test_registry_cli_logging.py`)
- CLI displays both required configuration and secrets for components
- **Friendly Error Mapper**: Transforms technical validation errors into human-readable messages with fix suggestions
- **JSON output for components list**: `osiris components list --json` outputs machine-readable JSON array
- Path-to-label mapping for common configuration fields (e.g., "/configSchema/properties/host" → "Database Host")
- Error categorization system (config_error, type_error, constraint_error, etc.) with contextual examples
- Verbose mode (`--verbose`) for components validate to show technical error details
- **Context Builder for LLM** (M1b.1): Minimal component context export for token-efficient LLM consumption
  - JSON schema for context format (`osiris/prompts/context.schema.json`)
  - Context builder implementation with SHA-256 fingerprinting and disk caching (`osiris/prompts/build_context.py`)
  - CLI command: `osiris prompts build-context [--out FILE] [--force] [--session-id ID] [--logs-dir DIR] [--json]`
  - Session-aware logging with structured events (`context_build_start`, `context_build_complete`)
  - Session management CLI flags match other commands (precedence: CLI > ENV > YAML > defaults)
  - Automatic cache invalidation on component spec changes (mtime + fingerprint + filter version)
  - **NO-SECRETS guarantee**: Secret fields excluded, suspicious values redacted (passwords, tokens, keys, etc.)
  - Compact JSON serialization optimized for tokens (~330 tokens for 4 components)
  - Comprehensive test coverage including secret filtering tests
- **LLM Context Integration** (M1b.2): Automatic component context injection into all LLM requests
  - Extended PromptManager with context loading, caching, and injection
  - Context injection into chat CLI with flags: `--context-file`, `--no-context`, `--context-strategy`, `--context-components`
- **Automated Validation Test Harness** (M1b.3): CLI tool for end-to-end validation testing with scenario-based approach
  - Command: `osiris test validation [--scenario valid|broken|unfixable|all] [--out DIR] [--max-attempts N]`
  - Pre-defined scenarios: valid (passes first try), broken (fixed after retry), unfixable (fails after max attempts)
  - Test harness module (`osiris/core/test_harness.py`) with structured artifact generation
  - Comprehensive pytest tests (`tests/test_validation_harness.py`) for automated verification
  - Rich terminal output with validation attempt summary tables
  - JSON result artifacts with `return_code` field and retry history
  - Enhanced `retry_trail.json` schema with `valid` boolean, error metrics, and token usage per attempt
  - Scenario fixtures in `tests/scenarios/` for reproducible testing
  - Works correctly from any directory including `testing_env/`
  - Token usage tracking and reporting in chat responses
  - Component-scoped context filtering for targeted prompts
  - Session event logging for context operations
- **Relaxed Log Redaction Policy**: Operational metrics visible while secrets remain masked
  - Privacy levels: `--privacy standard|strict` flag in chat CLI
  - Numeric metrics preserved as integers (prompt_tokens, response_tokens, duration_ms, etc.)
  - Fingerprints shortened to 8-char prefix with `...`
  - Paths converted to repo-relative format
  - Cache keys no longer treated as secrets

### Changed
- Log redaction system completely rewritten with configurable privacy levels
- SessionContext now uses advanced redaction with better granularity
- Event payloads now show concrete numbers for token counts and durations
- Fingerprints and hashes are partially revealed instead of fully masked
- **BREAKING**: Supabase components now require `key` field (was optional)
- Standardized on 'write' mode for data writing operations ('load' deprecated)
- Component capabilities updated to reflect actual implementation

### Fixed
- Context builder now guarantees no secrets in exported JSON (M1b.1)
- Session-aware logging properly tracks ephemeral sessions for prompts commands
- Writers now support 'discover' mode for target schema inspection
- CLI enhanced to show secrets and required config in property order
- Component validation now creates session logs with proper status tracking (completed/failed)
- **Components validate default output**: Now shows friendly, actionable error messages instead of technical JSON Schema errors
- Registry validation returns structured errors with both friendly and technical information
- Session events now include `friendly_errors` field for improved debugging

### Fixed
- Duplicate validation events eliminated - Registry and CLI no longer emit redundant events
- Session status now correctly shows "completed" or "failed" instead of "unknown"
- Component CLI path resolution works from any directory
- JSON Schema validation for component specs
- Capabilities now accurately reflect implementation (e.g., Supabase doesn't support adHocAnalytics)

### Deprecated
- 'load' mode for writers (use 'write' instead) - will be removed in v2.0.0

## [0.1.2] - 2025-09-02

### Added
- Session-scoped logging with per-session directories, structured JSONL events, metrics, and dual artifact storage (`output/` + `logs/<session>/artifacts/`).
- Session management CLI commands: `osiris logs list`, `show`, `bundle`, `gc`.
- Discovery cache fingerprinting with SHA-256 invalidation, component/version awareness, and TTL support.
- Connection validation with JSON Schema for MySQL and Supabase, supporting modes `off`, `warn`, `strict`.
- Configuration precedence system (CLI → ENV → YAML → defaults) with wildcard `*` event logging and effective config reporting.
- Test infrastructure for M0-Validation-4 (pytest suite + manual runner).

### Changed
- Session artifacts now stored under session directories.
- Cache storage enhanced with fingerprint metadata.
- Logging architecture moved from global to session-scoped.
- Error handling improved with fallback to temp directories.

### Fixed
- Pipeline YAML artifacts saved correctly to both `output/` and session directories.
- Validate command now respects configured log levels.
- Cache context mismatch resolved by fingerprinting.
- CLI parsing fixed to support both `--mode strict` and `--mode=strict`.

### Security
- Secrets masking: passwords, tokens, API keys redacted as `***` in logs, YAML, and artifacts.
- Explicit allowlist for test-only credentials.
- Pre-commit secret scanning enabled for all commits.

## [0.1.1] - 2025-08-30

### Added
- **Global JSON Output Support**: All CLI commands now support `--json` flag for programmatic access
- **Comprehensive Help System**: All commands support `--help` with JSON output option
- **Environment Variable Loading**: Fixed validate command to properly load `.env` files
- **Test Coverage**: Added comprehensive test suite for CLI command functionality

### Fixed
- **Environment Loading Bug**: Validate command now correctly loads environment variables from `.env` files
- **Help System**: Fixed argument passing to allow `--help` to reach all subcommands
- **JSON Consistency**: Ensured consistent JSON structure across all command outputs

### Changed
- **CLI Interface**: Added global `--json` flag that works with all commands
- **Error Handling**: Improved SystemExit handling in tests using contextlib.suppress
- **Code Quality**: Fixed linting issues for boolean comparisons and exception handling

## [0.1.0] - 2025-08-29

### Added
- **Conversational ETL Pipeline Generator**: LLM-first approach to pipeline creation through natural language
- **Multi-Database Support**: MySQL, Supabase (PostgreSQL), and CSV file processing
- **AI Chat Interface**: Interactive conversational mode for pipeline development
- **Pro Mode**: Custom LLM prompt system for domain-specific adaptations
- **Rich Terminal UI**: Beautiful formatted output with colors, tables, and progress indicators
- **Human-in-the-Loop Validation**: Manual approval required before pipeline execution
- **YAML Pipeline Format**: Structured, reusable pipeline configuration
- **Database Discovery**: Intelligent schema exploration and progressive profiling
- **SQL Safety**: Context-aware SQL validation and injection prevention
- **Session Management**: SQLite-based conversation state persistence
- **Testing Environment**: Isolated workspace for development and testing
- **Comprehensive Documentation**: Architecture, examples, and usage guides
- **Development Workflow**: Pre-commit hooks, linting, type checking, and testing
- **Multi-LLM Provider Support**: OpenAI GPT-4o, Claude-3 Sonnet, Gemini integration

### Core Components
- **Conversational Agent**: Main AI conversation engine
- **LLM Adapter**: Multi-provider interface for AI models
- **Database Discovery**: Progressive schema profiling system
- **State Store**: SQLite-based session persistence
- **Rich CLI**: Command-line interface with beautiful formatting
- **MySQL Connector**: Full MySQL/MariaDB support with connection pooling
- **Supabase Connector**: Cloud PostgreSQL integration

### Documentation
- Project architecture and component documentation
- Repository structure and file organization guide
- Pipeline format specification (OML - Osiris Markup Language)
- SQL safety and security guidelines
- Example pipelines and usage guides
- Development and testing procedures

### Initial Release Notes
This is the first MVP release of Osiris Pipeline - an experimental proof-of-concept demonstrating LLM-first ETL pipeline generation. The system successfully generates pipelines through natural language conversation, discovers database schemas intelligently, and provides human validation before execution.

**Status**: Early prototype suitable for demonstration and initial testing
**Confidence**: Core functionality working with movies database testing completed

[0.1.2]: https://github.com/keboola/osiris_pipeline/releases/tag/v0.1.2
[0.1.1]: https://github.com/keboola/osiris_pipeline/releases/tag/v0.1.1
[0.1.0]: https://github.com/keboola/osiris_pipeline/releases/tag/v0.1.0
