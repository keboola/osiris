"""
Test comprehensive error scenarios for MCP Phase 3.

Tests all error code patterns from ADR-0036 and MCP spec, covering:
- ERROR_CODES pattern matching (from errors.py)
- CLI subprocess failures (exit codes 1-255)
- Timeout scenarios (>30s default)
- Invalid/malformed JSON responses
- Network/subprocess failures
- Connection error mapping
"""

import json
import subprocess
from unittest.mock import Mock, patch

import pytest

from osiris.mcp.cli_bridge import map_cli_error_to_mcp, run_cli_json
from osiris.mcp.errors import (
    DiscoveryError,
    ErrorFamily,
    LintError,
    OsirisError,
    PolicyError,
    SchemaError,
    SemanticError,
)
from osiris.mcp.errors import map_cli_error_to_mcp as map_error_from_exception


class TestErrorCodePatterns:
    """Test 1: All ERROR_CODES patterns from errors.py."""

    def test_schema_errors_oml001_oml007(self):
        """Test OML schema error codes (OML001-OML007)."""
        # OML001: missing required field: name
        error = SchemaError("missing required field: name", path=["pipeline", "name"])
        assert error.to_dict()["code"] == "SCHEMA/OML001"

        # OML002: missing required field: steps
        error = SchemaError("missing required field: steps", path=["pipeline", "steps"])
        assert error.to_dict()["code"] == "SCHEMA/OML002"

        # OML003: missing required field: version
        error = SchemaError("missing required field: version", path=["pipeline", "version"])
        assert error.to_dict()["code"] == "SCHEMA/OML003"

        # OML004: generic missing field
        error = SchemaError("missing required field", path=["pipeline", "config"])
        assert error.to_dict()["code"] == "SCHEMA/OML004"

        # OML005: invalid type
        error = SchemaError("invalid type", path=["pipeline", "steps", "0", "type"])
        assert error.to_dict()["code"] == "SCHEMA/OML005"

        # OML006: invalid format
        error = SchemaError("invalid format", path=["pipeline", "steps", "0", "config"])
        assert error.to_dict()["code"] == "SCHEMA/OML006"

        # OML007: unknown property
        error = SchemaError("unknown property", path=["pipeline", "invalid_field"])
        assert error.to_dict()["code"] == "SCHEMA/OML007"

    def test_schema_errors_oml010_yaml_parse(self):
        """Test YAML/OML parse errors (OML010)."""
        # YAML parse error
        error = SchemaError("yaml parse error: unexpected indentation", path=["file"])
        assert error.to_dict()["code"] == "SCHEMA/OML010"

        # OML parse error
        error = SchemaError("oml parse error: invalid pipeline format", path=["file"])
        assert error.to_dict()["code"] == "SCHEMA/OML010"

    def test_schema_errors_oml020_intent(self):
        """Test intent requirement error (OML020)."""
        error = SchemaError("intent is required", path=["conversation", "intent"])
        assert error.to_dict()["code"] == "SCHEMA/OML020"

    def test_semantic_errors_sem001_sem005(self):
        """Test semantic error codes (SEM001-SEM005)."""
        # SEM001: unknown tool
        error = SemanticError("unknown tool", path=["pipeline", "steps", "0", "tool"])
        assert error.to_dict()["code"] == "SEMANTIC/SEM001"

        # SEM002: invalid connection
        error = SemanticError("invalid connection", path=["pipeline", "steps", "0", "connection"])
        assert error.to_dict()["code"] == "SEMANTIC/SEM002"

        # SEM003: invalid component
        error = SemanticError("invalid component", path=["pipeline", "steps", "0", "component"])
        assert error.to_dict()["code"] == "SEMANTIC/SEM003"

        # SEM004: circular dependency
        error = SemanticError("circular dependency", path=["pipeline", "steps"])
        assert error.to_dict()["code"] == "SEMANTIC/SEM004"

        # SEM005: duplicate name
        error = SemanticError("duplicate name", path=["pipeline", "steps", "1", "name"])
        assert error.to_dict()["code"] == "SEMANTIC/SEM005"

    def test_discovery_errors_disc001_disc005(self):
        """Test discovery error codes (DISC001-DISC005)."""
        # DISC001: connection not found
        error = DiscoveryError("connection not found", path=["connections", "@mysql.main"])
        assert error.to_dict()["code"] == "DISCOVERY/DISC001"

        # DISC002: source unreachable
        error = DiscoveryError("source unreachable", path=["connections", "@mysql.main"])
        assert error.to_dict()["code"] == "DISCOVERY/DISC002"

        # DISC003: permission denied
        error = DiscoveryError("permission denied", path=["connections", "@mysql.main"])
        assert error.to_dict()["code"] == "DISCOVERY/DISC003"

        # DISC005: invalid schema
        error = DiscoveryError("invalid schema", path=["connections", "@mysql.main", "database"])
        assert error.to_dict()["code"] == "DISCOVERY/DISC005"

    def test_lint_errors_lint001_lint003(self):
        """Test lint error codes (LINT001-LINT003)."""
        # LINT001: naming convention
        error = LintError("naming convention", path=["pipeline", "steps", "0", "name"])
        assert error.to_dict()["code"] == "LINT/LINT001"

        # LINT002: deprecated feature
        error = LintError("deprecated feature", path=["pipeline", "steps", "0", "type"])
        assert error.to_dict()["code"] == "LINT/LINT002"

        # LINT003: performance warning
        error = LintError("performance warning", path=["pipeline", "steps", "0", "config"])
        assert error.to_dict()["code"] == "LINT/LINT003"

    def test_policy_errors_pol001_pol005(self):
        """Test policy error codes (POL001-POL005)."""
        # POL001: consent required
        error = PolicyError("consent required", path=["memory", "capture"])
        assert error.to_dict()["code"] == "POLICY/POL001"

        # POL002: payload too large
        error = PolicyError("payload too large", path=["request", "body"])
        assert error.to_dict()["code"] == "POLICY/POL002"

        # POL003: rate limit exceeded
        error = PolicyError("rate limit exceeded", path=["api", "rate_limit"])
        assert error.to_dict()["code"] == "POLICY/POL003"

        # POL004: unauthorized
        error = PolicyError("unauthorized", path=["auth"])
        assert error.to_dict()["code"] == "POLICY/POL004"

        # POL005: forbidden operation
        error = PolicyError("forbidden operation", path=["operation"])
        assert error.to_dict()["code"] == "POLICY/POL005"

    def test_connection_errors_e_conn_patterns(self):
        """Test connection error codes (E_CONN_*)."""
        # E_CONN_SECRET_MISSING: missing environment variable
        error = map_error_from_exception("missing environment variable MYSQL_PASSWORD")
        assert error.to_dict()["code"] == "SEMANTIC/E_CONN_SECRET_MISSING"

        # E_CONN_AUTH_FAILED: authentication failed
        error = map_error_from_exception("authentication failed: invalid password")
        assert error.to_dict()["code"] == "SEMANTIC/E_CONN_AUTH_FAILED"

        # E_CONN_REFUSED: connection refused
        error = map_error_from_exception("connection refused by server")
        assert error.to_dict()["code"] == "SEMANTIC/E_CONN_REFUSED"

        # E_CONN_DNS: dns resolution failed
        error = map_error_from_exception("dns resolution failed: no such host")
        assert error.to_dict()["code"] == "SEMANTIC/E_CONN_DNS"

        # E_CONN_UNREACHABLE: could not connect
        error = map_error_from_exception("could not connect to database server")
        assert error.to_dict()["code"] == "SEMANTIC/E_CONN_UNREACHABLE"

        # E_CONN_TIMEOUT: connection timeout
        error = map_error_from_exception("connection timeout after 30s")
        assert error.to_dict()["code"] == "DISCOVERY/E_CONN_TIMEOUT"

    def test_error_code_determinism(self):
        """Test that error codes are deterministic for same messages."""
        # Same message should produce same code
        error1 = SchemaError("missing required field: name")
        error2 = SchemaError("missing required field: name")
        assert error1.to_dict()["code"] == error2.to_dict()["code"]

        # Different messages should produce different codes (via hash)
        error3 = SchemaError("unique error message xyz123")
        error4 = SchemaError("different error message abc456")
        assert error3.to_dict()["code"] != error4.to_dict()["code"]

    def test_unknown_error_fallback_hash(self):
        """Test unknown errors get hash-based codes."""
        error = SemanticError("This is a completely unique error message for testing 2025-10-20")
        code = error.to_dict()["code"]

        # Should be SEMANTIC/<HASH>
        assert code.startswith("SEMANTIC/SEM")
        # Hash should be 3 uppercase hex chars
        hash_part = code.split("/")[1][3:]  # Strip "SEM" prefix
        assert len(hash_part) == 3
        assert hash_part.isalnum()

    def test_error_pattern_priority_longest_first(self):
        """Test that longest patterns match first (as per sorted_patterns)."""
        # "missing environment variable" should match before "environment variable"
        error = map_error_from_exception("missing environment variable MYSQL_PASSWORD not set")
        assert error.to_dict()["code"] == "SEMANTIC/E_CONN_SECRET_MISSING"

        # "authentication failed" should match before generic patterns
        error = map_error_from_exception("authentication failed: invalid password provided")
        assert error.to_dict()["code"] == "SEMANTIC/E_CONN_AUTH_FAILED"


