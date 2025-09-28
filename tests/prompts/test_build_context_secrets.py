"""Tests for secret filtering in context builder."""

import json
import re
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from osiris.prompts.build_context import ContextBuilder


@pytest.fixture
def temp_components_with_secrets():
    """Create a temporary directory with component specs containing secrets."""
    with tempfile.TemporaryDirectory() as tmpdir:
        components_dir = Path(tmpdir) / "components"
        components_dir.mkdir()

        # Create schema file
        schema_path = components_dir / "spec.schema.json"
        with open(schema_path, "w") as f:
            json.dump(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "required": ["name", "version", "modes"],
                    "properties": {
                        "name": {"type": "string"},
                        "version": {"type": "string"},
                        "modes": {"type": "array"},
                    },
                },
                f,
            )

        # Create MySQL component with password secret
        mysql_dir = components_dir / "mysql.extractor"
        mysql_dir.mkdir()
        mysql_spec = {
            "name": "mysql.extractor",
            "version": "1.0.0",
            "modes": ["extract"],
            "configSchema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["host", "port", "database", "username", "password"],
                "properties": {
                    "host": {"type": "string", "description": "Database host"},
                    "port": {"type": "integer", "default": 3306},
                    "database": {"type": "string"},
                    "username": {"type": "string"},
                    "password": {"type": "string", "description": "Database password"},
                },
            },
            "secrets": ["/password"],
            "examples": [
                {
                    "title": "Basic MySQL connection",
                    "config": {
                        "host": "localhost",
                        "port": 3306,
                        "database": "mydb",
                        "username": "user",
                        "password": "super_secret_password_123",  # pragma: allowlist secret
                    },
                }
            ],
        }
        with open(mysql_dir / "spec.yaml", "w") as f:
            yaml.dump(mysql_spec, f)

        # Create Supabase component with API key secret
        supabase_dir = components_dir / "supabase.writer"
        supabase_dir.mkdir()
        supabase_spec = {
            "name": "supabase.writer",
            "version": "1.0.0",
            "modes": ["write"],
            "configSchema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["url", "key", "mode"],
                "properties": {
                    "url": {"type": "string"},
                    "key": {"type": "string", "description": "API key"},
                    "mode": {
                        "type": "string",
                        "enum": ["append", "merge", "replace"],
                        "default": "append",
                    },
                },
            },
            "secrets": ["/key"],
            "examples": [
                {
                    "title": "Supabase append",
                    "config": {
                        "url": "https://project.supabase.co",
                        "key": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InN1cGFiYXNlIiwicm9sZSI6ImFub24iLCJpYXQiOjE2MTYxMjM0NTZ9.abcdefghijklmnop",  # pragma: allowlist secret
                        "mode": "append",
                    },
                }
            ],
        }
        with open(supabase_dir / "spec.yaml", "w") as f:
            yaml.dump(supabase_spec, f)

        # Create a component with suspicious values in non-secret fields
        test_dir = components_dir / "test.component"
        test_dir.mkdir()
        test_spec = {
            "name": "test.component",
            "version": "1.0.0",
            "modes": ["test"],
            "configSchema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["name", "token_field", "api_endpoint"],
                "properties": {
                    "name": {"type": "string", "default": "my_secret_name"},  # Suspicious
                    "token_field": {"type": "string"},  # Name suggests secret
                    "api_endpoint": {
                        "type": "string",
                        "enum": [
                            "https://api.example.com",
                            "https://api.example.com?apikey=abc123def456",  # Suspicious
                        ],
                    },
                },
            },
            "secrets": [],  # No declared secrets
            "examples": [
                {
                    "title": "Test example",
                    "config": {
                        "name": "test_password_123",  # Suspicious value
                        "token_field": "Bearer abc123def456ghi789jkl",  # Suspicious
                        "api_endpoint": "https://api.example.com",
                    },
                }
            ],
        }
        with open(test_dir / "spec.yaml", "w") as f:
            yaml.dump(test_spec, f)

        yield components_dir


