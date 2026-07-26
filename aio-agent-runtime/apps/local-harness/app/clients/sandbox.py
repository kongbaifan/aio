import httpx


class SandboxError(RuntimeError):
    """Sandbox 返回非 2xx 或不可连接时使用的统一异常。"""


class SandboxClient:
    def __init__(self, base_url: str, token: str = "", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    def _headers(self) -> dict[str, str]:
        return {"X-Sandbox-Token": self.token} if self.token else {}

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            response = await self._client.request(
                method,
                f"{self.base_url}{path}",
                headers={**self._headers(), **kwargs.pop("headers", {})},
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise SandboxError(f"Sandbox unavailable: {exc}") from exc
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise SandboxError(f"Sandbox HTTP {response.status_code}: {detail}")
        try:
            return response.json()
        except ValueError as exc:
            raise SandboxError("Sandbox returned invalid JSON") from exc

    async def health(self) -> dict:
        return await self._request("GET", "/v1/healthz")

    async def list_files(self, path: str = ".") -> dict:
        return await self._request("GET", "/v1/files", params={"path": path})

    async def read_file(self, path: str) -> dict:
        return await self._request("GET", "/v1/files/read", params={"path": path})

    async def write_file(self, path: str, content: str) -> dict:
        return await self._request("POST", "/v1/files/write", json={"path": path, "content": content})

    async def execute_python(self, code: str, session_id: str | None = None) -> dict:
        return await self._request(
            "POST",
            "/v1/execute",
            json={"code": code, "language": "python", "session_id": session_id},
        )

    async def lint_python(self, code: str) -> dict:
        return await self._request("POST", "/v1/lint", json={"code": code, "language": "python"})

    async def metrics(self) -> dict:
        return await self._request("GET", "/v1/metrics")

    async def browser_info(self) -> dict:
        return await self._request("GET", "/v1/browser/info")

    async def download(self, path: str) -> httpx.Response:
        try:
            response = await self._client.get(
                f"{self.base_url}/v1/files/download",
                params={"path": path},
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise SandboxError(f"Sandbox unavailable: {exc}") from exc
        if response.status_code >= 400:
            raise SandboxError(f"Sandbox HTTP {response.status_code}: {response.text}")
        return response

