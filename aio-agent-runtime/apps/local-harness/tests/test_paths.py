"""项目根定位的回归测试。

原实现写死 parents[3] / parents[4]，容器里目录层级少一层，直接 IndexError，
docker compose 起不来。这里同时覆盖裸机与容器两种布局。
"""

from pathlib import Path

from app.paths import find_root, models_json_path, project_root


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def test_finds_repo_root_in_bare_metal_layout(tmp_path: Path):
    # <repo>/apps/local-harness/app/llm/providers.py，标志物在 <repo>/config
    repo = tmp_path / "aio-agent-runtime"
    (repo / "config").mkdir(parents=True)
    source = repo / "apps" / "local-harness" / "app" / "llm" / "providers.py"
    _touch(source)

    assert find_root(source) == repo


def test_finds_app_root_in_container_layout(tmp_path: Path):
    # 容器里是 /app/app/llm/providers.py，只有三层祖先，parents[4] 会越界
    app = tmp_path / "app"
    (app / "config").mkdir(parents=True)
    source = app / "app" / "llm" / "providers.py"
    _touch(source)

    assert find_root(source) == app
    # 相对项目根只有三层祖先，原实现取 parents[4] 必然越界
    assert len(source.relative_to(app).parents) == 3


def test_returns_none_when_no_marker(tmp_path: Path):
    source = tmp_path / "nowhere" / "deep" / "mod.py"
    _touch(source)

    assert find_root(source) is None


def test_explicit_env_override_wins(tmp_path: Path, monkeypatch):
    target = tmp_path / "elsewhere"
    target.mkdir()
    monkeypatch.setenv("HARNESS_PROJECT_ROOT", str(target))

    assert project_root() == target.resolve()
    assert models_json_path() == target.resolve() / "config" / "models.json"


def test_real_repo_root_has_models_json(monkeypatch):
    monkeypatch.delenv("HARNESS_PROJECT_ROOT", raising=False)

    root = project_root()

    assert (root / "config").is_dir()
    assert models_json_path() == root / "config" / "models.json"
