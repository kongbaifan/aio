import ast
import asyncio
import hmac
import mimetypes
import os
import platform
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import psutil
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# 运行时配置集中在环境变量中，便于本地运行和容器部署复用同一份代码。
WORKSPACE_DIR = os.path.abspath(
    os.environ.get(
        "SANDBOX_WORKSPACE_DIR",
        os.path.join(os.path.dirname(__file__), "tmp"),
    )
)
WORKSPACE_PATH = Path(WORKSPACE_DIR).resolve()
SANDBOX_TOKEN = os.environ.get("SANDBOX_TOKEN", "").strip()
EXECUTION_TIMEOUT_SECONDS = max(1, int(os.environ.get("SANDBOX_EXECUTION_TIMEOUT", "30")))
MAX_CODE_BYTES = max(1024, int(os.environ.get("SANDBOX_MAX_CODE_BYTES", "262144")))
MAX_FILE_BYTES = max(1024, int(os.environ.get("SANDBOX_MAX_FILE_BYTES", "10485760")))
MAX_OUTPUT_BYTES = max(1024, int(os.environ.get("SANDBOX_MAX_OUTPUT_BYTES", "1048576")))
# 单个 session 最多保留的执行记录数，以及并发保留的 session 总数上限，避免进程内字典无限增长。
MAX_SESSION_HISTORY = max(1, int(os.environ.get("SANDBOX_MAX_SESSION_HISTORY", "100")))
MAX_CODE_SESSIONS = max(1, int(os.environ.get("SANDBOX_MAX_CODE_SESSIONS", "256")))
BEARER_PREFIX = "bearer "
PROCESS_TERMINATE_TIMEOUT = 3
SESSION_ID_LENGTH = 8
SERVER_STARTED_AT = time.monotonic()
os.makedirs(WORKSPACE_DIR, exist_ok=True)

# 活跃终端和代码会话都只保存在当前进程内，生产环境应接入有 TTL 的持久化存储。
terminal_sessions: dict[str, dict] = {}
code_exec_sessions: dict[str, list] = {}
process_pool: dict[str, subprocess.Popen] = {}

