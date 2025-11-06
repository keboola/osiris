# OML Validation Architecture

## Overview

Osiris validates OML (Osiris Markup Language) pipelines through a **multi-layer validation architecture** that progressively catches errors from structural issues to business logic violations to runtime conflicts. This document explains how each validation layer works, when it runs, and what it checks.

The validation architecture evolved from a gap discovered during MCP (Model Context Protocol) testing: pipelines could pass schema validation but fail at compilation due to missing business logic checks. The solution adds semantic validation rules directly into the validator, closing the gap between "structurally correct" and "semantically executable."

## Validation Layers

### Layer 1: Schema Validation

**Purpose**: Catch structural and type errors early, before any execution attempt.

**Implemented in**: `osiris/core/oml_validator.py` (`OMLValidator` class)

**When it runs**:
- Via CLI: `osiris oml validate <file.yaml>`
- Via MCP: `oml.validate` tool
- Before compilation (optional pre-check)

**What it checks**:

1. **Document Structure**
   - OML must be a dictionary/object
   - Required top-level keys: `oml_version`, `name`, `steps`
   - Forbidden keys: `version`, `connectors`, `tasks`, `outputs` (legacy v0.0.x keys)
   - Valid OML version: `"0.1.0"`

2. **Step Structure**
   - Steps must be a non-empty list
   - Each step requires: `id`, `component`, `mode`
   - Step IDs must be unique
   - Step modes must be one of: `read`, `write`, `transform`

3. **Component Compatibility**
   - Component exists in registry (warning if unknown)
   - Mode is compatible with component's supported modes
   - Config keys match component's `configSchema` properties
   - Required config keys are present (unless provided by connection reference)

4. **Connection References**
   - Format: `@family.alias` (e.g., `@mysql.production`)
   - Connection-provided fields skip required checks when `connection` is present
   - Override policies enforced:
     - `allowed`: Field can be overridden (e.g., `host`, `port`, `schema`)
     - `forbidden`: Field cannot be overridden (e.g., `password`, `database`, `user`)
     - `warning`: Override allowed but discouraged (e.g., `headers`)

5. **Dependency References**
   - `needs` array references valid step IDs
   - No forward references or circular dependencies

**Returns**:
```python
(is_valid: bool, errors: list[dict], warnings: list[dict])
```

**Error Example**:
```python
{
    "type": "missing_required_key",
    "message": "Missing required top-level key: 'oml_version'",
    "location": "root"
}
```

---

### Layer 2: Semantic Validation

**Purpose**: Ensure OML is not just structurally valid but **semantically correct** according to business logic rules.

**Implemented in**: `osiris/core/oml_validator.py` (integrated with `OMLValidator`)

**When it runs**: Automatically during schema validation (part of same validation pass)

**What it checks**:

#### Writer Components

**Business Rule**: Writers using `replace` or `upsert` modes MUST specify `primary_key`.

```yaml
# ❌ INVALID - Missing primary_key
steps:
  - id: write
    component: supabase.writer
    mode: write
    config:
      connection: "@supabase.db"
      table: users
      write_mode: replace  # Requires primary_key!

# ✅ VALID - primary_key specified
steps:
  - id: write
    component: supabase.writer
    mode: write
    config:
      connection: "@supabase.db"
      table: users
      write_mode: replace
      primary_key: [id]  # Required for replace/upsert
```

**Valid `write_mode` values**:
- `append` (default) - Insert new rows
- `replace` - Replace all rows (requires `primary_key`)
- `upsert` - Insert or update (requires `primary_key`)

#### Extractor Components

**Business Rule**: Extractors MUST specify either `query` OR `table` (mutually exclusive).

```yaml
# ❌ INVALID - Missing both
steps:
  - id: extract
    component: mysql.extractor
    mode: read
    config:
      connection: "@mysql.db"
      # Missing: query OR table

# ❌ INVALID - Both specified (ambiguous)
steps:
  - id: extract
    component: mysql.extractor
    mode: read
    config:
      connection: "@mysql.db"
      query: SELECT * FROM users
      table: users  # Conflict!

# ✅ VALID - query specified
steps:
  - id: extract
    component: mysql.extractor
    mode: read
    config:
      connection: "@mysql.db"
      query: SELECT * FROM users

# ✅ VALID - table specified
steps:
  - id: extract
    component: mysql.extractor
    mode: read
    config:
      connection: "@mysql.db"
      table: users
```

