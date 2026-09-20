"""Archive decoding runs only in real bounded Docker cells; host code makes synthetic fixtures."""

import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import stat
import struct
import sys
import tarfile
from uuid import uuid4
import zipfile

import pytest

from test_docker_isolation import cell, execute


IDENTITY = {
    "name": "archive-sample",
    "version": "1.0.0",
    "description": "Synthetic archive fixture",
    "source": "internal synthetic fixture",
    "license": "MIT",
}


def package_files(*, native=False, wrapped=False, extra=()):
    files = [
        ("SKILL.md", b"# Synthetic skill\nUse only explicitly granted capabilities."),
        ("LICENSE", b"Synthetic license fixture."),
    ]
    if not native:
        manifest = {**IDENTITY, "entrypoints": []}
        files.insert(0, ("skill.json", json.dumps(manifest).encode()))
    files += list(extra)
    return [("sample/" + name if wrapped else name, value) for name, value in files]


def archive_bytes(files, kind="zip"):
    target = io.BytesIO()
    if kind == "zip":
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, value in files:
                # Windows ZipInfo normalizes backslashes during construction;
                # retain the exact hostile wire name instead of testing a
                # silently repaired fixture.
                item = zipfile.ZipInfo(name)
                item.filename = item.orig_filename = name
                item.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(item, value)
    else:
        with tarfile.open(fileobj=target, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for name, value in files:
                item = tarfile.TarInfo(name)
                item.size = len(value)
                archive.addfile(item, io.BytesIO(value))
    value = target.getvalue()
    return gzip.compress(value, mtime=0) if kind == "tar.gz" else value


def scan(managed, raw, kind="zip", native=None):
    # Control contracts are needed only for this opt-in full-project Docker
    # integration, not for importing the standalone Manager unit suite.
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps/local-harness"))
    from app.skills.archive_commands import archive_code
    from app.skills.archive_contracts import ARCHIVE_RESULT_PREFIX, SkillArchivePrepare
    from app.skills.contracts import SkillCreate

    manager, _, profile = managed
    request = SkillArchivePrepare(
        request_id=uuid4(),
        archive_format=kind,
        bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        sandbox_profile=profile.id,
        native=native,
    )
    spec = cell(
        profile,
        inputs=[{"path": "archive.bin", "sha256": request.sha256, "content_b64": base64.b64encode(raw).decode()}],
    )
    manager.ensure(spec)
    response = execute(manager, spec, archive_code(request.model_dump(mode="json")))
    markers = [
        line[len(ARCHIVE_RESULT_PREFIX) :]
        for line in response["stdout"].splitlines()
        if line.startswith(ARCHIVE_RESULT_PREFIX)
    ]
    assert len(markers) == 1 and not response["truncated"], response
    receipt = json.loads(markers[0])
    if response["exit_code"]:
        assert response["exit_code"] == 2 and receipt["state"] == "rejected"
        assert not response["stderr"]
        manager.stop(spec)
        return receipt, None
    assert receipt["state"] == "scanned"
    exported = manager.finalize(spec)
    assert exported["state"] == "destroyed" and [f["path"] for f in exported["files"]] == ["package.json"]
    result = base64.b64decode(exported["files"][0]["content_b64"], validate=True)
    assert len(result) == receipt["package_bytes"] and hashlib.sha256(result).hexdigest() == receipt["package_sha256"]
    value = SkillCreate(package=json.loads(result), sandbox_profile=profile.id)
    manager.acknowledge(spec)
    assert manager.journal.cell(spec.binding_id)["spec_json"] == ""
    return receipt, value.package


@pytest.mark.parametrize("kind", ["zip", "tar", "tar.gz"])
@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("wrapped", [False, True])
def test_archive_formats_and_native_instruction_packages_run_only_in_cells(managed, kind, native, wrapped):
    code = b"from pathlib import Path\nPath('UNEXPECTED_EFFECT').write_text('must not execute')\ndef run(payload): return {'ok': True}\n"
    raw = archive_bytes(package_files(native=native, wrapped=wrapped, extra=[("scripts/example.py", code)]), kind)
    receipt, package = scan(managed, raw, kind, IDENTITY if native else None)
    assert receipt["manual_source_license_review_required"] is True
    assert package.name == IDENTITY["name"] and len(package.files) == 3 and not package.entrypoints
    assert next(f.content for f in package.files if f.path == "scripts/example.py") == code.decode()


@pytest.mark.parametrize(
    "name",
    ["../outside.md", "/outside.md", "a\\outside.md", "C:/outside.md", "a//b.md", "a/./b.md", ".env", "cafe\u0301.md"],
)
def test_archive_unsafe_paths_never_become_skill_content(managed, name):
    raw = archive_bytes(package_files(extra=[(name, b"unsafe path")]))
    receipt, package = scan(managed, raw)
    assert package is None and receipt["error_code"] == "ARCHIVE_PATH_INVALID"


@pytest.mark.parametrize("kind", ["zip", "tar", "tar.gz"])
def test_archive_case_aliases_and_member_links_are_rejected(managed, kind):
    raw = archive_bytes(package_files(extra=[("notes.md", b"one"), ("NOTES.md", b"two")]), kind)
    assert scan(managed, raw, kind)[0]["error_code"] == "ARCHIVE_MEMBER_CONFLICT"


@pytest.mark.parametrize("kind", ["zip", "tar"])
def test_archive_symbolic_or_hard_links_are_not_followed(managed, kind):
    target = io.BytesIO()
    if kind == "zip":
        with zipfile.ZipFile(target, "w") as archive:
            for name, value in package_files():
                archive.writestr(name, value)
            link = zipfile.ZipInfo("link.md")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, "SKILL.md")
    else:
        with tarfile.open(fileobj=target, mode="w") as archive:
            for name, value in package_files():
                info = tarfile.TarInfo(name)
                info.size = len(value)
                archive.addfile(info, io.BytesIO(value))
            link = tarfile.TarInfo("link.md")
            link.type = tarfile.LNKTYPE
            link.linkname = "SKILL.md"
            archive.addfile(link)
    assert scan(managed, target.getvalue(), kind)[0]["error_code"] == "ARCHIVE_NODE_INVALID"


