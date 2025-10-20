"""
Tests for MCP tool response metrics (Phase 2.1).

Verifies that all tool responses include:
- correlation_id: Unique identifier for request tracing
- duration_ms: Time taken to process the request
- bytes_in: Size of the request parameters
- bytes_out: Size of the response payload
"""

import pytest


class TestMetricsFields:
    """Test that all tools return required metrics fields."""

    @pytest.mark.asyncio
    async def test_connections_list_metrics(self, mock_connections_tools):
        """Test connections.list returns metrics fields."""
        result = await mock_connections_tools.list({})

        # Verify required metrics fields
        assert "correlation_id" in result["_meta"], "Missing correlation_id"
        assert "duration_ms" in result["_meta"], "Missing duration_ms"
        assert "bytes_in" in result["_meta"], "Missing bytes_in"
        assert "bytes_out" in result["_meta"], "Missing bytes_out"

        # Verify field types
        assert isinstance(result["_meta"]["correlation_id"], str)
        assert isinstance(result["_meta"]["duration_ms"], int)
        assert isinstance(result["_meta"]["bytes_in"], int)
        assert isinstance(result["_meta"]["bytes_out"], int)

        # Verify non-negative values
        assert result["_meta"]["duration_ms"] >= 0
        assert result["_meta"]["bytes_in"] >= 0
        assert result["_meta"]["bytes_out"] >= 0

    @pytest.mark.asyncio
    async def test_connections_doctor_metrics(self, mock_connections_tools):
        """Test connections.doctor returns metrics fields."""
        result = await mock_connections_tools.doctor({"connection_id": "@mysql.default"})

        assert "correlation_id" in result["_meta"]
        assert "duration_ms" in result["_meta"]
        assert "bytes_in" in result["_meta"]
        assert "bytes_out" in result["_meta"]

    @pytest.mark.asyncio
    async def test_components_list_metrics(self, mock_components_tools):
        """Test components.list returns metrics fields."""
        result = await mock_components_tools.list({})

        assert "correlation_id" in result["_meta"]
        assert "duration_ms" in result["_meta"]
        assert "bytes_in" in result["_meta"]
        assert "bytes_out" in result["_meta"]

    @pytest.mark.asyncio
    async def test_discovery_request_metrics(self, mock_discovery_tools):
        """Test discovery.request returns metrics fields."""
        result = await mock_discovery_tools.request(
            {"connection_id": "@mysql.default", "component_id": "mysql.extractor", "samples": 5}
        )

        assert "correlation_id" in result["_meta"]
        assert "duration_ms" in result["_meta"]
        assert "bytes_in" in result["_meta"]
        assert "bytes_out" in result["_meta"]

    @pytest.mark.asyncio
    async def test_usecases_list_metrics(self, mock_usecases_tools):
        """Test usecases.list returns metrics fields."""
        result = await mock_usecases_tools.list({})

        assert "correlation_id" in result["_meta"]
        assert "duration_ms" in result["_meta"]
        assert "bytes_in" in result["_meta"]
        assert "bytes_out" in result["_meta"]

    @pytest.mark.asyncio
    async def test_oml_schema_get_metrics(self, mock_oml_tools):
        """Test oml.schema_get returns metrics fields."""
        result = await mock_oml_tools.schema_get({})

        assert "correlation_id" in result["_meta"]
        assert "duration_ms" in result["_meta"]
        assert "bytes_in" in result["_meta"]
        assert "bytes_out" in result["_meta"]

    @pytest.mark.asyncio
    async def test_oml_validate_metrics(self, mock_oml_tools):
        """Test oml.validate returns metrics fields."""
        result = await mock_oml_tools.validate(
            {"oml_content": "version: 0.1.0\nname: test\nsteps: []", "strict": True}
        )

        assert "correlation_id" in result["_meta"]
        assert "duration_ms" in result["_meta"]
        assert "bytes_in" in result["_meta"]
        assert "bytes_out" in result["_meta"]

    @pytest.mark.asyncio
    async def test_oml_save_metrics(self, mock_oml_tools):
        """Test oml.save returns metrics fields."""
        result = await mock_oml_tools.save(
            {"oml_content": "version: 0.1.0\nname: test\nsteps: []", "session_id": "test_session"}
        )

        assert "correlation_id" in result["_meta"]
        assert "duration_ms" in result["_meta"]
        assert "bytes_in" in result["_meta"]
        assert "bytes_out" in result["_meta"]

    @pytest.mark.asyncio
    async def test_guide_start_metrics(self, mock_guide_tools):
        """Test guide.start returns metrics fields."""
        result = await mock_guide_tools.start({"intent": "test intent"})

        assert "correlation_id" in result["_meta"]
        assert "duration_ms" in result["_meta"]
        assert "bytes_in" in result["_meta"]
        assert "bytes_out" in result["_meta"]

    @pytest.mark.asyncio
    async def test_memory_capture_metrics(self, mock_memory_tools):
        """Test memory.capture returns metrics fields."""
        result = await mock_memory_tools.capture({"consent": True, "session_id": "test_session", "intent": "test"})

        assert "correlation_id" in result["_meta"]
        assert "duration_ms" in result["_meta"]
        assert "bytes_in" in result["_meta"]
        assert "bytes_out" in result["_meta"]


