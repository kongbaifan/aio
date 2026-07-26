import asyncio
import json
from pathlib import Path
from typing import Any

from .models import utc_now_iso


class AuditLogger:
    """以 JSON Lines 追加审计事件，写失败时不影响主任务执行。

    按大小轮转：超过 max_bytes 就把当前文件挪成 .1，旧的依次后移，
    超出 backup_count 的最老一份删掉。工具参数和模型回答都会进来，
    长期跑不轮转的话这个文件会一直涨。
    """

    def __init__(self, path: Path, max_bytes: int = 5 * 1024 * 1024, backup_count: int = 3):
        self.path = path
        self.max_bytes = max(0, max_bytes)
        self.backup_count = max(0, backup_count)
        self._lock = asyncio.Lock()

    async def write(self, event: str, payload: dict[str, Any]) -> None:
        record = {"timestamp": utc_now_iso(), "event": event, **payload}
        try:
            async with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                await asyncio.to_thread(self._append, record)
        except OSError:
            # 审计磁盘不可写时由健康检查暴露，不在这里中断 Agent 主流程。
            return

    def _backup_path(self, index: int) -> Path:
        return self.path.with_name(f"{self.path.name}.{index}")

    def _rotate_if_needed(self) -> None:
        """max_bytes 为 0 表示不轮转。"""
        if self.max_bytes <= 0 or not self.path.exists():
            return
        if self.path.stat().st_size < self.max_bytes:
            return
        if self.backup_count == 0:
            self.path.unlink()
            return
        oldest = self._backup_path(self.backup_count)
        if oldest.exists():
            oldest.unlink()
        # 从旧到新依次后移，避免覆盖还没挪走的那一份
        for index in range(self.backup_count - 1, 0, -1):
            source = self._backup_path(index)
            if source.exists():
                source.replace(self._backup_path(index + 1))
        self.path.replace(self._backup_path(1))

    def _append(self, record: dict[str, Any]) -> None:
        self._rotate_if_needed()
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