class TestCliSubprocessFailures:
    """Test 2: CLI subprocess failures (exit codes 1-255)."""

    def test_exit_code_1_general_error(self):
        """Test exit code 1 maps to SEMANTIC error."""
        error = map_cli_error_to_mcp(
            exit_code=1, stderr="General execution error", cmd=["osiris", "mcp", "connections", "list"]
        )
        assert error.family == ErrorFamily.SEMANTIC
        assert "General execution error" in str(error)
        assert error.suggest is not None

    def test_exit_code_2_schema_validation(self):
        """Test exit code 2 maps to SCHEMA error."""
        error = map_cli_error_to_mcp(
            exit_code=2,
            stderr="Invalid argument: connection_id required",
            cmd=["osiris", "mcp", "connections", "doctor"],
        )
        assert error.family == ErrorFamily.SCHEMA
        assert "Invalid argument" in str(error)

    def test_exit_code_3_discovery_failure(self):
        """Test exit code 3 maps to DISCOVERY error."""
        error = map_cli_error_to_mcp(
            exit_code=3,
            stderr="Discovery operation failed: database unreachable",
            cmd=["osiris", "mcp", "discovery", "run"],
        )
        assert error.family == ErrorFamily.DISCOVERY
        assert "Discovery operation failed" in str(error)

    def test_exit_code_4_policy_violation(self):
        """Test exit code 4 maps to POLICY error."""
        error = map_cli_error_to_mcp(
            exit_code=4, stderr="Policy violation: consent required", cmd=["osiris", "mcp", "memory", "capture"]
        )
        assert error.family == ErrorFamily.POLICY
        assert "Policy violation" in str(error)

    def test_exit_code_5_execution_error(self):
        """Test exit code 5 maps to SEMANTIC error."""
        error = map_cli_error_to_mcp(
            exit_code=5, stderr="Execution failed: pipeline step error", cmd=["osiris", "run", "pipeline.yaml"]
        )
        assert error.family == ErrorFamily.SEMANTIC
        assert "Execution failed" in str(error)

    def test_exit_code_124_timeout(self):
        """Test exit code 124 (timeout) maps to DISCOVERY error."""
        error = map_cli_error_to_mcp(
            exit_code=124, stderr="Command timed out after 30 seconds", cmd=["osiris", "mcp", "discovery", "run"]
        )
        assert error.family == ErrorFamily.DISCOVERY
        assert "Command timed out" in str(error)
        assert "timeout" in error.suggest.lower()

    def test_exit_code_127_command_not_found(self):
        """Test exit code 127 (command not found) maps to SEMANTIC error."""
        error = map_cli_error_to_mcp(
            exit_code=127, stderr="/bin/sh: osiris: command not found", cmd=["osiris", "mcp", "connections", "list"]
        )
        assert error.family == ErrorFamily.SEMANTIC
        assert "command not found" in str(error).lower()
        assert "install" in error.suggest.lower()

    def test_exit_code_130_sigint(self):
        """Test exit code 130 (SIGINT) maps to SEMANTIC error."""
        error = map_cli_error_to_mcp(
            exit_code=130, stderr="Interrupted by user", cmd=["osiris", "mcp", "discovery", "run"]
        )
        assert error.family == ErrorFamily.SEMANTIC
        assert "Interrupted" in str(error)

    def test_exit_code_137_sigkill(self):
        """Test exit code 137 (SIGKILL) maps to SEMANTIC error."""
        error = map_cli_error_to_mcp(
            exit_code=137, stderr="Killed by system", cmd=["osiris", "mcp", "discovery", "run"]
        )
        assert error.family == ErrorFamily.SEMANTIC
        assert "Killed" in str(error)

    def test_exit_code_143_sigterm(self):
        """Test exit code 143 (SIGTERM) maps to SEMANTIC error."""
        error = map_cli_error_to_mcp(
            exit_code=143, stderr="Terminated gracefully", cmd=["osiris", "mcp", "discovery", "run"]
        )
        assert error.family == ErrorFamily.SEMANTIC
        assert "Terminated" in str(error)

    def test_unknown_exit_code_fallback(self):
        """Test unknown exit codes fallback to SEMANTIC error."""
        error = map_cli_error_to_mcp(exit_code=99, stderr="Unknown error occurred", cmd=["osiris", "mcp", "test"])
        assert error.family == ErrorFamily.SEMANTIC
        assert "Unknown error" in str(error)

    def test_error_includes_command_info(self):
        """Test that errors include command information."""
        error = map_cli_error_to_mcp(exit_code=1, stderr="Error message", cmd=["osiris", "mcp", "connections", "list"])
        assert error.path == ["cli_bridge", "run_cli_json"]
        # Command info should be in suggest or message context
        assert error.suggest is not None

    def test_multiline_stderr_extraction(self):
        """Test that multiline stderr extracts last line as message."""
        stderr = """
        Line 1: Some debug info
        Line 2: More context
        Line 3: Actual error message here
        """
        error = map_cli_error_to_mcp(exit_code=1, stderr=stderr, cmd=["osiris", "test"])
        # Should extract last non-empty line
        assert "Actual error message here" in str(error)

    def test_connection_error_suggestion(self):
        """Test connection errors get helpful suggestions."""
        error = map_cli_error_to_mcp(
            exit_code=1,
            stderr="Connection failed: database unreachable",
            cmd=["osiris", "mcp", "connections", "doctor"],
        )
        assert "connection" in error.suggest.lower()

    def test_permission_error_suggestion(self):
        """Test permission errors get helpful suggestions."""
        error = map_cli_error_to_mcp(
            exit_code=1, stderr="Permission denied: cannot write to file", cmd=["osiris", "run", "pipeline.yaml"]
        )
        assert "permission" in error.suggest.lower()