class TestCorrelationIdFormat:
    """Test correlation ID format and uniqueness."""

    @pytest.mark.asyncio
    async def test_correlation_id_format(self, mock_connections_tools):
        """Test correlation_id follows expected format."""
        result = await mock_connections_tools.list({})

        correlation_id = result["_meta"]["correlation_id"]
        # Format: mcp_<session>_<counter>
        assert correlation_id.startswith("mcp_")
        parts = correlation_id.split("_")
        assert len(parts) >= 3, "correlation_id should have at least 3 parts"

    @pytest.mark.asyncio
    async def test_correlation_id_uniqueness(self, mock_connections_tools):
        """Test correlation_ids are unique across calls."""
        result1 = await mock_connections_tools.list({})
        result2 = await mock_connections_tools.list({})

        # Should have different correlation IDs
        assert result1["_meta"]["correlation_id"] != result2["_meta"]["correlation_id"]


class TestMetricsAccuracy:
    """Test metrics accuracy and reasonableness."""

    @pytest.mark.asyncio
    async def test_duration_reasonableness(self, mock_connections_tools):
        """Test duration_ms is reasonable (< 10 seconds for unit tests)."""
        result = await mock_connections_tools.list({})

        # Should complete in < 10 seconds for mocked operations
        assert result["_meta"]["duration_ms"] < 10000, "Duration should be less than 10 seconds"

    @pytest.mark.asyncio
    async def test_bytes_in_calculation(self, mock_connections_tools):
        """Test bytes_in reflects input size."""
        # Empty args
        result1 = await mock_connections_tools.list({})

        # Args with data
        result2 = await mock_connections_tools.doctor({"connection_id": "@mysql.default"})

        # Result2 should have more bytes_in since it has arguments
        assert result2["_meta"]["bytes_in"] > result1["_meta"]["bytes_in"]

    @pytest.mark.asyncio
    async def test_bytes_out_non_zero(self, mock_connections_tools):
        """Test bytes_out is non-zero for successful responses."""
        result = await mock_connections_tools.list({})

        # Response should have content
        assert result["_meta"]["bytes_out"] > 0, "bytes_out should be greater than 0 for non-empty response"


