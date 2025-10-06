#!/usr/bin/env python3
"""
Enhanced component spec validator that also validates the configSchema is valid JSON Schema.

Usage:
    python validate_spec_enhanced.py <spec_file.yaml>
"""

import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator, ValidationError
import yaml


def load_file(path: Path):
    """Load JSON or YAML file"""
    content = path.read_text()
    if path.suffix in [".yaml", ".yml"]:
        return yaml.safe_load(content)
    else:
        return json.loads(content)


def validate_json_schema(schema_obj):
    """Validate that an object is a valid JSON Schema"""
    try:
        # This validates that the schema itself is valid
        Draft202012Validator.check_schema(schema_obj)
        return True, None
    except Exception as e:
        return False, str(e)


def validate_spec(spec_path: str):
    """Validate a component spec against the schema"""
    # Load schema
    schema_path = Path(__file__).parent.parent.parent / "components" / "spec.schema.json"
    if not schema_path.exists():
        print(f"❌ Schema not found at {schema_path}")
        sys.exit(1)

    schema = load_file(schema_path)

    # Load spec
    spec_file = Path(spec_path)
    if not spec_file.exists():
        print(f"❌ Spec file not found: {spec_path}")
        sys.exit(1)

    try:
        spec = load_file(spec_file)
    except Exception as e:
        print(f"❌ Failed to parse {spec_path}: {e}")
        sys.exit(1)

    # First, validate against component spec schema
    validator = Draft202012Validator(schema)

    try:
        validator.validate(spec)
        print(f"✅ Structure valid: {spec_path}")
    except ValidationError as e:
        print(f"❌ Invalid structure: {spec_path}")
        print(f"   Error: {e.message}")
        print(f"   Path: {' -> '.join(str(x) for x in e.absolute_path)}")
        return False

    # Second, validate that configSchema is a valid JSON Schema
    config_schema = spec.get("configSchema", {})
    is_valid_schema, error = validate_json_schema(config_schema)

    if not is_valid_schema:
        print("❌ Invalid configSchema: not a valid JSON Schema")
        print(f"   Error: {error}")
        return False

    # Third, validate that examples match the configSchema
    examples = spec.get("examples", [])
    if examples and "configSchema" in spec:
        config_validator = Draft202012Validator(config_schema)
        for i, example in enumerate(examples):
            if "config" in example:
                try:
                    config_validator.validate(example["config"])
                    print(f"✅ Example {i+1} validates against configSchema")
                except ValidationError as e:
                    print(f"❌ Example {i+1} doesn't match configSchema")
                    print(f"   Error: {e.message}")
                    print(f"   Path: {' -> '.join(str(x) for x in e.absolute_path)}")
                    return False

    # All validations passed
    print(f"\n✅ FULLY VALID: {spec_path}")
    print(f"   Component: {spec.get('name')} v{spec.get('version')}")
    print(f"   Modes: {', '.join(spec.get('modes', []))}")

    # Show capabilities
    caps = spec.get("capabilities", {})
    enabled_caps = [k for k, v in caps.items() if v]
    if enabled_caps:
        print(f"   Capabilities: {', '.join(enabled_caps)}")

    # Show secrets if present
    secrets = spec.get("secrets", [])
    if secrets:
        print(f"   Secrets: {len(secrets)} field(s) marked as sensitive")

    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_spec_enhanced.py <spec_file>")
        sys.exit(1)

    success = validate_spec(sys.argv[1])
    sys.exit(0 if success else 1)
