"""The cf-ng client speaks the exact wire contract, including its auth split."""

import httpx
import pytest

from osiris.cfng.client import MALFORMED_RESPONSE, TRANSPORT_ERROR, CfngClient, CfngError


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


# --- Failures that never reach an HTTP response -----------------------------
#
# Found in hands-on use, not by the suite: pointing the client at a dead host
# produced a raw httpx.ConnectError traceback. A caller should not have to know
# httpx exists to handle "cf-ng is unreachable".


def test_an_unreachable_host_becomes_a_cfng_error():
    def handler(request):
        raise httpx.ConnectError("connection refused")

    with pytest.raises(CfngError) as exc:
        _client(handler).catalog_version()
    assert exc.value.status == TRANSPORT_ERROR
    assert "could not reach cf-ng" in exc.value.detail


def test_an_unreachable_host_is_retryable():
    """The host may simply be restarting; that is not the same as a 403."""

    def handler(request):
        raise httpx.ConnectError("connection refused")

    with pytest.raises(CfngError) as exc:
        _client(handler).catalog_version()
    assert exc.value.retryable is True


def test_a_timeout_becomes_a_cfng_error():
    def handler(request):
        raise httpx.ReadTimeout("too slow")

    with pytest.raises(CfngError) as exc:
        _client(handler).catalog_version()
    assert exc.value.status == TRANSPORT_ERROR


def test_a_non_json_200_becomes_a_cfng_error():
    """A proxy or captive portal answering 200 with HTML is not cf-ng."""

    def handler(request):
        return httpx.Response(200, text="<html>Sign in to the network</html>", headers={"content-type": "text/html"})

    with pytest.raises(CfngError) as exc:
        _client(handler).catalog_version()
    assert exc.value.status == MALFORMED_RESPONSE
    assert "not JSON" in exc.value.detail
    assert exc.value.retryable is False


def test_the_transport_error_message_never_carries_the_token():
    def handler(request):
        raise httpx.ConnectError("connection refused")

    client = CfngClient("https://cfng.test", token="cfng_secrettokenvalue")  # pragma: allowlist secret
    client._http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://cfng.test")
    with pytest.raises(CfngError) as exc:
        client.catalog_version()
    assert "cfng_secrettokenvalue" not in str(exc.value)  # pragma: allowlist secret


def test_a_real_status_is_quoted_but_a_synthetic_one_is_named():
    """A user can act on '403'. '-1' is a number that exists only inside this module."""
    assert CfngError(403, "nope").label == "403"
    assert CfngError(TRANSPORT_ERROR, "nope").label == "unreachable"
    assert CfngError(MALFORMED_RESPONSE, "nope").label == "not a JSON response"
    assert "-1" not in str(CfngError(TRANSPORT_ERROR, "host is down"))
