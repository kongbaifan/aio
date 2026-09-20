"""Synthetic standards-shaped OAuth/RS fixture. Never imported by production startup."""

import base64
import hashlib
import json
import secrets
import time
from urllib.parse import parse_qs, urlencode

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa


class ByteStream(httpx.AsyncByteStream):
    def __init__(self, data):
        self.data = data

    async def __aiter__(self):
        yield self.data


def rpc_response(status, value=None, headers=None):
    return httpx.Response(
        status,
        headers={"Content-Type": "application/json", **(headers or {})},
        stream=ByteStream(json.dumps(value).encode() if value is not None else b""),
    )


class OAuthFixture:
    def __init__(
        self,
        origin="http://127.0.0.1:9191",
        platform="http://127.0.0.1:8080",
        endpoint_id="oauth-company",
        resource_path="/mcp",
    ):
        self.origin, self.platform, self.endpoint_id = origin, platform, endpoint_id
        self.resource_path, self.resource_uri = resource_path, origin + resource_path
        self.resource_metadata_path = "/.well-known/oauth-protected-resource" + resource_path
        self.initial_expiry_seconds = 3600
        self.access_expiry = {}
        self.authorizations = {}
        self.client_id = "fixture-mcp-client"
        self.redirect_uri = platform + "/auth/mcp/callback/" + endpoint_id
        self.codes, self.access_tokens, self.refresh_tokens = {}, {}, {}
        self.requests, self.effects, self.refreshes, self.revocations = [], [], 0, []
        self.mutate_token = None
        self.fail_refresh = False
        self.refresh_started = None
        self.refresh_release = None
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = self.key.public_key().public_numbers()

        def b64(x):
            return base64.urlsafe_b64encode(x.to_bytes((x.bit_length() + 7) // 8, "big")).rstrip(b"=").decode()

        self.jwk = {
            "kty": "RSA",
            "kid": "oauth-fixture-key",
            "use": "sig",
            "alg": "RS256",
            "n": b64(public.n),
            "e": b64(public.e),
        }

    def policy(self):
        return {
            "issuer": self.origin + "/oauth",
            "metadata_url": self.origin + "/.well-known/oauth-authorization-server/oauth",
            "resource_metadata_url": self.origin + self.resource_metadata_path,
            "authorization_endpoint": self.origin + "/oauth/authorize",
            "token_endpoint": self.origin + "/oauth/token",
            "revocation_endpoint": self.origin + "/oauth/revoke",
            "jwks_uri": self.origin + "/oauth/jwks",
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "scopes": ["openid", "mcp.read"],
            "client_auth_method": "none",
            "require_issuer_response": True,
        }

    def metadata(self):
        p = self.policy()
        return {
            "issuer": p["issuer"],
            "authorization_endpoint": p["authorization_endpoint"],
            "token_endpoint": p["token_endpoint"],
            "revocation_endpoint": p["revocation_endpoint"],
            "jwks_uri": p["jwks_uri"],
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none", "client_secret_basic", "client_secret_post"],
            "authorization_response_iss_parameter_supported": True,
        }

    def authorize(self, query, subject="alice"):
        fields = {k: (v[0] if isinstance(v, list) else v) for k, v in query.items()}
        assert fields["client_id"] == self.client_id and fields["redirect_uri"] == self.redirect_uri
        assert fields["response_type"] == "code" and fields["code_challenge_method"] == "S256"
        assert fields["resource"] == self.resource_uri and set(fields["scope"].split()) == {"openid", "mcp.read"}
        code = "code-" + secrets.token_urlsafe(32)
        self.codes[code] = {**fields, "subject": subject}
        return (
            self.redirect_uri + "?" + urlencode({"code": code, "state": fields["state"], "iss": self.origin + "/oauth"})
        )

    def issue(self, grant, *, initial=False):
        token = "access-" + grant["subject"] + "-" + secrets.token_urlsafe(24)
        refresh = "refresh-" + grant["subject"] + "-" + secrets.token_urlsafe(24)
        self.access_tokens[token] = grant
        expiry = self.initial_expiry_seconds if initial else 3600
        self.access_expiry[token] = time.time() + expiry
        self.refresh_tokens[refresh] = grant
        claims = {
            "iss": self.origin + "/oauth",
            "aud": self.client_id,
            "sub": grant["subject"],
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "nonce": grant["nonce"],
            "at_hash": base64.urlsafe_b64encode(hashlib.sha256(token.encode()).digest()[:16]).rstrip(b"=").decode(),
        }
        value = {
            "access_token": token,
            "refresh_token": refresh,
            "token_type": "Bearer",
            "expires_in": expiry,
            "scope": "openid mcp.read",
            "resource": self.resource_uri,
            "id_token": jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": "oauth-fixture-key"}),
        }
        if self.mutate_token:
            value = self.mutate_token(value, claims)
        return value

    async def handle(self, request):
        self.requests.append(request)
        path = request.url.path
        if path == self.resource_metadata_path:
            return httpx.Response(
                200,
                json={
                    "resource": self.resource_uri,
                    "authorization_servers": [self.origin + "/oauth"],
                    "scopes_supported": ["mcp.read"],
                },
            )
        if path == "/.well-known/oauth-authorization-server/oauth":
            return httpx.Response(200, json=self.metadata())
        if path == "/oauth/jwks":
            return httpx.Response(200, json={"keys": [self.jwk]})
        if path in {"/oauth/token", "/oauth/revoke"}:
            data = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
            if data.get("client_id") != self.client_id and not request.headers.get("authorization", "").startswith(
                "Basic "
            ):
                return httpx.Response(401, json={"error": "invalid_client"})
            if path == "/oauth/revoke":
                self.revocations.append(data["token"])
                self.access_tokens.pop(data["token"], None)
                self.refresh_tokens.pop(data["token"], None)
                return httpx.Response(200, content=b"")
            if data.get("resource") != self.resource_uri:
                return httpx.Response(400, json={"error": "invalid_target"})
            if data.get("grant_type") == "authorization_code":
                grant = self.codes.pop(data.get("code"), None)
                actual = (
                    base64.urlsafe_b64encode(hashlib.sha256(data.get("code_verifier", "").encode()).digest())
                    .rstrip(b"=")
                    .decode()
                )
                if not grant or grant["code_challenge"] != actual or data.get("redirect_uri") != self.redirect_uri:
                    return httpx.Response(400, json={"error": "invalid_grant"})
            else:
                self.refreshes += 1
                if self.fail_refresh:
                    raise httpx.ReadError("synthetic rotating refresh response lost", request=request)
                grant = self.refresh_tokens.pop(data.get("refresh_token"), None)
                if self.refresh_started:
                    self.refresh_started.set()
                if self.refresh_release:
                    await self.refresh_release.wait()
                if not grant:
                    return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json=self.issue(grant, initial=data.get("grant_type") == "authorization_code"))
        if path == self.resource_path:
            token = request.headers.get("authorization", "").removeprefix("Bearer ")
            grant = self.access_tokens.get(token)
            if (
                not grant
                or self.access_expiry.get(token, 0) <= time.time()
                or grant.get("resource") != self.resource_uri
            ):
                return rpc_response(401, {"error": "invalid_token"})
            if request.method == "DELETE":
                return rpc_response(204)
            body = json.loads(request.content)
            if body["method"] == "notifications/initialized":
                return rpc_response(202)
            headers = {}
            if body["method"] == "initialize":
                result = {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "oauth-fixture-mcp", "version": "1"},
                }
                headers["Mcp-Session-Id"] = secrets.token_hex(12)
            elif body["method"] == "tools/list":
                result = {
                    "tools": [
                        {
                            "name": "lookup_identity",
                            "description": "Synthetic OAuth identity",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"query": {"type": "string"}},
                                "required": ["query"],
                            },
                        }
                    ]
                }
            else:
                self.effects.append(grant["subject"])
                result = {
                    "content": [{"type": "text", "text": grant["subject"]}],
                    "structuredContent": {"subject": grant["subject"]},
                }
            return rpc_response(200, {"jsonrpc": "2.0", "id": body["id"], "result": result}, headers)
        return httpx.Response(404, json={"error": "not_found"})