@pytest.mark.asyncio
class TestTimeoutScenarios:
    """Test 3: Timeout scenarios (>30s default)."""

    async def test_default_timeout_30s(self):
        """Test default timeout is 30 seconds."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["osiris"], 30.0)):
            with patch("osiris.mcp.cli_bridge.ensure_base_path"):
                with pytest.raises(OsirisError) as exc_info:
                    await run_cli_json(["mcp", "discovery", "run"])

        assert exc_info.value.family == ErrorFamily.DISCOVERY
        assert "timed out after 30" in str(exc_info.value).lower()
        assert "timeout" in exc_info.value.suggest.lower()

    async def test_custom_timeout_60s(self):
        """Test custom timeout configuration."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["osiris"], 60.0)):
            with patch("osiris.mcp.cli_bridge.ensure_base_path"):
                with pytest.raises(OsirisError) as exc_info:
                    await run_cli_json(["mcp", "discovery", "run"], timeout_s=60.0)

        assert "60" in str(exc_info.value)

    async def test_timeout_error_family(self):
        """Test timeouts map to DISCOVERY error family."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["osiris"], 30.0)):
            with patch("osiris.mcp.cli_bridge.ensure_base_path"):
                with pytest.raises(OsirisError) as exc_info:
                    await run_cli_json(["mcp", "discovery", "run"])

        assert exc_info.value.family == ErrorFamily.DISCOVERY

    async def test_timeout_includes_suggestion(self):
        """Test timeout errors include helpful suggestions."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["osiris"], 30.0)):
            with patch("osiris.mcp.cli_bridge.ensure_base_path"):
                with pytest.raises(OsirisError) as exc_info:
                    await run_cli_json(["mcp", "discovery", "run"])

        assert exc_info.value.suggest is not None
        assert "timeout" in exc_info.value.suggest.lower() or "increase" in exc_info.value.suggest.lower()

    async def test_timeout_path_tracking(self):
        """Test timeout errors include proper path."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["osiris"], 30.0)):
            with patch("osiris.mcp.cli_bridge.ensure_base_path"):
                with pytest.raises(OsirisError) as exc_info:
                    await run_cli_json(["mcp", "discovery", "run"])

        assert exc_info.value.path == ["cli_bridge", "timeout"]


@pytest.mark.asyncio
class TestInvalidMalformedResponses:
    """Test 4: Invalid/malformed responses."""

    async def test_invalid_json_syntax(self):
        """Test subprocess returns syntactically invalid JSON."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "{invalid json syntax here"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            with patch("osiris.mcp.cli_bridge.ensure_base_path"):
                with pytest.raises(OsirisError) as exc_info:
                    await run_cli_json(["mcp", "connections", "list"])

        assert exc_info.value.family == ErrorFamily.SEMANTIC
        assert "json" in str(exc_info.value).lower()
        assert "invalid" in str(exc_info.value).lower()

    async def test_empty_json_response(self):
        """Test subprocess returns empty output."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            with patch("osiris.mcp.cli_bridge.ensure_base_path"):
                with pytest.raises(OsirisError) as exc_info:
                    await run_cli_json(["mcp", "connections", "list"])

        assert exc_info.value.family == ErrorFamily.SEMANTIC

    async def test_non_json_text_response(self):
        """Test subprocess returns plain text instead of JSON."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "This is just plain text, not JSON"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            with patch("osiris.mcp.cli_bridge.ensure_base_path"):
                with pytest.raises(OsirisError) as exc_info:
                    await run_cli_json(["mcp", "connections", "list"])

        assert exc_info.value.family == ErrorFamily.SEMANTIC
        assert "json" in str(exc_info.value).lower()

    async def test_partial_json_output(self):
        """Test subprocess returns truncated/partial JSON."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = '{"connections": [{"family": "mysql", "alias":'  # Truncated
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            with patch("osiris.mcp.cli_bridge.ensure_base_path"):
                with pytest.raises(OsirisError) as exc_info:
                    await run_cli_json(["mcp", "connections", "list"])

        assert exc_info.value.family == ErrorFamily.SEMANTIC

    async def test_json_with_control_characters(self):
        """Test subprocess returns JSON with invalid control characters."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = '{"message": "Error: \x00\x01\x02 invalid chars"}'
        mock_result.stderr = ""

        # This might actually parse successfully, but let's test handling
        with patch("subprocess.run", return_value=mock_result):
            with patch("osiris.mcp.cli_bridge.ensure_base_path"):
                try:
                    result = await run_cli_json(["mcp", "test"])
                    # If it parses, check it's handled gracefully
                    assert isinstance(result, dict)
                except OsirisError as e:
                    # If it fails to parse, should be SEMANTIC error
                    assert e.family == ErrorFamily.SEMANTIC

    async def test_json_array_response(self):
        """Test subprocess returns JSON array instead of dict."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps([{"item": 1}, {"item": 2}])
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            with patch("osiris.mcp.cli_bridge.ensure_base_path"):
                result = await run_cli_json(["mcp", "test"])

        # Should wrap array in dict with metadata
        assert isinstance(result, dict)
        assert "data" in result
        assert "_meta" in result
        assert isinstance(result["data"], list)

    async def test_json_null_response(self):
        """Test subprocess returns JSON null."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "null"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            with patch("osiris.mcp.cli_bridge.ensure_base_path"):
                result = await run_cli_json(["mcp", "test"])

        # Should wrap null in dict with metadata
        assert isinstance(result, dict)
        assert "data" in result
        assert result["data"] is None

    async def test_malformed_response_includes_helpful_error(self):
        """Test malformed responses produce helpful error messages."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Not JSON at all!"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            with patch("osiris.mcp.cli_bridge.ensure_base_path"):
                with pytest.raises(OsirisError) as exc_info:
                    await run_cli_json(["mcp", "connections", "list"])

        error = exc_info.value
        assert error.path == ["cli_bridge", "json_parse"]
        assert error.suggest is not None
        assert "--json" in error.suggest

    async def test_very_large_json_response(self):
        """Test subprocess returns very large JSON response."""
        # Generate 10MB JSON response
        large_data = {"data": [{"key": "value" * 1000} for _ in range(1000)]}
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(large_data)
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            with patch("osiris.mcp.cli_bridge.ensure_base_path"):
                result = await run_cli_json(["mcp", "test"])

        # Should handle large responses gracefully
        assert isinstance(result, dict)
        assert "_meta" in result
        # Check bytes_out metric reflects large size
        assert result["_meta"]["bytes_out"] > 1_000_000


@pytest.mark.asyncio
class TestNetworkSubprocessFailures:
    """Test network and subprocess-level failures."""

    async def test_file_not_found_osiris_py(self):
        """Test FileNotFoundError when osiris.py doesn't exist."""
        with patch("subprocess.run", side_effect=FileNotFoundError("osiris.py not found")):
            with patch("osiris.mcp.cli_bridge.ensure_base_path"):
                with pytest.raises(OsirisError) as exc_info:
                    await run_cli_json(["mcp", "connections", "list"])

        assert exc_info.value.family == ErrorFamily.SEMANTIC
        assert "not found" in str(exc_info.value).lower()
        assert exc_info.value.path == ["cli_bridge", "command_not_found"]

    async def test_permission_denied_execution(self):
        """Test PermissionError when subprocess can't execute."""
        with patch("subprocess.run", side_effect=PermissionError("Permission denied: osiris.py")):
            with patch("osiris.mcp.cli_bridge.ensure_base_path"):
                with pytest.raises(OsirisError) as exc_info:
                    await run_cli_json(["mcp", "connections", "list"])

        assert exc_info.value.family == ErrorFamily.SEMANTIC
        assert exc_info.value.path == ["cli_bridge", "unexpected"]

    async def test_os_error_subprocess(self):
        """Test OSError during subprocess execution."""
        with patch("subprocess.run", side_effect=OSError("OS error: resource exhausted")):
            with patch("osiris.mcp.cli_bridge.ensure_base_path"):
                with pytest.raises(OsirisError) as exc_info:
                    await run_cli_json(["mcp", "connections", "list"])

        assert exc_info.value.family == ErrorFamily.SEMANTIC

    async def test_keyboard_interrupt(self):
        """Test KeyboardInterrupt during subprocess execution."""
        # Note: KeyboardInterrupt is a BaseException, not Exception
        # The cli_bridge will not catch it (intentionally), so it propagates
        # We test that it's NOT wrapped in OsirisError (system-level interrupt)
        with patch("subprocess.run", side_effect=KeyboardInterrupt()):
            with patch("osiris.mcp.cli_bridge.ensure_base_path"):
                # KeyboardInterrupt should propagate, not be wrapped
                with pytest.raises(KeyboardInterrupt):
                    await run_cli_json(["mcp", "connections", "list"])

    async def test_memory_error(self):
        """Test MemoryError during subprocess execution."""
        with patch("subprocess.run", side_effect=MemoryError("Out of memory")):
            with patch("osiris.mcp.cli_bridge.ensure_base_path"):
                with pytest.raises(OsirisError) as exc_info:
                    await run_cli_json(["mcp", "connections", "list"])

        assert exc_info.value.family == ErrorFamily.SEMANTIC

    async def test_unexpected_exception(self):
        """Test unexpected exceptions are handled gracefully."""
        with patch("subprocess.run", side_effect=RuntimeError("Completely unexpected error")):
            with patch("osiris.mcp.cli_bridge.ensure_base_path"):
                with pytest.raises(OsirisError) as exc_info:
                    await run_cli_json(["mcp", "connections", "list"])

        assert exc_info.value.family == ErrorFamily.SEMANTIC
        assert exc_info.value.path == ["cli_bridge", "unexpected"]


class TestErrorResponseFormat:
    """Test error response format compliance with MCP protocol."""

    def test_error_to_dict_includes_all_fields(self):
        """Test OsirisError.to_dict() includes all required fields."""
        error = SchemaError("missing required field: name", path=["pipeline", "name"], suggest="Add name field")
        error_dict = error.to_dict()

        assert "code" in error_dict
        assert "message" in error_dict
        assert "path" in error_dict
        assert "suggest" in error_dict
        assert isinstance(error_dict["path"], list)

    def test_error_without_suggest(self):
        """Test error without suggestion is valid."""
        error = SchemaError("missing required field: name", path=["pipeline", "name"])
        error_dict = error.to_dict()

        assert "code" in error_dict
        assert "message" in error_dict
        assert "path" in error_dict
        # suggest is optional
        if "suggest" in error_dict:
            assert error_dict["suggest"] is None

    def test_error_code_format(self):
        """Test error code follows FAMILY/CODE format."""
        error = SchemaError("missing required field: name")
        code = error.to_dict()["code"]

        assert "/" in code
        family, specific_code = code.split("/", 1)
        assert family in ["SCHEMA", "SEMANTIC", "DISCOVERY", "LINT", "POLICY"]
        assert len(specific_code) > 0

    def test_error_path_normalization(self):
        """Test error path is always a list."""
        # Single string path
        error1 = SchemaError("error", path="field")
        assert isinstance(error1.path, list)
        assert error1.path == ["field"]

        # List path
        error2 = SchemaError("error", path=["parent", "child"])
        assert isinstance(error2.path, list)
        assert error2.path == ["parent", "child"]

        # None path
        error3 = SchemaError("error")
        assert isinstance(error3.path, list)
        assert error3.path == []

    def test_all_error_families_valid(self):
        """Test all ErrorFamily enum values are valid."""
        families = [
            ErrorFamily.SCHEMA,
            ErrorFamily.SEMANTIC,
            ErrorFamily.DISCOVERY,
            ErrorFamily.LINT,
            ErrorFamily.POLICY,
        ]

        for family in families:
            error = OsirisError(family=family, message="test error")
            assert error.family == family
            assert error.to_dict()["code"].startswith(family.value)
