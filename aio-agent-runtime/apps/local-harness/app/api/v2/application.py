"""Isolated platform entrypoint. It never instantiates the legacy RuntimeContainer."""

from __future__ import annotations

import asyncio
import hmac
import json
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ...auth.oidc import OIDCClient
from ...auth.principal import Principal
from ...auth.service import AuthService, csrf_token
from ...db.engine import Database
from ...platform_errors import PlatformError
from ...platform_settings import PlatformSettings
from ...runtime.service import PlatformService
from ...runtime.execution import ExecutionStore
from ...admin.service import AdminService
from ...admin.routes import register_admin_routes
from ...admin.contracts import Rename
from ...runtime.states import TERMINAL_STATES
from .contracts import ApprovalDecision, ProjectCreate, RunCreate, SessionCreate, RunReconciliation
from .middleware import RequestBoundary
from .contracts import UploadCreate
from ...workspaces.storage import BlobStore
from ...workspaces.service import ArtifactService
from ...execution.coordinator import SandboxCoordinator
from ...skills.service import SkillService
from ...skills.validation import SkillValidationStore
from ...skills.routes import register_skill_routes
from ...skills.archive_service import SkillArchiveService
from ...skills.archive_jobs import SkillArchiveJobs
from ...skills.archive_routes import register_archive_routes
from ...connections.service import ConnectionService
from ...connections.client import ConnectorClient
from ...connections.authority import ConnectorAuthority
from ...connections.routes import register_connection_routes
from ...knowledge.service import KnowledgeService
from ...knowledge.jobs import KnowledgeJobs
from ...knowledge.embedding import EmbeddingStore
from ...knowledge.retrieval import KnowledgeRetrieval
from ...knowledge.routes import register_knowledge_routes


