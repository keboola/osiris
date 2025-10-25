"""Unit tests for OML validator."""

from osiris.core.oml_validator import OMLValidator


class TestOMLValidator:
    """Test OML validation logic."""

    def test_valid_oml(self):
        """Test validation of a valid OML document."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "mysql.extractor",
                    "mode": "read",
                    "config": {"connection": "@mysql.test_db", "query": "SELECT * FROM users"},
                },
                {
                    "id": "step2",
                    "component": "filesystem.csv_writer",
                    "mode": "write",
                    "needs": ["step1"],
                    "config": {"path": "/tmp/output.csv"},
                },
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is True
        assert len(errors) == 0
        assert len(warnings) == 0

    def test_missing_required_keys(self):
        """Test detection of missing required keys."""
        oml = {"name": "test-pipeline", "steps": []}

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is False
        assert len(errors) == 2  # Missing oml_version and empty steps
        assert any(e["type"] == "missing_required_key" and "oml_version" in e["message"] for e in errors)
        assert any(e["type"] == "empty_steps" for e in errors)

    def test_forbidden_keys(self):
        """Test detection of forbidden keys."""
        oml = {
            "oml_version": "0.1.0",
            "version": "1.0",  # Forbidden
            "name": "test-pipeline",
            "connectors": {},  # Forbidden
            "tasks": [],  # Forbidden
            "outputs": {},  # Forbidden
            "steps": [{"id": "step1", "component": "mysql.extractor", "mode": "read"}],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is False
        assert len(errors) == 4
        forbidden_keys = {e["message"].split("'")[1] for e in errors if e["type"] == "forbidden_key"}
        assert forbidden_keys == {"version", "connectors", "tasks", "outputs"}

    def test_invalid_version(self):
        """Test validation of OML version."""
        oml = {"oml_version": 123, "name": "test-pipeline", "steps": []}  # Should be string

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is False
        assert any(e["type"] == "invalid_version_type" for e in errors)

    def test_unsupported_version_warning(self):
        """Test warning for unsupported version."""
        oml = {
            "oml_version": "0.2.0",  # Not 0.1.0
            "name": "test-pipeline",
            "steps": [{"id": "step1", "component": "mysql.extractor", "mode": "read"}],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is True
        assert len(warnings) == 1
        assert warnings[0]["type"] == "unsupported_version"

    def test_empty_steps(self):
        """Test detection of empty steps."""
        oml = {"oml_version": "0.1.0", "name": "test-pipeline", "steps": []}

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is False
        assert any(e["type"] == "empty_steps" for e in errors)

    def test_duplicate_step_ids(self):
        """Test detection of duplicate step IDs."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {"id": "step1", "component": "mysql.extractor", "mode": "read"},
                {"id": "step1", "component": "mysql.writer", "mode": "write"},  # Duplicate
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is False
        assert any(e["type"] == "duplicate_id" for e in errors)

    def test_invalid_mode(self):
        """Test detection of invalid mode."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "mysql.extractor",
                    "mode": "invalid_mode",  # Should be read/write/transform
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is False
        assert any(e["type"] == "invalid_mode" for e in errors)

    def test_unknown_dependency(self):
        """Test detection of unknown dependencies."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {"id": "step1", "component": "mysql.extractor", "mode": "read"},
                {
                    "id": "step2",
                    "component": "mysql.writer",
                    "mode": "write",
                    "needs": ["step3"],  # step3 doesn't exist
                },
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is False
        assert any(e["type"] == "unknown_dependency" for e in errors)

    def test_invalid_connection_ref(self):
        """Test detection of invalid connection reference."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "mysql.extractor",
                    "mode": "read",
                    "config": {"connection": "@invalid-format"},  # Should be @family.alias
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is False
        assert any(e["type"] == "invalid_connection_ref" for e in errors)

    def test_filesystem_csv_writer_validation(self):
        """Test component-specific validation for filesystem.csv_writer."""
        # Missing required path
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "filesystem.csv_writer",
                    "mode": "write",
                    "config": {"delimiter": ","},
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is False
        assert any(e["type"] == "missing_config_field" for e in errors)

        # Invalid newline value
        oml["steps"][0]["config"]["path"] = "/tmp/output.csv"
        oml["steps"][0]["config"]["newline"] = "invalid"

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is False
        assert any("newline must be 'lf' or 'crlf'" in e["message"] for e in errors)

    def test_unknown_component_warning(self):
        """Test warning for unknown components."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [{"id": "step1", "component": "unknown.component", "mode": "read"}],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is True  # Just a warning
        assert len(warnings) == 1
        assert warnings[0]["type"] == "unknown_component"

    def test_naming_convention_warning(self):
        """Test warning for pipeline name not following convention."""
        oml = {
            "oml_version": "0.1.0",
            "name": "TestPipeline_123",  # Should be lowercase with hyphens
            "steps": [{"id": "step1", "component": "mysql.extractor", "mode": "read"}],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is True
        assert any(w["type"] == "naming_convention" for w in warnings)

    def test_invalid_document_type(self):
        """Test validation of non-dict OML."""
        oml = "not a dictionary"

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is False
        assert errors[0]["type"] == "invalid_type"
        assert "must be a dictionary" in errors[0]["message"]

    def test_unknown_config_key(self):
        """Test detection of unknown config keys against component spec."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "mysql.extractor",
                    "mode": "read",
                    "config": {
                        "connection": "@mysql.test_db",
                        "connection_id": "test123",  # Invalid - should be 'connection' only
                        "invalid_key": "value",  # Unknown key not in spec
                    },
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is False
        # Should detect both unknown keys
        unknown_key_errors = [e for e in errors if e["type"] == "unknown_config_key"]
        assert len(unknown_key_errors) == 2
        assert any("connection_id" in e["message"] for e in unknown_key_errors)
        assert any("invalid_key" in e["message"] for e in unknown_key_errors)

    def test_missing_required_config_key(self):
        """Test detection of missing required config keys from component spec."""
        # Test without connection reference - should require connection params
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "mysql.extractor",
                    "mode": "read",
                    "config": {
                        # Missing required keys: host, database, user, password
                        # (These are required in mysql.extractor spec)
                    },
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is False
        # Should detect missing required keys when no connection reference is provided
        missing_key_errors = [e for e in errors if e["type"] == "missing_config_key"]
        assert len(missing_key_errors) == 4  # host, database, user, password
        assert any("host" in e["message"] for e in missing_key_errors)
        assert any("database" in e["message"] for e in missing_key_errors)
        assert any("user" in e["message"] for e in missing_key_errors)
        assert any("password" in e["message"] for e in missing_key_errors)

    def test_missing_required_config_key_with_connection_ref(self):
        """Test that connection reference allows skipping connection params."""
        # With connection reference, connection params are optional
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "mysql.extractor",
                    "mode": "read",
                    "config": {
                        "connection": "@mysql.test_db",
                        # Connection params (host, database, user, password) are resolved from reference
                        # So they should not be required
                    },
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should be valid - connection reference resolves required connection fields
        assert is_valid is True
        assert len(errors) == 0

    def test_valid_config_with_connection_reserved_key(self):
        """Test that 'connection' reserved key is allowed even if not in spec."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "mysql.extractor",
                    "mode": "read",
                    "config": {
                        "connection": "@mysql.test_db",
                        # When using connection, individual keys like host/user/password are optional
                        "table": "users",
                    },
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # The 'connection' key should be allowed as it's reserved
        # With connection reference, required connection params are optional
        assert is_valid is True
        unknown_config_errors = [e for e in errors if e["type"] == "unknown_config_key"]
        # 'connection' should NOT be flagged as unknown
        assert not any("connection" in e["message"] and "Unknown configuration key" in e["message"] for e in errors)

    def test_primary_key_required_for_upsert_supabase(self):
        """Test that primary_key is required for Supabase writer with upsert mode."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "supabase.writer",
                    "mode": "write",
                    "config": {
                        "connection": "@supabase.test_db",
                        "table": "users",
                        "write_mode": "upsert",
                        # Missing primary_key - should fail
                    },
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should fail due to missing primary_key
        assert is_valid is False
        assert any(
            e["type"] == "missing_required_field" and "primary_key" in e["message"] and "upsert" in e["message"]
            for e in errors
        )

    def test_primary_key_required_for_replace_supabase(self):
        """Test that primary_key is required for Supabase writer with replace mode."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "supabase.writer",
                    "mode": "write",
                    "config": {
                        "connection": "@supabase.test_db",
                        "table": "users",
                        "write_mode": "replace",
                        # Missing primary_key - should fail
                    },
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should fail due to missing primary_key
        assert is_valid is False
        assert any(
            e["type"] == "missing_required_field" and "primary_key" in e["message"] and "replace" in e["message"]
            for e in errors
        )

    def test_primary_key_required_for_upsert_mysql(self):
        """Test that primary_key is required for MySQL writer with upsert mode (uses 'mode' field)."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "mysql.writer",
                    "mode": "write",
                    "config": {
                        "connection": "@mysql.test_db",
                        "table": "users",
                        "mode": "upsert",  # MySQL uses 'mode' not 'write_mode'
                        # Missing primary_key - should fail
                    },
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should fail due to missing primary_key
        assert is_valid is False
        assert any(
            e["type"] == "missing_required_field" and "primary_key" in e["message"] and "upsert" in e["message"]
            for e in errors
        )

    def test_primary_key_optional_for_append_mode(self):
        """Test that primary_key is not required for append mode."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "supabase.writer",
                    "mode": "write",
                    "config": {
                        "connection": "@supabase.test_db",
                        "table": "users",
                        "write_mode": "append",
                        # No primary_key - should be OK for append
                    },
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should be valid - primary_key not required for append
        assert is_valid is True
        assert not any("primary_key" in e.get("message", "") for e in errors)

    def test_primary_key_valid_when_present_with_upsert(self):
        """Test that validation passes when primary_key is present with upsert."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "supabase.writer",
                    "mode": "write",
                    "config": {
                        "connection": "@supabase.test_db",
                        "table": "users",
                        "write_mode": "upsert",
                        "primary_key": "id",  # primary_key present - should be OK
                    },
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should be valid - primary_key is present
        assert is_valid is True
        assert not any("primary_key" in e.get("message", "") for e in errors)

    def test_unknown_write_mode_warning(self):
        """Test that unknown write modes generate a warning."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "supabase.writer",
                    "mode": "write",
                    "config": {
                        "connection": "@supabase.test_db",
                        "table": "users",
                        "write_mode": "merge",  # Unknown mode
                    },
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should have a warning about unknown write mode
        assert any(w["type"] == "unknown_write_mode" and "merge" in w["message"] for w in warnings)


class TestConnectionFieldsOverride:
    """Test x-connection-fields override behavior and merge strategy."""

    def test_connection_fields_simple_format(self):
        """Test simple array format for x-connection-fields."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "mysql.extractor",
                    "mode": "read",
                    "config": {"connection": "@mysql.db", "table": "users"},
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should be valid - host/port/database/user/password provided by connection
        assert is_valid is True
        assert len(errors) == 0

    def test_override_allowed(self):
        """Test that override: allowed fields can be overridden."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "mysql.extractor",
                    "mode": "read",
                    "config": {
                        "connection": "@mysql.db",
                        "host": "custom-host.example.com",  # Override allowed
                        "port": 3307,  # Override allowed
                        "table": "users",
                    },
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should be valid - host and port override is allowed
        assert is_valid is True
        assert len(errors) == 0

    def test_override_forbidden(self):
        """Test that override: forbidden fields cannot be overridden."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "mysql.extractor",
                    "mode": "read",
                    "config": {
                        "connection": "@mysql.db",
                        "password": "hacked!",  # Override forbidden!
                        "table": "users",
                    },
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should be invalid - password override is forbidden
        assert is_valid is False
        assert any(e.get("type") == "forbidden_override" for e in errors)
        assert any("password" in e.get("message", "") for e in errors)

    def test_override_forbidden_database(self):
        """Test that database field cannot be overridden (security)."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "mysql.extractor",
                    "mode": "read",
                    "config": {
                        "connection": "@mysql.db",
                        "database": "other_database",  # Override forbidden!
                        "table": "users",
                    },
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should be invalid - database override is forbidden
        assert is_valid is False
        assert any(e.get("type") == "forbidden_override" for e in errors)
        assert any("database" in e.get("message", "") for e in errors)

    def test_override_forbidden_user(self):
        """Test that user field cannot be overridden (security)."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "mysql.extractor",
                    "mode": "read",
                    "config": {
                        "connection": "@mysql.db",
                        "user": "admin",  # Override forbidden!
                        "table": "users",
                    },
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should be invalid - user override is forbidden
        assert is_valid is False
        assert any(e.get("type") == "forbidden_override" for e in errors)
        assert any("user" in e.get("message", "") for e in errors)

    def test_fallback_to_secrets_for_legacy_components(self):
        """Test that components without x-connection-fields fall back to secrets."""
        # MySQL has x-connection-fields, but we're testing the fallback logic
        # by checking a component without it would use secrets
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "duckdb.reader",
                    "mode": "read",
                    "config": {"path": "/tmp/data.duckdb", "query": "SELECT * FROM table"},
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should handle gracefully - duckdb doesn't require connection
        assert is_valid is True

    def test_empty_connection_fields(self):
        """Test components with no connection requirements."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "filesystem.csv_writer",
                    "mode": "write",
                    "config": {"path": "/tmp/output.csv"},
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should be valid - filesystem.csv_writer has no connection requirements
        assert is_valid is True

    def test_multiple_override_policies(self):
        """Test step with multiple fields having different override policies."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "mysql.extractor",
                    "mode": "read",
                    "config": {
                        "connection": "@mysql.db",
                        "host": "localhost",  # Override allowed
                        "password": "secret",  # Override forbidden - should error
                        "table": "users",
                    },
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should be invalid - password override forbidden
        assert is_valid is False
        assert any("password" in e.get("message", "") for e in errors)

    def test_connection_reference_without_overrides(self):
        """Test using connection reference without any field overrides."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "mysql.extractor",
                    "mode": "read",
                    "config": {
                        "connection": "@mysql.db",
                        # No connection field overrides - all from connection
                        "table": "users",
                        "limit": 100,
                    },
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should be valid - clean usage of connection reference
        assert is_valid is True
        assert len(errors) == 0

    def test_allowed_override_with_non_connection_fields(self):
        """Test that non-connection fields can still be provided alongside connection."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "mysql.extractor",
                    "mode": "read",
                    "config": {
                        "connection": "@mysql.db",
                        "schema": "custom_schema",  # Override allowed
                        "table": "users",  # Not a connection field
                        "limit": 1000,  # Not a connection field
                        "batch_size": 5000,  # Not a connection field
                    },
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should be valid - schema override allowed, other fields are normal config
        assert is_valid is True
        assert len(errors) == 0

    def test_multiple_forbidden_overrides(self):
        """Test multiple forbidden field overrides in same step."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "mysql.extractor",
                    "mode": "read",
                    "config": {
                        "connection": "@mysql.db",
                        "database": "hacked_db",  # Forbidden
                        "user": "admin",  # Forbidden
                        "password": "password123",  # Forbidden
                        "table": "users",
                    },
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should be invalid with multiple errors
        assert is_valid is False
        forbidden_errors = [e for e in errors if e.get("type") == "forbidden_override"]
        assert len(forbidden_errors) == 3
        error_messages = [e.get("message", "") for e in forbidden_errors]
        assert any("database" in msg for msg in error_messages)
        assert any("user" in msg for msg in error_messages)
        assert any("password" in msg for msg in error_messages)

    def test_override_warning(self):
        """Test that override: warning fields emit warning but allow override."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "graphql.extractor",
                    "mode": "read",
                    "config": {
                        "connection": "@graphql.api",
                        "headers": {"X-Custom": "value"},  # Override warning
                        "query": "{ users { id } }",
                    },
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should be valid with warning
        assert is_valid is True
        assert len(errors) == 0
        assert any(w.get("type") == "override_warning" for w in warnings)
        assert any("headers" in w.get("message", "") for w in warnings)

    def test_graphql_with_connection_reference(self):
        """Test GraphQL extractor with connection reference (real-world scenario)."""
        oml = {
            "oml_version": "0.1.0",
            "name": "graphql-pipeline",
            "steps": [
                {
                    "id": "extract",
                    "component": "graphql.extractor",
                    "mode": "read",
                    "config": {
                        "connection": "@graphql.github",
                        "query": "query { viewer { login } }",
                    },
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should be valid - endpoint and auth_token provided by connection
        assert is_valid is True
        assert len(errors) == 0

    def test_graphql_endpoint_override_allowed(self):
        """Test that GraphQL endpoint can be overridden."""
        oml = {
            "oml_version": "0.1.0",
            "name": "graphql-pipeline",
            "steps": [
                {
                    "id": "extract",
                    "component": "graphql.extractor",
                    "mode": "read",
                    "config": {
                        "connection": "@graphql.api",
                        "endpoint": "https://custom.api.com/graphql",  # Override allowed
                        "query": "{ users { id } }",
                    },
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should be valid - endpoint override is allowed
        assert is_valid is True
        assert len(errors) == 0

    def test_graphql_auth_token_override_forbidden(self):
        """Test that GraphQL auth_token cannot be overridden (security)."""
        oml = {
            "oml_version": "0.1.0",
            "name": "graphql-pipeline",
            "steps": [
                {
                    "id": "extract",
                    "component": "graphql.extractor",
                    "mode": "read",
                    "config": {
                        "connection": "@graphql.api",
                        "auth_token": "hacked_token",  # Override forbidden
                        "query": "{ users { id } }",
                    },
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should be invalid - auth_token override is forbidden
        assert is_valid is False
        assert any(e.get("type") == "forbidden_override" for e in errors)
        assert any("auth_token" in e.get("message", "") for e in errors)
