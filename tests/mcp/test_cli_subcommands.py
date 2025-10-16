"""
Test MCP CLI subcommands.

Tests all CLI subcommands that serve as delegation targets for MCP tools.
Verifies JSON output schemas, argument parsing, and error handling.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock

from osiris.cli.discovery_cmd import discovery_run
from osiris.cli.guide_cmd import guide_start
from osiris.cli.memory_cmd import memory_capture
from osiris.cli.usecases_cmd import list_usecases


class TestDiscoveryCommand:
    """Test discovery CLI subcommand."""

    def test_discovery_run_argument_parsing(self):
        """Test discovery command correctly parses @family.alias format."""
        # This is tested more thoroughly via integration tests
        # Here we just verify that correct parsing happens
        with patch('osiris.cli.discovery_cmd.SessionContext'):
            with patch('osiris.cli.discovery_cmd.resolve_connection') as mock_resolve:
                mock_resolve.return_value = {'host': 'localhost'}

                with patch('osiris.cli.discovery_cmd.get_registry') as mock_registry:
                    mock_registry.return_value.get_component.return_value = None

                    # Call discovery - it will fail at component check but that's OK
                    discovery_run(connection_id="@mysql.test", json_output=True)

                    # Verify resolve_connection was called with parsed family/alias
                    mock_resolve.assert_called_once_with('mysql', 'test')

    @patch('osiris.cli.discovery_cmd.SessionContext')
    def test_discovery_run_invalid_format(self, mock_session):
        """Test discovery with invalid connection ID format."""
        exit_code = discovery_run(
            connection_id="invalid-no-at",
            json_output=True
        )

        # Just verify the exit code - the function returns early
        assert exit_code == 2

    @patch('osiris.cli.discovery_cmd.SessionContext')
    def test_discovery_run_missing_dot(self, mock_session):
        """Test discovery with missing dot separator."""
        exit_code = discovery_run(
            connection_id="@mysqlinvalid",
            json_output=True
        )

        # Verify the exit code
        assert exit_code == 2

    @patch('osiris.cli.discovery_cmd.resolve_connection')
    @patch('osiris.cli.discovery_cmd.SessionContext')
    def test_discovery_run_connection_not_found(self, mock_session, mock_resolve):
        """Test discovery with non-existent connection."""
        mock_resolve.side_effect = ValueError("Connection alias 'notfound' not found")

        exit_code = discovery_run(
            connection_id="@mysql.notfound",
            json_output=True
        )

        # Verify error exit code
        assert exit_code == 1

    @patch('osiris.cli.discovery_cmd.resolve_connection')
    @patch('osiris.cli.discovery_cmd.get_registry')
    @patch('osiris.cli.discovery_cmd.SessionContext')
    def test_discovery_run_component_not_found(
        self, mock_session, mock_registry, mock_resolve
    ):
        """Test discovery when component doesn't exist."""
        mock_resolve.return_value = {'host': 'localhost'}
        mock_registry.return_value.get_component.return_value = None

        exit_code = discovery_run(
            connection_id="@mysql.test",
            json_output=True
        )

        # Verify error exit code
        assert exit_code == 1

    @patch('osiris.core.config.load_config')
    @patch('osiris.cli.discovery_cmd.SessionContext')
    def test_discovery_run_respects_filesystem_contract(self, mock_session, mock_load_config):
        """Test that discovery respects filesystem contract for logs."""
        mock_config = {
            'filesystem': {
                'base_path': '/test/path',
                'run_logs_dir': 'custom_logs'
            }
        }
        mock_load_config.return_value = mock_config

        # Mock session creation to verify logs_dir
        mock_session_instance = MagicMock()
        mock_session.return_value = mock_session_instance

        with patch('osiris.cli.discovery_cmd.resolve_connection', side_effect=ValueError("test")):
            discovery_run(connection_id="@mysql.test", json_output=True)

        # Verify SessionContext was called with correct base_logs_dir
        mock_session.assert_called_once()
        call_args = mock_session.call_args
        assert str(call_args[1]['base_logs_dir']) == '/test/path/custom_logs'


class TestGuideCommand:
    """Test guide CLI subcommand."""

    def test_guide_start_json_output(self, capsys):
        """Test guide start with JSON output."""
        exit_code = guide_start(context_file=None, json_output=True)

        assert exit_code == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        assert output["status"] == "success"
        assert output["mode"] == "guided_authoring"
        assert "suggested_steps" in output
        assert len(output["suggested_steps"]) == 5

        # Verify step structure
        first_step = output["suggested_steps"][0]
        assert "step" in first_step
        assert "action" in first_step
        assert "description" in first_step

    def test_guide_start_with_context_file(self, capsys):
        """Test guide start with context file."""
        exit_code = guide_start(context_file="/tmp/context.json", json_output=True)

        assert exit_code == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["context_file"] == "/tmp/context.json"

    def test_guide_start_human_output(self, capsys):
        """Test guide start with human-friendly output."""
        exit_code = guide_start(json_output=False)

        assert exit_code == 0

        captured = capsys.readouterr()
        assert "Osiris Guided OML Authoring" in captured.out
        assert "discover_schema" in captured.out
        assert "review_components" in captured.out


