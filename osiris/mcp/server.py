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


# Canonical tool ID mapping (all aliases -> canonical name)
# This ensures deterministic tool identification in metrics and audit logs
CANONICAL_TOOL_IDS = {
    # Connections tools
    "connections_list": "connections_list",
    "connections.list": "connections_list",
    "osiris.connections.list": "connections_list",
    "connections_doctor": "connections_doctor",
    "connections.doctor": "connections_doctor",
    "osiris.connections.doctor": "connections_doctor",
    # Discovery tools
    "discovery_request": "discovery_request",
    "discovery.request": "discovery_request",
    "osiris.discovery.request": "discovery_request",
    "osiris.introspect_sources": "discovery_request",  # Legacy alias
    # OML tools
    "oml_schema_get": "oml_schema_get",
    "oml.schema.get": "oml_schema_get",
    "osiris.oml.schema.get": "oml_schema_get",
    "oml_validate": "oml_validate",
    "oml.validate": "oml_validate",
    "osiris.oml.validate": "oml_validate",
    "osiris.validate_oml": "oml_validate",  # Legacy alias
    "oml_save": "oml_save",
    "oml.save": "oml_save",
    "osiris.oml.save": "oml_save",
    "osiris.save_oml": "oml_save",  # Legacy alias
    # Guide tools
    "guide_start": "guide_start",
    "guide.start": "guide_start",
    "osiris.guide_start": "guide_start",
    "osiris.guide.start": "guide_start",
    # Memory tools
    "memory_capture": "memory_capture",
    "memory.capture": "memory_capture",
    "osiris.memory.capture": "memory_capture",
    # AIOP tools
    "aiop_list": "aiop_list",
    "aiop.list": "aiop_list",
    "osiris.aiop.list": "aiop_list",
    "aiop_show": "aiop_show",
    "aiop.show": "aiop_show",
    "osiris.aiop.show": "aiop_show",
    # Components tools
    "components_list": "components_list",
    "components.list": "components_list",
    "osiris.components.list": "components_list",
    # Usecases tools
    "usecases_list": "usecases_list",
    "usecases.list": "usecases_list",
    "osiris.usecases.list": "usecases_list",
}


def canonical_tool_id(name: str) -> str:
    """
    Get canonical tool ID for any alias.

    This ensures all tool name variations map to the same canonical name,
    making metrics and audit logs deterministic across different client implementations.

    Args:
        name: Tool name or alias

    Returns:
        Canonical tool ID (or original name if no mapping exists)
    """
    return CANONICAL_TOOL_IDS.get(name, name)


def _success_envelope(result: dict, meta: dict) -> dict:
    """MCP protocol success response envelope."""
    return {"status": "success", "result": result, "_meta": meta}


def _error_envelope(code: str, message: str, details: dict | None, meta: dict) -> dict:
    """MCP protocol error response envelope."""
    return {"status": "error", "error": {"code": code, "message": message, "details": details or {}}, "_meta": meta}


# Policy constants
MAX_PAYLOAD_BYTES = 16 * 1024 * 1024  # 16MB


def _validate_payload_size(args: dict) -> tuple[bool, int, str | None]:
    """
    Validate payload size against 16MB limit.

    Returns:
        (is_valid, size_bytes, error_message)
    """
    size = len(json.dumps(args).encode("utf-8"))
    if size > MAX_PAYLOAD_BYTES:
        return False, size, f"Payload {size} bytes exceeds {MAX_PAYLOAD_BYTES} byte limit"
    return True, size, None


