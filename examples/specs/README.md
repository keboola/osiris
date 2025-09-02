# Example Component Specifications

This directory contains example and test component specifications for development and testing.

## Files

### Valid Examples
- **`test_spec.yaml`** - A valid test component spec with all common fields
- **`test_my_spec.py`** - Python script that validates an inline spec

### Invalid Examples (for testing)
- **`invalid_spec.yaml`** - Intentionally invalid spec to test error messages

## Usage

### Validate an example spec
```bash
# From project root
python tools/validation/validate_spec_strict.py examples/specs/test_spec.yaml
```

### Run the inline test
```bash
python examples/specs/test_my_spec.py
```

### Test error handling
```bash
python tools/validation/validate_spec.py examples/specs/invalid_spec.yaml
```

## Creating Your Own Test Specs

Copy `test_spec.yaml` and modify to test different scenarios:

```yaml
name: your.test.component
version: 1.0.0
modes:
  - extract
  - load
capabilities:
  discover: true
configSchema:
  type: object
  properties:
    # Your config fields here
  required:
    - field1
```

Then validate with:
```bash
python tools/validation/validate_spec_strict.py examples/specs/your_spec.yaml
```

## Notes

These are example specs for testing the component specification schema defined in `components/spec.schema.json`. Real component specs will be placed in `components/<component_name>/spec.yaml` directories.
