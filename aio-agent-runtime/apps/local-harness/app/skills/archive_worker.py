"""Independent archive import worker; parsing happens only through an authenticated Manager."""

import asyncio
from contextlib import suppress
import logging

from ..platform_errors import PlatformError

logger = logging.getLogger(__name__)


class SkillArchiveWorker:
    def __init__(self, jobs, manager, org, worker_id, *, stopping=None):
        self.jobs, self.manager, self.org, self.worker_id = jobs, manager, org, worker_id
        self.stopping = stopping or asyncio.Event()

    async def pulse(self, handle):
        while True:
            await asyncio.sleep(min(5, self.jobs.settings.lease_seconds / 3))
            await asyncio.to_thread(self.jobs.pulse, handle)

    async def cleanup(self, handle):
        if handle.get("spec") is not None:
            stopped = await self.manager.call("stop", {"spec": handle["spec"]})
            await asyncio.to_thread(self.jobs.stopped, handle, stopped)
            ack = await self.manager.call("acknowledge", {"spec": handle["spec"]})
            await asyncio.to_thread(self.jobs.acknowledged, handle, ack)
        return await asyncio.to_thread(self.jobs.finish, handle)

    async def run_once(self):
        await asyncio.to_thread(self.jobs.service.gc, self.org)
        recovery = await asyncio.to_thread(self.jobs.recover, self.org, self.worker_id)
        if recovery:
            return await self.cleanup(recovery)
        if getattr(self.jobs.settings, "skill_import_profile", None) is None:
            return None
        handle = await asyncio.to_thread(self.jobs.claim, self.org, self.worker_id)
        if handle is None:
            return None
        heartbeat = asyncio.create_task(self.pulse(handle))
        failure = None
        try:
            handle = await asyncio.to_thread(self.jobs.prepare, handle)
            spec, command = handle["spec"], handle["command"]
            ready = await self.manager.call("ensure", {"spec": spec})
            if (
                ready.get("state") != "ready"
                or ready.get("binding_id") != spec["binding_id"]
                or ready.get("spec_digest") != handle["spec_digest"]
            ):
                raise PlatformError("MANAGER_RESPONSE_INVALID", "Archive scanner allocation was not confirmed", 502)
            result = await self.manager.call("execute", {"spec": spec, "language": "python", **command})
            if heartbeat.done():
                await heartbeat
            await asyncio.to_thread(self.jobs.scanned, handle, result)
            exported = await self.manager.call("finalize", {"spec": spec})
            await asyncio.to_thread(self.jobs.candidate, handle, exported)
        except PlatformError as error:
            failure = error.code
        except asyncio.CancelledError:
            failure = "SKILL_IMPORT_INTERRUPTED"
            raise
        except Exception:
            failure = "SKILL_IMPORT_UNCONFIRMED"
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await heartbeat
            # The archive or an uncertain live cell never becomes an executable
            # draft merely because a request/worker disappeared.
            current = await asyncio.shield(asyncio.to_thread(self.jobs.stopping, handle, failure))
            # prepare may have committed a spec even if its thread response was
            # lost. Use the authoritative stopping snapshot, not stale local data.
            handle = {**handle, **current}
            result = await asyncio.shield(self.cleanup(handle))
        return result

    async def serve(self):
        while not self.stopping.is_set():
            try:
                result = await self.run_once()
            except Exception:
                logger.warning("Skill archive import deferred; durable cleanup state will be rechecked")
                result = None
            if result is None:
                try:
                    await asyncio.wait_for(self.stopping.wait(), timeout=1)
                except TimeoutError:
                    pass
