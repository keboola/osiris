"""Unit tests for compiler secret key collection."""

from unittest.mock import patch

from osiris.core.compiler_v0 import CompilerV0


class TestCompilerSecretCollection:
    """Test secret key collection from component specs."""

    def test_collect_all_secret_keys_with_x_secret(self):
        """Test that x-secret fields are properly collected."""
        compiler = CompilerV0()

        # Mock registry with a component that has x-secret fields
        mock_spec = {
            "mysql.extractor": {
                "name": "mysql.extractor",
                "configSchema": {
                    "properties": {
                        "host": {"type": "string"},
                        "database": {"type": "string"},
                        "password": {"type": "string"},
                        "api_token": {"type": "string"},
                    }
                },
                "x-secret": ["/password", "/api_token", "/resolved_connection/password"],
            }
        }

        with patch.object(compiler.registry, "load_specs", return_value=mock_spec):
            secret_keys = compiler._collect_all_secret_keys()

        # Should include both x-secret fields and common secret names
        assert "password" in secret_keys
        assert "api_token" in secret_keys
        assert "resolved_connection" in secret_keys  # First segment of pointer

    def test_secret_keys_for_component_with_spec(self):
        """Test secret key extraction from a single component spec."""
        compiler = CompilerV0()

        spec = {"name": "test.writer", "x-secret": ["/service_key", "/auth/token", "/nested/deep/secret"]}

        secret_keys = compiler._secret_keys_for_component(spec)

        # Should include x-secret fields plus common secret names
        assert "service_key" in secret_keys
        assert "auth" in secret_keys  # First segment of /auth/token
        assert "nested" in secret_keys  # First segment of /nested/deep/secret
        assert "password" in secret_keys  # Common secret name
        assert "key" in secret_keys  # Common secret name
        assert "token" in secret_keys  # Common secret name

    def test_secret_keys_for_component_without_spec(self):
        """Test that common secret names are returned when no spec provided."""
        compiler = CompilerV0()

        secret_keys = compiler._secret_keys_for_component(None)

        # Should include common secret names
        assert "password" in secret_keys
        assert "secret" in secret_keys
        assert "token" in secret_keys
        assert "api_key" in secret_keys
        assert "key" in secret_keys
        assert "service_key" in secret_keys
        assert "service_role_key" in secret_keys
        assert "anon_key" in secret_keys
        assert "dsn" in secret_keys
        assert "connection_string" in secret_keys

    def test_pointer_to_segments(self):
        """Test JSON pointer parsing."""
        compiler = CompilerV0()

        # Test various pointer formats
        assert compiler._pointer_to_segments("/password") == ["password"]
        assert compiler._pointer_to_segments("/auth/token") == ["auth", "token"]
        assert compiler._pointer_to_segments("/deep/nested/field") == ["deep", "nested", "field"]
        assert compiler._pointer_to_segments("") == []
        assert compiler._pointer_to_segments("/") == []

        # Test escaped characters
        assert compiler._pointer_to_segments("/field~0with~0tilde") == ["field~with~tilde"]
        assert compiler._pointer_to_segments("/field~1with~1slash") == ["field/with/slash"]

    def test_generate_configs_filters_x_secret_fields(self):
        """Test that fields marked with x-secret are filtered from configs."""
        compiler = CompilerV0()

        # Mock component spec with x-secret
        mock_spec = {
            "configSchema": {
                "properties": {"url": {"type": "string"}, "auth_token": {"type": "string"}, "table": {"type": "string"}}
            },
            "x-secret": ["/auth_token"],
        }

        oml = {
            "steps": [
                {
                    "id": "test_step",
                    "component": "test.component",
                    "with": {
                        "url": "https://api.example.com",
                        "auth_token": "secret123",  # pragma: allowlist secret
                        "table": "users",
                    },
                }
            ]
        }

        with patch.object(compiler.registry, "get_component", return_value=mock_spec):
            configs = compiler._generate_configs(oml)

        assert "test_step" in configs
        config = configs["test_step"]

        # Non-secret fields should be preserved
        assert config.get("url") == "https://api.example.com"
        assert config.get("table") == "users"

        # Secret field should be filtered
        assert "auth_token" not in config

    def test_primary_key_not_treated_as_secret(self):
        """Test that primary_key is never treated as a secret."""
        compiler = CompilerV0()

        # Even with a spec that might suggest 'key' is secret
        spec = {"x-secret": ["/api_key", "/secret_key"]}

        secret_keys = compiler._secret_keys_for_component(spec)

        # 'key' is in common secrets, but primary_key should not be filtered
        assert "key" in secret_keys
        assert "api_key" in secret_keys
        assert "secret_key" in secret_keys

        # But primary_key specifically should not be in the list
        # (handled by the filtering logic, not the secret list)
        assert "primary_key" not in secret_keys
