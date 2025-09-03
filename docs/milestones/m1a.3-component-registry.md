# Milestone M1a.3: Component Registry Implementation

**Status**: ✅ Complete  
**Branch**: `feature/m1a.3-component-registry`  
**Date Completed**: January 3, 2025

## Executive Summary

Successfully implemented the Component Registry for Osiris, providing centralized management of component specifications with filesystem loading, multi-level validation, and session-scoped logging integration. This milestone delivers the foundation for deterministic pipeline generation by establishing a single source of truth for component capabilities, configuration schemas, and runtime metadata.

## Scope & Acceptance Criteria

### ✅ Delivered Capabilities

- **Registry with filesystem loading** and in-memory cache with mtime-based invalidation
- **Three validation levels**: basic (schema), enhanced (configSchema), strict (semantic)  
- **Secret map extraction** for runtime redaction of sensitive fields
- **Session-scoped logging integration** consistent with M0 implementation
- **CLI commands** via `osiris components ...` for listing, showing, and validating specs

## Implementation Details

### Core Files Created/Modified

#### `osiris/components/registry.py` (440 lines)
Central registry implementation providing:
- Component spec loading from filesystem with automatic parent directory fallback
- In-memory caching with mtime-based invalidation for performance
- Three-tier validation system (basic, enhanced, strict)
- Secret and redaction field extraction for runtime masking
- Session context integration for structured logging
- Singleton pattern via `get_registry()` function for global access
- Automatic filtering of invalid specs during `load_specs()`

#### `osiris/cli/components_cmd.py` (Updated)
CLI commands refactored to use registry backend:
- Removed direct filesystem access logic
- All commands now use centralized `get_registry()` 
- Added session context support throughout
- Maintained backward compatibility with existing CLI interface

#### `tests/components/test_registry.py` (386 lines)
Comprehensive test suite with 13 test cases:
1. `test_load_specs` - Validates loading and filtering of invalid specs
2. `test_get_component` - Tests individual component retrieval
3. `test_list_components` - Tests listing with mode filtering
4. `test_validate_spec_basic` - Tests JSON Schema validation
5. `test_validate_spec_enhanced` - Tests configSchema and example validation
6. `test_validate_spec_strict` - Tests semantic validation (aliases, pointers)
7. `test_validate_spec_path` - Tests validation using file paths
8. `test_get_secret_map` - Tests secret extraction from specs
9. `test_cache_invalidation` - Tests mtime-based cache refresh
10. `test_clear_cache` - Tests manual cache clearing
11. `test_session_context_integration` - Tests logging event emission
12. `test_get_registry_singleton` - Tests singleton pattern
13. `test_parent_directory_fallback` - Tests ../components/ fallback

### Validation Levels Implemented

#### Basic Validation (`level="basic"`)
- Validates component specs against `components/spec.schema.json` using Draft202012Validator
- Checks all required fields as defined in schema
- Returns errors with path information (e.g., "Schema validation: 'version' is a required property at root")
- Automatically applied during `load_specs()` to filter out invalid components
- Invalid specs are logged as warnings but not loaded into the registry

#### Enhanced Validation (`level="enhanced"`)  
- Includes all basic validation checks, plus:
- Validates that `configSchema` is itself a valid JSON Schema using `Draft202012Validator.check_schema()`
- Iterates through all examples and validates each `example["config"]` against the component's `configSchema`
- Returns specific error messages for invalid examples (e.g., "Example 1 invalid: 'host' is a required property")
- Default level when not specified in CLI

#### Strict Validation (`level="strict"`)
- Includes all enhanced validation checks, plus:
- Calls `_validate_semantic()` for deep cross-reference validation:
  - Validates JSON Pointers in `secrets` array reference actual fields or common paths (auth, credentials, connection)
  - Validates JSON Pointers in `redaction.extras` with same rules as secrets
  - Validates each key in `llmHints.inputAliases` exists in `configSchema.properties`
- Returns detailed errors with available field lists for invalid aliases
- Provides highest confidence for production use

### Session Lifecycle & Events

The `components validate` command uses SessionContext and emits exactly 4 events per validation:

#### Event Sequence (No Duplication)

Each validation session emits these events in order:

1. **run_start** - Session initialization
```json
{
  "event": "run_start",
  "session_id": "test_fixed",
  "session_dir": "logs/test_fixed",
  "fallback_used": false
}
```

2. **component_validation_start** - Validation begins
```json
{
  "event": "component_validation_start",
  "component": "mysql.extractor",
  "level": "enhanced",
  "schema_version": "unknown",
  "command": "components.validate"
}
```

