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

### Logging & Events Integration

The registry emits four distinct events to the SessionContext:

#### Registry Loading Events
```python
# Emitted at start of load_specs()
self.session_context.log_event(
    "registry_load_start", 
    root=str(search_root)  # Path being searched
)

# Emitted after all specs processed
self.session_context.log_event(
    "registry_load_complete",
    root=str(search_root),          # Path that was searched
    components_loaded=len(specs),    # Number of valid specs loaded
    errors=errors                    # List of error messages for invalid specs
)
```

#### Validation Events
```python
# Emitted at start of validate_spec()
self.session_context.log_event(
    "component_validation_start", 
    component=name_or_path,  # Component name or file path
    level=level              # "basic", "enhanced", or "strict"
)

# Emitted after validation completes
self.session_context.log_event(
    "component_validation_complete",
    component=name_or_path,
    level=level,
    is_valid=len(errors) == 0,  # Boolean validation result
    error_count=len(errors)      # Number of validation errors
)
```

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

### Validate Component
```bash
# Enhanced validation (default when level not specified)
python osiris.py components validate mysql.writer

# Explicit validation levels (actual parameter: level="enhanced")
python osiris.py components validate mysql.writer --level basic
python osiris.py components validate mysql.writer --level enhanced
python osiris.py components validate supabase.extractor --level strict
```

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

### Automated Test Suite
All 13 tests passing with 100% success rate:

```bash
$ pytest tests/components/test_registry.py -v
============================= test session starts ==============================
collected 13 items

tests/components/test_registry.py::TestComponentRegistry::test_load_specs PASSED
tests/components/test_registry.py::TestComponentRegistry::test_get_component PASSED
tests/components/test_registry.py::TestComponentRegistry::test_list_components PASSED
tests/components/test_registry.py::TestComponentRegistry::test_validate_spec_basic PASSED
tests/components/test_registry.py::TestComponentRegistry::test_validate_spec_enhanced PASSED
tests/components/test_registry.py::TestComponentRegistry::test_validate_spec_strict PASSED
tests/components/test_registry.py::TestComponentRegistry::test_validate_spec_path PASSED
tests/components/test_registry.py::TestComponentRegistry::test_get_secret_map PASSED
tests/components/test_registry.py::TestComponentRegistry::test_cache_invalidation PASSED
tests/components/test_registry.py::TestComponentRegistry::test_clear_cache PASSED
tests/components/test_registry.py::TestComponentRegistry::test_session_context_integration PASSED
tests/components/test_registry.py::TestComponentRegistry::test_get_registry_singleton PASSED
tests/components/test_registry.py::TestComponentRegistry::test_parent_directory_fallback PASSED

============================== 13 passed in 0.64s ==============================
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
  
- **M1c**: Compiler and Manifest Generation
  - Compile OML to deterministic Run Manifests
  - Generate per-step configuration files
  - Ensure reproducible pipeline execution

- **M1d**: Pipeline Runner MVP
  - Execute compiled manifests locally
  - Integrate with existing connectors
  - Generate structured logs with secret masking

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
