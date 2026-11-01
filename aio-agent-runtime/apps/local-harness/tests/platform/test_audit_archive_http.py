"""HTTPS collector sink and worker wiring for the audit archive relay.

Contract tests use httpx.MockTransport; the PG tests deliver to a real loopback HTTP collector
that dedupes on Idempotency-Key, as the collector contract requires. No SIEM is deployed.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text, update

from app.db import schema as s
from app.observability import scrub
from app.observability.archive import ArchiveDeliveryError, ArchiveRecord
from app.observability.archive_http import HttpArchiveSink
from app.platform_errors import PlatformConfigurationError
from app.platform_settings import DeploymentMode, WorkerSettings
import run_worker
from test_audit_relay import entries, facts, make_due

TOKEN = "archive-collector-token-for-tests-0001"
MARKER = "synthetic-collector-body-marker"


def worker_env(platform_env, **extra):
    return {
        "HARNESS_MODE": "platform-test",
        "PLATFORM_DATABASE_URL": platform_env["PLATFORM_DATABASE_URL"],
        "PLATFORM_WORKER_ORG_ID": str(uuid4()),
        "PLATFORM_WORKER_ID": "test-worker",
        "PLATFORM_MODEL_ALLOWED_ORIGINS": "https://model.example.test",
        "PLATFORM_MODEL_SECRET_ENV_ALLOWLIST": "AIO_SYNTHETIC_MODEL_KEY",
        **extra,
    }


def production_env(platform_env, **extra):
    url = "postgresql+psycopg://runtime:test-only-password@db.example.test:5432/platform?sslmode=verify-full"
    return worker_env(platform_env, HARNESS_MODE="platform-production", PLATFORM_DATABASE_URL=url, **extra)


def record():
    return ArchiveRecord(
        org_id=uuid4(), audit_id=uuid4(), actor_id=uuid4(), service_actor_id=None, run_id=None,
        action="project.create", resource_id=uuid4(), resource_kind=None, outcome="created", decision=None,
        reason_code=None, policy_revision=None, subject_revision=None, risk_class=None, trace_id=None,
        metadata_schema="project.create:v1", metadata={}, created_at=datetime.now(timezone.utc),
    )


def sink_with(handler):
    seen = []

    def wrapped(request):
        seen.append(request)
        return handler(request)

    return HttpArchiveSink("https://archive.example.test/v1/audit", TOKEN,
                           client=httpx.AsyncClient(transport=httpx.MockTransport(wrapped))), seen


def test_production_worker_refuses_to_start_without_a_collector(platform_env):
    with pytest.raises(PlatformConfigurationError, match="audit archive"):
        WorkerSettings.from_env(production_env(platform_env))
    settings = WorkerSettings.from_env(production_env(
        platform_env, PLATFORM_AUDIT_ARCHIVE_URL="https://archive.example.test/v1/audit",
        PLATFORM_AUDIT_ARCHIVE_TOKEN=TOKEN,
    ))
    assert settings.audit_archive_url == "https://archive.example.test/v1/audit"
    assert TOKEN not in repr(settings)


def test_test_mode_may_run_without_a_collector_and_allows_only_loopback_http(platform_env):
    assert WorkerSettings.from_env(worker_env(platform_env)).audit_archive_url is None
    local = WorkerSettings.from_env(worker_env(
        platform_env, PLATFORM_AUDIT_ARCHIVE_URL="http://127.0.0.1:9/audit", PLATFORM_AUDIT_ARCHIVE_TOKEN=TOKEN
    ))
    assert local.audit_archive_url == "http://127.0.0.1:9/audit"


@pytest.mark.parametrize("change", [
    {"PLATFORM_AUDIT_ARCHIVE_URL": "https://archive.example.test/v1/audit"},  # no credential
    {"PLATFORM_AUDIT_ARCHIVE_TOKEN": TOKEN},  # credential without collector
    {"PLATFORM_AUDIT_ARCHIVE_URL": "https://archive.example.test/v1/audit", "PLATFORM_AUDIT_ARCHIVE_TOKEN": "short"},
    {"PLATFORM_AUDIT_ARCHIVE_URL": "http://archive.example.test/v1/audit", "PLATFORM_AUDIT_ARCHIVE_TOKEN": TOKEN},
    {"PLATFORM_AUDIT_ARCHIVE_URL": "https://u:p@archive.example.test/x", "PLATFORM_AUDIT_ARCHIVE_TOKEN": TOKEN},
    {"PLATFORM_AUDIT_ARCHIVE_URL": "https://archive.example.test/x?k=v", "PLATFORM_AUDIT_ARCHIVE_TOKEN": TOKEN},
])
def test_collector_configuration_is_strict(platform_env, change):
    with pytest.raises(PlatformConfigurationError):
        WorkerSettings.from_env(worker_env(platform_env, **change))


def test_collector_credential_must_differ_from_other_service_credentials(platform_env):
    with pytest.raises(PlatformConfigurationError, match="own explicit"):
        WorkerSettings.from_env(worker_env(
            platform_env, PLATFORM_CONNECTOR_URL="https://gateway.example.test", PLATFORM_CONNECTOR_TOKEN=TOKEN,
            PLATFORM_AUDIT_ARCHIVE_URL="https://archive.example.test/v1/audit", PLATFORM_AUDIT_ARCHIVE_TOKEN=TOKEN,
        ))


def test_collector_credential_is_registered_as_process_material(platform_env):
    settings = WorkerSettings.from_env(worker_env(
        platform_env, PLATFORM_AUDIT_ARCHIVE_URL="https://archive.example.test/v1/audit",
        PLATFORM_AUDIT_ARCHIVE_TOKEN=TOKEN,
    ))
    try:
        scrub.register_process_secrets(settings)
        with pytest.raises(scrub.SensitiveLeak):
            scrub.assert_clean("prefix " + TOKEN)
    finally:
        scrub.forget_material(TOKEN)


@pytest.mark.asyncio
async def test_sink_posts_one_record_with_idempotency_key_and_bearer():
    sink, seen = sink_with(lambda request: httpx.Response(201))
    item = record()
    await sink.deliver(item)
    (request,) = seen
    assert request.method == "POST" and str(request.url) == "https://archive.example.test/v1/audit"
    assert request.headers["Idempotency-Key"] == item.idempotency_key
    assert request.headers["Authorization"] == "Bearer " + TOKEN
    assert request.headers["Content-Type"] == "application/json"
    assert ArchiveRecord.model_validate_json(request.content) == item


@pytest.mark.asyncio
async def test_already_stored_conflict_counts_as_delivered():
    sink, _ = sink_with(lambda request: httpx.Response(409, text=MARKER))
    await sink.deliver(record())


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "code"), [
    (500, "ARCHIVE_UNAVAILABLE"), (503, "ARCHIVE_UNAVAILABLE"), (429, "ARCHIVE_UNAVAILABLE"),
    (408, "ARCHIVE_UNAVAILABLE"), (400, "ARCHIVE_REJECTED"), (401, "ARCHIVE_REJECTED"),
    (403, "ARCHIVE_REJECTED"), (413, "ARCHIVE_REJECTED"), (302, "ARCHIVE_REJECTED"),
])
async def test_failure_statuses_map_to_stable_codes_without_body_text(status, code):
    headers = {"Location": "https://elsewhere.example.test/"} if status == 302 else {}
    sink, seen = sink_with(lambda request: httpx.Response(status, text=MARKER, headers=headers))
    with pytest.raises(ArchiveDeliveryError) as raised:
        await sink.deliver(record())
    assert raised.value.code == code and MARKER not in str(raised.value)
    assert len(seen) == 1  # a redirect is never followed


@pytest.mark.asyncio
@pytest.mark.parametrize(("error", "code"), [
    (httpx.ReadTimeout(MARKER), "ARCHIVE_TIMEOUT"), (httpx.ConnectTimeout(MARKER), "ARCHIVE_TIMEOUT"),
    (httpx.ConnectError(MARKER), "ARCHIVE_UNAVAILABLE"), (httpx.RemoteProtocolError(MARKER), "ARCHIVE_UNAVAILABLE"),
])
async def test_transport_errors_map_to_stable_codes_without_exception_text(error, code):
    def fail(request):
        raise error

    sink, _ = sink_with(fail)
    with pytest.raises(ArchiveDeliveryError) as raised:
        await sink.deliver(record())
    assert raised.value.code == code and MARKER not in str(raised.value)
    assert raised.value.__cause__ is None and raised.value.__suppress_context__


@pytest.mark.asyncio
async def test_owned_client_does_not_follow_redirects_or_read_proxy_environment():
    sink = HttpArchiveSink("https://archive.example.test/v1/audit", TOKEN)
    try:
        assert sink.client.follow_redirects is False and sink.client._trust_env is False
    finally:
        await sink.close()
    assert sink.client.is_closed


def test_worker_starts_no_relay_without_a_collector(platform_env):
    assert run_worker.audit_relay(object(), WorkerSettings.from_env(worker_env(platform_env))) is None


@pytest.mark.asyncio
async def test_worker_builds_an_org_scoped_relay_with_the_http_sink(platform_env):
    settings = WorkerSettings.from_env(worker_env(
        platform_env, PLATFORM_WORKER_ID="w" * 128,
        PLATFORM_AUDIT_ARCHIVE_URL="https://archive.example.test/v1/audit", PLATFORM_AUDIT_ARCHIVE_TOKEN=TOKEN,
    ))
    relay = run_worker.audit_relay(object(), settings)
    try:
        assert relay.org_id == settings.org_id and isinstance(relay.sink, HttpArchiveSink)
        assert relay.owner == "w" * 110 + "-audit-archive"  # still within the relay's 128-char identity
        assert relay.sink.url == settings.audit_archive_url
    finally:
        await relay.sink.close()


class Collector:
    """Loopback collector honouring the contract: auth, one stored body per Idempotency-Key, 409 on repeat."""

    def __init__(self):
        self.stored, self.requests, self.outage = {}, [], False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                key = self.headers.get("Idempotency-Key")
                owner.requests.append(key)
                if self.headers.get("Authorization") != "Bearer " + TOKEN:
                    status = 401
                elif owner.outage:
                    status = 503
                elif key in owner.stored:
                    status = 409
                else:
                    owner.stored[key] = json.loads(body)
                    status = 201
                self.send_response(status)
                self.send_header("Content-Length", str(len(MARKER)))
                self.end_headers()
                self.wfile.write(MARKER.encode())

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1/audit"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def collector():
    server = Collector()
    yield server
    server.close()


def live_relay(t, platform_env, collector, token=TOKEN):
    settings = WorkerSettings.from_env(worker_env(
        platform_env, PLATFORM_WORKER_ORG_ID=str(t["org"]), PLATFORM_WORKER_ID="it-worker",
        PLATFORM_AUDIT_ARCHIVE_URL=collector.url, PLATFORM_AUDIT_ARCHIVE_TOKEN=token,
    ))
    assert settings.mode is DeploymentMode.TEST
    return run_worker.audit_relay(t["db"], settings)


def delivered_keys(t):
    return {f"{t['org']}:{e['aggregate_id']}" for e in entries(t) if e["delivered_at"]}


def test_worker_relay_delivers_through_a_real_collector_outage_and_replay(tenant, platform_env, collector):
    t = tenant
    t["service"].create_project(t["alice"], "Synthetic confidential project name")
    relay = live_relay(t, platform_env, collector)
    try:
        collector.outage = True
        result = asyncio.run(relay.run_once())
        assert result["failed"] == result["claimed"] == len(facts(t)) and not collector.stored
        assert {e["last_error_code"] for e in entries(t)} == {"ARCHIVE_UNAVAILABLE"}
        assert MARKER not in json.dumps(entries(t), default=str)

        collector.outage = False
        make_due(t)
        assert asyncio.run(relay.run_once())["delivered"] == len(facts(t))
        assert set(collector.stored) == delivered_keys(t) == {f"{t['org']}:{f}" for f in facts(t)}
        assert all(ArchiveRecord.model_validate(body).idempotency_key == key for key, body in collector.stored.items())
        assert "confidential" not in json.dumps(collector.stored)

        # Delivered but the finish was lost: the resend gets 409 and still counts as delivered, stored once.
        snapshot = dict(collector.stored)
        with t["admin"].begin() as c:
            c.execute(update(s.outbox).where(s.outbox.c.org_id == t["org"]).values(
                delivered_at=None, next_attempt_at=text("clock_timestamp() - interval '1 second'")))
        assert asyncio.run(relay.run_once())["delivered"] == len(facts(t))
        assert collector.stored == snapshot and len(collector.requests) == 3 * len(facts(t))
        assert relay.backlog()["pending"] == 0
    finally:
        asyncio.run(relay.sink.close())


def test_rejected_collector_credential_keeps_facts_pending_with_a_stable_code(tenant, platform_env, collector):
    t = tenant
    relay = live_relay(t, platform_env, collector, token="wrong-archive-collector-token-000001")
    try:
        assert asyncio.run(relay.run_once())["failed"] == len(facts(t))
        assert {e["last_error_code"] for e in entries(t)} == {"ARCHIVE_REJECTED"}
        assert not collector.stored and relay.backlog()["pending"] == len(facts(t))
    finally:
        asyncio.run(relay.sink.close())


def test_worker_relay_serves_until_drained_and_stops_with_the_worker(tenant, platform_env, collector):
    t = tenant
    for index in range(3):
        t["service"].create_project(t["alice"], f"Serve fixture {index}")
    expected = {f"{t['org']}:{f}" for f in facts(t)}

    async def scenario():
        relay = live_relay(t, platform_env, collector)
        stopping = asyncio.Event()
        task = asyncio.create_task(relay.serve(stopping, poll_seconds=0.1))
        try:
            for _ in range(100):
                if set(collector.stored) == expected:
                    break
                await asyncio.sleep(0.05)
            stopping.set()
            await asyncio.wait_for(task, 5)
        finally:
            await relay.sink.close()

    asyncio.run(scenario())
    assert set(collector.stored) == expected == delivered_keys(t)
