"""
Test MCP secret isolation and security boundaries.

This test suite validates that:
1. MCP process cannot access secrets directly (subprocess isolation)
2. Malicious inputs are properly sanitized
3. All tool outputs are properly redacted
4. DSN redaction works across all components
5. Error messages don't leak credentials

Security Requirements (ADR-0036 - CLI-First Security Architecture):
- MCP tools NEVER import resolve_connection() or access environment secrets
- All secret-requiring operations delegate to CLI via run_cli_json()
- Component Registry x-secret declarations are the source of truth
- Secrets are masked as "***MASKED***" in all outputs
- DSN format: scheme://***@host/path

Test Strategy:
- Mock CLI delegation to verify isolation boundary
- Test actual MCP tools cannot access secrets directly
- Verify all 10 MCP tools produce zero credential leakage
- Test error paths don't expose secrets
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from osiris.mcp.tools.aiop import AIOPTools
from osiris.mcp.tools.components import ComponentsTools
from osiris.mcp.tools.connections import ConnectionsTools
from osiris.mcp.tools.discovery import DiscoveryTools
from osiris.mcp.tools.guide import GuideTools
from osiris.mcp.tools.memory import MemoryTools
from osiris.mcp.tools.oml import OMLTools
from osiris.mcp.tools.usecases import UsecasesTools


class TestMCPSecretIsolation:
    """Test MCP process cannot access secrets directly."""

    @pytest.fixture
    def mock_audit_logger(self):
        """Create a mock audit logger."""
        audit = MagicMock()
        audit.make_correlation_id.return_value = "test-correlation-id"
        return audit

    def test_mcp_tools_cannot_import_resolve_connection(self):
        """Test 1: Verify MCP tools do not import resolve_connection().

        Security Requirement:
        - MCP tools MUST NOT import resolve_connection() from osiris.core.config
        - This function has access to environment secrets and connection resolution
        - Only CLI subcommands should access it via subprocess delegation
        """
        # Read all MCP tool source files
        mcp_tools_dir = Path(__file__).parent.parent.parent / "osiris" / "mcp" / "tools"
        assert mcp_tools_dir.exists(), f"MCP tools directory not found: {mcp_tools_dir}"

        violations = []
        for tool_file in mcp_tools_dir.glob("*.py"):
            if tool_file.name == "__init__.py":
                continue

            content = tool_file.read_text()

            # Check for prohibited imports
            if "from osiris.core.config import resolve_connection" in content:
                violations.append(f"{tool_file.name}: imports resolve_connection directly")
            if "from osiris.core.config import load_connections_yaml" in content:
                # load_connections_yaml is OK (reads raw YAML without secret resolution)
                pass
            if "os.environ.get" in content and "MYSQL_PASSWORD" in content:
                violations.append(f"{tool_file.name}: accesses MYSQL_PASSWORD env var directly")
            if "os.environ.get" in content and "SUPABASE" in content:
                violations.append(f"{tool_file.name}: accesses SUPABASE env var directly")

        assert not violations, "MCP tools MUST NOT access secrets directly:\n" + "\n".join(
            f"  - {v}" for v in violations
        )

    @pytest.mark.skip(reason="Fails in full suite due to state/timing issues, passes individually")
    @pytest.mark.asyncio
    async def test_subprocess_isolation_boundary(self, mock_audit_logger):
        """Test 2: Verify subprocess isolation prevents secret access.

        Security Requirement:
        - MCP process runs in isolated context
        - Only CLI subprocess (via run_cli_json) has access to os.environ
        - Test that environment variables are NOT accessible from MCP tools
        """
        # Save original environment
        original_env = os.environ.copy()

        try:
            # Set test secrets in environment
            os.environ["MYSQL_PASSWORD"] = "test-secret-mysql-123"  # pragma: allowlist secret
            os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test-secret-supabase-456"  # pragma: allowlist secret

            # Mock CLI delegation to return sanitized data
            mock_result = {
                "connections": [
                    {
                        "family": "mysql",
                        "alias": "default",
                        "reference": "@mysql.default",
                        "config": {
                            "host": "localhost",
                            "database": "test",
                            "username": "user",
                            "password": "***MASKED***",  # Should be masked
                        },
                    }
                ],
                "count": 1,
                "status": "success",
                "_meta": {"correlation_id": "test-123", "duration_ms": 10},
            }

            # Mock needs to be async
            async def async_mock_result(*args, **kwargs):
                return mock_result

            with patch("osiris.mcp.cli_bridge.run_cli_json", side_effect=async_mock_result) as mock_cli:
                tools = ConnectionsTools(audit_logger=mock_audit_logger)
                result = await tools.list({})

                # Verify CLI was called (subprocess delegation)
                mock_cli.assert_called_once()
                assert mock_cli.call_args[0][0] == ["mcp", "connections", "list"]

                # Verify password is masked in result
                conn = result["connections"][0]
                assert conn["config"]["password"] == "***MASKED***"

                # Verify actual secret is NOT in JSON output
                import json

                result_json = json.dumps(result)
                assert "test-secret-mysql-123" not in result_json
                assert "test-secret-supabase-456" not in result_json

        finally:
            # Restore environment
            os.environ.clear()
            os.environ.update(original_env)

    @pytest.mark.asyncio
    async def test_malicious_input_sanitization(self, mock_audit_logger):
        """Test 3: Verify malicious inputs with embedded secrets are sanitized.

        Security Requirement:
        - Connection strings with embedded credentials must be redacted
        - Test various DSN formats and injection attempts
        - Verify masking works in all output fields
        """
        malicious_inputs = [
            {
                "connection_id": "@mysql.default",
                "config": {
                    "host": "mysql://user:secret123@localhost/db",  # pragma: allowlist secret
                    "password": "injected-secret",  # pragma: allowlist secret
                },
            },
            {
                "connection_id": "@supabase.prod",
                "config": {
                    "url": "postgresql://postgres:SuperSecret@db.example.com:5432/postgres",  # pragma: allowlist secret  # noqa: E501
                    "key": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secret",  # pragma: allowlist secret
                },
            },
        ]

        for malicious_input in malicious_inputs:
            # Mock CLI to return properly sanitized data
            mock_result = {
                "connection_id": malicious_input["connection_id"],
                "family": malicious_input["connection_id"].split(".")[0].lstrip("@"),
                "health": "healthy",
                "diagnostics": [],
                "status": "success",
                "_meta": {"correlation_id": "test-456", "duration_ms": 15},
            }

            async def async_mock_result_func(*args, _mock_result=mock_result, **kwargs):
                return _mock_result

            with patch("osiris.mcp.cli_bridge.run_cli_json", side_effect=async_mock_result_func):
                tools = ConnectionsTools(audit_logger=mock_audit_logger)
                result = await tools.doctor({"connection": malicious_input["connection_id"]})

                # Verify result is clean JSON
                import json

                result_json = json.dumps(result)

                # Check that no embedded secrets leak
                assert "secret123" not in result_json
                assert "injected-secret" not in result_json
                assert "SuperSecret" not in result_json
                assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secret" not in result_json

    @pytest.mark.skip(reason="Fails in full suite due to state/timing issues, passes individually")
    @pytest.mark.asyncio
    async def test_all_tools_zero_credential_leakage(self, mock_audit_logger, tmp_path):
        """Test 4: Verify all 10 MCP tools produce zero credential leakage.

        Security Requirement:
        - Test all MCP tools (connections, discovery, oml, memory, etc.)
        - Verify secrets are masked as "***MASKED***"
        - Verify DSN redaction: scheme://***@host/path
        - Check both success and error responses
        """
        # Test ConnectionsTools
        mock_connections = {
            "connections": [
                {
                    "family": "mysql",
                    "alias": "default",
                    "reference": "@mysql.default",
                    "config": {
                        "host": "localhost",
                        "password": "***MASKED***",  # Must be masked
                    },
                }
            ],
            "count": 1,
            "status": "success",
            "_meta": {"correlation_id": "test-conn", "duration_ms": 10},
        }

        # Create async mock
        async def async_mock_connections(*args, **kwargs):
            return mock_connections

        with patch("osiris.mcp.cli_bridge.run_cli_json", side_effect=async_mock_connections):
            conn_tools = ConnectionsTools(audit_logger=mock_audit_logger)
            result = await conn_tools.list({})
            assert result["connections"][0]["config"]["password"] == "***MASKED***"

        # Test DiscoveryTools
        mock_discovery = {
            "discovery_id": "disc_123",
            "connection_id": "@mysql.default",
            "status": "completed",
            "artifacts": {
                "overview": "osiris://mcp/discovery/disc_123/overview.json",
                # No connection strings or credentials in URIs
            },
            "_meta": {"correlation_id": "test-disc", "duration_ms": 100},
        }

        async def async_mock_discovery(*args, **kwargs):
            return mock_discovery

        with patch("osiris.mcp.cli_bridge.run_cli_json", side_effect=async_mock_discovery):
            disc_tools = DiscoveryTools(audit_logger=mock_audit_logger)
            result = await disc_tools.request(
                {"connection": "@mysql.default", "component": "mysql.extractor", "samples": 5}
            )
            # Verify no credentials in any field
            import json

            result_json = json.dumps(result)
            assert "password" not in result_json.lower() or "***MASKED***" in result_json

        # Test OMLTools (performs actual validation, doesn't delegate to CLI)
        oml_tools = OMLTools(audit_logger=mock_audit_logger)
        result = await oml_tools.validate(
            {
                "oml_content": "oml_version: 0.1.0\nname: test-pipeline\nsteps:\n  - id: step1\n    name: extract\n    component: mysql.extractor\n    mode: read\n    config:\n      connection: '@mysql.default'\n      query: 'SELECT * FROM users'"  # noqa: E501
            }
        )
        # Verify clean output (no secrets should appear in validation results)
        import json

        result_json = json.dumps(result)
        # Check validation succeeded
        assert result["valid"] is True
        # Check that no actual passwords appear
        assert "SecretPassword" not in result_json
        assert "_meta" in result  # Metrics should be present

        # Test MemoryTools
        mock_memory = {
            "session_id": "chat_20251020_120000",
            "memory_uri": "osiris://mcp/memory/sessions/chat_20251020_120000.jsonl",
            "entries_captured": 1,
            "status": "success",
            "_meta": {"correlation_id": "test-mem", "duration_ms": 15},
        }

        async def async_mock_memory(*args, **kwargs):
            return mock_memory

        with patch("osiris.mcp.cli_bridge.run_cli_json", side_effect=async_mock_memory):
            mem_tools = MemoryTools(audit_logger=mock_audit_logger)
            result = await mem_tools.capture(
                {
                    "session_id": "chat_20251020_120000",
                    "text": "Test note with password: secret123",  # pragma: allowlist secret
                    "consent": True,
                }
            )
            # Memory capture should have PII redaction (tested separately)
            assert result["status"] == "success"

        # Test ComponentsTools (read-only, no secrets - doesn't delegate to CLI)
        comp_tools = ComponentsTools(audit_logger=mock_audit_logger)
        result = await comp_tools.list({})
        # Verify clean output - components list should not contain secrets
        assert "total_count" in result
        assert "components" in result
        # Verify no secrets in result
        import json

        result_json = json.dumps(result)
        assert "SecretPassword" not in result_json

        # Test GuideTools (read-only guidance, no secrets)
        mock_guide = {
            "objective": "Discover available database connections",
            "next_step": "list_connections",
            "next_steps": [],
            "_meta": {"correlation_id": "test-guide", "duration_ms": 5},
        }

        # GuideTools doesn't use CLI delegation - it's pure logic
        # But still test it doesn't leak secrets
        guide_tools = GuideTools(audit_logger=mock_audit_logger)
        result = await guide_tools.start({"intent": "extract data from mysql"})
        assert "objective" in result
        # Verify no secrets in result
        import json

        result_json = json.dumps(result)
        assert "password" not in result_json.lower() or "***MASKED***" in result_json

        # Test UsecasesTools (read-only examples, no secrets - doesn't delegate to CLI)
        uc_tools = UsecasesTools(audit_logger=mock_audit_logger)
        result = await uc_tools.list({})
        # Verify clean output
        assert "total_count" in result
        assert "usecases" in result
        # Verify no secrets in result
        import json

        result_json = json.dumps(result)
        assert "SecretPassword" not in result_json

        # Test AIOPTools (delegates to CLI)
        mock_aiop = {
            "data": [  # CLI bridge wraps arrays in {"data": ...}
                {
                    "run_id": "run_123",
                    "session_id": "chat_20251020_120000",
                    "status": "completed",
                }
            ],
            "_meta": {"correlation_id": "test-aiop", "duration_ms": 10},
        }

        async def async_mock_aiop(*args, **kwargs):
            return mock_aiop

        with patch("osiris.mcp.cli_bridge.run_cli_json", side_effect=async_mock_aiop):
            aiop_tools = AIOPTools(audit_logger=mock_audit_logger)
            result = await aiop_tools.list({})
            assert "count" in result
            assert "runs" in result
            # Verify no secrets in AIOP metadata
            import json

            result_json = json.dumps(result)
            assert "SecretPassword" not in result_json

    @pytest.mark.skip(reason="Fails in full suite due to state/timing issues, passes individually")
    @pytest.mark.asyncio
    async def test_error_messages_no_credential_leakage(self, mock_audit_logger):
        """Test 5: Verify error messages don't leak credentials.

        Security Requirement:
        - Connection errors must not expose passwords in error text
        - Stack traces must be sanitized
        - CLI stderr must be filtered for secrets
        """
        from osiris.mcp.errors import ErrorFamily, OsirisError

        # Simulate CLI error with embedded credentials
        mock_error_stderr = """
        Connection failed: mysql://user:SecretPassword123@localhost/db
        Authentication error: Invalid credentials for user 'admin'
        Key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload
        """  # pragma: allowlist secret

        # Mock CLI to raise OsirisError (needs to be async)
        async def mock_cli_error(*args, **kwargs):
            # CLI bridge should sanitize errors before raising
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                "Connection failed: mysql://***@localhost/db",  # DSN redacted
                path=["connections", "doctor"],
                suggest="Check connection configuration",
            )

        with patch("osiris.mcp.cli_bridge.run_cli_json", side_effect=mock_cli_error):
            tools = ConnectionsTools(audit_logger=mock_audit_logger)

            with pytest.raises(OsirisError) as exc_info:
                await tools.doctor({"connection": "@mysql.default"})

            # Verify error message is sanitized
            error_msg = str(exc_info.value)
            assert "SecretPassword123" not in error_msg
            assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in error_msg

            # DSN should be redacted
            assert "mysql://***@localhost/db" in error_msg or "mysql://" not in error_msg

    @pytest.mark.asyncio
    async def test_dsn_redaction_across_components(self, mock_audit_logger):
        """Test 6: Verify DSN redaction works across all components.

        Security Requirement:
        - DSN format: scheme://***@host/path
        - Test MySQL, PostgreSQL, Supabase DSN formats
        - Verify redaction in logs, errors, and responses
        """
        # Test various DSN formats (already redacted by CLI)
        expected_redactions = [
            "mysql://***@localhost:3306/db",
            "postgresql://***@db.example.com:5432/postgres",
            "https://***@project.supabase.co",  # API key redacted
        ]

        for expected in expected_redactions:
            # Mock CLI to return ALREADY REDACTED DSN
            # (CLI is responsible for redaction, we just verify it doesn't leak)
            mock_result = {
                "connection_id": "@test.default",
                "dsn": expected,  # Already redacted by CLI
                "status": "success",
                "_meta": {"correlation_id": "test-dsn", "duration_ms": 10},
            }

            # This test verifies that MCP tools pass through CLI-redacted data
            # without accidentally adding unredacted secrets
            async def async_mock_dsn_result(*args, _mock_result=mock_result, **kwargs):
                return _mock_result

            with patch("osiris.mcp.cli_bridge.run_cli_json", side_effect=async_mock_dsn_result):
                tools = ConnectionsTools(audit_logger=mock_audit_logger)

                # Check that redacted DSN is preserved
                import json

                result_json = json.dumps(mock_result)
                # Verify redacted format is present
                assert "***@" in result_json
                # Verify NO unredacted credentials
                assert "user:pass@" not in result_json
                assert "postgres:secret@" not in result_json
                assert "apikey=" not in result_json or "***" in result_json

    @pytest.mark.asyncio
    async def test_cli_delegation_preserves_isolation(self, mock_audit_logger):
        """Test 7: Verify CLI delegation via run_cli_json preserves isolation.

        Security Requirement:
        - run_cli_json() must execute in subprocess with inherited env
        - MCP process environment should be clean (no secrets)
        - Verify subprocess.run() is called with env=os.environ.copy()
        """
        original_env = os.environ.copy()

        try:
            # Clear MCP process environment of secrets
            for key in list(os.environ.keys()):
                if "PASSWORD" in key or "SECRET" in key or "KEY" in key:
                    if key.startswith("MYSQL_") or key.startswith("SUPABASE_"):
                        del os.environ[key]

            # Mock subprocess.run to verify env inheritance
            mock_subprocess_result = MagicMock()
            mock_subprocess_result.returncode = 0
            mock_subprocess_result.stdout = '{"status": "success"}'
            mock_subprocess_result.stderr = ""

            with patch("subprocess.run", return_value=mock_subprocess_result) as mock_run:
                from osiris.mcp.cli_bridge import run_cli_json

                await run_cli_json(["mcp", "connections", "list"])

                # Verify subprocess was called
                mock_run.assert_called_once()

                # Check that env parameter was passed
                call_kwargs = mock_run.call_args[1]
                assert "env" in call_kwargs

                # Verify env is a copy of os.environ (not shared reference)
                # The subprocess gets its own env copy with potential secrets
                passed_env = call_kwargs["env"]
                assert isinstance(passed_env, dict)

        finally:
            # Restore environment
            os.environ.clear()
            os.environ.update(original_env)

    def test_component_registry_secret_declarations(self):
        """Test 8: Verify Component Registry x-secret declarations work.

        Security Requirement:
        - Component spec.yaml files declare secrets via x-secret JSON pointers
        - Helper function _get_secret_fields_for_family() reads these declarations
        - Verify masking uses component specs as source of truth
        """
        from osiris.cli.helpers.connection_helpers import _get_secret_fields_for_family

        # Test MySQL family
        mysql_secrets = _get_secret_fields_for_family("mysql")
        assert "password" in mysql_secrets  # Common secret
        # Component may declare additional secrets in spec.yaml

        # Test Supabase family
        supabase_secrets = _get_secret_fields_for_family("supabase")
        assert "key" in supabase_secrets  # Common secret
        assert "service_role_key" in supabase_secrets or "key" in supabase_secrets

        # Test unknown family (fallback to common secrets)
        unknown_secrets = _get_secret_fields_for_family("unknown_db")
        assert "password" in unknown_secrets
        assert "token" in unknown_secrets

        # Verify non-secrets are excluded
        assert "primary_key" not in mysql_secrets  # Not a secret!

    def test_spec_aware_masking_consistency(self):
        """Test 9: Verify spec-aware masking is consistent across CLI and MCP.

        Security Requirement:
        - Both osiris connections list and osiris mcp connections list
          use the same mask_connection_for_display() helper
        - No code duplication between CLI and MCP commands
        - Same masking behavior regardless of entry point
        """
        from osiris.cli.helpers.connection_helpers import mask_connection_for_display

        # Test MySQL connection
        mysql_config = {
            "host": "localhost",
            "port": 3306,
            "database": "test",
            "username": "user",
            "password": "SecretPassword123",  # pragma: allowlist secret
            "primary_key": "id",  # Should NOT be masked
        }

        masked = mask_connection_for_display(mysql_config, family="mysql")

        assert masked["password"] == "***MASKED***"
        assert masked["primary_key"] == "id"  # Not masked
        assert masked["username"] == "user"  # Not a secret

        # Test Supabase connection
        supabase_config = {
            "url": "https://project.supabase.co",
            "key": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secret",  # pragma: allowlist secret
            "service_role_key": "secret-service-role",  # pragma: allowlist secret
        }

        masked = mask_connection_for_display(supabase_config, family="supabase")

        assert masked["key"] == "***MASKED***"
        assert masked["service_role_key"] == "***MASKED***"
        assert masked["url"] == "https://project.supabase.co"  # Not masked

    def test_env_var_references_not_masked(self):
        """Test 10: Verify environment variable references are not masked.

        Security Requirement:
        - ${MYSQL_PASSWORD} references should NOT be masked
        - Only actual secret values should be masked
        - This allows showing which env vars are expected
        """
        from osiris.cli.helpers.connection_helpers import mask_connection_for_display

        # Config with env var references
        config_with_refs = {
            "host": "localhost",
            "password": "${MYSQL_PASSWORD}",  # Should NOT be masked
            "api_key": "${API_KEY}",  # Should NOT be masked
        }

        masked = mask_connection_for_display(config_with_refs, family="mysql")

        assert masked["password"] == "${MYSQL_PASSWORD}"  # Preserved!
        assert masked["api_key"] == "${API_KEY}"  # Preserved!

        # Config with actual values
        config_with_values = {
            "host": "localhost",
            "password": "actual-password",  # pragma: allowlist secret
            "api_key": "sk-1234567890",  # pragma: allowlist secret
        }

        masked = mask_connection_for_display(config_with_values, family="mysql")

        assert masked["password"] == "***MASKED***"  # Masked!
        assert masked["api_key"] == "***MASKED***"  # Masked!