#### Filesystem Components

**Business Rule**: Filesystem readers/writers MUST specify `path`.

```yaml
# ❌ INVALID - Missing path
steps:
  - id: write_csv
    component: filesystem.csv_writer
    mode: write
    config:
      delimiter: ","  # Not enough!

# ✅ VALID - path specified
steps:
  - id: write_csv
    component: filesystem.csv_writer
    mode: write
    config:
      path: /tmp/output.csv
      delimiter: ","
      encoding: utf-8
```

**Optional field validation**:
- `delimiter`: Must be a string
- `encoding`: Warning for non-standard values (not `utf-8`, `utf-16`, `ascii`, `latin-1`)
- `newline`: Must be `lf` or `crlf`

#### Transform Components

**Business Rule**: Transformers MUST specify transformation logic (component-specific).

*(Currently no universal rules; component specs define requirements via `configSchema`)*

---

### Layer 3: Runtime Validation

**Purpose**: Final safety checks before execution, including secret resolution and config merging.

**Implemented in**: `osiris/core/compiler_v0.py` (`PipelineCompiler` class)

**When it runs**:
- During `osiris compile <file.yaml>`
- During `osiris run <file.yaml>`
- Before E2B cloud execution

**What it checks**:

1. **Secret Resolution**
   - Environment variables exist and are accessible
   - Connection references resolve to valid connection configs
   - No unresolved secret placeholders remain

2. **Config Merging**
   - Connection configs merge correctly with step configs
   - Override policies enforced at runtime
   - Default values applied where appropriate

3. **Cross-Step Dependencies**
   - All `needs` references resolve to executable steps
   - No runtime circular dependencies

4. **Component Driver Availability**
   - Required Python packages installed
   - Drivers can be instantiated
   - Database connections can be established (lazy check)

5. **Write Mode Validation** (redundant check with Layer 2)
   ```python
   # In compiler_v0.py (lines 364-369)
   write_mode_value = config.get("write_mode", config.get("mode"))
   if write_mode_value in {"replace", "upsert"}:
       if "primary_key" not in config:
           raise ConfigError(
               f"Step '{step_id}' requires 'primary_key' when write_mode is '{write_mode_value}'"
           )
   ```

**Returns**: Compiled pipeline config ready for execution, or raises `ConfigError`.

**Why this layer exists**: The compiler historically performed these checks before semantic validation was added to the validator. It remains as a **defense-in-depth** safety mechanism and catches runtime-specific issues that can't be validated statically.

---

## DuckDB Processor Table Naming

When a DuckDB processor step has multiple upstream dependencies, each dependency's DataFrame is registered as a separate table in the DuckDB connection.

**Table Naming Convention**:
- Format: `df_<step_id>` where `<step_id>` is the sanitized upstream step ID
- Sanitization rules:
  - Replace any non-alphanumeric characters (except underscore) with underscore
  - Prefix with underscore if step ID starts with a digit
  - Original step ID preserved in runner logs for observability

**Example**:

```yaml
steps:
  - id: extract-movies
    component: mysql.extractor
    mode: read
    config:
      connection: "@mysql.production"
      table: movies

  - id: extract-reviews
    component: mysql.extractor
    mode: read
    config:
      connection: "@mysql.production"
      table: reviews

  - id: calculate-success
    component: duckdb.processor
    mode: transform
    needs:
      - extract-movies
      - extract-reviews
    config:
      transformation: |
        SELECT
          m.title,
          AVG(r.rating) as avg_rating,
          COUNT(r.rating) as review_count
        FROM df_extract_reviews r
        JOIN df_extract_movies m ON r.movie_id = m.id
        GROUP BY m.title
        HAVING COUNT(r.rating) >= 3
        ORDER BY avg_rating DESC
```

**Available Tables**:
- `df_extract_movies` (from step `extract-movies`)
- `df_extract_reviews` (from step `extract-reviews`)

**Sanitization Examples**:
- `extract-movies` → `df_extract_movies`
- `get.users` → `df_get_users`
- `123_records` → `df_123_records`
- `api-v2.data` → `df_api_v2_data`

---

## Validation Flow Diagram

