"""Independent bounded Skill-validation queue; uses authenticated remote manager only."""

import asyncio
import logging
from contextlib import suppress

from ..platform_errors import PlatformError
from ..runtime.actions import canonical_digest

logger = logging.getLogger(__name__)


class SkillValidationWorker:
    def __init__(self, store, manager, org_id, worker_id, *, stopping=None):
        self.store, self.manager, self.org_id, self.worker_id = store, manager, org_id, worker_id
        self.stopping = stopping or asyncio.Event()

    async def _pulse(self, handle):
        while True:
            await asyncio.sleep(min(5, self.store.settings.lease_seconds / 3))
            await asyncio.to_thread(self.store.pulse, handle)

    async def _cleanup(self, handle):
        response = await self.manager.call("stop", {"spec": handle["spec"]})
        return await asyncio.to_thread(self.store.finish, handle, response)

    async def run_once(self):
        recovery = await asyncio.to_thread(self.store.recover_one, self.org_id, self.worker_id)
        if recovery:
            return await self._cleanup(recovery)
        handle = await asyncio.to_thread(self.store.claim, self.org_id, self.worker_id)
        if not handle:
            return None
        pulse = asyncio.create_task(self._pulse(handle))
        failure = None
        try:
            spec = handle["spec"]
            ready = await self.manager.call("ensure", {"spec": spec})
            if (
                ready.get("state") != "ready"
                or ready.get("binding_id") != spec["binding_id"]
                or ready.get("spec_digest") != canonical_digest("aio-cell-spec-v1", spec)
            ):
                raise PlatformError("MANAGER_RESPONSE_INVALID", "Manager returned an unrelated validation cell", 502)
            for index, command in enumerate(handle["commands"]):
                if pulse.done():
                    await pulse
                response = await self.manager.call(
                    "execute",
                    {
                        "spec": spec,
                        "dispatch_id": command["dispatch_id"],
                        "language": "python",
                        "code": command["code"],
                        "timeout_seconds": command["timeout_seconds"],
                    },
                )
                await asyncio.to_thread(self.store.record, handle, index, response)
        except PlatformError as exc:
            failure = exc.code
        except asyncio.CancelledError:
            failure = "VALIDATION_INTERRUPTED"
            raise
        except Exception:
            failure = "VALIDATION_UNCONFIRMED"
        finally:
            pulse.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await pulse
            # Intention is persisted before stop; a lost stop response leaves a durable cleanup blocker.
            await asyncio.shield(asyncio.to_thread(self.store.stopping, handle, failure))
            result = await asyncio.shield(self._cleanup(handle))
        return result

    async def serve(self):
        while not self.stopping.is_set():
            try:
                result = await self.run_once()
            except Exception:
                # Do not log untrusted source or remote response bodies.
                logger.warning("Skill validation deferred; durable state will be rechecked")
                result = None
            if result is None:
                try:
                    await asyncio.wait_for(self.stopping.wait(), timeout=1)
                except TimeoutError:
                    pass
