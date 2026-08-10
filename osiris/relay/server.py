"""MCP relay: forwards tool calls to cf-ng and records what actually happened.

The engine's differentiator is evidence. If it is not in the path it cannot
produce evidence, only accept claims — so freeze is grounded in observations
recorded here, not in the agent's recollection.
"""

import asyncio
from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING, Any

from osiris import __version__
from osiris.cfng.client import CfngClient, CfngError
from osiris.cfng.pins import tool_pin
from osiris.evidence.session import Session

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps `mcp` out of import time
    from mcp.server import Server

HANDSHAKE_INSTRUCTIONS = """\
You are connected to Osiris, which relays your cf-ng tool calls and records them.

Workflow:
1. EXPLORE. Call cf-ng tools through this server exactly as you normally would.
   Every call is recorded: arguments, result shape, tool schema hash, duration.
2. FREEZE. When the user wants a finding to run on a schedule, call
   `osiris_freeze` with an explicit plan. Do not guess at arguments you did not
   actually use — the recorded observations are the ground truth and freeze
   validates your plan against them and against cf-ng's live schemas.
3. The frozen artifact runs deterministically with no LLM. Anything that needs
   judgement must be resolved now, at freeze time, not at run time.

Rules:
- Tool names are `connector__tool`.
- Never put a literal credential in a plan. Use `${CFNG_TOKEN}`-style references.
- If a step's result could legitimately be empty, add an `assert` step so a
  silent upstream change stops the run instead of producing an empty result.
"""

FREEZE_TOOL = "osiris_freeze"
OBSERVATIONS_TOOL = "osiris_observations"


class Relay:
    """Records every relayed cf-ng call as an observation."""

    def __init__(self, client: CfngClient, session: Session) -> None:
        self._client = client
        self._session = session
        self._observations: list[dict[str, Any]] = []
        self._schema_cache: dict[str, str] = {}

    def _input_schema_pin(self, connector: str, tool: str) -> str | None:
        """Pin from the REST manifest, not from anything the gateway rewrote."""
        key = f"{connector}__{tool}"
        if key not in self._schema_cache:
            try:
                manifests = self._client.list_tools(connector)
            except CfngError:
                return None
            for manifest in manifests:
                self._schema_cache[f"{connector}__{manifest.get('name')}"] = tool_pin(manifest).input
        return self._schema_cache.get(key)

    @staticmethod
    def _split(name: str) -> tuple[str, str]:
        connector, sep, tool = name.partition("__")
        if not sep or not connector or not tool:
            raise ValueError(f"tool name must be 'connector__tool', got {name!r}")
        return connector, tool

    def list_tools(self, connector: str) -> list[dict[str, Any]]:
        return self._client.list_tools(connector)

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        connector, tool = self._split(name)
        schema_pin = self._input_schema_pin(connector, tool)
        started = datetime.now(UTC)

        observation: dict[str, Any] = {
            "connector": connector,
            "tool": tool,
            "arguments": arguments,
            "input_schema": schema_pin,
            "ts": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        try:
            body = self._client.call_tool(connector, tool, arguments)
        except CfngError as exc:
            observation |= {
                "outcome": "error",
                "status": exc.status,
                "retryable": exc.retryable,
                "detail": exc.detail,
                "duration_ms": round((datetime.now(UTC) - started).total_seconds() * 1000, 1),
            }
            self._record(observation)
            raise

        result = body.get("result")
        observation |= {
            "outcome": "success",
            "rows": len(result) if isinstance(result, list) else 1,
            "server_ms": body.get("_meta", {}).get("server_ms"),
            "duration_ms": round((datetime.now(UTC) - started).total_seconds() * 1000, 1),
        }
        self._record(observation)
        return body

    def _record(self, observation: dict[str, Any]) -> None:
        self._observations.append(observation)
        self._session.log_event("tool_call", **observation)

    def observations(self) -> list[dict[str, Any]]:
        return list(self._observations)


def engine_tools() -> list[dict[str, Any]]:
    """The engine's own tools, as plain MCP-shaped manifests.

    Kept SDK-free so both `build_server` and callers that only want the
    catalogue (tests, `osiris doctor`) read the same single definition.
    """
    return [
        {
            "name": FREEZE_TOOL,
            "description": "Freeze the current exploration into a deterministic, runnable plan.",
            "inputSchema": {
                "type": "object",
                "required": ["plan"],
                "properties": {"plan": {"type": "object", "description": "The draft plan to freeze."}},
            },
        },
        {
            "name": OBSERVATIONS_TOOL,
            "description": "List the tool calls recorded in this session, as ground truth for freezing.",
            "inputSchema": {"type": "object", "properties": {}},
        },
    ]


def build_server(relay: Relay) -> "Server":
    """Wire the relay into an MCP server.

    The `mcp` SDK is imported lazily: `osiris run` never speaks MCP and should
    not pay for the import.
    """
    from mcp import types  # noqa: PLC0415
    from mcp.server import Server  # noqa: PLC0415

    tools = [types.Tool(**manifest) for manifest in engine_tools()]

    def _text_result(text: str, *, is_error: bool = False) -> "types.CallToolResult":
        return types.CallToolResult(content=[types.TextContent(type="text", text=text)], is_error=is_error)

    async def _list_tools(_ctx: Any, _params: Any) -> "types.ListToolsResult":
        return types.ListToolsResult(tools=tools)

    async def _call_tool(_ctx: Any, params: Any) -> "types.CallToolResult":
        name = params.name
        arguments = params.arguments or {}

        if name == OBSERVATIONS_TOOL:
            return _text_result(json.dumps(relay.observations(), ensure_ascii=False, indent=2))
        if name == FREEZE_TOOL:
            return _text_result(json.dumps({"status": "not_implemented_in_phase_1"}))

        try:
            body = await asyncio.to_thread(relay.call, name, arguments)
        except (CfngError, ValueError) as exc:
            # A failed relay is a tool-level failure, not a protocol failure: the
            # agent needs to see it and adapt, and the observation is already recorded.
            return _text_result(str(exc), is_error=True)
        return _text_result(json.dumps(body, ensure_ascii=False))

    return Server(
        "osiris",
        version=__version__,
        instructions=HANDSHAKE_INSTRUCTIONS,
        on_list_tools=_list_tools,
        on_call_tool=_call_tool,
    )


async def serve_stdio(relay: Relay) -> None:
    """Run the relay over stdio with the handshake instructions attached."""
    from mcp.server.stdio import stdio_server  # noqa: PLC0415

    server = build_server(relay)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