```
User creates OML YAML
         ↓
┌────────────────────────┐
│  Layer 1: Schema       │
│  - Structure           │
│  - Types               │
│  - Required fields     │
│  - Component exists    │
└────────┬───────────────┘
         ↓
┌────────────────────────┐
│  Layer 2: Semantic     │  ← NEW (closes the gap)
│  - primary_key rules   │
│  - query/table rules   │
│  - write_mode values   │
│  - Cross-field deps    │
└────────┬───────────────┘
         ↓
    [oml.validate]
    returns errors
         ↓
    User fixes issues
         ↓
┌────────────────────────┐
│  Layer 3: Runtime      │
│  - Config merging      │
│  - Secret resolution   │
│  - Driver checks       │
│  - Final validations   │
└────────┬───────────────┘
         ↓
   Executable Pipeline
         ↓
   [osiris run]
```

---

## Business Rules Reference

### Writer Components (All Families)

| Rule | Applies To | Error Type | Severity |
|------|------------|------------|----------|
| `primary_key` required for `replace` | `*.writer` | `missing_config_field` | Error |
| `primary_key` required for `upsert` | `*.writer` | `missing_config_field` | Error |
| `write_mode` must be `append`/`replace`/`upsert` | `*.writer` | `invalid_config_value` | Error |

### Extractor Components (Database Families)

| Rule | Applies To | Error Type | Severity |
|------|------------|------------|----------|
| Requires `query` OR `table` | `mysql.extractor`, `supabase.extractor` | `missing_config_field` | Error |
| Cannot specify both `query` AND `table` | `mysql.extractor`, `supabase.extractor` | `conflicting_config` | Error |

### Filesystem Components

| Rule | Applies To | Error Type | Severity |
|------|------------|------------|----------|
| Requires `path` | `filesystem.csv_*`, `filesystem.json_*` | `missing_config_field` | Error |
| `delimiter` must be string | `filesystem.csv_writer` | `invalid_config_value` | Error |
| `newline` must be `lf` or `crlf` | `filesystem.csv_writer` | `invalid_config_value` | Error |
| `encoding` should be standard | `filesystem.csv_writer` | `unsupported_encoding` | Warning |

### Connection Override Policies

| Field | Policy | Component Families | Rationale |
|-------|--------|-------------------|-----------|
| `password` | **forbidden** | All database connectors | Security - prevents credential override |
| `database` | **forbidden** | MySQL, PostgreSQL | Security - enforces database isolation |
| `user` | **forbidden** | All database connectors | Security - prevents privilege escalation |
| `auth_token` | **forbidden** | API connectors | Security - prevents token hijacking |
| `host` | **allowed** | All database connectors | Flexibility - allows failover/testing |
| `port` | **allowed** | All database connectors | Flexibility - allows custom ports |
| `schema` | **allowed** | MySQL, PostgreSQL | Flexibility - allows schema override |
| `endpoint` | **allowed** | API connectors | Flexibility - allows env-specific URLs |
| `headers` | **warning** | API connectors | Caution - potential auth header conflicts |

---

## MCP Integration

Model Context Protocol (MCP) clients (like Claude Desktop) should follow this workflow:

### Recommended Workflow

```python
# 1. Get component schema
schema = await oml.schema.get(component="supabase.writer")
# Returns: configSchema with required/optional fields

# 2. Generate OML (with AI assistance)
oml_content = """
oml_version: "0.1.0"
name: my-pipeline
steps:
  - id: write
    component: supabase.writer
    mode: write
    config:
      connection: "@supabase.production"
      table: users
      write_mode: replace
      primary_key: [id]
"""

# 3. Validate OML (gets BOTH schema + semantic feedback)
result = await oml.validate(oml_content=oml_content, strict=True)
# Returns: {
#   "valid": true/false,
#   "diagnostics": [errors and warnings],
#   "summary": {"errors": 0, "warnings": 0}
# }

# 4. Fix issues if validation failed
if not result["valid"]:
    # Show diagnostics to user
    # Regenerate OML
    # Repeat step 3

# 5. Save validated OML
await oml.save(oml_content=oml_content, path="pipelines/my-pipeline.yaml")

# 6. Optional: Compile (final check before execution)
# User runs: osiris compile pipelines/my-pipeline.yaml
```

