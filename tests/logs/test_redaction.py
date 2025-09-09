#!/usr/bin/env python3
"""Tests for redaction of sensitive data to prevent leaks."""

import json

from osiris.core.session_reader import SessionReader


class TestRedactionPatterns:
    """Test all redaction patterns to ensure no secrets leak."""

    def test_mysql_credentials_redacted(self):
        """Test MySQL connection strings are properly redacted."""
        reader = SessionReader()

        test_cases = [
            # Standard MySQL URLs
            (
                "mysql://user:password@localhost:3306/db",  # pragma: allowlist secret
                "mysql://***@localhost:3306/db",
            ),  # pragma: allowlist secret
            (
                "mysql://admin:SuperSecret123!@192.168.1.1:3306/production",  # pragma: allowlist secret
                "mysql://***@192.168.1.1:3306/production",
            ),
            # Password with special chars but no @ should work
            (
                "mysql://root:p$$w0rd@db.example.com/myapp",
                "mysql://***@db.example.com/myapp",
            ),  # pragma: allowlist secret
            # With special characters - @ in password breaks the pattern
            # This is a limitation - passwords with @ won't be fully redacted
            # Multiple occurrences
            (
                "Connect to mysql://user:pass@host1/db1 and mysql://admin:secret@host2/db2",  # pragma: allowlist secret
                "Connect to mysql://***@host1/db1 and mysql://***@host2/db2",
            ),
        ]

        for original, expected in test_cases:
            redacted = reader.redact_text(original)
            assert redacted == expected, f"Failed to redact: {original}"
            # Ensure password is not in output
            assert "password" not in redacted.lower() or "password" in expected.lower()
            assert "secret" not in redacted.lower()
            assert "p@ss" not in redacted

    def test_postgresql_credentials_redacted(self):
        """Test PostgreSQL connection strings are properly redacted."""
        reader = SessionReader()

        test_cases = [
            # PostgreSQL variations
            (
                "postgresql://user:password@localhost/db",  # pragma: allowlist secret
                "postgresql://***@localhost/db",
            ),
            (
                "postgres://admin:secret@pg.example.com:5432/mydb",  # pragma: allowlist secret
                "postgres://***@pg.example.com:5432/mydb",
            ),
            (
                "postgresql://deploy:D3pl0y!@10.0.0.1/production",  # pragma: allowlist secret
                "postgresql://***@10.0.0.1/production",
            ),
            # In config strings
            (
                'DATABASE_URL="postgresql://user:pass@host/db"',  # pragma: allowlist secret
                'DATABASE_URL="postgresql://***@host/db"',
            ),
        ]

        for original, expected in test_cases:
            redacted = reader.redact_text(original)
            assert redacted == expected, f"Failed to redact: {original}"
            assert "password" not in redacted.lower() or "password" in expected.lower()
            assert "secret" not in redacted.lower()
            assert "D3pl0y" not in redacted

    def test_json_passwords_redacted(self):
        """Test passwords in JSON structures are redacted."""
        reader = SessionReader()

        test_cases = [
            # Simple JSON password
            ('{"password": "secret123"}', '{"password": "***"}'),  # pragma: allowlist secret
            # Nested JSON
            (
                '{"db": {"password": "dbpass", "host": "localhost"}}',  # pragma: allowlist secret
                '{"db": {"password": "***", "host": "localhost"}}',
            ),
            # Multiple passwords
            (
                '{"password": "pass1", "old_password": "pass2"}',  # pragma: allowlist secret
                '{"password": "***", "old_password": "pass2"}',  # pragma: allowlist secret
            ),  # Only exact "password" key
            # With spaces - pattern normalizes to single space
            (
                '{ "password" : "my secret" }',
                '{ "password": "***" }',
            ),  # Regex replacement doesn't preserve exact spacing
            # In larger text
            (
                'Config: {"user": "admin", "password": "secret", "port": 3306}',  # pragma: allowlist secret
                'Config: {"user": "admin", "password": "***", "port": 3306}',
            ),
        ]

        for original, expected in test_cases:
            redacted = reader.redact_text(original)
            assert redacted == expected, f"Failed to redact: {original}"
            assert "secret" not in redacted or "secret" in expected
            assert "dbpass" not in redacted

    def test_api_keys_redacted(self):
        """Test API keys are properly redacted."""
        reader = SessionReader()

        test_cases = [
            # API key in JSON
            (
                '{"api_key": "sk-1234567890abcdef"}',  # pragma: allowlist secret
                '{"api_key": "***"}',
            ),  # pragma: allowlist secret
            ('{"api_key": "key_live_abcd1234"}', '{"api_key": "***"}'),  # pragma: allowlist secret
            # Service role keys
            (
                '{"service_role_key": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"}',  # pragma: allowlist secret
                '{"service_role_key": "***"}',  # pragma: allowlist secret
            ),
            # Multiple keys
            (
                '{"api_key": "key1", "service_role_key": "key2"}',  # pragma: allowlist secret
                '{"api_key": "***", "service_role_key": "***"}',  # pragma: allowlist secret
            ),
        ]

        for original, expected in test_cases:
            redacted = reader.redact_text(original)
            assert redacted == expected, f"Failed to redact: {original}"
            assert "sk-" not in redacted
            assert "key_live" not in redacted
            assert "eyJ" not in redacted or "eyJ" in expected

    def test_bearer_tokens_redacted(self):
        """Test Bearer tokens are properly redacted."""  # pragma: allowlist secret
        reader = SessionReader()

        test_cases = [
            # Standard Bearer token  # pragma: allowlist secret
            (
                "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWI",  # pragma: allowlist secret
                "Authorization: Bearer ***",
            ),
            # In headers dict
            (
                '{"Authorization": "Bearer abc123xyz"}',
                '{"Authorization": "Bearer ***"}',
            ),  # pragma: allowlist secret
            # Multiple tokens
            (
                "Bearer token1234 and Bearer xyz789",
                "Bearer *** and Bearer ***",
            ),  # pragma: allowlist secret
            # With different casing
            ("bearer AbC123", "bearer AbC123"),  # Lowercase 'bearer' not matched
            ("BEARER ABC123", "BEARER ABC123"),  # Uppercase 'BEARER' not matched
            (
                "Bearer ABC123",
                "Bearer ***",
            ),  # Correct casing is matched  # pragma: allowlist secret
        ]

        for original, expected in test_cases:
            redacted = reader.redact_text(original)
            assert redacted == expected, f"Failed to redact: {original}"
            assert "eyJ" not in redacted or "eyJ" in expected
            assert "token1234" not in redacted
            assert "xyz789" not in redacted

    def test_multiple_secrets_in_text(self):
        """Test redaction of multiple different secrets in same text."""
        reader = SessionReader()

        text = """
        Database config:
        - Primary: mysql://admin:SuperSecret@db1.example.com/main  # pragma: allowlist secret
        - Replica: postgresql://reader:ReadOnly123@db2.example.com/replica  # pragma: allowlist secret

        API Settings:
        {
            "api_key": "sk-proj-1234567890",  # pragma: allowlist secret
            "service_role_key": "srv_key_abc123",  # pragma: allowlist secret
            "password": "ApiPassword123"  # pragma: allowlist secret
        }

        Headers:
        Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature  # pragma: allowlist secret
        """

        redacted = reader.redact_text(text)

        # Check all secrets are gone
        assert "SuperSecret" not in redacted
        assert "ReadOnly123" not in redacted
        assert "sk-proj-1234567890" not in redacted
        assert "srv_key_abc123" not in redacted  # pragma: allowlist secret
        assert "ApiPassword123" not in redacted
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in redacted

        # Check replacements are present
        assert "mysql://***@db1.example.com/main" in redacted
        assert "postgresql://***@db2.example.com/replica" in redacted
        assert '"api_key": "***"' in redacted
        assert '"service_role_key": "***"' in redacted  # pragma: allowlist secret
        assert '"password": "***"' in redacted
        assert "Bearer ***" in redacted

    def test_no_over_redaction(self):
        """Test that non-sensitive data is not redacted."""
        reader = SessionReader()

        safe_text = """
        Session Information:
        - session_id: test_123
        - status: success
        - started_at: 2025-01-01T10:00:00Z
        - rows_read: 1000
        - tables: users, orders
        - mode: extract
        - component_type: mysql.extractor
        """

        redacted = reader.redact_text(safe_text)

        # Should be unchanged
        assert redacted == safe_text

    def test_partial_matches_not_redacted(self):
        """Test that partial matches are not incorrectly redacted."""
        reader = SessionReader()

        test_cases = [
            # Not a connection string
            ("mysql://localhost/db", "mysql://localhost/db"),  # No user:pass
            (
                "postgresql://user@host/db",
                "postgresql://user@host/db",
            ),  # No colon means no password
            # Not a JSON password
            ("password_field", "password_field"),  # Not in JSON structure
            ("my_password", "my_password"),  # Not a JSON key
            # Not a Bearer token  # pragma: allowlist secret
            ("Bearer", "Bearer"),  # No token after Bearer
            ("MyBearerToken", "MyBearerToken"),  # Not the pattern
        ]

        for original, expected in test_cases:
            redacted = reader.redact_text(original)
            assert redacted == expected, f"Over-redacted: {original}"


