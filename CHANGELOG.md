# Changelog

All notable changes to the Osiris Pipeline project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Milestone M2a - AI Operation Package (AIOP)** planning document
  - Comprehensive implementation plan for ADR-0027
  - JSON-LD based semantic export format for LLM consumption
  - Three-layer architecture: Narrative, Semantic, Evidence
  - CLI command specification: `osiris logs aiop`
  - Deterministic, secret-free export with size controls

## [0.2.0] - 2025-01-23

**Major Release: Milestone M1 - Component Registry and Runner**

This release represents a complete architectural overhaul with the implementation of the Component Registry system, unified runtime, E2B Transparent Proxy, and comprehensive tooling for data engineers. The system now provides full parity between local and E2B execution with production-ready logging, validation, and error handling.

### Documentation (2025-01-23)
- **Comprehensive Documentation Overhaul**
  - Eliminated all TODOs (50+ → 0) across documentation
  - Created quickstart.md for 10-minute onboarding experience
  - Consolidated 3 user guides into single comprehensive user-guide.md
  - Added complete log interpretation guide with troubleshooting
  - Created 7 module documentation files covering all core modules
  - Added specialized LLM contracts for drivers, CLI, and testing
  - Updated overview.md with executive positioning and value proposition
  - Fixed architecture.md version discrepancies (v0.1.2 → v0.2.0)
  - Created 7 layered architecture diagrams for better readability
  - Archived 16+ obsolete milestone documents
  - Updated all ADRs with implementation status
  - Added screenshots to README showcasing HTML reports
  - Simplified README to avoid duplication, added LLM-friendly documentation section
  - Updated docs/README.md as comprehensive documentation hub

### Upgrade notes
- **Breaking**: Supabase writers now require `key` field (was optional). **Action**: Add `key` to Supabase connection config.
- **Deprecated**: `load` mode → use `write`. **Action**: Update OML/manifests accordingly.
- **Note**: ExecutionAdapter interface stabilized; remove any custom references to deleted legacy E2B classes (E2BPack, PayloadBuilder).
- If you parse logs programmatically, prefer `cleanup_complete.total_rows` as source of truth for totals.

### Added
- **E2B Transparent Proxy Architecture** (M1e/M1f)
  - Complete redesign eliminating E2BPack in favor of transparent proxy approach
  - New `E2BTransparentProxy` class replacing legacy `E2BAdapter` and `PayloadBuilder`
  - `ProxyWorker` for remote execution in E2B sandbox environment
  - RPC protocol for communication between proxy and worker
  - Full parity between local and E2B execution paths
  - Identical log structure and artifact layout across environments
  - Support for verbose output passthrough from E2B sandbox
  - Heartbeat mechanism for long-running operations
  - Clean separation of concerns with ExecutionAdapter pattern
  - Adapter factory pattern for runtime adapter selection (local vs E2B)
  - PreparedRun dataclass with deterministic execution packages
  - ExecutionContext for unified session and artifact management
  - Support for E2B-specific features: timeout, CPU, memory configuration

- **HTML Logs Browser** (M1d)
  - Complete data engineer-focused log visualization system
  - Performance dashboard matching e2b.dev design aesthetics
  - SessionReader for structured session analysis and metrics aggregation
  - Sortable tables with row counts and session statistics
  - Technical Logs tab with filtered event streams
  - Multi-page report generation with session details
  - Mermaid diagram support for pipeline visualization
  - Rich terminal integration for session management

- **HTML Report Enhancements**
  - Visual badges to distinguish execution environments (orange E2B badge, grey Local badge)
  - E2B Bootstrap time metric in Performance panel showing sandbox initialization time
  - Scroll indicator for Overview tab when content overflows with smooth fade effect
  - Improved visual distinction between local and E2B runs in session lists and detail pages

