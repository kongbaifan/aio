"""OpenAI Chat Completions 兼容客户端（pi-ai openai-completions 风格）。

支持：
- 流式 / 非流式
- tools + tool_choice
- 错误响应体回传
- 429/5xx 有限重试
- compat：developer 角色、max_tokens 字段名
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlsplit

import httpx

from .base import AssistantTurn, TextDelta, ToolCall, Usage
from .providers import ModelRef

logger = logging.getLogger(__name__)


class LlmError(RuntimeError):
    """模型 HTTP 或协议层错误。"""

    def __init__(self, message: str, *, status_code: int | None = None, body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


# 常见密钥形态：sk- / key- / Bearer xxx / AIza / GitHub token / Slack token。
# one-api 系网关的错误体经常回显请求头甚至完整请求，这里先脱敏再进异常消息。
_SECRET_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9_-]{8,}|key-[A-Za-z0-9]{8,}|Bearer\s+[A-Za-z0-9._~+/-]{8,}"
    r"|AIza[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9]{8,}|xox[baprs]-[A-Za-z0-9-]{8,})"
)

# 进异常消息（进而进 SSE error 帧和审计日志）的上游响应体上限。
# 诊断只需要开头一小段：更长的内容徒增日志体积，还扩大回显面。
_ERROR_BODY_LIMIT = 200


def _sanitize_upstream(text: str, limit: int = _ERROR_BODY_LIMIT) -> str:
    """截短并脱敏上游响应体。

    这些文本最终会走两条路：SSE error 帧发到浏览器、audit.write 落进
    var/audit.jsonl。网关的错误体常常回显请求头 / token 前缀，等于把密钥写进
    日志，所以先截短、再抹掉疑似密钥，宁可多挡不可漏。
    """
    snippet = (text or "")[:limit]
    return _SECRET_PATTERN.sub("[REDACTED]", snippet)


def _normalize_chat_url(base_url: str) -> str:
    """拼出 .../chat/completions；兼容 base 已含完整路径、含 /v1 或仅域名。

    只给 host 时补 /v1：这是 OpenAI 兼容接口的通行布局，https://api.openai.com
    不加就是 404。原实现的两个分支返回的是同一个表达式，注释写着「优先加 /v1」
    但代码没加。DeepSeek 两种都受理，所以补 /v1 对它无影响。
    带路径的 baseUrl（如 https://gw.example.com/api）保持原样，不擅自插 /v1。
    """
    root = base_url.rstrip("/")
    if root.endswith("/chat/completions"):
        return root
    path = urlsplit(root).path
    if not path or path == "/":
        return f"{root}/v1/chat/completions"
    return f"{root}/chat/completions"


def _prepare_messages(
    messages: list[dict[str, Any]],
    *,
    supports_developer_role: bool,
) -> list[dict[str, Any]]:
    """按 compat 调整 system/developer 角色。"""
    prepared: list[dict[str, Any]] = []
    for item in messages:
        msg = dict(item)
        role = msg.get("role")
        if role == "developer" and not supports_developer_role:
            msg["role"] = "system"
        elif role == "system" and supports_developer_role:
            # 保持 system；部分推理模型用 developer，本项目统一 system 更兼容
            pass
        prepared.append(msg)
    return prepared


class OpenAICompatibleClient:
    """调用 OpenAI Chat Completions 兼容接口，不绑定具体厂商 SDK。

    构造方式对齐 pi-ai：传入 ModelRef（由 get_model 得到），而不是散落的字符串。
    """

    def __init__(
        self,
        model: ModelRef | None = None,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model_id: str | None = None,
        timeout: float = 90,
        temperature: float = 0.1,
        max_tokens: int | None = None,
        max_retries: int = 2,
        provider: str = "custom",
        http_client: httpx.AsyncClient | None = None,
    ):
        if model is not None:
            self.model_ref = model
        else:
            if not api_key:
                raise ValueError(
                    "api_key is required：请在 config/models.json 对应 provider 下配置 apiKey"
                    "（写环境变量名，值放进 .env）"
                )
            if not base_url or not model_id:
                raise ValueError("base_url and model are required")
            self.model_ref = ModelRef(
                provider=provider,
                id=model_id,
                name=model_id,
                base_url=base_url.rstrip("/"),
                api="openai-completions",
                api_key=api_key,
                max_tokens=max_tokens,
            )
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens if max_tokens is not None else self.model_ref.max_tokens
        self.max_retries = max(0, max_retries)
        # http_client 仅供测试注入 MockTransport；生产路径不传，走默认真实客户端。
        self._client = http_client or httpx.AsyncClient(timeout=timeout)

    @property
    def model(self) -> str:
        return self.model_ref.id

    @property
    def base_url(self) -> str:
        return self.model_ref.base_url

    @property
    def provider(self) -> str:
        return self.model_ref.provider

    async def close(self) -> None:
        await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.model_ref.api_key}",
            "Content-Type": "application/json",
        }
        headers.update(self.model_ref.headers)
        return headers

    def _build_payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        stream: bool = False,
    ) -> dict[str, Any]:
        prepared = _prepare_messages(
            messages,
            supports_developer_role=self.model_ref.supports_developer_role,
        )
        payload: dict[str, Any] = {
            "model": self.model_ref.id,
            "messages": prepared,
            "temperature": self.temperature,
        }
        if self.max_tokens is not None:
            field = self.model_ref.max_tokens_field or "max_tokens"
            payload[field] = self.max_tokens
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if stream:
            payload["stream"] = True
            if self.model_ref.supports_stream_usage:
                # 让上游在最后一个 chunk 里附带 usage；该 chunk 的 choices 为空数组。
                payload["stream_options"] = {"include_usage": True}
        return payload

    async def _request_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = _normalize_chat_url(self.model_ref.base_url)
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.post(url, headers=self._headers(), json=payload)
                if response.status_code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                    wait = min(2**attempt, 8)
                    logger.warning(
                        "LLM %s %s，%ss 后重试 (%s/%s)",
                        response.status_code,
                        url,
                        wait,
                        attempt + 1,
                        self.max_retries,
                    )
                    await asyncio.sleep(wait)
                    continue
                if response.status_code >= 400:
                    body = _sanitize_upstream(response.text)
                    raise LlmError(
                        f"LLM request failed: HTTP {response.status_code} — {body}",
                        status_code=response.status_code,
                        body=body,
                    )
                try:
                    return response.json()
                except ValueError as exc:
                    raise LlmError(
                        f"LLM returned non-JSON body: {_sanitize_upstream(response.text)}"
                    ) from exc
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    wait = min(2**attempt, 8)
                    logger.warning("LLM 网络错误，%ss 后重试: %s", wait, exc)
                    await asyncio.sleep(wait)
                    continue
                raise LlmError(f"LLM request failed: {exc}") from exc
        raise LlmError(f"LLM request failed after retries: {last_error}")

    def _parse_assistant_message(self, message: dict[str, Any]) -> AssistantTurn:
        calls: list[ToolCall] = []
        for raw_call in message.get("tool_calls") or []:
            function = raw_call.get("function") or {}
            name = function.get("name") or ""
            raw_arguments = function.get("arguments", "{}")
            try:
                if isinstance(raw_arguments, str):
                    arguments = json.loads(raw_arguments) if raw_arguments.strip() else {}
                else:
                    arguments = raw_arguments
            except json.JSONDecodeError:
                # 不中断整轮：把坏参数当成空 dict，并在 name 侧由工具层报错
                logger.warning("工具 %s 参数 JSON 无效: %s", name, raw_arguments)
                arguments = {}
            if not isinstance(arguments, dict):
                arguments = {}
            calls.append(
                ToolCall(
                    id=raw_call.get("id") or uuid.uuid4().hex,
                    name=name,
                    arguments=arguments,
                )
            )
        content = message.get("content")
        if content is None:
            content = ""
        # DeepSeek reasoner 等把思考过程放在 reasoning_content。正常情况下两者
        # 都有，取 content 即可；但只返回 reasoning_content 时，原实现是
        # `content = ""`（空操作，写了等于没写），用户拿到一个空回答。
        # 宁可把思考过程给出去，也好过界面上什么都没有。
        if not content and not calls:
            reasoning = message.get("reasoning_content")
            if reasoning:
                content = str(reasoning)
        return AssistantTurn(content=str(content), tool_calls=calls)

    async def respond(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> AssistantTurn:
        data = await self._request_json(self._build_payload(messages, tools))
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmError(
                f"LLM response missing choices[0].message: {_sanitize_upstream(repr(data))}"
            ) from exc
        turn = self._parse_assistant_message(message)
        usage = Usage.from_payload(data.get("usage"))
        choice = (data.get("choices") or [{}])[0]
        return AssistantTurn(
            content=turn.content,
            tool_calls=turn.tool_calls,
            usage=usage if usage.calls else Usage(calls=1),
            finish_reason=str(choice.get("finish_reason") or ""),
        )

    async def _sleep_before_retry(self, attempt: int, reason: str) -> None:
        wait = min(2**attempt, 8)
        logger.warning("LLM 流式 %s，%ss 后重试 (%s/%s)", reason, wait, attempt + 1, self.max_retries)
        await asyncio.sleep(wait)

    async def respond_stream(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AsyncIterator["TextDelta | AssistantTurn"]:
        """带 tools 的流式调用。

        逐个 yield TextDelta（本次新增文本），流结束后 yield 一个聚合好的
        AssistantTurn（含完整 content 与解析后的 tool_calls）。调用方据此边收
        文本边推送，收完再判断这一轮是要调工具还是给最终答案。

        重试只发生在**建立连接阶段**（429/5xx、连接失败）：一旦开始 yield
        TextDelta，前端就已经把文本显示出来了，重来会导致内容重复，所以
        那之后的错误一律直接抛。此前流式路径完全没有重试，而工作台默认走
        流式，等于 LLM_MAX_RETRIES 对主路径无效。
        """
        url = _normalize_chat_url(self.model_ref.base_url)
        payload = self._build_payload(messages, tools, stream=True)
        content = ""
        reasoning = ""
        finish_reason = ""
        usage = Usage()
        # 按 index 累积 tool_call 分片：{index: {"id","name","arguments"}}
        tool_fragments: dict[int, dict[str, str]] = {}
        # 上游省略 index 时的兜底：按 call id 记住它属于第几个分片。
        # 不做这件事的话所有分片都落进 index 0，不同工具的 arguments 首尾相连
        # 拼成坏 JSON，解析失败后静默降级成 {}，第一个工具调用彻底消失。
        id_to_index: dict[str, int] = {}
        # 是否已经把内容推给上层。一旦为真就不能重试——前端已经显示了。
        emitted = False
        for attempt in range(self.max_retries + 1):
            try:
                async with self._client.stream(
                    "POST", url, headers=self._headers(), json=payload
                ) as response:
                    if response.status_code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                        await response.aread()  # 释放连接再重试
                        await self._sleep_before_retry(attempt, f"HTTP {response.status_code}")
                        continue
                    if response.status_code >= 400:
                        body = _sanitize_upstream(
                            (await response.aread()).decode("utf-8", errors="replace")
                        )
                        raise LlmError(
                            f"LLM stream failed: HTTP {response.status_code} — {body}",
                            status_code=response.status_code,
                            body=body,
                        )
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        # include_usage 的最后一个 chunk 里 choices 为空、只带 usage
                        if chunk.get("usage"):
                            usage = Usage.from_payload(chunk["usage"])
                        choice = (chunk.get("choices") or [{}])[0]
                        if choice.get("finish_reason"):
                            finish_reason = str(choice["finish_reason"])
                        delta = choice.get("delta") or {}
                        piece = delta.get("content") or ""
                        if piece:
                            content += piece
                            emitted = True
                            yield TextDelta(text=piece)
                        # 思考过程单独累起来，不混进正文的打字机；只有在正文最终
                        # 为空时才拿它兜底，免得 reasoner 模型给出一个空回答。
                        reasoning_piece = delta.get("reasoning_content") or ""
                        if reasoning_piece:
                            reasoning += reasoning_piece
                        for raw_call in delta.get("tool_calls") or []:
                            emitted = True
                            index = raw_call.get("index")
                            call_id = raw_call.get("id") or ""
                            if index is None:
                                # 没有 index：优先按 id 归组，连 id 都没有就新开一片。
                                if call_id and call_id in id_to_index:
                                    index = id_to_index[call_id]
                                else:
                                    index = len(tool_fragments)
                            try:
                                index = int(index)
                            except (TypeError, ValueError):
                                index = len(tool_fragments)
                            if call_id:
                                id_to_index.setdefault(call_id, index)
                            fragment = tool_fragments.setdefault(
                                index, {"id": "", "name": "", "arguments": ""}
                            )
                            if raw_call.get("id"):
                                fragment["id"] = raw_call["id"]
                            function = raw_call.get("function") or {}
                            if function.get("name"):
                                fragment["name"] = function["name"]
                            if function.get("arguments"):
                                fragment["arguments"] += function["arguments"]
                break  # 正常读完，跳出重试循环
            except httpx.HTTPError as exc:
                # 连接层错误：还没吐出任何内容且有剩余次数时才重试，
                # 否则重来会让前端已显示的文本重复一遍。
                if not emitted and attempt < self.max_retries:
                    await self._sleep_before_retry(attempt, f"网络错误 {exc}")
                    continue
                raise LlmError(f"LLM stream failed: {exc}") from exc

        calls: list[ToolCall] = []
        for index in sorted(tool_fragments):
            fragment = tool_fragments[index]
            if not fragment["name"]:
                continue
            raw_arguments = fragment["arguments"].strip()
            try:
                arguments = json.loads(raw_arguments) if raw_arguments else {}
            except json.JSONDecodeError:
                logger.warning("流式工具 %s 参数 JSON 无效: %s", fragment["name"], raw_arguments)
                arguments = {}
            if not isinstance(arguments, dict):
                arguments = {}
            calls.append(
                ToolCall(
                    id=fragment["id"] or uuid.uuid4().hex,
                    name=fragment["name"],
                    arguments=arguments,
                )
            )
        if usage.calls == 0:
            # 上游没上报 usage（不支持 include_usage 等），至少记下发生过一次调用，
            # 免得统计看起来像「一次都没调」。
            usage = Usage(calls=1)
        # 只有思考过程、没有正文时用它兜底（见 _parse_assistant_message 的同款处理）。
        if not content and not calls and reasoning:
            content = reasoning
        yield AssistantTurn(
            content=content, tool_calls=calls, usage=usage, finish_reason=finish_reason
        )

    async def complete(self, system: str, user: str) -> str:
        text, _ = await self.complete_with_usage(system, user)
        return text

    async def complete_with_usage(self, system: str, user: str) -> tuple[str, Usage]:
        data = await self._request_json(
            self._build_payload(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                tools=None,
            )
        )
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmError(
                f"LLM response missing choices[0].message: {_sanitize_upstream(repr(data))}"
            ) from exc
        usage = Usage.from_payload(data.get("usage"))
        return str(message.get("content") or ""), (usage if usage.calls else Usage(calls=1))

    async def stream_text(self, messages: list[dict[str, Any]]) -> AsyncIterator[str]:
        """流式输出纯文本（无 tools），yield 累计全文。"""
        url = _normalize_chat_url(self.model_ref.base_url)
        payload = self._build_payload(messages, tools=None, stream=True)
        full = ""
        try:
            async with self._client.stream("POST", url, headers=self._headers(), json=payload) as response:
                if response.status_code >= 400:
                    body = _sanitize_upstream(
                        (await response.aread()).decode("utf-8", errors="replace")
                    )
                    raise LlmError(
                        f"LLM stream failed: HTTP {response.status_code} — {body}",
                        status_code=response.status_code,
                        body=body,
                    )
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                    else:
                        continue
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                    piece = delta.get("content") or ""
                    if piece:
                        full += piece
                        yield full
        except httpx.HTTPError as exc:
            raise LlmError(f"LLM stream failed: {exc}") from exc