def _validate_consent(tool_name: str, args: dict) -> tuple[bool, str | None]:
    """
    Validate consent requirement for memory tools.

    Returns:
        (is_valid, error_message)
    """
    if tool_name in ["memory_capture", "memory.capture", "osiris.memory.capture"]:
        if not args.get("consent", False):
            return False, "Memory capture requires explicit --consent flag"
    return True, None


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
                    "properties": {"connection": {"type": "string", "description": "Connection ID to diagnose"}},
                    "required": ["connection"],
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
                description="Discover database schema and optionally sample data. 💡 Use this to explore database schemas before creating pipelines. Helps understand table structure and relationships.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connection": {"type": "string", "description": "Database connection ID"},
                        "component": {"type": "string", "description": "Component ID for discovery"},
                        "samples": {
                            "type": "integer",
                            "description": "Number of sample rows to fetch",
                            "minimum": 0,
                            "maximum": 100,
                        },
                        "idempotency_key": {"type": "string", "description": "Key for deterministic caching"},
                    },
                    "required": ["connection", "component"],
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
                description="Get the OML v0.1.0 JSON schema. ⚠️ CALL THIS FIRST before creating any OML pipeline. Returns the complete OML v0.1.0 JSON schema.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            types.Tool(
                name="oml_validate",
                description="Validate an OML pipeline definition. ⚠️ ALWAYS call this before oml_save. Validates OML structure, connections, and business logic.",
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
                description="Save an OML pipeline draft. ⚠️ ONLY call after successful oml_validate. Saves the validated OML pipeline draft.",
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
                description="⚠️ REQUIRED: Call this FIRST when starting any OML pipeline task. Returns complete workflow instructions, validation requirements, and guided next steps. Contains critical rules you MUST follow.",
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
            # Generate correlation ID for tracking
            # NOTE: MCP SDK doesn't expose request_id at handler level, so we use random UUID
            # If request_id becomes available in future SDK versions, use derive_correlation_id(request_id)
            import uuid  # noqa: PLC0415  # Lazy import

            correlation_id = str(uuid.uuid4())

            # Get canonical tool ID for deterministic metrics
            canonical_tool = canonical_tool_id(name)

            # POLICY GUARD: Validate payload size (BEFORE delegating to CLI)
            is_valid, size, error_msg = _validate_payload_size(arguments)
            if not is_valid:
                meta = {
                    "correlation_id": correlation_id,
                    "tool": canonical_tool,
                    "bytes_in": size,
                    "bytes_out": 0,
                    "duration_ms": 0,
                }
                error_response = _error_envelope(
                    "payload_too_large", error_msg, {"limit_bytes": MAX_PAYLOAD_BYTES, "actual_bytes": size}, meta
                )
                return [types.TextContent(type="text", text=json.dumps(error_response))]

            # POLICY GUARD: Validate consent for memory tools (BEFORE delegating to CLI)
            is_valid, error_msg = _validate_consent(name, arguments)
            if not is_valid:
                meta = {
                    "correlation_id": correlation_id,
                    "tool": canonical_tool,
                    "bytes_in": size,
                    "bytes_out": 0,
                    "duration_ms": 0,
                }
                error_response = _error_envelope("consent_required", error_msg, {"tool": canonical_tool}, meta)
                return [types.TextContent(type="text", text=json.dumps(error_response))]

            # Log the tool call
            await self.audit.log_tool_call(tool_name=canonical_tool, arguments=arguments)

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

            # Inject canonical tool ID into _meta if not already present
            if isinstance(result, dict) and "_meta" in result:
                if "tool" not in result["_meta"]:
                    result["_meta"]["tool"] = canonical_tool

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
        try:
            result = await self.connections_tools.list(args)
            meta = result.pop("_meta", {})
            return _success_envelope(result, meta)
        except OsirisError as e:
            meta = getattr(e, "meta", {})
            return _error_envelope(
                e.family.value if hasattr(e, "family") else "UNKNOWN",
                str(e),
                e.to_dict() if hasattr(e, "to_dict") else None,
                meta,
            )
        except Exception as e:
            return _error_envelope("INTERNAL", str(e), None, {})

    async def _handle_connections_doctor(self, args: dict[str, Any]) -> dict:
        """Handle connections.doctor tool."""
        try:
            result = await self.connections_tools.doctor(args)
            meta = result.pop("_meta", {})
            return _success_envelope(result, meta)
        except OsirisError as e:
            meta = getattr(e, "meta", {})
            return _error_envelope(
                e.family.value if hasattr(e, "family") else "UNKNOWN",
                str(e),
                e.to_dict() if hasattr(e, "to_dict") else None,
                meta,
            )
        except Exception as e:
            return _error_envelope("INTERNAL", str(e), None, {})

    async def _handle_components_list(self, args: dict[str, Any]) -> dict:
        """Handle components.list tool."""
        try:
            result = await self.components_tools.list(args)
            meta = result.pop("_meta", {})
            return _success_envelope(result, meta)
        except OsirisError as e:
            meta = getattr(e, "meta", {})
            return _error_envelope(
                e.family.value if hasattr(e, "family") else "UNKNOWN",
                str(e),
                e.to_dict() if hasattr(e, "to_dict") else None,
                meta,
            )
        except Exception as e:
            return _error_envelope("INTERNAL", str(e), None, {})

    async def _handle_discovery_request(self, args: dict[str, Any]) -> dict:
        """Handle discovery.request tool."""
        try:
            result = await self.discovery_tools.request(args)
            meta = result.pop("_meta", {})
            return _success_envelope(result, meta)
        except OsirisError as e:
            meta = getattr(e, "meta", {})
            return _error_envelope(
                e.family.value if hasattr(e, "family") else "UNKNOWN",
                str(e),
                e.to_dict() if hasattr(e, "to_dict") else None,
                meta,
            )
        except Exception as e:
            return _error_envelope("INTERNAL", str(e), None, {})

    async def _handle_usecases_list(self, args: dict[str, Any]) -> dict:
        """Handle usecases.list tool."""
        try:
            result = await self.usecases_tools.list(args)
            meta = result.pop("_meta", {})
            return _success_envelope(result, meta)
        except OsirisError as e:
            meta = getattr(e, "meta", {})
            return _error_envelope(
                e.family.value if hasattr(e, "family") else "UNKNOWN",
                str(e),
                e.to_dict() if hasattr(e, "to_dict") else None,
                meta,
            )
        except Exception as e:
            return _error_envelope("INTERNAL", str(e), None, {})

    async def _handle_oml_schema_get(self, args: dict[str, Any]) -> dict:
        """Handle oml.schema.get tool."""
        try:
            result = await self.oml_tools.schema_get(args)
            meta = result.pop("_meta", {})
            return _success_envelope(result, meta)
        except OsirisError as e:
            meta = getattr(e, "meta", {})
            return _error_envelope(
                e.family.value if hasattr(e, "family") else "UNKNOWN",
                str(e),
                e.to_dict() if hasattr(e, "to_dict") else None,
                meta,
            )
        except Exception as e:
            return _error_envelope("INTERNAL", str(e), None, {})

    async def _handle_validate_oml(self, args: dict[str, Any]) -> dict:
        """Handle validate_oml tool."""
        try:
            result = await self.oml_tools.validate(args)
            meta = result.pop("_meta", {})
            return _success_envelope(result, meta)
        except OsirisError as e:
            meta = getattr(e, "meta", {})
            return _error_envelope(
                e.family.value if hasattr(e, "family") else "UNKNOWN",
                str(e),
                e.to_dict() if hasattr(e, "to_dict") else None,
                meta,
            )
        except Exception as e:
            return _error_envelope("INTERNAL", str(e), None, {})

    async def _handle_save_oml(self, args: dict[str, Any]) -> dict:
        """Handle save_oml tool."""
        try:
            result = await self.oml_tools.save(args)
            meta = result.pop("_meta", {})
            return _success_envelope(result, meta)
        except OsirisError as e:
            meta = getattr(e, "meta", {})
            return _error_envelope(
                e.family.value if hasattr(e, "family") else "UNKNOWN",
                str(e),
                e.to_dict() if hasattr(e, "to_dict") else None,
                meta,
            )
        except Exception as e:
            return _error_envelope("INTERNAL", str(e), None, {})

    async def _handle_guide_start(self, args: dict[str, Any]) -> dict:
        """Handle guide.start tool."""
        try:
            result = await self.guide_tools.start(args)
            meta = result.pop("_meta", {})
            return _success_envelope(result, meta)
        except OsirisError as e:
            meta = getattr(e, "meta", {})
            return _error_envelope(
                e.family.value if hasattr(e, "family") else "UNKNOWN",
                str(e),
                e.to_dict() if hasattr(e, "to_dict") else None,
                meta,
            )
        except Exception as e:
            return _error_envelope("INTERNAL", str(e), None, {})

    async def _handle_memory_capture(self, args: dict[str, Any]) -> dict:
        """Handle memory.capture tool."""
        try:
            result = await self.memory_tools.capture(args)
            meta = result.pop("_meta", {})
            return _success_envelope(result, meta)
        except OsirisError as e:
            meta = getattr(e, "meta", {})
            return _error_envelope(
                e.family.value if hasattr(e, "family") else "UNKNOWN",
                str(e),
                e.to_dict() if hasattr(e, "to_dict") else None,
                meta,
            )
        except Exception as e:
            return _error_envelope("INTERNAL", str(e), None, {})

    async def _handle_aiop_list(self, args: dict[str, Any]) -> dict:
        """Handle aiop_list tool."""
        try:
            result = await self.aiop_tools.list(args)
            meta = result.pop("_meta", {})
            return _success_envelope(result, meta)
        except OsirisError as e:
            meta = getattr(e, "meta", {})
            return _error_envelope(
                e.family.value if hasattr(e, "family") else "UNKNOWN",
                str(e),
                e.to_dict() if hasattr(e, "to_dict") else None,
                meta,
            )
        except Exception as e:
            return _error_envelope("INTERNAL", str(e), None, {})

    async def _handle_aiop_show(self, args: dict[str, Any]) -> dict:
        """Handle aiop_show tool."""
        try:
            result = await self.aiop_tools.show(args)
            meta = result.pop("_meta", {})
            return _success_envelope(result, meta)
        except OsirisError as e:
            meta = getattr(e, "meta", {})
            return _error_envelope(
                e.family.value if hasattr(e, "family") else "UNKNOWN",
                str(e),
                e.to_dict() if hasattr(e, "to_dict") else None,
                meta,
            )
        except Exception as e:
            return _error_envelope("INTERNAL", str(e), None, {})

    async def run(self):
        """Run the MCP server with stdio transport."""
        # Initialize telemetry if enabled
        telemetry = None
        if self.config.telemetry_enabled:
            telemetry = init_telemetry(enabled=True, output_dir=self.config.telemetry_dir)
            telemetry.emit_server_start(self.config.SERVER_VERSION, self.config.PROTOCOL_VERSION)

        try:
            async with stdio_server() as (read_stream, write_stream):
                # Prepare server instructions for LLM clients
                instructions = (
                    "Osiris MCP Server - Usage Instructions:\n\n"
                    "WORKFLOW:\n"
                    "1. List connections: Use 'connections.list' to see available data sources\n"
                    "2. Get OML schema: ALWAYS call 'oml.schema.get' FIRST to understand OML v0.1.0 structure\n"
                    "3. Clarify business logic: Before creating OML, ask user to define ambiguous terms:\n"
                    "   - 'TOP products' → Top by what metric? (sales, rating, date)\n"
                    "   - 'recent data' → What timeframe? (last day, week, month)\n"
                    "   - Ensure transformations and filters are well-defined\n"
                    "4. Create OML: Draft pipeline following schema structure (use 'duckdb.processor' for SQL transformations)\n"
                    "5. Validate: ALWAYS call 'oml.validate' to verify OML before saving\n"
                    "6. Save: Only call 'oml.save' if validation passes\n"
                    "7. Capture learnings: Use 'memory.capture' to save successful patterns, business decisions, user preferences\n\n"
                    "VALIDATION RULES:\n"
                    "- Steps with write_mode='replace' or 'upsert' REQUIRE 'primary_key' field\n"
                    "- Connection references must use '@family.alias' format\n"
                    "- All step IDs must be unique\n\n"
                    "DISCOVERY:\n"
                    "- Use 'discovery.request' to explore database schemas and tables\n"
                    "- Progressive discovery helps understand data structure before creating pipelines\n\n"
                    "TRANSFORMATIONS & OUTPUT:\n"
                    "- Use 'duckdb.processor' for in-memory SQL transformations (joins, aggregations, filters)\n"
                    "- Use 'filesystem.csv_writer' for local CSV file output\n\n"
                    "For detailed guidance, use 'guide.get' with specific topics."
                )

                await self.server.run(
                    read_stream,
                    write_stream,
                    InitializationOptions(
                        server_name=self.server_name,
                        server_version=self.config.SERVER_VERSION,
                        capabilities=self.server.get_capabilities(
                            notification_options=NotificationOptions(), experimental_capabilities={}
                        ),
                        instructions=instructions,
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
