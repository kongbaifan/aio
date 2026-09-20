import json

import pytest

from app.platform_settings import PlatformSettings, PlatformConfigurationError


@pytest.mark.parametrize("input_policy", ["none", "run_attachments"])
def test_stdio_endpoint_reference_hash_matches_gateway_without_executable_input(platform_env, tmp_path, input_policy):
    from aio_connector_gateway.contracts import Endpoint

    ref = {
        "profile_id": "fixed",
        "image_digest": "sha256:" + "a" * 64,
        "template_digest": "b" * 64,
        "credential_env": "UPSTREAM_TOKEN",
        "network_profile": "none",
        "input_policy": input_policy,
    }
    data = {
        "id": "fixed-stdio",
        "url": "stdio://fixed",
        "transport": "stdio",
        "authentication": "bearer",
        "read_tools": ["read_data"],
        "stdio": ref,
    }
    path = tmp_path / "stdio-endpoints.json"
    path.write_text(json.dumps({"endpoints": [data]}), encoding="utf-8")
    settings = PlatformSettings.from_env({**platform_env, "PLATFORM_CONNECTOR_ENDPOINTS": str(path.resolve())})
    endpoint = Endpoint(**{**data, "read_tools": frozenset(data["read_tools"])})
    assert settings.connector_profiles[0]["digest"] == endpoint.digest
    assert "executable" not in settings.connector_profiles[0]["stdio"]


@pytest.mark.parametrize(
    "update",
    [
        {"credential_env": "LD_PRELOAD"},
        {"network_profile": "host"},
        {"executable": "cmd.exe"},
        {"image_digest": "latest"},
        {"input_policy": "host_directory"},
    ],
)
def test_browser_cannot_expand_stdio_template_reference(platform_env, tmp_path, update):
    ref = {
        "profile_id": "fixed",
        "image_digest": "sha256:" + "a" * 64,
        "template_digest": "b" * 64,
        "credential_env": "UPSTREAM_TOKEN",
        **update,
    }
    path = tmp_path / "invalid-stdio.json"
    path.write_text(
        json.dumps(
            {
                "endpoints": [
                    {
                        "id": "fixed",
                        "url": "stdio://fixed",
                        "transport": "stdio",
                        "authentication": "bearer",
                        "read_tools": [],
                        "stdio": ref,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises((PlatformConfigurationError, ValueError)):
        PlatformSettings.from_env({**platform_env, "PLATFORM_CONNECTOR_ENDPOINTS": str(path.resolve())})


def test_run_stdio_input_permission_is_opt_in_and_strict_boolean():
    from uuid import uuid4
    from pydantic import ValidationError
    from app.api.v2.contracts import RunCreate

    body = {"message": "read", "agent_version_id": uuid4(), "expected_session_revision": 0}
    assert RunCreate(**body).allow_stdio_attachments is False
    assert RunCreate(**body, allow_stdio_attachments=True).allow_stdio_attachments is True
    for value in ["true", 1, None]:
        with pytest.raises(ValidationError):
            RunCreate(**body, allow_stdio_attachments=value)
