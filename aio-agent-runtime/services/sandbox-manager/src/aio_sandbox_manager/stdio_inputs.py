"""Bounded immutable input metadata; user document bytes never enter the Manager journal."""

import base64
import hashlib
import json
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .contracts import Contract, InputFile, ManagerError, safe_relative

MAX_STDIO_INPUT_BYTES = 4 * 1024 * 1024
MAX_STDIO_INPUT_FILES = 32
MANIFEST_PATH = "attachments/manifest.json"


class StdioAttachment(Contract):
    artifact_id: UUID
    source_path: str = Field(min_length=1, max_length=256)
    path: str = Field(min_length=1, max_length=64)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(ge=0, le=MAX_STDIO_INPUT_BYTES, strict=True)

    @field_validator("source_path")
    @classmethod
    def safe_name(cls, value):
        return safe_relative(value)

    @model_validator(mode="after")
    def fixed_destination(self):
        if self.path != "attachments/" + str(self.artifact_id):
            raise ValueError("Stdio attachments use server-derived immutable object paths")
        return self


def initial_files(spec, supplied):
    """Validate ALL bytes before creating a cell; generate a manifest, never extract user archives."""
    if spec.schema_version == 1:
        if supplied:
            raise ManagerError("STDIO_INPUTS_NOT_ALLOWED", "This template does not accept Run attachments", 403)
        return ()
    expected = {item.path: item for item in spec.input_manifest}
    actual = {item.path: item for item in supplied}
    if len(actual) != len(supplied) or set(actual) != set(expected):
        raise ManagerError("STDIO_INPUT_MANIFEST_MISMATCH", "Inputs must exactly match the approved manifest", 422)
    for path, item in actual.items():
        record = expected[path]
        if item.sha256 != record.sha256 or len(item.bytes()) != record.bytes:
            raise ManagerError("STDIO_INPUT_INTEGRITY_ERROR", "Input bytes do not match their immutable metadata", 422)
    manifest = json.dumps(
        {"schema_version": 1, "files": [item.model_dump(mode="json") for item in spec.input_manifest]},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return (
        *supplied,
        InputFile(
            path=MANIFEST_PATH,
            sha256=hashlib.sha256(manifest).hexdigest(),
            content_b64=base64.b64encode(manifest).decode("ascii"),
        ),
    )