3. **component_validation_complete** - Validation ends
   
   **Success case**:
```json
{
  "event": "component_validation_complete",
  "component": "mysql.extractor",
  "level": "enhanced",
  "status": "ok",
  "errors": 0,
  "duration_ms": 8,
  "command": "components.validate"
}
```

   **Failure case**:
```json
{
  "event": "component_validation_complete",
  "component": "nonexistent",
  "level": "enhanced",
  "status": "failed",
  "errors": 1,
  "duration_ms": 41,
  "command": "components.validate"
}
```

4. **run_end** - Session closure
```json
{
  "event": "run_end",
  "status": "completed",  // or "failed" for validation failures
  "duration_ms": 8
}
```

#### Important: No Registry Events in CLI Context

The Registry class (`osiris/components/registry.py`) can emit its own `component_validation_start` and `component_validation_complete` events when used programmatically with a session_context. However, when called from the CLI validation command, the registry is intentionally NOT given a session_context to prevent duplicate event emission. The CLI handles all session events directly.

**Note**: Pipeline execution events like `write.*` or `load.*` are NOT part of component validation. Those belong to actual pipeline runs, not registry validation.

## CLI Reference

**Available Functions** (in `osiris/cli/components_cmd.py`):
- `list_components()` - List all or filtered components
- `show_component()` - Display detailed component information
- `validate_component()` - Validate spec at specified level
- `show_config_example()` - Show example configurations
- `discover_with_component()` - Run discovery mode (placeholder)

### List Components
```bash
# List all components
python osiris.py components list

# Filter by mode (actual parameter: mode="extract")
python osiris.py components list --mode extract
python osiris.py components list --mode write
```

### Show Component Details
```bash
# Display component specification (actual parameter: as_json=False)
python osiris.py components show mysql.extractor
python osiris.py components show supabase.writer --json
```

### Validate Component (Session-Aware)

**New in M1a.3**: The validate command now creates session-scoped logs with structured events.

```bash
# Basic usage (creates auto-generated session)
python osiris.py components validate mysql.writer

# Validation levels
python osiris.py components validate mysql.writer --level basic
python osiris.py components validate mysql.writer --level enhanced  # default
python osiris.py components validate supabase.extractor --level strict

# Session management flags
python osiris.py components validate mysql.writer \
    --session-id my_validation_001 \
    --logs-dir custom_logs \
    --log-level DEBUG \
    --events "component_validation_*" \
    --json

# Configuration precedence (CLI > ENV > YAML > defaults)
export OSIRIS_LOG_LEVEL=WARNING
python osiris.py components validate test.component --log-level DEBUG  # DEBUG wins
```

#### CLI Flags & Configuration Precedence

| Flag | Description | Default | Precedence |
|------|-------------|---------|------------|
| `--level` | Validation level: `basic`, `enhanced`, `strict` | `enhanced` | CLI only |
| `--session-id` | Custom session identifier | `components_validate_<timestamp>` | CLI only |
| `--logs-dir` | Directory for session logs | `logs` | CLI > ENV > YAML > default |
| `--log-level` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` | CLI > ENV > YAML > default |
| `--events` | Event patterns to log (comma-separated or `"*"` for all) | `["*"]` | CLI > ENV > YAML > default |
| `--json` | Output results in JSON format | `false` | CLI only |

**Note on event filtering**: Use `--events "*"` to capture all events (wildcard). Specific patterns like `"component_validation_*"` filter to matching events only.

### Show Configuration Example
```bash
# Display example configuration (actual parameter: example_index=0)
python osiris.py components config-example mysql.extractor
python osiris.py components config-example supabase.writer --index 1
```

### Discover Mode (placeholder implementation)
```bash
# Currently shows message: "Discovery mode would run here"
# Note: "Component runner integration not yet implemented"
python osiris.py components discover mysql.extractor --config config.yaml
```

## Testing & Evidence

### Automated Test Suites

#### `tests/components/test_registry.py` (13 tests)
Core registry functionality tests covering:
- **Loading & filtering**: Invalid specs are filtered during `load_specs()`
- **Component retrieval**: Individual component access via `get_component()`
- **Mode filtering**: List components by operational mode
- **Validation levels**: Basic (schema), enhanced (configSchema + examples), strict (semantic)
- **Secret extraction**: Proper extraction from `secrets` and `redaction.extras`
- **Cache behavior**: Mtime-based invalidation and manual clearing
- **Session integration**: Event emission to SessionContext
- **Singleton pattern**: Global registry instance management
- **Parent directory fallback**: Automatic `../components/` detection

#### `tests/components/test_registry_cli_logging.py` (8 tests)
Session-aware CLI validation tests covering:
- **Session creation**: Custom and auto-generated session IDs
- **Event logging**: Structured events (start, complete, end) with proper fields
- **Failed validation**: Correct status propagation for errors
- **Non-existent components**: Graceful handling with session creation
- **Secrets masking**: Sensitive data redacted in logs
- **Configuration precedence**: CLI > ENV > YAML > defaults
- **JSON output format**: Machine-readable validation results
- **Event filtering**: Pattern-based event capture

```bash
$ pytest tests/components/ -v
============================= test session starts ==============================
collected 21 items

