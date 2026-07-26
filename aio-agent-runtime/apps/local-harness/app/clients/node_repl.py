import httpx


class NodeReplError(RuntimeError):
    pass


class NodeReplClient:
    def __init__(self, base_url: str, timeout: float = 30.0):
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

