# Changelog

All notable changes to the Osiris Pipeline project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.0]: https://github.com/keboola/osiris_pipeline/releases/tag/v0.1.0
