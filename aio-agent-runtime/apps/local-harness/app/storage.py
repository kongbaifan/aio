"""会话的 SQLite 持久化层。

只负责存取，不含业务规则——淘汰策略、消息条数上限这些仍归 SessionStore 管。

用同步的 sqlite3 而不是 aiosqlite：本地单用户场景数据量很小（默认最多 50 个会话、
每个会话 200 条消息），调用方用 asyncio.to_thread 包一层就够，不值得为此多一个依赖。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id                TEXT PRIMARY KEY,
    title             TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    provider          TEXT NOT NULL DEFAULT '',
    model             TEXT NOT NULL DEFAULT '',
    messages          TEXT NOT NULL DEFAULT '[]',
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    usage_calls       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions (updated_at DESC);
"""


class SessionDatabase:
    """会话表的读写。每个会话整行覆写，消息以 JSON 存在一列里。

    消息不拆表是有意的：条数有上限、总是整段读取，一次 UPSERT 比增量插入更简单，
    也天然避免了消息与会话元数据写到一半不一致。
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        # WAL 让读写不互相阻塞；本地单进程也能少一些锁等待。
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(SCHEMA)
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def load_all(self) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def upsert(self, record: dict[str, Any]) -> None:
        self._connection.execute(
            """
            INSERT INTO sessions (
                id, title, created_at, updated_at, provider, model,
                messages, prompt_tokens, completion_tokens, usage_calls
            ) VALUES (
                :id, :title, :created_at, :updated_at, :provider, :model,
                :messages, :prompt_tokens, :completion_tokens, :usage_calls
            )
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                updated_at = excluded.updated_at,
                provider = excluded.provider,
                model = excluded.model,
                messages = excluded.messages,
                prompt_tokens = excluded.prompt_tokens,
                completion_tokens = excluded.completion_tokens,
                usage_calls = excluded.usage_calls
            """,
            {**record, "messages": json.dumps(record["messages"], ensure_ascii=False)},
        )
        self._connection.commit()

    def delete(self, session_id: str) -> None:
        self._connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self._connection.commit()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        try:
            messages = json.loads(row["messages"])
        except (TypeError, ValueError):
            # 单条记录损坏不该让整个工作台起不来，丢掉这条会话的历史即可。
            messages = []
        if not isinstance(messages, list):
            messages = []
        return {
            "id": row["id"],
            "title": row["title"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "provider": row["provider"],
            "model": row["model"],
            "messages": messages,
            "prompt_tokens": row["prompt_tokens"],
            "completion_tokens": row["completion_tokens"],
            "usage_calls": row["usage_calls"],
        }
