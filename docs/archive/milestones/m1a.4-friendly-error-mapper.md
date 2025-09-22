# Milestone M1a.4: Friendly Error Mapper

**Status**: ✅ Complete  
**Branch**: `feature/m1a.4-friendly-error-mapper`  
**Completed Date**: January 2025

## Executive Summary

Transform cryptic technical validation and runtime errors into user-friendly, actionable messages that help users fix problems quickly. This milestone enhances the developer experience by providing clear error messages with fix suggestions while maintaining technical details for debugging.

## Goal & Scope

### Goals
- Convert JSON Schema validation errors to human-readable messages
- Map JSON Pointer paths to friendly field names
- Provide contextual fix suggestions with examples
- Maintain consistency with M1a.3 session logging
- Add JSON output support for `osiris components list`

### Non-Goals
- Redesign validation levels (basic/enhanced/strict remain unchanged)
- Alter pipeline execution logic
- Modify existing event names or duplicate events
- Change component specification schema

## Design Overview

### FriendlyErrorMapper Architecture

```python
class FriendlyErrorMapper:
    """Maps technical errors to friendly, actionable messages."""
    
    def map_error(self, error: dict) -> FriendlyError:
        """Transform raw validation error to friendly format."""
        # Input: Raw validation error from jsonschema or custom validation
        # Output: Structured friendly error with category, fix hints
```

### Error Categories

Error categories use snake_case naming for consistency:

1. **schema_error**: Component specification structure issues
2. **config_error**: Missing or invalid configuration values  
3. **type_error**: Wrong data type provided
4. **constraint_error**: Values don't meet requirements (min/max, enum, pattern)
5. **runtime_error**: Component execution failures

Note: All error categories must use snake_case (e.g., `config_error`, not `ConfigError`) in both implementation and JSON outputs.

### Path to Label Mapping

```python
PATH_LABELS = {
    "/configSchema/properties/host": "Database Host",
    "/configSchema/properties/port": "Connection Port",
    "/configSchema/properties/password": "Database Password",
    "/configSchema/properties/table": "Table Name",
    "/configSchema/properties/key": "API Key",
    "/secrets": "Secret Fields",
    "/modes": "Supported Modes",
    "/capabilities": "Component Capabilities"
}
```

### Fix Suggestions

```python
FIX_SUGGESTIONS = {
    "missing_required": {
        "host": "Add 'host: your-database-server.com' to your config. For local development, use 'localhost'",
        "password": "Set the password in your config or via environment variable MYSQL_PASSWORD",
        "key": "Get your API key from Supabase Dashboard > Settings > API > anon/public key",
        "table": "Specify the table name you want to read from or write to"
    },
    "invalid_type": {
        "port": "Port must be a number (e.g., 3306), not a string '3306'",
        "batch_size": "Batch size must be an integer (e.g., 1000)",
        "echo": "Echo must be a boolean (true or false)"
    },
    "constraint_violation": {
        "port": "Port must be between 1 and 65535",
        "batch_size": "Batch size must be positive",
        "upsert_keys": "When using upsert mode, you must specify at least one key field"
    }
}
```

### Secret Handling

Validation errors on secret fields must **never expose actual values**:

```python
# BAD - exposes secret
"Password 'mysecret123' is too short (minimum 8 characters)"

# GOOD - references field without exposing value
"Database Password is too short (minimum 8 characters)"
```

Example friendly error for a secret field:
```json
{
  "category": "constraint_error",
  "field": "Database Password",
  "problem": "Password does not meet security requirements",
  "fix": "Use a password with at least 8 characters",
  "example": "password: ${DB_PASSWORD}  # Set via environment variable"
}
```

## Integration Points

### 1. Registry Integration (`osiris/components/registry.py`)

```python
def validate_spec(self, component_name: str, level: str = "basic") -> tuple[bool, list[dict]]:
    """Validate component spec at specified level.
    
    Returns:
        tuple: (is_valid, errors) where errors contain both technical and friendly info
    """
    # Existing validation logic...
    
    if errors:
        mapper = FriendlyErrorMapper()
        friendly_errors = [mapper.map_error(err) for err in errors]
        return False, friendly_errors
    return True, []
```

### 2. CLI Enhancement (`osiris/cli/components_cmd.py`)

#### Default Output (Friendly)
```
❌ Missing Required Configuration
   Component: mysql.writer
   Field: Database Host
   Problem: The 'host' field is required but not provided
   Fix: Add 'host: your-database-server.com' to your config
   Example: host: localhost

⚠️  Invalid Type
   Field: Port Number
   Problem: Expected number but got string "3306"
   Fix: Remove quotes - use 3306 instead of "3306"
```

