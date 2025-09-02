#!/usr/bin/env python3
"""
Test a specific component spec
"""

import json
from pathlib import Path

from jsonschema import Draft202012Validator


def test_my_spec():
    # Load schema
    schema_path = Path(__file__).parent.parent.parent / "components" / "spec.schema.json"
    schema = json.loads(schema_path.read_text())

    # Your spec here (or load from file)
    my_spec = {
        "name": "my.awesome.component",
        "version": "2.1.0-beta",
        "modes": ["extract", "load", "transform"],
        "capabilities": {"discover": True, "streaming": True, "inMemoryMove": False},
        "configSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "target": {"type": "string"},
                "options": {
                    "type": "object",
                    "properties": {
                        "parallel": {"type": "boolean"},
                        "threads": {"type": "integer", "minimum": 1, "maximum": 10},
                    },
                },
            },
            "required": ["source", "target"],
        },
        "secrets": ["/options/apiKey", "/options/secretToken"],
        "examples": [
            {
                "title": "Basic transfer",
                "config": {
                    "source": "input.csv",
                    "target": "output.parquet",
                    "options": {"parallel": True, "threads": 4},
                },
            }
        ],
    }

    # Validate
    validator = Draft202012Validator(schema)

    # This will raise if invalid
    validator.validate(my_spec)

    # Additional checks
    assert my_spec["name"] == "my.awesome.component"
    assert "discover" in my_spec["capabilities"]
    assert len(my_spec["secrets"]) == 2

    print("✅ Spec is valid!")


if __name__ == "__main__":
    test_my_spec()
