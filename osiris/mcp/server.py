"""
Osiris MCP Server implementation using the official Model Context Protocol Python SDK.

This server provides OML authoring capabilities through MCP tools and resources.
"""

import asyncio
import json
import logging
from typing import Any

from mcp import types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from osiris.mcp.audit import AuditLogger
from osiris.mcp.cache import DiscoveryCache
from osiris.mcp.config import get_config
from osiris.mcp.errors import ErrorFamily, OsirisError, OsirisErrorHandler
from osiris.mcp.payload_limits import get_limiter
from osiris.mcp.resolver import ResourceResolver
from osiris.mcp.telemetry import init_telemetry

logger = logging.getLogger(__name__)


class OsirisMCPServer:
    """
    Main MCP Server for Osiris OML authoring.

    Provides tools for:
    - Connection management
    - Discovery operations
    - OML validation and saving
    - Use case exploration
    - Guided authoring
    - Memory capture
    """

    def _register_handlers(self):
        """Register all MCP handlers."""
        # Register tool handlers
        self.server.list_tools()(self._list_tools)
        self.server.call_tool()(self._call_tool)

        # Register resource handlers
        self.server.list_resources()(self._list_resources)
        self.server.read_resource()(self._read_resource)

        # Register prompt handlers (if needed)
        self.server.list_prompts()(self._list_prompts)
        self.server.get_prompt()(self._get_prompt)

    async def _list_tools(self) -> list[types.Tool]:
        """List all available tools with their schemas."""
        tools = [
            # Connection tools
            types.Tool(
                name="connections_list",
                description="List all configured database connections",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            types.Tool(
                name="connections_doctor",
                description="Diagnose connection issues",
                inputSchema={
                    "type": "object",
                    "properties": {"connection_id": {"type": "string", "description": "Connection ID to diagnose"}},
                    "required": ["connection_id"],
                },
            ),
            # Component tools
            types.Tool(
                name="components_list",
                description="List available pipeline components",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            # Discovery tool
            types.Tool(
                name="discovery_request",
                description="Discover database schema and optionally sample data",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connection_id": {"type": "string", "description": "Database connection ID"},
                        "component_id": {"type": "string", "description": "Component ID for discovery"},
                        "samples": {
                            "type": "integer",
                            "description": "Number of sample rows to fetch",
                            "minimum": 0,
                            "maximum": 100,
                        },
                        "idempotency_key": {"type": "string", "description": "Key for deterministic caching"},
                    },
                    "required": ["connection_id", "component_id"],
                },
            ),
            # Use cases tool
            types.Tool(
                name="usecases_list",
                description="List available OML use case templates",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            # OML tools
            types.Tool(
                name="oml_schema_get",
                description="Get the OML v0.1.0 JSON schema",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            types.Tool(
                name="oml_validate",
                description="Validate an OML pipeline definition",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "oml_content": {"type": "string", "description": "OML YAML content to validate"},
                        "strict": {"type": "boolean", "description": "Enable strict validation", "default": True},
                    },
                    "required": ["oml_content"],
                },
            ),
            types.Tool(
                name="oml_save",
                description="Save an OML pipeline draft",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "oml_content": {"type": "string", "description": "OML YAML content to save"},
                        "session_id": {"type": "string", "description": "Session ID for the draft"},
                        "filename": {"type": "string", "description": "Optional filename for the draft"},
                    },
                    "required": ["oml_content", "session_id"],
                },
            ),
            # Guide tool
            types.Tool(
                name="guide_start",
                description="Get guided next steps for OML authoring",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "intent": {"type": "string", "description": "User's intent or goal"},
                        "known_connections": {
                            "type": "array",
                            "description": "List of known connection IDs",
                            "items": {"type": "string"},
                        },
                        "has_discovery": {"type": "boolean", "description": "Whether discovery has been performed"},
                        "has_previous_oml": {"type": "boolean", "description": "Whether there's a previous OML draft"},
                        "has_error_report": {"type": "boolean", "description": "Whether there's an error report"},
                    },
                    "required": ["intent"],
                },
            ),
            # Memory tool
            types.Tool(
                name="memory_capture",
                description="Capture session memory with consent",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "consent": {"type": "boolean", "description": "User consent for memory capture"},
                        "retention_days": {"type": "integer", "description": "Days to retain memory", "default": 365},
                        "session_id": {"type": "string", "description": "Session ID"},
                        "actor_trace": {
                            "type": "array",
                            "description": "Trace of actor actions",
                            "items": {"type": "object"},
                        },
                        "intent": {"type": "string", "description": "Captured intent"},
                        "decisions": {"type": "array", "description": "Decision points", "items": {"type": "object"}},
                        "artifacts": {"type": "array", "description": "Artifact URIs", "items": {"type": "string"}},
                        "oml_uri": {"type": ["string", "null"], "description": "OML draft URI if available"},
                        "error_report": {"type": ["object", "null"], "description": "Error report if any"},
                        "notes": {"type": "string", "description": "Additional notes"},
                    },
                    "required": ["consent", "session_id", "intent"],
                },
            ),
            # AIOP tools
            types.Tool(
                name="aiop_list",
                description="List AIOP runs (read-only)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "pipeline": {"type": "string", "description": "Filter by pipeline slug"},
                        "profile": {"type": "string", "description": "Filter by profile name"},
                    },
                },
            ),
            types.Tool(
                name="aiop_show",
                description="Show AIOP summary for a specific run (read-only)",
                inputSchema={
                    "type": "object",
                    "properties": {"run_id": {"type": "string", "description": "Run ID to show"}},
                    "required": ["run_id"],
                },
            ),
        ]

        # Note: Aliases are handled in _call_tool, not registered as separate tools
        return tools

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        """Execute a tool call."""
        try:
            # Log the tool call
            await self.audit.log_tool_call(tool_name=name, arguments=arguments)

            # Resolve aliases
            actual_name = self.tool_aliases.get(name, name)

            # Route to appropriate handler
            if actual_name == "connections_list":
                result = await self._handle_connections_list(arguments)
            elif actual_name == "connections_doctor":
                result = await self._handle_connections_doctor(arguments)
            elif actual_name == "components_list":
                result = await self._handle_components_list(arguments)
            elif actual_name == "discovery_request":
                result = await self._handle_discovery_request(arguments)
            elif actual_name == "usecases_list":
                result = await self._handle_usecases_list(arguments)
            elif actual_name == "oml_schema_get":
                result = await self._handle_oml_schema_get(arguments)
            elif actual_name == "oml_validate":
                result = await self._handle_validate_oml(arguments)
            elif actual_name == "oml_save":
                result = await self._handle_save_oml(arguments)
            elif actual_name == "guide_start":
                result = await self._handle_guide_start(arguments)
            elif actual_name == "memory_capture":
                result = await self._handle_memory_capture(arguments)
            elif actual_name == "aiop_list":
                result = await self._handle_aiop_list(arguments)
            elif actual_name == "aiop_show":
                result = await self._handle_aiop_show(arguments)
            else:
                raise OsirisError(
                    ErrorFamily.SEMANTIC,
                    f"Unknown tool: {name}",
                    path=["tool", "name"],
                    suggest="Use guide_start to see available tools",
                )

            # Convert result to JSON
            result_json = json.dumps(result)

            # Check payload size
            limiter = get_limiter()
            try:
                limiter.check_response(result_json)
            except Exception as e:
                if hasattr(e, "family"):
                    raise
                else:
                    raise OsirisError(
                        ErrorFamily.POLICY, str(e), path=["payload"], suggest="Request smaller data or use pagination"
                    ) from e

            return [types.TextContent(type="text", text=result_json)]

        except OsirisError as e:
            error_response = self.error_handler.format_error(e)
            return [types.TextContent(type="text", text=json.dumps(error_response))]
        except Exception as e:
            logger.error(f"Unexpected error in tool {name}: {e}")
            error_response = self.error_handler.format_unexpected_error(str(e))
            return [types.TextContent(type="text", text=json.dumps(error_response))]

    async def _list_resources(self) -> list[types.Resource]:
        """List available resources."""
        return await self.resolver.list_resources()

    async def _read_resource(self, uri: str) -> types.ReadResourceResult:
        """Read a resource by URI."""
        return await self.resolver.read_resource(uri)

    async def _list_prompts(self) -> list[types.Prompt]:
        """List available prompts."""
        # For MVP, we may not need prompts
        return []

    async def _get_prompt(self, name: str, arguments: dict[str, Any]) -> types.GetPromptResult:
        """Get a prompt by name."""
        raise OsirisError(ErrorFamily.SEMANTIC, f"Prompt not found: {name}", path=["prompt", "name"])

    def __init__(self, server_name: str = None, debug: bool = False):
        """Initialize the MCP server."""
        # Load configuration
        self.config = get_config()
        self.server_name = server_name or self.config.SERVER_NAME
        self.debug = debug

        # Initialize low-level server
        self.server = Server(self.server_name)

        # Initialize components with config-driven paths (filesystem contract compliance)
        self.audit = AuditLogger(log_dir=self.config.audit_dir)
        self.cache = DiscoveryCache(
            cache_dir=self.config.cache_dir, default_ttl_hours=self.config.discovery_cache_ttl_hours
        )
        self.resolver = ResourceResolver(config=self.config)  # Uses config paths for runtime resources
        self.error_handler = OsirisErrorHandler()

        # Initialize tool handlers
        from osiris.mcp.tools import (  # noqa: PLC0415  # Lazy import for performance
            AIOPTools,
            ComponentsTools,
            ConnectionsTools,
            DiscoveryTools,
            GuideTools,
            MemoryTools,
            OMLTools,
            UsecasesTools,
        )

        self.connections_tools = ConnectionsTools(audit_logger=self.audit)
        self.components_tools = ComponentsTools(audit_logger=self.audit)
        self.discovery_tools = DiscoveryTools(self.cache, audit_logger=self.audit)
        self.oml_tools = OMLTools(self.resolver, audit_logger=self.audit)
        self.guide_tools = GuideTools(audit_logger=self.audit)
        self.memory_tools = MemoryTools(memory_dir=self.config.memory_dir, audit_logger=self.audit)
        self.usecases_tools = UsecasesTools(audit_logger=self.audit)
        self.aiop_tools = AIOPTools(audit_logger=self.audit)

        # Register handlers
        self._register_handlers()

        # Tool aliases for backward compatibility
        # Maps legacy names (with dots or osiris prefix) to new underscore-based names
        self.tool_aliases = {
            # Legacy osiris.* names → new names
            "osiris.connections.list": "connections_list",
            "osiris.connections.doctor": "connections_doctor",
            "osiris.components.list": "components_list",
            "osiris.introspect_sources": "discovery_request",
            "osiris.usecases.list": "usecases_list",
            "osiris.oml.schema.get": "oml_schema_get",
            "osiris.validate_oml": "oml_validate",
            "osiris.save_oml": "oml_save",
            "osiris.guide_start": "guide_start",
            "osiris.memory.capture": "memory_capture",
            # Old dot-notation names → new underscore names (for backward compatibility)
            "connections.list": "connections_list",
            "connections.doctor": "connections_doctor",
            "components.list": "components_list",
            "discovery.request": "discovery_request",
            "usecases.list": "usecases_list",
            "oml.schema.get": "oml_schema_get",
            "oml.validate": "oml_validate",
            "oml.save": "oml_save",
            "guide.start": "guide_start",
            "memory.capture": "memory_capture",
        }

    # Tool handler implementations using actual tool modules
    async def _handle_connections_list(self, args: dict[str, Any]) -> dict:
        """Handle connections.list tool."""
        return await self.connections_tools.list(args)

    async def _handle_connections_doctor(self, args: dict[str, Any]) -> dict:
        """Handle connections.doctor tool."""
        return await self.connections_tools.doctor(args)

    async def _handle_components_list(self, args: dict[str, Any]) -> dict:
        """Handle components.list tool."""
        return await self.components_tools.list(args)

    async def _handle_discovery_request(self, args: dict[str, Any]) -> dict:
        """Handle discovery.request tool."""
        return await self.discovery_tools.request(args)

    async def _handle_usecases_list(self, args: dict[str, Any]) -> dict:
        """Handle usecases.list tool."""
        return await self.usecases_tools.list(args)

    async def _handle_oml_schema_get(self, args: dict[str, Any]) -> dict:
        """Handle oml.schema.get tool."""
        return await self.oml_tools.schema_get(args)

    async def _handle_validate_oml(self, args: dict[str, Any]) -> dict:
        """Handle validate_oml tool."""
        return await self.oml_tools.validate(args)

    async def _handle_save_oml(self, args: dict[str, Any]) -> dict:
        """Handle save_oml tool."""
        return await self.oml_tools.save(args)

    async def _handle_guide_start(self, args: dict[str, Any]) -> dict:
        """Handle guide.start tool."""
        return await self.guide_tools.start(args)

    async def _handle_memory_capture(self, args: dict[str, Any]) -> dict:
        """Handle memory.capture tool."""
        return await self.memory_tools.capture(args)

    async def _handle_aiop_list(self, args: dict[str, Any]) -> dict:
        """Handle aiop_list tool."""
        return await self.aiop_tools.list(args)

    async def _handle_aiop_show(self, args: dict[str, Any]) -> dict:
        """Handle aiop_show tool."""
        return await self.aiop_tools.show(args)

    async def run(self):
        """Run the MCP server with stdio transport."""
        # Initialize telemetry if enabled
        telemetry = None
        if self.config.telemetry_enabled:
            telemetry = init_telemetry(enabled=True, output_dir=self.config.telemetry_dir)
            telemetry.emit_server_start(self.config.SERVER_VERSION, self.config.PROTOCOL_VERSION)

        try:
            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(
                    read_stream,
                    write_stream,
                    InitializationOptions(
                        server_name=self.server_name,
                        server_version=self.config.SERVER_VERSION,
                        capabilities=self.server.get_capabilities(
                            notification_options=NotificationOptions(), experimental_capabilities={}
                        ),
                    ),
                )
        finally:
            if telemetry:
                telemetry.emit_server_stop("shutdown")


def main():
    """Entry point for the MCP server."""
    import sys  # noqa: PLC0415  # Lazy import for performance

    # Set up logging
    logging.basicConfig(
        level=logging.INFO if "--debug" not in sys.argv else logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create and run server
    server = OsirisMCPServer(debug="--debug" in sys.argv)
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
