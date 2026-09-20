"""Verification diagnostics must not weaken production exception redaction."""

import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts/platform"))
from preview_diagnostics import diagnostic_worker, exception_metadata, observe_manager_errors


def test_preview_exception_evidence_excludes_values_sql_and_locals():
    secret = "synthetic-private-credential-and-document-text"
    try:
        raise ValueError(secret)
    except ValueError as error:
        error.statement = secret
        error.orig = SimpleNamespace(sqlstate="40P01")
        evidence = exception_metadata(error)
    assert evidence["type"] == "ValueError" and evidence["sqlstate"] == "40P01"
    assert evidence["frames"][-1]["function"] == "test_preview_exception_evidence_excludes_values_sql_and_locals"
    assert secret not in json.dumps(evidence)
    malformed = ValueError(secret)
    malformed.orig = SimpleNamespace(sqlstate=secret)
    assert exception_metadata(malformed)["sqlstate"] is None


def test_preview_worker_observer_preserves_original_failure_and_bounds_records():
    error = ValueError("private-body")

    class Worker:
        async def _drive(self, handle):
            raise error

        async def _db(self, method, *args, **kwargs):
            raise error

    records = []
    worker = diagnostic_worker(Worker, records)()
    handle = SimpleNamespace(run_id=uuid4())

    async def exercise():
        with pytest.raises(ValueError) as caught:
            await worker._drive(handle)
        assert caught.value is error and records[0]["run_id"] == str(handle.run_id)
        for _ in range(105):
            with pytest.raises(ValueError):
                await worker._db(None)

    asyncio.run(exercise())
    assert len(records) == 100 and "private-body" not in json.dumps(records)


def test_preview_worker_observer_does_not_intercept_cancellation():
    class Worker:
        async def _drive(self, handle):
            raise asyncio.CancelledError()

    records = []
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(diagnostic_worker(Worker, records)()._drive(SimpleNamespace(run_id=uuid4())))
    assert records == []


def test_preview_manager_observer_preserves_redacted_response_and_bounds_evidence():
    from docker.errors import APIError, DockerException
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient

    secret = "synthetic-private-docker-error-body"
    error = APIError(secret, response=SimpleNamespace(status_code=500), explanation=secret)
    app = FastAPI()

    @app.exception_handler(DockerException)
    async def original(request, raised):
        assert raised is error
        return JSONResponse({"error": "RUNTIME_UNAVAILABLE"}, status_code=503)

    @app.get("/test")
    def failure():
        raise error

    records = []
    assert observe_manager_errors(app, records) is app
    with TestClient(app) as client:
        response = client.get("/test")
        assert response.status_code == 503 and response.json() == {"error": "RUNTIME_UNAVAILABLE"}
        assert records[0]["http_status"] == 500 and records[0]["route"] == "failure"
        assert secret not in json.dumps(records)
        records.extend({} for _ in range(99))
        assert client.get("/test").status_code == 503 and len(records) == 100


def test_failed_http_verification_replaces_stale_success_with_current_redacted_evidence(tmp_path, monkeypatch):
    import time
    import verify_workbench_http as verification

    report_path = tmp_path / "var/verification/workbench-http.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text('{"status":"passed","verification_id":"preview-old"}', encoding="utf-8")
    info = tmp_path / "info.json"
    info.write_text(
        json.dumps(
            {
                "state": "running",
                "verification_id": "preview-current",
                "url": "http://127.0.0.1:29901",
                "identity_url": "http://127.0.0.1:29902",
                "org_id": str(uuid4()),
                "expires_at_epoch": time.time() + 60,
            }
        ),
        encoding="utf-8",
    )
    closed = []

    class Client:
        def __init__(self, **kwargs):
            current = json.loads(report_path.read_text(encoding="utf-8"))
            assert current["status"] == "running" and current["verification_id"] == "preview-current"

        def get(self, path):
            return SimpleNamespace(json=lambda: {"organization_id": "wrong-synthetic-org"})

        def close(self):
            closed.append(True)

    monkeypatch.setattr(verification, "ROOT", tmp_path)
    monkeypatch.setattr(verification.httpx, "Client", Client)
    monkeypatch.setattr(sys, "argv", ["verify_workbench_http.py", "--info", str(info)])
    with pytest.raises(AssertionError, match="fixture_org_alice"):
        verification.main()
    result = json.loads(report_path.read_text(encoding="utf-8"))
    assert result["status"] == "failed" and result["verification_id"] == "preview-current"
    assert result["failure_type"] == "AssertionError" and result["failed_check"] == "fixture_org_alice"
    assert result["checks"] == [] and closed == [True]