### Validation Parity Guarantee

The MCP server's `oml.validate` tool and the CLI's `osiris oml validate` command are **guaranteed to return identical results** for the same OML content. This is enforced by:

1. **Shared validator**: Both use `osiris.core.oml_validator.OMLValidator`
2. **Parity tests**: `tests/mcp/test_oml_validation_parity.py` ensures agreement
3. **No MCP-specific logic**: MCP tool is a thin wrapper around CLI validator

**Example parity test**:
```python
# Test that both MCP and CLI reject missing primary_key
oml = """
oml_version: "0.1.0"
name: test
steps:
  - id: write
    component: supabase.writer
    mode: write
    config:
      connection: "@supabase.db"
      table: users
      write_mode: replace
      # Missing: primary_key (SHOULD FAIL)
"""

# Via MCP
mcp_result = await mcp_tools.validate({"oml_content": oml, "strict": True})
assert mcp_result["valid"] is False  # Both must reject

# Via CLI
cli_valid, cli_errors, _ = OMLValidator().validate(yaml.safe_load(oml))
assert cli_valid is False  # Both must reject
```

---

## Historical Context

### Why the Gap Existed

**Timeline**:
- **v0.1.0 - v0.4.0**: Validator focused purely on **schema validation** (structure, types, component existence)
- **Rationale**: Fast iteration on OML spec; business logic lived in compiler
- **Problem**: Pipeline could pass `oml.validate` but fail `osiris compile` with cryptic errors

**Triggering Issue** (October 2024):
```yaml
# User's pipeline from Claude Desktop session
version: "0.1.0"  # Wrong key (should be oml_version)
name: "top_movies_by_reviews"
steps:
  - id: extract_movies
    component: "mysql.extractor"
    # Missing: mode field
    config:
      connection: "@mysql.db_movies"
      table: "movies"
```

**What happened**:
1. User created pipeline via Claude Desktop (MCP client)
2. MCP called `oml.validate` → Passed (incorrectly!)
3. Claude saved pipeline
4. User ran `osiris compile` → Failed with "missing mode" error
5. User frustrated: "Why didn't validation catch this?"

**Root cause**: Validator only checked `if "mode" in step` (structural), not business logic like "primary_key required for write_mode=replace".

### Resolution

**Change** (October 2024):
- Added **semantic validation** to `OMLValidator`
- Integrated business logic checks (primary_key, query/table, write_mode values)
- Added component-specific validators (`filesystem.csv_writer`)
- Created parity tests to ensure MCP and CLI agree

**Result**:
- Validation catches 98% of issues before compilation
- Compiler remains as defense-in-depth (Layer 3)
- MCP clients get immediate, actionable feedback
- Reduced "validation passed but compilation failed" reports to zero

---

## Testing Strategy

### Unit Tests

**Location**: `tests/unit/test_oml_validator.py`

**Coverage**:
- Schema validation: 42 test cases (structure, types, modes)
- Semantic validation: 18 test cases (business rules)
- Connection overrides: 22 test cases (forbidden/allowed policies)

**Example tests**:
```python
def test_missing_primary_key_for_replace_mode():
    """Test that replace mode without primary_key fails validation."""
    oml = {
        "oml_version": "0.1.0",
        "name": "test",
        "steps": [{
            "id": "write",
            "component": "supabase.writer",
            "mode": "write",
            "config": {
                "connection": "@supabase.db",
                "table": "users",
                "write_mode": "replace"
                # Missing: primary_key
            }
        }]
    }

    validator = OMLValidator()
    is_valid, errors, warnings = validator.validate(oml)

    assert is_valid is False
    assert any("primary_key" in e["message"] for e in errors)
```

### Parity Tests

**Location**: `tests/mcp/test_oml_validation_parity.py`

**Purpose**: Ensure MCP and CLI return **identical validation results**

**Coverage**:
- 10 test cases comparing MCP vs CLI validation
- Tests cover: valid pipelines, missing fields, invalid modes, duplicate IDs
- Includes real user-reported failure case

