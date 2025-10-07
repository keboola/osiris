"""Tests for run_export_v2 redaction functionality."""

import json

from osiris.core.run_export_v2 import canonicalize_json, redact_secrets


def test_redact_secrets_simple():
    """Test basic redaction of sensitive field names."""
    data = {
        "password": "secret123  # pragma: allowlist secret",
        "api_key": "sk-12345",  # pragma: allowlist secret
        "token": "bearer-xyz",  # pragma: allowlist secret
        "private_key": "-----BEGIN RSA PRIVATE KEY-----",  # pragma: allowlist secret
        "safe_field": "keep_this",
    }

    result = redact_secrets(data)

    assert result["password"] == "[REDACTED]"
    assert result["api_key"] == "[REDACTED]"
    assert result["token"] == "[REDACTED]"
    assert result["private_key"] == "[REDACTED]"
    assert result["safe_field"] == "keep_this"

    # Ensure original secrets not in serialized output
    serialized = canonicalize_json(result)
    assert "secret123" not in serialized
    assert "sk-12345" not in serialized
    assert "bearer-xyz" not in serialized
    assert "BEGIN RSA" not in serialized


def test_redact_secrets_nested():
    """Test deep redaction in nested structures."""
    data = {
        "config": {
            "database": {"password": "db_pass", "host": "localhost"},  # pragma: allowlist secret
            "api": {
                "secret_key": "api_secret",  # pragma: allowlist secret
                "endpoint": "https://api.example.com",
            },
        },
        "credentials": [
            {"type": "oauth", "token": "oauth_token"},  # pragma: allowlist secret
            {"type": "basic", "authorization": "Basic xyz"},  # pragma: allowlist secret
        ],
    }

    result = redact_secrets(data)

    assert result["config"]["database"]["password"] == "[REDACTED]"
    assert result["config"]["database"]["host"] == "localhost"
    assert result["config"]["api"]["secret_key"] == "[REDACTED]"
    assert result["config"]["api"]["endpoint"] == "https://api.example.com"
    assert result["credentials"][0]["token"] == "[REDACTED]"
    assert result["credentials"][1]["authorization"] == "[REDACTED]"

    # Verify no secrets in serialized output
    serialized = canonicalize_json(result)
    assert "db_pass" not in serialized
    assert "api_secret" not in serialized
    assert "oauth_token" not in serialized
    assert "Basic xyz" not in serialized


def test_redact_connection_strings():
    """Test redaction of credentials in connection strings."""
    data = {
        "connections": {
            "postgres": "postgresql://user:password123@localhost:5432/db",  # pragma: allowlist secret
            "mysql": "mysql://admin:secret@db.example.com/mydb",  # pragma: allowlist secret
            "mongodb": "mongodb://user:pass@cluster.mongodb.net/test",  # pragma: allowlist secret
            "safe_url": "https://example.com/path",
        }
    }

    result = redact_secrets(data)

    # Connection strings should have passwords masked
    assert "password123" not in result["connections"]["postgres"]
    assert "secret" not in result["connections"]["mysql"]
    assert "pass" not in result["connections"]["mongodb"]
    assert "***" in result["connections"]["postgres"]
    assert "***" in result["connections"]["mysql"]
    assert "***" in result["connections"]["mongodb"]
    assert result["connections"]["safe_url"] == "https://example.com/path"

    # Verify no passwords in serialized output
    serialized = canonicalize_json(result)
    assert "password123" not in serialized
    assert "secret" not in serialized
    assert ":pass@" not in serialized


def test_redact_case_insensitive():
    """Test that redaction is case-insensitive."""
    data = {
        "PASSWORD": "upper_secret",  # pragma: allowlist secret
        "Password": "mixed_secret",  # pragma: allowlist secret
        "API_KEY": "upper_key",  # pragma: allowlist secret
        "ApiKey": "camel_key",  # pragma: allowlist secret
        "PRIVATE_key": "mixed_private",  # pragma: allowlist secret
    }

    result = redact_secrets(data)

    assert result["PASSWORD"] == "[REDACTED]"
    assert result["Password"] == "[REDACTED]"
    assert result["API_KEY"] == "[REDACTED]"
    assert result["ApiKey"] == "[REDACTED]"
    assert result["PRIVATE_key"] == "[REDACTED]"


def test_redact_preserves_structure():
    """Test that redaction preserves data structure."""
    data = {
        "level1": {
            "password": "secret",  # pragma: allowlist secret
            "nested": {"token": "token123", "data": [1, 2, 3]},  # pragma: allowlist secret
        },
        "array": [{"key": "value1"}, {"secret": "hidden"}],  # pragma: allowlist secret
    }

    result = redact_secrets(data)

    # Structure should be preserved
    assert "level1" in result
    assert "nested" in result["level1"]
    assert result["level1"]["nested"]["data"] == [1, 2, 3]
    assert len(result["array"]) == 2
    assert result["array"][0]["key"] == "value1"
    assert result["array"][1]["secret"] == "[REDACTED]"


