import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .llm.base import Usage
from .models import SessionSummary
from .storage import SessionDatabase


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Session:
    id: str
    title: str
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    messages: list[dict[str, Any]] = field(default_factory=list)
    # 会话级模型选择；新建时从默认拷贝，下拉切换后写回。
    provider: str = ""
    model: str = ""
    # 本会话累计的 token 消耗（跨轮、跨 team 步骤累加）
    usage: Usage = field(default_factory=Usage)

    def to_record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "provider": self.provider,
            "model": self.model,
            "messages": self.messages,
            "prompt_tokens": self.usage.prompt_tokens,
            "completion_tokens": self.usage.completion_tokens,
            "usage_calls": self.usage.calls,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "Session":
        return cls(
            id=record["id"],
            title=record["title"],
            created_at=record["created_at"],
            updated_at=record["updated_at"],
            messages=record["messages"],
            provider=record["provider"],
            model=record["model"],
            usage=Usage(
                prompt_tokens=record["prompt_tokens"],
                completion_tokens=record["completion_tokens"],
                calls=record["usage_calls"],
            ),
        )


class SessionStore:
    """会话存储：内存里保持一份，变更同步落 SQLite。

    db_path 为 None 时退化为纯内存（测试和临时进程用）。

    内存副本是进程内的唯一读路径，所以多 worker 部署会读到各自的缓存——
    当前 harness 是单进程 uvicorn，够用；真要多 worker 得改成每次读库。
    """

    def __init__(self, db_path: Path | str | None = None, max_sessions: int = 50):
        self.max_sessions = max_sessions
        self._sessions: dict[str, Session] = {}
        self._lock = asyncio.Lock()
        self._db = SessionDatabase(Path(db_path)) if db_path else None
        if self._db is not None:
            for record in self._db.load_all():
                session = Session.from_record(record)
                self._sessions[session.id] = session

    async def close(self) -> None:
        if self._db is not None:
            await asyncio.to_thread(self._db.close)

    async def _persist(self, session: Session) -> None:
        """把一个会话写回库。调用方必须已持有 _lock。"""
        if self._db is None:
            return
        await asyncio.to_thread(self._db.upsert, session.to_record())

    async def _forget(self, session_id: str) -> None:
        if self._db is None:
            return
        await asyncio.to_thread(self._db.delete, session_id)

    async def get_or_create(
        self,
        session_id: str | None,
        title: str,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> Session:
        async with self._lock:
            if session_id and session_id in self._sessions:
                session = self._sessions[session_id]
                if provider:
                    session.provider = provider
                if model:
                    session.model = model
                session.updated_at = _now()
                await self._persist(session)
                return session
            if len(self._sessions) >= self.max_sessions:
                oldest = min(self._sessions.values(), key=lambda item: item.updated_at)
                self._sessions.pop(oldest.id, None)
                await self._forget(oldest.id)
            new_id = session_id or uuid.uuid4().hex[:12]
            session = Session(
                id=new_id,
                title=title[:40] or "新会话",
                provider=provider or "",
                model=model or "",
            )
            self._sessions[new_id] = session
            await self._persist(session)
            return session

    async def get(self, session_id: str | None) -> Session | None:
        if not session_id:
            return None
        async with self._lock:
            return self._sessions.get(session_id)

    async def set_model(self, session_id: str, provider: str, model: str) -> Session | None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            session.provider = provider
            session.model = model
            session.updated_at = _now()
            await self._persist(session)
            return session

    async def append(self, session: Session, message: dict[str, Any]) -> None:
        async with self._lock:
            session.messages.append(message)
            session.messages = session.messages[-200:]
            session.updated_at = _now()
            await self._persist(session)

    async def add_usage(self, session: Session, usage: Usage) -> None:
        """累加一次模型调用的消耗；team 模式各步骤共享会话，会累加到同一处。"""
        if not usage.calls and not usage.total_tokens:
            return
        async with self._lock:
            session.usage = session.usage + usage
            session.updated_at = _now()
            await self._persist(session)

    async def list(self) -> list[SessionSummary]:
        async with self._lock:
            sessions = sorted(self._sessions.values(), key=lambda item: item.updated_at, reverse=True)
            return [
                SessionSummary(
                    id=item.id,
                    title=item.title,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                    message_count=len(item.messages),
                    provider=item.provider,
                    model=item.model,
                    usage=item.usage.to_dict(),
                )
                for item in sessions
            ]

    async def delete(self, session_id: str) -> bool:
        async with self._lock:
            removed = self._sessions.pop(session_id, None) is not None
            if removed:
                await self._forget(session_id)
            return removed
