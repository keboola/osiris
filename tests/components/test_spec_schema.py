"""
Tests for Component Specification Schema (M1a.1)

Tests the JSON Schema for self-describing components including:
- Schema meta-validation
- Component spec validation (positive/negative cases)
- Secrets pointer validation
- Examples validation against configSchema
- LLM hints validation
- Redaction policy validation
"""

import json
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError
import pytest


class TestComponentSpecSchema:
    """Test suite for component specification schema"""

    @pytest.fixture
    def schema(self):
        """Load the component spec schema"""
        schema_path = Path(__file__).parent.parent.parent / "components" / "spec.schema.json"
        with open(schema_path) as f:
            return json.load(f)

    @pytest.fixture
    def validator(self, schema):
        """Create a JSON Schema validator"""
        return Draft202012Validator(schema)

    def test_schema_meta_validation(self, schema):
        """Test that the schema itself is valid JSON Schema Draft 2020-12"""
        # This will raise if the schema is invalid
        Draft202012Validator.check_schema(schema)

        # Verify required meta fields
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert "$id" in schema
        assert "title" in schema
        assert "type" in schema

    def test_minimal_valid_component_spec(self, validator):
        """Test a minimal valid component specification"""
        minimal_spec = {
            "name": "test.component",
            "version": "1.0.0",
            "modes": ["extract", "load"],
            "capabilities": {"discover": True, "streaming": False},
            "configSchema": {
                "type": "object",
                "properties": {"connection": {"type": "string"}, "table": {"type": "string"}},
                "required": ["connection", "table"],
            },
        }

        # Should not raise
        validator.validate(minimal_spec)

    def test_complete_component_spec(self, validator):
        """Test a complete component specification with all optional fields"""
        complete_spec = {
            "name": "mysql.table",
            "version": "2.1.0-beta.1",
            "title": "MySQL Table Connector",
            "description": "Connect to MySQL tables for ETL operations",
            "modes": ["extract", "load", "discover", "analyze"],
            "capabilities": {
                "discover": True,
                "adHocAnalytics": True,
                "inMemoryMove": False,
                "streaming": True,
                "bulkOperations": True,
                "transactions": True,
                "partitioning": False,
                "customTransforms": False,
            },
            "configSchema": {
                "type": "object",
                "properties": {
                    "connection": {
                        "type": "object",
                        "properties": {
                            "host": {"type": "string"},
                            "port": {"type": "integer"},
                            "database": {"type": "string"},
                            "username": {"type": "string"},
                            "password": {"type": "string"},
                        },
                        "required": ["host", "database", "username", "password"],
                    },
                    "table": {"type": "string"},
                    "schema": {"type": "string"},
                    "options": {
                        "type": "object",
                        "properties": {
                            "batchSize": {"type": "integer"},
                            "timeout": {"type": "integer"},
                        },
                    },
                },
                "required": ["connection", "table"],
            },
            "secrets": ["/connection/password", "/connection/username"],
            "redaction": {"strategy": "mask", "mask": "****", "extras": ["/connection/host"]},
            "constraints": {
                "required": [
                    {
                        "when": {"modes": ["load"]},
                        "must": {"options": {"batchSize": {"minimum": 1}}},
                        "error": "batchSize must be at least 1 for load mode",
                    }
                ],
                "environment": {"python": ">=3.10", "memory": "512MB", "disk": "1GB"},
            },
            "examples": [
                {
                    "title": "Basic MySQL extraction",
                    "config": {
                        "connection": {
                            "host": "localhost",
                            "port": 3306,
                            "database": "mydb",
                            "username": "user",
                            "password": "secret",  # pragma: allowlist secret
                        },
                        "table": "customers",
                        "schema": "public",
                    },
                    "omlSnippet": "type: mysql.table\nconnection: @mysql\ntable: customers",
                    "notes": "Requires read permissions on the table",
                }
            ],
            "compatibility": {
                "requires": ["python>=3.10", "mysql>=8.0"],
                "conflicts": ["postgres"],
                "platforms": ["linux", "darwin", "docker"],
            },
            "llmHints": {
                "inputAliases": {
                    "table": ["table_name", "source_table"],
                    "schema": ["database", "namespace"],
                },
                "promptGuidance": "Use this component for MySQL table operations. Always specify both connection and table. For bulk operations, set appropriate batchSize.",
                "yamlSnippets": [
                    "type: mysql.table\nconnection: @mysql",
                    "table: {{ table_name }}\nschema: {{ schema_name }}",
                ],
                "commonPatterns": [
                    {
                        "pattern": "bulk_load",
                        "description": "Use batchSize option for efficient bulk loading",
                    }
                ],
            },
            "loggingPolicy": {
                "sensitivePaths": ["/connection/host", "/connection/port"],
                "eventDefaults": ["discovery.start", "discovery.complete", "transfer.progress"],
                "metricsToCapture": ["rows_read", "rows_written", "duration_ms"],
            },
            "limits": {
                "maxRows": 1000000,
                "maxSizeMB": 1024,
                "maxDurationSeconds": 3600,
                "maxConcurrency": 10,
                "rateLimit": {"requests": 100, "period": "minute"},
            },
        }

        # Should not raise
        validator.validate(complete_spec)

    def test_invalid_component_name(self, validator):
        """Test that invalid component names are rejected"""
        invalid_names = [
            "Test.Component",  # uppercase
            "test component",  # space
            "test@component",  # invalid character
            "test/component",  # invalid character
            "",  # empty
        ]

        for name in invalid_names:
            spec = {
                "name": name,
                "version": "1.0.0",
                "modes": ["extract"],
                "capabilities": {"discover": True},
                "configSchema": {"type": "object", "properties": {}},
            }

            with pytest.raises(ValidationError) as exc_info:
                validator.validate(spec)
            assert "name" in str(exc_info.value.absolute_path)

    def test_invalid_semver(self, validator):
        """Test that invalid semantic versions are rejected"""
        invalid_versions = [
            "1",  # incomplete
            "1.0",  # incomplete
            "v1.0.0",  # prefix
            "1.0.0.0",  # too many parts
            "1.a.0",  # non-numeric
            "",  # empty
        ]

        for version in invalid_versions:
            spec = {
                "name": "test.component",
                "version": version,
                "modes": ["extract"],
                "capabilities": {"discover": True},
                "configSchema": {"type": "object", "properties": {}},
            }

            with pytest.raises(ValidationError):
                validator.validate(spec)

    def test_valid_semver(self, validator):
        """Test that valid semantic versions are accepted"""
        valid_versions = [
            "0.0.1",
            "1.0.0",
            "2.1.3",
            "1.0.0-alpha",
            "1.0.0-alpha.1",
            "1.0.0-0.3.7",
            "1.0.0-x.7.z.92",
            "1.0.0+20130313144700",
            "1.0.0-beta+exp.sha.5114f85",
        ]

        for version in valid_versions:
            spec = {
                "name": "test.component",
                "version": version,
                "modes": ["extract"],
                "capabilities": {"discover": True},
                "configSchema": {"type": "object", "properties": {}},
            }

            # Should not raise
            validator.validate(spec)

    def test_invalid_modes(self, validator):
        """Test that invalid modes are rejected"""
        invalid_specs = [
            {
                "name": "test.component",
                "version": "1.0.0",
                "modes": [],  # empty array
                "capabilities": {"discover": True},
                "configSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "test.component",
                "version": "1.0.0",
                "modes": ["invalid_mode"],  # invalid mode
                "capabilities": {"discover": True},
                "configSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "test.component",
                "version": "1.0.0",
                "modes": ["extract", "extract"],  # duplicates
                "capabilities": {"discover": True},
                "configSchema": {"type": "object", "properties": {}},
            },
        ]

        for spec in invalid_specs:
            with pytest.raises(ValidationError):
                validator.validate(spec)

    def test_json_pointer_validation(self, validator):
        """Test JSON Pointer format validation for secrets"""
        valid_pointers = [
            "/connection/password",
            "/auth/apiKey",
            "/nested/deeply/buried/secret",
            "/0",  # array index
            "/items/0/secret",
        ]

        for pointer in valid_pointers:
            spec = {
                "name": "test.component",
                "version": "1.0.0",
                "modes": ["extract"],
                "capabilities": {"discover": True},
                "configSchema": {"type": "object", "properties": {}},
                "secrets": [pointer],
            }

            # Should not raise
            validator.validate(spec)

    def test_invalid_json_pointers(self, validator):
        """Test that invalid JSON Pointers are rejected"""
        invalid_pointers = [
            "connection/password",  # missing leading slash
            "/connection/",  # trailing slash
            "//connection",  # double slash
            "",  # empty
            "/",  # just slash
        ]

        for pointer in invalid_pointers:
            spec = {
                "name": "test.component",
                "version": "1.0.0",
                "modes": ["extract"],
                "capabilities": {"discover": True},
                "configSchema": {"type": "object", "properties": {}},
                "secrets": [pointer],
            }

            with pytest.raises(ValidationError):
                validator.validate(spec)

    def test_duplicate_secrets(self, validator):
        """Test that duplicate secret pointers are rejected"""
        spec = {
            "name": "test.component",
            "version": "1.0.0",
            "modes": ["extract"],
            "capabilities": {"discover": True},
            "configSchema": {"type": "object", "properties": {}},
            "secrets": ["/connection/password", "/connection/password"],  # duplicate
        }

        with pytest.raises(ValidationError) as exc_info:
            validator.validate(spec)
        assert "uniqueItems" in str(exc_info.value)

    def test_example_config_validation(self, validator):
        """Test that example configs must match configSchema"""
        # This test validates the structural requirement
        # In practice, we'd need to validate each example.config against configSchema
        spec = {
            "name": "test.component",
            "version": "1.0.0",
            "modes": ["extract"],
            "capabilities": {"discover": True},
            "configSchema": {
                "type": "object",
                "properties": {"required_field": {"type": "string"}},
                "required": ["required_field"],
            },
            "examples": [
                {"title": "Valid example", "config": {"required_field": "value"}},
                {
                    "title": "With OML snippet",
                    "config": {"required_field": "value"},
                    "omlSnippet": "type: test.component\nrequired_field: value",
                    "notes": "This is a note",
                },
            ],
        }

        # Should not raise
        validator.validate(spec)

    def test_redaction_policy_validation(self, validator):
        """Test redaction policy validation"""
        valid_policies = [
            {"strategy": "mask", "mask": "***"},
            {"strategy": "drop"},
            {"strategy": "hash"},
            {"strategy": "mask", "mask": "[REDACTED]", "extras": ["/extra/field"]},
        ]

        for policy in valid_policies:
            spec = {
                "name": "test.component",
                "version": "1.0.0",
                "modes": ["extract"],
                "capabilities": {"discover": True},
                "configSchema": {"type": "object", "properties": {}},
                "redaction": policy,
            }

            # Should not raise
            validator.validate(spec)

    def test_invalid_redaction_strategy(self, validator):
        """Test that invalid redaction strategies are rejected"""
        spec = {
            "name": "test.component",
            "version": "1.0.0",
            "modes": ["extract"],
            "capabilities": {"discover": True},
            "configSchema": {"type": "object", "properties": {}},
            "redaction": {"strategy": "invalid_strategy"},
        }

        with pytest.raises(ValidationError) as exc_info:
            validator.validate(spec)
        assert "enum" in str(exc_info.value)

    def test_llm_hints_validation(self, validator):
        """Test LLM hints validation"""
        spec = {
            "name": "test.component",
            "version": "1.0.0",
            "modes": ["extract"],
            "capabilities": {"discover": True},
            "configSchema": {"type": "object", "properties": {}},
            "llmHints": {
                "inputAliases": {"table": ["table_name", "tbl"], "schema": ["database", "db"]},
                "promptGuidance": "Use this for testing",
                "yamlSnippets": ["type: test", "connection: @test"],
                "commonPatterns": [{"pattern": "test_pattern", "description": "A test pattern"}],
            },
        }

        # Should not raise
        validator.validate(spec)

    def test_llm_hints_optional(self, validator):
        """Test that LLM hints are optional"""
        spec = {
            "name": "test.component",
            "version": "1.0.0",
            "modes": ["extract"],
            "capabilities": {"discover": True},
            "configSchema": {"type": "object", "properties": {}},
            # No llmHints - should be valid
        }

        # Should not raise
        validator.validate(spec)

    def test_logging_policy_validation(self, validator):
        """Test logging policy validation"""
        spec = {
            "name": "test.component",
            "version": "1.0.0",
            "modes": ["extract"],
            "capabilities": {"discover": True},
            "configSchema": {"type": "object", "properties": {}},
            "loggingPolicy": {
                "sensitivePaths": ["/sensitive/field"],
                "eventDefaults": ["start", "complete"],
                "metricsToCapture": ["rows_read", "duration_ms", "errors"],
            },
        }

        # Should not raise
        validator.validate(spec)

    def test_limits_validation(self, validator):
        """Test limits validation"""
        spec = {
            "name": "test.component",
            "version": "1.0.0",
            "modes": ["extract"],
            "capabilities": {"discover": True},
            "configSchema": {"type": "object", "properties": {}},
            "limits": {
                "maxRows": 1000000,
                "maxSizeMB": 512,
                "maxDurationSeconds": 3600,
                "maxConcurrency": 5,
                "rateLimit": {"requests": 100, "period": "minute"},
            },
        }

        # Should not raise
        validator.validate(spec)

    def test_compatibility_validation(self, validator):
        """Test compatibility requirements validation"""
        spec = {
            "name": "test.component",
            "version": "1.0.0",
            "modes": ["extract"],
            "capabilities": {"discover": True},
            "configSchema": {"type": "object", "properties": {}},
            "compatibility": {
                "requires": ["python>=3.10", "mysql>=8.0"],
                "conflicts": ["postgres", "oracle"],
                "platforms": ["linux", "darwin"],
            },
        }

        # Should not raise
        validator.validate(spec)

    def test_constraints_validation(self, validator):
        """Test constraints validation"""
        spec = {
            "name": "test.component",
            "version": "1.0.0",
            "modes": ["extract", "load"],
            "capabilities": {"discover": True},
            "configSchema": {"type": "object", "properties": {}},
            "constraints": {
                "required": [
                    {
                        "when": {"mode": "load"},
                        "must": {"batchSize": {"minimum": 1}},
                        "error": "batchSize required for load mode",
                    }
                ],
                "environment": {"python": ">=3.10", "memory": "512MB", "disk": "10GB"},
            },
        }

        # Should not raise
        validator.validate(spec)

    def test_no_additional_properties(self, validator):
        """Test that additional properties are rejected at the root level"""
        spec = {
            "name": "test.component",
            "version": "1.0.0",
            "modes": ["extract"],
            "capabilities": {"discover": True},
            "configSchema": {"type": "object", "properties": {}},
            "unknownField": "value",  # Should be rejected
        }

        with pytest.raises(ValidationError) as exc_info:
            validator.validate(spec)
        assert "additionalProperties" in str(exc_info.value)

    def test_configschema_structure(self, validator):
        """Test that configSchema must be a valid JSON Schema"""
        valid_configs = [
            {"type": "object", "properties": {"field": {"type": "string"}}},
            {
                "type": "object",
                "properties": {"nested": {"type": "object", "properties": {"field": {"type": "integer"}}}},
                "required": ["nested"],
            },
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        ]

        for config in valid_configs:
            spec = {
                "name": "test.component",
                "version": "1.0.0",
                "modes": ["extract"],
                "capabilities": {"discover": True},
                "configSchema": config,
            }

            # Should not raise
            validator.validate(spec)

    def test_yaml_snippets_limit(self, validator):
        """Test that yamlSnippets has a maximum limit"""
        spec = {
            "name": "test.component",
            "version": "1.0.0",
            "modes": ["extract"],
            "capabilities": {"discover": True},
            "configSchema": {"type": "object", "properties": {}},
            "llmHints": {
                "yamlSnippets": [
                    "snippet1",
                    "snippet2",
                    "snippet3",
                    "snippet4",
                    "snippet5",
                ]  # Max 5 allowed
            },
        }

        # Should not raise
        validator.validate(spec)

        # Test with too many snippets
        spec["llmHints"]["yamlSnippets"].append("snippet6")

        with pytest.raises(ValidationError) as exc_info:
            validator.validate(spec)
        assert "maxItems" in str(exc_info.value)

    def test_prompt_guidance_length(self, validator):
        """Test that promptGuidance has a maximum length"""
        spec = {
            "name": "test.component",
            "version": "1.0.0",
            "modes": ["extract"],
            "capabilities": {"discover": True},
            "configSchema": {"type": "object", "properties": {}},
            "llmHints": {"promptGuidance": "x" * 500},  # Max 500 chars
        }

        # Should not raise
        validator.validate(spec)

        # Test with too long guidance
        spec["llmHints"]["promptGuidance"] = "x" * 501

        with pytest.raises(ValidationError) as exc_info:
            validator.validate(spec)
        assert "maxLength" in str(exc_info.value)
