import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.platform_errors import PlatformError
from app.platform_errors import PlatformConfigurationError
from app.platform_settings import _skill_import_profile
from app.runtime.actions import canonical_digest
from app.skills.archive_commands import archive_code, archive_receipt
from app.skills.archive_contracts import ARCHIVE_RESULT_PREFIX, SkillArchivePrepare
from app.skills.contracts import SkillFile, SkillPackage


def intention(**change):
    return {
        "request_id": str(uuid4()),
        "archive_format": "zip",
        "bytes": 12,
        "sha256": "a" * 64,
        "sandbox_profile": "approved",
        **change,
    }


def test_legacy_package_normalization_and_digest_survive_metadata_base_extraction():
    fields = {
        "name": "legacy",
        "version": "1.0.0",
        "description": "known",
        "source": "known",
        "license": "known",
        "files": [{"path": "SKILL.md", "content": "# known"}],
    }
    expected = {**fields, "schema_version": 1, "instruction_path": "SKILL.md", "reference_paths": [], "entrypoints": []}
    package = SkillPackage(**fields)
    assert package.normalized() == expected
    assert package.digest() == canonical_digest("aio-skill-package-v1", expected)


@pytest.mark.parametrize(
    "change",
    [
        {"bytes": True},
        {"bytes": 2097153},
        {"archive_format": "rar"},
        {"sha256": "bad"},
        {
            "native": {
                "name": "x",
                "version": "1.0.0",
                "description": "d",
                "source": "s",
                "license": "l",
                "entrypoints": [],
            }
        },
        {"install": "pip install unreviewed"},
    ],
)
def test_archive_intention_is_bounded_metadata_not_install_or_execution_authority(change):
    with pytest.raises(ValidationError):
        SkillArchivePrepare.model_validate(intention(**change))


def test_archive_program_is_fixed_source_with_serialized_data_not_host_execution():
    request = intention(
        native={
            "name": "safe",
            "version": "1.0.0",
            "description": "'\nraise SystemExit('injected')",
            "source": "test",
            "license": "test",
        }
    )
    command = archive_code(request)
    compile(command, "<not-executed-archive-command>", "exec")
    assert len(command.encode()) < 65536
    assert "archive.bin" in command and "extractall(" not in command


@pytest.mark.parametrize(
    "value",
    [
        {"state": "rejected", "error_code": ["bad"]},
        {"state": "rejected", "error_code": "PRIVATE_CREDENTIAL_LEAK"},
        {"state": "scanned", "schema_version": True},
        [],
    ],
)
def test_unknown_or_malformed_scan_receipt_is_not_trusted(value):
    with pytest.raises(PlatformError):
        archive_receipt(
            {"exit_code": 0, "truncated": False, "stdout": ARCHIVE_RESULT_PREFIX + json.dumps(value)}, "a" * 64
        )


def test_license_notices_are_data_and_hidden_configuration_stays_forbidden():
    assert SkillFile(path="LICENSE", content="Synthetic legal notice").path == "LICENSE"
    with pytest.raises(ValidationError):
        SkillFile(path=".env", content="private")
    with pytest.raises(ValidationError):
        SkillFile(path="binary.png", content="not a text package")


def test_archive_scanner_is_explicit_and_cannot_fall_back_to_unconfigured_host_execution():
    assert _skill_import_profile({}, ()) is None
    source = {
        "PLATFORM_SKILL_IMPORT_PROFILE": "approved",
        "PLATFORM_MANAGER_URL": "http://127.0.0.1:9999",
        "PLATFORM_ARTIFACT_ROOT": "explicit-test-root",
    }
    with pytest.raises(PlatformConfigurationError):
        _skill_import_profile(source, ())
    profile = ({"id": "approved", "max_timeout_seconds": 30},)
    assert _skill_import_profile(source, profile) == "approved"
    with pytest.raises(PlatformConfigurationError):
        _skill_import_profile({**source, "PLATFORM_MANAGER_URL": ""}, profile)
    with pytest.raises(PlatformConfigurationError):
        _skill_import_profile(source, ({"id": "approved", "max_timeout_seconds": 1},))
