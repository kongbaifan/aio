"""compat 开关与几处平台/配置健壮性。

supportsDeveloperRole 和 supportsReasoningEffort 此前都是死配置：
前者只有 developer→system 的降级路径，而代码库里没有任何地方产出 developer
角色，等于空转，默认值 True 的方向也是反的；后者解析后零引用，
models.json 里三个 provider 都认真配了它，实际从不生效。
"""

import json
from pathlib import Path

import httpx
import pytest

from app.llm.openai_compatible import OpenAICompatibleClient, _prepare_messages
from app.llm.providers import ModelConfigError, ModelRef, ModelRegistry


def _ref(**kwargs) -> ModelRef:
    base = dict(
        provider="p",
        id="m",
        name="m",
        base_url="https://gw.example.com/v1",
        api="openai-completions",
        api_key="sk-test-key",
    )
    base.update(kwargs)
    return ModelRef(**base)


def _captured_payload(ref: ModelRef) -> dict:
    """发一次请求，把上游收到的 JSON body 抓出来。"""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = OpenAICompatibleClient(
        ref, timeout=5, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    import asyncio

    async def go():
        await client.respond([{"role": "system", "content": "S"}, {"role": "user", "content": "U"}], [])
        await client._client.aclose()

    asyncio.run(go())
    return seen


# --- supportsDeveloperRole --------------------------------------------------


def test_system_stays_system_by_default():
    """默认关闭：绝大多数 OpenAI 兼容网关只认 system。"""
    prepared = _prepare_messages(
        [{"role": "system", "content": "S"}], supports_developer_role=False
    )
    assert prepared[0]["role"] == "system"


def test_system_upgraded_to_developer_when_enabled():
    """开关打开时才升格。此前这条路径根本不存在，开关是空转的。"""
    prepared = _prepare_messages(
        [{"role": "system", "content": "S"}], supports_developer_role=True
    )
    assert prepared[0]["role"] == "developer"


def test_developer_downgraded_when_unsupported():
    prepared = _prepare_messages(
        [{"role": "developer", "content": "D"}], supports_developer_role=False
    )
    assert prepared[0]["role"] == "system"


def test_developer_role_default_is_off(tmp_path: Path, monkeypatch):
    """compat 不写时，默认必须是「不支持 developer」。"""
    models = tmp_path / "models.json"
    models.write_text(
        json.dumps(
            {
                "providers": {
                    "p": {
                        "baseUrl": "https://gw.example.com/v1",
                        "apiKey": "sk-test-key",
                        "models": [{"id": "m", "name": "m"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    ref = ModelRegistry.load(models_json=models).get_model("p", "m")
    assert ref.supports_developer_role is False


# --- supportsReasoningEffort ------------------------------------------------


def test_reasoning_effort_not_sent_by_default():
    assert "reasoning_effort" not in _captured_payload(_ref())


def test_reasoning_effort_needs_both_switch_and_value():
    # 只开开关、没配值：不发
    assert "reasoning_effort" not in _captured_payload(
        _ref(supports_reasoning_effort=True)
    )
    # 只配值、开关关着：也不发
    assert "reasoning_effort" not in _captured_payload(
        _ref(reasoning_effort="high", supports_reasoning_effort=False)
    )


def test_reasoning_effort_is_sent_when_configured():
    """两个条件都满足才下发——此前这个开关解析后零引用，是死配置。"""
    payload = _captured_payload(_ref(reasoning_effort="high", supports_reasoning_effort=True))
    assert payload["reasoning_effort"] == "high"


# --- 未知 model id ----------------------------------------------------------


def test_unknown_model_id_raises_instead_of_silent_fallback(tmp_path: Path):
    """打错 model id 要在本地报错，而不是拼个组合发给上游拿回看不懂的 400。"""
    models = tmp_path / "models.json"
    models.write_text(
        json.dumps(
            {
                "providers": {
                    "deepseek": {
                        "baseUrl": "https://api.deepseek.com",
                        "apiKey": "sk-test-key",
                        "models": [{"id": "deepseek-chat", "name": "Chat"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    registry = ModelRegistry.load(models_json=models)

    with pytest.raises(ModelConfigError) as err:
        registry.get_model("deepseek", "gpt-5.5")   # 别家的 model
    # 报错要指出可用项，便于定位
    assert "deepseek-chat" in str(err.value)


# --- 平台细节 ---------------------------------------------------------------


def test_windows_command_split_keeps_backslashes(monkeypatch):
    """shlex 默认 POSIX 模式会把 Windows 路径的反斜杠当转义符吃掉。"""
    from app.clients import browser

    monkeypatch.setattr(browser.os, "name", "nt")
    parts = browser._split_command(r"C:\tools\agent-browser.exe")
    assert parts == [r"C:\tools\agent-browser.exe"]

    parts = browser._split_command(r'"C:\Program Files\node\node.exe" C:\tools\b.js')
    assert parts == [r"C:\Program Files\node\node.exe", r"C:\tools\b.js"]


def test_client_timeout_exceeds_server_execution_timeout():
    """客户端超时必须明显大于服务端执行超时，否则超时归因会随机。"""
    from app.clients.node_repl import DEFAULT_TIMEOUT_SECONDS as node_timeout
    from app.clients.sandbox import DEFAULT_TIMEOUT_SECONDS as sandbox_timeout

    # 服务端默认 SANDBOX_EXECUTION_TIMEOUT=30、node REPL 请求体 timeout=30000ms
    assert sandbox_timeout > 30
    assert node_timeout > 30
