"""The cf-ng client speaks the exact wire contract, including its auth split."""

import httpx
import pytest

from osiris.cfng.client import CfngClient, CfngError


def _client(handler, token="cfng_abc") -> CfngClient:  # pragma: allowlist secret
    c = CfngClient("https://cfng.test", token=token)
    c._http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://cfng.test")
    return c


def test_scoped_token_uses_cfng_header():
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(200, json={"tools": []})

    _client(handler).list_tools("imdb")
    assert seen["x-cfng-token"] == "cfng_abc"  # pragma: allowlist secret
    assert "x-storageapi-token" not in seen


def test_master_token_uses_storage_header_and_stack():
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(200, json={"tools": []})

    c = CfngClient("https://cfng.test", token="master-xyz", stack="connection.keboola.com")  # pragma: allowlist secret
    c._http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://cfng.test")
    c.list_tools("imdb")
    assert seen["x-storageapi-token"] == "master-xyz"  # pragma: allowlist secret
    assert seen["x-cfng-stack"] == "connection.keboola.com"


def test_list_tools_unwraps_the_tools_key():
    def handler(request):
        assert request.url.path == "/connectors/imdb/tools"
        return httpx.Response(200, json={"connector": "imdb", "tools": [{"name": "search_titles"}]})

    assert _client(handler).list_tools("imdb") == [{"name": "search_titles"}]


def test_call_tool_posts_the_documented_body_and_returns_full_response():
    def handler(request):
        import json

        assert request.url.path == "/tools/call"
        assert json.loads(request.content) == {"connector": "imdb", "tool": "search", "arguments": {"q": "dune"}}
        return httpx.Response(
            200,
            json={"connector": "imdb", "tool": "search", "result": {"n": 1}, "_meta": {"server_ms": 12.0}},
        )

    body = _client(handler).call_tool("imdb", "search", {"q": "dune"})
    assert body["result"] == {"n": 1}
    assert body["_meta"]["server_ms"] == 12.0


def test_catalog_version_is_unwrapped():
    def handler(request):
        assert request.url.path == "/catalog/version"
        return httpx.Response(200, json={"catalog_version": "sha256:1a2b", "count": 979})

    assert _client(handler).catalog_version() == "sha256:1a2b"


@pytest.mark.parametrize(
    ("status", "retryable"),
    [(400, False), (401, False), (403, False), (404, False), (429, True), (502, True), (503, True)],
)
def test_errors_carry_status_detail_and_retryability(status, retryable):
    def handler(request):
        return httpx.Response(status, json={"detail": "nope"})

    with pytest.raises(CfngError) as exc:
        _client(handler).call_tool("imdb", "search", {})
    assert exc.value.status == status
    assert exc.value.detail == "nope"
    assert exc.value.retryable is retryable
