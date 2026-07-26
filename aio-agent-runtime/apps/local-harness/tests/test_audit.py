"""审计日志的写入与轮转。

工具参数和模型回答都会进这个文件，长期跑不轮转就会一直涨。
"""

import asyncio
import json
from pathlib import Path

import pytest

from app.audit import AuditLogger


def _read_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


@pytest.mark.asyncio
async def test_writes_json_lines_with_timestamp(tmp_path: Path):
    log = tmp_path / "audit.jsonl"
    logger = AuditLogger(log)

    await logger.write("tool.call", {"tool": "write_file", "status": "success"})
    await logger.write("agent.finish", {"rounds": 2})

    records = _read_lines(log)
    assert [item["event"] for item in records] == ["tool.call", "agent.finish"]
    assert records[0]["tool"] == "write_file"
    assert all(item["timestamp"] for item in records)


@pytest.mark.asyncio
async def test_chinese_stays_readable(tmp_path: Path):
    log = tmp_path / "audit.jsonl"
    await AuditLogger(log).write("tool.blocked", {"detail": "用户拒绝了该操作。"})

    assert "用户拒绝了该操作。" in log.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_rotates_when_over_limit(tmp_path: Path):
    log = tmp_path / "audit.jsonl"
    # 每条记录上百字节，200 字节上限意味着基本每写一两条就轮转一次
    logger = AuditLogger(log, max_bytes=200, backup_count=2)

    for index in range(12):
        await logger.write("tool.call", {"index": index, "padding": "x" * 80})

    assert log.exists()
    assert (tmp_path / "audit.jsonl.1").exists()
    assert (tmp_path / "audit.jsonl.2").exists()
    # 只保留 backup_count 份，第三份不该出现
    assert not (tmp_path / "audit.jsonl.3").exists()
    # 当前文件里是最新的那条
    assert _read_lines(log)[-1]["index"] == 11


@pytest.mark.asyncio
async def test_backups_shift_oldest_out(tmp_path: Path):
    log = tmp_path / "audit.jsonl"
    logger = AuditLogger(log, max_bytes=120, backup_count=1)

    await logger.write("first", {"padding": "a" * 150})
    await logger.write("second", {"padding": "b" * 150})
    await logger.write("third", {"padding": "c" * 150})

    # .1 应该是上一次的内容，更早的已经被挤掉
    assert _read_lines(tmp_path / "audit.jsonl.1")[0]["event"] == "second"
    assert _read_lines(log)[0]["event"] == "third"
    assert not (tmp_path / "audit.jsonl.2").exists()


@pytest.mark.asyncio
async def test_zero_backup_count_just_truncates(tmp_path: Path):
    log = tmp_path / "audit.jsonl"
    logger = AuditLogger(log, max_bytes=120, backup_count=0)

    await logger.write("first", {"padding": "a" * 150})
    await logger.write("second", {"padding": "b" * 150})

    assert not (tmp_path / "audit.jsonl.1").exists()
    assert [item["event"] for item in _read_lines(log)] == ["second"]


@pytest.mark.asyncio
async def test_rotation_disabled_when_max_bytes_zero(tmp_path: Path):
    log = tmp_path / "audit.jsonl"
    logger = AuditLogger(log, max_bytes=0, backup_count=3)

    for index in range(10):
        await logger.write("tool.call", {"index": index, "padding": "x" * 200})

    assert not (tmp_path / "audit.jsonl.1").exists()
    assert len(_read_lines(log)) == 10


@pytest.mark.asyncio
async def test_unwritable_path_does_not_raise(tmp_path: Path):
    """审计写不进去也不能中断 Agent 主流程。"""
    # 用一个已存在的文件当目录，mkdir 会失败
    blocker = tmp_path / "blocker"
    blocker.write_text("", encoding="utf-8")
    logger = AuditLogger(blocker / "nested" / "audit.jsonl")

    await logger.write("tool.call", {"tool": "write_file"})  # 不应抛异常


@pytest.mark.asyncio
async def test_concurrent_writes_do_not_interleave(tmp_path: Path):
    log = tmp_path / "audit.jsonl"
    logger = AuditLogger(log)

    await asyncio.gather(*(logger.write("tool.call", {"index": i}) for i in range(50)))

    records = _read_lines(log)
    assert len(records) == 50
    assert sorted(item["index"] for item in records) == list(range(50))
