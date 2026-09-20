import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest
from pydantic import ValidationError

from aio_runtime_policy import RuntimeManifest, approve
from app.platform_settings import _sandbox_profiles, PlatformConfigurationError
from app.skills.contracts import DependencySkillPackage, SkillCreate, package_digest
from skill_fixtures import sample_package

ROOT = Path(__file__).resolve().parents[4]


def test_skill_v1_missing_version_and_existing_digest_remain_compatible():
    package = sample_package()
    raw = package.model_dump(mode="json")
    raw.pop("schema_version")
    parsed = SkillCreate(package=raw, sandbox_profile="standard")
    assert parsed.package.digest() == package.digest()
    assert package_digest(package.normalized()) == package.digest()


def test_skill_v2_numeric_version_and_dependency_order_are_canonical():
    raw = json.loads((ROOT / "config/skill-packages/example-analytics.json").read_text(encoding="utf-8"))
    first = DependencySkillPackage.model_validate(raw)
    raw["dependencies"].reverse()
    second = SkillCreate(package=raw, sandbox_profile="analytics").package
    assert second.schema_version == 2 and isinstance(second.schema_version, int)
    assert first.digest() == second.digest() == package_digest(second.normalized())
    assert first.digest() != sample_package().digest()
    for change in [{"dependencies": [{"name": "numpy", "version": ">=2"}]}, {"install_command": "pip install evil"}]:
        with pytest.raises(ValidationError):
            SkillCreate(package={**raw, **change}, sandbox_profile="analytics")


@pytest.mark.parametrize("fault", [None, "unknown-key", "tamper", "production"])
def test_platform_profile_approval_does_not_trust_incoming_key_or_test_purpose(tmp_path, fault):
    manifest = RuntimeManifest.model_validate_json((ROOT / "config/runtime-locks/analytics-python.json").read_bytes())
    private = Ed25519PrivateKey.generate()
    approval = approve(
        manifest,
        "sha256:" + "a" * 64,
        {"inventory_sha256": "b" * 64, "smoke_sha256": "c" * 64, "sbom_sha256": "d" * 64},
        key_id="operator",
        private_key=private.private_bytes_raw(),
        purpose="test",
        review_note="Synthetic contract test, not production approval",
    )
    record = approval.model_dump(mode="json")
    if fault == "tamper":
        record["manifest"]["packages"][0]["version"] = "0.0.1"
    if fault == "unknown-key":
        record["key_id"] = "attacker"
    keys = tmp_path / "keys.json"
    keys.write_text(
        json.dumps(
            {
                "keys": [
                    {"id": "operator", "public_key": base64.b64encode(private.public_key().public_bytes_raw()).decode()}
                ]
            }
        ),
        encoding="utf-8",
    )
    profiles = tmp_path / "profiles.json"
    profiles.write_text(
        json.dumps(
            {"profiles": [{"id": "analytics", "image_digest": approval.image_digest, "runtime_approval": record}]}
        ),
        encoding="utf-8",
    )
    env = {
        "PLATFORM_SANDBOX_PROFILES": str(profiles),
        "PLATFORM_RUNTIME_TRUST_KEYS": str(keys),
        "HARNESS_MODE": "platform-production" if fault == "production" else "platform-test",
    }
    if fault:
        with pytest.raises(PlatformConfigurationError):
            _sandbox_profiles(env)
    else:
        result = _sandbox_profiles(env)[0]
        assert result["runtime"]["manifest_digest"] == manifest.digest and "signature" not in result["runtime"]