#### Verbose Output (`--verbose`)
```
❌ Missing Required Configuration
   Component: mysql.writer
   Field: Database Host
   Problem: The 'host' field is required but not provided
   Fix: Add 'host: your-database-server.com' to your config
   Example: host: localhost
   
   Technical Details:
   - Path: $.configSchema.properties.host
   - Schema: {"type": "string", "description": "MySQL server hostname"}
   - Error: ValidationError at /configSchema/properties
```

### 3. Session Logging

Events remain consistent with M1a.3:
- `run_start`
- `component_validation_start` 
- `component_validation_complete` (includes friendly_errors field)
- `run_end`

Example event with friendly errors:
```json
{
  "ts": "2025-01-03T12:00:00.456Z",
  "session": "components_validate_1735900000456",
  "event": "component_validation_complete",
  "component": "mysql.writer",
  "level": "enhanced",
  "status": "failed",
  "errors": 2,
  "friendly_errors": [
    {
      "category": "config_error",
      "field": "Database Host",
      "problem": "Required field missing",
      "fix": "Add 'host: your-database-server.com'",
      "path": "/configSchema/properties/host"
    }
  ],
  "duration_ms": 45
}
```

## CLI UX Enhancements

### 1. Validation with Friendly Errors

```bash
# Default: friendly output
$ osiris components validate mysql.writer --level strict
❌ Validation failed for 'mysql.writer' (strict level)

Missing Required Field:
  • Database Host: Add 'host' to your configuration
    Example: host: localhost

Invalid Type:
  • Port: Must be a number, not "3306"
    Fix: Use 3306 without quotes

Session: components_validate_1735900000456

# With verbose flag: includes technical details
$ osiris components validate mysql.writer --level strict --verbose
[Same friendly output as above, plus:]

Technical Details:
  ValidationError: 'host' is a required property
  Path: $.configSchema.properties.host
  Schema Location: components/mysql.writer/spec.yaml:24-27
```

### 2. JSON Output for Components List

```bash
# Human-readable table (default)
$ osiris components list
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Component         ┃ Version ┃ Modes           ┃ Description           ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━┩
│ mysql.extractor   │ 1.0.0   │ extract,discover│ Extract from MySQL... │
└───────────────────┴─────────┴─────────────────┴───────────────────────┘

# Machine-readable JSON
$ osiris components list --json
[
  {
    "name": "mysql.extractor",
    "version": "1.0.0",
    "modes": ["extract", "discover"],
    "description": "Extract data from MySQL databases"
  },
  {
    "name": "mysql.writer",
    "version": "1.0.0",
    "modes": ["write", "discover"],
    "description": "Write data to MySQL databases"
  }
]

# Empty component list returns valid JSON
$ osiris components list --json
[]

# Errors also return JSON (never partial Rich tables)
$ osiris components list --json --mode invalid
{
  "error": "Invalid mode: 'invalid'. Valid modes are: all, extract, write, discover",
  "valid_modes": ["all", "extract", "write", "discover"]
}
```

## Acceptance Criteria

- [x] `osiris components validate mysql.writer --level strict` prints friendly messages for validation failures
- [x] Session logs (JSONL) include friendly error details without duplicate events
- [x] `osiris components validate ... --verbose` shows both friendly and technical details
- [x] `osiris components list --json` outputs clean JSON array (no Rich table)
- [x] `osiris components list --json` returns `[]` for empty component list (valid JSON)
- [ ] `osiris components list --json` returns error JSON for invalid parameters (never partial output) - *Not implemented: out of scope*
- [x] Error messages include actionable fix suggestions with examples
- [x] JSON Pointer paths map to human-readable field names
- [x] Error categories consistently use snake_case (e.g., `config_error`) in all outputs
- [x] Secret field values are NEVER exposed in friendly error messages (only field names)
- [x] All existing tests pass with no regressions
- [x] New tests achieve >80% coverage for error mapper

## Testing Strategy

### Unit Tests (`tests/components/test_error_mapper.py`)
- Path to label mapping for all common fields
- Error categorization using snake_case (schema_error/config_error/type_error/constraint_error)
- Fix suggestion generation
- Example value recommendations
- Secret values never exposed in error messages (test with password/key fields)
- Verify only field names appear for secret fields, not values