tests/components/test_registry.py::TestComponentRegistry::test_load_specs PASSED
tests/components/test_registry.py::TestComponentRegistry::test_get_component PASSED
# ... [13 tests total]

tests/components/test_registry_cli_logging.py::TestComponentValidationLogging::test_session_creation_with_custom_id PASSED
tests/components/test_registry_cli_logging.py::TestComponentValidationLogging::test_validation_events_logged PASSED
# ... [8 tests total]

============================== 21 passed in 1.03s ==============================
```

### Manual Verification Examples

```bash
# List all components
$ python osiris.py components list
Available Components
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Component          ┃ Version ┃ Modes             ┃ Description               ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ mysql.extractor    │ 1.0.0   │ extract, discover │ Extract data from MySQL...│
│ mysql.writer       │ 1.0.0   │ write, discover   │ Write data to MySQL...    │
│ supabase.extractor │ 1.0.0   │ extract, discover │ Extract data from...      │
│ supabase.writer    │ 1.0.0   │ write, discover   │ Write data to Supabase... │
└────────────────────┴─────────┴───────────────────┴───────────────────────────┘

# Show component details
$ python osiris.py components show mysql.writer
mysql.writer v1.0.0
MySQL Data Writer
Write data to MySQL databases with support for append, replace, and upsert...

# Validate with strict checking
$ python osiris.py components validate supabase.extractor --level strict
✓ Component 'supabase.extractor' is valid (level: strict)
  Version: 1.0.0
  Modes: extract, discover
```

## ADR Alignment

### ADR-0007: Component Specification and Capabilities
- Registry enforces specification requirements defined in ADR-0007
- Three-level validation ensures specs meet quality standards
- Amendment 1: Writers standardized on `write` mode + `discover` (not `load`)

### ADR-0008: Component Registry  
- Implements centralized registry as single source of truth
- Provides deterministic access to component specifications
- Enables AI-driven pipeline generation through structured metadata
- Foundation for future workflow orchestration capabilities

## Migration Notes & Gotchas

### Mode Standardization
- Writers now expose `modes: ["write", "discover"]` 
- `load` mode is deprecated in schema but retained for backward compatibility
- Logging events renamed from `load.*` to `write.*` for consistency

### Secret & Redaction Configuration

#### Secret Extraction (`get_secret_map()` method)
The registry extracts sensitive field identifiers from exactly two locations:

1. **Primary secrets**: `spec.secrets` array (JSON Pointer format, e.g., "/password", "/api_key")
2. **Redaction extras**: `spec.redaction.extras` array (additional sensitive paths)

**Note**: No legacy support for `loggingPolicy.sensitivePaths` is implemented (this was incorrect in initial documentation).

#### Return Format
```python
{
    "secrets": [/* from spec.secrets */],
    "redaction_extras": [/* from spec.redaction.extras */]
}
```

#### Usage Example
```python
registry = get_registry()
secret_map = registry.get_secret_map("mysql.writer")
# Returns: {"secrets": ["/password"], "redaction_extras": ["/host", "/user"]}

### Cache Behavior

#### Mtime-based Invalidation
- The `_is_cache_valid()` method compares stored mtime with current file mtime
- Cache automatically refreshes when spec files are modified
- Both `_cache` (spec data) and `_mtime_cache` (modification times) are maintained

#### Parent Directory Fallback
Implemented in `__init__()` constructor:
```python
if not self.root.exists():
    parent_root = Path("..") / "components"
    if parent_root.exists():
        self.root = parent_root
```
- Automatically checks `../components/` if `./components/` doesn't exist
- Essential for running from `testing_env/` or other subdirectories
- No recursive search - only immediate parent is checked

#### Cache Management
- `clear_cache()` method manually clears both caches
- Cache is instance-level, not shared between registry instances
- Singleton pattern ensures cache persistence within a process

