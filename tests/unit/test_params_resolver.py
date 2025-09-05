"""Tests for parameter resolution."""

import os

import pytest

from osiris.core.params_resolver import ParamsResolver


class TestParamsResolver:
    def test_precedence_order(self):
        """Parameters follow correct precedence."""
        resolver = ParamsResolver()

        # Set up test environment
        os.environ["OSIRIS_PARAM_TEST"] = "from_env"

        try:
            params = resolver.load_params(
                defaults={"test": "from_defaults", "other": "default_val"},
                cli_params={"test": "from_cli"},
                profile="dev",
                profiles={"dev": {"params": {"test": "from_profile"}}},
            )

            # CLI should win
            assert params["test"] == "from_cli"
            assert params["other"] == "default_val"

            # Test without CLI
            resolver2 = ParamsResolver()
            params2 = resolver2.load_params(
                defaults={"test": "from_defaults"},
                profile="dev",
                profiles={"dev": {"params": {"test": "from_profile"}}},
            )
            # Profile should win over env
            assert params2["test"] == "from_profile"

            # Test without profile
            resolver3 = ParamsResolver()
            params3 = resolver3.load_params(defaults={"test": "from_defaults"})
            # Env should win over defaults
            assert params3["test"] == "from_env"

        finally:
            del os.environ["OSIRIS_PARAM_TEST"]

    def test_resolve_string(self):
        """String templates are resolved."""
        resolver = ParamsResolver()
        resolver.params = {"db": "mydb", "table": "users"}

        template = "SELECT * FROM ${params.db}.${params.table}"
        resolved = resolver.resolve_string(template)

        assert resolved == "SELECT * FROM mydb.users"

    def test_unresolved_params(self):
        """Unresolved parameters raise error."""
        resolver = ParamsResolver()
        resolver.params = {"known": "value"}

        template = "${params.known} and ${params.unknown}"

        with pytest.raises(ValueError) as exc_info:
            resolver.resolve_string(template)

        assert "unknown" in str(exc_info.value)
        assert "Unresolved parameters" in str(exc_info.value)

    def test_resolve_nested(self):
        """Nested structures are resolved."""
        resolver = ParamsResolver()
        resolver.params = {"host": "localhost", "port": "5432"}

        data = {
            "connection": {
                "url": "postgresql://${params.host}:${params.port}/db",
                "options": ["--host=${params.host}"],
            }
        }

        resolved = resolver.resolve_value(data)

        assert resolved["connection"]["url"] == "postgresql://localhost:5432/db"
        assert resolved["connection"]["options"][0] == "--host=localhost"

    def test_resolve_oml_with_defaults(self):
        """OML resolution uses document defaults."""
        resolver = ParamsResolver()
        resolver.params = {"override": "cli_value"}

        oml = {
            "params": {
                "default_param": {"default": "default_value"},
                "override": {"default": "should_be_overridden"},
            },
            "steps": [
                {"config": {"value1": "${params.default_param}", "value2": "${params.override}"}}
            ],
        }

        resolved = resolver.resolve_oml(oml)

        assert resolved["steps"][0]["config"]["value1"] == "default_value"
        assert resolved["steps"][0]["config"]["value2"] == "cli_value"

    def test_env_variable_parsing(self):
        """Environment variables are parsed correctly."""
        resolver = ParamsResolver()

        os.environ["OSIRIS_PARAM_DB_HOST"] = "prod.db.com"
        os.environ["OSIRIS_PARAM_DB_PORT"] = "3306"

        try:
            params = resolver.load_params()

            assert params["db_host"] == "prod.db.com"
            assert params["db_port"] == "3306"

        finally:
            del os.environ["OSIRIS_PARAM_DB_HOST"]
            del os.environ["OSIRIS_PARAM_DB_PORT"]

    def test_profile_application(self):
        """Profiles are applied correctly."""
        resolver = ParamsResolver()

        profiles = {
            "dev": {"params": {"db": "dev_db", "debug": "true"}},
            "prod": {"params": {"db": "prod_db", "debug": "false"}},
        }

        params = resolver.load_params(profile="dev", profiles=profiles)

        assert params["db"] == "dev_db"
        assert params["debug"] == "true"
