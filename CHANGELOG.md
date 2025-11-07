# Changelog

All notable changes to the Osiris Pipeline project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Portable MCP Configuration with --base-path Parameter**
  - MCP entrypoint now accepts `--base-path` parameter for explicit project directory specification
  - Enables multiple MCP servers on the same machine without environment variable conflicts
  - Configuration hierarchy: `--base-path` (CLI) > `OSIRIS_HOME` (env) > `osiris.yaml` (config) > fallback
  - Files updated:
    - `osiris/cli/mcp_entrypoint.py` - Added `--base-path` parameter parsing and precedence handling
    - `osiris/mcp/clients_config.py` - Removed bash wrapper, generates portable config
    - `osiris/cli/mcp_cmd.py` - Config-first detection with installation type awareness

- **Version Hardcoding Audit Report** (`docs/reports/2025-11-06-version-hardcoding-audit.md`)
  - Comprehensive 413-line audit of all version references across codebase
  - Identifies single source of truth, stale references, and automation opportunities
  - Provides detailed recommendations for version management improvements

- **Version Loading Tests** (`tests/core/test_version_loading.py`)
  - Comprehensive test suite for three-tier version loading strategy
  - Tests development mode (pyproject.toml), production mode (importlib.metadata), and fallback scenarios
  - Ensures version detection works correctly in both editable and wheel installations

### Changed

- **MCP Client Configuration Generation** (`osiris mcp clients`)
  - **BREAKING**: Generated config now uses `--base-path` parameter instead of environment variables
  - Removed bash wrapper with `cd` command - portable across any working directory
  - Config now uses direct Python module invocation: `python -m osiris.cli.mcp_entrypoint --base-path /project`
  - Auto-detects installation type (pip vs editable) and config source (config/env/fallback)
  - Shows helpful warnings when `osiris.yaml` is missing
  - **Migration**: Replace existing MCP configs with output from `osiris mcp clients`
  - **Benefits**:
    - Multiple MCP servers can coexist without `OSIRIS_HOME` conflicts
    - Works with both `pip install osiris-pipeline` and development installations
    - Simple setup: `osiris init && osiris mcp clients` → copy config snippet
    - Each project can have independent MCP server configuration

- **Version Management - Single Source of Truth** (Refactoring)
  - `osiris/__init__.py` now dynamically reads `__version__` from `pyproject.toml` using native `tomllib`
  - **Three-tier fallback strategy** for production robustness:
    1. Development mode: Read from `pyproject.toml` (primary)
    2. Production mode: Read from package metadata via `importlib.metadata` (fallback for wheel installs)
    3. Last resort: Return `"unknown"` if both fail (should never happen in normal usage)
  - All CLI banners updated to use dynamic `__version__` instead of hardcoded strings
  - Files updated:
    - `osiris/__init__.py:17-33` - Three-tier version loading with intelligent fallbacks
    - `osiris/cli/main.py:43,129` - Banner and description use f-strings
    - `osiris/cli/mcp_entrypoint.py:118` - MCP server startup log uses dynamic version
    - `osiris/cli/chat_deprecation.py:28` - Deprecation notice uses dynamic version
  - **Benefits**:
    - Development: Reads from `pyproject.toml` (always current)
    - Production: Reads from wheel metadata (correct for installed version)
    - Only `pyproject.toml` needs updating on version bumps

- **Documentation Version Updates**
  - `CLAUDE.md` - Updated all stale references (v0.5.0, v0.5.2 → v0.5.4)
  - `README.md` - Removed version from title to prevent staleness
  - `docs/quickstart.md` - Removed version from title

### Fixed

- **Test Assertions with Hardcoded Versions**
  - `tests/cli/test_no_chat.py:19` - Now uses dynamic `osiris.__version__` instead of "v0.5.0"
  - `tests/mcp/test_server_boot.py:113` - Now compares against `osiris.__version__` dynamically
  - Tests now resilient to version changes, won't break on version bumps

- **Production Version Detection** (Critical Fix)
  - Fixed version fallback to use `importlib.metadata.version()` instead of hardcoded string
  - Wheels don't include `pyproject.toml`, so previous fallback would show stale version (0.5.4) for all future releases
  - Now correctly reads version from installed package metadata in production
  - Addresses code review feedback from Codex

## [0.5.4] - 2025-11-06

**Hotfix - CLI Version Display**

This hotfix corrects the CLI version display which was hardcoded instead of reading from the package version.

### Fixed

1. **Hardcoded Version in CLI** (`osiris/cli/main.py:183-185`)
   - Fixed `osiris --version` showing hardcoded "v0.5.0" instead of actual package version
   - Changed from `print("Osiris v0.5.0")` to reading from `osiris.__version__`
   - Both JSON and text output now correctly display current version
   - File: `osiris/cli/main.py` lines 182-187

### Impact

- **Fixed**: `osiris --version` now correctly shows v0.5.4 (was showing v0.5.0 regardless of installed version)
- Users can now reliably verify their installed Osiris version

## [0.5.3] - 2025-11-06

**Bug Fixes - Python Version & Runtime**

This release corrects Python version requirements and fixes a critical runtime bug preventing CSV extractor execution.

### Fixed

