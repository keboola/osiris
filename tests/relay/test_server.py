"""The relay forwards to cf-ng and records ground truth for freeze."""

import anyio
import httpx
from mcp.client.session import ClientSession
from mcp.shared.memory import create_client_server_memory_streams
import pytest

from osiris.cfng.client import CfngClient, CfngError
from osiris.evidence.session import Session
from osiris.relay.server import HANDSHAKE_INSTRUCTIONS, Relay, build_server


def _client(handler) -> CfngClient:
    c = CfngClient("https://cfng.test", token="cfng_secrettoken")  # pragma: allowlist secret
    c._http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://cfng.test")
    return c


def _ok(request):
    if request.url.path.endswith("/tools"):
        return httpx.Response(
            200, json={"connector": "imdb", "tools": [{"name": "search", "inputSchema": {"type": "object"}}]}
        )
    return httpx.Response(
        200, json={"connector": "imdb", "tool": "search", "result": [{"t": "Dune"}], "_meta": {"server_ms": 5.0}}
    )


def _relay(tmp_path, handler=_ok) -> Relay:
    session = Session(tmp_path, "sess_1", secrets=["cfng_secrettoken"])  # pragma: allowlist secret
    return Relay(_client(handler), session)


def test_call_forwards_and_returns_the_result(tmp_path):
    body = _relay(tmp_path).call("imdb__search", {"q": "dune"})
    assert body["result"] == [{"t": "Dune"}]


def test_call_records_an_observation_with_the_schema_pin(tmp_path):
    relay = _relay(tmp_path)
    relay.call("imdb__search", {"q": "dune"})
    obs = relay.observations()
    assert len(obs) == 1
    assert obs[0]["connector"] == "imdb"
    assert obs[0]["tool"] == "search"
    assert obs[0]["arguments"] == {"q": "dune"}
    assert obs[0]["input_schema"].startswith("sha256:")
    assert obs[0]["outcome"] == "success"
    assert obs[0]["rows"] == 1


def test_observation_records_failures_too(tmp_path):
    def handler(request):
        if request.url.path.endswith("/tools"):
            return _ok(request)
        return httpx.Response(502, json={"detail": "Upstream provider error."})

    relay = _relay(tmp_path, handler)
    with pytest.raises(CfngError):
        relay.call("imdb__search", {})
    obs = relay.observations()
    assert obs[0]["outcome"] == "error"
    assert obs[0]["status"] == 502
    assert obs[0]["retryable"] is True


def test_token_never_appears_in_recorded_evidence(tmp_path):
    relay = _relay(tmp_path)
    relay.call("imdb__search", {"token": "cfng_secrettoken"})  # pragma: allowlist secret
    raw = (tmp_path / "sess_1" / "events.jsonl").read_text()
    assert "cfng_secrettoken" not in raw  # pragma: allowlist secret


def test_unqualified_tool_name_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="connector__tool"):
        _relay(tmp_path).call("search", {})


def test_handshake_instructions_name_the_workflow(tmp_path):
    for token in ("explore", "osiris_freeze", "deterministic"):
        assert token in HANDSHAKE_INSTRUCTIONS.lower()


def test_schema_pins_are_fetched_once_per_connector(tmp_path):
    """The manifest fetch pins every tool of a connector, so a second tool is free."""
    manifest_fetches = 0

    def handler(request):
        nonlocal manifest_fetches
        if request.url.path.endswith("/tools"):
            manifest_fetches += 1
            return httpx.Response(
                200,
                json={
                    "connector": "imdb",
                    "tools": [
                        {"name": "search", "inputSchema": {"type": "object"}},
                        {
                            "name": "detail",
                            "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}},
                        },
                    ],
                },
            )
        return httpx.Response(200, json={"connector": "imdb", "tool": "x", "result": []})

    relay = _relay(tmp_path, handler)
    relay.call("imdb__search", {})
    relay.call("imdb__detail", {"id": "tt1"})

    assert manifest_fetches == 1
    pins = [obs["input_schema"] for obs in relay.observations()]
    assert all(pin.startswith("sha256:") for pin in pins)
    assert pins[0] != pins[1], "each tool must pin its own schema, not the connector's first one"


@pytest.mark.asyncio
async def test_build_server_serves_the_engine_tools_over_mcp(tmp_path):
    """Constructing and driving the server proves the SDK wiring, not just the Relay."""
    relay = _relay(tmp_path)
    server = build_server(relay)

    async with create_client_server_memory_streams() as (client_streams, server_streams):
        client_read, client_write = client_streams
        server_read, server_write = server_streams
        async with anyio.create_task_group() as tg:
            tg.start_soon(server.run, server_read, server_write, server.create_initialization_options())
            async with ClientSession(client_read, client_write) as session:
                init = await session.initialize()
                assert init.instructions == HANDSHAKE_INSTRUCTIONS

                listed = await session.list_tools()
                assert [tool.name for tool in listed.tools] == ["osiris_freeze", "osiris_observations"]

                relayed = await session.call_tool("imdb__search", {"q": "dune"})
                assert relayed.is_error is False
                assert "Dune" in relayed.content[0].text

                recorded = await session.call_tool("osiris_observations", {})
                assert "imdb" in recorded.content[0].text
            tg.cancel_scope.cancel()
