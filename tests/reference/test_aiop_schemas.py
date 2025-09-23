#!/usr/bin/env python3
# Copyright (c) 2025 Osiris Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for AIOP schema and context files."""

import json
from pathlib import Path

import jsonschema
import pytest


def test_aiop_schema_valid_json():
    """Test that aiop.schema.json is valid JSON."""
    schema_path = Path(__file__).parent.parent.parent / "docs/reference/aiop.schema.json"
    assert schema_path.exists(), f"Schema file not found at {schema_path}"

    with open(schema_path) as f:
        schema = json.load(f)

    # Should not raise
    assert isinstance(schema, dict)
    assert "$schema" in schema
    assert "type" in schema
    assert "properties" in schema


def test_aiop_schema_is_valid_json_schema():
    """Test that aiop.schema.json is a valid JSON Schema draft-07."""
    schema_path = Path(__file__).parent.parent.parent / "docs/reference/aiop.schema.json"

    with open(schema_path) as f:
        schema = json.load(f)

    # Validate against the meta-schema
    # jsonschema will validate the schema itself
    try:
        jsonschema.Draft7Validator.check_schema(schema)
    except jsonschema.SchemaError as e:
        pytest.fail(f"Invalid JSON Schema: {e}")


def test_aiop_context_valid_jsonld():
    """Test that aiop.context.jsonld is well-formed JSON-LD."""
    context_path = Path(__file__).parent.parent.parent / "docs/reference/aiop.context.jsonld"
    assert context_path.exists(), f"Context file not found at {context_path}"

    with open(context_path) as f:
        context = json.load(f)

    # Basic JSON-LD validation
    assert isinstance(context, dict)
    assert "@context" in context
    assert isinstance(context["@context"], dict)

    # Check for required vocabulary terms
    ctx = context["@context"]
    assert "osiris" in ctx
    assert "AIOperationPackage" in ctx
    assert "Pipeline" in ctx
    assert "Run" in ctx
    assert "Step" in ctx

    # Check for predicates
    assert "produces" in ctx
    assert "consumes" in ctx
    assert "depends_on" in ctx


def test_minimal_aiop_validates():
    """Test that a minimal AIOP instance validates against the schema."""
    schema_path = Path(__file__).parent.parent.parent / "docs/reference/aiop.schema.json"

    with open(schema_path) as f:
        schema = json.load(f)

    # Create a minimal valid AIOP instance
    minimal_aiop = {
        "@context": "https://osiris.dev/ontology/v1/aiop.context.jsonld",
        "@type": "AIOperationPackage",
        "@id": "osiris://run/@session_test",
        "run": {
            "session_id": "session_test",
            "status": "completed",
            "start_time": "2024-01-15T10:00:00Z",
            "end_time": "2024-01-15T10:05:00Z",
        },
        "pipeline": {"name": "test_pipeline", "manifest_hash": "a" * 64},  # 64 hex chars
        "narrative": {},
        "semantic": {},
        "evidence": {},
        "metadata": {
            "osiris_version": "0.2.0",
            "aiop_format": "1.0",
            "generated": "2024-01-15T10:06:00Z",
            "size_bytes": 1234,
        },
    }

    # Should validate without error
    try:
        jsonschema.validate(instance=minimal_aiop, schema=schema)
    except jsonschema.ValidationError as e:
        pytest.fail(f"Minimal AIOP failed validation: {e}")


def test_aiop_schema_rejects_invalid():
    """Test that the schema rejects invalid AIOP instances."""
    schema_path = Path(__file__).parent.parent.parent / "docs/reference/aiop.schema.json"

    with open(schema_path) as f:
        schema = json.load(f)

    # Missing required field
    invalid_aiop = {
        "@context": "https://osiris.dev/ontology/v1/aiop.context.jsonld",
        "@type": "AIOperationPackage",
        # Missing @id
        "run": {
            "session_id": "session_test",
            "status": "completed",
            "start_time": "2024-01-15T10:00:00Z",
            "end_time": "2024-01-15T10:05:00Z",
        },
        "pipeline": {"name": "test_pipeline", "manifest_hash": "a" * 64},
        "narrative": {},
        "semantic": {},
        "evidence": {},
        "metadata": {
            "osiris_version": "0.2.0",
            "aiop_format": "1.0",
            "generated": "2024-01-15T10:06:00Z",
            "size_bytes": 1234,
        },
    }

    with pytest.raises(jsonschema.ValidationError) as exc_info:
        jsonschema.validate(instance=invalid_aiop, schema=schema)

    assert "'@id' is a required property" in str(exc_info.value)


def test_aiop_schema_validates_status_enum():
    """Test that run.status is restricted to valid values."""
    schema_path = Path(__file__).parent.parent.parent / "docs/reference/aiop.schema.json"

    with open(schema_path) as f:
        schema = json.load(f)

    # Invalid status value
    invalid_aiop = {
        "@context": "https://osiris.dev/ontology/v1/aiop.context.jsonld",
        "@type": "AIOperationPackage",
        "@id": "osiris://run/@session_test",
        "run": {
            "session_id": "session_test",
            "status": "invalid_status",  # Not in enum
            "start_time": "2024-01-15T10:00:00Z",
            "end_time": "2024-01-15T10:05:00Z",
        },
        "pipeline": {"name": "test_pipeline", "manifest_hash": "a" * 64},
        "narrative": {},
        "semantic": {},
        "evidence": {},
        "metadata": {
            "osiris_version": "0.2.0",
            "aiop_format": "1.0",
            "generated": "2024-01-15T10:06:00Z",
            "size_bytes": 1234,
        },
    }

    with pytest.raises(jsonschema.ValidationError) as exc_info:
        jsonschema.validate(instance=invalid_aiop, schema=schema)

    assert "is not one of" in str(exc_info.value)


def test_aiop_control_contract_valid_yaml():
    """Test that aiop.control.contract.yaml exists and is valid YAML."""
    import yaml

    control_path = Path(__file__).parent.parent.parent / "docs/reference/aiop.control.contract.yaml"
    assert control_path.exists(), f"Control contract not found at {control_path}"

    with open(control_path) as f:
        control = yaml.safe_load(f)

    # Basic structure validation
    assert isinstance(control, dict)
    assert "version" in control
    assert "dry_run" in control
    assert control["dry_run"] is True  # Must be true in PR1
    assert "capabilities" in control
    assert isinstance(control["capabilities"], list)
    assert len(control["capabilities"]) > 0

    # Check first capability structure
    first_cap = control["capabilities"][0]
    assert "id" in first_cap
    assert "type" in first_cap
    assert "description" in first_cap
