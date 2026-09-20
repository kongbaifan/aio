"""Loopback-only synthetic MCP upstream for finite-lived workbench verification."""

import secrets
import time

from fastapi import Request
from fastapi.responses import JSONResponse, Response

TOKENS = {
    "admin": "synthetic-preview-admin-read-token",
    "alice": "synthetic-preview-alice-read-token",
    "bob": "synthetic-preview-bob-read-token",
}


def register_fixture(app):
    sessions = {}

    def identity(request):
        header = request.headers.get("authorization", "")
        return next((name for name, token in TOKENS.items() if header == "Bearer " + token), None)

    @app.post("/mcp")
    async def mcp(request: Request):
        subject = identity(request)
        if subject is None:
            return JSONResponse({"error": "synthetic_identity_required"}, status_code=401)
        body = await request.json()
        id, method = body.get("id"), body.get("method")
        headers = {}
        if method == "initialize":
            sid = secrets.token_hex(24)
            sessions[sid] = (subject, time.monotonic() + 60)
            headers["Mcp-Session-Id"] = sid
            result = {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "synthetic-company-readonly-mcp", "version": "1"},
            }
        else:
            sid = request.headers.get("mcp-session-id", "")
            current = sessions.get(sid)
            if current is None or current[0] != subject or current[1] < time.monotonic():
                return JSONResponse({"error": "session_scope_denied"}, status_code=403)
            if request.headers.get("mcp-protocol-version") != "2025-06-18":
                return JSONResponse({"error": "version_required"}, status_code=400)
            if method == "notifications/initialized":
                return Response(status_code=202)
            if method == "tools/list":
                result = {
                    "tools": [
                        {
                            "name": "identity_lookup",
                            "description": "读取当前合成外部账号的数据，用于验证凭据隔离。",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"query": {"type": "string"}},
                                "required": ["query"],
                                "additionalProperties": False,
                            },
                            "annotations": {"readOnlyHint": True},
                        }
                    ]
                }
            elif method == "tools/call" and body.get("params", {}).get("name") == "identity_lookup":
                result = {
                    "content": [{"type": "text", "text": "合成源系统身份：" + subject}],
                    "structuredContent": {"subject": subject, "fixture_only": True},
                }
            else:
                return JSONResponse(
                    {"jsonrpc": "2.0", "id": id, "error": {"code": -32601, "message": "Synthetic tool not available"}}
                )
        return JSONResponse({"jsonrpc": "2.0", "id": id, "result": result}, headers=headers)

    @app.delete("/mcp")
    async def close(request: Request):
        subject = identity(request)
        sid = request.headers.get("mcp-session-id", "")
        if subject is None or sessions.get(sid, (None,))[0] != subject:
            return Response(status_code=403)
        sessions.pop(sid, None)
        return Response(status_code=204)
