"""Loopback-only synthetic OIDC/model fixture for workbench verification; NEVER a production IdP."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import html
import json
import re
import secrets
import time
from urllib.parse import parse_qs, urlencode

from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
import jwt


def fixture_app(
    issuer: str, redirect_uri: str, client_id: str, client_secret: str, accounts: dict[str, dict], model_key: str
):
    app = FastAPI(title="Synthetic verification services", docs_url=None, redoc_url=None, openapi_url=None)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="preview-key", use="sig", alg="RS256")
    requests = {}
    codes = {}

    @app.get("/healthz")
    def health():
        return {"status": "ok", "synthetic": True}

    @app.get("/authorize")
    def authorize(
        client_id: str, redirect_uri: str, state: str, nonce: str, code_challenge: str, code_challenge_method: str
    ):
        if (
            client_id != app.state.client_id
            or redirect_uri != app.state.redirect_uri
            or code_challenge_method != "S256"
            or len(state) > 128
            or len(nonce) > 128
        ):
            return JSONResponse({"error": "invalid_request"}, status_code=400)
        id = secrets.token_urlsafe(24)
        requests[id] = {"state": state, "nonce": nonce, "challenge": code_challenge, "expires": time.time() + 300}
        choices = "".join(
            '<form method="post" action="/choose"><input type="hidden" name="request_id" value="' + id + '"/>'
            '<input type="hidden" name="subject" value="' + html.escape(subject, quote=True) + '"/>'
            '<button type="submit">'
            + html.escape(info["name"])
            + " · "
            + html.escape(info["role_label"])
            + "</button></form>"
            for subject, info in accounts.items()
        )
        return HTMLResponse(
            '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>仅本地验证 · 选择合成身份</title>'
            "<style>body{font-family:system-ui;margin:60px auto;max-width:550px;background:#f4f7fa;color:#21394f}h1{font-size:24px}"
            "p{color:#637b90;line-height:1.8}button{display:block;width:100%;padding:16px;margin:12px 0;text-align:left;border:1px solid #cbdce4;border-radius:8px;background:white;font-size:16px;cursor:pointer}"
            "small{display:block;margin-top:24px;color:#8b7760}</style><h1>本地验证身份提供方</h1>"
            "<p>以下是合成账号，不是公司的真实登录入口。登录仍经过签名、state、nonce 与 PKCE 校验。</p>"
            + choices
            + "<small>此服务只绑定回环地址，不能部署为生产身份系统。</small></html>"
        )

    @app.post("/choose")
    async def choose(request: Request):
        values = parse_qs((await request.body()).decode())
        rid = values.get("request_id", [""])[0]
        subject = values.get("subject", [""])[0]
        auth = requests.pop(rid, None)
        if not auth or auth["expires"] < time.time() or subject not in accounts:
            return JSONResponse({"error": "expired"}, status_code=400)
        code = secrets.token_urlsafe(32)
        codes[code] = {**auth, "subject": subject}
        return RedirectResponse(
            app.state.redirect_uri + "?" + urlencode({"state": auth["state"], "code": code}), status_code=303
        )

    @app.post("/token")
    async def token(request: Request):
        values = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
        auth = codes.pop(values.get("code", ""), None)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(values.get("code_verifier", "").encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        if (
            not auth
            or auth["expires"] < time.time()
            or values.get("client_secret") != app.state.client_secret
            or values.get("client_id") != app.state.client_id
            or values.get("redirect_uri") != app.state.redirect_uri
            or challenge != auth["challenge"]
        ):
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        now = int(time.time())
        claims = {
            "iss": issuer,
            "sub": auth["subject"],
            "aud": app.state.client_id,
            "nonce": auth["nonce"],
            "iat": now,
            "exp": now + 300,
        }
        return {
            "id_token": jwt.encode(claims, key, algorithm="RS256", headers={"kid": "preview-key"}),
            "token_type": "Bearer",
        }

    @app.get("/jwks")
    def keys():
        return {"keys": [jwk]}

    @app.post("/v1/embeddings")
    async def embeddings(request: Request):
        if request.headers.get("authorization") != "Bearer " + model_key:
            return JSONResponse({"error": "denied"}, status_code=401)
        body = await request.json()
        values = body.get("input", [])
        data = []
        for index, text in enumerate(values):
            lowered = str(text).lower()
            vector = (
                [1.0, 0.0, 0.0]
                if any(word in lowered for word in ("报销", "发票", "expense"))
                else [0.0, 1.0, 0.0]
                if any(word in lowered for word in ("年假", "休假", "leave"))
                else [0.0, 0.0, 1.0]
            )
            data.append({"index": index, "embedding": vector})
        return {"data": data, "usage": {"prompt_tokens": 100, "total_tokens": 100}}

    @app.post("/v1/chat/completions")
    async def model(request: Request):
        if request.headers.get("authorization") != "Bearer " + model_key:
            return JSONResponse({"error": "denied"}, status_code=401)
        body = await request.json()
        messages = body.get("messages", [])
        tools = body.get("tools", [])
        has_result = any(m.get("role") == "tool" for m in messages)
        from preview_team import content as team_content
        from preview_handoff import turn as handoff_turn

        handoff = handoff_turn(messages)
        team_text = handoff.get("content") if handoff else team_content(messages)
        marker = re.search(
            r"stdio-attachment:([0-9a-f-]{36})",
            "\n".join(str(message.get("content", "")) for message in messages if message.get("role") == "user"),
        )
        attachment = (
            marker.group(1)
            if marker and any(tool["function"]["name"] == "stdio_read_attachment" for tool in tools)
            else None
        )

        async def stream():
            if (handoff and handoff.get("tool")) or (tools and not has_result and team_text is None):
                tool_name = handoff["tool"] if handoff else tools[0]["function"]["name"]
                if attachment and not handoff:
                    tool_name = "stdio_read_attachment"
                code = "from pathlib import Path; Path('analysis-result.csv').write_text('item,value\\nexample,42\\n',encoding='utf-8'); print('Verification report created in the isolated workspace')"
                arguments = {"value": 21} if tool_name == "http_skill_double" else {"code": code}
                if tool_name in {"mcp_identity", "stdio_identity"}:
                    arguments = {"query": "我的合成资料"}
                elif tool_name == "analytics_summary":
                    arguments = {"values": [2, 4, 6]}
                elif tool_name == "stdio_read_attachment":
                    arguments = {"artifact_id": attachment}
                elif tool_name.startswith("knowledge_search_"):
                    arguments = {"query": "销售人员餐费报销标准"}
                if handoff:
                    arguments = handoff["arguments"]
                value = {
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "preview-call-1",
                                        "type": "function",
                                        "function": {
                                            "name": tool_name,
                                            "arguments": json.dumps(arguments),
                                        },
                                    }
                                ]
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                }
                yield "data: " + json.dumps(value) + "\n\n"
            else:
                answer = "这是本地验收模型的合成回答，用于验证工作台流程。\n\n"
                answer += "**已完成**：任务状态、模型回合和审批权限均由服务端维护。"
                if has_result:
                    if tools and tools[0]["function"]["name"] == "analytics_summary":
                        answer += "\n\n固定依赖工具返回的事实：" + next(
                            message["content"] for message in reversed(messages) if message["role"] == "tool"
                        )
                    elif attachment:
                        try:
                            result = json.loads(
                                next(message["content"] for message in reversed(messages) if message["role"] == "tool")
                            )
                            source = result.get("structured_content") or json.loads(result["content"][0]["text"])
                            answer += "\n\n隔离附件结果（合成参考工具）：" + json.dumps(source, ensure_ascii=False)
                        except (ValueError, KeyError, TypeError):
                            answer += "\n\n附件未得到可确认的读取结果。"
                    elif tools and tools[0]["function"]["name"].startswith("knowledge_search_"):
                        try:
                            matches = json.loads(next(m["content"] for m in reversed(messages) if m["role"] == "tool"))[
                                "matches"
                            ]
                            answer += (
                                "\n\n文档依据：" + matches[0]["text"] + " [" + matches[0]["label"] + "]"
                                if matches
                                else "\n\n未找到获权资料，不能提供带文档依据的答案。"
                            )
                        except (ValueError, KeyError, TypeError):
                            answer += "\n\n文档检索尚未得到可确认的证据。"
                    elif tools and tools[0]["function"]["name"] == "mcp_identity":
                        try:
                            source = json.loads(next(m["content"] for m in reversed(messages) if m["role"] == "tool"))[
                                "structured_content"
                            ]["subject"]
                            answer += "\n\nMCP 已通过独立凭据网关读取。合成源身份：**" + source + "**。"
                        except (ValueError, KeyError, TypeError):
                            answer += "\n\nMCP 未返回可确认的资料，请检查连接状态。"
                    elif tools and tools[0]["function"]["name"] == "stdio_identity":
                        try:
                            result = json.loads(next(m["content"] for m in reversed(messages) if m["role"] == "tool"))
                            source = result.get("structured_content") or json.loads(result["content"][0]["text"])
                            answer += "\n\n专属 stdio 进程已验证。合成身份摘要：**" + source["subject_digest"] + "**。"
                        except (ValueError, KeyError, TypeError):
                            answer += "\n\nstdio 进程未返回可确认的身份摘要。"
                    else:
                        answer += "\n\nPython 代码已经在真实隔离容器中执行，结果文件已进入产物发布流程。"
                if team_text is not None:
                    answer = team_text
                for i in range(0, len(answer), 8):
                    yield (
                        "data: "
                        + json.dumps(
                            {"choices": [{"index": 0, "delta": {"content": answer[i : i + 8]}}]}, ensure_ascii=False
                        )
                        + "\n\n"
                    )
                    await asyncio.sleep(0.08)
                yield "data: " + json.dumps({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}) + "\n\n"
            yield (
                "data: "
                + json.dumps({"choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 60}})
                + "\n\n"
            )
            yield "data: [DONE]\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    app.state.client_id = client_id
    app.state.client_secret = client_secret
    app.state.redirect_uri = redirect_uri
    return app