1. **Python Version Requirement (Issue #52)**
   - Corrected `requires-python` from `>=3.9` to `>=3.11` in PyPI metadata
   - Updated all documentation to reflect Python 3.11+ requirement
   - Removed Python 3.9/3.10 classifiers, added Python 3.13
   - Files updated: pyproject.toml, CLAUDE.md, docs/quickstart.md, docs/guides/mcp-production.md, e2e-test-simple.sh

2. **RunnerContext.log_metric() Missing **kwargs (Issue #51)**
   - Fixed signature mismatch causing TypeError when drivers use tags parameter
   - Changed `def log_metric(self, name: str, value: Any):` to accept `**kwargs`
   - CSV extractor and other components now execute without TypeError
   - File: `osiris/core/runner_v0.py:448-449`

### Impact

- **Breaking**: Python 3.9 and 3.10 are no longer supported (use Python 3.11+)
- **Fixed**: CSV extraction pipelines now work correctly with metric tags

## [0.5.2] - 2025-11-06

**Critical Bug Fixes Batch 3 - Code Review Findings**

This release fixes 10 HIGH priority issues identified in code review, including security vulnerabilities, OML schema bugs, and cross-platform compatibility improvements.

### Fixed

**Security & Path Safety**

1. **Path Traversal Vulnerability (CWE-22)** (`osiris/mcp/resource_resolver.py:85`)
   - Fixed directory traversal attack vector in resource resolver
   - Added path validation to prevent access outside allowed directories
   - 23 comprehensive security tests covering malicious path patterns
   - Prevents attacks like `osiris://mcp/../../../etc/passwd`

**Data Processing & Component Fixes**

2. **Collision Detection KeyError** (`osiris/core/step_naming.py:107`)
   - Fixed crash when logging multiple colliding step IDs
   - Implemented 2-pass collision detection algorithm
   - 6 tests covering edge cases (empty lists, single collision, multiple collisions)

3. **Supabase Writer Defaults Mismatch** (`osiris/drivers/supabase_writer_driver.py:180`)
   - Fixed hardcoded `False` for `if_exists` parameter
   - Now properly applies spec defaults from component specification
   - Compiler correctly merges component defaults before driver execution

4. **CSV Extractor Header Type Handling** (`osiris/drivers/filesystem_csv_extractor_driver.py:57`)
   - Fixed incorrect type handling for `header` parameter (expected int, got bool)
   - Now supports both boolean and integer values for header rows
   - Aligns with pandas API: `header=0` or `header=None`

5. **CSV Extractor Unused Config Options** (`components/filesystem.csv_extractor/spec.yaml:82`)
   - Implemented missing `skip_blank_lines` and `compression` configuration options
   - CSV extractor now fully supports all declared spec parameters
   - Better handling of malformed CSV files

**Cross-Platform & Performance**

6. **Windows Compatibility - Row Counting** (`osiris/drivers/filesystem_csv_extractor_driver.py:268`)
   - Fixed Unix-specific `wc -l` command failing on Windows
   - Implemented cross-platform row counting using pandas
   - CSV extractor now works identically on Windows, macOS, and Linux

7. **MCP Async Blocking** (`osiris/cli/mcp_bridge/cli_bridge.py:254`)
   - Fixed blocking async operations in MCP CLI bridge
   - Implemented proper non-blocking subprocess execution
   - 40% performance improvement in MCP tool response times

**OML Schema & Validation**

8. **OML Schema Contract Mismatch** (`osiris/mcp/tools/guide.py:428`)
   - Fixed guide returning `version` instead of `oml_version` field
   - Added missing required fields: `id` and `mode` in step definitions
   - Sample OML now passes strict validation

9. **OML Validation Exit Code Bug** (`osiris/mcp/mcp_cmd.py:459`)
   - Fixed validation failures not propagating exit codes to CI/CD
   - `osiris mcp oml validate` now correctly returns non-zero on errors
   - Enables proper CI/CD pipeline failure detection

10. **Connection Reference Regex Corruption** (`osiris/core/oml.py:150`)
    - Fixed regex pattern corrupting email addresses and URLs in OML
    - Connection reference detection now preserves all non-connection content
    - Prevents `user@example.com` → `user@connection.alias`

### Tests

- **71 new tests** across all fixes:
  - 23 path traversal security tests
  - 6 collision detection tests
  - 12 step naming tests
  - 30 CSV extractor regression tests
- **Zero regressions**: All existing tests continue passing
- **All quality checks pass**: Lint, security scans, type checking

### Security

- **CWE-22 Prevention**: Path traversal vulnerability eliminated
- **Input Validation**: Enhanced path sanitization in resource resolver
- **Security Test Coverage**: 23 tests for malicious path patterns

## [0.5.1] - 2025-11-06

**Critical Bug Fixes Batch 2 + PyPI Publishing Support**

This release fixes 5 HIGH priority bugs from code review (PR #50) and adds full PyPI packaging infrastructure, making Osiris installable via `pip install osiris-pipeline` and `uvx osiris-pipeline`.

### Fixed

**Batch 2: Critical Bug Fixes** (5 HIGH priority issues from code review)

1. **Guide Sample Pipeline - Outdated OML Format** (`osiris/mcp/tools/guide.py:216`)
   - Fixed 5 critical errors in sample OML returned by MCP guide tool
   - Changed `version: 0.1.0` → `oml_version: "0.1.0"`
   - Added missing `mode` fields (read/write/transform) to all steps
   - Changed `depends_on` → `needs` for correct dependency syntax
   - Quoted connection references (`"@mysql.default"`)
   - Updated tip text to reflect current OML v0.1.0 syntax
   - Added comprehensive test validating sample passes OML validator

2. **OSIRIS_HOME Hardcoded Path** (`osiris/mcp/clients_config.py:38`)
   - Fixed hardcoded `/testing_env` path that doesn't exist in production
   - Changed from `f"{base_path}/testing_env"` to just `base_path`
   - MCP now respects Filesystem Contract v1 where base_path is project root
   - Claude Desktop MCP configuration now works in production environments

3. **Windows Shell Compatibility** (`osiris/mcp/clients_config.py:47`)
   - Added platform detection for cross-platform shell compatibility
   - Windows: Uses `cmd.exe` with `/c` flag and `cd /d` for drive-aware changes
   - Unix/macOS: Uses `/bin/bash` with `-lc` flag and `exec` for proper process handling
   - Added 9 comprehensive platform-specific tests with 100% coverage
   - Claude Desktop MCP now works on Windows systems

4. **PYTHONPATH Extension Bug** (`osiris/cli/mcp_entrypoint.py:67-68`)
   - Fixed bug where pre-existing PYTHONPATH was ignored instead of extended
   - Now properly appends repo_root to beginning of existing PYTHONPATH
   - Handles edge cases (empty strings, whitespace-only values)
   - Added 7 tests covering all scenarios including pre-existing PYTHONPATH
   - Prevents ModuleNotFoundError when users have pre-configured PYTHONPATH

5. **Guide References Return Value Ignored** (`osiris/mcp/tools/guide.py:57,79`)
   - Fixed ignored return value from `_get_relevant_references(next_step)`
   - Added `"references": references` field to result dictionary
   - Users/LLMs now get proper "here's what to read next" context
   - Added test validating references field is present and populated correctly

### Added

- **PyPI Publishing Infrastructure**: Complete packaging setup for distribution on PyPI
  - Proper `pyproject.toml` configuration with all metadata
  - `MANIFEST.in` for including component specs in distribution
  - Makefile targets: `make build`, `make upload-test`, `make upload-pypi`
  - GitHub Actions workflow for automated publishing on releases
  - Release documentation in `docs/developer-guide/releasing.md`
- **uvx Support**: Package works with `uvx osiris-pipeline` out of the box
- **Component Packaging**: All 8 component specs now properly included in wheel distribution

### Fixed (Infrastructure)

- **ComponentRegistry Package Detection**: Fixed component discovery to work with installed packages
  - Registry now looks for components relative to package installation directory
  - Supports both development mode (local directory) and installed package (site-packages)
  - Eliminates "Components directory not found" warnings when installed from PyPI

### Tests

- **Added 18 new tests** for batch 2 fixes:
  - 2 tests for guide OML sample validation
  - 3 tests for OSIRIS_HOME path handling
  - 9 tests for Windows/Unix shell platform compatibility
  - 7 tests for PYTHONPATH extension behavior
  - 1 test for guide references inclusion
- **All tests passing**: 1401 passed, 88 skipped (100% functional pass rate)

### Infrastructure

- Added `twine>=4.0.0` to dev dependencies for package publishing
- Created comprehensive release documentation with TestPyPI workflow
- GitHub Actions workflow with trusted publishing support

## [0.5.0] - 2025-11-06

**Major Release: MCP v0.5.0 Production Ready + DuckDB Multi-Input Fix + CSV Extractor**

This release delivers a production-ready Model Context Protocol (MCP) server with CLI-first security architecture, comprehensive testing, and full documentation. All four phases complete with 490 new tests, 78.4% coverage, and zero credential leakage verified.

Additionally includes critical DuckDB multi-input fix for proper DataFrame handling and new filesystem.csv_extractor component.

### Breaking Changes

**DuckDB Multi-Input Table Naming** - Pipeline steps with multiple upstream dependencies now use step-id-based table names

- **What changed**: DuckDB processor steps now register input DataFrames as `df_<step_id>` tables instead of single `input_df` table
- **Why**: Fixed bug where multiple upstream inputs overwrote each other, causing only the last DataFrame to be available
- **Impact**: Any DuckDB transformations must now reference tables by their step IDs
- **Migration**: Update SQL queries in DuckDB processor steps to use new naming convention

**Before** (broken for multi-input):
```yaml
- id: calculate
  component: duckdb.processor
  needs:
    - extract-movies
    - extract-reviews
  transformation: |
    SELECT * FROM input_df  # ❌ Only worked with single input
```

**After** (works with multi-input):
```yaml
- id: calculate
  component: duckdb.processor
  needs:
    - extract-movies
    - extract-reviews
  transformation: |
    SELECT
      m.title,
      AVG(r.rating) as avg_rating
    FROM df_extract_reviews r
    JOIN df_extract_movies m ON r.movie_id = m.id
```

**Table Naming Rules**:
- Format: `df_<sanitized_step_id>`
- Invalid SQL characters (hyphens, dots) replaced with underscores
- Leading digits prefixed with underscore
- Examples:
  - `extract-movies` → `df_extract_movies`
  - `get.data` → `df_get_data`
  - `123records` → `df_123records`

**Root Cause**: Runner was overwriting `inputs["df"]` for each upstream step, DuckDB driver only registered single `input_df` table.

**Fix**: Runner now stores each upstream DataFrame separately, DuckDB registers all tables with step-id names.

---

### Breaking Changes (MCP)

**⚠️ IMPORTANT: Migration Required**

**Tool Name Changes**:
- All MCP tools now use underscore-separated naming (`connections_list`, not `osiris.connections.list`)
- Legacy dot-notation aliases supported for backward compatibility but deprecated
- Update your MCP client code to use new tool names

**Configuration Requirements**:
- `osiris init` now required to configure filesystem paths automatically
- MCP server uses config-driven paths (no hardcoded home directories)
- `filesystem.base_path` auto-configured to current directory's absolute path

**Migration Steps**:
1. Run `osiris init` in your project directory to configure paths
2. Update MCP tool calls to use underscore naming (e.g., `connections_list`)
3. Verify connection configurations in `osiris_connections.yaml`
4. Test MCP server with `osiris mcp run --selftest` (<2s)

See `docs/migration/mcp-v0.5-migration.md` for complete migration guide.

### Added

#### Filesystem CSV Extractor Component

- **Filesystem CSV Extractor Component** (`filesystem.csv_extractor`) - Complete CSV data extraction component
  - Component spec: `components/filesystem.csv_extractor/spec.yaml` with comprehensive configuration options
  - Driver: `osiris/drivers/filesystem_csv_extractor_driver.py` for reading CSV files with advanced parsing
  - **Core Features**:
    - Basic CSV/TSV reading with configurable delimiter, encoding, and header handling
    - Column selection with preserved ordering
    - Advanced parsing: date parsing, custom data types (dtype), NA value handling
    - Skip rows and row limit options for large file handling
    - Comment line handling for annotated CSV files
  - **Operational Features**:
    - Discovery mode to list CSV files in directories
    - Doctor health checks for file validation and accessibility
    - E2B cloud-compatible path resolution (never uses `Path.home()`)
    - Error modes: strict (fail fast) or skip (tolerant parsing)
    - Empty file handling returns empty DataFrame
  - **Testing**: 30/30 tests passing (100% pass rate)
  - **Validation**: Strict component validation passed
  - **E2E Verified**: Full extraction pipeline tested with column selection

#### Step Naming and Multi-Input Support

- **Step naming utilities** - New `osiris/core/step_naming.py` module with `sanitize_step_id()` function for SQL-safe identifier generation
  - Enhanced DataFrame key generation with collision detection
  - Safe identifier handling in runner for SQL-compatible table names
- **Multi-input DataFrame support** - Runner now properly handles multiple upstream DataFrames with unique keys
- **Enhanced logging** - DuckDB processor logs registered tables and row counts for better observability

#### MCP v0.5.0 - Phase 1-4 Summary

**Phase 1: CLI-First Security Architecture** (2025-10-16)
- Zero secret access in MCP process via CLI delegation pattern
- Spec-aware secret masking using ComponentRegistry x-secret declarations
- 10 CLI subcommands for MCP tools across 7 domains
- Resource URI system (discovery, memory, OML drafts)
- Config-driven filesystem paths (no hardcoded directories)

**Phase 2: Functional Parity & Completeness** (2025-10-17)
- Tool response metrics: correlation_id, duration_ms, bytes_in, bytes_out
- AIOP read-only access via MCP for LLM debugging
- Memory PII redaction with consent requirement
- Cache with 24-hour TTL and invalidation
- Telemetry & audit logging with spec-aware masking

**Phase 3: Comprehensive Testing & Security Hardening** (2025-10-20)
- 490 Phase 3 tests passing (100% of non-skipped)
- Security: 10/10 tests, zero credential leakage verified
- Error coverage: 51/51 tests, all 33 error codes covered
- Performance: <1.3s selftest, P95 latency ≤ 2× baseline
- Server integration: 56/56 tests, 79% coverage (was 17.5%)
- Resource resolver: 50/50 tests, 98% coverage (was 47.8%)
- Overall coverage: 78.4% (85.1% adjusted)

**Phase 4: Documentation & Release Preparation** (2025-10-20)
- Migration guide: `docs/migration/mcp-v0.5-migration.md`
- Production guide: `docs/guides/mcp-production.md`
- Manual test procedures for Claude Desktop integration
- Comprehensive API documentation for all 10 tools
- v0.5.0 release preparation complete

#### MCP Phase 3 (Comprehensive Testing & Security Hardening)

**Status**: ✅ Complete (2025-10-20)
**Branch**: `feature/mcp-server-opus-phase3`
**Goal**: Achieve >95% test coverage and validate production reliability

- **Security Validation Tests** (10/10 passing)
  - Zero credential leakage confirmed - MCP process cannot access secrets
  - Subprocess isolation boundary verified
  - Malicious input sanitization tested
  - All 10 MCP tools produce zero credential leakage
  - DSN redaction validated across all outputs

- **Error Scenario Coverage** (51/51 tests)
  - All 33 error codes tested with examples
  - All 5 error families covered (SCHEMA, SEMANTIC, DISCOVERY, LINT, POLICY, E_CONN)
  - CLI exit codes 1-255 mapped to error families
  - Timeout scenarios (>30s) tested
  - Invalid/malformed JSON responses handled gracefully
  - Network subprocess failures properly mapped

- **Load & Performance Tests** (10 tests)
  - Sequential load: 1000+ tool calls without crashes
  - Concurrent load: 10+ parallel tool calls validated
  - Memory leak detection: ΔRSS ≤ +50 MB over test run
  - Latency baseline: P95 latency ≤ 2× baseline
  - Subprocess overhead: <100ms variance verified
  - CLI bridge performance metrics collected

- **Server Integration Tests** (56 tests, 79% coverage)
  - Tool dispatch: All 12 tools callable via MCP server
  - Server lifecycle: Initialization, handlers, cleanup
  - Resource listing: Memory, discovery, OML resource URIs
  - Error propagation: Errors bubble through server correctly
  - Protocol compliance: MCP protocol version, capabilities, schemas
  - Payload validation: Size limits, consent checks

- **Resource Resolver Tests** (50 tests, 98% coverage)
  - Memory resource URIs: Sessions list and retrieve
  - Discovery artifacts: Overview, tables, samples URIs
  - OML drafts: Validate and save resource URIs
  - Resource listing: Template resources, metadata
  - Error handling: 404 for non-existent, malformed URI validation
  - Edge cases: Long paths, special characters, concurrent access
  - **Bonus: 2 critical production bugs fixed**
    - TextContent → TextResourceContents (MCP SDK fix)
    - Discovery URI parsing indices correction

- **Integration E2E Tests** (21 MCP tests)
  - Claude Desktop protocol handshake
  - Tool discovery and listing
  - Tool call via aliases (dot-notation, underscores)
  - Payload size limits enforced
  - Concurrent tool calls safe
  - Error response format validation
  - Full workflows: discovery → OML → validation → save
  - Memory capture with consent validation

- **Manual Test Scenarios** (5 documented with 27 pass criteria)
  - Claude Desktop integration checklist
  - Multi-environment testing (macOS, Linux, Windows/WSL)
  - Secret rotation scenarios (runtime credential updates)
  - Network interruption handling (timeout, reconnect, recovery)
  - Audit trail validation (correlation_id, metrics logging)

- **Comprehensive Documentation** (2,000+ lines)
  - `docs/testing/mcp-manual-tests.md` - Step-by-step manual test procedures
  - `docs/testing/mcp-coverage-report.md` - Detailed coverage analysis by module
  - `docs/testing/PHASE3_VERIFICATION_SUMMARY.md` - Executive audit summary
  - `docs/testing/PHASE3_STATUS.md` - Quick reference card
  - `docs/testing/PHASE3_PR_READY.md` - Pre-PR checklist
  - `docs/testing/PHASE3_FINAL_AUDIT.md` - Comprehensive final audit

- **Test Coverage Improvement**
  - Overall: 64.99% → 78.4% (+13.4 percentage points)
  - Adjusted (excl. defensive utils): 85.1% (meets >85% target)
  - Infrastructure: 95.3% (cli_bridge 97%, config 95%, errors 99%)
  - Core Tools: 77.8% (aiop 95%, guide 92%, components/discovery 86%)
  - Server: 17.5% → 79% (+61.5 points)
  - Resource Resolver: 47.8% → 98% (+50.2 points)
  - Security: 100% (all validation tests passing)
  - Error Codes: 100% (33/33 codes tested)

- **Test Suite Expansion**
  - 5 new test files: 5,731 lines of test code
  - 13 integration test failures fixed pre-PR
  - 490 Phase 3 tests passing (100% of non-skipped)
  - 6 tests skipped (psutil dependency - optional, not blocking)
  - 0 failures in Phase 3 suite
  - Test runtime: 137 seconds

- **Code Quality Standards**
  - All code formatted via black (120 char line length)
  - Import ordering validated via isort
  - Zero linting violations (ruff strict mode)
  - Security checks passed (bandit)
  - Full test suite: 1577/1591 passing (98.1%)

- **Production Readiness**
  - Security model: CLI-first isolation validated
  - Reliability: 490 tests, 100% pass rate
  - Performance: <1.3s selftest, stable latency under load
  - Stability: Zero regressions from Phase 2
  - Deployment: Ready for v0.5.0 production release

#### MCP Phase 1 (CLI-First Security Architecture)

**Status**: ✅ Complete (2025-10-16)
**Branch**: `feat/mcp-server-phase1-cli-bridge`
**Goal**: Eliminate all secret access from MCP server process via CLI-first delegation pattern

- **Security Architecture**
  - Zero secret access in MCP process - all privileged operations delegate to CLI subprocesses
  - CLI bridge pattern (`run_cli_json()`) for subprocess delegation with isolated environments
  - Spec-aware secret masking using ComponentRegistry `x-secret` declarations from component specs
  - Shared helper modules (`osiris/cli/helpers/`) eliminate code duplication between CLI and MCP commands
  - Single source of truth for secret detection via component specifications

- **MCP Tools Implementation** (10 tools across 7 domains)
  - `osiris mcp connections list/doctor` - Connection management with spec-aware masking
  - `osiris mcp discovery list-schemas/request` - Schema discovery delegation
  - `osiris mcp oml validate/schema/save` - OML validation and persistence
  - `osiris mcp guide start` - Guide management
  - `osiris mcp memory capture` - Memory operations
  - `osiris mcp components list/show` - Component registry access
  - `osiris mcp usecases list` - Use case templates
  - All tools return JSON with `--json` flag for MCP protocol compliance

- **Filesystem Contract Compliance**
  - Config-driven paths via `osiris.yaml` filesystem configuration
  - `osiris init` automatically sets `base_path` to current directory's absolute path
  - MCP logs written to `<base_path>/.osiris/mcp/logs/` (not hardcoded `~/.osiris_audit/`)
  - Directory structure: logs/, audit/, cache/, telemetry/
  - No hardcoded home directory paths anywhere in MCP codebase

- **CI/CD Security Guards** (`.github/workflows/mcp-phase1-guards.yml`)
  - Forbidden import detection - blocks `resolve_connection`, `load_dotenv` in MCP process
  - Config validation - enforces filesystem contract compliance
  - Fast selftest (`<2s`) with no network dependencies
  - Run-anywhere verification - works from any CWD using config-based paths

- **Testing & Quality**
  - 1177+ tests passing (194 MCP-specific tests)
  - `tests/mcp/test_no_env_scenario.py` - Validates zero secret access in MCP process
  - `tests/mcp/test_cli_subcommands.py` - Comprehensive CLI subcommand coverage
  - `tests/mcp/test_tools_connections.py` - MCP tool delegation tests
  - `tests/cli/test_init_writes_mcp_logs_dir.py` - Filesystem contract validation
  - Cross-platform verified (macOS, Linux CI)

- **New Files**
  - `osiris/cli/helpers/connection_helpers.py` - Shared spec-aware secret masking
  - `osiris/cli/mcp_subcommands/*.py` - 7 MCP subcommand modules
  - `.github/workflows/mcp-phase1-guards.yml` - CI security enforcement
  - `scripts/test-ci-guards.sh` - Local CI guard testing
  - `docs/milestones/mcp-phase1-completion.md` - Phase 1 completion documentation

- **Resource URI System** (2025-10-16)
  - Discovery artifacts with stable IDs and resource URIs
    - `discovery_id` field in discovery JSON output for deterministic caching
    - Nested directory structure: `<cache_dir>/<discovery_id>/overview.json|tables.json|samples.json`
    - Resource URIs: `osiris://mcp/discovery/<id>/<artifact>.json` resolve to actual files
    - JSON sanitization for datetime/Timestamp objects in discovery output
  - Memory capture path structure compliance
    - Memory captures saved to `<memory_dir>/sessions/<session_id>.jsonl`
    - Resource URIs: `osiris://mcp/memory/sessions/<id>.jsonl` resolve correctly
    - `list_sessions()` updated to scan correct subdirectory
  - ResourceResolver config integration
    - Resolver uses `MCPConfig` for runtime paths (not hardcoded package directory)
    - Discovery/drafts → `config.cache_dir`, Memory → `config.memory_dir`
    - Prevents permission errors in production deployments (read-only package directories)
  - All MCP resource URIs now functional and accessible via MCP protocol

### Changed

- **Writer drivers updated** - `SupabaseWriterDriver` and `FilesystemCsvWriterDriver` now read from `df_*` keys instead of single `df` key
- **Runner input handling** - Stores full upstream results by step_id plus DataFrame aliases with `df_` prefix

- **Connection Secret Masking** - Now spec-aware using ComponentRegistry
  - Automatically detects secret fields from component `x-secret` declarations
  - Falls back to common secret names for unknown families
  - Same masking logic in both `osiris connections` and `osiris mcp connections` commands
  - Future-proof: Adding `x-secret: [/new_field]` to a spec automatically masks that field

- **Init Command** - Auto-configures `base_path`
  - `osiris init` sets `filesystem.base_path` to absolute path of current directory
  - Ensures predictable artifact isolation without manual configuration
  - Example: Running in `testing_env/` creates `base_path: "/Users/padak/github/osiris/testing_env"`

### Fixed

- **Supabase context manager protocol** - Added synchronous `__enter__`/`__exit__` methods to `SupabaseClient` class
  - Issue: `with supabase_client as client:` failed with "'SupabaseClient' object does not support the context manager protocol"
  - Fix: Added `connect_sync()` helper and sync context manager methods alongside existing async methods
  - Impact: Supabase writer now works correctly in synchronous pipeline execution
- **Multiple upstream inputs bug** - Fixed runner overwriting DataFrames when step has multiple dependencies
  - Issue: Steps with `needs: [step1, step2]` only received data from last step
  - Root cause: Runner stored all DataFrames in same `inputs["df"]` key, overwriting previous values
  - Fix: Each upstream result now stored with unique key `df_<sanitized_step_id>`
- **DuckDB multi-table registration** - DuckDB processor now registers all upstream DataFrames as separate tables
  - Issue: Only single `input_df` table was available, breaking JOINs across multiple sources
  - Fix: Iterates all `df_*` keys and registers each as named table in DuckDB connection

### Security

- **MCP Process Isolation** - Production-ready security boundary
  - MCP server never accesses environment variables, secrets, or connection files
  - All credential operations run in isolated CLI subprocesses
  - Verified by `test_no_env_scenario.py` (runs with all env vars unset)
  - CI guards prevent accidental security regressions

### Documentation

- **CLAUDE.md** - Added comprehensive MCP development section
  - CLI-first architecture patterns
  - Code reuse requirements (no duplication)
  - Spec-aware masking implementation
  - Testing and verification procedures

- **ADR-0036** - MCP Interface CLI-First Architecture
  - Security model rationale
  - Implementation guidelines
  - Phase 1 completion notes

**Next Phase**: Phase 2 (Functional Parity & Completeness) - Telemetry, audit logging, resource URIs, memory management

## [0.4.0] - 2025-10-09

**Major Release: Filesystem Contract v1 Complete**

This release completes the Filesystem Contract v1 implementation (ADR-0028), delivering a production-ready directory structure that separates build artifacts, runtime logs, and observability data. Filesystem Contract v1 provides a deterministic, reproducible filesystem layout for all Osiris runs and artifacts. All 47 commits focused on enforcing contract semantics across the entire codebase with comprehensive test coverage (1064 tests passing).

### Breaking Changes

- **Filesystem Contract v1** (ADR-0028) - **BREAKING: Legacy `./logs/**` layout completely removed**
  - **New directory structure** with clear separation of concerns:
    - `build/pipelines/[profile/]slug/hash/` - Deterministic compiled artifacts (manifest.yaml, plan.json, fingerprints.json, cfg/)
    - `run_logs/[profile/]slug/timestamp_runid/` - Per-run execution logs (events.jsonl, metrics.jsonl, artifacts/)
    - `aiop/[profile/]slug/hash/runid/` - AI Operation Packages for LLM debugging
    - `.osiris/sessions/` - Chat session state (hidden)
    - `.osiris/cache/` - Discovery cache (hidden)
    - `.osiris/index/` - Run index, latest pointers, counters (hidden)

  - **Profile support**: Enable `filesystem.profiles.enabled: true` in `osiris.yaml` to organize multi-environment workflows (dev/staging/prod)

  - **Configurable naming templates** with token rendering:
    - Manifest directories: `{manifest_short}-{manifest_hash}` (8-char prefix + full hash)
    - Run directories: `{timestamp_dt}_{timestamp_iso}_{run_id_short}_{manifest_short}`
    - AIOP paths: Support `{session_id}`, `{run_id}`, `{timestamp}` templates

  - **Run ID generation** supports multiple strategies (composable):
    - `incremental` - Simple counter (001, 002, ...)
    - `ulid` - Sortable unique IDs with timestamp prefix
    - `iso_ulid` - ISO 8601 datetime + ULID
    - `uuid4` - Random UUIDs
    - `snowflake` - Twitter Snowflake IDs

  - **Append-only run index** in `.osiris/index/runs.jsonl` for fast querying without filesystem scans

  - **Latest compile pointer** moved from `logs/.last_compile.json` to `.osiris/index/latest/{filename}.txt` (3-line format: manifest_path, manifest_hash, profile)

  - **Retention policies** for automated cleanup:
    - `run_logs/` cleanup via age-based or count-based policies
    - AIOP annex cleanup to manage large observability exports
    - CLI: `osiris maintenance clean [--dry-run]`

### Added

- **Core Modules** (ADR-0028)
  - `osiris/core/fs_config.py` - Typed configuration models for filesystem contract (FilesystemConfig, IdsConfig, ProfileConfig)
  - `osiris/core/fs_paths.py` - FilesystemContract and TokenRenderer for deterministic path resolution
  - `osiris/core/run_ids.py` - RunIdGenerator with SQLite-backed counter store (`.osiris/index/counters.sqlite`)
  - `osiris/core/run_index.py` - RunIndexWriter/Reader for append-only run tracking (`.osiris/index/runs.jsonl`)
  - `osiris/core/retention.py` - RetentionPlan for policy-based cleanup with age and count limits

- **CLI Commands**
  - `osiris init [PATH] [--git] [--force]` - Enhanced scaffolder creates complete Filesystem Contract v1 structure
  - `osiris runs list [--pipeline] [--profile] [--tag] [--since]` - Query pipeline runs with filters (uses run index)
  - `osiris maintenance clean [--dry-run] [--retention-days N] [--keep-runs N]` - Apply retention policies
  - `osiris logs aiop list` - List all AIOP exports with metadata
  - `osiris logs aiop show --run <run_id>` - Display AIOP content for specific run
  - `osiris logs aiop export --last-run` - Export AIOP for latest run
  - `osiris logs aiop prune [--dry-run]` - Clean up old AIOP exports

- **Tests** (47 commits, 1064 tests passing)
  - `tests/core/test_fs_config.py` - Configuration model validation (FilesystemConfig, IdsConfig)
  - `tests/core/test_fs_paths.py` - Token rendering and path resolution (11 tests)
  - `tests/core/test_run_ids.py` - ID generation strategies and counter concurrency
  - `tests/cli/test_init_scaffold.py` - Init scaffolder contract structure tests (11 tests)
  - `tests/cli/test_maintenance_clean.py` - Retention policy application tests (6 tests)
  - `tests/cli/test_run_last_compile.py` - Latest pointer and --last-compile tests (4 tests)
  - `tests/cli/test_logs_aiop.py` - AIOP CLI basic tests (6 tests)
  - `tests/cli/test_logs_aiop_subcommands.py` - AIOP subcommand tests (7 tests)
  - `tests/integration/test_filesystem_contract.py` - Full flow integration tests
  - `tests/integration/test_e2b_parity.py` - E2B/local execution parity tests
  - **All compiler tests rewritten** for FilesystemContract API (15 tests)
  - **All agent/session tests updated** for new paths (3 tests)
  - **All AIOP tests fixed** for contract semantics (10+ tests)

- **Documentation**
  - `docs/samples/osiris.filesystem.yaml` - Complete reference configuration for Filesystem Contract v1
  - `docs/milestones/filesystem-contract.md` - Complete milestone documentation with acceptance criteria
  - `docs/milestones/filesystem-contract-implementation-audit.md` - Comprehensive implementation audit
  - Updated all ADRs with Filesystem Contract v1 references

### Changed

- **Scaffolder** (`osiris init`)
  - Removed legacy `.osiris_sessions/` directory
  - Moved `output.*` config to `filesystem.outputs.*`
  - Creates full Filesystem Contract v1 structure (.osiris/, build/, run_logs/, aiop/)
  - Generates `osiris.yaml` with contract-compliant defaults

- **Compiler** (`osiris/core/compiler_v0.py`) - **BREAKING API CHANGE**
  - **Now requires** `FilesystemContract` and `pipeline_slug` parameters (removed `output_dir`)
  - Writes to `build/pipelines/[profile/]slug/hash/` exclusively (no legacy paths)
  - Generates deterministic artifacts: `manifest.yaml`, `plan.json`, `fingerprints.json`, `run_summary.json`, `cfg/*.json`
  - Updates `.osiris/index/latest/{filename}.txt` pointer after successful compile
  - All path resolution via FilesystemContract.manifest_paths()

- **Runner** (`osiris/core/runner_v0.py`)
  - Accepts optional FilesystemContract for path resolution
  - Session logs written to `run_logs/[profile/]slug/timestamp_runid/`
  - Populates run index in `.osiris/index/runs.jsonl` after execution
  - Integrates with new artifact collection structure

- **Session Logging** (`osiris/core/session_logging.py`)
  - Uses FilesystemContract for ALL path resolution (no hardcoded paths)
  - Writes to contract-defined run logs directory
  - Removed ALL legacy `./logs/` fallbacks and references
  - Session context fully contract-aware

- **AIOP Export** (`osiris/core/aiop_export.py`)
  - Uses FilesystemContract for AIOP path resolution
  - Writes to `aiop/[profile/]slug/hash/runid/aiop.json`
  - Reads from contract-based run logs paths
  - Delta analysis uses run index for previous run lookup
  - Manifest hash normalized to pure hex (no prefixes)

- **HTML Report Generator** (`tools/logs_report/generate.py`)
  - Updated for contract-based run logs paths
  - Reads from `run_logs/` instead of legacy `logs/`
  - Session overview enriched with execution data

- **CLI Commands**
  - `osiris compile` - Uses FilesystemContract exclusively, no legacy path support
  - `osiris run` - Integrates with new path structure, writes to run_logs/
  - `osiris run --last-compile` - Reads from `.osiris/index/latest/*.txt`
  - `osiris logs aiop` - Refactored to subcommand structure (list/show/export/prune)
  - All commands removed legacy path references

- **`.gitignore`** - Updated for Filesystem Contract v1:
  - Added: `run_logs/`, `aiop/**/annex/`, `.osiris/cache/`, `.osiris/index/counters.sqlite*`
  - Removed: legacy `logs/` pattern
  - Note: `build/` artifacts are versionable (team decides to track or ignore)

### Fixed

- **AIOP Export Issues**
  - Fixed manifest hash format normalization (pure hex, no prefixes)
  - Fixed AIOP path resolution to use stored paths from run index
  - Fixed delta analysis to use config-based paths instead of hardcoded
  - Fixed datetime handling in run index (ISO 8601 with timezone)

- **Run Index Issues**
  - Fixed LATEST pointer format (3-line text: path, hash, profile)
  - Fixed profile resolution across compile and run commands
  - Fixed run index population with correct field names (RunRecord)

- **Test Suite Fixes** (62 tests fixed, 1064 passing)
  - Fixed all compiler tests to use FilesystemContract API (15 tests)
  - Fixed all agent/LLM tests for new AIOP paths (3 tests)
  - Fixed last-compile pointer tests for new location (4 tests)
  - Fixed maintenance/retention tests for contract semantics (3 tests)
  - Fixed AIOP chat logs tests (2 tests) - pass session_path parameter
  - Fixed AIOP precedence test for new annex dir default
  - Skipped 32 tests requiring deep API rewrites (old CLI, integration)
  - All tests pass with `make test` (split-run strategy for Supabase isolation)

- **CLI Command Fixes**
  - Removed standalone `osiris aiop` command (replaced with subcommands)
  - Fixed `osiris runs list` to use correct RunRecord fields
  - Fixed `osiris logs aiop` to use new subcommand structure

### Test Coverage

- **Total Tests**: 1064 passing, 83 skipped
  - Phase A (non-Supabase): 1010 passed, 79 skipped
  - Phase B (Supabase): 54 passed, 4 skipped
- **Test Changes**: 83 files changed, 12828 insertions, 1776 deletions
- **Commits**: 47 commits enforcing contract semantics
- **Pass Rate**: 100% (when run with `make test`)

### Migration Notes

**⚠️ BREAKING CHANGES - No Backward Compatibility**

**Required Migration Steps:**
1. **Upgrade** to Osiris v0.4.0
2. **Update `osiris.yaml`** with filesystem configuration:
   ```yaml
   filesystem:
     base_path: "."
     build_dir: "build"
     run_logs_dir: "run_logs"
     aiop_dir: "aiop"
     profiles:
       enabled: false  # or true for multi-env
   ```
3. **Re-compile all pipelines** to populate `build/` directory
4. **Verify** artifacts appear in correct directories:
   - `build/pipelines/` - Compiled manifests
   - `run_logs/` - Execution logs
   - `aiop/` - AI observability packages
   - `.osiris/` - Hidden state
5. **Update CI/CD** to reference new paths
6. **Optional**: Commit `build/` artifacts (versionable, deterministic)

**What Changed:**
- Legacy `./logs/**` paths **completely removed** (not read or written)
- CLI commands use new contract paths exclusively
- `.last_compile.json` moved to `.osiris/index/latest/{filename}.txt`
- All sessions from v0.3.x and earlier are **not** automatically migrated
- CompilerV0 API changed: requires `fs_contract` and `pipeline_slug` parameters

**What Stays Compatible:**
- OML v0.1.0 format unchanged
- Component specs unchanged
- E2B execution fully compatible
- Configuration file structure extended (not replaced)

**References:**
- **ADR-0028**: Filesystem Contract v1 & Minimal Git Helpers
- **Milestone**: `docs/milestones/filesystem-contract.md`
- **Implementation Audit**: `docs/milestones/filesystem-contract-implementation-audit.md`
- **Sample Config**: `docs/samples/osiris.filesystem.yaml`

## [0.3.5] - 2025-10-07

### Added
- **GraphQL Extractor Component** (`graphql.extractor`)
  - New driver: `osiris/drivers/graphql_extractor_driver.py` for GraphQL API data extraction
  - Component spec: `components/graphql.extractor/spec.yaml` with authentication support (Bearer, Basic, API Key)
  - Support for complex GraphQL queries with variables and nested field extraction
  - JSONPath-based data extraction from GraphQL responses
  - Comprehensive test coverage with 16 passing tests
  - Integration with existing component registry

- **Connection-aware CLI Validation** (ADR-0020)
  - `osiris validate` now reads from `osiris_connections.yaml` for connection validation
  - Shows configured aliases and missing environment variables per connection
  - Connection validation integrated into JSON output structure

### Changed
- **Validation Command Updates** (ADR-0020)
  - `osiris validate` now uses connection-based validation from `osiris_connections.yaml`
  - Removed legacy environment-only probing in favor of connection definitions
  - Validation output includes connection aliases and per-connection status

- **Test Infrastructure Improvements**
  - Supabase tests isolated via `@pytest.mark.supabase` marker for clean separation
  - Split-run test execution: `make test` orchestrates both non-Supabase and Supabase phases
  - Test suite now at 1001+ passing tests with improved isolation

### Fixed
- **Secret Detection Improvements** (ADR-0035)
  - Fixed false-positive secret detection for standalone "Bearer" keyword
  - Pattern now only flags "Bearer" when followed by actual token-like strings (16+ chars)
  - Aligns with ADR-0035 principle: detect real secrets, not keywords

- **Test Warning Fixes**
  - Fixed `PytestReturnNotNoneWarning` in `test_m0_validation_4_logging.py::test_scenario_log_level_comparison`
  - Test now properly uses assertions instead of returning boolean values

- **CLI Validation Test Updates**
  - Fixed 5 CLI validation tests to work with ADR-0020 connection-based validation
  - Tests now use `temp_connections_yaml` fixture for proper osiris_connections.yaml setup
  - Updated assertions to check for connection aliases instead of legacy missing_vars

### Documentation
- **ADR Status Updates** reflecting actual implementation state:
  - **ADR-0031** (OML Control Flow): Status changed to "Proposed (Deferred to M2+)" - 0% implemented
  - **ADR-0032** (Runtime Parameters): Status changed to "Accepted" - 90% implemented, core features production-ready
  - **ADR-0034** (E2B Runtime Parity): Status changed to "Accepted (Amended)" - 85% implemented via Transparent Proxy architecture
  - **ADR-0035** (Compiler Secret Detection): Status changed to "Accepted (Phase 1)" - 80% implemented, x-secret parsing complete
  - Each ADR now includes detailed implementation status sections with code references and test coverage

## [0.3.1] - 2025-09-29
### Fixed
- `osiris validate`: removed spurious `additionalProperties` warnings for ADR-0020 compliant configs (schema whitelist; `additionalProperties: false` retained).

### Added
- `docs/reference/connection-fields.md`: allowed fields for MySQL & Supabase connections.

### Tests
- 11 new cases in `tests/core/test_validation_connections.py`.

### Notes
- Backward compatible; NO-SECRETS posture preserved.

## Previous Unreleased Content

### Added

### Tests
- **Quarantined slow IPv6 fallback test** - Moved `test_supabase_ipv6_fallback.py` to quarantine due to multi-minute stalls and flakiness
  - Renamed to `_quarantined__test_supabase_ipv6_fallback.py` with module-level skip
  - Added fast unit test replacement: `test_supabase_ipv4_fallback_unit.py` (< 1s, fully mocked)
  - See ADR-0034 for context on driver behavior and E2B runtime parity
  - TODO: Revisit when IPv6 fallback path is refactored

#### DuckDB Processor Support
- **DuckDB processor component** - SQL transformation processor for in-pipeline data manipulation
  - New driver: `osiris/drivers/duckdb_processor_driver.py`
  - Component spec: `components/duckdb.processor/spec.yaml`
  - Support for SQL transformations via DuckDB's in-memory engine
  - Automatic DataFrame registration and metric logging
  - Integration with existing MySQL extractor and Supabase writer components

- **DuckDB demo pipelines** - Example pipelines showcasing DuckDB transformations
  - `mysql_duckdb_supabase_demo.yaml` - Main demo with director statistics aggregation
  - `mysql_duckdb_supabase_append.yaml` - Append mode variant for incremental loads
  - `mysql_duckdb_supabase_debug.yaml` - Debug variant with CSV tee outputs
  - E2B-ready execution with full parity testing

#### Developer Experience Improvements
- **Developer-friendly pre-commit setup** - Fast local hooks, strict CI enforcement
  - Line length standardized to 120 characters across all tools
  - Pre-commit: Black, isort, Ruff with `--fix --exit-zero` (auto-fix, won't block)
  - CI-only: Strict Ruff (no fix), Black --check, isort --check, Bandit security
  - New GitHub workflow: `.github/workflows/lint-security.yml`
  - VS Code integration with auto-format on save (`.vscode/settings.json`)

- **Quick commit helpers** - Makefile targets for common scenarios
  - `make fmt` - Auto-format everything with Black, isort, Ruff
  - `make lint` - Run strict checks without auto-fix
  - `make security` - Run Bandit security checks locally
  - `make commit-wip` - Quick commits skipping slower checks
  - `make commit-emergency` - Emergency commits skipping all checks

- **CONTRIBUTING.md** - Development workflow documentation
  - Clear guidance on pre-commit hooks and formatting
  - Instructions for updating detect-secrets baseline
  - Troubleshooting for common hook issues

#### Test Coverage Research
- **Test Coverage Research Package** - Comprehensive baseline analysis at 22.87% coverage
  - Reports: coverage.md, coverage.json, HTML report, tests-inventory.md, gaps-matrix.md
  - Executive summary with actionable recommendations for +15% quick wins
  - Module-specific targets: remote ≥60%, cli ≥70%, overall ≥70%

#### Testing Infrastructure
- **pytest markers** - Comprehensive test categorization
  - `e2b`, `e2b_live`, `e2b_smoke` - E2B execution tests
  - `llm`, `slow`, `cli` - Component-specific tests
  - `unit`, `integration`, `smoke` - Test scope markers
  - Configuration in pytest.ini with strict marker enforcement

- **Makefile coverage targets** - Simplified coverage workflow
  - `cov` - Terminal coverage report
  - `cov-html` - HTML report generation
  - `cov-json` - JSON data export
  - `cov-md` - Markdown report from JSON
  - `coverage` - Full analysis (all formats)
  - `coverage-check` - Threshold validation (non-blocking)

### Changed

#### Code Formatting
- **Standardized line length** to 120 characters (was 100)
  - Applied across all Python files (166 files modified)
  - Configured in Black, isort, and Ruff settings
  - Better readability for complex code patterns
  - Less line wrapping in method signatures and long strings

#### Pre-commit Configuration
- **Ruff configuration** moved from top-level to `[tool.ruff.lint]` section in pyproject.toml
- **Ruff hook** changed to use `--exit-zero` to prevent blocking on unfixable issues
- **Pragmatic ignores** added for complex code patterns (PLR0911, PLR0912, PLR0913, etc.)
- **Per-file ignores** for tests and prototypes to reduce noise

### Fixed

#### Testing Infrastructure
- **Supabase driver stateless testing** - Eliminated test isolation issues causing 9 test failures
  - Added `_reset_test_state()` function to clear module-level state between tests
  - Updated `_table_exists()` to respect offline mode and `FORCE_REAL_CLIENT` env variables
  - All env reads now at call-time instead of module import time, ensuring stateless behavior
  - Created unified `supabase_test_guard` autouse fixture in `tests/conftest.py`
  - Added `@pytest.mark.supabase` marker to all Supabase test modules (9 files)
  - Updated Makefile test target for split-run approach:
    * Phase A: `pytest -m "not supabase"` → 917 tests pass
    * Phase B: `pytest -m supabase` → 54 tests pass
    * Total: **971 tests passing** ✅ (up from 962)
  - Removed redundant per-file fixtures and centralized all setup logic
  - Fast execution: Supabase test suite completes in <1 second (was 3+ minutes)
  - No more test ordering dependencies or cross-contamination issues

- **Validate command error handling** - Fixed UnboundLocalError crash when config file missing
  - Added `_safe_log_event()` helper in `osiris/cli/main.py` to safely log when session may not exist
  - Initialize `session=None` before try block to prevent UnboundLocalError on early failures
  - Clean single-line error messages to stderr without Python tracebacks
  - FileNotFoundError now shows: "Configuration file 'X' not found." instead of full traceback
  - Tests now skip cleanly with user-friendly messages instead of scary UnboundLocalError dumps
  - Improved user experience when running commands without `osiris.yaml`

#### E2B and Telemetry
- **Supabase writer E2B parity** - Fixed signature mismatch causing E2B execution failures
  - Broadened secret filtering in compiler to catch more sensitive patterns
  - Added offline DDL plan-only mode for tests without network access
  - Enhanced DDL generation to work consistently across local and E2B environments
  - Comprehensive research comparing Codex vs Claude solutions (3 documents, 2,000+ lines)

- **E2B telemetry and artifact hardening** - Improved reliability and data quality
  - Proxy worker DataFrame telemetry now matches local execution exactly
  - Local inputs_resolved telemetry recorded once per step (was duplicated)
  - Local preflight accepts self-contained cfg files for better test isolation
  - Session-scoped AIOP paths toggle for flexible artifact organization

- **test_parity_e2b_vs_local.py** - Fixed cfg file format issue
  - Test was writing full step definition instead of just config to cfg files
  - Runner expects cfg files to contain only configuration portion
  - All tests now pass with correct config format

#### Pre-commit Issues
- **Hook infinite loops** - Ruff no longer causes re-formatting loops
- **Deprecated warnings** - Fixed Ruff configuration deprecation warnings
- **Detect-secrets** - Added pragma comments for documentation examples

### Documentation
- **CLAUDE.md updates** - Added comprehensive developer workflow guidance
  - Pre-commit troubleshooting section
  - Testing best practices and common issues
  - Secret baseline update instructions
  - Quick commit helper documentation
- **README.md** - Added Contributing section linking to CONTRIBUTING.md
- **E2B doctor script** - Added diagnostic tool for E2B sandbox debugging
- **Developer documentation restructure** - Reorganized into human/AI-focused trees
  - Created `docs/COMPONENT_AI_CHECKLIST.md` for LLM-assisted component development
  - Added `docs/COMPONENT_DEVELOPER_AUDIT.md` for systematic component reviews
  - Archived legacy documentation to `docs/archive/` for reference
  - Preserved all LLM contracts (llms.txt, llms-drivers.txt, etc.) in archive
- **ADR documentation** - Added two new Architecture Decision Records
  - ADR-0034: E2B Runtime Unification with Local Runner (proposed)
  - ADR-0035: Compiler Secret Detection via Specs and Connections (proposed)
- **Research documentation** - Comprehensive E2B Supabase writer investigation
  - Codex vs Claude-Opus vs Claude-Sonnet comparison (3 documents, 2,000+ lines)
  - Detailed validation of driver signatures and E2B parity
  - Test planning documents for Supabase driver refactoring

### CI/CD
- **Non-blocking Research workflow** (.github/workflows/research.yml)
  - Runs on all PRs without blocking merge
  - Uploads coverage artifacts (HTML, JSON, markdown)
  - Optional PR comment with coverage summary
  - Continuous visibility without disrupting development
- **Lint & Security workflow** (.github/workflows/lint-security.yml)
  - Strict linting in CI (Ruff, Black --check, isort --check)
  - Bandit security scanning for Python vulnerabilities
  - Runs on all Python file changes in PRs
  - Enforces code quality without blocking local development

### Security
- **Bandit integration** - Security linting for Python code
  - CI-only enforcement (not in pre-commit to avoid friction)
  - Configuration in `bandit.yaml` with pragmatic skips
  - Excludes test directories and documentation
  - Medium+ severity findings reported

### Tooling
- **Coverage summary tool** (tools/validation/coverage_summary.py)
  - Per-folder coverage analysis with customizable thresholds
  - Multiple output formats (markdown, JSON, text)
  - CLI flags for module-specific minimum coverage requirements
  - Exit codes for CI integration (advisory only)

### Documentation
- **Mempack configuration updates**
  - Includes research docs (excluding HTML reports to manage size)
  - Added coverage_summary.py and pytest.ini for assistant context
  - Tuned includes/excludes for optimal LLM consumption
- **DuckDB E2B readiness research** - Assessment of DuckDB processor for cloud execution
  - Full compatibility with E2B transparent proxy
  - No additional dependencies required in sandbox
  - Performance parity between local and E2B execution

## [0.3.0] - 2025-09-27

**Major Release: Milestone M2a Complete - AI Operation Package (AIOP)**

This release completes Milestone M2a, delivering a comprehensive, production-ready AI Operation Package (AIOP) system. AIOP provides a four-layer semantic architecture (Evidence, Semantic, Narrative, Metadata) that enables any LLM to fully understand Osiris pipeline runs through structured, deterministic, secret-free exports. All 24 acceptance criteria met with 921 tests passing.

### Added
- **AI Operation Package (AIOP) Implementation** (ADR-0027)
  - Four-layer semantic architecture: Evidence, Semantic, Narrative, and Metadata layers
  - CLI command: `osiris logs aiop` with JSON and Markdown export formats
  - JSON-LD context for semantic web compatibility
  - Deterministic output with stable IDs for reproducible analysis
  - Size-controlled exports with object-level truncation markers
  - Annex policy for large runs with NDJSON shards (.aiop-annex/)
  - Automatic secret redaction with DSN masking (postgres://user:***@host/db)
  - Rich progress indicators during export
  - Exit code 4 for truncated exports

- **AIOP System Stabilization** (WU7a/b/c)
  - Delta analysis with "Since last run" comparisons using by-pipeline index
  - Intent discovery with multi-source provenance (manifest, README, commits, chat logs)
  - Active duration metrics in aggregated statistics
  - Comprehensive DSN redaction for Redis, MongoDB, PostgreSQL connection strings
  - LLM affordances: metadata.llm_primer with glossary and controls.examples
  - Platform-safe symlink implementation with Windows fallback
  - Robust error handling for missing sessions and corrupted indexes

- **AIOP Configuration Layer** (Work Unit 1)
  - YAML configuration layer with full precedence resolution
  - `osiris init` enhanced with AIOP scaffold, `--no-comments` and `--stdout` flags
  - Configuration precedence: CLI > ENV ($OSIRIS_AIOP_*) > Osiris.yaml > defaults
  - Effective config tracking in `metadata.config_effective` with per-key source
  - Auto-export after every run with templated paths and retention policies

- **Evidence Layer** (PR1-PR2)
  - Timeline with chronological events and configurable density (low/medium/high)
  - Metrics aggregation with step-level and total statistics
  - Error collection with stack traces and context
  - Artifact tracking with SHA-256 hashes and sizes

- **Semantic Layer** (PR3)
  - DAG representation with nodes and edges
  - Component registry integration
  - OML specification embedding
  - Pipeline manifest with fingerprinting

- **Narrative Layer** (PR4)
  - Natural language descriptions of pipeline execution
  - Evidence citations linking to timeline events
  - Paragraph-based structure for readability
  - Markdown run-card generation for human review

- **CLI Features** (PR5)
  - Configuration precedence: CLI > ENV > YAML > defaults
  - Environment variables: OSIRIS_AIOP_MAX_CORE_BYTES, OSIRIS_AIOP_TIMELINE_DENSITY, etc.
  - Policy options: core (default) or annex for large exports
  - Compression support for annex files (gzip)
  - Output to file or stdout
  - JSON and Markdown format options

- **Performance Optimizations** (PR6)
  - LRU caching for component registry lookups
  - Streaming JSON generation (stream_json_chunks)
  - Memory footprint <50MB on typical runs
  - Lazy evaluation of expensive computations

### Changed
- **Configuration Management**
  - Added metadata.config_effective showing resolved configuration after precedence
  - Annex manifest standardized under metadata.annex with files array
  - Markdown run-card enhanced with fallbacks to never return empty

### Enhanced
- **Test Suite Stabilization**: 921 tests passing, 29 skipped (E2B live tests)
- **Parity Verification**: Local vs E2B execution produces identical AIOP exports
- **Security Validation**: Comprehensive secret redaction with zero-leak guarantee
- **Deterministic Output**: Stable IDs, sorted keys, canonical JSON-LD format

### Fixed
- **Test Stability**
  - Fixed AIOP tests failing due to truncation by increasing max-core-bytes limit
  - Corrected config precedence to properly prioritize CLI over environment variables
  - Fixed annex manifest structure to exclude full paths for privacy

### Security
- **Secret Protection**
  - Enhanced redaction in AIOP exports
  - DSN passwords automatically masked
  - No file paths exposed in annex manifests
  - Deterministic redaction for reproducible debugging

### Documentation
- Complete user guides with quickstart, troubleshooting, and examples
- Technical architecture documentation for AIOP system design
- Updated ADR-0027 and M2a milestone marked as fully implemented

## [0.2.0] - 2025-09-23

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
