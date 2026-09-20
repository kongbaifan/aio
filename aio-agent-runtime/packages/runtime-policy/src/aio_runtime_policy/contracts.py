"""Only immutable exact wheel environments can be approved; requirements never become commands."""

import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Literal
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import rfc8785


class RuntimePolicyError(ValueError):
    pass


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


def canonical_digest(domain, value):
    return hashlib.sha256(domain.encode("ascii") + b"\0" + rfc8785.dumps(value)).hexdigest()


class DependencyRequirement(Contract):
    name: str = Field(pattern=r"^[a-z0-9](?:[a-z0-9-]{0,98}[a-z0-9])?$")
    version: str = Field(pattern=r"^[0-9][A-Za-z0-9.+!_-]{0,63}$")

    @field_validator("name")
    @classmethod
    def canonical_name(cls, value):
        if re.sub(r"[-_.]+", "-", value).lower() != value:
            raise ValueError("Use a canonical Python distribution name")
        return value


class RuntimePackage(DependencyRequirement):
    filename: str = Field(pattern=r"^[A-Za-z0-9_.+-]{1,220}\.whl$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(ge=1, le=64 * 1024 * 1024, strict=True)
    imports: tuple[str, ...] = Field(default=(), max_length=8)

    @field_validator("imports")
    @classmethod
    def module_names(cls, value):
        if len(set(value)) != len(value) or any(
            not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", name) or len(name) > 96
            for name in value
        ):
            raise ValueError("Smoke imports must be fixed module identifiers")
        return value


class RuntimeManifest(Contract):
    schema_version: Literal[1] = 1
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{0,47}$")
    python: Literal["3.12"] = "3.12"
    platform: Literal["linux-x86_64"] = "linux-x86_64"
    base_image: str = Field(pattern=r"^python@sha256:[0-9a-f]{64}$")
    recipe_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    packages: tuple[RuntimePackage, ...] = Field(min_length=1, max_length=64)
    install_path: Literal["/opt/aio-deps"] = "/opt/aio-deps"
    network_profile: Literal["none"] = "none"

    @model_validator(mode="after")
    def bounded_unique_lock(self):
        names = [item.name for item in self.packages]
        files = [item.filename for item in self.packages]
        if names != sorted(names) or len(names) != len(set(names)) or len(files) != len(set(files)):
            raise ValueError("A runtime lock must be canonical and contain unique exact distributions/wheels")
        if sum(item.bytes for item in self.packages) > 128 * 1024 * 1024:
            raise ValueError("Runtime wheel input exceeds its bound")
        if len(self.model_dump_json().encode("utf-8")) > 32768:
            raise ValueError("Runtime manifest exceeds its control bound")
        return self

    @property
    def digest(self):
        return canonical_digest("aio-runtime-manifest-v1", self.model_dump(mode="json"))


class RuntimeApproval(Contract):
    schema_version: Literal[1] = 1
    release_id: UUID
    image_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    manifest: RuntimeManifest
    inventory_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sbom_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    smoke_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_at: datetime
    key_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    purpose: Literal["production", "test"]
    review_note: str = Field(min_length=16, max_length=1000)
    signature: str = Field(min_length=88, max_length=88)

    @field_validator("approved_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Approval timestamp must be timezone aware")
        return value.astimezone(timezone.utc)

    def signed_bytes(self):
        return b"aio-runtime-approval-v1\0" + rfc8785.dumps(self.model_dump(mode="json", exclude={"signature"}))


def load_trust_keys(path):
    """Read an explicit operator public-key store, never a key embedded by the claimant."""
    if not path:
        return {}
    file = Path(path)
    if not file.is_absolute() or file.stat().st_size > 16384:
        raise RuntimePolicyError("Runtime trust store must be an explicit bounded absolute file")
    data = json.loads(file.read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or set(data) != {"keys"}
        or not isinstance(data["keys"], list)
        or not 1 <= len(data["keys"]) <= 16
    ):
        raise RuntimePolicyError("Runtime trust store is invalid")
    keys = {}
    for item in data["keys"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"id", "public_key"}
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", item["id"])
        ):
            raise RuntimePolicyError("Runtime trust key is invalid")
        value = base64.b64decode(item["public_key"], validate=True)
        if len(value) != 32 or item["id"] in keys:
            raise RuntimePolicyError("Runtime trust keys must be unique Ed25519 public keys")
        Ed25519PublicKey.from_public_bytes(value)
        keys[item["id"]] = value
    return keys


def verify_approval(raw, image_digest, trusted_keys, *, allow_test=False):
    try:
        approval = RuntimeApproval.model_validate(raw)
        if approval.image_digest != image_digest or approval.key_id not in trusted_keys:
            raise RuntimePolicyError("Runtime image or signing authority is not approved")
        if approval.purpose == "test" and not allow_test:
            raise RuntimePolicyError("Synthetic runtime approvals cannot authorize production execution")
        if (approval.approved_at - datetime.now(timezone.utc)).total_seconds() > 60:
            raise RuntimePolicyError("Runtime approval is not yet valid")
        signature = base64.b64decode(approval.signature, validate=True)
        Ed25519PublicKey.from_public_bytes(trusted_keys[approval.key_id]).verify(signature, approval.signed_bytes())
        return approval
    except (ValueError, TypeError, KeyError, InvalidSignature):
        raise RuntimePolicyError("Runtime approval failed signature, purpose or immutable image validation") from None


def approve(manifest, image_digest, evidence, *, key_id, private_key, purpose, review_note):
    """Operator-only signing helper. No caller of this library receives a private key by default."""
    values = dict(
        release_id=uuid4(),
        image_digest=image_digest,
        manifest=manifest,
        inventory_sha256=evidence["inventory_sha256"],
        sbom_sha256=evidence["sbom_sha256"],
        smoke_sha256=evidence["smoke_sha256"],
        approved_at=datetime.now(timezone.utc),
        key_id=key_id,
        purpose=purpose,
        review_note=review_note,
        signature=base64.b64encode(b"\0" * 64).decode("ascii"),
    )
    approval = RuntimeApproval(**values)
    key = Ed25519PrivateKey.from_private_bytes(private_key)
    return approval.model_copy(
        update={"signature": base64.b64encode(key.sign(approval.signed_bytes())).decode("ascii")}
    )
