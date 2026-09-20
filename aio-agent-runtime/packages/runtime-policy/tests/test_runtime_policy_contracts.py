import base64
from datetime import datetime, timedelta, timezone
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from aio_runtime_policy import RuntimeManifest, RuntimePolicyError, approve, load_trust_keys, verify_approval


def sample():
    manifest = RuntimeManifest(
        name="example",
        base_image="python@sha256:" + "a" * 64,
        recipe_sha256="b" * 64,
        packages=[
            {
                "name": "example",
                "version": "1.0.0",
                "filename": "example-1.0.0-py3-none-any.whl",
                "sha256": "c" * 64,
                "bytes": 100,
                "imports": ["example"],
            }
        ],
    )
    key = Ed25519PrivateKey.generate()
    approval = approve(
        manifest,
        "sha256:" + "d" * 64,
        {"inventory_sha256": "e" * 64, "sbom_sha256": "f" * 64, "smoke_sha256": "a" * 64},
        key_id="operator",
        private_key=key.private_bytes_raw(),
        purpose="test",
        review_note="Explicit synthetic runtime verification",
    )
    return approval, key, {"operator": key.public_key().public_bytes_raw()}


def test_signature_requires_independent_trust_and_never_accepts_test_for_production():
    value, _, keys = sample()
    assert verify_approval(value.model_dump(mode="json"), value.image_digest, keys, allow_test=True) == value
    for supplied, test in [({}, True), (keys, False)]:
        with pytest.raises(RuntimePolicyError):
            verify_approval(value, value.image_digest, supplied, allow_test=test)


@pytest.mark.parametrize("field", ["image", "manifest", "review", "evidence", "key", "signature"])
def test_runtime_approval_cannot_be_rebound_after_review(field):
    value, _, keys = sample()
    raw = value.model_dump(mode="json")
    if field == "image":
        raw["image_digest"] = "sha256:" + "f" * 64
    elif field == "manifest":
        raw["manifest"]["packages"][0]["version"] = "2.0.0"
    elif field == "review":
        raw["review_note"] = "Different review statement after signing"
    elif field == "evidence":
        raw["inventory_sha256"] = "1" * 64
    elif field == "key":
        raw["key_id"] = "attacker"
    else:
        raw["signature"] = base64.b64encode(b"x" * 64).decode()
    with pytest.raises(RuntimePolicyError):
        verify_approval(raw, value.image_digest, keys, allow_test=True)


def test_signed_future_approval_is_not_yet_valid():
    value, key, keys = sample()
    future = value.model_copy(update={"approved_at": datetime.now(timezone.utc) + timedelta(hours=1)})
    future = future.model_copy(update={"signature": base64.b64encode(key.sign(future.signed_bytes())).decode()})
    with pytest.raises(RuntimePolicyError):
        verify_approval(future, future.image_digest, keys, allow_test=True)


@pytest.mark.parametrize(
    "change",
    [
        {"version": ">=1"},
        {"filename": "../x.whl"},
        {"imports": ["os.system('x')"]},
        {"name": "EXAMPLE"},
        {"bytes": True},
    ],
)
def test_runtime_lock_is_data_not_install_commands(change):
    value, _, _ = sample()
    data = value.manifest.model_dump(mode="json")
    data["packages"][0].update(change)
    with pytest.raises(ValidationError):
        RuntimeManifest.model_validate(data)


def test_runtime_lock_rejects_duplicate_package_and_mutable_import_path():
    value, _, _ = sample()
    data = value.manifest.model_dump(mode="json")
    with pytest.raises(ValidationError):
        RuntimeManifest.model_validate({**data, "packages": data["packages"] * 2})
    with pytest.raises(ValidationError):
        RuntimeManifest.model_validate({**data, "install_path": "/workspace/deps"})


def test_public_key_store_has_explicit_path_unique_ids_and_no_self_embedded_keys(tmp_path):
    approval, _, keys = sample()
    record = {"id": "operator", "public_key": base64.b64encode(keys["operator"]).decode()}
    file = tmp_path / "trust.json"
    file.write_text(json.dumps({"keys": [record]}), encoding="utf-8")
    assert load_trust_keys(file) == keys
    file.write_text(json.dumps({"keys": [record, record]}), encoding="utf-8")
    with pytest.raises(RuntimePolicyError):
        load_trust_keys(file)
    with pytest.raises(RuntimePolicyError):
        load_trust_keys("relative-file")
    with pytest.raises(RuntimePolicyError):
        verify_approval(
            {**approval.model_dump(mode="json"), "public_key": record["public_key"]},
            approval.image_digest,
            keys,
            allow_test=True,
        )