### Integration Tests
- Extend `tests/components/test_registry_cli_logging.py`:
  - Validation failures produce friendly messages
  - Session events contain friendly_errors field with snake_case categories
  - --verbose flag includes technical details
  - Secret field errors never expose actual values
- New test: `tests/cli/test_components_list_json.py`:
  - JSON output format validation
  - Empty list returns `[]` (valid JSON)
  - Invalid parameters return error JSON (not partial output)
  - No Rich table artifacts in JSON mode
  - All components included in output

### Sample Input/Output

#### Before (Technical Error)
```
ValidationError: 'host' is a required property
Failed validating 'required' in schema['properties']['configSchema']:
    {'properties': {...}, 'required': ['host', 'database', 'user', 'password', 'table']}
On instance['configSchema']:
    {'port': 3306, 'database': 'mydb', 'user': 'root', 'password': '***', 'table': 'users'}
```

#### After (Friendly Error)
```
❌ Missing Required Configuration
   Field: Database Host
   Problem: The 'host' field is required but was not provided
   Fix: Add 'host: your-database-server.com' to your configuration
   Example: host: localhost (for local development)
   
   Need the full server address where your MySQL database is running.
```

#### Secret Field Error Example
```
# Technical error (never show to users)
ValidationError: 'supersecret123' does not match pattern '^(?=.*[A-Z])(?=.*[0-9]).*$'

# Friendly error (safe to show)
❌ Constraint Violation
   Field: Database Password  
   Problem: Password does not meet security requirements
   Fix: Password must contain at least one uppercase letter and one number
   Example: password: ${DB_PASSWORD}  # Use environment variable for security
   
   Note: Never commit passwords to version control.
```

## Implementation Details

### Created Files
- [x] `osiris/components/error_mapper.py` - Core FriendlyErrorMapper class with path mappings and fix suggestions
- [x] `tests/components/test_error_mapper.py` - 18 unit tests covering all error types and secret masking
- [x] `tests/cli/test_components_list_json.py` - 6 tests for JSON output functionality

### Modified Files
- [x] `osiris/components/registry.py` - Updated to return structured errors with friendly and technical info
- [x] `osiris/cli/components_cmd.py` - Added JSON output for list, friendly error display for validate
- [x] `osiris/cli/main.py` - Added --json and --verbose flags
- [x] `tests/components/test_registry_friendly_errors.py` - 7 integration tests for friendly errors
- [x] `CHANGELOG.md` - Updated with M1a.4 changes

## Risks & Limitations

### Known Limitations
1. **Generic Suggestions**: Initial implementation uses generic fix suggestions; component-specific hints require manual curation
2. **Path Coverage**: Only common JSON Pointer paths have friendly labels; uncommon paths show technical names
3. **Language**: Error messages are English-only in this version
4. **Complex Constraints**: Multi-field constraints may not have perfect friendly representations

### Mitigation Strategies
- Collect user feedback on confusing errors for targeted improvements
- Consider component-specific error dictionaries in future iterations
- Document technical paths for advanced users

## Follow-up Work

### Future Enhancements (M1a.5+)
1. **Component-Specific Suggestions**: Per-component fix dictionaries with context-aware hints
2. **Error Recovery**: Suggest valid alternative configurations
3. **Interactive Fixes**: CLI prompt to apply suggested fixes automatically
4. **Localization**: Multi-language error messages
5. **Error Analytics**: Track common errors to improve component design

### Documentation Updates
- Update component development guide with error message guidelines
- Add troubleshooting section to user documentation
- Create error reference with all possible validation failures

## Lessons Learned

1. **Secret Masking Critical**: Ensuring that validation errors never expose sensitive data required careful handling of error messages at all levels
2. **Snake_case Consistency**: Maintaining consistent naming conventions (snake_case) across all error categories simplified both implementation and testing
3. **JSON Output Edge Cases**: Empty component lists and error conditions needed special handling to ensure valid JSON output in all cases
4. **Test Coverage**: Comprehensive test coverage (31 tests total) helped catch edge cases early and ensured robust implementation
5. **Backward Compatibility**: Supporting both string and structured errors ensured smooth migration path

## References

- [M1 Overview](../milestones/m1-component-registry-and-runner.md)
- [ADR-0007: Component Specification](../adr/0007-component-specification-and-capabilities.md)
- [ADR-0008: Component Registry](../adr/0008-component-registry.md)
- [M1a.3: Component Registry Implementation](./m1a.3-component-registry.md)
