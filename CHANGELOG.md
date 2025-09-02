# Changelog

All notable changes to the Osiris Pipeline project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
