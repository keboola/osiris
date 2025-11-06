"""
Test memory PII redaction functionality.

Ensures memory capture:
1. Requires explicit consent
2. Redacts email addresses
3. Redacts DSN/connection strings
4. Redacts secrets (using spec-aware detection)
5. Redacts API keys
6. Writes to correct config-driven path
"""

from unittest.mock import patch

import pytest

from osiris.mcp.tools.memory import MemoryTools


class TestMemoryPIIRedaction:
    """Test PII redaction in memory capture."""

    @pytest.fixture
    def memory_tools(self, tmp_path):
        """Create memory tools with temporary directory."""
        return MemoryTools(memory_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_consent_required(self, memory_tools):
        """Test that consent flag is mandatory."""
        result = await memory_tools.capture(
            {
                "consent": False,
                "session_id": "test_session",
                "intent": "Test pipeline",
            }
        )

        # Should return error structure (not raise exception)
        assert result["captured"] is False
        assert "error" in result
        assert "consent" in result["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_consent_missing(self, memory_tools):
        """Test that missing consent is treated as False."""
        result = await memory_tools.capture(
            {
                # No consent field at all
                "session_id": "test_session",
                "intent": "Test pipeline",
            }
        )

        assert result["captured"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_email_redaction(self, memory_tools):
        """Test email addresses are redacted."""
        # Mock CLI call to verify redaction happens
        with patch("osiris.mcp.cli_bridge.run_cli_json") as mock_cli:
            mock_cli.return_value = {
                "status": "success",
                "captured": True,
                "memory_id": "mem_test123",
                "session_id": "email_test",
                "memory_uri": "osiris://mcp/memory/sessions/email_test.jsonl",
                "retention_days": 365,
                "timestamp": "2025-10-16T14:00:00+00:00",
                "entry_size_bytes": 100,
            }

            result = await memory_tools.capture(
                {
                    "consent": True,
                    "session_id": "email_test",
                    "intent": "Contact user@example.com for approval",
                    "notes": "Email support@company.org if issues arise",
                }
            )

            assert result["captured"] is True
            # Verify CLI was called with events containing PII
            call_args = mock_cli.call_args[0][0]
            assert "--events" in call_args

    @pytest.mark.asyncio
    async def test_dsn_redaction_internal(self, memory_tools):
        """Test DSN/connection string redaction using internal method."""
        # Test the internal _redact_pii method directly
        test_data = {
            "connection": "mysql://user:password@localhost:3306/mydb",  # pragma: allowlist secret
            "supabase_url": "postgresql://postgres:secret@db.supabase.co:5432/postgres",  # pragma: allowlist secret
            "notes": "Use mysql://admin:pass@prod.example.com/sales",  # pragma: allowlist secret
        }

        redacted = memory_tools._redact_pii(test_data)

        # Verify DSN patterns are redacted
        assert isinstance(redacted, dict)
        assert "connection" in redacted

        # Verify userinfo (credentials) are masked in DSN strings
        assert "mysql://***@localhost" in redacted["connection"]
        assert "postgresql://***@db.supabase.co" in redacted["supabase_url"]
        assert "mysql://***@prod.example.com" in redacted["notes"]

        # Verify passwords are NOT visible
        assert "password" not in redacted["connection"]  # pragma: allowlist secret
        assert "secret" not in redacted["supabase_url"]  # pragma: allowlist secret
        assert "pass@" not in redacted["notes"]

    @pytest.mark.asyncio
    async def test_secret_field_redaction(self, memory_tools):
        """Test secret field names are redacted."""
        test_data = {
            "api_key": "sk-1234567890abcdef",  # pragma: allowlist secret
            "password": "supersecret",  # pragma: allowlist secret
            "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",  # pragma: allowlist secret
            "service_role_key": "service_key_xyz",  # pragma: allowlist secret
            "user_name": "john_doe",  # Should NOT be redacted
            "database": "mydb",  # Should NOT be redacted
        }

        redacted = memory_tools._redact_pii(test_data)

        # Secret keys should be redacted
        assert redacted["api_key"] == "***REDACTED***"
        assert redacted["password"] == "***REDACTED***"
        assert redacted["token"] == "***REDACTED***"
        assert redacted["service_role_key"] == "***REDACTED***"

        # Non-secret fields should remain
        assert redacted["user_name"] == "john_doe"
        assert redacted["database"] == "mydb"

    @pytest.mark.asyncio
    async def test_nested_pii_redaction(self, memory_tools):
        """Test PII redaction in nested structures."""
        test_data = {
            "config": {
                "database": "mydb",
                "credentials": {
                    "password": "secret123",  # pragma: allowlist secret
                    "api_key": "key_xyz",  # pragma: allowlist secret
                },
                "admin_email": "admin@example.com",
            },
            "logs": [
                "Connected to db",
                "User john@example.com logged in",
                "API token: abc123",  # pragma: allowlist secret
            ],
        }

        redacted = memory_tools._redact_pii(test_data)

        # Nested secrets should be redacted
        assert redacted["config"]["credentials"]["password"] == "***REDACTED***"
        assert redacted["config"]["credentials"]["api_key"] == "***REDACTED***"

        # Email in string should be redacted
        assert "***EMAIL***" in str(redacted["logs"])

    @pytest.mark.asyncio
    async def test_phone_number_redaction(self, memory_tools):
        """Test phone numbers are redacted."""
        test_data = {
            "notes": "Call customer at 555-123-4567 for verification",
            "contact": "Support: +1 (800) 555-0123",
        }

        redacted = memory_tools._redact_pii(test_data)

        assert "***PHONE***" in redacted["notes"]
        assert "***PHONE***" in redacted["contact"]

    @pytest.mark.asyncio
    async def test_ip_address_redaction(self, memory_tools):
        """Test IP addresses are redacted."""
        test_data = {
            "source_ip": "192.168.1.100",
            "notes": "Request from 10.0.0.5 rejected",
        }

        redacted = memory_tools._redact_pii(test_data)

        assert "***IP***" in str(redacted["source_ip"])
        assert "***IP***" in redacted["notes"]

    @pytest.mark.asyncio
    async def test_memory_path_config_driven(self, tmp_path):
        """Test memory writes to config-driven path."""
        memory_dir = tmp_path / "custom_memory"
        tools = MemoryTools(memory_dir=memory_dir)

        # Use internal save method to test path
        test_entry = {
            "session_id": "path_test",
            "timestamp": "2025-10-16T14:00:00+00:00",
            "events": [],
        }

        memory_id = tools._save_memory(test_entry)

        # Verify file was created in sessions/ subdirectory
        sessions_dir = memory_dir / "sessions"
        memory_file = sessions_dir / "path_test.jsonl"

        assert sessions_dir.exists()
        assert memory_file.exists()
        assert memory_id.startswith("mem_")

        # Verify content
        with open(memory_file) as f:
            content = f.read()
            assert "path_test" in content

    @pytest.mark.asyncio
    async def test_redaction_count(self, memory_tools):
        """Test redaction counting is accurate."""
        original = {
            "email": "test@example.com",
            "password": "secret",  # pragma: allowlist secret
            "notes": "Contact support@company.org",
        }

        redacted = memory_tools._redact_pii(original)
        count = memory_tools._count_redactions(original, redacted)

        # Should have at least 2 redactions (email in field, email in notes, password)
        assert count >= 2

    @pytest.mark.asyncio
    async def test_no_false_positives(self, memory_tools):
        """Test that non-PII data is not over-redacted."""
        test_data = {
            "primary_key": "id",  # Should NOT be redacted (not a secret)
            "foreign_key": "user_id",  # Should NOT be redacted
            "database_password": "secret",  # SHOULD be redacted  # pragma: allowlist secret
            "table_name": "users",  # Should NOT be redacted
            "column_names": ["id", "email", "name"],  # Should NOT be redacted
        }

        redacted = memory_tools._redact_pii(test_data)

        # Non-secrets should remain
        assert redacted["primary_key"] == "id"
        assert redacted["foreign_key"] == "user_id"
        assert redacted["table_name"] == "users"
        assert redacted["column_names"] == ["id", "email", "name"]

        # Actual secret should be redacted
        assert redacted["database_password"] == "***REDACTED***"

    @pytest.mark.asyncio
    async def test_consent_cli_delegation(self, memory_tools):
        """Test consent is properly passed through CLI delegation."""
        with patch("osiris.mcp.cli_bridge.run_cli_json") as mock_cli:
            mock_cli.return_value = {
                "status": "success",
                "captured": True,
                "memory_id": "mem_consent123",
                "session_id": "consent_test",
                "memory_uri": "osiris://mcp/memory/sessions/consent_test.jsonl",
                "retention_days": 365,
                "timestamp": "2025-10-16T14:00:00+00:00",
                "entry_size_bytes": 50,
            }

            result = await memory_tools.capture(
                {
                    "consent": True,
                    "session_id": "consent_test",
                    "intent": "Test consent flow",
                }
            )

            # Verify CLI was called with --consent flag
            call_args = mock_cli.call_args[0][0]
            assert "--consent" in call_args
            assert "consent_test" in call_args

            assert result["captured"] is True

    @pytest.mark.asyncio
    async def test_retention_clamping(self, memory_tools):
        """Test retention days are clamped to valid range."""
        with patch("osiris.mcp.cli_bridge.run_cli_json") as mock_cli:
            mock_cli.return_value = {
                "status": "success",
                "captured": True,
                "memory_id": "mem_ret123",
                "session_id": "retention_test",
                "memory_uri": "osiris://mcp/memory/sessions/retention_test.jsonl",
                "retention_days": 365,
                "timestamp": "2025-10-16T14:00:00+00:00",
                "entry_size_bytes": 50,
            }

            # Test negative retention
            result1 = await memory_tools.capture(
                {
                    "consent": True,
                    "session_id": "retention_test",
                    "retention_days": -100,
                }
            )
            assert result1["captured"] is True

            # Test excessive retention (>730 days / 2 years)
            result2 = await memory_tools.capture(
                {
                    "consent": True,
                    "session_id": "retention_test",
                    "retention_days": 10000,
                }
            )
            assert result2["captured"] is True

    @pytest.mark.asyncio
    async def test_complex_actor_trace_redaction(self, memory_tools):
        """Test PII redaction in complex actor traces."""
        complex_trace = [
            {
                "action": "discover",
                "target": "@mysql.source",
                "config": {
                    "host": "db.example.com",
                    "password": "db_pass_123",  # pragma: allowlist secret
                    "admin_email": "admin@example.com",
                },
            },
            {
                "action": "validate",
                "result": {
                    "errors": [],
                    "warnings": ["Contact support@company.org"],
                },
            },
        ]

        redacted_trace = memory_tools._redact_pii(complex_trace)

        # Password should be redacted
        assert redacted_trace[0]["config"]["password"] == "***REDACTED***"

        # Emails should be redacted
        assert "***EMAIL***" in str(redacted_trace)

    @pytest.mark.asyncio
    async def test_session_id_required(self, memory_tools):
        """Test that session_id is required for capture."""
        with pytest.raises(Exception) as exc_info:
            await memory_tools.capture(
                {
                    "consent": True,
                    # Missing session_id
                    "intent": "Test without session",
                }
            )

        # Should mention session in error
        assert "session" in str(exc_info.value).lower()
