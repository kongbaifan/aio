import pytest

from app.platform_errors import PlatformConfigurationError
from app.platform_settings import DeploymentMode, PlatformSettings, deployment_mode


def test_legacy_is_explicit_default():
    assert deployment_mode({}) is DeploymentMode.LEGACY_LOCAL


@pytest.mark.parametrize("value", ["", "production", "platform-prod", " PLATFORM-TEST ", "false"])
def test_unknown_mode_fails_closed(value):
    with pytest.raises(PlatformConfigurationError):
        deployment_mode({"HARNESS_MODE": value})


def test_platform_preserves_exact_issuer_and_hides_credentials(platform_env):
    settings = PlatformSettings.from_env(platform_env)
    assert settings.oidc_issuer.endswith("/tenant/")
    assert settings.oidc_client_secret not in repr(settings)
    assert "test-only-password" not in repr(settings)
    assert settings.session_cookie == "aio_session"


@pytest.mark.parametrize(
    "key",
    [
        "PLATFORM_DATABASE_URL",
        "PLATFORM_PUBLIC_ORIGIN",
        "PLATFORM_OIDC_ISSUER",
        "PLATFORM_OIDC_CLIENT_ID",
        "PLATFORM_OIDC_CLIENT_SECRET",
    ],
)
def test_required_inputs_have_no_fallback(platform_env, key):
    platform_env.pop(key)
    with pytest.raises(PlatformConfigurationError):
        PlatformSettings.from_env(platform_env)


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///tmp.db",
        "postgresql+psycopg://user:secret@host/db?sslmode=disable",
        "postgresql+psycopg://user:secret@host/db?sslmode=require",
    ],
)
def test_production_rejects_insecure_database_without_echoing_url(platform_env, url):
    platform_env["HARNESS_MODE"] = "platform-production"
    platform_env["PLATFORM_DATABASE_URL"] = url
    with pytest.raises(PlatformConfigurationError) as exc:
        PlatformSettings.from_env(platform_env)
    assert url not in str(exc.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.example.test",
        "https://user:secret@example.test",
        "https://example.test?token=private",
        "https://example.test/#secret",
        "https://example.test\\@evil.test",
        "https://example.test:bad",
    ],
)
def test_bad_endpoint_rejected(platform_env, url):
    platform_env["PLATFORM_OIDC_TOKEN_ENDPOINT"] = url
    with pytest.raises(PlatformConfigurationError):
        PlatformSettings.from_env(platform_env)


@pytest.mark.parametrize("value", ["0", "-1", "1.2", "nan", "999999", "１２"])
def test_numbers_never_silently_become_permissive_defaults(platform_env, value):
    platform_env["PLATFORM_RUN_TIMEOUT"] = value
    with pytest.raises(PlatformConfigurationError):
        PlatformSettings.from_env(platform_env)


def test_production_https_cookie(platform_env):
    platform_env.update(
        HARNESS_MODE="platform-production",
        PLATFORM_PUBLIC_ORIGIN="https://agent.example.test",
        PLATFORM_DATABASE_URL="postgresql+psycopg://runtime:fake-secret@db.example.test/platform?sslmode=verify-full",
    )
    settings = PlatformSettings.from_env(platform_env)
    assert settings.secure_cookies
    assert settings.session_cookie.startswith("__Host-")


def test_legacy_config_is_blocked_before_dotenv(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("HARNESS_MODE", "platform-test")
    monkeypatch.setattr("app.config._load_environment_file", lambda *_: pytest.fail("legacy dotenv was read"))
    with pytest.raises(PlatformConfigurationError):
        Settings.from_env()


def test_platform_entry_does_not_construct_legacy_model_registry(monkeypatch):
    from app import main

    monkeypatch.setenv("HARNESS_MODE", "platform-production")
    monkeypatch.delenv("PLATFORM_DATABASE_URL", raising=False)
    monkeypatch.setattr(main, "RuntimeContainer", lambda *_: pytest.fail("legacy runtime constructed"))
    monkeypatch.setattr(main.Settings, "from_env", lambda: pytest.fail("legacy Settings called"))
    with pytest.raises(PlatformConfigurationError):
        main.create_app()


def test_direct_legacy_secret_parser_is_guarded_before_shell(monkeypatch):
    from app.llm.providers import _resolve_secret_value

    monkeypatch.setenv("HARNESS_MODE", "platform-production")
    monkeypatch.setattr("app.llm.providers.subprocess.run", lambda *a, **kw: pytest.fail("Shell executed"))
    with pytest.raises(PlatformConfigurationError):
        _resolve_secret_value("!this-must-never-run")


def test_web_build_location_does_not_assume_repository_depth(platform_env, tmp_path, monkeypatch):
    import app.platform_settings as settings_module

    fake = tmp_path / "app" / "platform_settings.py"
    monkeypatch.setattr(settings_module, "__file__", str(fake))
    monkeypatch.setattr("app.paths.find_root", lambda _: None)
    settings = PlatformSettings.from_env(platform_env)
    assert settings.web_dist == tmp_path / "web" / "platform" / "dist"
    explicit = PlatformSettings.from_env({**platform_env, "PLATFORM_WEB_DIST": str(tmp_path / "custom-dist")})
    assert explicit.web_dist == tmp_path / "custom-dist"


def test_api_capability_catalog_rejects_shell_credential_reference(platform_env):
    with pytest.raises(PlatformConfigurationError):
        PlatformSettings.from_env({**platform_env, "PLATFORM_MODEL_SECRET_ENV_ALLOWLIST": "!command"})
