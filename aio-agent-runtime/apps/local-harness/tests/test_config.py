from pathlib import Path

from app.config import Settings


def test_harness_model_and_models_json_path(tmp_path: Path, monkeypatch):
    env_file = tmp_path / "model.env"
    env_file.write_text(
        "HARNESS_MODEL=deepseek/deepseek-chat\n"
        "LLM_MODE=auto\n"
        "DEEPSEEK_API_KEY=secret-value\n",
        encoding="utf-8",
    )
    for name in (
        "LLM_MODE",
        "LLM_PROVIDER",
        "LLM_MODEL",
        "HARNESS_MODEL",
        "HARNESS_MODELS_JSON",
        "DEEPSEEK_API_KEY",
        "MODEL_NAME",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HARNESS_ENV_FILE", str(env_file))

    settings = Settings.from_env()
    assert settings.harness_model == "deepseek/deepseek-chat"
    assert settings.llm_mode == "auto"


def test_explicit_models_json_path(tmp_path: Path, monkeypatch):
    models = tmp_path / "custom-models.json"
    models.write_text("{}", encoding="utf-8")
    for name in ("HARNESS_MODELS_JSON", "HARNESS_ENV_FILE", "HARNESS_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HARNESS_MODELS_JSON", str(models))
    settings = Settings.from_env()
    assert settings.models_json == str(models)
