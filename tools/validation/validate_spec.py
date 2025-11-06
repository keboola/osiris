#!/usr/bin/env python3
"""
Validate a component spec against the schema.

Usage:
    python validate_spec.py <spec_file.yaml>
    python validate_spec.py <spec_file.json>
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

    # Validate
    validator = Draft202012Validator(schema)

    try:
        validator.validate(spec)
        print(f"✅ Valid: {spec_path}")
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

    except ValidationError as e:
        print(f"❌ Invalid: {spec_path}")
        print(f"   Error: {e.message}")
        print(f"   Path: {' -> '.join(str(x) for x in e.absolute_path)}")

        # Provide helpful context
        if e.validator == "required":
            print(f"   Missing required field(s): {e.validator_value}")
        elif e.validator == "enum":
            print(f"   Invalid value. Must be one of: {e.validator_value}")
        elif e.validator == "pattern":
            print(f"   Value doesn't match pattern: {e.validator_value}")

        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_spec.py <spec_file>")
        sys.exit(1)

    success = validate_spec(sys.argv[1])
    sys.exit(0 if success else 1)