- **Runtime Driver Layer** (M1c)
  - New `DriverRegistry` for dynamic driver registration and lookup
  - Concrete drivers: `MySQLExtractorDriver` and `FilesystemCsvWriterDriver`
  - Driver protocol: `run(step_id, config, inputs, ctx) -> dict`
  - Automatic metrics emission: `rows_read` and `rows_written`
  - In-memory result caching for DataFrame passing between steps
  - Foundation for future streaming IO implementation (ADR-0022)

- **Component Registry and Architecture** (M1a)
  - Component Registry backend with mtime-based caching and three validation levels (basic/enhanced/strict)
  - Component specification schema (JSON Schema Draft 2020-12) for self-describing components
  - Bootstrap component specs for MySQL and Supabase extractors/writers
  - Component management CLI commands: `osiris components list`, `show`, `validate`, `config-example`, `discover`
  - Session-aware `osiris components validate` command with structured event logging
  - **Friendly Error Mapper**: Transforms technical validation errors into human-readable messages with fix suggestions
  - JSON output for components list with `--json` flag
  - Path-to-label mapping for common configuration fields
  - Error categorization system with contextual examples
  - Verbose mode (`--verbose`) for components validate to show technical error details

- **Context Builder for LLM** (M1b.1)
  - Minimal component context export for token-efficient LLM consumption (~330 tokens)
  - JSON schema for context format (`osiris/prompts/context.schema.json`)
  - Context builder implementation with SHA-256 fingerprinting and disk caching
  - CLI command: `osiris prompts build-context [--out FILE] [--force]`
  - Session-aware logging with structured events
  - Automatic cache invalidation on component spec changes
  - **NO-SECRETS guarantee**: Secret fields excluded, suspicious values redacted
  - Comprehensive test coverage including secret filtering tests

- **LLM Context Integration** (M1b.2)
  - Automatic component context injection into all LLM requests
  - Extended PromptManager with context loading, caching, and injection
  - Context injection into chat CLI with flags: `--context-file`, `--no-context`, `--context-strategy`, `--context-components`

- **Post-generation Validation** (M1b.3)
  - Automatic validation of LLM-generated pipelines against component specifications
  - Pipeline validator validates OML against registry specs
  - Friendly error messages using FriendlyErrorMapper
  - Validation events logged to session with attempt tracking
  - Configurable bounded retries (0-5, default 2) per ADR-0013
  - HITL (Human-In-The-Loop) escalation when auto-retries fail
  - Retry trail artifacts saved to session directories for debugging

- **Validation Test Harness**
  - Command: `osiris test validation [--scenario valid|broken|unfixable|all]`
  - Pre-defined scenarios for automated testing
  - Exit codes: 0 for success scenarios, 1 for unfixable (CI/CD ready)
  - Output structure with result.json, retry_trail.json, and artifacts/
  - Token usage tracking and reporting in chat responses

- **Chat State Machine and OML Synthesis** (ADR-0019)
  - Mandatory FSM flow: INIT → INTENT_CAPTURED → DISCOVERY → OML_SYNTHESIS → VALIDATE_OML → COMPILE → RUN → COMPLETE
  - Hard rule: NO open questions after discovery phase - immediate OML synthesis
  - Strict OML v0.1.0 contract enforcement with required keys
  - Forbidden legacy keys with automatic detection
  - Single regeneration attempt on validation failure
  - Structured event logging for each state transition

- **Connection Resolution and Secrets Management** (ADR-0020)
  - External `osiris_connections.yaml` for non-secret connection metadata
  - Environment variable substitution for secrets using `${ENV_VAR}` syntax
  - Connection alias model with family-based organization
  - Default selection precedence: `default:true` → alias named "default" → error
  - Optional OML reference syntax: `config.connection: "@family.alias"`
  - CLI commands: `osiris connections list` and `osiris connections doctor`
  - Complete separation of secrets from pipeline definitions
  - Runtime connection resolution integration
  - Per-step events: `connection_resolve_start` and `connection_resolve_complete`

