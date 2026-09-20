"""Explicit operator startup. No legacy dotenv, model keys, user configuration or shell hooks."""

import base64
import json
import os
import ssl
from pathlib import Path

import uvicorn

from .api import create_app
from .contracts import Endpoint
from .protocol import MCPClient
from .oauth_http import OAuthHTTP
from .service import ConnectorGateway, RemoteAuthority
from .vault import Vault


def main():
    try:
        source = Path(os.environ["CONNECTOR_ENDPOINTS_FILE"])
        if not source.is_absolute() or source.stat().st_size > 65536:
            raise ValueError
        values = json.loads(source.read_text(encoding="utf-8"))["endpoints"]
        if not isinstance(values, list) or len(values) > 32:
            raise ValueError
        testing = os.environ.get("CONNECTOR_TEST_MODE") == "1"
        endpoints = {}
        for value in values:
            endpoint = Endpoint(**{**value, "read_tools": frozenset(value["read_tools"]), "test_mode": testing})
            if endpoint.id in endpoints:
                raise ValueError
            endpoints[endpoint.id] = endpoint
        key = base64.b64decode(os.environ["CONNECTOR_VAULT_KEY"], validate=True)
        if len(key) != 32:
            raise ValueError
        service_token = os.environ["CONNECTOR_SERVICE_TOKEN"]
        control_token = os.environ["CONNECTOR_CONTROL_TOKEN"]
        if service_token == control_token:
            raise ValueError
        context = None
        if os.environ.get("CONNECTOR_CA_FILE"):
            ca = Path(os.environ["CONNECTOR_CA_FILE"])
            if not ca.is_absolute() or ca.stat().st_size > 4 * 1024 * 1024:
                raise ValueError
            context = ssl.create_default_context(cafile=str(ca))
        authority = RemoteAuthority(
            os.environ["CONNECTOR_CONTROL_ORIGIN"], control_token, test_mode=testing, ssl_context=context
        )
        vault = Vault(Path(os.environ["CONNECTOR_VAULT_ROOT"]), key)
        stdio = None
        if os.environ.get("CONNECTOR_STDIO_MANAGER_URL"):
            from .stdio_client import StdioManagerClient

            stdio = StdioManagerClient(
                os.environ["CONNECTOR_STDIO_MANAGER_URL"],
                os.environ["CONNECTOR_STDIO_MANAGER_TOKEN"],
                test_mode=testing,
                ssl_context=context,
            )
        if any(endpoint.transport == "stdio" for endpoint in endpoints.values()) and stdio is None:
            raise ValueError("Stdio endpoints require a dedicated remote manager, never host subprocess")
        gateway = ConnectorGateway(
            vault,
            endpoints,
            authority,
            client_factory=lambda endpoint, token: MCPClient(endpoint, token, ssl_context=context),
            oauth_http_factory=lambda endpoint: OAuthHTTP(endpoint, ssl_context=context),
            stdio_manager=stdio,
        )
        app = create_app(gateway, service_token)
        port = int(os.environ.get("CONNECTOR_PORT", "8082"))
        if not 1024 <= port <= 65535:
            raise ValueError
    except (KeyError, ValueError, OSError, TypeError):
        raise RuntimeError("Connector configuration is incomplete or invalid; secret values are not printed") from None
    uvicorn.run(
        app, host=os.environ.get("CONNECTOR_HOST", "127.0.0.1"), port=port, log_level="warning", access_log=False
    )


if __name__ == "__main__":
    main()
