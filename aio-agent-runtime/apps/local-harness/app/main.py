import hmac
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .audit import AuditLogger
from .clients.browser import BrowserCliClient
from .clients.node_repl import NodeReplClient
from .clients.sandbox import SandboxClient, SandboxError
from .config import Settings
from .llm.factory import ModelService, create_model_service
from .llm.providers import ModelConfigError
from .models import ChatRequest, ChatResponse, SkillMatchRequest
from .agent import AgentRunner, AnswerDelta, StreamStart
from .orchestrator import Orchestrator
from .sessions import SessionStore
from .skills.registry import SkillRegistry
from .tools.registry import ToolRegistry


class RuntimeContainer:
    """应用运行时依赖，方便测试时替换为 fake client。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.sandbox = SandboxClient(settings.sandbox_url, settings.sandbox_token)
        self.node = NodeReplClient(settings.node_repl_url)
        self.browser = BrowserCliClient(settings.agent_browser_command)
        self.skills = SkillRegistry(settings.skill_roots)
        self.sessions = SessionStore()
        self.audit = AuditLogger(settings.audit_log_path)
        self.models = create_model_service(settings)
        self.tools = ToolRegistry(self.sandbox, self.node, self.browser)
        self.runner = AgentRunner(
            self.tools,
            self.skills,
            self.sessions,
            self.audit,
            settings.max_agent_rounds,
            settings.require_tool_confirmation,
        )
        self.orchestrator = Orchestrator(self.runner, self.sessions, settings.max_team_steps)

    async def close(self) -> None:
        await self.sandbox.close()
        await self.node.close()
        await self.models.close()


def _authorized(request: Request, token: str) -> bool:
    if not token:
        return True
    auth = request.headers.get("authorization", "")
    supplied = auth[7:].strip() if auth.lower().startswith("bearer ") else request.headers.get("x-harness-token", "")
    return hmac.compare_digest(supplied.strip(), token)


def create_app(settings: Settings | None = None) -> FastAPI:
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

        async def event_source():
            answer = "任务已完成，但没有产生最终回答。"
            session_out = request.session_id or ""
            matched: list[str] = []
            try:
                if request.mode == "team":
                    # 团队模式没有流式生成器：跑完后按序补发事件，保持前端渲染一致。
                    answer, session_out, events, matched = await container.orchestrator.run(
                        request.message,
                        model_client,
                        request.session_id,
                        request.mode,
                        provider=provider,
                        model_id=model_id,
                    )
                    yield _sse("start", {"session_id": session_out, "matched": matched})
                    for event in events:
                        yield _sse("event", {"event": event.model_dump()})
                    yield _sse("answer", {"answer": answer})
                else:
                    async for item in container.runner.run_stream(
                        request.message,
                        model_client,
                        request.session_id,
                        provider=provider,
                        model_id=model_id,
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
                        yield _sse("event", {"event": item.model_dump()})
                        if item.type in {"result", "error"}:
                            answer = item.detail
                            # answer 帧携带完整文本，供前端定稿（如切换到 Markdown 渲染）。
                            yield _sse("answer", {"answer": answer})
                files = await _final_files()
                yield _sse(
                    "done",
                    {
                        "session_id": session_out,
                        "provider": provider,
                        "model": model_id,
                        "files": files,
                        "matched_skills": matched,
                    },
                )
            except Exception as exc:  # noqa: BLE001 - 兜底避免连接悬挂
                yield _sse("error", {"detail": str(exc)})

        return StreamingResponse(
            event_source(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/sessions")
    async def sessions():
        return {"sessions": [item.model_dump() for item in await runtime().sessions.list()]}

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