class TestMemoryCommand:
    """Test memory CLI subcommand."""

    def test_memory_capture_missing_consent(self, capsys):
        """Test memory capture without consent flag."""
        exit_code = memory_capture(
            session_id="test123",
            consent=False,
            json_output=True
        )

        assert exit_code == 1

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["status"] == "error"
        assert "consent" in output["error"].lower()

    def test_memory_capture_missing_session_id(self, capsys):
        """Test memory capture without session ID."""
        exit_code = memory_capture(
            session_id=None,
            consent=True,
            json_output=True
        )

        assert exit_code == 2

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["status"] == "error"
        assert "session id required" in output["error"].lower()

    def test_memory_capture_success(self, capsys):
        """Test successful memory capture."""
        exit_code = memory_capture(
            session_id="test_session_123",
            consent=True,
            json_output=True
        )

        assert exit_code == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["status"] == "success"
        assert output["session_id"] == "test_session_123"
        assert output["consent_provided"] is True
        assert output["memory_captured"] is True

    def test_memory_capture_human_output(self, capsys):
        """Test memory capture with human-friendly output."""
        exit_code = memory_capture(
            session_id="test123",
            consent=True,
            json_output=False
        )

        assert exit_code == 0

        captured = capsys.readouterr()
        assert "Memory captured" in captured.out
        assert "test123" in captured.out


class TestUsecasesCommand:
    """Test usecases CLI subcommand."""

    def test_usecases_list_all(self, capsys):
        """Test listing all use cases."""
        exit_code = list_usecases(category=None, json_output=True)

        assert exit_code == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        assert output["status"] == "success"
        assert output["count"] == 4
        assert len(output["usecases"]) == 4
        assert output["category_filter"] is None

        # Verify use case structure
        first_usecase = output["usecases"][0]
        assert "name" in first_usecase
        assert "category" in first_usecase
        assert "description" in first_usecase
        assert "components" in first_usecase

    def test_usecases_list_by_category(self, capsys):
        """Test listing use cases filtered by category."""
        exit_code = list_usecases(category="etl", json_output=True)

        assert exit_code == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        assert output["status"] == "success"
        assert output["category_filter"] == "etl"
        assert output["count"] == 2  # Should have 2 ETL use cases

        # Verify all returned use cases are ETL category
        for usecase in output["usecases"]:
            assert usecase["category"] == "etl"

    def test_usecases_list_empty_category(self, capsys):
        """Test listing with non-existent category."""
        exit_code = list_usecases(category="nonexistent", json_output=True)

        assert exit_code == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        assert output["status"] == "success"
        assert output["count"] == 0
        assert len(output["usecases"]) == 0

    def test_usecases_list_human_output(self, capsys):
        """Test use cases with human-friendly output."""
        exit_code = list_usecases(json_output=False)

        assert exit_code == 0

        captured = capsys.readouterr()
        assert "OML Use Case Templates" in captured.out
        assert "mysql_to_supabase_etl" in captured.out
        assert "Found 4 use case template(s)" in captured.out


class TestJSONSchemaCompliance:
    """Test that all CLI commands produce valid, stable JSON schemas."""

    def test_discovery_json_schema_stability(self):
        """Test discovery JSON output has stable schema (via exit codes)."""
        # Test that discovery command follows predictable patterns:
        # - Invalid format returns 2
        # - Not found returns 1
        # - Success returns 0
        with patch('osiris.cli.discovery_cmd.SessionContext'):
            code = discovery_run(connection_id="invalid", json_output=True)
            assert code == 2  # Invalid format

            with patch('osiris.cli.discovery_cmd.resolve_connection', side_effect=ValueError("test")):
                code = discovery_run(connection_id="@mysql.test", json_output=True)
                assert code == 1  # Connection not found

    def test_guide_json_schema_stability(self, capsys):
        """Test guide JSON output has stable schema."""
        guide_start(json_output=True)

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        required_fields = ["status", "mode", "suggested_steps"]
        for field in required_fields:
            assert field in output, f"Missing required field: {field}"

        # Verify steps schema
        for step in output["suggested_steps"]:
            assert "step" in step
            assert "action" in step
            assert "description" in step

    def test_memory_json_schema_stability(self, capsys):
        """Test memory JSON output has stable schema."""
        memory_capture(session_id="test", consent=True, json_output=True)

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        required_fields = ["status", "session_id", "consent_provided", "memory_captured"]
        for field in required_fields:
            assert field in output, f"Missing required field: {field}"

    def test_usecases_json_schema_stability(self, capsys):
        """Test usecases JSON output has stable schema."""
        list_usecases(json_output=True)

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        required_fields = ["status", "usecases", "count"]
        for field in required_fields:
            assert field in output, f"Missing required field: {field}"

        # Verify usecase schema
        for usecase in output["usecases"]:
            assert "name" in usecase
            assert "category" in usecase
            assert "description" in usecase
            assert "components" in usecase


class TestErrorCodes:
    """Test that CLI commands return correct exit codes."""

    def test_discovery_error_codes(self):
        """Test discovery command exit codes."""
        with patch('osiris.cli.discovery_cmd.SessionContext'):
            # Invalid format: exit code 2
            code = discovery_run(connection_id="invalid", json_output=True)
            assert code == 2

            # Connection not found: exit code 1
            with patch('osiris.cli.discovery_cmd.resolve_connection', side_effect=ValueError("not found")):
                code = discovery_run(connection_id="@mysql.test", json_output=True)
                assert code == 1

    def test_memory_error_codes(self):
        """Test memory command exit codes."""
        # Missing consent: exit code 1
        code = memory_capture(session_id="test", consent=False, json_output=True)
        assert code == 1

        # Missing session_id: exit code 2
        code = memory_capture(session_id=None, consent=True, json_output=True)
        assert code == 2

        # Success: exit code 0
        code = memory_capture(session_id="test", consent=True, json_output=True)
        assert code == 0

    def test_guide_always_succeeds(self):
        """Test guide command always returns 0 (stub implementation)."""
        code = guide_start(json_output=True)
        assert code == 0

    def test_usecases_always_succeeds(self):
        """Test usecases command always returns 0."""
        code = list_usecases(json_output=True)
        assert code == 0
