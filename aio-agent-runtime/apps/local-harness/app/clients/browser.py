import asyncio
import os
import shlex


# 与其它 client 的 httpx 超时对齐，避免 CLI 卡死时请求永久阻塞。
DEFAULT_TIMEOUT_SECONDS = 90


def _split_command(command: str) -> list[str]:
    """按平台拆分命令行。

    shlex 默认是 POSIX 模式，把反斜杠当转义符：Windows 上
    r"C:\\tools\\agent-browser.exe" 会被拆成 ['C:toolsagent-browser.exe']，
    只要 AGENT_BROWSER_COMMAND 填原生路径就必然 FileNotFoundError。
    Windows 上关掉 POSIX 模式并去掉残留引号。
    """
    if os.name == "nt":
        return [part.strip('"') for part in shlex.split(command, posix=False)]
    return shlex.split(command)


class BrowserCliError(RuntimeError):
    pass


class BrowserCliClient:
    """可选的 agent-browser CLI 适配器，未配置命令时不会注册浏览器写操作。"""

    def __init__(self, command: str = "", timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS):
        self.command = command
        self.timeout_seconds = timeout_seconds

    @property
    def enabled(self) -> bool:
        return bool(self.command)

    async def run(self, args: list[str]) -> dict:
        if not self.enabled:
            raise BrowserCliError("Browser CLI is not configured")
        # 用 create_subprocess_exec（非 shell）执行，不存在 shell 注入；模型提供的
        # 参数（如 url）在调用方 registry 处做校验，避免以 "-" 开头被当作选项解析。
        executable = _split_command(self.command)
        process = await asyncio.create_subprocess_exec(
            *executable,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError as exc:
            # 超时后必须真正终止子进程，否则它会继续在后台占用资源。
            process.kill()
            await process.wait()
            raise BrowserCliError(
                f"Browser CLI timed out after {self.timeout_seconds}s"
            ) from exc
        return {
            "exit_code": process.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
        }

