#!/usr/bin/env python3
"""
Interactive component spec validator with detailed feedback.
"""

import json
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

# Load the schema
schema_path = Path(__file__).parent.parent.parent / "components" / "spec.schema.json"
schema = json.loads(schema_path.read_text())
validator = Draft202012Validator(schema)

# Create a test spec (modify this to test different scenarios)
test_spec = {
    "name": "invalid.test",  # Try changing to "Invalid.Test" to see error
    "version": "1.0.0",
    "modes": ["extract"],
    "capabilities": {"discover": True},
    "configSchema": {"type": "object", "properties": {"connection": {"type": "string"}}},
}

print("Validating spec...")
print(json.dumps(test_spec, indent=2))
print("-" * 40)

try:
    validator.validate(test_spec)
    print("✅ VALID!")
except ValidationError as e:
    print("❌ INVALID!")
    print(f"Error: {e.message}")
    print(f"Failed at: {list(e.absolute_path)}")

    # Show all validation errors
    errors = sorted(validator.iter_errors(test_spec), key=lambda e: e.path)
    if len(errors) > 1:
        print("\nAll errors:")
        for error in errors:
            print(f"  - {list(error.path)}: {error.message}")