def create_platform_app(
    settings: PlatformSettings,
    *,
    database: Database | None = None,
    oidc_client: OIDCClient | None = None,
    connector_client=None,
) -> FastAPI:
    db = database or Database(settings.database_url)
    auth = AuthService(db, settings)
    service = PlatformService(db, settings)
    admin = AdminService(db, settings)
    execution = ExecutionStore(db, settings)
    artifacts = ArtifactService(db, BlobStore(settings.artifact_root)) if settings.artifact_root else None
    coordinator = SandboxCoordinator(execution, artifacts) if artifacts else None
    skills = SkillService(db, settings)
    skill_validation = SkillValidationStore(db, settings)
    skill_archives = SkillArchiveService(db, settings, artifacts.blobs if artifacts else None)
    skill_import_jobs = SkillArchiveJobs(skill_archives)
    connector = connector_client or (
        ConnectorClient(settings.connector_url, settings.connector_token) if settings.connector_url else None
    )
    connections = ConnectionService(db, settings, connector)
    connector_authority = ConnectorAuthority(execution, connections)
    from ...connections.stdio import StdioAuthority

    stdio_authority = StdioAuthority(connector_authority)
    knowledge = KnowledgeService(db, settings, artifacts.blobs if artifacts else None)
    knowledge_jobs = KnowledgeJobs(db, settings, knowledge)
    embedding_billing = EmbeddingStore(db, settings, knowledge_jobs, execution)
    knowledge_retrieval = KnowledgeRetrieval(
        db, execution
    )  # Browser preview is lexical; model requests live in Worker only.
    oidc = oidc_client or OIDCClient(settings)
    subscriptions: dict[tuple[UUID, UUID], int] = {}

    @asynccontextmanager
    async def lifespan(app):
        try:
            await asyncio.to_thread(db.verify_runtime_role)
            app.state.ready = True
            yield
        finally:
            app.state.ready = False
            await oidc.close()
            if connector and connector_client is None:
                await connector.close()
            if database is None:
                await asyncio.to_thread(db.dispose)

    app = FastAPI(
        title="AIO Enterprise Platform",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.ready = False
    app.state.database = db
    app.state.platform_service = service
    app.state.connection_service = connections
    app.state.knowledge_service = knowledge
    app.add_middleware(
        RequestBoundary,
        max_bytes=settings.max_request_bytes,
        max_upload_bytes=settings.max_upload_bytes,
        control_token=settings.manager_control_token,
        connector_token=settings.connector_control_token,
    )

    def error_response(request: Request, code: str, message: str, status: int, retryable: bool = False):
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "request_id": getattr(request.state, "request_id", ""),
                    "retryable": retryable,
                }
            },
        )

    @app.exception_handler(PlatformError)
    async def platform_error(request: Request, exc: PlatformError):
        return error_response(request, exc.code, exc.message, exc.status, exc.retryable)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        # FastAPI's default includes the rejected input, which may contain credentials.
        return error_response(request, "INVALID_REQUEST", "Request does not match the endpoint contract", 422)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        return error_response(request, "PERSISTENCE_UNAVAILABLE", "Persistent state is unavailable", 503, True)

    async def principal(request: Request) -> Principal:
        token = request.cookies.get(settings.session_cookie)
        identity = await asyncio.to_thread(auth.authenticate, token)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            supplied = request.headers.get("x-csrf-token", "")
            if (
                request.headers.get("origin") != settings.public_origin
                or not supplied
                or not hmac.compare_digest(supplied.encode("utf-8"), csrf_token(token).encode("ascii"))
            ):
                raise PlatformError("CSRF_DENIED", "Request origin or CSRF proof is invalid", 403)
        return identity

    @app.get("/healthz")
    async def health():
        return {"status": "ok", "service": "aio-platform"}

    @app.get("/readyz")
    async def ready(request: Request):
        if not request.app.state.ready:
            raise PlatformError("NOT_READY", "Platform startup checks have not passed", 503)

        def ping():
            with db.bootstrap() as connection:
                connection.execute(text("SELECT 1"))

        await asyncio.to_thread(ping)
        return {"status": "ready"}

    @app.get("/auth/login")
    async def login(org_id: UUID):
        start = await asyncio.to_thread(auth.begin_login, org_id)
        response = RedirectResponse(oidc.authorization_url(start), status_code=303)
        response.set_cookie(
            "__Host-aio_login" if settings.secure_cookies else "aio_login",
            start.binding,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="lax",
            path="/",
            max_age=settings.login_ttl_seconds,
        )
        return response

    @app.get("/auth/callback")
    async def callback(request: Request, state: str, code: str):
        binding_cookie = "__Host-aio_login" if settings.secure_cookies else "aio_login"
        attempt = await asyncio.to_thread(auth.consume_login, state, request.cookies.get(binding_cookie, ""))
        issuer, subject = await oidc.verify_code(code, attempt)
        token, identity = await asyncio.to_thread(auth.create_session, attempt.org_id, issuer, subject)
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            settings.session_cookie,
            token,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="lax",
            path="/",
            max_age=settings.session_ttl_seconds,
        )
        response.delete_cookie(binding_cookie, path="/", secure=settings.secure_cookies, httponly=True, samesite="lax")
        return response

    @app.post("/auth/logout")
    async def logout(identity: Principal = Depends(principal)):
        await asyncio.to_thread(auth.logout, identity)
        response = JSONResponse({"logged_out": True})
        response.delete_cookie(
            settings.session_cookie, path="/", secure=settings.secure_cookies, httponly=True, samesite="lax"
        )
        return response

    @app.get("/api/v2/me")
    async def me(request: Request, identity: Principal = Depends(principal)):
        return {
            **await asyncio.to_thread(admin.me, identity),
            "csrf_token": csrf_token(request.cookies[settings.session_cookie]),
            "capabilities": {
                "file_upload": artifacts is not None,
                "python_compute": bool(settings.sandbox_profiles),
                "mcp": bool(connector and settings.connector_profiles),
                "knowledge": bool(artifacts and settings.manager_url and settings.document_profiles),
                "skill_publishing": bool(settings.manager_url and settings.sandbox_profiles),
                "team": True,
            },
        }

    @app.get("/api/public/login")
    async def login_configuration():
        return {
            "organization_id": settings.login_org_id,
            "organization_label": settings.organization_label,
            "authentication": "enterprise-sso",
        }

    @app.post("/internal/v1/sandbox/authorize")
    async def sandbox_authorize(request: Request, body: dict):
        supplied = request.headers.get("x-manager-token", "")
        if not settings.manager_control_token or not hmac.compare_digest(
            supplied.encode("utf-8"), settings.manager_control_token.encode("ascii")
        ):
            raise PlatformError("UNAUTHORIZED_SERVICE", "Manager identity is required", 401)
        spec = body.get("spec")
        if isinstance(spec, dict) and spec.get("kind") == "mcp_stdio":
            await asyncio.to_thread(stdio_authority.authorize, body.get("operation"), body)
            return {"allowed": True}
        if isinstance(spec, dict) and spec.get("target_slot") == "knowledge/ingestion":
            await asyncio.to_thread(knowledge_jobs.authorize, body.get("operation"), body)
            return {"allowed": True}
        if isinstance(spec, dict) and spec.get("target_slot") == "skill/validation":
            await asyncio.to_thread(skill_validation.authorize, body.get("operation"), body)
            return {"allowed": True}
        if isinstance(spec, dict) and spec.get("target_slot") == "skill/archive-import":
            await asyncio.to_thread(skill_import_jobs.authorize, body.get("operation"), body)
            return {"allowed": True}
        if coordinator is None:
            raise PlatformError("STORAGE_UNAVAILABLE", "Sandbox storage is not configured", 503)
        await asyncio.to_thread(coordinator.authorize, body.get("operation"), body)
        return {"allowed": True}

    @app.post("/internal/v1/connectors/authorize")
    async def connector_authorize(request: Request, body: dict):
        supplied = request.headers.get("x-connector-token", "")
        if not settings.connector_control_token or not hmac.compare_digest(
            supplied.encode("utf-8"), settings.connector_control_token.encode("ascii")
        ):
            raise PlatformError("UNAUTHORIZED_SERVICE", "Connector identity is required", 401)
        await asyncio.to_thread(connector_authority.authorize, body.get("operation"), body)
        return {"allowed": True}

    @app.post("/internal/v1/connectors/stdio")
    async def stdio_control(request: Request, body: dict):
        supplied = request.headers.get("x-connector-token", "")
        if not settings.connector_control_token or not hmac.compare_digest(
            supplied.encode("utf-8"), settings.connector_control_token.encode("ascii")
        ):
            raise PlatformError("UNAUTHORIZED_SERVICE", "Gateway control identity is required", 401)
        operation, payload = body.get("operation"), body.get("payload")
        if not isinstance(payload, dict):
            raise PlatformError("INVALID_REQUEST", "Stdio context must be explicit", 422)
        if operation == "prepare":
            context = payload.get("context")
            if not isinstance(context, dict) or set(context) != {"operation", "payload"}:
                raise PlatformError("INVALID_REQUEST", "Stdio requires the original authorized MCP request", 422)
            result = await asyncio.to_thread(stdio_authority.prepare, context["operation"], context["payload"])
        elif operation == "inputs":
            result = await asyncio.to_thread(stdio_authority.inputs.load, payload)
        elif operation == "cleanup":
            result = await asyncio.to_thread(stdio_authority.cleanup, payload)
        else:
            raise PlatformError("INVALID_REQUEST", "Unknown stdio control operation", 422)
        return {"allowed": True, **result}

    def storage():
        if artifacts is None:
            raise PlatformError("STORAGE_UNAVAILABLE", "Artifact storage has not been configured", 503)
        return artifacts

    @app.post("/api/v2/projects/{project_id}/uploads", status_code=201)
    async def create_upload(project_id: UUID, body: UploadCreate, identity: Principal = Depends(principal)):
        if body.max_bytes > settings.max_upload_bytes:
            raise PlatformError("PAYLOAD_TOO_LARGE", "Upload exceeds this deployment's limit", 413)
        return await asyncio.to_thread(storage().create_upload, identity, project_id, body.path, body.max_bytes)

    @app.put("/api/v2/uploads/{upload_id}/content")
    async def upload_content(upload_id: UUID, request: Request, identity: Principal = Depends(principal)):
        data = await request.body()
        return await asyncio.to_thread(storage().upload, identity, upload_id, data)

    @app.get("/api/v2/projects/{project_id}/files")
    async def project_files(project_id: UUID, identity: Principal = Depends(principal)):
        return {"items": await asyncio.to_thread(storage().list_project, identity, project_id)}

    @app.get("/api/v2/artifacts/{artifact_id}")
    async def artifact_info(artifact_id: UUID, identity: Principal = Depends(principal)):
        return await asyncio.to_thread(storage().info, identity, artifact_id)

    @app.get("/api/v2/artifacts/{artifact_id}/download")
    async def artifact_download(artifact_id: UUID, identity: Principal = Depends(principal)):
        from urllib.parse import quote

        meta, data = await asyncio.to_thread(storage().download, identity, artifact_id)
        filename = meta["path"].rsplit("/", 1)[-1]
        return Response(
            data,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename, safe=""),
                "Content-Security-Policy": "default-src 'none'; sandbox",
            },
        )

    @app.get("/api/v2/projects")
    async def projects(
        after: UUID | None = None, limit: int = Query(50, ge=1, le=100), identity: Principal = Depends(principal)
    ):
        items = await asyncio.to_thread(service.list_projects, identity, after=after, limit=limit)
        return {"items": items, "next_cursor": str(items[-1]["id"]) if len(items) == limit else None}

    @app.post("/api/v2/projects", status_code=201)
    async def create_project(body: ProjectCreate, identity: Principal = Depends(principal)):
        return await asyncio.to_thread(service.create_project, identity, body.name)

    @app.get("/api/v2/projects/{project_id}")
    async def project_detail(project_id: UUID, identity: Principal = Depends(principal)):
        return await asyncio.to_thread(service.project_detail, identity, project_id)

    @app.get("/api/v2/agents")
    async def agents(identity: Principal = Depends(principal)):
        return {"items": await asyncio.to_thread(service.list_agents, identity)}

    @app.get("/api/v2/sessions")
    async def sessions(
        after: UUID | None = None, limit: int = Query(50, ge=1, le=100), identity: Principal = Depends(principal)
    ):
        items = await asyncio.to_thread(service.list_sessions, identity, after=after, limit=limit)
        return {"items": items, "next_cursor": str(items[-1]["id"]) if len(items) == limit else None}

    @app.post("/api/v2/sessions", status_code=201)
    async def create_session(body: SessionCreate, identity: Principal = Depends(principal)):
        return await asyncio.to_thread(
            service.create_session, identity, body.project_id, body.agent_version_id, body.title
        )

    @app.get("/api/v2/sessions/{session_id}")
    async def session_detail(session_id: UUID, identity: Principal = Depends(principal)):
        return await asyncio.to_thread(service.session_detail, identity, session_id)

    @app.patch("/api/v2/sessions/{session_id}")
    async def rename_session(session_id: UUID, body: Rename, identity: Principal = Depends(principal)):
        return await asyncio.to_thread(service.rename_session, identity, session_id, body.name, body.expected_revision)

    @app.delete("/api/v2/sessions/{session_id}")
    async def archive_session(
        session_id: UUID, expected_revision: int = Query(ge=0), identity: Principal = Depends(principal)
    ):
        return await asyncio.to_thread(service.archive_session, identity, session_id, expected_revision)

    @app.post("/api/v2/sessions/{session_id}/runs", status_code=202)
    async def create_run(session_id: UUID, request: Request, body: RunCreate, identity: Principal = Depends(principal)):
        if len(body.message.encode("utf-8")) > settings.max_message_bytes:
            raise PlatformError("PAYLOAD_TOO_LARGE", "Message exceeds the configured byte limit", 413)
        result = await asyncio.to_thread(
            service.create_run,
            identity,
            session_id,
            body.model_dump(mode="json"),
            request.headers.get("idempotency-key", ""),
        )
        id = result["run_id"]
        return {**result, "status_url": f"/api/v2/runs/{id}", "events_url": f"/api/v2/runs/{id}/events"}

    @app.get("/api/v2/runs/{run_id}")
    async def get_run(run_id: UUID, identity: Principal = Depends(principal)):
        return await asyncio.to_thread(service.get_run, identity, run_id)

    @app.post("/api/v2/runs/{run_id}/cancel")
    async def cancel_run(run_id: UUID, identity: Principal = Depends(principal)):
        return await asyncio.to_thread(service.cancel_run, identity, run_id)

    @app.get("/api/v2/approvals")
    async def approvals(limit: int = Query(50, ge=1, le=100), identity: Principal = Depends(principal)):
        return {"items": await asyncio.to_thread(service.list_approvals, identity, limit=limit)}

    @app.get("/api/v2/approvals/{approval_id}")
    async def approval_detail(approval_id: UUID, identity: Principal = Depends(principal)):
        return await asyncio.to_thread(service.approval_detail, identity, approval_id)

    @app.post("/api/v2/runs/{run_id}/reconcile")
    async def reconcile_run(run_id: UUID, body: RunReconciliation, identity: Principal = Depends(principal)):
        return await asyncio.to_thread(
            execution.reconcile, identity, run_id, body.expected_revision, body.conclusion, body.evidence_ref
        )

    @app.post("/api/v2/approvals/{approval_id}/decision")
    async def decide(approval_id: UUID, body: ApprovalDecision, identity: Principal = Depends(principal)):
        return await asyncio.to_thread(
            service.decide_approval, identity, approval_id, body.expected_revision, body.action_digest, body.decision
        )

    @app.get("/api/v2/runs/{run_id}/events")
    async def events(
        run_id: UUID, request: Request, after_seq: int = Query(0, ge=0), identity: Principal = Depends(principal)
    ):
        cursor = after_seq
        supplied = request.headers.get("last-event-id")
        if supplied:
            try:
                prior_run, raw_seq = supplied.rsplit(":", 1)
                if UUID(prior_run) != run_id or not raw_seq.isascii() or not raw_seq.isdecimal():
                    raise ValueError
                parsed_seq = int(raw_seq)
                if "after_seq" in request.query_params and after_seq != parsed_seq:
                    raise ValueError
                cursor = parsed_seq
            except ValueError:
                raise PlatformError("INVALID_EVENT_CURSOR", "Event cursor is not valid for this run", 409) from None
        initial, state = await asyncio.to_thread(service.read_events, identity, run_id, cursor, settings.sse_batch_size)
        key = (identity.org_id, identity.user_id)
        if subscriptions.get(key, 0) >= 4:
            raise PlatformError("SUBSCRIPTION_LIMIT", "Too many concurrent event subscriptions", 429)
        subscriptions[key] = subscriptions.get(key, 0) + 1
        raw_token = request.cookies[settings.session_cookie]

        async def stream():
            nonlocal cursor
            rows, current_state = initial, state
            try:
                while True:
                    # Logout/revocation may happen after the initial request authorization.
                    refreshed = await asyncio.to_thread(auth.authenticate, raw_token)
                    if refreshed != identity:
                        return
                    for row in rows:
                        cursor = row["seq"]
                        payload = json.dumps(
                            jsonable_encoder(
                                {
                                    "schema_version": row["schema_version"],
                                    "run_id": run_id,
                                    "seq": cursor,
                                    "timestamp": row["created_at"],
                                    "payload": row["payload"],
                                }
                            ),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        yield f"id: {run_id}:{cursor}\nevent: {row['kind']}\ndata: {payload}\n\n"
                    if (
                        current_state in {s.value for s in TERMINAL_STATES} | {"recovery_required"}
                        and len(rows) < settings.sse_batch_size
                    ):
                        return
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(settings.sse_poll_seconds)
                    # PG is the source of truth, so a lost notification cannot create a replay gap.
                    rows, current_state = await asyncio.to_thread(
                        service.read_events, refreshed, run_id, cursor, settings.sse_batch_size
                    )
            except (PlatformError, SQLAlchemyError):
                # Never emit unscoped exception bodies or continue after authorization is lost.
                return
            finally:
                subscriptions[key] -= 1
                if subscriptions[key] == 0:
                    subscriptions.pop(key, None)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})

    register_admin_routes(app, admin, principal)
    register_skill_routes(app, skills, principal)
    register_archive_routes(app, skill_archives, principal)
    register_connection_routes(app, connections, principal)
    register_knowledge_routes(app, knowledge, knowledge_retrieval, knowledge_jobs, embedding_billing, principal)
    if settings.web_dist and (settings.web_dist / "index.html").is_file():
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import FileResponse

        app.mount("/assets", StaticFiles(directory=settings.web_dist / "assets"), name="platform-assets")

        @app.get("/", include_in_schema=False)
        @app.get("/app", include_in_schema=False)
        @app.get("/app/{path:path}", include_in_schema=False)
        async def workbench(path: str = ""):
            return FileResponse(settings.web_dist / "index.html")

    return app