- **Streaming IO and Spill** (ADR-0022)
  - Iterator-first RowStream interface for memory-safe data processing
  - Support for datasets of 10GB+ without loading into memory
  - Optional spill-to-disk capability with DuckDB temp tables or Parquet files
  - Backward compatibility via DataFrame adapters

- **Remote Object Store Writers** (ADR-0023)
  - Direct writing to S3, Azure Blob Storage, and Google Cloud Storage
  - Multipart upload support for files >100MB
  - Deterministic CSV contract matching filesystem.csv_writer
  - Connection-based credential management

- **M1c Thin-Slice: Deterministic Compiler and Local Runner**
  - Minimal OML v0.1.0 to manifest compiler with deterministic output
  - Canonical YAML/JSON serialization with stable key ordering
  - SHA-256 fingerprinting for all compilation inputs/outputs
  - Parameter resolution with precedence: defaults < ENV < profile < CLI
  - Strict no-secrets enforcement
  - CLI commands: `osiris compile` and unified `osiris run`
  - Structured artifacts in session directories

- **Unified run command with last-compile support**
  - Single `run` command handles both OML and compiled manifests
  - `--last-compile` flag runs most recently compiled manifest
  - `--last-compile-in DIR` finds latest compile in specified directory
  - Pointer files track successful compilations
  - Environment variable fallbacks: `OSIRIS_LAST_MANIFEST`, `OSIRIS_LAST_COMPILE_DIR`

- **Relaxed Log Redaction Policy**
  - Privacy levels: `--privacy standard|strict` flag in chat CLI
  - Numeric metrics preserved as integers
  - Fingerprints shortened to 8-char prefix
  - Paths converted to repo-relative format

- Session ID wrapping in `osiris logs list` for full copy/paste capability
- Migration guide for 'load' to 'write' mode transition
- Comprehensive test suites for component specifications and registry
- CLI displays both required configuration and secrets for components
- Component-level `doctor()` capability (ADR-0021)
- Comprehensive driver unit tests and integration tests

### Changed
- **ExecutionAdapter Interface Stabilization**
  - Refactored from concrete implementations to abstract base class
  - Three-phase execution model: prepare() → execute() → collect()
  - Unified context handling across local and remote execution
  - Session directory structure simplified (no nested session segments)
  - Artifact collection standardized with CollectedArtifacts dataclass

- **Component Registry as Single Source of Truth**
  - Removed legacy `COMPONENT_MAP` from compiler completely
  - Runtime exclusively uses ComponentRegistry for component resolution
  - Mode aliasing implemented at compile boundary (read→extract, write→write, transform→transform)
  - Compiler generates manifests with canonical driver names

- **Unified CLI command structure**
  - `run` command now handles both OML compilation and manifest execution
  - All commands use consistent session directories (`logs/<type>_<timestamp>/`)
  - Stdout limited to progress and summary; detailed logs in session files
  - `osiris logs list` shows command type for each session
  - INFO/DEBUG logging redirected from stdout to `logs/<session>/osiris.log`

- **CLI Framework**: Completely removed Click library dependency, using only Rich framework for all CLI commands

- **MySQL/Supabase/DuckDB connectors** now consume injected connections from runner
  - Removed direct environment variable access at runtime
  - All connection data passed via config dict
  - Backward compatibility maintained for testing

- **Development Environment**
  - Added `*.bak` files to .gitignore to prevent tracking of backup files
  - Cleaned up old backup files from repository

- Clarified ADR-0022: Spill to disk is implementation detail only
- Connection JSON output shape: now under `connections` with top-level `session_id`
- Tests updated to align with the new JSON shape
- Log redaction system completely rewritten with configurable privacy levels
- SessionContext now uses advanced redaction with better granularity
- Event payloads now show concrete numbers for token counts and durations
- Fingerprints and hashes are partially revealed instead of fully masked
- Standardized on 'write' mode for data writing operations ('load' deprecated)
- Component capabilities updated to reflect actual implementation