def register_fixture(app, fixture, subjects):
    """Only the finite synthetic preview calls this. It is not a production authorization server."""
    import html
    from fastapi import Request
    from fastapi.responses import HTMLResponse, RedirectResponse, Response

    @app.get("/oauth/authorize")
    async def authorize(request: Request):
        if len(str(request.url)) > 16384:
            return Response(status_code=413)
        params = dict(request.query_params)
        ticket = secrets.token_urlsafe(24)
        fixture.authorizations[ticket] = params
        choices = "".join(
            '<option value="' + html.escape(subject, quote=True) + '">' + html.escape(subject) + "</option>"
            for subject in subjects
        )
        return HTMLResponse(
            "<!doctype html><title>合成 MCP OAuth 授权</title><h1>选择合成源系统身份</h1>"
            "<p>这不是公司真实账号；仅用于验证状态、PKCE、nonce 和独立凭据网关。</p>"
            '<form method="post" action="/oauth/consent"><input type="hidden" name="request_id" value="' + ticket + '">'
            '<select name="subject">' + choices + '</select><button type="submit">确认授权</button></form>',
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )

    @app.post("/oauth/consent")
    async def consent(request: Request):
        raw = await request.body()
        if len(raw) > 8192:
            return Response(status_code=413)
        values = parse_qs(raw.decode())
        ticket = values.get("request_id", [""])[0]
        params = fixture.authorizations.pop(ticket, None)
        subject = values.get("subject", [""])[0]
        if params is None or subject not in subjects:
            return Response(status_code=400)
        return RedirectResponse(
            fixture.authorize(params, subject),
            status_code=303,
            headers={"Referrer-Policy": "no-referrer", "Cache-Control": "no-store"},
        )

    async def endpoint(request: Request):
        body = await request.body()
        if len(body) > 65536:
            return Response(status_code=413)
        result = await fixture.handle(
            httpx.Request(request.method, str(request.url), headers=request.headers, content=body)
        )
        content = await result.aread()
        return Response(content, status_code=result.status_code, headers=dict(result.headers))

    for path in (fixture.resource_metadata_path, "/.well-known/oauth-authorization-server/oauth", "/oauth/jwks"):
        app.add_api_route(path, endpoint, methods=["GET"])
    for path in ("/oauth/token", "/oauth/revoke"):
        app.add_api_route(path, endpoint, methods=["POST"])
    app.add_api_route(fixture.resource_path, endpoint, methods=["POST", "DELETE"])

    @app.get("/oauth/verification")
    async def verification():
        private = [r for r in fixture.requests if r.url.path in {"/oauth/token", fixture.resource_path}]
        return {
            "fixture_only": True,
            "refresh_count": fixture.refreshes,
            "revocation_count": len(fixture.revocations),
            "subjects_called": list(fixture.effects),
            "gateway_forwarded_platform_cookie": any("cookie" in r.headers for r in private),
        }