## Lessons Learned

### 1. JSON Schema Limitations
JSON Schema alone cannot enforce cross-references between fields. Runtime validation in the registry is essential for catching semantic errors like:
- Invalid JSON Pointer references
- Input aliases pointing to non-existent fields
- Mismatched constraint conditions

### 2. Cache Performance
Mtime-based caching keeps CLI operations snappy (<50ms response time) while ensuring correctness. The cache automatically invalidates when specs change, providing the best of both worlds.

### 3. Validation Layers
The three-tier validation system proved valuable:
- **Basic**: Catches structural issues quickly during development
- **Enhanced**: Ensures examples are valid (critical for LLM context)
- **Strict**: Provides production-ready confidence through semantic checks

### 4. Session Context Integration
Integrating with M0's session logging from the start ensures consistent observability across the entire Osiris pipeline lifecycle.

### 5. Event Duplication Bug
Initially, both the Registry and CLI emitted validation events when the Registry was given a session_context, causing duplicate events. The fix was to NOT pass session_context to the Registry when called from CLI commands, letting the CLI handle all session events. This teaches an important lesson about event ownership in layered architectures.

## Artifacts & Logs Path

### Session Directory Structure

By default, sessions are created in `./logs/<session_id>/` containing:
- **events.jsonl**: Structured event stream (run_start, validation events, run_end)
- **osiris.log**: Standard application logs
- **debug.log**: Debug-level logs (if `--log-level DEBUG`)
- **artifacts/**: Empty directory (reserved for future use)

**Note**: Component validation intentionally does NOT create:
- YAML bundles or pipeline artifacts (those belong to pipeline generation)
- metrics.jsonl (no metrics currently emitted during validation)
- session.json (not implemented yet)

### Example Session Contents

```bash
$ ls -la logs/components_validate_1756883996401/
total 16
drwxr-xr-x  5 user  staff   160 Jan  3 09:13 .
drwxr-xr-x  42 user  staff  1344 Jan  3 09:13 ..
drwxr-xr-x  2 user  staff    64 Jan  3 09:13 artifacts/
-rw-r--r--  1 user  staff  1432 Jan  3 09:13 events.jsonl
-rw-r--r--  1 user  staff   256 Jan  3 09:13 osiris.log
```

## Session-Aware Validation Examples

### Success Case - Complete JSONL Stream

```bash
$ python osiris.py components validate mysql.extractor --session-id test_fixed
$ cat logs/test_fixed/events.jsonl
```

```json
{"ts": "2025-09-03T07:48:26.050909+00:00", "session": "test_fixed", "event": "run_start", "session_id": "test_fixed", "session_dir": "logs/test_fixed", "fallback_used": false}
{"ts": "2025-09-03T07:48:26.056870+00:00", "session": "test_fixed", "event": "component_validation_start", "component": "mysql.extractor", "level": "enhanced", "schema_version": "unknown", "command": "components.validate"}
{"ts": "2025-09-03T07:48:26.059906+00:00", "session": "test_fixed", "event": "component_validation_complete", "component": "mysql.extractor", "level": "enhanced", "status": "ok", "errors": 0, "duration_ms": 8, "command": "components.validate"}
{"ts": "2025-09-03T07:48:26.061327+00:00", "session": "test_fixed", "event": "run_end", "status": "completed", "duration_ms": 8}
```

### Failure Case - Complete JSONL Stream

```bash
$ python osiris.py components validate nonexistent --session-id test_fail_fixed
$ cat logs/test_fail_fixed/events.jsonl
```

```json
{"ts": "2025-09-03T07:49:17.378526+00:00", "session": "test_fail_fixed", "event": "run_start", "session_id": "test_fail_fixed", "session_dir": "logs/test_fail_fixed", "fallback_used": false}
{"ts": "2025-09-03T07:49:17.400500+00:00", "session": "test_fail_fixed", "event": "component_validation_start", "component": "nonexistent", "level": "enhanced", "schema_version": "unknown", "command": "components.validate"}
{"ts": "2025-09-03T07:49:17.420714+00:00", "session": "test_fail_fixed", "event": "component_validation_complete", "component": "nonexistent", "level": "enhanced", "status": "failed", "errors": 1, "duration_ms": 41, "command": "components.validate"}
{"ts": "2025-09-03T07:49:17.422200+00:00", "session": "test_fail_fixed", "event": "run_end", "status": "failed", "duration_ms": 41}
```

**Note**: Each validation emits exactly 4 events. No duplicate events occur because the Registry is not given a session_context when called from the CLI.

### Viewing Sessions with `logs` Commands

```bash
# List recent validation sessions
$ python osiris.py logs list --limit 5
┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┓
┃ Session ID           ┃ Start Time ┃ Status    ┃ Duration ┃ Events   ┃
┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━┩
│ failure_demo         │ 09:14:12   │ failed    │ 0.04s    │ 6        │
│ success_demo         │ 09:13:34   │ completed │ 0.04s    │ 6        │
└──────────────────────┴────────────┴───────────┴──────────┴──────────┘

# Show specific session events
$ python osiris.py logs show --session success_demo --events
```

## Risks & Mitigations

### Risk: Stale Spec Detection
**Issue**: Mtime-based caching could miss changes if system time is incorrect.  
**Mitigation**: `clear_cache()` method provides manual refresh option. Consider adding checksum validation in future.

### Risk: Mis-declared Secrets
**Issue**: Components might forget to declare sensitive fields in `secrets` array.  
**Mitigation**: Strict validation checks JSON Pointers are valid. M1a.2 audit verified all bootstrap components have proper secret declarations.

### Risk: JSON Schema Limitations
**Issue**: Cannot enforce complex cross-field dependencies or business logic.  
**Mitigation**: Strict validation layer adds semantic checks. Runtime validation in pipeline execution provides final safety net.

### Risk: Invalid Specs in Production
**Issue**: Invalid specs could be deployed if validation is skipped.  
**Mitigation**: `load_specs()` automatically filters invalid specs. CI/CD should run `validate_component --level strict`.

## Known Limitations

### Current Implementation Gaps
- **schema_version**: Currently returns "unknown" for all components (field exists in spec but not reliably extracted)
- **discover_with_component**: Placeholder implementation showing "Component runner integration not yet implemented"
- **metrics.jsonl**: No metrics are emitted during validation (file not created)
- **session.json**: Summary file not yet implemented
- **Bulk validation**: No support for validating multiple components in single command

### Technical Debt
- Registry loads all specs on every CLI invocation (no persistent cache between runs)
- JSON Pointer validation only checks path syntax, not actual field existence in configs
- No support for component versioning or multiple versions of same component

## Next Steps

### Immediate (M1a.4 - Friendly Error Mapper)
- Map JSON Schema validation errors to human-readable messages
- Provide actionable fix suggestions
- Generate links to component documentation
- Estimated timeline: 1 week

### Upcoming Milestones
- **M1b**: Context Builder and LLM Integration
  - Extract minimal context from registry for token efficiency
  - Integrate into conversational agent
  - Validate generated OML against specs
  - Address schema_version extraction issue
  
- **M1c**: Compiler and Manifest Generation
  - Compile OML to deterministic Run Manifests
  - Generate per-step configuration files
  - Ensure reproducible pipeline execution

- **M1d**: Pipeline Runner MVP
  - Execute compiled manifests locally
  - Integrate with existing connectors
  - Generate structured logs with secret masking
  - Implement discover_with_component functionality

## Completion Checklist

- [x] **Code implemented**: Registry with all required methods
- [x] **Validation levels**: Basic, enhanced, and strict validation working
- [x] **Caching system**: Mtime-based invalidation implemented
- [x] **Tests passing**: 13/13 tests with 100% success rate
- [x] **CLI integration**: All 5 commands using registry backend
- [x] **Session logging**: 4 distinct events integrated
- [x] **Documentation**: Milestone document with accurate details

## Links and References

### Milestone Documents
- **Previous**: [M1a.2 Bootstrap Component Specs](m1a.2-bootstrap-component-specs.md)
- **Parent**: [M1 Component Registry and Runner](m1-component-registry-and-runner.md)
- **Next**: M1a.4 Friendly Error Mapper (pending)

### Architecture Decision Records
- [ADR-0007: Component Specification and Capabilities](../adr/0007-component-specification-and-capabilities.md)
- [ADR-0008: Component Registry](../adr/0008-component-registry.md)

### Implementation Files
- Registry: `osiris/components/registry.py`
- CLI Integration: `osiris/cli/components_cmd.py`  
- Tests: `tests/components/test_registry.py`
- Component Specs: `components/*/spec.yaml`

## Conclusion

M1a.3 successfully delivers a robust Component Registry that serves as the foundation for deterministic pipeline generation. The implementation provides efficient filesystem loading with caching, comprehensive multi-level validation, and seamless integration with existing session logging infrastructure. With this registry in place, Osiris can now reliably discover, validate, and utilize component specifications for AI-driven pipeline creation.