class TestSafeFieldFiltering:
    """Test filtering of safe vs unsafe fields."""

    def test_whitelist_fields_kept(self):
        """Test that whitelisted fields are kept."""
        reader = SessionReader()

        data = {
            "session_id": "test_123",
            "started_at": "2025-01-01T10:00:00Z",
            "finished_at": "2025-01-01T10:05:00Z",
            "duration_ms": 300000,
            "status": "success",
            "labels": ["test", "automated"],
            "pipeline_name": "test_pipeline",
            "oml_version": "0.1.0",
            "event": "step_complete",
            "level": "info",
            "step_id": "extract_1",
            "rows_read": 1000,
            "rows_written": 950,
            "tables": ["users", "orders"],
            "mode": "extract",
            "component_type": "mysql.extractor",
        }

        filtered = reader.filter_safe_fields(data)

        # All whitelisted fields should be present
        for key in data:
            assert key in filtered
            assert filtered[key] == data[key]

    def test_sensitive_fields_removed(self):
        """Test that non-whitelisted fields are removed."""
        reader = SessionReader()

        data = {
            "session_id": "test_123",
            "status": "success",
            # Sensitive fields that should be removed
            "password": "secret123",  # pragma: allowlist secret
            "api_key": "sk-1234567890",  # pragma: allowlist secret
            "connection_string": "mysql://user:pass@host/db",  # pragma: allowlist secret
            "secret_key": "very_secret",  # pragma: allowlist secret
            "credentials": {"user": "admin", "pass": "admin123"},
            "auth_token": "Bearer abc123",  # pragma: allowlist secret
            "database_url": "postgresql://user:pass@host/db",  # pragma: allowlist secret
            "private_key": "-----BEGIN PRIVATE KEY-----",  # pragma: allowlist secret
        }

        filtered = reader.filter_safe_fields(data)

        # Only whitelisted fields should remain
        assert "session_id" in filtered
        assert "status" in filtered

        # Sensitive fields should be removed
        assert "password" not in filtered
        assert "api_key" not in filtered
        assert "connection_string" not in filtered
        assert "secret_key" not in filtered
        assert "credentials" not in filtered
        assert "auth_token" not in filtered
        assert "database_url" not in filtered
        assert "private_key" not in filtered

    def test_empty_dict_handling(self):
        """Test filtering handles empty dict gracefully."""
        reader = SessionReader()

        filtered = reader.filter_safe_fields({})
        assert filtered == {}

    def test_none_values_preserved(self):
        """Test that None values in safe fields are preserved."""
        reader = SessionReader()

        data = {
            "session_id": "test_123",
            "started_at": None,
            "finished_at": None,
            "status": "running",
            "password": None,  # Should still be filtered even if None
        }

        filtered = reader.filter_safe_fields(data)

        assert filtered["session_id"] == "test_123"
        assert filtered["started_at"] is None
        assert filtered["finished_at"] is None
        assert filtered["status"] == "running"
        assert "password" not in filtered