@pytest.mark.parametrize(
    "problem",
    [
        "trailing",
        "huge_file",
        "too_many",
        "binary",
        "credential",
        "metadata_credential",
        "duplicate_json",
        "files_override",
        "two_roots",
    ],
)
def test_archive_admission_rejects_ambiguous_oversized_and_secret_content(managed, problem):
    files = package_files()
    if problem == "huge_file":
        files.append(("large.txt", b"a" * 65537))
    elif problem == "too_many":
        files += [(f"item-{n}.txt", b"x") for n in range(128)]
    elif problem == "binary":
        files.append(("image.png", b"\x89PNG\0"))
    elif problem == "credential":
        files.append(("secret.txt", b"sk-" + b"a" * 30))
    elif problem == "metadata_credential":
        files[0] = ("skill.json", json.dumps({**IDENTITY, "source": "sk-" + "a" * 30}).encode())
    elif problem == "duplicate_json":
        files[0] = ("skill.json", b'{"name":"first","name":"second"}')
    elif problem == "files_override":
        files[0] = ("skill.json", json.dumps({**IDENTITY, "files": []}).encode())
    elif problem == "two_roots":
        files = [("one/" + k, v) for k, v in files] + [("two/skill.json", b"{}")]
    raw = archive_bytes(files)
    if problem == "trailing":
        raw += b"not part of the skill archive"
    receipt, package = scan(managed, raw)
    assert package is None and receipt["state"] == "rejected"
    assert "sk-" not in json.dumps(receipt)


@pytest.mark.parametrize(
    "problem",
    [
        "encrypted",
        "unknown_compression",
        "gzip_bomb",
        "gzip_concatenation",
        "tar_trailing",
        "device",
        "sparse",
        "nul_name",
        "file_ancestor",
    ],
)
def test_additional_archive_format_and_node_boundaries_are_enforced_in_real_cell(managed, problem):
    kind = "zip"
    files = package_files()
    if problem == "encrypted":
        raw = bytearray(archive_bytes(files))
        offset = 0
        while True:
            offset = raw.find(b"PK\x03\x04", offset)
            if offset < 0:
                break
            flags = struct.unpack_from("<H", raw, offset + 6)[0]
            struct.pack_into("<H", raw, offset + 6, flags | 1)
            offset += 4
        offset = 0
        while True:
            offset = raw.find(b"PK\x01\x02", offset)
            if offset < 0:
                break
            flags = struct.unpack_from("<H", raw, offset + 8)[0]
            struct.pack_into("<H", raw, offset + 8, flags | 1)
            offset += 4
        raw = bytes(raw)
    elif problem == "unknown_compression":
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_BZIP2) as z:
            for name, value in files:
                z.writestr(name, value)
        raw = stream.getvalue()
    elif problem == "gzip_bomb":
        raw, kind = gzip.compress(b"\0" * (8 * 1024 * 1024 + 1), mtime=0), "tar.gz"
    elif problem == "gzip_concatenation":
        raw, kind = archive_bytes(files, "tar.gz") + gzip.compress(b"hidden", mtime=0), "tar.gz"
    elif problem == "tar_trailing":
        raw, kind = archive_bytes(files, "tar") + b"X" * 512, "tar"
    elif problem in {"device", "sparse"}:
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for name, value in files:
                member = tarfile.TarInfo(name)
                member.size = len(value)
                tar.addfile(member, io.BytesIO(value))
            member = tarfile.TarInfo("unsafe.txt")
            if problem == "device":
                member.type = tarfile.CHRTYPE
                member.devmajor = 1
                member.devminor = 3
            else:
                member.pax_headers = {"GNU.sparse.realsize": "999999999999"}
            tar.addfile(member)
        raw, kind = stream.getvalue(), "tar"
    elif problem == "nul_name":
        raw = archive_bytes(files + [("bad\0name.txt", b"ignored name suffix must not hide data")])
    else:
        raw = archive_bytes(files + [("node.txt", b"file"), ("NODE.txt/child.md", b"not a directory")])
    receipt, package = scan(managed, raw, kind)
    assert package is None and receipt["state"] == "rejected"
