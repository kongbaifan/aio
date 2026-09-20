import json
from pathlib import Path
import sys

import pytest

from app.platform_settings import PlatformSettings, PlatformConfigurationError
from app.runtime.actions import canonical_digest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts/platform"))
from oauth_fixture import OAuthFixture


def test_operator_oauth_policy_digest_matches_independent_gateway_and_hides_secret_reference(platform_env, tmp_path):
    from aio_connector_gateway.contracts import Endpoint

    fixture = OAuthFixture()
    config = fixture.policy()
    config.update(client_auth_method="client_secret_basic", client_secret_env="CONNECTOR_OAUTH_CLIENT_SECRET_COMPANY")
    raw = {
        "id": fixture.endpoint_id,
        "url": fixture.resource_uri,
        "authentication": "oauth2",
        "read_tools": ["lookup_identity"],
        "oauth": config,
    }
    file = tmp_path / "oauth.json"
    file.write_text(json.dumps({"endpoints": [raw]}), encoding="utf-8")
    settings = PlatformSettings.from_env({**platform_env, "PLATFORM_CONNECTOR_ENDPOINTS": str(file.resolve())})
    profile = settings.connector_profiles[0]
    endpoint = Endpoint(**{**raw, "read_tools": frozenset(raw["read_tools"]), "test_mode": True})
    assert profile["digest"] == endpoint.digest
    assert "client_secret_env" not in profile["oauth"]
    assert profile["oauth"]["config_digest"] == canonical_digest("aio-oauth-config-v1", config)


@pytest.mark.parametrize(
    "change",
    [
        {"client_auth_method": "client_secret_post", "client_secret_env": "CONNECTOR_VAULT_KEY"},
        {"redirect_uri": "https://attacker.example/callback"},
        {"authorization_endpoint": "http://unapproved.example/authorize"},
        {"authorization_parameters": {"scope": "admin"}},
        {"scopes": ["mcp.read", "mcp.read"]},
    ],
)
def test_invalid_operator_oauth_configuration_is_not_an_arbitrary_secret_or_redirect_surface(
    platform_env, tmp_path, change
):
    fixture = OAuthFixture()
    data = {
        "id": fixture.endpoint_id,
        "url": fixture.resource_uri,
        "authentication": "oauth2",
        "read_tools": ["lookup_identity"],
        "oauth": {**fixture.policy(), **change},
    }
    file = tmp_path / "bad-oauth.json"
    file.write_text(json.dumps({"endpoints": [data]}), encoding="utf-8")
    with pytest.raises((ValueError, PlatformConfigurationError)):
        PlatformSettings.from_env({**platform_env, "PLATFORM_CONNECTOR_ENDPOINTS": str(file.resolve())})
