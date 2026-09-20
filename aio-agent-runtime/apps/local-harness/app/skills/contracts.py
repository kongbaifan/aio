"""Text package v1 admission. Archive/binary imports require a separate isolated importer."""

from typing import Literal
from uuid import UUID
from pathlib import PurePosixPath
import hashlib
import unicodedata

from pydantic import Field, field_validator, model_validator
from aio_runtime_policy import DependencyRequirement

from ..api.v2.contracts import RequestContract
from ..runtime.catalog import validate_schema, validate_arguments
from ..runtime.contracts import bounded_json
from ..runtime.actions import canonical_digest
from ..workspaces.storage import safe_path


class SkillFile(RequestContract):
    path: str = Field(min_length=1, max_length=256)
    content: str = Field(max_length=65536)

    @field_validator("path")
    @classmethod
    def path_is_safe(cls, value):
        safe_path(value)
        text_suffix = PurePosixPath(value).suffix.lower() in {
            ".md",
            ".txt",
            ".py",
            ".json",
            ".csv",
        }
        notice = PurePosixPath(value).name in {"LICENSE", "NOTICE", "COPYING", "README"}
        if unicodedata.normalize("NFC", value) != value or not (text_suffix or notice):
            raise ValueError("Only normalized text-package paths are supported")
        if any(part.startswith(".") or part in {"node_modules", "__pycache__"} for part in value.split("/")):
            raise ValueError("Hidden/config/cache files are not Skill package content")
        return value

    @field_validator("content")
    @classmethod
    def bounded_text(cls, value):
        if "\0" in value or len(value.encode("utf-8")) > 65536:
            raise ValueError("Text file exceeds its UTF-8 bound")
        return value


class SkillTest(RequestContract):
    input: dict
    expected: dict


class SkillEntrypoint(RequestContract):
    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,47}$")
    path: str = Field(min_length=1, max_length=256)
    description: str = Field(min_length=1, max_length=1024)
    input_schema: dict
    output_schema: dict
    tests: tuple[SkillTest, ...] = Field(min_length=1, max_length=3)
    timeout_seconds: int = Field(default=10, ge=1, le=30, strict=True)

    @model_validator(mode="after")
    def schemas_and_samples(self):
        validate_schema(self.input_schema)
        validate_schema(self.output_schema)
        for case in self.tests:
            validate_arguments({"input_schema": self.input_schema}, bounded_json(case.input, 8192))
            validate_arguments({"input_schema": self.output_schema}, bounded_json(case.expected, 8192))
        return self


class SkillMetadata(RequestContract):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")
    version: str = Field(pattern=r"^(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})$")
    description: str = Field(min_length=1, max_length=1024)
    source: str = Field(min_length=1, max_length=1024)
    license: str = Field(min_length=1, max_length=128)


class SkillPackage(SkillMetadata):
    schema_version: Literal[1] = 1
    instruction_path: str = "SKILL.md"
    reference_paths: tuple[str, ...] = Field(default=(), max_length=24)
    entrypoints: tuple[SkillEntrypoint, ...] = Field(default=(), max_length=4)
    files: tuple[SkillFile, ...] = Field(min_length=1, max_length=48)

    @model_validator(mode="after")
    def coherent(self):
        files = {item.path: item for item in self.files}
        if len(files) != len(self.files) or len({p.casefold() for p in files}) != len(files):
            raise ValueError("Package paths must be unique, including case aliases")
        if self.instruction_path not in files or not self.instruction_path.endswith(".md"):
            raise ValueError("A declared Markdown instruction file is required")
        if len(files[self.instruction_path].content.encode("utf-8")) > 32768:
            raise ValueError("Skill instructions exceed their context bound")
        if len(set(self.reference_paths)) != len(self.reference_paths) or any(
            p not in files for p in self.reference_paths
        ):
            raise ValueError("References must name unique package files")
        if any(len(files[path].content.encode("utf-8")) > 32768 for path in self.reference_paths):
            raise ValueError("Reference files exceed the bounded tool result limit")
        if len({e.name for e in self.entrypoints}) != len(self.entrypoints):
            raise ValueError("Entrypoint names must be unique")
        for e in self.entrypoints:
            if e.path not in files or not e.path.endswith(".py") or len(files[e.path].content.encode("utf-8")) > 32768:
                raise ValueError("Entrypoints require bounded Python source in the package")
        if (
            sum(len(e.tests) for e in self.entrypoints) > 8
            or sum(e.timeout_seconds * len(e.tests) for e in self.entrypoints) > 120
        ):
            raise ValueError("Validation work exceeds the per-package time/case bound")
        bounded_json(self.model_dump(mode="json"), 262144)
        return self

    def normalized(self) -> dict:
        content = self.model_dump(mode="json")
        content["files"] = sorted(content["files"], key=lambda item: item["path"])
        return content

    def file_manifest(self) -> list[dict]:
        return [
            {
                "path": file.path,
                "bytes": len(file.content.encode("utf-8")),
                "sha256": hashlib.sha256(file.content.encode("utf-8")).hexdigest(),
            }
            for file in sorted(self.files, key=lambda item: item.path)
        ]

    def digest(self) -> str:
        return canonical_digest("aio-skill-package-v1", self.normalized())


class DependencySkillPackage(SkillPackage):
    schema_version: Literal[2] = 2
    runtime_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    dependencies: tuple[DependencyRequirement, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def unique_dependencies(self):
        if len({item.name for item in self.dependencies}) != len(self.dependencies):
            raise ValueError("Dependency requirements must have unique exact distribution names")
        return self

    def normalized(self):
        value = super().normalized()
        value["dependencies"] = sorted(value["dependencies"], key=lambda item: item["name"])
        return value

    def digest(self):
        return canonical_digest("aio-skill-package-v2", self.normalized())


def package_digest(package):
    from ..platform_errors import PlatformError

    version = package.get("schema_version", 1)
    if type(version) is not int or version not in {1, 2}:
        raise PlatformError("SKILL_PACKAGE_VERSION_UNSUPPORTED", "Unsupported immutable Skill package version", 409)
    return canonical_digest(f"aio-skill-package-v{version}", package)


class SkillCreate(RequestContract):
    # Integer discriminator mappings are incorrectly emitted as string literals by TS OpenAPI generators.
    # The Literal versions and extra=forbid make this bounded union unambiguous without a discriminator.
    package: SkillPackage | DependencySkillPackage
    sandbox_profile: str = Field(min_length=1, max_length=64)

    @field_validator("package", mode="before")
    @classmethod
    def legacy_default(cls, value):
        if isinstance(value, dict) and "schema_version" not in value:
            return {"schema_version": 1, **value}
        return value


class SkillValidate(RequestContract):
    expected_revision: int = Field(ge=0, strict=True)
    reviewer_id: UUID


class SkillReview(RequestContract):
    expected_revision: int = Field(ge=0, strict=True)
    decision: Literal["approve", "reject"]
    note: str = Field(min_length=1, max_length=1000)
