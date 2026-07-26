import httpx


class NodeReplError(RuntimeError):
    pass


# 同 SandboxClient：客户端超时要比请求体里给 REPL 的执行超时（默认 30000ms）宽，
# 否则跑满时长的代码会让 httpx 先抛 ReadTimeout，盖掉服务端本来要返回的超时结果。
DEFAULT_TIMEOUT_SECONDS = 45.0


class NodeReplClient:
    def __init__(self, base_url: str, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def execute(self, code: str, session_id: str | None = None, timeout: int = 30000) -> dict:
        if not self.base_url:
            raise NodeReplError("Node REPL is not configured")
        try:
            response = await self._client.post(
                f"{self.base_url}/execute",
                json={"code": code, "session_id": session_id, "timeout": timeout},
            )
        except httpx.HTTPError as exc:
            raise NodeReplError(f"Node REPL unavailable: {exc}") from exc
        if response.status_code >= 400:
            raise NodeReplError(f"Node REPL HTTP {response.status_code}: {response.text}")
        return response.json()

    async def health(self) -> dict:
        if not self.base_url:
            return {"status": "disabled"}
        try:
            response = await self._client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            return {"status": "unavailable", "detail": str(exc)}

