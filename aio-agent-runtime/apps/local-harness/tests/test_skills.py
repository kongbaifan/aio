"""Skill 目录的读取入口与清单注入。

改造前：context() 只列关键词匹配到的 3 个 skill、只给一句 description，
而 SKILL.md 正文（全仓库 6000 多行操作指南）没有任何工具能读到——
skill 里写的「先读 ../xxx/references/yyy.md」对 agent 是够不着的。
"""

from pathlib import Path

import pytest

from app.skills.registry import SkillRegistry, _frontmatter
from app.tools.registry import ToolRegistry
from fakes import FakeBrowser, FakeNode, FakeSandbox


def _make_skills(root: Path) -> None:
    minutes = root / "business" / "lark-minutes"
    (minutes / "references").mkdir(parents=True)
    (minutes / "SKILL.md").write_text(
        '---\nname: lark-minutes\ndescription: "飞书妙记：查询、下载、生成会议纪要。"\n---\n\n'
        "# minutes\n\n开始前必须先读 ../lark-vc/references/boundaries.md。\n",
        encoding="utf-8",
    )
    (minutes / "references" / "api.md").write_text("# 妙记 API\n\nminutes +search\n", encoding="utf-8")

    vc = root / "business" / "lark-vc"
    (vc / "references").mkdir(parents=True)
    (vc / "SKILL.md").write_text(
        '---\nname: lark-vc\ndescription: "飞书视频会议。"\n---\n\n# vc\n', encoding="utf-8"
    )
    (vc / "references" / "boundaries.md").write_text("# 领域边界\n\n妙记和纪要相互独立。\n", encoding="utf-8")


@pytest.fixture()
def registry(tmp_path: Path) -> SkillRegistry:
    _make_skills(tmp_path)
    return SkillRegistry((tmp_path,))


def test_loads_skills_with_relative_directory(registry: SkillRegistry):
    names = {item.name: item.directory for item in registry.list()}

    assert names == {
        "lark-minutes": "business/lark-minutes",
        "lark-vc": "business/lark-vc",
    }


def test_read_skill_markdown(registry: SkillRegistry):
    result = registry.read("business/lark-minutes/SKILL.md")

    assert "# minutes" in result["content"]
    assert result["path"] == "business/lark-minutes/SKILL.md"
    assert result["size"] > 0


def test_read_reference_across_skills(registry: SkillRegistry):
    """SKILL.md 要求读的邻近 skill 参考文档必须够得着。"""
    result = registry.read("business/lark-vc/references/boundaries.md")

    assert "妙记和纪要相互独立" in result["content"]


@pytest.mark.parametrize(
    "path",
    [
        "../../../etc/passwd",
        "business/../../outside.md",
        # Windows 形态：盘符、反斜杠分隔符。项目主要跑在 Windows 上。
        "C:/Windows/win.ini",
        r"C:\Windows\win.ini",
        r"..\..\outside.md",
    ],
)
def test_read_rejects_paths_outside_skill_root(registry: SkillRegistry, tmp_path: Path, path: str):
    """越界必须是 ValueError（边界检查命中），不能是 FileNotFoundError。

    之前这里断言的是 (ValueError, FileNotFoundError)，等于没断言：
    "../../../etc/passwd" 在 Windows 上本来就不存在，把整段边界检查删掉它照样通过。
    """
    (tmp_path.parent / "outside.md").write_text("secret", encoding="utf-8")

    with pytest.raises(ValueError):
        registry.read(path)


@pytest.mark.parametrize("path", ["/etc/passwd", "//server/share/x.md"])
def test_absolute_paths_are_neutralized_into_root(registry: SkillRegistry, path: str):
    """绝对路径/UNC 被 lstrip 中和成 root 内的相对路径，因此是「找不到」而非「越界」。

    与上一个用例分开：它们测的不是边界检查，混在一起会让越界断言失去意义。
    """
    with pytest.raises(FileNotFoundError):
        registry.read(path)


