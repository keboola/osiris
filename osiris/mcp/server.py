"""
Osiris MCP Server implementation using the official Model Context Protocol Python SDK.

This server provides OML authoring capabilities through MCP tools and resources.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Union

import mcp.types as types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from osiris.mcp.audit import AuditLogger
from osiris.mcp.cache import DiscoveryCache
from osiris.mcp.errors import OsirisErrorHandler, OsirisError, ErrorFamily
from osiris.mcp.resolver import ResourceResolver

logger = logging.getLogger(__name__)

# MCP Protocol version
MCP_VERSION = "0.5"
MCP_PAYLOAD_LIMIT_MB = 16
SERVER_VERSION = "0.5.0"


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

    async def _list_tools(self) -> List[types.Tool]:
        """List all available tools with their schemas."""
        tools = [
            # Connection tools
            types.Tool(
                name="osiris.connections.list",
                description="List all configured database connections",
                inputSchema={
                    "type": "object",
                    "properties": {},
                }
            ),
            types.Tool(
                name="osiris.connections.doctor",
                description="Diagnose connection issues",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connection_id": {
                            "type": "string",
                            "description": "Connection ID to diagnose"
                        }
                    },
                    "required": ["connection_id"]
                }
            ),

            # Component tools
            types.Tool(
                name="osiris.components.list",
                description="List available pipeline components",
                inputSchema={
                    "type": "object",
                    "properties": {},
                }
            ),

            # Discovery tool
            types.Tool(
                name="osiris.introspect_sources",
                description="Discover database schema and optionally sample data",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connection_id": {
                            "type": "string",
                            "description": "Database connection ID"
                        },
                        "component_id": {
                            "type": "string",
                            "description": "Component ID for discovery"
                        },
                        "samples": {
                            "type": "integer",
                            "description": "Number of sample rows to fetch",
                            "minimum": 0,
                            "maximum": 100
                        },
                        "idempotency_key": {
                            "type": "string",
                            "description": "Key for deterministic caching"
                        }
                    },
                    "required": ["connection_id", "component_id"]
                }
            ),

            # Use cases tool
            types.Tool(
                name="osiris.usecases.list",
                description="List available OML use case templates",
                inputSchema={
                    "type": "object",
                    "properties": {},
                }
            ),

            # OML tools
            types.Tool(
                name="osiris.oml.schema.get",
                description="Get the OML v0.1.0 JSON schema",
                inputSchema={
                    "type": "object",
                    "properties": {},
                }
            ),
            types.Tool(
                name="osiris.validate_oml",
                description="Validate an OML pipeline definition",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "oml_content": {
                            "type": "string",
                            "description": "OML YAML content to validate"
                        },
                        "strict": {
                            "type": "boolean",
                            "description": "Enable strict validation",
                            "default": True
                        }
                    },
                    "required": ["oml_content"]
                }
            ),
            types.Tool(
                name="osiris.save_oml",
                description="Save an OML pipeline draft",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "oml_content": {
                            "type": "string",
                            "description": "OML YAML content to save"
                        },
                        "session_id": {
                            "type": "string",
                            "description": "Session ID for the draft"
                        },
                        "filename": {
                            "type": "string",
                            "description": "Optional filename for the draft"
                        }
                    },
                    "required": ["oml_content", "session_id"]
                }
            ),

            # Guide tool
            types.Tool(
                name="osiris.guide_start",
                description="Get guided next steps for OML authoring",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "intent": {
                            "type": "string",
                            "description": "User's intent or goal"
                        },
                        "known_connections": {
                            "type": "array",
                            "description": "List of known connection IDs",
                            "items": {"type": "string"}
                        },
                        "has_discovery": {
                            "type": "boolean",
                            "description": "Whether discovery has been performed"
                        },
                        "has_previous_oml": {
                            "type": "boolean",
                            "description": "Whether there's a previous OML draft"
                        },
                        "has_error_report": {
                            "type": "boolean",
                            "description": "Whether there's an error report"
                        }
                    },
                    "required": ["intent"]
                }
            ),

            # Memory tool
            types.Tool(
                name="osiris.memory.capture",
                description="Capture session memory with consent",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "consent": {
                            "type": "boolean",
                            "description": "User consent for memory capture"
                        },
                        "retention_days": {
                            "type": "integer",
                            "description": "Days to retain memory",
                            "default": 365
                        },
                        "session_id": {
                            "type": "string",
                            "description": "Session ID"
                        },
                        "actor_trace": {
                            "type": "array",
                            "description": "Trace of actor actions",
                            "items": {"type": "object"}
                        },
                        "intent": {
                            "type": "string",
                            "description": "Captured intent"
                        },
                        "decisions": {
                            "type": "array",
                            "description": "Decision points",
                            "items": {"type": "object"}
                        },
                        "artifacts": {
                            "type": "array",
                            "description": "Artifact URIs",
                            "items": {"type": "string"}
                        },
                        "oml_uri": {
                            "type": ["string", "null"],
                            "description": "OML draft URI if available"
                        },
                        "error_report": {
                            "type": ["object", "null"],
                            "description": "Error report if any"
                        },
                        "notes": {
                            "type": "string",
                            "description": "Additional notes"
                        }
                    },
                    "required": ["consent", "session_id", "intent"]
                }
            ),
        ]

        # Add tool aliases
        for alias, primary in self.tool_aliases.items():
            # Find the primary tool
            primary_tool = next((t for t in tools if t.name == primary), None)
            if primary_tool:
                # Create alias tool with same schema but different name
                alias_tool = types.Tool(
                    name=alias,
                    description=f"Alias for {primary}: {primary_tool.description}",
                    inputSchema=primary_tool.inputSchema
                )
                tools.append(alias_tool)

        return tools

    async def _call_tool(
        self,
        name: str,
        arguments: Dict[str, Any]
    ) -> List[types.TextContent]:
        """Execute a tool call."""
        try:
            # Log the tool call
            await self.audit.log_tool_call(name, arguments)

            # Resolve aliases
            actual_name = self.tool_aliases.get(name, name)

            # Route to appropriate handler
            if actual_name == "osiris.connections.list":
                result = await self._handle_connections_list(arguments)
            elif actual_name == "osiris.connections.doctor":
                result = await self._handle_connections_doctor(arguments)
            elif actual_name == "osiris.components.list":
                result = await self._handle_components_list(arguments)
            elif actual_name == "osiris.introspect_sources":
                result = await self._handle_discovery_request(arguments)
            elif actual_name == "osiris.usecases.list":
                result = await self._handle_usecases_list(arguments)
            elif actual_name == "osiris.oml.schema.get":
                result = await self._handle_oml_schema_get(arguments)
            elif actual_name == "osiris.validate_oml":
                result = await self._handle_validate_oml(arguments)
            elif actual_name == "osiris.save_oml":
                result = await self._handle_save_oml(arguments)
            elif actual_name == "osiris.guide_start":
                result = await self._handle_guide_start(arguments)
            elif actual_name == "osiris.memory.capture":
                result = await self._handle_memory_capture(arguments)
            else:
                raise OsirisError(
                    ErrorFamily.SEMANTIC,
                    f"Unknown tool: {name}",
                    path=["tool", "name"],
                    suggest="Use osiris.guide_start to see available tools"
                )

            # Check payload size
            result_json = json.dumps(result)
            if len(result_json) > MCP_PAYLOAD_LIMIT_MB * 1024 * 1024:
                raise OsirisError(
                    ErrorFamily.POLICY,
                    f"Response exceeds {MCP_PAYLOAD_LIMIT_MB}MB limit",
                    path=["payload"],
                    suggest="Request smaller data or use pagination"
                )

            return [types.TextContent(type="text", text=result_json)]

        except OsirisError as e:
            error_response = self.error_handler.format_error(e)
            return [types.TextContent(type="text", text=json.dumps(error_response))]
        except Exception as e:
            logger.error(f"Unexpected error in tool {name}: {e}")
            error_response = self.error_handler.format_unexpected_error(str(e))
            return [types.TextContent(type="text", text=json.dumps(error_response))]

    async def _list_resources(self) -> List[types.Resource]:
        """List available resources."""
        return await self.resolver.list_resources()

    async def _read_resource(self, uri: str) -> types.ReadResourceResult:
        """Read a resource by URI."""
        return await self.resolver.read_resource(uri)

    async def _list_prompts(self) -> List[types.Prompt]:
        """List available prompts."""
        # For MVP, we may not need prompts
        return []

    async def _get_prompt(self, name: str, arguments: Dict[str, Any]) -> types.GetPromptResult:
        """Get a prompt by name."""
        raise OsirisError(
            ErrorFamily.SEMANTIC,
            f"Prompt not found: {name}",
            path=["prompt", "name"]
        )

    def __init__(
        self,
        server_name: str = "osiris-mcp-server",
        debug: bool = False
    ):
        """Initialize the MCP server."""
        self.server_name = server_name
        self.debug = debug

        # Initialize low-level server
        self.server = Server(server_name)

        # Initialize components
        self.audit = AuditLogger()
        self.cache = DiscoveryCache()
        self.resolver = ResourceResolver()
        self.error_handler = OsirisErrorHandler()

        # Initialize tool handlers
        from osiris.mcp.tools import (
            ConnectionsTools,
            ComponentsTools,
            DiscoveryTools,
            OMLTools,
            GuideTools,
            MemoryTools,
            UsecasesTools
        )

        self.connections_tools = ConnectionsTools()
        self.components_tools = ComponentsTools()
        self.discovery_tools = DiscoveryTools(self.cache)
        self.oml_tools = OMLTools(self.resolver)
        self.guide_tools = GuideTools()
        self.memory_tools = MemoryTools()
        self.usecases_tools = UsecasesTools()

        # Register handlers
        self._register_handlers()

        # Tool aliases for ADR-0036 compatibility
        self.tool_aliases = {
            "discovery.request": "osiris.introspect_sources",
            "guide.start": "osiris.guide_start",
            "oml.validate": "osiris.validate_oml",
            "oml.save": "osiris.save_oml",
        }

    # Tool handler implementations using actual tool modules
    async def _handle_connections_list(self, args: Dict[str, Any]) -> dict:
        """Handle connections.list tool."""
        return await self.connections_tools.list(args)

    async def _handle_connections_doctor(self, args: Dict[str, Any]) -> dict:
        """Handle connections.doctor tool."""
        return await self.connections_tools.doctor(args)

    async def _handle_components_list(self, args: Dict[str, Any]) -> dict:
        """Handle components.list tool."""
        return await self.components_tools.list(args)

    async def _handle_discovery_request(self, args: Dict[str, Any]) -> dict:
        """Handle discovery.request tool."""
        return await self.discovery_tools.request(args)

    async def _handle_usecases_list(self, args: Dict[str, Any]) -> dict:
        """Handle usecases.list tool."""
        return await self.usecases_tools.list(args)

    async def _handle_oml_schema_get(self, args: Dict[str, Any]) -> dict:
        """Handle oml.schema.get tool."""
        return await self.oml_tools.schema_get(args)

    async def _handle_validate_oml(self, args: Dict[str, Any]) -> dict:
        """Handle validate_oml tool."""
        return await self.oml_tools.validate(args)

    async def _handle_save_oml(self, args: Dict[str, Any]) -> dict:
        """Handle save_oml tool."""
        return await self.oml_tools.save(args)

    async def _handle_guide_start(self, args: Dict[str, Any]) -> dict:
        """Handle guide.start tool."""
        return await self.guide_tools.start(args)

    async def _handle_memory_capture(self, args: Dict[str, Any]) -> dict:
        """Handle memory.capture tool."""
        return await self.memory_tools.capture(args)

    async def run(self):
        """Run the MCP server with stdio transport."""
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name=self.server_name,
                    server_version=SERVER_VERSION,
                    capabilities=self.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={}
                    )
                )
            )


def main():
    """Entry point for the MCP server."""
    import sys

    # Set up logging
    logging.basicConfig(
        level=logging.INFO if "--debug" not in sys.argv else logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create and run server
    server = OsirisMCPServer(debug="--debug" in sys.argv)
    asyncio.run(server.run())


if __name__ == "__main__":
    main()