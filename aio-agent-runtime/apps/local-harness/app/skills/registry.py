from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


DOMAIN_KEYWORDS: dict[str, set[str]] = {
    "doc": {"文档", "word", "docx", "pdf", "报告", "简历"},
    "sheets": {"表格", "excel", "xlsx", "csv", "数据", "图表"},
    "browser": {"浏览器", "网页", "网站", "登录", "截图", "点击"},
    "calendar": {"日历", "日程", "会议", "预约"},
    "mail": {"邮件", "邮箱", "mail"},
    "ppt": {"ppt", "演示文稿", "幻灯片"},
    "project": {"项目", "任务", "进度", "okr"},
}


# 单个 skill 文件的读取上限；SKILL.md 最大的也只有 600 多行，超过这个量级多半不是文档。
MAX_SKILL_FILE_BYTES = 262144


@dataclass(frozen=True)
class SkillInfo:
    name: str
    description: str
    path: str
    # 相对 skill root 的目录，如 business/lark-minutes。模型据此拼 read_skill 的路径。
    directory: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    result: dict[str, str] = {}
    lines = parts[1].splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        # 缩进块的范围：从当前位置起，所有空行和以空白开头的行都属于上一个键。
        def _consume_block() -> list[str]:
            nonlocal index
            block: list[str] = []
            while index < len(lines):
                candidate = lines[index]
                if candidate.strip() and not candidate[:1].isspace():
                    break  # 回到顶层键，块结束
                block.append(candidate.strip())
                index += 1
            return block

        # YAML 块标量：`|` 保留换行，`>` 折叠成空格（后面可跟 - / + 表示 chomping）。
        # 不支持的话 description 会只剩一个 "|"，该 skill 对模型等于不存在。
        if value[:1] in {"|", ">"}:
            block = _consume_block()
            if value[0] == "|":
                result[key] = "\n".join(block).strip()
            else:
                result[key] = " ".join(part for part in block if part).strip()
            continue

        # 嵌套映射（如 metadata:）：整块跳过，否则子键会被当成顶层键混进来。
        if not value:
            _consume_block()
            result[key] = ""
            continue

        if value.startswith('"'):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = value.strip('"')
        result[key] = value
    return result


class SkillRegistry:
    """扫描项目内的 SKILL.md，并按任务关键词选择少量相关 Skill。"""

    def __init__(self, roots: tuple[Path, ...]):
        self.roots = roots
        self.skills = self._load()

    def _load(self) -> list[SkillInfo]:
        skills: list[SkillInfo] = []
        seen: set[str] = set()
        for root in self.roots:
            if not root.exists():
                continue
            for path in root.rglob("SKILL.md"):
                try:
                    metadata = _frontmatter(path.read_text(encoding="utf-8"))
                except OSError:
                    continue
                name = metadata.get("name") or path.parent.name
                if name in seen:
                    continue
                seen.add(name)
                try:
                    directory = path.parent.relative_to(root).as_posix()
                except ValueError:
                    directory = path.parent.name
                skills.append(
                    SkillInfo(
                        name=name,
                        description=metadata.get("description", ""),
                        path=str(path),
                        directory=directory,
                    )
                )
        return sorted(skills, key=lambda item: item.name)

    def list(self) -> list[SkillInfo]:
        return self.skills

    def match(self, query: str, limit: int = 3) -> list[SkillInfo]:
        normalized = query.lower()
        scored: list[tuple[int, SkillInfo]] = []
        for skill in self.skills:
            score = 0
            name_parts = [part for part in re.split(r"[-_]", skill.name.lower()) if len(part) > 2]
            score += sum(5 for part in name_parts if part in normalized)
            haystack = f"{skill.name} {skill.description}".lower()
            for domain, words in DOMAIN_KEYWORDS.items():
                if domain in skill.name.lower():
                    score += sum(3 for word in words if word in normalized)
                elif any(word in normalized and word in haystack for word in words):
                    score += 1
            if score:
                scored.append((score, skill))
        scored.sort(key=lambda item: (-item[0], item[1].name))
        return [item[1] for item in scored[:limit]]

    def context(self, matches: list[SkillInfo]) -> str:
        """给出完整 skill 目录，并把关键词匹配到的几个标为优先查看。

        以前这里只列匹配到的 3 个、且只给一句 description。问题是关键词表只有 7 个域，
        覆盖不了全部 skill——「请假审批」「考勤」「发消息」这类都会落空，模型连 skill
        存在都不知道。全部 30 个 skill 的 description 合计约 3k token，直接全给更可靠，
        让模型自己判断，再用 read_skill 读正文。
        """
        if not self.skills:
            return ""
        lines = [
            "## 可用 Skill",
            "",
            "下面是本地 skill 目录。description 只是索引，**具体命令、参数和流程都在各自的 "
            "SKILL.md 里**，需要时用 read_skill 工具读取，不要凭 description 猜。",
            "SKILL.md 内如果要求先读某个 references 文档，必须照做后再动手。",
            "路径相对 skill 根目录，例如 read_skill(\"business/lark-minutes/SKILL.md\")。",
            "",
        ]
        if matches:
            hint = "、".join(item.name for item in matches)
            lines.append(f"关键词初筛认为可能相关（仅供参考，不一定准）：{hint}")
            lines.append("")
        for item in self.skills:
            location = item.directory or item.name
            description = " ".join(item.description.split())[:500]
            lines.append(f"- {item.name}（{location}）：{description}")
        return "\n".join(lines)

    def read(self, path: str) -> dict[str, object]:
        """读取 skill 根目录内的文件，路径不得越界。

        skill 正文经常引用同级或邻近 skill 的 references 文档，agent 需要能读到它们；
        workspace 的 read_file 够不着这里，所以单独开一个受限入口。
        """
        cleaned = (path or "").strip().replace("\\", "/").lstrip("/")
        if not cleaned or "\x00" in cleaned:
            raise ValueError("path 不能为空")

        escaped = False
        for root in self.roots:
            base = root.resolve()
            candidate = (base / cleaned).resolve()
            try:
                candidate.relative_to(base)
            except ValueError:
                escaped = True
                continue
            if not candidate.is_file():
                continue
            size = candidate.stat().st_size
            if size > MAX_SKILL_FILE_BYTES:
                raise ValueError(f"文件超过 {MAX_SKILL_FILE_BYTES} 字节上限：{cleaned}")
            return {
                "path": cleaned,
                "content": candidate.read_text(encoding="utf-8", errors="replace"),
                "size": size,
            }

        if escaped:
            raise ValueError("path 越出 skill 目录边界")
        raise FileNotFoundError(f"skill 目录内没有这个文件：{cleaned}")

    def entries(self, directory: str = "") -> dict[str, object]:
        """列出 skill 根目录（或其子目录）下的条目，供 agent 查找 references。"""
        cleaned = (directory or "").strip().replace("\\", "/").strip("/")
        items: list[dict[str, str]] = []
        found = False
        for root in self.roots:
            base = root.resolve()
            target = (base / cleaned).resolve() if cleaned else base
            try:
                target.relative_to(base)
            except ValueError:
                continue
            if not target.is_dir():
                continue
            found = True
            for child in sorted(target.iterdir()):
                items.append(
                    {
                        "name": child.name,
                        "path": child.relative_to(base).as_posix(),
                        "type": "dir" if child.is_dir() else "file",
                    }
                )
        if not found:
            raise FileNotFoundError(f"skill 目录内没有这个路径：{cleaned or '.'}")
        return {"directory": cleaned or ".", "items": items}
