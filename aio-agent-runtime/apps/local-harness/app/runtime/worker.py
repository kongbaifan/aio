"""Independent durable Worker, never coupled to an HTTP response lifetime."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from ..platform_errors import PlatformError
from .actions import canonical_digest
from .contracts import DispatchPermit, ModelTurn, NotDispatched, WorkHandle
from .execution import ExecutionStore


class ToolDriver(Protocol):
    async def execute(self, permit: DispatchPermit): ...


class ToolDrivers:
    """Only code-registered drivers; never import/exec a driver name supplied by a model."""

    def __init__(self, drivers: dict[str, ToolDriver] | None = None):
        self._drivers = dict(drivers or {})

    def get(self, name: str) -> ToolDriver:
        if name not in self._drivers:
            raise NotDispatched("TOOL_EXECUTOR_UNAVAILABLE", "An approved executor for this tool is not installed", 503)
        return self._drivers[name]

    async def finalize(self, handle):
        for driver in {id(d): d for d in self._drivers.values()}.values():
            callback = getattr(driver, "finalize", None)
            if callback:
                await callback(handle)

    async def cleanup(self, handle):
        for driver in {id(d): d for d in self._drivers.values()}.values():
            callback = getattr(driver, "cleanup", None)
            if callback:
                await callback(handle)

    async def suspend(self, handle):
        for driver in {id(d): d for d in self._drivers.values()}.values():
            callback = getattr(driver, "suspend", None)
            if callback:
                await callback(handle)


class DurableWorker:
    def __init__(
        self, store: ExecutionStore, org_id: UUID, worker_id: str, model_factory, drivers: ToolDrivers | None = None
    ):
        self.store, self.org_id, self.worker_id = store, org_id, worker_id
        self.models, self.drivers = model_factory, drivers or ToolDrivers()
        self.stopping = asyncio.Event()

    async def _db(self, method, *args, **kwargs):
        return await asyncio.to_thread(method, *args, **kwargs)

    async def run_once(self) -> dict | None:
        await self._db(self.store.recover_due, self.org_id)
        claimed = await self._db(self.store.platform.claim_next, self.org_id, self.worker_id)
        if claimed is None:
            return None
        try:
            handle = await self._db(self.store.handle_for_claim, claimed, self.worker_id)
        except PlatformError as exc:
            # Safety-only abort can operate after membership revocation; it cannot execute user actions.
            from ..auth.principal import Principal

            handle = WorkHandle(
                Principal(self.org_id, claimed["actor_id"], 0, service_actor_id=self.worker_id),
                claimed["id"],
                claimed["generation"],
                self.worker_id,
                claimed["deadline_at"],
            )
            return await self._db(self.store.abort, handle, exc.code)
        return await self.run_handle(handle)

    async def run_handle(self, handle: WorkHandle) -> dict:
        async def heartbeat():
            while True:
                await asyncio.sleep(max(1, self.store.settings.lease_seconds / 3))
                await self._db(self.store.pulse, handle)

        drive = asyncio.create_task(self._drive(handle))
        pulse = asyncio.create_task(heartbeat())
        try:
            seconds = max(0, (handle.deadline - datetime.now(timezone.utc)).total_seconds())
            async with asyncio.timeout(seconds):
                done, _ = await asyncio.wait({drive, pulse}, return_when=asyncio.FIRST_COMPLETED)
                if drive in done:
                    result = await drive
                    if result.get("state") != "waiting_approval":
                        await self.drivers.cleanup(handle)
                    return result
                await pulse
                raise PlatformError("WORKER_HEARTBEAT_STOPPED", "Worker heartbeat stopped unexpectedly", 503)
        except asyncio.TimeoutError:
            reason = "RUN_DEADLINE_EXCEEDED"
        except asyncio.CancelledError:
            reason = "WORKER_STOPPED"
        except PlatformError as exc:
            reason = exc.code
        except Exception:
            # Provider/driver exceptions may contain credentials; never persist their raw body or traceback.
            reason = "EXECUTION_FAILED"
        finally:
            drive.cancel()
            pulse.cancel()
            await asyncio.gather(drive, pulse, return_exceptions=True)
        try:
            await self.drivers.cleanup(handle)
        except Exception:
            pass  # Lease remains pending; manager/PG reapers must confirm cleanup, never mark success here.
        try:
            return await self._db(self.store.abort, handle, reason)
        except (PlatformError, SQLAlchemyError):
            # A superseding generation or persistence outage must not be overwritten by this worker.
            return {"run_id": handle.run_id, "state": "requires_lifecycle_reconciliation", "reason_code": reason}

    async def _suspend(self, handle):
        await self.drivers.suspend(handle)
        state = await self._db(self.store.suspend_approval, handle)
        return {"run_id": handle.run_id, "state": state} if state else None

    async def _drive(self, handle: WorkHandle) -> dict:
        while True:
            loaded = await self._db(self.store.load, handle)
            run, cp = loaded["run"], loaded["checkpoint"]
            if loaded["engine"] != "local-harness-v2":
                raise PlatformError("ENGINE_UNAVAILABLE", "This agent engine is not installed", 409)
            mode = run["input"].get("mode", "single")
            if mode not in {"single", "team"}:
                raise PlatformError("ENGINE_MODE_UNAVAILABLE", "Unknown engine mode", 409)
            if run["state"] == "waiting_approval":
                suspended = await self._suspend(handle)
                if suspended:
                    return suspended
                continue
            if mode == "team" and await self._db(self.store.advance_team, handle, run["checkpoint_seq"]):
                continue
            if cp.phase == "final":
                await self.drivers.finalize(handle)
                return await self._db(self.store.finish, handle, run["checkpoint_seq"])
            max_rounds = loaded["manifest"].get("max_rounds", 8)
            if type(max_rounds) is not int or not 1 <= max_rounds <= 32:
                raise PlatformError("INVALID_MANIFEST", "Agent round budget is invalid", 409)
            if cp.phase == "model":
                if cp.round >= max_rounds:
                    raise PlatformError("AGENT_ROUND_LIMIT", "Agent exceeded its allowed model rounds", 409)
                definition = await self._db(self.store.model_definition, handle)
                tools = await self._db(self.store.tools_for_model, handle)
                model = self.models.create(definition)
                try:
                    messages = [dict(item) for item in cp.messages]
                    digest = canonical_digest(
                        "aio-model-request-v1",
                        {"model_id": str(definition["id"]), "messages": messages, "tools": tools},
                    )
                    call = await self._db(
                        self.store.prepare_model_call, handle, run["checkpoint_seq"], digest, model.max_charge
                    )
                    await self._db(self.store.start_model_call, handle, call["id"])
                    turn = None
                    pending_text = ""
                    last_emit = asyncio.get_running_loop().time()
                    async for item in model.stream(messages, tools):
                        if isinstance(item, ModelTurn):
                            if turn is not None:
                                raise PlatformError(
                                    "MODEL_PROTOCOL_INVALID", "Model emitted more than one final turn", 502
                                )
                            turn = item
                        elif isinstance(item, str) and turn is None:
                            pending_text += item
                            now = asyncio.get_running_loop().time()
                            while len(pending_text.encode("utf-8")) >= 16384:
                                # Character bound is conservative for UTF-8 and preserves Unicode characters.
                                fragment, pending_text = pending_text[:4096], pending_text[4096:]
                                await self._db(self.store.append_delta, handle, str(call["id"]), fragment)
                            if pending_text and now - last_emit >= 0.15:
                                await self._db(self.store.append_delta, handle, str(call["id"]), pending_text)
                                pending_text, last_emit = "", now
                        else:
                            raise PlatformError("MODEL_PROTOCOL_INVALID", "Model returned an invalid stream item", 502)
                    if turn is None:
                        raise PlatformError("MODEL_STREAM_INCOMPLETE", "Model stream has no committed turn", 502)
                    if pending_text:
                        await self._db(self.store.append_delta, handle, str(call["id"]), pending_text)
                    await self._db(
                        self.store.complete_model_call,
                        handle,
                        run["checkpoint_seq"],
                        call["id"],
                        turn,
                        model.charge(turn),
                    )
                finally:
                    await model.close()
            else:
                invocation = await self._db(self.store.plan_tool, handle, run["checkpoint_seq"])
                if invocation["state"] == "waiting_approval":
                    suspended = await self._suspend(handle)
                    if suspended:
                        return suspended
                    continue
                # Resolve the installed driver BEFORE consuming an irreversible dispatch permit.
                entry = next(
                    (
                        entry
                        for entry in loaded["manifest"].get("tools", [])
                        if entry["name"] == cp.pending_calls[cp.next_tool].name
                    ),
                    None,
                )
                if entry is None:
                    raise PlatformError("TOOL_NOT_ALLOWED", "Tool is not in the fixed manifest", 403)
                driver = self.drivers.get(entry.get("driver", "")) if invocation["state"] != "denied" else None
                dispatch = await self._db(self.store.prepare_dispatch, handle, run["checkpoint_seq"], invocation["id"])
                if dispatch["state"] == "denied":
                    continue
                if driver is None:
                    raise PlatformError("TOOL_EXECUTOR_UNAVAILABLE", "Tool driver is unavailable", 503)
                permit = await self._db(self.store.consume_dispatch, handle, dispatch["id"])
                try:
                    seconds = max(0, (permit.not_after - datetime.now(timezone.utc)).total_seconds())
                    async with asyncio.timeout(seconds):
                        output = await driver.execute(permit)
                except NotDispatched as exc:
                    await self._db(
                        self.store.complete_dispatch,
                        handle,
                        run["checkpoint_seq"],
                        dispatch["id"],
                        {"error": exc.code},
                        outcome="not_sent",
                    )
                    continue
                # Any other error after consumption is uncertain, even if a driver returned no response.
                await self._db(self.store.complete_dispatch, handle, run["checkpoint_seq"], dispatch["id"], output)

    async def serve(self, poll_seconds: float = 1.0):
        while not self.stopping.is_set():
            try:
                result = await self.run_once()
            except (PlatformError, SQLAlchemyError):
                result = None
            if result is None:
                try:
                    await asyncio.wait_for(self.stopping.wait(), timeout=poll_seconds)
                except asyncio.TimeoutError:
                    pass