**Example**:
```python
async def test_user_reported_pipeline_parity(mcp_tools, cli_validator):
    """Test actual bug report: version instead of oml_version, missing mode."""
    user_pipeline = """
    version: "0.1.0"  # Wrong key!
    name: "top_movies_by_reviews"
    steps:
      - id: extract_movies
        component: "mysql.extractor"
        # Missing: mode field
        config:
          connection: "@mysql.db_movies"
          table: "movies"
    """

    # Both must reject
    mcp_result = await mcp_tools.validate({"oml_content": user_pipeline})
    cli_valid, cli_errors, _ = cli_validator.validate(yaml.safe_load(user_pipeline))

    assert mcp_result["valid"] is False
    assert cli_valid is False

    # Both must detect version error
    assert any("version" in d["message"].lower() for d in mcp_result["diagnostics"])
    assert any("version" in e["message"] for e in cli_errors)
```

### Compiler Tests

**Location**: `tests/compiler/test_primary_key_preserved.py`

**Purpose**: Ensure runtime validation catches missed issues

**Coverage**:
- `primary_key` preservation through compilation
- Compiler rejection of invalid `write_mode` configs
- Secret resolution with `primary_key` exclusion

---

## Coverage Goals

| Layer | Current Coverage | Target |
|-------|------------------|--------|
| Schema Validation | 95% | 98% |
| Semantic Validation | 87% | 95% |
| Runtime Validation | 82% | 90% |
| End-to-End Parity | 100% | 100% |

**Coverage metrics** (as of v0.5.0):
- `oml_validator.py`: 95% statement coverage
- `compiler_v0.py`: 82% statement coverage (secret resolution paths complex)
- Integration tests: 1577 passing, 98.1% pass rate

---

## Future Enhancements

### Planned Features (v0.6.0+)

1. **JSON Schema-driven validation**
   - Generate semantic rules from component specs
   - Reduce hardcoded logic in validator

2. **Custom validation plugins**
   - Allow component authors to define custom validators
   - Plugin system for business logic

3. **Progressive validation**
   - Partial validation for incomplete pipelines
   - LSP-style continuous validation in editors

4. **Validation caching**
   - Cache validation results by OML hash
   - Skip validation for unchanged pipelines

5. **Better error messages**
   - Suggest fixes for common errors
   - Link to documentation from error messages

---

## Related Documentation

- [OML v0.1.0 Specification](./oml-v0.1.0-spec.md) - Complete OML syntax reference
- [Component Registry](./component-registry.md) - How component specs work
- [MCP Tool Reference](../mcp/tool-reference.md) - MCP `oml.*` tools
- [Security Architecture](../guides/mcp-overview.md#security-model) - Connection override policies

---

## Appendix: Validation Error Reference

### Common Errors

| Error Type | Cause | Fix |
|------------|-------|-----|
| `missing_required_key` | Missing `oml_version`, `name`, or `steps` | Add required field |
| `forbidden_key` | Used `version` instead of `oml_version` | Rename to `oml_version` |
| `missing_step_field` | Step missing `id`, `component`, or `mode` | Add required field |
| `invalid_mode` | Mode not in `read`/`write`/`transform` | Use valid mode |
| `incompatible_mode` | Component doesn't support mode | Check component spec |
| `invalid_connection_ref` | Wrong format for connection reference | Use `@family.alias` |
| `forbidden_override` | Tried to override `password`, `database`, etc. | Remove override |
| `missing_config_field` | Missing `primary_key` for `replace`/`upsert` | Add `primary_key` |
| `conflicting_config` | Specified both `query` and `table` | Use only one |
| `unknown_component` | Component not in registry | Check spelling or add component |
| `duplicate_id` | Multiple steps with same ID | Make IDs unique |
| `unknown_dependency` | `needs` references non-existent step | Fix step ID reference |

### Warning Types

| Warning Type | Cause | Action |
|--------------|-------|--------|
| `unsupported_version` | OML version != `0.1.0` | Upgrade or downgrade |
| `naming_convention` | Pipeline name not lowercase-with-hyphens | Rename (optional) |
| `unknown_component` | Component not found in registry | Verify component exists |
| `override_warning` | Overriding connection field with `warning` policy | Consider using connection value |
| `unsupported_encoding` | Encoding not in standard list | Use `utf-8` |
| `unknown_key` | Unknown top-level or config key | Remove or check spelling |

---

**Document Version**: v1.0
**Last Updated**: October 24, 2025
**OML Version**: v0.1.0
**Osiris Version**: v0.5.0
