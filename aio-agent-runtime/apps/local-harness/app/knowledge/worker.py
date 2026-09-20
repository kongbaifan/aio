import asyncio
import logging
from contextlib import suppress

from ..platform_errors import PlatformError
from ..runtime.actions import canonical_digest
from .jobs import PARSER_COMMAND, PARSER_TIMEOUT

logger = logging.getLogger(__name__)


class KnowledgeWorker:
    def __init__(self, jobs, manager, embedder, org_id, worker_id, *, stopping=None):
        self.jobs, self.manager, self.embedder, self.org_id, self.worker_id = jobs, manager, embedder, org_id, worker_id
        self.stopping = stopping or asyncio.Event()

    async def _pulse(self, handle):
        while True:
            await asyncio.sleep(min(5, self.jobs.settings.lease_seconds / 3))
            await asyncio.to_thread(self.jobs.pulse, handle)

    async def _ack(self, handle, spec):
        response = await self.manager.call("acknowledge", {"spec": spec})
        await asyncio.to_thread(self.jobs.acknowledged, handle, response)

    async def _cleanup(self, handle):
        if handle.get("spec") and not handle.get("export_acknowledged"):
            response = await self.manager.call("stop", {"spec": handle["spec"]})
            await asyncio.to_thread(self.jobs.stopped, handle, response)
            await self._ack(handle, handle["spec"])

    async def run_once(self):
        recovery = await asyncio.to_thread(self.jobs.recover, self.org_id, self.worker_id)
        if recovery:
            if recovery["state"] == "cleanup_pending":
                await self._cleanup(recovery)
            return {"id": recovery["id"], "state": recovery["state"]}
        handle = await asyncio.to_thread(self.jobs.claim, self.org_id, self.worker_id)
        if not handle:
            return None
        pulse = asyncio.create_task(self._pulse(handle))

        async def drive():
            nonlocal handle
            if handle["phase"] == "parse":
                handle = await asyncio.to_thread(self.jobs.prepare, handle)
                spec = handle["spec"]
                response = await self.manager.call("ensure", {"spec": spec})
                if (
                    response.get("binding_id") != spec["binding_id"]
                    or response.get("state") != "ready"
                    or response.get("spec_digest") != canonical_digest("aio-cell-spec-v1", spec)
                ):
                    raise PlatformError("PARSER_RESPONSE_INVALID", "Parser binding is unrelated", 502)
                response = await self.manager.call(
                    "execute",
                    {
                        "spec": spec,
                        "dispatch_id": str(handle["dispatch_id"]),
                        "language": "python",
                        "code": PARSER_COMMAND,
                        "timeout_seconds": PARSER_TIMEOUT,
                    },
                )
                await asyncio.to_thread(self.jobs.parsed, handle, response)
                response = await self.manager.call("finalize", {"spec": spec})
                await asyncio.to_thread(self.jobs.stage, handle, response)
                await self._ack(handle, spec)
                handle = {**handle, "phase": "embed", "cleanup_state": "confirmed", "export_acknowledged": True}
            await self.embedder.index(handle)
            return await asyncio.to_thread(self.jobs.finish, handle)

        work = asyncio.create_task(drive())
        try:
            done, _ = await asyncio.wait({pulse, work}, return_when=asyncio.FIRST_COMPLETED)
            if work in done:
                return await work
            if pulse in done:
                await pulse
            return await work
        except BaseException as exc:
            work.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await work
            code = exc.code if isinstance(exc, PlatformError) else "INGESTION_UNCONFIRMED"
            latest = await asyncio.shield(asyncio.to_thread(self.jobs.fail, handle, code))
            await asyncio.shield(self._cleanup(latest))
            if isinstance(exc, asyncio.CancelledError):
                raise
            return {"id": handle["id"], "state": "failed", "error_code": code}
        finally:
            pulse.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await pulse

    async def serve(self):
        while not self.stopping.is_set():
            try:
                result = await self.run_once()
                await asyncio.to_thread(self.jobs.knowledge.purge, self.org_id)
            except Exception:
                logger.warning("Knowledge ingestion deferred; durable state and cleanup will be rechecked")
                result = None
            if result is None:
                try:
                    await asyncio.wait_for(self.stopping.wait(), timeout=1)
                except TimeoutError:
                    pass
