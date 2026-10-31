"""Bounded Chat Completions streaming for approved platform model versions.

No legacy ModelRegistry/.env/shell resolver is used. Endpoints and secret variable
names must be explicitly allowlisted by the operator; user content cannot select
them. No automatic HTTP retries after a potentially billed request.
"""

from __future__ import annotations

import codecs
import os
import re
from decimal import Decimal, ROUND_CEILING
from typing import AsyncIterator
from urllib.parse import urlsplit

import httpx

from ..observability import scrub
from ..platform_errors import PlatformError
from ..platform_settings import validate_endpoint
from .actions import strict_json
from .contracts import ModelTurn, PlannedCall, bounded_json


class ChatModel:
    def __init__(
        self,
        definition: dict,
        *,
        approved_origins: frozenset[str],
        secret_names: frozenset[str],
        production: bool,
        client: httpx.AsyncClient | None = None,
    ):
        self.definition = definition
        config = definition["config"]
        endpoint = validate_endpoint(config.get("endpoint", ""), "model endpoint", production=production)
        parts = urlsplit(endpoint)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in approved_origins:
            raise PlatformError("MODEL_ENDPOINT_DENIED", "Model endpoint is not operator-approved", 403)
        name = config.get("secret_env")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", name) or name not in secret_names:
            raise PlatformError("MODEL_SECRET_DENIED", "Model credential reference is not approved", 403)
        secret = os.environ.get(name, "")
        if not secret or len(secret) > 16384 or any(ord(ch) < 32 for ch in secret):
            raise PlatformError("MODEL_SECRET_UNAVAILABLE", "Model credential is unavailable", 503)
        # Every later scrub (tool results, audit, archive, logs) also removes this key in any encoding.
        scrub.register_material(secret)
        self._secret = secret
        self.endpoint = endpoint
        self.max_tokens = config.get("max_output_tokens", 2048)
        if type(self.max_tokens) is not int or not 1 <= self.max_tokens <= 32768:
            raise PlatformError("MODEL_CONFIG_INVALID", "Output token limit is invalid", 409)
        self.max_charge = self._decimal(config.get("max_call_charge"), positive=True)
        self.input_price = self._decimal(config.get("input_price_per_million"))
        self.output_price = self._decimal(config.get("output_price_per_million"))
        if config.get("currency", "USD") != "USD":
            raise PlatformError("MODEL_CONFIG_INVALID", "Unsupported billing currency", 409)
        self.max_tokens_field = config.get("max_tokens_field", "max_tokens")
        if self.max_tokens_field not in {"max_tokens", "max_completion_tokens"}:
            raise PlatformError("MODEL_CONFIG_INVALID", "Unsupported token-limit field", 409)
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(90, connect=10), trust_env=False, follow_redirects=False
        )
        self._owns_client = client is None

    @staticmethod
    def _decimal(raw, *, positive=False) -> Decimal:
        try:
            value = Decimal(str(raw))
            if not value.is_finite() or value < 0 or (positive and value == 0) or value.as_tuple().exponent < -6:
                raise ValueError
            return value
        except (ValueError, ArithmeticError):
            raise PlatformError(
                "MODEL_CONFIG_INVALID", "Model pricing and charge bounds must be finite decimals", 409
            ) from None

    def charge(self, turn: ModelTurn) -> Decimal | None:
        if turn.input_tokens is None:
            return None
        return (
            (Decimal(turn.input_tokens) * self.input_price + Decimal(turn.output_tokens) * self.output_price)
            / Decimal(1000000)
        ).quantize(Decimal("0.000001"), rounding=ROUND_CEILING)

    async def stream(self, messages: list[dict], tools: list[dict]) -> AsyncIterator[str | ModelTurn]:
        payload = {
            "model": self.definition["model"],
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            self.max_tokens_field: self.max_tokens,
        }
        if tools:
            payload["tools"] = tools
        bounded_json(payload, 1048576)
        content, tool_parts, usage, reason = [], {}, None, None
        content_bytes = 0
        buffer, total, done = "", 0, False
        decoder = codecs.getincrementaldecoder("utf-8")("strict")
        try:
            async with self.client.stream(
                "POST",
                self.endpoint,
                json=payload,
                headers={
                    "Authorization": "Bearer " + self._secret,
                    "Accept": "text/event-stream",
                    "Accept-Encoding": "identity",
                },
            ) as response:
                if response.status_code != 200:
                    # Upstream bodies may echo credentials; deliberately do not expose them.
                    raise PlatformError("MODEL_UPSTREAM_FAILED", "Model provider rejected the request", 502)
                if not response.headers.get("content-type", "").lower().startswith("text/event-stream"):
                    raise PlatformError(
                        "MODEL_PROTOCOL_INVALID", "Model provider did not return the approved stream protocol", 502
                    )
                if response.headers.get("content-encoding", "identity").lower() not in {"identity", ""}:
                    raise PlatformError("MODEL_PROTOCOL_INVALID", "Compressed model streams are not enabled", 502)
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > 2 * 1024 * 1024:
                        raise PlatformError("MODEL_OUTPUT_LIMIT", "Model stream exceeded its byte limit", 502)
                    buffer += decoder.decode(chunk)
                    if len(buffer.encode("utf-8")) > 262144:
                        raise PlatformError("MODEL_OUTPUT_LIMIT", "Model frame exceeded its byte limit", 502)
                    while "\n\n" in buffer or "\r\n\r\n" in buffer:
                        lf = buffer.find("\n\n")
                        crlf = buffer.find("\r\n\r\n")
                        index, length = (crlf, 4) if crlf >= 0 and (lf < 0 or crlf < lf) else (lf, 2)
                        frame, buffer = buffer[:index], buffer[index + length :]
                        data = "\n".join(
                            line[5:].lstrip(" ") for line in frame.splitlines() if line.startswith("data:")
                        )
                        if not data:
                            continue
                        if data == "[DONE]":
                            done = True
                            break
                        obj = strict_json(data.encode("utf-8"), max_bytes=262144)
                        if not isinstance(obj, dict) or "error" in obj:
                            raise ValueError("Invalid stream object")
                        if obj.get("usage") is not None:
                            u = obj["usage"]
                            if (
                                not isinstance(u, dict)
                                or type(u.get("prompt_tokens")) is not int
                                or type(u.get("completion_tokens")) is not int
                                or min(u["prompt_tokens"], u["completion_tokens"]) < 0
                            ):
                                raise ValueError("Invalid usage")
                            usage = (u["prompt_tokens"], u["completion_tokens"])
                        choices = obj.get("choices", [])
                        if not isinstance(choices, list) or len(choices) > 1:
                            raise ValueError("Unsupported choices")
                        if not choices:
                            continue
                        choice = choices[0]
                        if choice.get("index", 0) != 0:
                            raise ValueError("Unsupported choice index")
                        if choice.get("finish_reason") is not None:
                            reason = choice["finish_reason"]
                        delta = choice.get("delta", {})
                        text_delta = delta.get("content")
                        if text_delta is not None:
                            if not isinstance(text_delta, str):
                                raise ValueError("Non-text content delta")
                            content_bytes += len(text_delta.encode("utf-8"))
                            if content_bytes > 262144:
                                raise ValueError("Content too large")
                            content.append(text_delta)
                            yield text_delta
                        calls = delta.get("tool_calls", [])
                        if not isinstance(calls, list) or len(calls) > 16:
                            raise ValueError("Too many tool calls")
                        for item in calls:
                            idx = item.get("index")
                            if type(idx) is not int or not 0 <= idx < 16 or item.get("type", "function") != "function":
                                raise ValueError("Invalid tool index/type")
                            part = tool_parts.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                            fn = item.get("function", {})
                            for key, value in [
                                ("id", item.get("id")),
                                ("name", fn.get("name")),
                                ("arguments", fn.get("arguments")),
                            ]:
                                if value is not None:
                                    if not isinstance(value, str):
                                        raise ValueError("Invalid tool fragment")
                                    part[key] += value
                            if (
                                len(part["arguments"].encode("utf-8")) > 65536
                                or len(part["id"]) > 128
                                or len(part["name"]) > 64
                            ):
                                raise ValueError("Tool frame limit")
                    if done:
                        break
                decoder.decode(b"", final=True)
                if not done or reason not in {"stop", "tool_calls", "length"}:
                    raise ValueError("Incomplete model stream")
        except (httpx.HTTPError, UnicodeError, ValueError, TypeError, AttributeError, KeyError):
            raise PlatformError(
                "MODEL_STREAM_INCOMPLETE", "Model response could not be safely completed", 502
            ) from None
        calls = tuple(
            PlannedCall(
                id=p["id"], name=p["name"], arguments=strict_json(p["arguments"].encode("utf-8"), max_bytes=65536)
            )
            for _, p in sorted(tool_parts.items())
        )
        turn = ModelTurn(
            content="".join(content),
            tool_calls=calls,
            input_tokens=usage[0] if usage else None,
            output_tokens=usage[1] if usage else None,
            finish_reason=reason,
        )
        yield turn

    async def close(self):
        if self._owns_client:
            await self.client.aclose()
        self._secret = ""


class ModelFactory:
    def __init__(self, *, approved_origins: frozenset[str], secret_names: frozenset[str], production: bool):
        self.approved_origins, self.secret_names, self.production = approved_origins, secret_names, production

    def create(self, definition: dict) -> ChatModel:
        return ChatModel(
            definition,
            approved_origins=self.approved_origins,
            secret_names=self.secret_names,
            production=self.production,
        )
