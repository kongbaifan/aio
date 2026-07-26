"""models.local.json 的深合并。

_deep_merge_providers 此前零测试覆盖，而它同时存在四个语义问题：
local 路径不跟随主配置、扁平格式静默忽略、model 整体替换、headers 整体替换。
"""

import json
from pathlib import Path

import pytest

from app.llm.providers import ModelConfigError, ModelRegistry


BASE = {
    "default": {"provider": "deepseek", "model": "deepseek-chat"},
    "providers": {
        "deepseek": {
            "baseUrl": "https://api.deepseek.com",
            "api": "openai-completions",
            "apiKey": "DEEPSEEK_API_KEY",
            "headers": {"X-Title": "aio", "X-Keep": "yes"},
            "compat": {"maxTokensField": "max_tokens", "supportsStreamUsage": True},
            "models": [
                {
                    "id": "deepseek-chat",
                    "name": "DeepSeek Chat",
                    "maxTokens": 8192,
                    "contextWindow": 128000,
                }
            ],
        }
    },
}


@pytest.fixture()
def config_dir(tmp_path: Path, monkeypatch) -> Path:
    (tmp_path / "models.json").write_text(json.dumps(BASE), encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key")
    monkeypatch.delenv("HARNESS_MODELS_JSON", raising=False)
    return tmp_path


def _write_local(directory: Path, payload: dict) -> None:
    (directory / "models.local.json").write_text(json.dumps(payload), encoding="utf-8")


def test_local_override_follows_primary_config_path(config_dir: Path):
    """local 覆盖跟随主配置所在目录，而不是永远指向项目的 config/。

    此前 local_path 写死成 project_root()/config/models.local.json：
    用 HARNESS_MODELS_JSON 指向另一套配置时，项目里的本机覆盖仍会污染进来，
    测试也会因为开发者本地建了那个文件而莫名其妙地红。
    """
    _write_local(config_dir, {"providers": {"deepseek": {"baseUrl": "https://local.example.com"}}})

    registry = ModelRegistry.load(models_json=config_dir / "models.json")
    assert registry.get_model("deepseek", "deepseek-chat").base_url == "https://local.example.com"


def test_local_accepts_flat_format(config_dir: Path):
    """local 允许省略 providers 外层——和主配置同样的宽容度。

    此前 local 走 `else {}`，照着主文件写成扁平格式会被静默完全忽略：
    不报错、不生效，覆盖凭空消失。
    """
    _write_local(config_dir, {"deepseek": {"baseUrl": "https://flat.example.com"}})

    registry = ModelRegistry.load(models_json=config_dir / "models.json")
    assert registry.get_model("deepseek", "deepseek-chat").base_url == "https://flat.example.com"


def test_model_fields_are_merged_not_replaced(config_dir: Path):
    """local 只改 maxTokens 时，不能把同一个 model 的其他字段一起丢掉。"""
    _write_local(
        config_dir,
        {"providers": {"deepseek": {"models": [{"id": "deepseek-chat", "maxTokens": 4096}]}}},
    )

    ref = ModelRegistry.load(models_json=config_dir / "models.json").get_model(
        "deepseek", "deepseek-chat"
    )
    assert ref.max_tokens == 4096          # 被覆盖
    assert ref.context_window == 128000    # 未提及的字段要保住
    assert ref.name == "DeepSeek Chat"


def test_headers_are_merged_not_replaced(config_dir: Path):
    """headers 之前是整体替换：加一个新 header，原有的全没了。"""
    _write_local(
        config_dir,
        {"providers": {"deepseek": {"headers": {"HTTP-Referer": "https://local"}}}},
    )

    ref = ModelRegistry.load(models_json=config_dir / "models.json").get_model(
        "deepseek", "deepseek-chat"
    )
    assert ref.headers["HTTP-Referer"] == "https://local"  # 新增
    assert ref.headers["X-Title"] == "aio"                 # 原有的要保住
    assert ref.headers["X-Keep"] == "yes"


def test_compat_is_merged(config_dir: Path):
    _write_local(
        config_dir,
        {"providers": {"deepseek": {"compat": {"supportsStreamUsage": False}}}},
    )

    ref = ModelRegistry.load(models_json=config_dir / "models.json").get_model(
        "deepseek", "deepseek-chat"
    )
    assert ref.supports_stream_usage is False        # 被覆盖
    assert ref.max_tokens_field == "max_tokens"      # 同组其他键保住


def test_local_can_add_new_provider(config_dir: Path):
    _write_local(
        config_dir,
        {
            "providers": {
                "extra": {
                    "baseUrl": "https://extra.example.com/v1",
                    "api": "openai-completions",
                    "apiKey": "sk-test-extra",
                    "models": [{"id": "x-1", "name": "X 1"}],
                }
            }
        },
    )

    registry = ModelRegistry.load(models_json=config_dir / "models.json")
    assert registry.get_model("extra", "x-1").base_url == "https://extra.example.com/v1"
    # 原有 provider 不受影响
    assert registry.get_model("deepseek", "deepseek-chat").base_url == "https://api.deepseek.com"


def test_missing_models_json_still_raises(tmp_path: Path, monkeypatch):
    """主配置不存在时应报错——且不能因为别处有个 models.local.json 就放行。"""
    monkeypatch.delenv("HARNESS_MODELS_JSON", raising=False)
    with pytest.raises(ModelConfigError):
        ModelRegistry.load(models_json=tmp_path / "nope.json")
