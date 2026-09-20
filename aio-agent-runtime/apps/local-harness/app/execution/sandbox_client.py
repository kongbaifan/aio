"""Authenticated remote manager client and registered Python execution driver."""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

import httpx

from ..platform_errors import PlatformError
from ..runtime.actions import canonical_digest, strict_json
from ..runtime.contracts import DispatchPermit, WorkHandle, NotDispatched
from .coordinator import SandboxCoordinator


class ManagerClient:
    def __init__(self, url: str, token: str, *, client: httpx.AsyncClient | None = None):
        from ..platform_settings import validate_endpoint

        parsed = urlsplit(url)
        testing = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        self.url = validate_endpoint(url, "manager endpoint", production=not testing).rstrip("/")
        if len(token) < 32:
            raise ValueError("Manager service credential is required")
        self.token = token
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(330, connect=5), follow_redirects=False, trust_env=False
        )
        self.owns_client = client is None

    async def call(self, operation: str, payload: dict) -> dict:
        if operation not in {"ensure", "execute", "finalize", "checkpoint", "stop", "status", "acknowledge"}:
            raise ValueError("Unknown manager operation")
        try:
            async with self.client.stream(
                "POST",
                self.url + "/v1/cells/" + operation,
                json=payload,
                headers={"Authorization": "Bearer " + self.token, "Accept-Encoding": "identity"},
            ) as response:
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 14 * 1024 * 1024:
                        raise PlatformError("MANAGER_RESPONSE_TOO_LARGE", "Execution response exceeded its limit", 502)
                obj = strict_json(bytes(data), max_bytes=14 * 1024 * 1024)
                if response.status_code != 200:
                    code = (
                        obj.get("error", {}).get("code", "MANAGER_FAILED")
                        if isinstance(obj, dict)
                        else "MANAGER_FAILED"
                    )
                    if not isinstance(code, str) or not code.replace("_", "").isalnum() or len(code) > 64:
                        code = "MANAGER_FAILED"
                    raise PlatformError(code, "Isolated execution could not complete this operation", 502)
                if not isinstance(obj, dict):
                    raise PlatformError("MANAGER_RESPONSE_INVALID", "Execution response is invalid", 502)
                return obj
        except httpx.HTTPError:
            raise PlatformError(
                "MANAGER_UNAVAILABLE", "Execution manager connection failed; outcome may require reconciliation", 503
            ) from None

    async def close(self):
        if self.owns_client:
            await self.client.aclose()


class SandboxPythonDriver:
    def __init__(self, coordinator: SandboxCoordinator, client: ManagerClient):
        self.coordinator, self.client = coordinator, client

    async def execute(self, permit: DispatchPermit):
        try:
            spec = await asyncio.to_thread(self.coordinator.reserve, permit)
            code = await asyncio.to_thread(self.coordinator.command, permit)
        except PlatformError as exc:
            raise NotDispatched(exc.code, exc.message, exc.status) from None
        ready = await self.client.call("ensure", {"spec": spec})
        if (
            ready.get("binding_id") != spec["binding_id"]
            or ready.get("state") != "ready"
            or ready.get("spec_digest") != canonical_digest("aio-cell-spec-v1", spec)
        ):
            raise PlatformError("MANAGER_RESPONSE_INVALID", "Manager returned an unrelated execution binding", 502)
        await asyncio.to_thread(self.coordinator.observed, spec, "ready", ready.get("container_id"))
        result = await self.client.call(
            "execute",
            {
                "spec": spec,
                "dispatch_id": str(permit.id),
                "language": "python",
                "code": code,
                "timeout_seconds": permit.config.get("timeout_seconds", 120),
            },
        )
        if result.get("binding_id") != spec["binding_id"] or result.get("dispatch_id") != str(permit.id):
            raise PlatformError("MANAGER_RESPONSE_INVALID", "Manager returned an unrelated execution result", 502)
        if result.get("error_code"):
            stopped = await self.client.call("stop", {"spec": spec})
            if stopped.get("state") == "destroyed":
                await asyncio.to_thread(self.coordinator.observed, spec, "destroyed")
        if permit.driver == "skill.python":
            return await asyncio.to_thread(self.coordinator.skill_result, permit, result)
        return {k: result.get(k) for k in ("stdout", "stderr", "exit_code", "error_code", "truncated")}

    async def finalize(self, handle: WorkHandle):
        restored = await asyncio.to_thread(self.coordinator.store.workspace.inputs, handle)
        if restored is not None:
            from ..workspaces.checkpoints import as_export

            await asyncio.to_thread(
                self.coordinator.artifacts.stage_export,
                handle.principal,
                handle.run_id,
                handle.generation,
                as_export(restored),
            )
        for lease in await asyncio.to_thread(self.coordinator.leases, handle):
            if lease["state"] == "destroyed":
                continue
            spec = lease["spec"]
            result = await self.client.call("finalize", {"spec": spec})
            if (
                result.get("binding_id") != spec["binding_id"]
                or result.get("spec_digest") != lease["spec_digest"]
                or result.get("state") != "destroyed"
            ):
                raise PlatformError(
                    "MANAGER_RESPONSE_INVALID", "Finalization did not confirm the expected stopped writer", 502
                )
            await asyncio.to_thread(self.coordinator.observed, spec, "destroyed")
            await asyncio.to_thread(
                self.coordinator.artifacts.stage_export,
                handle.principal,
                handle.run_id,
                handle.generation,
                result["files"],
            )

    async def suspend(self, handle: WorkHandle):
        checkpoints = self.coordinator.store.workspace
        saved = await asyncio.to_thread(checkpoints.begin, handle)
        if saved is None or saved["state"] == "ready":
            return
        result = await self.client.call("checkpoint", {"spec": saved["spec"]})
        await asyncio.to_thread(checkpoints.accept, handle, saved["id"], result)
        try:
            ack = await self.client.call("acknowledge", {"spec": saved["spec"]})
            if ack.get("state") == "acknowledged" and ack.get("binding_id") == saved["spec"]["binding_id"]:
                await asyncio.to_thread(checkpoints.mark_acknowledged, handle.principal.org_id, saved["id"])
        except PlatformError:
            pass  # Durable ready files are usable; the maintenance loop retries only payload purging.

    async def cleanup(self, handle: WorkHandle):
        for lease in await asyncio.to_thread(self.coordinator.leases, handle):
            if lease["state"] == "destroyed":
                continue
            spec = lease["spec"]
            result = await self.client.call("stop", {"spec": spec})
            if result.get("state") != "destroyed" or result.get("binding_id") != spec["binding_id"]:
                raise PlatformError("CLEANUP_UNCONFIRMED", "Manager did not confirm cleanup", 503)
            await asyncio.to_thread(self.coordinator.observed, spec, "destroyed")
