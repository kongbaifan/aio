"""会话详情接口。

会话已经落 SQLite 了，但一直没有接口能把历史消息取回来——
前端点开旧会话只切了 id，对话区是空的，存下来的数据用不到。
"""

import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.llm.base import Usage
from app.main import RuntimeContainer, create_app


def _make_app(tmp_path: Path, monkeypatch):
    models_json = tmp_path / "models.json"
    models_json.write_text(
        json.dumps(
            {
                "default": {"provider": "fake", "model": "fake-1"},
                "providers": {
                    "fake": {
                        "baseUrl": "http://127.0.0.1:9",
                        "api": "openai-completions",
                        "apiKey": "test-key",
                        "models": [{"id": "fake-1", "name": "fake-1", "maxTokens": 128}],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HARNESS_MODELS_JSON", str(models_json))
    monkeypatch.setenv("HARNESS_SKILL_ROOTS", str(tmp_path))
    monkeypatch.delenv("HARNESS_ENV_FILE", raising=False)
    monkeypatch.delenv("HARNESS_TOKEN", raising=False)

    settings = Settings.from_env()
    app = create_app(settings)
    app.state.runtime = RuntimeContainer(settings)
    return app, app.state.runtime


async def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )


@pytest.mark.asyncio
async def test_returns_full_history(tmp_path: Path, monkeypatch):
    app, container = _make_app(tmp_path, monkeypatch)
    session = await container.sessions.get_or_create(
        None, "统计销售数据", provider="fake", model="fake-1"
    )
    await container.sessions.append(session, {"role": "user", "content": "统计销售数据"})
    await container.sessions.append(session, {"role": "assistant", "content": "已生成 CSV"})
    await container.sessions.add_usage(session, Usage(12375, 38, calls=1))

    async with await _client(app) as client:
        response = await client.get(f"/api/sessions/{session.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "统计销售数据"
    assert body["message_count"] == 2
    assert [item["content"] for item in body["messages"]] == ["统计销售数据", "已生成 CSV"]
    assert body["usage"]["total_tokens"] == 12413
    assert body["provider"] == "fake"
    await container.close()


@pytest.mark.asyncio
async def test_unknown_session_is_404(tmp_path: Path, monkeypatch):
    app, container = _make_app(tmp_path, monkeypatch)

    async with await _client(app) as client:
        response = await client.get("/api/sessions/nope")

    assert response.status_code == 404
    await container.close()


@pytest.mark.asyncio
async def test_list_stays_lightweight(tmp_path: Path, monkeypatch):
    """列表接口不该带上整段历史，否则侧边栏一次要拉全部会话的消息。"""
    app, container = _make_app(tmp_path, monkeypatch)
    session = await container.sessions.get_or_create(None, "会话")
    await container.sessions.append(session, {"role": "user", "content": "x" * 500})

    async with await _client(app) as client:
        body = (await client.get("/api/sessions")).json()

    assert body["sessions"][0]["message_count"] == 1
    assert "messages" not in body["sessions"][0]
    await container.close()


@pytest.mark.asyncio
async def test_detail_survives_restart(tmp_path: Path, monkeypatch):
    """重启后仍能通过接口把历史读回来——持久化到接口这条链路是通的。"""
    app, container = _make_app(tmp_path, monkeypatch)
    session = await container.sessions.get_or_create(None, "跨重启")
    await container.sessions.append(session, {"role": "user", "content": "重启前说的话"})
    session_id = session.id
    await container.close()

    revived_app, revived = _make_app(tmp_path, monkeypatch)
    async with await _client(revived_app) as client:
        body = (await client.get(f"/api/sessions/{session_id}")).json()

    assert [item["content"] for item in body["messages"]] == ["重启前说的话"]
    await revived.close()
