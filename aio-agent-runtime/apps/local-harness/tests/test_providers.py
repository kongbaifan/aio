import json
from pathlib import Path

import pytest

from app.llm.openai_compatible import OpenAICompatibleClient, _normalize_chat_url
from app.llm.providers import ModelConfigError, ModelRegistry, get_model, parse_model_ref


def test_parse_model_ref():
    assert parse_model_ref("deepseek/deepseek-chat") == ("deepseek", "deepseek-chat")
    assert parse_model_ref("openrouter/auto/foo") == ("openrouter", "auto/foo")
    assert parse_model_ref("nodash") is None


def test_load_project_models_json(tmp_path: Path, monkeypatch):
    models_file = tmp_path / "models.json"
    models_file.write_text(
        json.dumps(
            {
                "default": {"provider": "deepseek", "model": "deepseek-chat"},
                "providers": {
                    "deepseek": {
                        "baseUrl": "https://api.deepseek.com",
                        "api": "openai-completions",
                        "apiKey": "DEEPSEEK_API_KEY",
                        "models": [{"id": "deepseek-chat", "name": "DeepSeek Chat", "maxTokens": 4096}],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key")
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    registry = ModelRegistry.load(models_json=models_file)
    assert registry.default_provider == "deepseek"
    assert registry.default_model == "deepseek-chat"

    catalog = registry.catalog()
    labels = {f"{item.provider}/{item.id}": item for item in catalog}
    assert labels["deepseek/deepseek-chat"].available is True

    ref = registry.get_model("deepseek", "deepseek-chat")
    assert ref.api_key == "sk-test-key"
    assert ref.base_url == "https://api.deepseek.com"
    assert ref.max_tokens == 4096
    assert ref.api == "openai-completions"


def test_literal_api_key_like_pi(tmp_path: Path, monkeypatch):
    """与 pi 一致：provider.apiKey 直接写 sk- 字面量，无需 .env。"""
    models_file = tmp_path / "models.json"
    models_file.write_text(
        json.dumps(
            {
                "default": {"provider": "zmoon", "model": "grok-4.5"},
                "providers": {
                    "zmoon": {
                        "baseUrl": "https://newapi.zmoon.top/v1",
                        "api": "openai-completions",
                        # 假值：本用例只验证「sk- 字面量不走环境变量解析」，与真实密钥无关。
                        "apiKey": "sk-test-literal",
                        "compat": {
                            "supportsDeveloperRole": False,
                            "supportsReasoningEffort": False,
                            "maxTokensField": "max_tokens",
                        },
                        "models": [
                            {
                                "id": "grok-4.5",
                                "name": "grok-4.5",
                                "maxTokens": 128000,
                                "contextWindow": 1000000,
                            }
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    for name in ("DEEPSEEK_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    registry = ModelRegistry.load(models_json=models_file)
    item = next(i for i in registry.catalog() if i.id == "grok-4.5")
    assert item.available is True
    ref = registry.get_model("zmoon", "grok-4.5")
    assert ref.api_key.startswith("sk-")
    assert ref.base_url == "https://newapi.zmoon.top/v1"
    assert ref.supports_developer_role is False


def test_missing_key_marks_unavailable(tmp_path: Path, monkeypatch):
    models_file = tmp_path / "models.json"
    models_file.write_text(
        json.dumps(
            {
                "providers": {
                    "deepseek": {
                        "baseUrl": "https://api.deepseek.com",
                        "api": "openai-completions",
                        "apiKey": "DEEPSEEK_API_KEY",
                        "models": [{"id": "deepseek-chat", "name": "Chat"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    for name in ("DEEPSEEK_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    registry = ModelRegistry.load(models_json=models_file)
    item = next(i for i in registry.catalog() if i.id == "deepseek-chat")
    assert item.available is False
    with pytest.raises(ModelConfigError):
        registry.get_model("deepseek", "deepseek-chat")


def test_generic_llm_api_key_does_not_leak_across_providers(tmp_path: Path, monkeypatch):
    """全局 LLM_API_KEY 不得作为任意 provider 的兜底。

    曾经的行为：provider 专属 key 没配时回落到 LLM_API_KEY —— 那意味着 A 家的密钥
    会被当 Bearer 发给 B 家的 baseUrl，而 catalog() 还会把该 provider 标成 available，
    界面上完全看不出来。
    """
    models_file = tmp_path / "models.json"
    models_file.write_text(
        json.dumps(
            {
                "providers": {
                    "deepseek": {
                        "baseUrl": "https://api.deepseek.com",
                        "api": "openai-completions",
                        "apiKey": "DEEPSEEK_API_KEY",
                        "models": [{"id": "deepseek-chat", "name": "Chat"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "sk-test-belongs-to-another-vendor")

    registry = ModelRegistry.load(models_json=models_file)
    item = next(i for i in registry.catalog() if i.id == "deepseek-chat")
    assert item.available is False
    with pytest.raises(ModelConfigError):
        registry.get_model("deepseek", "deepseek-chat")


def test_missing_models_json_raises(tmp_path: Path, monkeypatch):
    missing = tmp_path / "nope.json"
    monkeypatch.delenv("HARNESS_MODELS_JSON", raising=False)
    with pytest.raises(ModelConfigError):
        ModelRegistry.load(models_json=missing)


def test_normalize_chat_url():
    assert _normalize_chat_url("https://api.openai.com/v1") == "https://api.openai.com/v1/chat/completions"
    assert _normalize_chat_url("https://api.deepseek.com") == "https://api.deepseek.com/chat/completions"


def test_openai_client_from_ref(tmp_path: Path, monkeypatch):
    models_file = tmp_path / "models.json"
    models_file.write_text(
        json.dumps(
            {
                "providers": {
                    "deepseek": {
                        "baseUrl": "https://api.deepseek.com",
                        "api": "openai-completions",
                        "apiKey": "DEEPSEEK_API_KEY",
                        "models": [{"id": "deepseek-chat", "name": "Chat"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    ref = get_model("deepseek", "deepseek-chat", registry=ModelRegistry.load(models_file))
    client = OpenAICompatibleClient(ref, timeout=5)
    assert client.model == "deepseek-chat"
    assert client.provider == "deepseek"