### Fixed
- **HTML Report Improvements**
  - Fixed E2B connection aliases showing as "unknown" in reports
  - Fixed Data Volume calculation to use single source of truth (cleanup_complete > writers > extractors)
  - Fixed Total Step Time aggregation that was showing 0.00s
  - Fixed metadata fields in driver config causing validation errors in E2B execution

- **Session Reader OML Version Extraction**
  - Fixed missing oml_validated event handling in _read_events_v2 method
  - Added oml_version extraction from oml_validated events
  - Added pipeline name extraction from oml_validated events
  - Restored parity between _read_events and _read_events_v2 methods

- **Local Row Totals Parity with E2B**
  - Local runs now report correct total rows matching E2B execution
  - Added `cleanup_complete` event with accurate `total_rows` in local sessions
  - Fixed double-counting issue where extractors and writers were both summed
  - Improved SessionReader fallback logic for historical sessions without cleanup totals

- **Verbose Output Streaming in LocalAdapter**
  - Local `--verbose` now streams events live during execution, matching E2B behavior
  - Added real-time event interception with `[local]` prefix for consistency
  - Step events appear as they happen, not after completion
  - Metrics displayed immediately when emitted
  - All verbose output properly flushed to avoid buffering delays

- **Test Suite Modernization**
  - Fixed RunnerV0 API changes to include required output_dir parameter
  - Removed 18 obsolete test files for deleted components
  - Fixed mock directory pollution in repository root
  - Updated .gitignore to prevent test artifact pollution
  - All 694 tests now passing (was 91 failures)

- **Pipeline Execution Issues**
  - DataFrames now correctly passed between extract and write steps
  - CSV writer produces non-empty files with proper column ordering
  - Manifest dependency ordering corrected
  - Newline handling in CSV writer fixed
  - Connection resolution properly merges into step config

- **Test Suite Improvements**
  - Fixed StateStore → SQLiteStateStore imports
  - Removed references to non-existent methods
  - Updated CLI test to check for --last-compile
  - Fixed session logging imports
  - Added pragma comments for test-only credentials

- **Context and Validation Issues**
  - Context builder now guarantees no secrets in exported JSON
  - Session-aware logging properly tracks ephemeral sessions
  - Writers now support 'discover' mode for target schema inspection
  - Component validation now creates session logs with proper status tracking
  - Components validate default output shows friendly error messages
  - Registry validation returns structured errors
  - Session events include `friendly_errors` field

- **Various Fixes**
  - Over-masking of event names/session ids resolved
  - Context builder console noise reduced
  - Test harness exit codes corrected
  - --max-attempts parameter properly limits total attempts
  - Supabase health check avoids 404s
  - Secrets redacted consistently in CLI outputs
  - Duplicate validation events eliminated
  - Component CLI path resolution works from any directory
  - JSON Schema validation for component specs
  - Capabilities accurately reflect implementation

### Security
- **Enhanced secrets protection in runner path**
  - Connection passwords/keys never logged in runner events
  - Automatic redaction of sensitive fields in connection dicts
  - No secrets written to manifest.yaml or config artifacts
  - Connection resolution events log only family and alias names

### Removed
- **Legacy E2B Implementation**
  - Deleted E2BPack and PayloadBuilder classes (replaced by E2BTransparentProxy)
  - Removed SafeLogger (functionality integrated into ProxyWorker)
  - Eliminated nested run directory structure in E2B execution
  - Removed obsolete test files for old E2B architecture
  - Deleted cfg materialization tests (now handled by adapters)

- **`execute` command** - functionality merged into unified `run` command
- **Direct stdout INFO logging** - all detailed logs now in session files

### Deprecated
- 'load' mode for writers (use 'write' instead) - will be removed in v2.0.0