def test_redact_secrets_masks_dsn():
    """Test that DSN connection strings properly mask credentials."""
    from osiris.core.run_export_v2 import redact_secrets

    data = {
        "connections": {
            "postgres": {
                "conn": "postgres://user:pass@host/db",  # pragma: allowlist secret
                "url": "postgresql://admin:secret123@db.example.com:5432/mydb",  # pragma: allowlist secret
            },
            "mysql": {
                "dsn": "mysql://root:password@localhost:3306/database",  # pragma: allowlist secret
            },
            "basic_auth": {
                "endpoint": "https://user:token@api.example.com/v1/data",  # pragma: allowlist secret
            },
            "query_params": {
                "url": "https://api.com/endpoint?key=secret_key&token=abc123",  # pragma: allowlist secret
            },
        },
        "nested": {
            "api_key": "sk-1234567890",  # pragma: allowlist secret
            "token": "bearer_xyz",  # pragma: allowlist secret
            "Authorization": "Bearer secret_token",  # pragma: allowlist secret
        },
    }

    result = redact_secrets(data)

    # Check DSN credentials are masked
    assert result["connections"]["postgres"]["conn"] == "postgres://***@host/db"
    assert result["connections"]["postgres"]["url"] == "postgresql://***@db.example.com:5432/mydb"
    assert result["connections"]["mysql"]["dsn"] == "mysql://***@localhost:3306/database"
    assert result["connections"]["basic_auth"]["endpoint"] == "https://***@api.example.com/v1/data"

    # Check query params are masked
    assert "?key=***" in result["connections"]["query_params"]["url"]
    assert "&token=***" in result["connections"]["query_params"]["url"]

    # Check nested secrets are redacted
    assert result["nested"]["api_key"] == "[REDACTED]"
    assert result["nested"]["token"] == "[REDACTED]"
    assert result["nested"]["Authorization"] == "[REDACTED]"

    # Ensure no raw secrets in JSON

    json_str = json.dumps(result)
    assert "pass" not in json_str
    assert "secret123" not in json_str
    assert "password" not in json_str
    assert "secret_key" not in json_str
    assert "abc123" not in json_str
    assert "sk-1234567890" not in json_str
    assert "bearer_xyz" not in json_str
    assert "secret_token" not in json_str


def test_redact_dsn_credentials_extended():
    """Test extended DSN credential masking patterns."""
    data = {
        "connections": {
            "postgres_full": "postgresql://user:password@host.com:5432/database",  # pragma: allowlist secret
            "mysql_with_options": "mysql://admin:secret@db.example.com/mydb?charset=utf8",  # pragma: allowlist secret
            "mongodb_srv": "mongodb+srv://user:pass@cluster.mongodb.net/test?retryWrites=true",  # pragma: allowlist secret
            "redis_auth": "redis://:authpass@redis.example.com:6379/0",  # pragma: allowlist secret
            "no_password": "postgresql://user@host.com/db",  # pragma: allowlist secret
            "no_auth": "postgresql://localhost/db",
        }
    }

    result = redact_secrets(data)

    # Check DSN credential masking
    assert result["connections"]["postgres_full"] == "postgresql://***@host.com:5432/database"
    assert result["connections"]["mysql_with_options"] == "mysql://***@db.example.com/mydb?charset=utf8"
    assert result["connections"]["mongodb_srv"] == "mongodb+srv://***@cluster.mongodb.net/test?retryWrites=true"
    assert result["connections"]["redis_auth"] == "redis://***@redis.example.com:6379/0"

    # No password cases should be unchanged
    assert result["connections"]["no_password"] == "postgresql://user@host.com/db"  # pragma: allowlist secret
    assert result["connections"]["no_auth"] == "postgresql://localhost/db"


def test_dsn_masking_masks_user_and_token():
    """Test that DSN masking properly masks user credentials and tokens in query params."""
    from osiris.core.run_export_v2 import redact_secrets

    data = {
        "connection_string": "mysql://user:pass@host/db?token=abc",  # pragma: allowlist secret
        "complex_url": "postgresql://admin:secret123@db.example.com:5432/mydb?sslmode=require&apikey=xyz123",  # pragma: allowlist secret
        "with_token": "https://api.example.com/data?access_token=secret_token&client_id=123",  # pragma: allowlist secret
        "multiple_params": "mysql://root:password@host/db?token=abc&secret=xyz&key=123",  # pragma: allowlist secret
    }

    result = redact_secrets(data)

    # Basic DSN with token in query
    assert result["connection_string"] == "mysql://***@host/db?token=***"

    # Complex PostgreSQL with apikey
    assert "***@" in result["complex_url"]
    assert "apikey=***" in result["complex_url"]
    assert "sslmode=require" in result["complex_url"]  # Non-sensitive params preserved

    # HTTPS URL with access token
    assert "access_token=***" in result["with_token"]
    assert "client_id=123" in result["with_token"]  # Non-sensitive params preserved

    # Multiple sensitive params
    assert "***@" in result["multiple_params"]
    assert "token=***" in result["multiple_params"]
    assert "secret=***" in result["multiple_params"]
    assert "key=***" in result["multiple_params"]

    # Ensure no raw secrets in output
    json_str = json.dumps(result)
    assert "pass" not in json_str
    assert "secret123" not in json_str
    assert "password" not in json_str
    assert "secret_token" not in json_str
    assert "abc" not in json_str
    assert "xyz123" not in json_str
    assert "xyz" not in json_str
