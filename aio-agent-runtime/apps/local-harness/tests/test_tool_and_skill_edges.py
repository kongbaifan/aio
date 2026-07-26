"""工具与 skill 读取的边界行为。"""

from pathlib import Path

import pytest

from app.skills.registry import SkillRegistry
from app.tools.registry import ToolRegistry, _viewport_env
from fakes import FakeBrowser, FakeNode, FakeSandbox


# --- list_files 的空路径 -----------------------------------------------------


@pytest.mark.asyncio
async def test_list_files_treats_empty_path_as_root(tmp_path: Path):
    """模型传 {"path": ""} 时不能 400。

    键存在时 get 的默认值不生效，空串会一路透传到 safe_path 换来 400；
    而同一个 registry 里 list_skill_files 的描述写的是「留空表示根目录」，
    两个列目录工具语义相反，模型很容易踩。
    """
    sandbox = FakeSandbox()
    seen = []

    async def _list_files(path="."):
        seen.append(path)
        return {"items": [], "cwd": path}

    sandbox.list_files = _list_files
    tools = ToolRegistry(sandbox, FakeNode(), FakeBrowser(), SkillRegistry((tmp_path,)))

    await tools.execute("list_files", {"path": ""})
    await tools.execute("list_files", {})

    assert seen == [".", "."]


# --- 视口环境变量 -----------------------------------------------------------


def test_viewport_env_falls_back_on_garbage(monkeypatch):
    """填非数字时退回默认值，而不是抛 invalid literal for int()。"""
    monkeypatch.setenv("AGENT_BROWSER_WIDTH", "abc")
    assert _viewport_env("AGENT_BROWSER_WIDTH", "SANDBOX_BROWSER_WIDTH", 1368) == 1368


def test_viewport_env_reads_primary_then_fallback(monkeypatch):
    monkeypatch.delenv("AGENT_BROWSER_WIDTH", raising=False)
    monkeypatch.setenv("SANDBOX_BROWSER_WIDTH", "800")
    assert _viewport_env("AGENT_BROWSER_WIDTH", "SANDBOX_BROWSER_WIDTH", 1368) == 800

    monkeypatch.setenv("AGENT_BROWSER_WIDTH", "1024")
    assert _viewport_env("AGENT_BROWSER_WIDTH", "SANDBOX_BROWSER_WIDTH", 1368) == 1024


# --- skill 读取的凭据防护 ---------------------------------------------------


@pytest.fixture()
def skills_root(tmp_path: Path) -> Path:
    skill = tmp_path / "business" / "demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        '---\nname: demo\ndescription: "示例"\n---\n\n# demo\n', encoding="utf-8"
    )
    (skill / "notes.md").write_text("文档正文", encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    "name",
    [".env", ".env.local", "id_rsa", "server.pem", "client.key", ".netrc"],
)
def test_read_rejects_credential_files(skills_root: Path, name: str):
    """read_skill 的边界只保证不出 skill 根目录，根内什么都能读。

    不做扩展名白名单（skill 会引用自己的 scripts/*.py，白名单会误伤），
    但要挡住明显的凭据类文件——防止有人把 .env 或私钥放进 skills/ 后被模型读走。
    """
    (skills_root / "business" / "demo" / name).write_text("SECRET=x", encoding="utf-8")
    registry = SkillRegistry((skills_root,))

    with pytest.raises(ValueError):
        registry.read(f"business/demo/{name}")


def test_read_still_allows_normal_docs(skills_root: Path):
    registry = SkillRegistry((skills_root,))
    assert "文档正文" in registry.read("business/demo/notes.md")["content"]


# --- entries 与 read 的语义一致 ---------------------------------------------


def test_entries_does_not_merge_across_roots(tmp_path: Path):
    """entries 应与 read 一样「首个命中的 root 就返回」。

    原实现遍历所有 root 往同一个列表里累加：目录名重叠时，列出来的某个
    business/x/y.md 会被 read_skill 解析到另一个 root 的同名文件，
    列表里还会出现重复条目。
    """
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    for root, filename in ((root_a, "from_a.md"), (root_b, "from_b.md")):
        directory = root / "business" / "shared"
        directory.mkdir(parents=True)
        (directory / filename).write_text("x", encoding="utf-8")
        (directory / "SKILL.md").write_text(
            '---\nname: shared\ndescription: "d"\n---\n', encoding="utf-8"
        )

    registry = SkillRegistry((root_a, root_b))
    names = {item["name"] for item in registry.entries("business/shared")["items"]}

    # 只应看到第一个 root 的内容，且 read 解析到的是同一个 root
    assert "from_a.md" in names
    assert "from_b.md" not in names
    assert registry.read("business/shared/from_a.md")["content"] == "x"