def test_read_rejects_empty_path(registry: SkillRegistry):
    with pytest.raises(ValueError):
        registry.read("   ")


def test_read_missing_file(registry: SkillRegistry):
    with pytest.raises(FileNotFoundError):
        registry.read("business/lark-minutes/nope.md")


@pytest.mark.parametrize(
    ("style", "expected"),
    [("|", "第一行。\n第二行。"), (">", "第一行。 第二行。")],
)
def test_frontmatter_reads_block_scalar_description(tmp_path: Path, style: str, expected: str):
    """YAML 块标量（| 和 >）必须解析出正文。

    不支持的话 description 只剩一个 "|"，该 skill 在注入 system prompt 的清单里
    等于没有描述，模型不会知道它存在——仓库里的 lark-project / lark-whiteboard
    正是这样静默消失的。
    """
    skill = tmp_path / "business" / "demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: demo\ndescription: {style}\n  第一行。\n  第二行。\nversion: 1.0\n---\n\n# demo\n",
        encoding="utf-8",
    )

    info = next(item for item in SkillRegistry((tmp_path,)).list() if item.name == "demo")
    assert info.description == expected


def test_frontmatter_skips_nested_mapping():
    """嵌套映射（metadata: 之类）的子键不能被当成顶层键混进来。

    直接测 _frontmatter 而不是走 SkillInfo：污染发生在 requires / bins 这些
    SkillInfo 不暴露的键上，只断言 description 的话，把跳过逻辑删掉测试照样绿。
    """
    result = _frontmatter(
        "---\nname: demo\nmetadata:\n  requires: lark-cli\n  bins: foo\n"
        "description: 正常描述。\n---\n\n# demo\n"
    )

    assert result["description"] == "正常描述。"
    assert result["metadata"] == ""
    # 关键断言：嵌套子键不得升格成顶层键。
    assert "requires" not in result
    assert "bins" not in result


def test_entries_lists_directory(registry: SkillRegistry):
    result = registry.entries("business/lark-minutes")

    names = {item["name"]: item["type"] for item in result["items"]}
    assert names == {"SKILL.md": "file", "references": "dir"}


def test_entries_root_defaults_to_dot(registry: SkillRegistry):
    result = registry.entries()

    assert result["directory"] == "."
    assert [item["name"] for item in result["items"]] == ["business"]


def test_entries_rejects_unknown_path(registry: SkillRegistry):
    with pytest.raises(FileNotFoundError):
        registry.entries("nope")


def test_context_lists_every_skill_not_just_matches(registry: SkillRegistry):
    # 关键词只可能命中其中一个，但清单必须把两个都给出来
    matches = registry.match("视频会议")
    context = registry.context(matches)

    assert "lark-minutes" in context
    assert "lark-vc" in context
    assert "business/lark-minutes" in context
    # 明确告诉模型 description 只是索引，正文要用 read_skill 取
    assert "read_skill" in context


def test_context_is_empty_without_skills(tmp_path: Path):
    assert SkillRegistry((tmp_path,)).context([]) == ""


# --- 工具注册 ---------------------------------------------------------------


def test_skill_tools_registered_when_registry_present(registry: SkillRegistry):
    tools = ToolRegistry(FakeSandbox(), FakeNode(), FakeBrowser(), registry)

    assert "read_skill" in tools.names()
    assert "list_skill_files" in tools.names()
    # 只读，不该要求确认
    assert not tools.requires_confirmation("read_skill")


def test_skill_tools_absent_without_registry():
    tools = ToolRegistry(FakeSandbox(), FakeNode(), FakeBrowser())

    assert "read_skill" not in tools.names()


@pytest.mark.asyncio
async def test_read_skill_tool_executes(registry: SkillRegistry):
    tools = ToolRegistry(FakeSandbox(), FakeNode(), FakeBrowser(), registry)

    output = await tools.execute("read_skill", {"path": "business/lark-vc/references/boundaries.md"})

    assert "妙记和纪要相互独立" in output
