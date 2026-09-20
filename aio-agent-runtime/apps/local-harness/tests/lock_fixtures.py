"""Deterministic, real-PostgreSQL lock-order assertions for lifecycle callbacks."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import queue
import threading
import time

from sqlalchemy import select, text

from app.db import schema as s


def resource_before_run(t, monkeypatch, run_id, callback):
    return _lock_prefix(t, monkeypatch, run_id, callback, organization=False)


def organization_before_resource(t, monkeypatch, run_id, callback):
    return _lock_prefix(t, monkeypatch, run_id, callback, organization=True)


def _lock_prefix(t, monkeypatch, run_id, callback, *, organization):
    backend = queue.Queue(maxsize=1)
    original_scope = t["db"].scoped

    @contextmanager
    def observed_scope(org, user):
        with original_scope(org, user) as connection:
            if threading.current_thread().name.startswith("lifecycle-receipt"):
                backend.put(connection.connection.driver_connection.info.backend_pid)
            yield connection

    monkeypatch.setattr(t["db"], "scoped", observed_scope)
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lifecycle-receipt")
    try:
        with t["db"].transaction(t["alice"]) as holder:
            if organization:
                predecessor = select(s.organizations.c.id).where(s.organizations.c.id == t["org"])
            else:
                predecessor = select(s.resources.c.id).where(
                    s.resources.c.org_id == t["org"], s.resources.c.id == run_id
                )
            holder.execute(predecessor.with_for_update()).one()
            receipt = pool.submit(callback)
            pid = backend.get(timeout=3)
            deadline = time.monotonic() + 2
            with t["admin"].connect() as observer:
                while True:
                    observer.execute(text("SELECT pg_stat_clear_snapshot()"))
                    waiting = observer.execute(
                        text("SELECT wait_event_type FROM pg_stat_activity WHERE pid=:pid"), {"pid": pid}
                    ).scalar_one()
                    if waiting == "Lock":
                        break
                    if receipt.done():
                        receipt.result()
                        raise AssertionError("Receipt bypassed the held predecessor lock")
                    if time.monotonic() >= deadline:
                        raise AssertionError("Receipt did not reach an observable lock wait")
                    time.sleep(0.01)
            # Waiting on an earlier lock must not own the successor already.
            successor = s.resources if organization else s.runs
            holder.execute(
                select(successor.c.id)
                .where(successor.c.org_id == t["org"], successor.c.id == run_id)
                .with_for_update(nowait=True)
            ).one()
        return receipt.result(timeout=5)
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