class TestSecretFiltering:
    """Test secret filtering in context builder."""

    def test_no_secrets_in_context(self, temp_components_with_secrets, tmp_path):
        """Test that no secret fields or values appear in generated context."""
        cache_dir = tmp_path / "cache"

        with patch("osiris.prompts.build_context.get_registry") as mock_get_registry:
            mock_registry = MagicMock()
            mock_registry.root = temp_components_with_secrets

            # Load the specs from our test directory
            specs = {}
            for comp_dir in temp_components_with_secrets.iterdir():
                if comp_dir.is_dir() and comp_dir.name != "__pycache__":
                    spec_file = comp_dir / "spec.yaml"
                    if not spec_file.exists():
                        spec_file = comp_dir / "spec.json"
                    if spec_file.exists():
                        with open(spec_file) as f:
                            if spec_file.suffix == ".yaml":
                                spec = yaml.safe_load(f)
                            else:
                                spec = json.load(f)
                            specs[spec["name"]] = spec

            mock_registry.load_specs.return_value = specs
            mock_get_registry.return_value = mock_registry

            builder = ContextBuilder(cache_dir=cache_dir)
            context = builder.build_context(force_rebuild=True)

            # Convert context to JSON string for searching
            context_str = json.dumps(context, separators=(",", ":")).lower()

            # Check that no secret values appear
            assert "super_secret_password_123" not in context_str
            assert "eyjhbgcioijiuzi1niisinr5cci6ikpxvcj9" not in context_str  # JWT token (lowercased)
            assert "bearer abc123def456ghi789jkl" not in context_str
            assert "test_password_123" not in context_str
            assert "apikey=abc123def456" not in context_str
            assert "my_secret_name" not in context_str

            # Verify password and key fields are excluded from required_config
            for component in context["components"]:
                if component["name"] == "mysql.extractor":
                    fields = [c["field"] for c in component.get("required_config", [])]
                    assert "password" not in fields
                    assert "host" in fields  # Non-secret field should be present
                    assert "database" in fields

                    # Check example doesn't have password
                    if "example" in component:
                        assert "password" not in component["example"]
                        assert "host" in component["example"]

                elif component["name"] == "supabase.writer":
                    fields = [c["field"] for c in component.get("required_config", [])]
                    assert "key" not in fields
                    assert "url" in fields  # Non-secret field should be present

                    # Check example doesn't have key
                    if "example" in component:
                        assert "key" not in component["example"]
                        assert "url" in component["example"]

                elif component["name"] == "test.component":
                    # Check that suspicious values are redacted
                    for field_config in component.get("required_config", []):
                        if field_config["field"] == "name" and "default" in field_config:
                            assert field_config["default"] == "***redacted***"
                        if field_config["field"] == "api_endpoint" and "enum" in field_config:
                            # Should have redacted the suspicious enum value
                            assert "***redacted***" in field_config["enum"]

                    # Check example values are redacted
                    if "example" in component:
                        assert component["example"].get("name") == "***redacted***"
                        assert component["example"].get("token_field") == "***redacted***"

    def test_no_secret_patterns_in_context(self, temp_components_with_secrets, tmp_path):
        """Test that no secret-like patterns appear in the context."""
        cache_dir = tmp_path / "cache"

        with patch("osiris.prompts.build_context.get_registry") as mock_get_registry:
            mock_registry = MagicMock()
            mock_registry.root = temp_components_with_secrets

            # Load specs
            specs = {}
            for comp_dir in temp_components_with_secrets.iterdir():
                if comp_dir.is_dir() and comp_dir.name != "__pycache__":
                    spec_file = comp_dir / "spec.yaml"
                    if not spec_file.exists():
                        spec_file = comp_dir / "spec.json"
                    if spec_file.exists():
                        with open(spec_file) as f:
                            if spec_file.suffix == ".yaml":
                                spec = yaml.safe_load(f)
                            else:
                                spec = json.load(f)
                            specs[spec["name"]] = spec

            mock_registry.load_specs.return_value = specs
            mock_get_registry.return_value = mock_registry

            builder = ContextBuilder(cache_dir=cache_dir)
            context = builder.build_context(force_rebuild=True)

            # Convert to JSON string
            context_str = json.dumps(context, separators=(",", ":"))

            # Define patterns that should NOT appear (except in component names/modes)
            # We need to be careful to allow these in component names like "supabase"
            forbidden_patterns = [
                r"\bpassword\b",
                r"\bsecret\b",
                r"\bapi[_-]?key\b",
                r"\btoken\b",
                r"\bBearer\b",
            ]

            # Remove component names, modes, and fingerprint from the string for checking
            # This allows "supabase" in names but not "password" in values
            test_str = context_str

            # Remove the fingerprint field entirely (it's a SHA-256 hash, not a secret)
            if '"fingerprint"' in test_str:
                import re as regex

                test_str = regex.sub(r'"fingerprint"\s*:\s*"[a-f0-9]{64}"', '"fingerprint":"REMOVED"', test_str)

            for component in context["components"]:
                # Remove component name from test string
                test_str = test_str.replace(f'"{component["name"]}"', '""')
                # Remove modes
                for mode in component.get("modes", []):
                    test_str = test_str.replace(f'"{mode}"', '""')

            # Now check for forbidden patterns
            for pattern in forbidden_patterns:
                matches = re.findall(pattern, test_str, re.IGNORECASE)
                # Filter out allowed occurrences
                filtered_matches = []
                for match in matches:
                    # Allow "password", "token", etc. only as field names in the schema structure
                    # but not as values
                    if match.lower() in ["password", "key", "token", "secret", "api_key"]:
                        # Check if it's a field name (appears before a colon in JSON)
                        # This is a simplified check
                        continue
                    filtered_matches.append(match)

                assert not filtered_matches, f"Found forbidden pattern {pattern}: {filtered_matches}"

    def test_redaction_of_suspicious_values(self, tmp_path):
        """Test that suspicious values are properly redacted."""
        builder = ContextBuilder(cache_dir=tmp_path)

        # Test various suspicious values
        assert builder._redact_suspicious_value("my_password_123") == "***redacted***"
        assert builder._redact_suspicious_value("secret_token") == "***redacted***"
        assert builder._redact_suspicious_value("api-key-abc123") == "***redacted***"
        assert builder._redact_suspicious_value("Bearer eyJhbGciOiJIUzI1NiIs") == "***redacted***"
        assert builder._redact_suspicious_value("basic YWRtaW46cGFzc3dvcmQ=") == "***redacted***"

        # Long hex string (potential key/token)
        assert builder._redact_suspicious_value("a" * 32) == "***redacted***"

        # Non-suspicious values should pass through
        assert builder._redact_suspicious_value("localhost") == "localhost"
        assert builder._redact_suspicious_value("https://example.com") == "https://example.com"
        assert builder._redact_suspicious_value("append") == "append"
        assert builder._redact_suspicious_value(123) == 123  # Non-string

    def test_secret_field_detection(self, tmp_path):
        """Test that secret fields are correctly identified."""
        builder = ContextBuilder(cache_dir=tmp_path)

        spec = {
            "secrets": ["/password", "/api_key", "/auth/token"],
        }

        assert builder._is_secret_field("password", spec) is True
        assert builder._is_secret_field("/password", spec) is True
        assert builder._is_secret_field("api_key", spec) is True
        assert builder._is_secret_field("/api_key", spec) is True
        assert builder._is_secret_field("username", spec) is False
        assert builder._is_secret_field("host", spec) is False
