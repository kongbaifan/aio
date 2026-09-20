import asyncio
from types import SimpleNamespace

from ..runtime.contracts import NotDispatched
from .authority import call_payload
from .client import ConnectorError


class MCPDriver:
    def __init__(self, client):
        self.client = client

    async def execute(self, permit):
        payload = call_payload(
            permit.handle,
            permit.id,
            permit.operation_key,
            {"config": permit.config},
            SimpleNamespace(not_after=permit.not_after),
            permit.arguments,
        )
        try:
            result = await self.client.call("mcp/call", payload)
        except ConnectorError as exc:
            if exc.not_sent:
                raise NotDispatched(exc.code, exc.message, exc.status) from None
            raise
        if result.get("operation_key") != permit.operation_key or not isinstance(result.get("result"), dict):
            raise ConnectorError("CONNECTOR_INVALID_RESPONSE")
        return result["result"]

    async def cleanup(self, handle):
        result = await self.client.call(
            "stdio/cleanup",
            {"org_id": str(handle.principal.org_id), "run_id": str(handle.run_id), "generation": handle.generation},
        )
        if result.get("state") not in {"destroyed", "not_configured"}:
            raise ConnectorError("STDIO_CLEANUP_UNCONFIRMED")

    async def finalize(self, handle):
        await self.cleanup(handle)

    async def suspend(self, handle):
        await self.cleanup(handle)


async def maintain_connections(service, org_id, stopping):
    while not stopping.is_set():
        try:
            await service.cleanup(org_id)
        except Exception:
            # No raw HTTP/credential error body in worker logs; durable retiring rows are retained.
            pass
        try:
            await asyncio.wait_for(stopping.wait(), timeout=5)
        except TimeoutError:
            pass
