"""
Test MCP AIOP tools.
"""

from unittest.mock import patch

import pytest

from osiris.mcp.errors import OsirisError
from osiris.mcp.tools.aiop import AIOPTools


class TestAIOPTools:
    """Test aiop_list and aiop_show tools."""

    @pytest.fixture
    def aiop_tools(self):
        """Create AIOPTools instance."""
        return AIOPTools()

    @pytest.mark.asyncio
    async def test_aiop_list_all(self, aiop_tools):
        """Test listing all AIOP runs via CLI delegation."""
        # Mock CLI delegation response (CLI returns a list)
        mock_result = [
            {
                "pipeline": "orders_etl",
                "run_id": "2025-10-17T10-30-00Z_01J9Z8",
                "profile": None,
                "timestamp": "2025-10-17T10:30:00Z",
                "status": "success",
                "summary_size": 245678,
                "summary_path": "/path/to/aiop/orders_etl/abc123/2025-10-17T10-30-00Z_01J9Z8/summary.json",
            },
            {
                "pipeline": "customers_sync",
                "run_id": "2025-10-17T11-00-00Z_02K8Y7",
                "profile": "prod",
                "timestamp": "2025-10-17T11:00:00Z",
                "status": "success",
                "summary_size": 189234,
                "summary_path": "/path/to/aiop/customers_sync/def456/2025-10-17T11-00-00Z_02K8Y7/summary.json",
            },
        ]

        with patch("osiris.mcp.tools.aiop.run_cli_json", return_value=mock_result):
            result = await aiop_tools.list({})

            # Result should be wrapped in dict with runs and count
            assert isinstance(result, dict)
            assert "runs" in result
            assert "count" in result
            assert result["count"] == 2
            assert len(result["runs"]) == 2

            # Check first run
            first_run = result["runs"][0]
            assert first_run["pipeline"] == "orders_etl"
            assert first_run["run_id"] == "2025-10-17T10-30-00Z_01J9Z8"
            assert first_run["status"] == "success"

            # Check second run
            second_run = result["runs"][1]
            assert second_run["pipeline"] == "customers_sync"
            assert second_run["profile"] == "prod"

    @pytest.mark.asyncio
    async def test_aiop_list_filtered_by_pipeline(self, aiop_tools):
        """Test listing AIOP runs filtered by pipeline."""
        mock_result = [
            {
                "pipeline": "orders_etl",
                "run_id": "2025-10-17T10-30-00Z_01J9Z8",
                "profile": None,
                "timestamp": "2025-10-17T10:30:00Z",
                "status": "success",
                "summary_size": 245678,
                "summary_path": "/path/to/aiop/orders_etl/abc123/2025-10-17T10-30-00Z_01J9Z8/summary.json",
            }
        ]

        with patch("osiris.mcp.tools.aiop.run_cli_json", return_value=mock_result) as mock_cli:
            result = await aiop_tools.list({"pipeline": "orders_etl"})

            # Verify CLI was called with correct args
            mock_cli.assert_called_once()
            cli_args = mock_cli.call_args[0][0]
            assert "mcp" in cli_args
            assert "aiop" in cli_args
            assert "list" in cli_args
            assert "--pipeline" in cli_args
            assert "orders_etl" in cli_args

            assert result["count"] == 1
            assert len(result["runs"]) == 1
            assert result["runs"][0]["pipeline"] == "orders_etl"

    @pytest.mark.asyncio
    async def test_aiop_list_filtered_by_profile(self, aiop_tools):
        """Test listing AIOP runs filtered by profile."""
        mock_result = [
            {
                "pipeline": "customers_sync",
                "run_id": "2025-10-17T11-00-00Z_02K8Y7",
                "profile": "prod",
                "timestamp": "2025-10-17T11:00:00Z",
                "status": "success",
                "summary_size": 189234,
                "summary_path": "/path/to/aiop/customers_sync/def456/2025-10-17T11-00-00Z_02K8Y7/summary.json",
            }
        ]

        with patch("osiris.mcp.tools.aiop.run_cli_json", return_value=mock_result) as mock_cli:
            result = await aiop_tools.list({"profile": "prod"})

            # Verify CLI was called with correct args
            cli_args = mock_cli.call_args[0][0]
            assert "--profile" in cli_args
            assert "prod" in cli_args

            assert result["count"] == 1
            assert len(result["runs"]) == 1
            assert result["runs"][0]["profile"] == "prod"

    @pytest.mark.asyncio
    async def test_aiop_list_empty(self, aiop_tools):
        """Test listing AIOP runs when none exist."""
        mock_result = []

        with patch("osiris.mcp.tools.aiop.run_cli_json", return_value=mock_result):
            result = await aiop_tools.list({})

            assert isinstance(result, dict)
            assert "runs" in result
            assert "count" in result
            assert result["count"] == 0
            assert len(result["runs"]) == 0

    @pytest.mark.asyncio
    async def test_aiop_show_success(self, aiop_tools):
        """Test showing AIOP summary for a specific run."""
        mock_result = {
            "run_id": "2025-10-17T10-30-00Z_01J9Z8",
            "pipeline": "orders_etl",
            "profile": None,
            "timestamp": "2025-10-17T10:30:00Z",
            "status": "success",
            "core": {
                "run_metadata": {
                    "run_id": "2025-10-17T10-30-00Z_01J9Z8",
                    "pipeline_slug": "orders_etl",
                    "start_time": "2025-10-17T10:30:00Z",
                    "end_time": "2025-10-17T10:35:00Z",
                    "status": "success",
                },
                "evidence": {
                    "timeline": [],
                    "metrics": {},
                    "errors": [],
                    "artifacts": [],
                },
                "semantic": {"intent": "Extract and load orders", "steps_executed": 3},
                "narrative": "Successfully processed 1000 orders.",
            },
            "summary_path": "/path/to/summary.json",
        }

        with patch("osiris.mcp.tools.aiop.run_cli_json", return_value=mock_result) as mock_cli:
            result = await aiop_tools.show({"run_id": "2025-10-17T10-30-00Z_01J9Z8"})

            # Verify CLI was called with correct args
            cli_args = mock_cli.call_args[0][0]
            assert "mcp" in cli_args
            assert "aiop" in cli_args
            assert "show" in cli_args
            assert "--run" in cli_args
            assert "2025-10-17T10-30-00Z_01J9Z8" in cli_args

            # Check result structure
            assert result["run_id"] == "2025-10-17T10-30-00Z_01J9Z8"
            assert result["pipeline"] == "orders_etl"
            assert result["status"] == "success"
            assert "core" in result
            assert "run_metadata" in result["core"]
            assert "evidence" in result["core"]
            assert "semantic" in result["core"]
            assert "narrative" in result["core"]

    @pytest.mark.asyncio
    async def test_aiop_show_missing_run_id(self, aiop_tools):
        """Test showing AIOP summary without run_id raises error."""
        with pytest.raises(OsirisError) as exc_info:
            await aiop_tools.show({})

        assert "run_id is required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_aiop_show_nonexistent_run(self, aiop_tools):
        """Test showing AIOP summary for nonexistent run."""
        # CLI will raise an error which should be caught and re-raised
        with patch("osiris.mcp.tools.aiop.run_cli_json", side_effect=Exception("Run not found")):
            with pytest.raises(OsirisError) as exc_info:
                await aiop_tools.show({"run_id": "nonexistent_run_id"})

            assert "Failed to show AIOP run" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_aiop_list_with_metrics(self, aiop_tools):
        """Test that aiop_list includes metrics in response."""
        mock_result = [
            {
                "pipeline": "orders_etl",
                "run_id": "2025-10-17T10-30-00Z_01J9Z8",
                "profile": None,
                "timestamp": "2025-10-17T10:30:00Z",
                "status": "success",
                "summary_size": 245678,
                "summary_path": "/path/to/summary.json",
            }
        ]

        # Mock audit logger to provide correlation_id
        mock_audit = type("MockAudit", (), {"make_correlation_id": lambda self: "test-corr-123"})()

        tools_with_audit = AIOPTools(audit_logger=mock_audit)

        with patch("osiris.mcp.tools.aiop.run_cli_json", return_value=mock_result):
            result = await tools_with_audit.list({})

            # Check that metrics were added at top level (not nested)
            assert "correlation_id" in result
            assert result["correlation_id"] == "test-corr-123"
            assert "duration_ms" in result
            assert "bytes_in" in result
            assert "bytes_out" in result

    @pytest.mark.asyncio
    async def test_aiop_show_with_metrics(self, aiop_tools):
        """Test that aiop_show includes metrics in response."""
        mock_result = {
            "run_id": "2025-10-17T10-30-00Z_01J9Z8",
            "pipeline": "orders_etl",
            "status": "success",
            "core": {},
        }

        # Mock audit logger
        mock_audit = type("MockAudit", (), {"make_correlation_id": lambda self: "test-corr-456"})()
        tools_with_audit = AIOPTools(audit_logger=mock_audit)

        with patch("osiris.mcp.tools.aiop.run_cli_json", return_value=mock_result):
            result = await tools_with_audit.show({"run_id": "2025-10-17T10-30-00Z_01J9Z8"})

            # Check that metrics were added at top level (not nested)
            assert "correlation_id" in result
            assert result["correlation_id"] == "test-corr-456"
            assert "duration_ms" in result
            assert "bytes_in" in result
            assert "bytes_out" in result

    @pytest.mark.asyncio
    async def test_aiop_list_cli_error(self, aiop_tools):
        """Test handling of CLI errors during list."""
        with patch("osiris.mcp.tools.aiop.run_cli_json", side_effect=Exception("AIOP index not found")):
            with pytest.raises(OsirisError) as exc_info:
                await aiop_tools.list({})

            assert "Failed to list AIOP runs" in str(exc_info.value)