app = FastAPI(title="AIO Sandbox Lite", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.environ.get(
            "SANDBOX_CORS_ORIGINS",
            "http://127.0.0.1:8080,http://localhost:8080,http://127.0.0.1:8081,http://localhost:8081",
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend files
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


def _extract_token(headers, query_token: str = "") -> str:
    """从 Authorization / X-Sandbox-Token 请求头解析 token，HTTP 与 WebSocket 共用。

    query_token 仅作为 WebSocket 的兜底来源；把 token 放进 URL 容易被日志和代理
    记录，因此正常应优先使用请求头。
    """
    authorization = headers.get("authorization", "")
    if authorization.lower().startswith(BEARER_PREFIX):
        return authorization[len(BEARER_PREFIX):].strip()
    header_token = headers.get("x-sandbox-token", "").strip()
    if header_token:
        return header_token
    return query_token.strip()


def _request_token(request: Request) -> str:
    """读取 Bearer 或专用请求头，避免把 token 放在普通业务参数中。"""
    return _extract_token(request.headers)


def _token_is_valid(token: str) -> bool:
    if not SANDBOX_TOKEN:
        return True
    # compare_digest 对含非 ASCII 字符的 str 会抛 TypeError，在中间件里变成
    # 500 而不是 401。先编码成 bytes：既避免报错，也仍是常数时间比较。
    return hmac.compare_digest(token.encode("utf-8"), SANDBOX_TOKEN.encode("utf-8"))


# 传给用户代码的环境变量白名单，避免子进程读到 SANDBOX_TOKEN 等宿主机密钥。
_SUBPROCESS_ENV_PASSTHROUGH = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "LANG", "LC_ALL", "TZ")


def _build_subprocess_env() -> dict[str, str]:
    env = {
        name: os.environ[name]
        for name in _SUBPROCESS_ENV_PASSTHROUGH
        if name in os.environ
    }
    env["PYTHONIOENCODING"] = "utf-8"
    return env


@app.middleware("http")
async def authenticate_request(request: Request, call_next):
    """本地开发默认不鉴权；设置 SANDBOX_TOKEN 后所有写入/执行请求必须带 token。"""
    public_paths = {
        "/",
        "/index.html",
        "/healthz",
        "/v1/healthz",
        "/openapi.json",
        "/docs",
        "/redoc",
    }
    if request.url.path not in public_paths and not request.url.path.startswith("/static"):
        if not _token_is_valid(_request_token(request)):
            return JSONResponse(status_code=401, content={"detail": "Invalid sandbox token"})
    return await call_next(request)

# ─── Models ────────────────────────────────────────────────────
class CodeExecuteRequest(BaseModel):
    code: str
    language: str = "python"
    session_id: Optional[str] = None

class CodeExecuteResult(BaseModel):
    session_id: str
    output: str
    error: str = ""
    exit_code: int = 0

class FileInfo(BaseModel):
    name: str
    path: str
    type: str
    size: int
    modified: str

class WriteFileRequest(BaseModel):
    path: str
    content: str

class MkdirRequest(BaseModel):
    path: str

class DeleteRequest(BaseModel):
    path: str

# ─── Health & Info ──────────────────────────────────────────────
@app.get("/healthz")
@app.get("/v1/healthz")
async def healthz():
    return {"status": "ok", "timestamp": time.time()}

@app.get("/v1/sandbox")
async def sandbox_info():
    return {
        "version": "1.0.0",
        "platform": platform.platform(),
        "python": sys.version,
        "hostname": platform.node(),
        "uptime_seconds": round(time.monotonic() - SERVER_STARTED_AT, 3),
        "workspace": WORKSPACE_DIR,
        "limits": {
            "execution_timeout_seconds": EXECUTION_TIMEOUT_SECONDS,
            "max_code_bytes": MAX_CODE_BYTES,
            "max_file_bytes": MAX_FILE_BYTES,
            "max_output_bytes": MAX_OUTPUT_BYTES,
        },
    }

# ─── File Operations ────────────────────────────────────────────
# Windows 保留设备名：这些名字（不论扩展名、不论大小写）会被系统解析为设备而非
# 文件。写 NUL 会"成功"但数据蒸发，写 COM1 会去打开串口并可能挂死。
_WIN_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def _reject_windows_alias(path: str) -> None:
    """拦截 Windows 上会被静默改写或指向设备的路径别名。

    resolve() 对付得了 ../ 和盘符，但对付不了这两类 Win32 命名怪癖：
    - 尾随点 / 空格：'report.txt.' 会被剥成 'report.txt'，静默覆盖已有文件；
    - 保留设备名：写 NUL 数据蒸发、写 COM1 打开串口。
    两者都会让"写新文件"变成别的事，且响应仍回显原始 path，模型完全无感。
    """
    for part in path.replace("\\", "/").split("/"):
        if not part:
            continue
        # "." 和 ".." 是合法的路径段（越界由后面的 resolve + relative_to 判定），
        # 不能被下面的"尾随点"规则误伤。
        if part in {".", ".."}:
            continue
        # 尾随点 / 空格：Win32 打开时会被剥掉，等价于另一个文件名。
        if part != part.rstrip(" ."):
            raise HTTPException(400, "路径段不能以点或空格结尾")
        # NTFS 备用数据流：'a.txt:stash' 能写入，但 os.listdir 看不到、
        # a.txt 的 st_size 也不变，等于在 workspace 里藏了个 list_files 无感的文件。
        # 盘符（'C:'）不会走到这里——它在首段，且越界由 resolve 判定。
        if ":" in part:
            raise HTTPException(400, "路径段不能包含冒号（NTFS 备用数据流）")
        # 设备名判定只看点号前的主名，NUL 和 NUL.txt 一样危险。
        stem = part.split(".", 1)[0].strip().lower()
        if stem in _WIN_RESERVED:
            raise HTTPException(400, f"路径包含保留设备名：{part}")


def safe_path(path: str) -> str:
    """把用户路径约束到 workspace 内，不能使用字符串前缀代替真实路径边界判断。"""
    if not path or "\x00" in path:
        raise HTTPException(400, "Invalid path")
    _reject_windows_alias(path)
    candidate = (WORKSPACE_PATH / path.lstrip("/\\")).resolve()
    try:
        candidate.relative_to(WORKSPACE_PATH)
    except ValueError as exc:
        raise HTTPException(403, "Path traversal denied") from exc
    return str(candidate)


def _encoded_size(value: str) -> int:
    return len(value.encode("utf-8"))


def _truncate_output(value: str) -> str:
    """按 UTF-8 字节限制输出，同时尽量避免截断到半个字符。"""
    encoded = value.encode("utf-8")
    if len(encoded) <= MAX_OUTPUT_BYTES:
        return value
    clipped = encoded[:MAX_OUTPUT_BYTES].decode("utf-8", errors="ignore")
    return f"{clipped}\n...[output truncated at {MAX_OUTPUT_BYTES} bytes]"

@app.get("/v1/files")
async def list_files(path: str = Query(".")):
    target = safe_path(path)
    if not os.path.exists(target):
        raise HTTPException(404, "Path not found")
    if not os.path.isdir(target):
        raise HTTPException(400, "Not a directory")
    items = []
    for name in sorted(os.listdir(target)):
        full = os.path.join(target, name)
        try:
            st = os.stat(full)
            items.append(FileInfo(
                name=name,
                # 基准必须用 WORKSPACE_PATH（已 resolve），不能用 WORKSPACE_DIR。
                # target 是 safe_path resolve 过的，拿未 resolve 的 WORKSPACE_DIR
                # 算相对路径，遇到 8.3 短名 / 符号链接会算出 ..\..\job steam\... 这种
                # 越权样式的路径，还会把宿主机真实用户名泄进模型上下文。
                path=os.path.relpath(full, WORKSPACE_PATH),
                type="dir" if os.path.isdir(full) else "file",
                size=st.st_size if os.path.isfile(full) else 0,
                modified=datetime.fromtimestamp(st.st_mtime).isoformat(),
            ))
        except OSError:
            pass
    return {"items": items, "cwd": os.path.relpath(target, WORKSPACE_PATH)}

@app.get("/v1/files/read")
async def read_file(path: str = Query(...)):
    target = safe_path(path)
    if not os.path.isfile(target):
        raise HTTPException(404, "File not found")
    size = os.path.getsize(target)
    if size > MAX_FILE_BYTES:
        raise HTTPException(413, f"File exceeds {MAX_FILE_BYTES} byte limit")
    try:
        with open(target, "r", encoding="utf-8") as f:
            content = f.read()
        return {"path": path, "content": content, "size": size}
    except UnicodeDecodeError:
        return {"path": path, "content": "[Binary file]", "size": size}

@app.post("/v1/files/write")
async def write_file(req: WriteFileRequest):
    content_size = _encoded_size(req.content)
    if content_size > MAX_FILE_BYTES:
        raise HTTPException(413, f"Content exceeds {MAX_FILE_BYTES} byte limit")
    target = safe_path(req.path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(req.content)
    return {"path": req.path, "size": content_size}

@app.post("/v1/files/mkdir")
async def mkdir(req: MkdirRequest):
    target = safe_path(req.path)
    os.makedirs(target, exist_ok=True)
    return {"path": req.path}

@app.post("/v1/files/delete")
async def delete_file(req: DeleteRequest):
    target = safe_path(req.path)
    if Path(target) == WORKSPACE_PATH:
        raise HTTPException(400, "Workspace root cannot be deleted")
    if not os.path.exists(target):
        raise HTTPException(404, "Not found")
    if os.path.isdir(target):
        shutil.rmtree(target)
    else:
        os.unlink(target)
    return {"deleted": req.path}

@app.post("/v1/files/upload")
async def upload_file(request: Request):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_size = int(content_length)
        except ValueError as exc:
            # 拒绝伪造的长度头，避免异常直接变成 500。
            raise HTTPException(400, "Invalid Content-Length header") from exc
        if declared_size < 0:
            raise HTTPException(400, "Invalid Content-Length header")
        if declared_size > MAX_FILE_BYTES:
            raise HTTPException(413, f"Upload exceeds {MAX_FILE_BYTES} byte limit")
    body = await request.body()
    if len(body) > MAX_FILE_BYTES:
        raise HTTPException(413, f"Upload exceeds {MAX_FILE_BYTES} byte limit")
    path = request.headers.get("X-File-Path", str(uuid.uuid4()))
    target = safe_path(path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as f:
        f.write(body)
    return {"path": path, "size": len(body)}

@app.get("/v1/files/download")
async def download_file(path: str = Query(...)):
    target = safe_path(path)
    if not os.path.isfile(target):
        raise HTTPException(404, "File not found")
    size = os.path.getsize(target)
    if size > MAX_FILE_BYTES:
        raise HTTPException(413, f"File exceeds {MAX_FILE_BYTES} byte limit")
    media_type, _ = mimetypes.guess_type(target)
    return FileResponse(target, media_type=media_type or "application/octet-stream")

# ─── Code Execution ─────────────────────────────────────────────
@app.post("/v1/execute", response_model=CodeExecuteResult)
async def execute_code(req: CodeExecuteRequest):
    sid = req.session_id or str(uuid.uuid4())
    output_lines = []
    error_lines = []

    if req.language == "python" and _encoded_size(req.code) > MAX_CODE_BYTES:
        raise HTTPException(413, f"Code exceeds {MAX_CODE_BYTES} byte limit")

    def _run_python() -> subprocess.CompletedProcess:
        # subprocess.run 是同步阻塞调用，放进线程避免卡住事件循环。
        return subprocess.run(
            [sys.executable, "-c", req.code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=EXECUTION_TIMEOUT_SECONDS,
            cwd=WORKSPACE_DIR,
            env=_build_subprocess_env(),
        )

    try:
        if req.language == "python":
            result = await asyncio.to_thread(_run_python)
            if result.stdout:
                output_lines.append(result.stdout)
            if result.stderr:
                error_lines.append(result.stderr)
            exit_code = result.returncode
        else:
            error_lines.append(f"Unsupported language: {req.language}")
            exit_code = 1
    except subprocess.TimeoutExpired:
        error_lines.append(f"Execution timed out ({EXECUTION_TIMEOUT_SECONDS}s)")
        exit_code = -1
    except Exception as e:
        error_lines.append(str(e))
        exit_code = -1

    output = _truncate_output("".join(output_lines))
    error = _truncate_output("".join(error_lines))
    if sid not in code_exec_sessions:
        # 达到 session 总数上限时按 FIFO 淘汰最旧的 session，避免进程内字典无限增长。
        while len(code_exec_sessions) >= MAX_CODE_SESSIONS:
            oldest_sid = next(iter(code_exec_sessions))
            code_exec_sessions.pop(oldest_sid, None)
        code_exec_sessions[sid] = []
    code_exec_sessions[sid].append({
        "code": req.code,
        "timestamp": time.time(),
        "output": output,
        "error": error,
    })
    # 防止单个 session 无限增长，只保留最近若干次执行记录。
    code_exec_sessions[sid] = code_exec_sessions[sid][-MAX_SESSION_HISTORY:]

    return CodeExecuteResult(
        session_id=sid,
        output=output,
        error=error,
        exit_code=exit_code,
    )

@app.get("/v1/execute/sessions")
async def list_exec_sessions():
    return {"sessions": list(code_exec_sessions.keys())}

# ─── Lint (Python syntax check) ────────────────────────────────
@app.post("/v1/lint")
async def lint_code(req: CodeExecuteRequest):
    if req.language != "python":
        return {"errors": [], "warnings": []}
    errors = []
    try:
        ast.parse(req.code)
    except SyntaxError as e:
        errors.append({
            "line": e.lineno or 1,
            "col": e.offset or 0,
            "message": e.msg,
            "text": e.text or "",
        })
    return {"errors": errors, "warnings": []}

# ─── Shell (via WebSocket) ──────────────────────────────────────
@app.websocket("/v1/shell/ws")
async def shell_ws(websocket: WebSocket):
    # WebSocket 不经过 HTTP middleware，需要在 accept 前单独校验 token。
    token = _extract_token(websocket.headers, websocket.query_params.get("token", ""))
    if not _token_is_valid(token):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    session_id = str(uuid.uuid4())[:SESSION_ID_LENGTH]
    await websocket.send_json({"type": "session_id", "data": session_id})
    await websocket.send_json({"type": "ready", "data": f"AIO Sandbox Terminal [session: {session_id}]"})

    proc = None
    read_tasks: list[asyncio.Task] = []
    loop = asyncio.get_running_loop()
    try:
        if os.name == "nt":
            # 不使用 shell=True：直接执行 cmd.exe，避免 list + shell 在 Windows 上的语义混乱。
            proc = subprocess.Popen(
                ["cmd.exe"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=WORKSPACE_DIR,
            )
        else:
            proc = subprocess.Popen(
                ["/bin/bash", "--login"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=WORKSPACE_DIR,
            )

        process_pool[session_id] = proc
        terminal_sessions[session_id] = {"proc": proc, "ws": websocket}

        async def pump_stream(stream) -> None:
            """把子进程某个输出流逐行转发到 WebSocket，stdout/stderr 共用。"""
            while stream:
                line = await loop.run_in_executor(None, stream.readline)
                if not line:
                    break
                try:
                    await websocket.send_json({"type": "output", "data": line.decode("utf-8", errors="replace")})
                except Exception:
                    break

        read_tasks = [
            asyncio.create_task(pump_stream(proc.stdout)),
            asyncio.create_task(pump_stream(proc.stderr)),
        ]

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")
            if msg_type == "input" and proc and proc.stdin:
                payload = data.get("data", "")
                if len(payload.encode("utf-8")) > MAX_OUTPUT_BYTES:
                    await websocket.send_json({"type": "error", "data": "Input is too large"})
                    continue
                await loop.run_in_executor(None, proc.stdin.write, payload.encode("utf-8"))
                await loop.run_in_executor(None, proc.stdin.flush)
            elif msg_type == "resize":
                pass
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong", "data": data.get("data", {})})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "data": str(e)})
        except Exception:
            pass
    finally:
        # 先取消读任务，避免它们悬挂在 run_in_executor(readline) 的线程池线程里。
        for task in read_tasks:
            task.cancel()
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=PROCESS_TERMINATE_TIMEOUT)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        process_pool.pop(session_id, None)
        terminal_sessions.pop(session_id, None)

# ─── Browser Info (mock) ────────────────────────────────────────
# 浏览器视口默认 1368x1080；可用 SANDBOX_BROWSER_WIDTH / SANDBOX_BROWSER_HEIGHT 覆盖。
BROWSER_VIEWPORT_WIDTH = max(1, int(os.environ.get("SANDBOX_BROWSER_WIDTH", "1368")))
BROWSER_VIEWPORT_HEIGHT = max(1, int(os.environ.get("SANDBOX_BROWSER_HEIGHT", "1080")))


@app.get("/v1/browser/info")
async def browser_info():
    viewport = {"width": BROWSER_VIEWPORT_WIDTH, "height": BROWSER_VIEWPORT_HEIGHT}
    return {
        "data": {
            "cdp_url": "ws://127.0.0.1:9222/devtools/browser",
            "viewport": viewport,
            "page_viewport": dict(viewport),
        }
    }

# ─── System Metrics ─────────────────────────────────────────────
@app.get("/v1/metrics")
async def metrics():
    # interval=None 立即返回自上次调用以来的 CPU 使用率，不阻塞事件循环。
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "memory": psutil.virtual_memory()._asdict(),
        "disk": psutil.disk_usage(WORKSPACE_DIR)._asdict(),
        "processes": len(process_pool),
        "sessions": len(terminal_sessions),
    }

# ─── Frontend ───────────────────────────────────────────────────
@app.get("/")
@app.get("/index.html")
async def index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return PlainTextResponse("Frontend not found. Run: cd static && python create_frontend.py")

# ─── Main ───────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    # 默认只监听回环地址；容器通过 SANDBOX_HOST=0.0.0.0 显式对外暴露。
    host = os.environ.get("SANDBOX_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("SANDBOX_PORT", "8081"))
    except ValueError:
        port = 8081
    print(f"  Workspace: {WORKSPACE_DIR}")
    print(f"  Frontend:  {static_dir}")
    print(f"  Open:      http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
