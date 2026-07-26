"""会话持久化。

以前 SessionStore 是纯内存的，进程一重启全部会话连同 token 统计一起消失。
现在变更同步落 SQLite，重启后能原样读回来。
"""

import json
import sqlite3
from pathlib import Path

import pytest

from app.llm.base import Usage
from app.sessions import SessionStore
from app.storage import SessionDatabase


@pytest.mark.asyncio
async def test_survives_restart(tmp_path: Path):
    db = tmp_path / "sessions.db"

    store = SessionStore(db)
    session = await store.get_or_create(None, "统计销售数据", provider="fastai", model="gpt-5.5")
    await store.append(session, {"role": "user", "content": "统计销售数据"})
    await store.append(session, {"role": "assistant", "content": "已生成 CSV"})
    await store.add_usage(session, Usage(12375, 38, calls=1))
    session_id = session.id
    await store.close()

    # 新进程重新打开同一个库
    revived = SessionStore(db)
    restored = await revived.get(session_id)

    assert restored is not None
    assert restored.title == "统计销售数据"
    assert restored.provider == "fastai"
    assert restored.model == "gpt-5.5"
    assert [item["content"] for item in restored.messages] == ["统计销售数据", "已生成 CSV"]
    assert restored.usage == Usage(12375, 38, calls=1)
    await revived.close()


@pytest.mark.asyncio
async def test_delete_removes_row(tmp_path: Path):
    db = tmp_path / "sessions.db"
    store = SessionStore(db)
    session = await store.get_or_create(None, "临时会话")
    await store.append(session, {"role": "user", "content": "x"})

    assert await store.delete(session.id) is True
    assert await store.delete(session.id) is False
    await store.close()

    revived = SessionStore(db)
    assert await revived.get(session.id) is None
    assert await revived.list() == []
    await revived.close()


@pytest.mark.asyncio
async def test_eviction_also_drops_from_disk(tmp_path: Path):
    """超过上限被淘汰的会话不该继续留在库里，否则重启会「复活」。"""
    db = tmp_path / "sessions.db"
    store = SessionStore(db, max_sessions=2)

    first = await store.get_or_create(None, "第一个")
    await store.get_or_create(None, "第二个")
    await store.get_or_create(None, "第三个")
    await store.close()

    revived = SessionStore(db)
    titles = {item.title for item in await revived.list()}

    assert first.title not in titles
    assert titles == {"第二个", "第三个"}
    await revived.close()


@pytest.mark.asyncio
async def test_message_cap_is_persisted(tmp_path: Path):
    db = tmp_path / "sessions.db"
    store = SessionStore(db)
    session = await store.get_or_create(None, "长会话")
    for index in range(210):
        await store.append(session, {"role": "user", "content": f"第 {index} 条"})
    await store.close()

    revived = SessionStore(db)
    restored = await revived.get(session.id)

    assert len(restored.messages) == 200
    assert restored.messages[0]["content"] == "第 10 条"
    await revived.close()


@pytest.mark.asyncio
async def test_in_memory_mode_writes_nothing(tmp_path: Path):
    """db_path 为 None 时保持旧行为，测试和临时进程都靠这个。"""
    store = SessionStore(None)
    session = await store.get_or_create(None, "内存会话")
    await store.append(session, {"role": "user", "content": "x"})
    await store.close()

    assert list(tmp_path.iterdir()) == []
    assert len(await store.list()) == 1


@pytest.mark.asyncio
async def test_set_model_is_persisted(tmp_path: Path):
    db = tmp_path / "sessions.db"
    store = SessionStore(db)
    session = await store.get_or_create(None, "换模型", provider="a", model="m1")
    await store.set_model(session.id, "deepseek", "deepseek-v4-pro")
    await store.close()

    revived = SessionStore(db)
    restored = await revived.get(session.id)

    assert (restored.provider, restored.model) == ("deepseek", "deepseek-v4-pro")
    await revived.close()


def test_corrupt_messages_column_does_not_break_startup(tmp_path: Path):
    """单条记录坏掉只该丢它的历史，不该让整个工作台起不来。"""
    db = tmp_path / "sessions.db"
    database = SessionDatabase(db)
    database.upsert(
        {
            "id": "ok",
            "title": "正常",
            "created_at": "2026-07-26T00:00:00+00:00",
            "updated_at": "2026-07-26T00:00:00+00:00",
            "provider": "",
            "model": "",
            "messages": [{"role": "user", "content": "hi"}],
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "usage_calls": 0,
        }
    )
    database.close()

    raw = sqlite3.connect(db)
    raw.execute("UPDATE sessions SET messages = ? WHERE id = ?", ("{不是 JSON", "ok"))
    raw.commit()
    raw.close()

    reopened = SessionDatabase(db)
    records = reopened.load_all()
    reopened.close()

    assert len(records) == 1
    assert records[0]["messages"] == []


def test_messages_are_stored_as_readable_json(tmp_path: Path):
    """中文不该被转成 \\uXXXX，方便直接查库排障。"""
    db = tmp_path / "sessions.db"
    database = SessionDatabase(db)
    database.upsert(
        {
            "id": "s1",
            "title": "中文",
            "created_at": "2026-07-26T00:00:00+00:00",
            "updated_at": "2026-07-26T00:00:00+00:00",
            "provider": "",
            "model": "",
            "messages": [{"role": "user", "content": "你好"}],
            "prompt_tokens": 1,
            "completion_tokens": 2,
            "usage_calls": 1,
        }
    )
    database.close()

    raw = sqlite3.connect(db)
    stored = raw.execute("SELECT messages FROM sessions WHERE id = 's1'").fetchone()[0]
    raw.close()

    assert "你好" in stored
    assert json.loads(stored)[0]["content"] == "你好"
