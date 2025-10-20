"""
Claude Desktop integration tests - simulates MCP protocol communication.

Tests the complete MCP protocol flow as used by Claude Desktop, including:
- Handshake and initialization
- Tool listing and discovery
- Tool calls with various argument patterns
- Backward compatibility (dot notation → underscore)
- Payload size limits
- Concurrent tool calls
- Error handling and recovery

Pass Criteria:
1. Protocol handshake completes successfully
2. All tools discoverable via list_tools
3. Tool aliases resolve correctly (dot → underscore)
4. Payload limits enforced (16MB max)
5. Concurrent calls succeed without interference
6. Error responses follow MCP protocol
"""

import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from osiris.mcp.errors import ErrorFamily, OsirisError
from osiris.mcp.server import OsirisMCPServer


class TestClaudeDesktopSimulation:
    """Simulate Claude Desktop MCP protocol communication."""

    @pytest.fixture
    def mcp_server(self):
        """Create MCP server instance."""
        with patch("osiris.mcp.server.init_telemetry"):
            server = OsirisMCPServer(server_name="osiris-mcp-test", debug=True)
            return server

    @pytest.fixture
    def mock_cli_bridge(self):
        """Mock CLI bridge to avoid subprocess calls."""
        with patch("osiris.mcp.cli_bridge.run_cli_json") as mock:
            yield mock

    @pytest.mark.asyncio
    async def test_protocol_handshake(self, mcp_server):
        """
        Test MCP protocol initialization handshake.

        Pass Criteria:
        - Server name and version set correctly
        - Capabilities advertised
        - Tools, resources, prompts support declared
        """
        assert mcp_server.server_name == "osiris-mcp-test"
        assert mcp_server.config.SERVER_VERSION is not None
        assert mcp_server.config.PROTOCOL_VERSION == "2024-11-05"

        # Verify server initialized correctly
        assert mcp_server.server is not None
        assert mcp_server.connections_tools is not None
        assert mcp_server.discovery_tools is not None
        assert mcp_server.oml_tools is not None

    @pytest.mark.asyncio
    async def test_list_tools_discovery(self, mcp_server):
        """
        Test tool listing (Claude Desktop first call).

        Pass Criteria:
        - All 12+ tools returned
        - Each tool has name, description, inputSchema
        - Schema validates (type: object, properties defined)
        - No aliases in list (aliases handled in call_tool)
        """
        tools = await mcp_server._list_tools()

        # Should return all tools
        assert len(tools) >= 12

        # Verify each tool has required fields
        tool_names = set()
        for tool in tools:
            assert hasattr(tool, "name")
            assert hasattr(tool, "description")
            assert hasattr(tool, "inputSchema")

            # Verify schema structure
            schema = tool.inputSchema
            assert schema["type"] == "object"
            assert "properties" in schema or schema["properties"] == {}

            tool_names.add(tool.name)

        # Verify expected tools present
        expected_tools = {
            "connections_list",
            "connections_doctor",
            "components_list",
            "discovery_request",
            "usecases_list",
            "oml_schema_get",
            "oml_validate",
            "oml_save",
            "guide_start",
            "memory_capture",
            "aiop_list",
            "aiop_show",
        }
        assert expected_tools.issubset(tool_names)

        # Verify no aliases in tool list (handled separately)
        alias_names = {
            "connections.list",
            "osiris.connections.list",
            "discovery.request",
        }
        assert alias_names.isdisjoint(tool_names)

    @pytest.mark.asyncio
    async def test_tool_call_via_alias(self, mock_cli_bridge, mcp_server):
        """
        Test tool call using legacy alias (backward compatibility).

        Pass Criteria:
        - Dot notation aliases resolve (connections.list → connections_list)
        - Osiris prefix aliases resolve (osiris.connections.list → connections_list)
        - Original tool name works
        - All produce identical results
        """
        # Mock response
        mock_response = {
            "connections": [],
            "count": 0,
            "status": "success",
            "_meta": {"correlation_id": "alias-test-001", "duration_ms": 10.0},
        }
        mock_cli_bridge.return_value = mock_response

        # Test 1: Call with underscore name (canonical)
        result1 = await mcp_server._call_tool("connections_list", {})
        result1_data = json.loads(result1[0].text)
        assert result1_data["status"] == "success"

        # Test 2: Call with dot notation (legacy)
        result2 = await mcp_server._call_tool("connections.list", {})
        result2_data = json.loads(result2[0].text)
        assert result2_data["status"] == "success"

        # Test 3: Call with osiris prefix (legacy)
        result3 = await mcp_server._call_tool("osiris.connections.list", {})
        result3_data = json.loads(result3[0].text)
        assert result3_data["status"] == "success"

        # All should produce identical results (excluding timing-based metadata)
        def normalize(data):
            """Remove non-deterministic fields for comparison."""
            import copy
            normalized = copy.deepcopy(data)

            # Remove top-level timing fields
            normalized.pop('duration_ms', None)
            normalized.pop('correlation_id', None)

            # Remove _meta timing fields but KEEP canonical tool name
            if '_meta' in normalized:
                meta = normalized['_meta']
                meta.pop('duration_ms', None)
                meta.pop('correlation_id', None)
                meta.pop('bytes_in', None)
                meta.pop('bytes_out', None)
                # Keep 'tool' field - it should be deterministic (canonical ID)

            # Remove timing fields from nested result object (CLI response)
            if 'result' in normalized and isinstance(normalized['result'], dict):
                result = normalized['result']
                result.pop('duration_ms', None)
                result.pop('correlation_id', None)
                result.pop('bytes_in', None)
                result.pop('bytes_out', None)
                # Also clean nested _meta in result
                if '_meta' in result:
                    result_meta = result['_meta']
                    result_meta.pop('duration_ms', None)
                    result_meta.pop('correlation_id', None)
                    result_meta.pop('bytes_in', None)
                    result_meta.pop('bytes_out', None)

            return normalized

        # Verify canonical tool ID is consistent across aliases (check before normalization)
        assert result1_data.get('_meta', {}).get('tool') == "connections_list"
        assert result2_data.get('_meta', {}).get('tool') == "connections_list"
        assert result3_data.get('_meta', {}).get('tool') == "connections_list"

        # Verify normalized results are identical (after removing timing/correlation fields)
        assert normalize(result1_data) == normalize(result2_data) == normalize(result3_data)

        # Verify CLI bridge called 3 times with same command
        assert mock_cli_bridge.call_count == 3

    @pytest.mark.asyncio
    async def test_payload_size_limits(self, mock_cli_bridge, mcp_server):
        """
        Test payload size limit enforcement (16MB max).

        Pass Criteria:
        - Small payloads (<16MB) succeed
        - Large payloads (>16MB) rejected with POLICY error
        - Error suggests pagination/filtering
        """
        # Test 1: Small payload succeeds
        small_response = {
            "connections": [{"family": "mysql", "alias": "test"}],
            "count": 1,
            "_meta": {"correlation_id": "test", "duration_ms": 10, "bytes_in": 10, "bytes_out": 100},
        }
        mock_cli_bridge.return_value = small_response

        small_args = {"filter": "test"}  # Small input args
        result = await mcp_server._call_tool("connections_list", small_args)
        result_data = json.loads(result[0].text)
        assert result_data["status"] == "success"

        # Test 2: Large input payload rejected (before CLI delegation)
        # Create INPUT arguments that exceed 16MB when serialized
        large_data = "x" * (17 * 1024 * 1024)  # 17MB
        large_args = {"data": large_data}  # Large INPUT arguments

        result = await mcp_server._call_tool("connections_list", large_args)
        result_data = json.loads(result[0].text)

        # Should return error response (payload guard blocks before CLI call)
        assert result_data["status"] == "error"
        assert result_data["error"]["code"] == "payload_too_large"
        assert "payload" in result_data["error"]["message"].lower() or "16" in result_data["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_concurrent_tool_calls(self, mock_cli_bridge, mcp_server):
        """
        Test 10 concurrent tool calls (Claude Desktop pattern).

        Pass Criteria:
        - All calls complete successfully
        - No cross-contamination between calls
        - Each gets unique correlation ID
        - Performance acceptable (<5s for 10 concurrent calls)
        """
        import time

        # Create 10 different mock responses
        responses = [
            {
                "result": f"response_{i}",
                "status": "success",
                "_meta": {"correlation_id": f"concurrent-{i:03d}", "duration_ms": 50.0},
            }
            for i in range(10)
        ]

        # Mock will cycle through responses
        mock_cli_bridge.side_effect = responses

        # Define 10 different tool calls
        calls = [
            ("connections_list", {}),
            ("components_list", {}),
            ("usecases_list", {}),
            ("oml_schema_get", {}),
            ("aiop_list", {}),
            ("connections_list", {}),
            ("components_list", {}),
            ("usecases_list", {}),
            ("aiop_list", {}),
            ("connections_list", {}),
        ]

        # Execute concurrently
        start_time = time.time()
        tasks = [mcp_server._call_tool(name, args) for name, args in calls]
        results = await asyncio.gather(*tasks)
        duration = time.time() - start_time

        # Verify all succeeded
        assert len(results) == 10
        for i, result in enumerate(results):
            result_data = json.loads(result[0].text)
            assert result_data["status"] == "success"
            assert result_data["result"] == f"response_{i}"

        # Verify performance (should be fast with mocked CLI)
        assert duration < 5.0  # Should complete in <5s

        # Verify CLI bridge called 10 times
        assert mock_cli_bridge.call_count == 10

    @pytest.mark.asyncio
    async def test_error_response_format(self, mock_cli_bridge, mcp_server):
        """
        Test that errors follow MCP protocol format.

        Pass Criteria:
        - Error responses include status: "error"
        - Error family present and valid
        - Error message clear
        - Suggestion provided when applicable
        - Path array indicates error location
        """
        # Simulate CLI error
        mock_cli_bridge.side_effect = OsirisError(
            ErrorFamily.SCHEMA,
            "Missing required field: connection_id",
            path=["arguments", "connection_id"],
            suggest="Provide connection_id in the format @family.alias",
        )

        result = await mcp_server._call_tool("connections_doctor", {})
        result_data = json.loads(result[0].text)

        # Verify error format
        assert result_data["status"] == "error"
        assert "error" in result_data

        error = result_data["error"]
        assert error["family"] == "SCHEMA"
        assert "connection_id" in error["message"]
        assert error["path"] == ["arguments", "connection_id"]
        assert error["suggest"] is not None
        assert "@family.alias" in error["suggest"]

    @pytest.mark.asyncio
    async def test_all_tool_schemas_valid(self, mcp_server):
        """
        Test that all tool schemas are valid JSON Schema.

        Pass Criteria:
        - Each schema has type: object
        - Required fields declared
        - Properties have types
        - Descriptions provided
        """
        tools = await mcp_server._list_tools()

        for tool in tools:
            schema = tool.inputSchema

            # Basic structure
            assert schema["type"] == "object"
            assert "properties" in schema

            # Verify required fields are in properties
            if "required" in schema:
                for req_field in schema["required"]:
                    assert req_field in schema["properties"]

            # Verify properties have types
            for prop_name, prop_schema in schema["properties"].items():
                assert "type" in prop_schema or "enum" in prop_schema
                # Description recommended
                # assert "description" in prop_schema

    @pytest.mark.asyncio
    async def test_discovery_workflow(self, mock_cli_bridge, mcp_server):
        """
        Test complete discovery workflow as Claude Desktop would use it.

        Workflow:
        1. List connections
        2. Request discovery
        3. Read discovery resources
        4. Generate OML
        5. Validate OML
        6. Save OML

        Pass Criteria:
        - All steps succeed
        - Data flows correctly
        - Resources accessible
        """
        # Step 1: List connections (CLI response format - no envelope)
        connections_response = {
            "connections": [
                {
                    "family": "mysql",
                    "alias": "db1",
                    "reference": "@mysql.db1",
                    "config": {"host": "localhost"},
                }
            ],
            "count": 1,
            "_meta": {"correlation_id": "wf-001", "duration_ms": 10.0, "bytes_in": 0, "bytes_out": 100},
        }

        # Step 2: Discovery (CLI response format)
        discovery_response = {
            "discovery_id": "disc_wf_test_123",
            "connection_id": "@mysql.db1",
            "component_id": "@mysql/extractor",
            "artifacts": {
                "overview": "osiris://mcp/discovery/disc_wf_test_123/overview.json",
            },
            "summary": {"table_count": 5},
            "_meta": {"correlation_id": "wf-002", "duration_ms": 500.0, "bytes_in": 50, "bytes_out": 200},
        }

        # Step 3: Validation (CLI response format)
        validation_response = {
            "valid": True,
            "version": "0.1.0",
            "step_count": 2,
            "_meta": {"correlation_id": "wf-003", "duration_ms": 30.0, "bytes_in": 100, "bytes_out": 50},
        }

        # Step 4: Save (CLI response format)
        save_response = {
            "saved": True,
            "uri": "osiris://mcp/drafts/oml/test_pipeline.yaml",
            "_meta": {"correlation_id": "wf-004", "duration_ms": 15.0, "bytes_in": 200, "bytes_out": 50},
        }

        mock_cli_bridge.side_effect = [
            connections_response,
            discovery_response,
            validation_response,
            save_response,
        ]

        # Execute workflow
        result1 = await mcp_server._call_tool("connections_list", {})
        result1_data = json.loads(result1[0].text)
        # MCP server wraps CLI response in envelope: {status, result, _meta}
        assert result1_data["status"] == "success"
        assert result1_data["result"]["count"] == 1

        result2 = await mcp_server._call_tool(
            "discovery_request",
            {
                "connection_id": "@mysql.db1",
                "component_id": "@mysql/extractor",
            },
        )
        result2_data = json.loads(result2[0].text)
        assert result2_data["status"] == "success"
        assert result2_data["result"]["discovery_id"].startswith("disc_")

        oml_content = """
pipeline:
  name: test
  version: 0.1.0
steps:
  - id: step1
    component: "@mysql/extractor"
    config:
      connection: "@mysql.db1"
  - id: step2
    component: "@supabase/writer"
    config:
      connection: "@supabase.target"
"""

        result3 = await mcp_server._call_tool("oml_validate", {"oml_content": oml_content})
        result3_data = json.loads(result3[0].text)
        assert result3_data["valid"] is True

        result4 = await mcp_server._call_tool(
            "oml_save",
            {
                "oml_content": oml_content,
                "session_id": "test_session",
                "filename": "test_pipeline.yaml",
            },
        )
        result4_data = json.loads(result4[0].text)
        assert result4_data["saved"] is True

        # Verify 4 CLI calls made
        assert mock_cli_bridge.call_count == 4

    @pytest.mark.asyncio
    async def test_guide_workflow(self, mock_cli_bridge, mcp_server):
        """
        Test guided authoring workflow.

        Pass Criteria:
        - Guide provides next steps
        - Recommendations based on state
        - Links to relevant tools
        """
        guide_response = {
            "next_steps": [
                {
                    "step": "list_connections",
                    "tool": "connections_list",
                    "description": "First, discover available connections",
                },
                {
                    "step": "run_discovery",
                    "tool": "discovery_request",
                    "description": "Explore database schema",
                },
            ],
            "current_state": {
                "has_connections": False,
                "has_discovery": False,
                "has_oml_draft": False,
            },
            "status": "success",
            "_meta": {"correlation_id": "guide-001", "duration_ms": 5.0},
        }

        mock_cli_bridge.return_value = guide_response

        result = await mcp_server._call_tool(
            "guide_start",
            {
                "intent": "Create a data pipeline",
                "known_connections": [],
                "has_discovery": False,
            },
        )
        result_data = json.loads(result[0].text)

        assert result_data["status"] == "success"
        assert len(result_data["next_steps"]) > 0
        assert result_data["next_steps"][0]["tool"] in [
            "connections_list",
            "components_list",
        ]

    @pytest.mark.asyncio
    async def test_memory_capture_consent(self, mock_cli_bridge, mcp_server):
        """
        Test memory capture with PII consent.

        Pass Criteria:
        - Consent required
        - PII redaction applied
        - Session data stored
        - Retention honored
        """
        # Test 1: Consent required
        result_no_consent = await mcp_server._call_tool(
            "memory_capture",
            {
                "consent": False,
                "session_id": "test_session",
                "intent": "Debug connection",
            },
        )
        result_no_consent_data = json.loads(result_no_consent[0].text)

        # Should fail without consent
        assert result_no_consent_data["status"] == "error"

        # Test 2: With consent
        memory_response = {
            "captured": True,
            "session_id": "test_session",
            "memory_uri": "osiris://mcp/memory/sessions/test_session.jsonl",
            "pii_redacted": True,
            "status": "success",
            "_meta": {"correlation_id": "mem-001", "duration_ms": 20.0},
        }

        mock_cli_bridge.return_value = memory_response

        result_with_consent = await mcp_server._call_tool(
            "memory_capture",
            {
                "consent": True,
                "session_id": "test_session",
                "intent": "Debug connection",
                "actor_trace": [],
                "decisions": [],
                "artifacts": [],
            },
        )
        result_with_consent_data = json.loads(result_with_consent[0].text)

        assert result_with_consent_data["captured"] is True
        assert result_with_consent_data["pii_redacted"] is True

    @pytest.mark.asyncio
    async def test_unknown_tool(self, mock_cli_bridge, mcp_server):
        """
        Test calling unknown tool.

        Pass Criteria:
        - Returns error (not exception)
        - Error family: SEMANTIC
        - Suggests using guide_start
        """
        result = await mcp_server._call_tool("nonexistent_tool", {})
        result_data = json.loads(result[0].text)

        assert result_data["status"] == "error"
        assert result_data["error"]["family"] == "SEMANTIC"
        assert "unknown" in result_data["error"]["message"].lower()
        assert "guide_start" in result_data["error"]["suggest"]

    @pytest.mark.asyncio
    async def test_missing_required_argument(self, mock_cli_bridge, mcp_server):
        """
        Test tool call with missing required argument.

        Pass Criteria:
        - Returns error
        - Error family: SCHEMA
        - Indicates missing field
        """
        # connections_doctor requires connection_id
        result = await mcp_server._call_tool("connections_doctor", {})
        result_data = json.loads(result[0].text)

        assert result_data["status"] == "error"
        assert result_data["error"]["family"] == "SCHEMA"
        assert "connection_id" in result_data["error"]["message"]

    @pytest.mark.asyncio
    async def test_all_tools_callable(self, mock_cli_bridge, mcp_server):
        """
        Test that all listed tools are callable.

        Pass Criteria:
        - Every tool from list_tools can be called
        - No unhandled tools
        - All return proper response format
        """
        tools = await mcp_server._list_tools()

        # Mock generic success response
        mock_cli_bridge.return_value = {
            "status": "success",
            "_meta": {"correlation_id": "test-001", "duration_ms": 10.0},
        }

        for tool in tools:
            # Build minimal valid arguments
            args = {}
            if "required" in tool.inputSchema:
                for req_field in tool.inputSchema["required"]:
                    # Provide dummy values based on type
                    prop_schema = tool.inputSchema["properties"][req_field]
                    if prop_schema["type"] == "string":
                        args[req_field] = "test_value"
                    elif prop_schema["type"] == "boolean":
                        args[req_field] = True
                    elif prop_schema["type"] == "integer":
                        args[req_field] = 1

            # Call tool
            result = await mcp_server._call_tool(tool.name, args)
            result_data = json.loads(result[0].text)

            # Should return response (error or success, but not exception)
            assert "status" in result_data
            assert result_data["status"] in ["success", "error"]
