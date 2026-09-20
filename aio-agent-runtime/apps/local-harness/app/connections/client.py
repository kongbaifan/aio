"""Private gateway client; API/Worker know credential references, never a vault master key."""

import httpx

from ..platform_errors import PlatformError
from ..runtime.actions import strict_json


class ConnectorError(PlatformError):
    def __init__(self, code, status=502, *, not_sent=False):
        self.not_sent = not_sent
        super().__init__(code, "The isolated connector could not complete this operation", status)


class ConnectorClient:
    def __init__(self, url, token, *, client=None):
        self.url, self._token = url.rstrip("/"), token
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(130, connect=5), trust_env=False, follow_redirects=False
        )
        self._owned = client is None

    async def call(self, path, payload):
        if path not in {
            "credentials/put",
            "credentials/revoke",
            "mcp/discover",
            "mcp/call",
            "mcp/status",
            "oauth/start",
            "oauth/exchange",
            "stdio/cleanup",
        }:
            raise ValueError("Unsupported connector operation")
        try:
            async with self.client.stream(
                "POST",
                self.url + "/v1/" + path,
                json=payload,
                headers={"Authorization": "Bearer " + self._token, "Accept-Encoding": "identity"},
            ) as response:
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 2 * 1024 * 1024:
                        raise ConnectorError("CONNECTOR_RESPONSE_TOO_LARGE")
                result = strict_json(bytes(data), max_bytes=2 * 1024 * 1024)
                if not isinstance(result, dict):
                    raise ConnectorError("CONNECTOR_INVALID_RESPONSE")
                if response.status_code != 200:
                    error = result.get("error", {})
                    code = error.get("code", "CONNECTOR_FAILED") if isinstance(error, dict) else "CONNECTOR_FAILED"
                    if not isinstance(code, str) or len(code) > 64 or not code.replace("_", "").isalnum():
                        code = "CONNECTOR_FAILED"
                    raise ConnectorError(
                        code,
                        response.status_code if response.status_code in {403, 409, 422, 429} else 502,
                        not_sent=error.get("not_sent") is True if isinstance(error, dict) else False,
                    )
                return result
        except httpx.HTTPError:
            raise ConnectorError("CONNECTOR_UNAVAILABLE", 503) from None

    async def close(self):
        if self._owned:
            await self.client.aclose()
