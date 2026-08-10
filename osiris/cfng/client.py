"""HTTP client for the cf-ng REST surface.

Pins are always computed from GET /connectors/{id}/tools, never from the MCP
gateway: the gateway rewrites inputSchema to inject `credentials` and
`credentials_label`, so a gateway-derived hash would drift whenever a
connector's credential schema changed, even if the tool itself did not.
"""

from typing import Any

import httpx

_RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})

# Synthetic statuses for failures that never reached an HTTP response. Negative
# so they can never collide with a real one, and so `status` stays a single
# comparable field rather than becoming an optional.
TRANSPORT_ERROR = -1
MALFORMED_RESPONSE = -2

_RETRYABLE_SYNTHETIC = frozenset({TRANSPORT_ERROR})


_SYNTHETIC_LABELS = {
    TRANSPORT_ERROR: "unreachable",
    MALFORMED_RESPONSE: "not a JSON response",
}


class CfngError(Exception):
    """A cf-ng call failed."""

    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail
        self.retryable = status in _RETRYABLE_STATUSES or status in _RETRYABLE_SYNTHETIC
        super().__init__(f"cf-ng {self.label}: {detail}")

    @property
    def label(self) -> str:
        """How to name this failure to a human.

        A real HTTP status is worth quoting; a synthetic one is not. `status -1`
        in a message a user reads is a number that exists only inside this
        module, and it reads as a bug rather than as "the host did not answer".
        """
        return _SYNTHETIC_LABELS.get(self.status, str(self.status))


class CfngClient:
    """Talks to cf-ng with either a scoped capability token or a Keboola master token."""

    def __init__(self, base_url: str, token: str, stack: str | None = None, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._stack = stack
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout)

    def _headers(self) -> dict[str, str]:
        if self._token.startswith("cfng_"):
            return {"X-Cfng-Token": self._token}
        headers = {"X-StorageApi-Token": self._token}
        if self._stack:
            headers["X-Cfng-Stack"] = self._stack
        return headers

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._http.request(method, path, headers=self._headers(), **kwargs)
        except httpx.HTTPError as exc:
            # A caller should not have to know httpx exists to handle "cf-ng is
            # unreachable". Found in hands-on use: pointing the client at a dead
            # host produced a raw ConnectError traceback, which is the same class
            # of unhandled exit the pin probe was fixed for -- just one layer down,
            # where every other caller inherits it.
            raise CfngError(TRANSPORT_ERROR, f"could not reach cf-ng at {self.base_url}: {exc}") from exc

        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise CfngError(response.status_code, str(detail))

        try:
            return response.json()
        except ValueError as exc:
            # A 200 that is not JSON means something is answering that is not
            # cf-ng -- a proxy, a captive portal, an HTML error page.
            raise CfngError(
                MALFORMED_RESPONSE,
                f"cf-ng returned {response.status_code} with a body that is not JSON "
                f"(content-type {response.headers.get('content-type', 'unknown')}). "
                f"Check that {self.base_url} is really a cf-ng instance.",
            ) from exc

    def list_tools(self, connector: str) -> list[dict[str, Any]]:
        """Canonical MCP-shaped tool manifests for one connector."""
        return self._request("GET", f"/connectors/{connector}/tools").get("tools", [])

    def call_tool(self, connector: str, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute one tool. Returns the full body: {connector, tool, result, _meta}."""
        return self._request(
            "POST",
            "/tools/call",
            json={"connector": connector, "tool": tool, "arguments": arguments},
        )

    def catalog_version(self) -> str:
        """Content hash of the catalog; cheap drift probe."""
        return self._request("GET", "/catalog/version")["catalog_version"]

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "CfngClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