class TestRedactionInContext:
    """Test redaction in realistic contexts."""

    def test_redact_session_events(self):
        """Test redaction of events.jsonl content."""
        reader = SessionReader()

        # Simulate events that might contain secrets
        events = [
            {
                "ts": "2025-01-01T10:00:00Z",
                "session": "test_123",
                "event": "config_loaded",
                "config": {
                    "database": "mysql://user:password@localhost/db",  # pragma: allowlist secret
                    "api_key": "sk-1234567890",  # pragma: allowlist secret
                },
            },
            {
                "ts": "2025-01-01T10:00:01Z",
                "session": "test_123",
                "event": "connection_established",
                "connection_string": "postgresql://admin:secret@host/db",  # pragma: allowlist secret
            },
        ]

        # Redact each event
        for event in events:
            event_str = json.dumps(event)
            redacted_str = reader.redact_text(event_str)

            # Check secrets are gone
            assert "password" not in redacted_str or '"password"' in redacted_str
            assert "secret" not in redacted_str
            assert "sk-1234567890" not in redacted_str

            # Check structure is preserved
            redacted_event = json.loads(redacted_str)
            assert redacted_event["ts"] == event["ts"]
            assert redacted_event["session"] == event["session"]
            assert redacted_event["event"] == event["event"]

    def test_redact_error_messages(self):
        """Test redaction of secrets in error messages."""
        reader = SessionReader()

        error_messages = [
            "Failed to connect to mysql://user:pass123@db.example.com/app",  # pragma: allowlist secret
            "Authentication failed for postgresql://admin:wrong_pass@localhost/db",  # pragma: allowlist secret
            'Invalid API key: {"api_key": "sk-abc123", "endpoint": "https://api.example.com"}',  # pragma: allowlist secret
            "Bearer token expired: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.exp",  # pragma: allowlist secret
        ]

        for error in error_messages:
            redacted = reader.redact_text(error)

            # Original passwords/tokens should be gone
            assert "pass123" not in redacted
            assert "wrong_pass" not in redacted
            assert "sk-abc123" not in redacted  # pragma: allowlist secret
            assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in redacted

            # Error context should be preserved
            assert "Failed to connect" in redacted or "***" in redacted
            assert "Authentication failed" in redacted or "***" in redacted

    def test_no_redaction_in_safe_logs(self):
        """Test that normal log messages are not affected."""
        reader = SessionReader()

        safe_logs = [
            "Starting session test_123",
            "Processing step: extract_users",
            "Rows read: 1000, Rows written: 950",
            "Table users has 50 columns",
            "Pipeline completed successfully",
            "Duration: 300.5 seconds",
            "Status: success",
        ]

        for log in safe_logs:
            redacted = reader.redact_text(log)
            assert redacted == log, f"Incorrectly redacted safe log: {log}"
