# Component Spec Validation Tools

This directory contains validation utilities for Osiris component specifications.

## Validation Scripts

### Basic Validation
- **`validate_spec.py`** - Basic structural validation against `components/spec.schema.json`
  ```bash
  python tools/validation/validate_spec.py components/mysql.table/spec.yaml
  ```

### Enhanced Validation
- **`validate_spec_enhanced.py`** - Adds validation that `configSchema` is valid JSON Schema
  ```bash
  python tools/validation/validate_spec_enhanced.py components/mysql.table/spec.yaml
  ```

### Strict Validation (Recommended)
- **`validate_spec_strict.py`** - Full validation including semantic checks
  - Validates structure against schema
  - Validates configSchema is valid JSON Schema  
  - Validates examples match configSchema
  - Validates inputAliases reference real fields
  - Validates JSON Pointers reference actual/common fields
  ```bash
  python tools/validation/validate_spec_strict.py components/mysql.table/spec.yaml
  ```

### Interactive Testing
- **`validate_interactive.py`** - Interactive validator for testing inline specs
  ```bash
  python tools/validation/validate_interactive.py
  ```

## Usage

All validators accept YAML or JSON component specs:

```bash
# From project root
python tools/validation/validate_spec_strict.py examples/specs/test_spec.yaml

# Check a real component
python tools/validation/validate_spec_strict.py components/mysql.table/spec.yaml
```

## Validation Levels

1. **Structural** - Schema structure validation (all validators)
2. **ConfigSchema** - Valid JSON Schema check (enhanced & strict)
3. **Examples** - Match configSchema (enhanced & strict)
4. **Semantic** - Cross-references valid (strict only)

## Notes

These are development tools for M1a. In M1a.3, this validation will be integrated into `osiris/components/registry.py` for automatic validation at runtime.
