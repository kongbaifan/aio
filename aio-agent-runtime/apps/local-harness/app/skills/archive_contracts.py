"""Bounded archive intentions. These contracts never parse or execute archive bytes."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from ..api.v2.contracts import RequestContract
from .contracts import SkillMetadata


MAX_ARCHIVE_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 128
MAX_TAR_BYTES = 8 * 1024 * 1024
MAX_EXPANSION_RATIO = 200
MAX_PACKAGE_BYTES = 262144
MAX_IMPORTS = 100
MAX_QUARANTINE_BYTES = 32 * 1024 * 1024
SCAN_TIMEOUT_SECONDS = 30
IMPORT_DEADLINE_SECONDS = 60
ARCHIVE_RESULT_PREFIX = "AIO_SKILL_ARCHIVE_RESULT:"


class SkillArchivePrepare(RequestContract):
    request_id: UUID
    archive_format: Literal["zip", "tar", "tar.gz"]
    bytes: int = Field(ge=1, le=MAX_ARCHIVE_BYTES, strict=True)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sandbox_profile: str = Field(min_length=1, max_length=64)
    # None means an explicit skill.json manifest. Native SKILL.md packages never
    # gain executable entrypoints merely because their frontmatter says so.
    native: SkillMetadata | None = None


class SkillArchiveRevision(RequestContract):
    expected_revision: int = Field(ge=0, strict=True)
