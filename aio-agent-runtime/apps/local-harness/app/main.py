import asyncio
import hmac
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .platform_settings import DeploymentMode, PlatformSettings, deployment_mode, require_legacy_mode
from .audit import AuditLogger
from .clients.browser import BrowserCliClient
from .clients.node_repl import NodeReplClient
from .clients.sandbox import SandboxClient, SandboxError
from .config import Settings
from .llm.factory import create_model_service
from .llm.providers import ModelConfigError
from .models import (
    ChatRequest,
    ChatResponse,
    ConfirmDecisionRequest,
    SessionDetail,
    SkillMatchRequest,
)
from .agent import AgentRunner, AnswerDelta, ConfirmRequest, StreamStart
from .orchestrator import Orchestrator
from .sessions import SessionStore
from .skills.registry import SkillRegistry
from .tools.registry import ToolRegistry


class ConfirmationRegistry:
    """人工确认的反向通道：agent 循环挂起在一个 Future 上，
    /api/chat/confirm 端点据 confirmation_id 唤醒它并回传用户决定。

    单进程内存实现；进程重启后未决确认会随之丢失（按拒绝/超时处理）。
    """

    def __init__(self, timeout_seconds: float = 300.0):
        self._pending: dict[str, asyncio.Future[bool]] = {}
        self.timeout = timeout_seconds
        self._lock = asyncio.Lock()

    async def create(self, confirmation_id: str) -> asyncio.Future[bool]:
        """登记一个未决确认并返回它的 Future；重复调用返回同一个。

        有两个调用点：SSE 侧在把 confirm 帧发给前端【之前】先登记，agent 侧随后
        取到同一个 Future 再挂起等待。先登记后发帧，用户点得再快也能被 resolve 命中。
        """
        async with self._lock:
            future = self._pending.get(confirmation_id)
            if future is None or future.done():
                future = asyncio.get_running_loop().create_future()
                self._pending[confirmation_id] = future
            return future

    def discard(self, confirmation_id: str) -> None:
        """清理未决确认；dict.pop 在单线程 event loop 下是原子的，无需加锁。"""
        self._pending.pop(confirmation_id, None)

    async def wait(self, confirmation_id: str) -> bool:
        """登记并挂起等待用户决定；超时或连接断开按拒绝（False）处理。"""
        future = await self.create(confirmation_id)
        try:
            return await asyncio.wait_for(future, timeout=self.timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            return False
        finally:
            self.discard(confirmation_id)

    async def resolve(self, confirmation_id: str, approved: bool) -> bool:
        """回传用户决定；命中未决确认返回 True，否则 False（已超时/未知 id）。"""
        async with self._lock:
            future = self._pending.get(confirmation_id)
        if future is None or future.done():
            return False
        future.set_result(approved)
        return True


class RuntimeContainer:
    """应用运行时依赖，方便测试时替换为 fake client。"""

    def __init__(self, settings: Settings):
        require_legacy_mode()
        self.settings = settings
        self.sandbox = SandboxClient(settings.sandbox_url, settings.sandbox_token)
        self.node = NodeReplClient(settings.node_repl_url)
        self.browser = BrowserCliClient(settings.agent_browser_command)
        self.skills = SkillRegistry(settings.skill_roots)
        self.sessions = SessionStore(settings.session_db_path)
        self.audit = AuditLogger(
            settings.audit_log_path,
            max_bytes=settings.audit_max_bytes,
            backup_count=settings.audit_backup_count,
        )
        self.models = create_model_service(settings)
        self.tools = ToolRegistry(self.sandbox, self.node, self.browser, self.skills)
        self.runner = AgentRunner(
            self.tools,
            self.skills,
            self.sessions,
            self.audit,
            settings.max_agent_rounds,
            settings.require_tool_confirmation,
            settings.tool_context_limit,
        )
        self.orchestrator = Orchestrator(self.runner, self.sessions, settings.max_team_steps)
        self.confirmations = ConfirmationRegistry()

    async def close(self) -> None:
        await self.sandbox.close()
        await self.node.close()
        await self.models.close()
        await self.sessions.close()


def _authorized(request: Request, token: str) -> bool:
    if not token:
        return True
    auth = request.headers.get("authorization", "")
    supplied = auth[7:].strip() if auth.lower().startswith("bearer ") else request.headers.get("x-harness-token", "")
    return hmac.compare_digest(supplied.strip(), token)


def create_app(settings: Settings | None = None) -> FastAPI:
    if deployment_mode() is not DeploymentMode.LEGACY_LOCAL:
        if settings is not None:
            raise ValueError("Legacy settings cannot initialize platform mode")
        from .api.v2.application import create_platform_app

        return create_platform_app(PlatformSettings.from_env())
    settings = settings or Settings.from_env()
    static_dir = Path(__file__).parent / "static"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        container = RuntimeContainer(settings)
        app.state.runtime = container
        yield
        await container.close()

    app = FastAPI(title="AIO Local Harness", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:8080", "http://localhost:8080"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        public = {"/", "/index.html", "/api/health", "/docs", "/openapi.json", "/redoc"}
        if request.url.path not in public and not request.url.path.startswith("/static"):
            if not _authorized(request, settings.harness_token):
                return JSONResponse(status_code=401, content={"detail": "Invalid harness token"})
        return await call_next(request)

    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    def runtime() -> RuntimeContainer:
        return app.state.runtime

    def _default_model_info(container: RuntimeContainer) -> dict[str, str]:
        return container.models.default_selection()

    @app.get("/api/health")
    async def health():
        container = runtime()
        try:
            sandbox = await container.sandbox.health()
        except SandboxError as exc:
            sandbox = {"status": "unavailable", "detail": str(exc)}
        node = await container.node.health()
        selection = _default_model_info(container)
        return {
            "status": "ok",
            "model_mode": "models.json",
            "provider": selection["provider"],
            "model": selection["model"],
            "model_label": selection["label"],
            "models_source": container.models.registry.source_path,
            "sandbox": sandbox,
            "node": node,
            "tools": container.tools.names(),
            "skills": len(container.skills.list()),
            "mcp": {
                "status": "optional",
                "name": "AIO Local Harness",
                "transport": "stdio",
                "tools": ["list_files", "read_file", "write_file", "execute_python"],
            },
        }

    @app.get("/api/config")
    async def config():
        container = runtime()
        selection = _default_model_info(container)
        return {
            "model_mode": "models.json",
            "provider": selection["provider"],
            "model": selection["model"],
            "model_label": selection["label"],
            "models_source": container.models.registry.source_path,
            "sandbox_url": settings.sandbox_url,
            "node_enabled": bool(settings.node_repl_url),
            "browser_enabled": container_browser_enabled(container),
            "tools": container.tools.names(),
        }

    @app.get("/api/models")
    async def list_models():
        container = runtime()
        selection = _default_model_info(container)
        return {
            "default": selection,
            "source": container.models.registry.source_path,
            "models": container.models.list_models(),
        }

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest):
        container = runtime()
        # 解析顺序：请求体 → 已有会话绑定 → 全局默认
        existing = await container.sessions.get(request.session_id)
        provider, model_id = container.models.resolve_selection(
            request.provider,
            request.model,
            fallback_provider=existing.provider if existing else None,
            fallback_model=existing.model if existing else None,
        )
        try:
            model_client = container.models.get_client(provider, model_id)
        except ModelConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        answer, session_id, events, matched = await container.orchestrator.run(
            request.message,
            model_client,
            request.session_id,
            request.mode,
            provider=provider,
            model_id=model_id,
        )
        try:
            files = (await container.sandbox.list_files(".")).get("items", [])
        except SandboxError:
            files = []
        return ChatResponse(
            session_id=session_id,
            answer=answer,
            mode=request.mode,
            events=events,
            files=files,
            matched_skills=matched,
            provider=provider,
            model=model_id,
        )

    @app.post("/api/chat/stream")
    async def chat_stream(request: ChatRequest):
        container = runtime()
        # 解析顺序与 /api/chat 保持一致：请求体 → 已有会话绑定 → 全局默认
        existing = await container.sessions.get(request.session_id)
        provider, model_id = container.models.resolve_selection(
            request.provider,
            request.model,
            fallback_provider=existing.provider if existing else None,
            fallback_model=existing.model if existing else None,
        )
        try:
            model_client = container.models.get_client(provider, model_id)
        except ModelConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        def _sse(kind: str, payload: dict) -> str:
            return "data: " + json.dumps({"kind": kind, **payload}, ensure_ascii=False) + "\n\n"

        async def _final_files() -> list:
            try:
                return (await container.sandbox.list_files(".")).get("items", [])
            except SandboxError:
                return []

        async def _confirmer(req: ConfirmRequest) -> bool:
            # 反向通道：挂起等待前端通过 /api/chat/confirm 回传决定。Future 在发出
            # confirm 帧前已登记，create 会拿到同一个。超时（默认 5 分钟）或连接
            # 断开按拒绝处理，避免 agent 永久挂起。
            future = await container.confirmations.create(req.confirmation_id)
            try:
                return await asyncio.wait_for(future, timeout=container.confirmations.timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                return False
            finally:
                container.confirmations.discard(req.confirmation_id)

        async def event_source():
            answer = "任务已完成，但没有产生最终回答。"
            session_out = request.session_id or ""
            matched: list[str] = []
            run_usage: dict = {}
            try:
                # single 与 team 都走 orchestrator：team 也能流式推送并弹出确认框。
                async for item in container.orchestrator.run_stream(
                    request.message,
                    model_client,
                    request.session_id,
                    request.mode,
                    provider=provider,
                    model_id=model_id,
                    confirmer=_confirmer,
                ):
                    if isinstance(item, StreamStart):
                        session_out = item.session_id
                        matched = item.matched
                        yield _sse("start", {"session_id": session_out, "matched": matched})
                        continue
                    if isinstance(item, AnswerDelta):
                        # 最终答案的文本增量：逐段推给前端做打字机效果。
                        if item.text:
                            yield _sse("delta", {"text": item.text})
                        continue
                    if isinstance(item, ConfirmRequest):
                        # 先登记未决确认再发帧，随后 _confirmer 会挂到同一个 Future 上。
                        # 实际上 StreamingResponse 有缓冲、生成器通常领先于 send，_confirmer
                        # 多半已经先登记过了；这里不依赖那个时序，把窗口显式关死。
                        await container.confirmations.create(item.confirmation_id)
                        yield _sse(
                            "confirm",
                            {
                                "confirmation_id": item.confirmation_id,
                                "tool": item.tool,
                                "arguments": item.arguments,
                            },
                        )
                        continue
                    yield _sse("event", {"event": item.model_dump()})
                    # team 模式里子步骤的终态事件叫 step-N，只有最终汇总才是 answer。
                    if item.type == "error" or (item.type == "result" and item.name == "answer"):
                        answer = item.detail
                        run_usage = item.payload.get("usage") or run_usage
                        # 文本已通过 delta 流式发过则不再整段重发，避免与打字机重复。
                        # is_error 必须带上：错误事件同样走这里（它没有 streamed 标志），
                        # 前端只能靠这个字段把失败渲染成错误气泡，而不是当成正常回答。
                        if not item.payload.get("streamed"):
                            yield _sse("answer", {"answer": answer, "is_error": item.type == "error"})
                files = await _final_files()
                session_after = await container.sessions.get(session_out)
                yield _sse(
                    "done",
                    {
                        "session_id": session_out,
                        "provider": provider,
                        "model": model_id,
                        "files": files,
                        "matched_skills": matched,
                        # usage 是本次请求的消耗，session_usage 是该会话累计。
                        "usage": run_usage,
                        "session_usage": session_after.usage.to_dict() if session_after else {},
                    },
                )
            except Exception as exc:  # noqa: BLE001 - 兜底避免连接悬挂
                yield _sse("error", {"detail": str(exc)})

        return StreamingResponse(
            event_source(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/chat/confirm")
    async def chat_confirm(request: ConfirmDecisionRequest):
        # 反向通道端点：前端弹窗批准/拒绝后调用，resolve 挂起中的 agent。
        resolved = await runtime().confirmations.resolve(request.confirmation_id, request.approved)
        if not resolved:
            # 找不到对应挂起项：多为超时后重复提交或流已结束，返回 404 便于前端提示。
            raise HTTPException(404, "确认请求不存在或已失效")
        return {"resolved": True, "approved": request.approved}

    @app.get("/api/sessions")
    async def sessions():
        return {"sessions": [item.model_dump() for item in await runtime().sessions.list()]}

    @app.get("/api/sessions/{session_id}", response_model=SessionDetail)
    async def session_detail(session_id: str):
        session = await runtime().sessions.get(session_id)
        if not session:
            raise HTTPException(404, "Session not found")
        return SessionDetail(
            id=session.id,
            title=session.title,
            created_at=session.created_at,
            updated_at=session.updated_at,
            message_count=len(session.messages),
            provider=session.provider,
            model=session.model,
            usage=session.usage.to_dict(),
            messages=session.messages,
        )

    @app.delete("/api/sessions/{session_id}")
    async def delete_session(session_id: str):
        deleted = await runtime().sessions.delete(session_id)
        if not deleted:
            raise HTTPException(404, "Session not found")
        return {"deleted": True}

    @app.get("/api/files")
    async def files(path: str = Query(".")):
        try:
            return await runtime().sandbox.list_files(path)
        except SandboxError as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.get("/api/files/content")
    async def file_content(path: str = Query(...)):
        try:
            return await runtime().sandbox.read_file(path)
        except SandboxError as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.get("/api/files/download")
    async def file_download(path: str = Query(...)):
        try:
            response = await runtime().sandbox.download(path)
        except SandboxError as exc:
            raise HTTPException(502, str(exc)) from exc
        return StreamingResponse(
            iter([response.content]),
            media_type=response.headers.get("content-type", "application/octet-stream"),
            headers={"Content-Disposition": f'attachment; filename="{Path(path).name}"'},
        )

    @app.get("/api/skills")
    async def skills():
        return {"skills": [item.to_dict() for item in runtime().skills.list()]}

    @app.post("/api/skills/match")
    async def skill_match(request: SkillMatchRequest):
        return {"skills": [item.to_dict() for item in runtime().skills.match(request.query, request.limit)]}

    @app.get("/")
    @app.get("/index.html")
    async def index():
        return FileResponse(static_dir / "index.html")

    return app


def container_browser_enabled(container: RuntimeContainer) -> bool:
    return container.browser.enabled


app = create_app()
