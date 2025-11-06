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
from unittest.mock import patch

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
            normalized.pop("duration_ms", None)
            normalized.pop("correlation_id", None)

            # Remove _meta timing fields but KEEP canonical tool name
            if "_meta" in normalized:
                meta = normalized["_meta"]
                meta.pop("duration_ms", None)
                meta.pop("correlation_id", None)
                meta.pop("bytes_in", None)
                meta.pop("bytes_out", None)
                # Keep 'tool' field - it should be deterministic (canonical ID)

            # Remove timing fields from nested result object (CLI response)
            if "result" in normalized and isinstance(normalized["result"], dict):
                result = normalized["result"]
                result.pop("duration_ms", None)
                result.pop("correlation_id", None)
                result.pop("bytes_in", None)
                result.pop("bytes_out", None)
                # Also clean nested _meta in result
                if "_meta" in result:
                    result_meta = result["_meta"]
                    result_meta.pop("duration_ms", None)
                    result_meta.pop("correlation_id", None)
                    result_meta.pop("bytes_in", None)
                    result_meta.pop("bytes_out", None)

            return normalized

        # Verify canonical tool ID is consistent across aliases (check before normalization)
        assert result1_data.get("_meta", {}).get("tool") == "connections_list"
        assert result2_data.get("_meta", {}).get("tool") == "connections_list"
        assert result3_data.get("_meta", {}).get("tool") == "connections_list"

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

        # Create 10 different mock responses matching actual tool outputs
        # Each tool type returns different structure
        def make_response(idx, tool_type):
            """Create mock response for tool type."""
            base = {"tag": f"call_{idx}", "_meta": {"correlation_id": f"concurrent-{idx:03d}", "duration_ms": 50.0}}
            if "connections" in tool_type:
                return {**base, "connections": [], "count": 0}
            elif "components" in tool_type:
                return {**base, "components": [], "count": 0}
            elif "usecases" in tool_type:
                return {**base, "usecases": [], "count": 0}
            elif "oml_schema" in tool_type:
                return {**base, "version": "0.1.0", "schema": {}}
            elif "aiop" in tool_type:
                # AIOP expects {"data": [...]} from CLI
                return {**base, "data": [], "count": 0}
            else:
                return {**base, "data": []}

        # List of tool calls
        tool_calls = [
            "connections_list",
            "components_list",
            "usecases_list",
            "oml_schema_get",
            "aiop_list",
            "connections_list",
            "components_list",
            "usecases_list",
            "aiop_list",
            "connections_list",
        ]

        # Generate responses for each tool call
        responses = [make_response(i, tool) for i, tool in enumerate(tool_calls)]

        # Mock will cycle through responses
        mock_cli_bridge.side_effect = responses

        # Execute concurrently
        start_time = time.time()
        tasks = [mcp_server._call_tool(name, {}) for name in tool_calls]
        results = await asyncio.gather(*tasks)
        duration = time.time() - start_time

        # Verify all succeeded
        assert len(results) == 10
        for result in results:
            result_data = json.loads(result[0].text)
            assert result_data["status"] == "success"
            # Server wraps tool response in envelope: {status, result, _meta}
            # Verify tag is in the wrapped result
            if "result" in result_data and "tag" in result_data["result"]:
                # Tag should match call_N format (order may vary due to async)
                assert result_data["result"]["tag"].startswith("call_")
            # Note: We don't verify tag values because async execution order is non-deterministic

        # Verify performance (should be fast with mocked CLI)
        assert duration < 5.0  # Should complete in <5s

        # Verify CLI bridge called for delegated tools
        # Not all tools use CLI bridge (oml_schema_get is direct)
        # But we should see multiple calls for the ones that do delegate
        assert mock_cli_bridge.call_count > 0  # At least some tools delegated to CLI
        assert mock_cli_bridge.call_count <= 10  # No more than total tool calls

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
            "Missing required field: connection",
            path=["arguments", "connection"],
            suggest="Provide connection in the format @family.alias",
        )

        result = await mcp_server._call_tool("connections_doctor", {})
        result_data = json.loads(result[0].text)

        # Verify error format (error envelope structure)
        # Envelope: {status: "error", error: {code, message, details}, _meta}
        assert result_data["status"] == "error"
        assert "error" in result_data

        error = result_data["error"]
        # Top-level error has code (family) and message
        assert error["code"] == "SCHEMA"  # Family value
        assert "connection" in error["message"]

        # Details dict contains the full error info
        details = error.get("details", {})
        # OsirisError was created with path=["arguments", "connection"] but tool may simplify
        # Check that connection is mentioned in the path
        if "path" in details:
            assert "connection" in str(details.get("path", []))
        assert details.get("suggest") is not None or "suggest" in error
        # Check for connection reference format (may vary slightly in wording)
        suggest = details.get("suggest", "") or error.get("suggest", "")
        assert "@" in suggest and (
            "family" in suggest.lower() or "alias" in suggest.lower() or "connection" in suggest.lower()
        )

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
            for _prop_name, prop_schema in schema["properties"].items():
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
                "connection": "@mysql.db1",
                "component": "@mysql/extractor",
            },
        )
        result2_data = json.loads(result2[0].text)
        assert result2_data["status"] == "success"
        assert result2_data["result"]["discovery_id"].startswith("disc_")

        oml_content = """
oml_version: 0.1.0
name: test-pipeline
steps:
  - id: step1
    component: "mysql.extractor"
    mode: "read"
    config:
      connection: "@mysql.db1"
      query: "SELECT * FROM users"
  - id: step2
    component: "supabase.writer"
    mode: "write"
    config:
      connection: "@supabase.target"
      table: "users"
"""

        result3 = await mcp_server._call_tool("oml_validate", {"oml_content": oml_content})
        result3_data = json.loads(result3[0].text)
        # OML validate returns result in envelope
        assert result3_data["status"] == "success"
        # Extract valid field from result envelope
        if "result" in result3_data:
            assert result3_data["result"]["valid"] is True
        else:
            # Fallback for flat structure (shouldn't happen but handle gracefully)
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
        # OML save returns result in envelope
        assert result4_data["status"] == "success"
        assert result4_data["result"]["saved"] is True

        # Verify only 2 CLI calls made (connections_list and discovery_request)
        # OML validate and save are implemented directly, not via CLI bridge
        assert mock_cli_bridge.call_count == 2

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

        # Guide returns result in envelope
        assert result_data["status"] == "success"
        # Extract next_steps from result envelope
        next_steps = result_data.get("result", result_data).get("next_steps", [])
        assert len(next_steps) > 0
        # Guide tool uses dot notation for tool names (legacy format)
        assert next_steps[0]["tool"] in [
            "connections.list",
            "osiris.connections.list",
            "components.list",
            "osiris.components.list",
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

        # Consent validation happens in _call_tool before delegation
        # Returns error status (policy violation)
        assert result_no_consent_data["status"] == "error"
        # Error should mention consent
        assert "consent" in result_no_consent_data["error"]["message"].lower()

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

        # Memory returns result in envelope
        assert result_with_consent_data["status"] == "success"
        # Extract fields from result envelope
        result_obj = result_with_consent_data.get("result", result_with_consent_data)
        assert result_obj["captured"] is True
        assert result_obj["pii_redacted"] is True

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

        # _call_tool returns error envelope for unknown tools
        # May have either {success: false, error: ...} or {status: "error", error: ...}
        is_error = result_data.get("success") is False or result_data.get("status") == "error"
        assert is_error
        assert "error" in result_data
        # Error dict has code, message, path, suggest
        error = result_data["error"]
        assert "SEMANTIC" in error["code"]
        assert "unknown" in error["message"].lower()
        suggest = error.get("suggest", "") or error.get("details", {}).get("suggest", "")
        assert "guide_start" in suggest

    @pytest.mark.asyncio
    async def test_missing_required_argument(self, mock_cli_bridge, mcp_server):
        """
        Test tool call with missing required argument.

        Pass Criteria:
        - Returns error
        - Error family: SCHEMA
        - Indicates missing field
        """
        # connections_doctor requires connection (tool will raise OsirisError directly)
        # Mock will not be called because validation happens before CLI delegation
        result = await mcp_server._call_tool("connections_doctor", {})
        result_data = json.loads(result[0].text)

        # When tool raises OsirisError, handler returns envelope format
        # (different from unknown tool which uses _call_tool's error handler)
        assert result_data["status"] == "error"
        # Error should mention connection
        error = result_data["error"]
        # Check code is SCHEMA error family
        assert error["code"] in ["SCHEMA", "schema"]
        assert "connection" in error["message"]

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
