"""Content-free exception evidence for the finite, synthetic verification stack only."""

from collections import deque
from pathlib import Path
import re
import traceback


ROOT = Path(__file__).resolve().parents[2]


def exception_metadata(error: Exception) -> dict:
    """Never format the exception, SQL, frame source or locals: all may contain secrets."""
    frames = deque(maxlen=12)
    for frame, line in traceback.walk_tb(error.__traceback__):
        # Loaded control-module filenames are absolute. Do not stat/resolve a
        # filesystem path for each frame, or inspect dynamically generated code.
        path = Path(frame.f_code.co_filename)
        if path.is_absolute() and path.is_relative_to(ROOT) and ".venv" not in path.parts:
            frames.append({"file": path.relative_to(ROOT).as_posix(), "function": frame.f_code.co_name, "line": line})
    sqlstate = getattr(getattr(error, "orig", None), "sqlstate", None)
    status = getattr(getattr(error, "response", None), "status_code", None)
    return {
        "type": type(error).__name__,
        "sqlstate": sqlstate if isinstance(sqlstate, str) and re.fullmatch(r"[0-9A-Z]{5}", sqlstate) else None,
        "http_status": status if type(status) is int and 100 <= status <= 599 else None,
        "frames": list(frames),
    }


def diagnostic_worker(worker_class, records):
    """Wrap the real Worker without changing its failure, cancellation or retry behavior."""

    class DiagnosticWorker(worker_class):
        async def _drive(self, handle):
            try:
                return await super()._drive(handle)
            except Exception as error:
                if len(records) < 100:
                    records.append({"run_id": str(handle.run_id), "stage": "drive", **exception_metadata(error)})
                raise

        async def _db(self, method, *args, **kwargs):
            try:
                return await super()._db(method, *args, **kwargs)
            except Exception as error:
                if len(records) < 100:
                    records.append({"stage": "database", **exception_metadata(error)})
                raise

    return DiagnosticWorker


def observe_manager_errors(app, records):
    """Keep the real Docker error handler and response; only add content-free test evidence."""
    from docker.errors import DockerException

    original = app.exception_handlers[DockerException]

    @app.exception_handler(DockerException)
    async def observed(request, error):
        if len(records) < 100:
            route = request.scope.get("route")
            records.append({"stage": "manager", "route": getattr(route, "name", None), **exception_metadata(error)})
        return await original(request, error)

    return app
