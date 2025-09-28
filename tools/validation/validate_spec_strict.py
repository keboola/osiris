#!/usr/bin/env python3
"""
Strict component spec validator with semantic validation.

This validator performs:
1. Structural validation against spec.schema.json
2. JSON Schema validation of configSchema
3. Example validation against configSchema
4. Semantic validation of cross-references

Usage:
    python validate_spec_strict.py <spec_file.yaml>
"""

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, ValidationError


def load_file(path: Path):
    """Load JSON or YAML file"""
    content = path.read_text()
    if path.suffix in [".yaml", ".yml"]:
        return yaml.safe_load(content)
    else:
        return json.loads(content)


def extract_config_fields(schema_obj, prefix=""):
    """Extract all field paths from a JSON Schema"""
    fields = set()

    if not isinstance(schema_obj, dict):
        return fields

    # Handle properties
    if "properties" in schema_obj:
        for field_name, field_schema in schema_obj["properties"].items():
            field_path = f"{prefix}/{field_name}" if prefix else field_name
            fields.add(field_path)
            # Recursively extract nested fields
            if isinstance(field_schema, dict):
                fields.update(extract_config_fields(field_schema, field_path))

    # Handle items (for arrays)
    if "items" in schema_obj:
        fields.update(extract_config_fields(schema_obj["items"], f"{prefix}/[]"))

    return fields


def validate_json_pointer_references(spec, errors):
    """Validate that JSON Pointers reference actual fields"""
    config_schema = spec.get("configSchema", {})
    config_fields = extract_config_fields(config_schema)

    # Check secrets pointers
    secrets = spec.get("secrets", [])
    for pointer in secrets:
        # Remove leading slash and check if path exists
        path = pointer[1:] if pointer.startswith("/") else pointer
        # Convert pointer format to field path
        path_parts = path.split("/")

        # Check if any config field starts with this path
        path_valid = False
        for field in config_fields:
            if field.startswith(path_parts[0]):
                path_valid = True
                break

        if not path_valid and path_parts[0] not in ["auth", "credentials", "connection"]:
            errors.append(f"Secret pointer '{pointer}' doesn't reference a field in configSchema")

    # Check redaction extras
    if "redaction" in spec and "extras" in spec["redaction"]:
        for pointer in spec["redaction"]["extras"]:
            path = pointer[1:] if pointer.startswith("/") else pointer
            path_parts = path.split("/")

            path_valid = False
            for field in config_fields:
                if field.startswith(path_parts[0]):
                    path_valid = True
                    break

            if not path_valid and path_parts[0] not in ["auth", "credentials", "connection"]:
                errors.append(f"Redaction extra pointer '{pointer}' doesn't reference a field in configSchema")


def validate_input_aliases(spec, errors):
    """Validate that inputAliases reference actual configSchema fields"""
    if "llmHints" not in spec or "inputAliases" not in spec["llmHints"]:
        return

    config_schema = spec.get("configSchema", {})

    # Get just the top-level field names
    top_level_fields = set()
    if "properties" in config_schema:
        top_level_fields = set(config_schema["properties"].keys())

    input_aliases = spec["llmHints"]["inputAliases"]

    for alias_key in input_aliases:
        if alias_key not in top_level_fields:
            errors.append(
                f"inputAlias key '{alias_key}' doesn't match any field in configSchema. "
                f"Available fields: {', '.join(sorted(top_level_fields))}"
            )


def validate_spec(spec_path: str):
    """Validate a component spec with strict semantic checks"""
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

    errors = []

    # 1. Structural validation
    validator = Draft202012Validator(schema)
    try:
        validator.validate(spec)
        print("✅ Structure valid")
    except ValidationError as e:
        print("❌ Invalid structure")
        print(f"   Error: {e.message}")
        print(f"   Path: {' -> '.join(str(x) for x in e.absolute_path)}")
        return False

    # 2. ConfigSchema validation
    config_schema = spec.get("configSchema", {})
    try:
        Draft202012Validator.check_schema(config_schema)
        print("✅ ConfigSchema is valid JSON Schema")
    except Exception as e:
        errors.append(f"ConfigSchema is not valid JSON Schema: {e}")

    # 3. Example validation
    examples = spec.get("examples", [])
    if examples and "configSchema" in spec:
        config_validator = Draft202012Validator(config_schema)
        for i, example in enumerate(examples):
            if "config" in example:
                try:
                    config_validator.validate(example["config"])
                    print(f"✅ Example {i+1} validates against configSchema")
                except ValidationError as e:
                    errors.append(f"Example {i+1} doesn't match configSchema: {e.message}")

    # 4. Semantic validations
    validate_input_aliases(spec, errors)
    validate_json_pointer_references(spec, errors)

    # Report results
    if errors:
        print("\n❌ SEMANTIC VALIDATION FAILED:")
        for error in errors:
            print(f"   • {error}")
        return False

    print(f"\n✅ ALL VALIDATIONS PASSED: {spec_path}")
    print(f"   Component: {spec.get('name')} v{spec.get('version')}")
    print(f"   Modes: {', '.join(spec.get('modes', []))}")

    # Show capabilities
    caps = spec.get("capabilities", {})
    enabled_caps = [k for k, v in caps.items() if v]
    if enabled_caps:
        print(f"   Capabilities: {', '.join(enabled_caps)}")

    # Show validated cross-references
    if "llmHints" in spec and "inputAliases" in spec["llmHints"]:
        print(f"   Input aliases: {', '.join(spec['llmHints']['inputAliases'].keys())}")

    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_spec_strict.py <spec_file>")
        sys.exit(1)

    success = validate_spec(sys.argv[1])
    sys.exit(0 if success else 1)