class TestErrorResponseMetrics:
    """Test that error responses also include metrics."""

    @pytest.mark.asyncio
    async def test_guide_start_error_has_metrics(self, mock_guide_tools):
        """Test guide.start error response includes metrics."""
        # Call without intent triggers error structure
        result = await mock_guide_tools.start({})

        # Should have error but still have metrics
        assert "error" in result
        assert "correlation_id" in result["_meta"]
        assert "duration_ms" in result["_meta"]
        assert "bytes_in" in result["_meta"]
        assert "bytes_out" in result["_meta"]

    @pytest.mark.asyncio
    async def test_memory_capture_no_consent_has_metrics(self, mock_memory_tools):
        """Test memory.capture without consent includes metrics."""
        result = await mock_memory_tools.capture({"consent": False, "session_id": "test", "intent": "test"})

        # Should have error but still have metrics
        assert "error" in result
        assert "correlation_id" in result["_meta"]
        assert "duration_ms" in result["_meta"]
        assert "bytes_in" in result["_meta"]
        assert "bytes_out" in result["_meta"]


# Fixtures


@pytest.fixture
def mock_audit_logger():
    """Mock audit logger for testing."""

    class MockAuditLogger:
        def __init__(self):
            self.counter = 0

        def make_correlation_id(self):
            self.counter += 1
            return f"mcp_test_session_{self.counter}"

    return MockAuditLogger()


@pytest.fixture
def mock_connections_tools(mock_audit_logger, monkeypatch):
    """Mock connections tools with audit logger."""
    from osiris.mcp.tools.connections import ConnectionsTools

    # Mock CLI calls at the cli_bridge level
    async def mock_run_cli_json(args):
        if "list" in args:
            return {"connections": [], "count": 0, "status": "success"}
        elif "doctor" in args:
            return {"connection_id": "@mysql.default", "status": "ok", "message": "Connection OK"}
        return {}

    from osiris.mcp import cli_bridge

    monkeypatch.setattr(cli_bridge, "run_cli_json", mock_run_cli_json)

    tools = ConnectionsTools(audit_logger=mock_audit_logger)

    return tools


@pytest.fixture
def mock_components_tools(mock_audit_logger):
    """Mock components tools with audit logger."""
    from osiris.mcp.tools.components import ComponentsTools

    return ComponentsTools(audit_logger=mock_audit_logger)


@pytest.fixture
def mock_discovery_tools(mock_audit_logger, monkeypatch):
    """Mock discovery tools with audit logger."""
    # Mock CLI calls at the cli_bridge level
    async def mock_run_cli_json(args):
        return {"discovery_id": "disc_test123", "cached": False, "status": "success"}

    from osiris.mcp import cli_bridge

    monkeypatch.setattr(cli_bridge, "run_cli_json", mock_run_cli_json)

    from osiris.mcp.tools.discovery import DiscoveryTools

    tools = DiscoveryTools(audit_logger=mock_audit_logger)

    return tools


@pytest.fixture
def mock_usecases_tools(mock_audit_logger):
    """Mock usecases tools with audit logger."""
    from osiris.mcp.tools.usecases import UsecasesTools

    return UsecasesTools(audit_logger=mock_audit_logger)


@pytest.fixture
def mock_oml_tools(mock_audit_logger):
    """Mock OML tools with audit logger."""
    from osiris.mcp.tools.oml import OMLTools

    return OMLTools(audit_logger=mock_audit_logger)


@pytest.fixture
def mock_guide_tools(mock_audit_logger):
    """Mock guide tools with audit logger."""
    from osiris.mcp.tools.guide import GuideTools

    return GuideTools(audit_logger=mock_audit_logger)


@pytest.fixture
def mock_memory_tools(mock_audit_logger, tmp_path, monkeypatch):
    """Mock memory tools with audit logger."""
    from osiris.mcp.tools.memory import MemoryTools

    # Mock CLI calls at the cli_bridge level
    async def mock_run_cli_json(args):
        return {"captured": True, "memory_id": "mem_test123", "status": "success"}

    from osiris.mcp import cli_bridge

    monkeypatch.setattr(cli_bridge, "run_cli_json", mock_run_cli_json)

    tools = MemoryTools(memory_dir=tmp_path / "memory", audit_logger=mock_audit_logger)

    return tools
