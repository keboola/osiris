"""Test connection validation with ADR-0020 compliant fields.

This module tests that the validation schemas correctly handle
all fields used in osiris_connections.yaml per ADR-0020.
"""

import pytest

from osiris.core.validation import (
    ConnectionValidator,
    ValidationMode,
)


class TestConnectionSchemas:
    """Test connection schemas accept ADR-0020 fields."""

    def test_mysql_schema_accepts_adr20_fields(self):
        """MySQL schema should accept all ADR-0020 fields without warnings."""
        validator = ConnectionValidator(mode=ValidationMode.WARN)

        # Minimal valid MySQL config with ADR-0020 fields
        config = {
            "type": "mysql",
            "host": "localhost",
            "port": 3306,
            "database": "testdb",
            "user": "testuser",
            "password": "testpass",  # pragma: allowlist secret
            "default": True,  # ADR-0020 field
            "alias": "test_alias",  # Metadata field
            "charset": "utf8mb4",
        }

        result = validator.validate_connection(config)
        assert result.is_valid
        assert len(result.warnings) == 0
        assert len(result.errors) == 0

    def test_mysql_schema_accepts_dsn_alternative(self):
        """MySQL schema should accept DSN as alternative connection method."""
        validator = ConnectionValidator(mode=ValidationMode.WARN)

        config = {
            "type": "mysql",
            "host": "localhost",
            "database": "testdb",
            "user": "testuser",
            "password": "testpass",  # pragma: allowlist secret
            "dsn": "mysql://testuser:testpass@localhost:3306/testdb",  # pragma: allowlist secret  # Alternative
        }

        result = validator.validate_connection(config)
        assert result.is_valid
        assert len(result.warnings) == 0

    def test_supabase_schema_accepts_adr20_fields(self):
        """Supabase schema should accept all ADR-0020 fields without warnings."""
        validator = ConnectionValidator(mode=ValidationMode.WARN)

        config = {
            "type": "supabase",
            "url": "https://project.supabase.co",
            "key": "test-key",
            "default": True,  # ADR-0020 field
            "alias": "main",  # Metadata field
            "pg_dsn": "postgresql://user:pass@host:5432/db",  # pragma: allowlist secret  # Alternative connection
            "password": "dbpass",  # pragma: allowlist secret  # For pg_dsn
        }

        result = validator.validate_connection(config)
        assert result.is_valid
        assert len(result.warnings) == 0
        assert len(result.errors) == 0

    def test_supabase_schema_accepts_key_variants(self):
        """Supabase schema should accept different key field names."""
        validator = ConnectionValidator(mode=ValidationMode.WARN)

        # Test with service_role_key
        config = {
            "type": "supabase",
            "url": "https://project.supabase.co",
            "key": "anon-key",
            "service_role_key": "service-key",  # Alternative key field
        }

        result = validator.validate_connection(config)
        assert result.is_valid
        assert len(result.warnings) == 0

    def test_unknown_field_produces_helpful_warning(self):
        """Unknown fields should produce actionable warnings in warn mode."""
        validator = ConnectionValidator(mode=ValidationMode.WARN)

        config = {
            "type": "mysql",
            "host": "localhost",
            "database": "testdb",
            "user": "testuser",
            "password": "testpass",  # pragma: allowlist secret
            "unknown_field": "value",  # This should trigger warning
            "another_bad": "field",
        }

        result = validator.validate_connection(config)
        assert result.is_valid  # Still valid in warn mode
        assert len(result.warnings) > 0

        # Check warning message is helpful
        warning = result.warnings[0]
        assert "unknown_field" in warning.why or "another_bad" in warning.why
        assert "allowed keys" in warning.fix.lower()

    def test_unknown_field_fails_strict_mode(self):
        """Unknown fields should cause failure in strict mode."""
        validator = ConnectionValidator(mode=ValidationMode.STRICT)

        config = {
            "type": "mysql",
            "host": "localhost",
            "database": "testdb",
            "user": "testuser",
            "password": "testpass",  # pragma: allowlist secret
            "totally_unknown": "value",
        }

        result = validator.validate_connection(config)
        assert not result.is_valid
        assert len(result.errors) > 0

        # Check error message lists the unexpected key
        error = result.errors[0]
        assert "totally_unknown" in error.why or "totally_unknown" in error.message

    def test_validation_off_mode_accepts_anything(self):
        """OFF mode should accept any configuration."""
        validator = ConnectionValidator(mode=ValidationMode.OFF)

        config = {
            "type": "mysql",
            "completely": "invalid",
            "random": "fields",
        }

        result = validator.validate_connection(config)
        assert result.is_valid
        assert len(result.warnings) == 0
        assert len(result.errors) == 0


class TestRealWorldConfigurations:
    """Test with actual osiris_connections.yaml patterns."""

    def test_production_mysql_config(self):
        """Test actual MySQL config from osiris_connections.yaml."""
        validator = ConnectionValidator(mode=ValidationMode.WARN)

        # This mimics testing_env/osiris_connections.yaml after env substitution
        config = {
            "type": "mysql",
            "host": "test-api-to-mysql.cjtmwuzxk8bh.us-east-1.rds.amazonaws.com",
            "port": 3306,
            "database": "padak",
            "user": "admin",
            "password": "actual-password-here",  # pragma: allowlist secret
            "default": True,
        }

        result = validator.validate_connection(config)
        assert result.is_valid
        assert len(result.warnings) == 0
        assert len(result.errors) == 0

    def test_production_supabase_config(self):
        """Test actual Supabase config from osiris_connections.yaml."""
        validator = ConnectionValidator(mode=ValidationMode.WARN)

        config = {
            "type": "supabase",
            "url": "https://nedklmkgzjsyvqfxbmve.supabase.co",
            "key": "actual-service-key",
            "pg_dsn": "postgresql://postgres:dbpass@db.nedklmkgzjsyvqfxbmve.supabase.co:5432/postgres",  # pragma: allowlist secret
            "default": True,
        }

        result = validator.validate_connection(config)
        assert result.is_valid
        assert len(result.warnings) == 0
        assert len(result.errors) == 0


class TestBackwardCompatibility:
    """Ensure we didn't break existing valid configs."""

    def test_minimal_mysql_still_works(self):
        """Minimal MySQL config without new fields should still validate."""
        validator = ConnectionValidator(mode=ValidationMode.STRICT)

        config = {
            "type": "mysql",
            "host": "localhost",
            "database": "db",
            "user": "user",
            "password": "pass",  # pragma: allowlist secret
        }

        result = validator.validate_connection(config)
        assert result.is_valid

    def test_minimal_supabase_still_works(self):
        """Minimal Supabase config without new fields should still validate."""
        validator = ConnectionValidator(mode=ValidationMode.STRICT)

        config = {
            "type": "supabase",
            "url": "https://project.supabase.co",
            "key": "key",
        }

        result = validator.validate_connection(config)
        assert result.is_valid


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
