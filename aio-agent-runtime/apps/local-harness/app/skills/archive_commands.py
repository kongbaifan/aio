"""Fixed remote archive program. NEVER execute this source on a control host."""

import json
import re

from ..platform_errors import PlatformError
from ..runtime.actions import strict_json

from .archive_contracts import (
    ARCHIVE_RESULT_PREFIX,
    MAX_ARCHIVE_BYTES,
    MAX_ARCHIVE_MEMBERS,
    MAX_EXPANSION_RATIO,
    MAX_PACKAGE_BYTES,
    MAX_TAR_BYTES,
)
from .commands import SCAN_CODE, CREDENTIAL_PATTERN


ARCHIVE_CODE = r"""
import hashlib, io, json, re, stat, struct, sys, tarfile, unicodedata, zipfile, zlib
from pathlib import Path, PurePosixPath

class ArchiveRejected(Exception):
    pass

def fail(code):
    raise ArchiveRejected(code)

def json_data(raw, maximum):
    if len(raw) > maximum:
        fail("ARCHIVE_METADATA_LIMIT")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                fail("ARCHIVE_DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                       parse_constant=lambda _: fail("ARCHIVE_METADATA_INVALID"))
    def bounded(item, depth=0):
        if depth > 24:
            fail("ARCHIVE_METADATA_LIMIT")
        if isinstance(item, dict):
            for child in item.values(): bounded(child, depth + 1)
        elif isinstance(item, list):
            for child in item: bounded(child, depth + 1)
    bounded(value)
    if not isinstance(value, dict):
        fail("ARCHIVE_METADATA_INVALID")
    return value

def path_name(value, directory=False):
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 256:
        fail("ARCHIVE_PATH_INVALID")
    if value != unicodedata.normalize("NFC", value) or "\\" in value or ":" in value:
        fail("ARCHIVE_PATH_INVALID")
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        fail("ARCHIVE_PATH_INVALID")
    if directory and value.endswith("/"):
        value = value[:-1]
    parts = value.split("/")
    if len(parts) > 8 or any(not p or p in {".", ".."} or p.startswith(".") for p in parts):
        fail("ARCHIVE_PATH_INVALID")
    if any(p.casefold() in {"node_modules", "__pycache__", "con", "prn", "aux", "nul"}
           or p.rstrip(" .") != p for p in parts):
        fail("ARCHIVE_PATH_INVALID")
    return value

def read_members(raw, kind, limits):
    records, seen, total = [], set(), 0
    def add(name, directory, size, read):
        nonlocal total
        name = path_name(name, directory)
        key = name.casefold()
        if key in seen or len(records) >= limits["members"]:
            fail("ARCHIVE_MEMBER_CONFLICT")
        seen.add(key)
        if directory:
            if size:
                fail("ARCHIVE_NODE_INVALID")
            records.append((name, True, None))
            return
        limit = 131072 if name.rsplit("/", 1)[-1] == "skill.json" else 65536
        if type(size) is not int or size < 0 or size > limit:
            fail("ARCHIVE_FILE_LIMIT")
        data = read(size + 1)
        if len(data) != size:
            fail("ARCHIVE_SIZE_MISMATCH")
        total += size
        if total > 524288:
            fail("ARCHIVE_CONTENT_LIMIT")
        records.append((name, False, data))

    if kind == "zip":
        # This bounded format is not self-extracting, concatenated, encrypted or
        # ZIP64. Enforce exact record coverage instead of ignoring trailing data.
        if len(raw) < 22 or raw[-22:-18] != b"PK\x05\x06":
            fail("ARCHIVE_TRAILING_DATA")
        _, disk, central_disk, disk_count, count, central_size, central_offset, comment_size = struct.unpack("<4s4H2LH", raw[-22:])
        if disk or central_disk or disk_count != count or count > limits["members"] or comment_size or central_offset + central_size != len(raw) - 22:
            fail("ARCHIVE_LAYOUT_INVALID")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if archive.comment:
                fail("ARCHIVE_METADATA_INVALID")
            members = archive.infolist()
            if len(members) != count or len(members) > limits["members"]:
                fail("ARCHIVE_MEMBER_LIMIT")
            cursor = 0
            for member in sorted(members, key=lambda item: item.header_offset):
                if member.header_offset != cursor or cursor + 30 > central_offset:
                    fail("ARCHIVE_LAYOUT_INVALID")
                magic, version, flags, method, _, _, crc, compressed, expanded, name_size, extra_size = struct.unpack("<4s5H3L2H", raw[cursor:cursor+30])
                if magic != b"PK\x03\x04" or version > 20 or flags != member.flag_bits or method != member.compress_type or flags & ~0x80e:
                    fail("ARCHIVE_LAYOUT_INVALID")
                start = cursor + 30 + name_size + extra_size
                local_name = raw[cursor+30:cursor+30+name_size].decode("utf-8" if flags & 0x800 else "cp437")
                if start > central_offset or local_name != member.orig_filename:
                    fail("ARCHIVE_LAYOUT_INVALID")
                if not flags & 8 and (crc, compressed, expanded) != (member.CRC, member.compress_size, member.file_size):
                    fail("ARCHIVE_SIZE_MISMATCH")
                cursor = start + member.compress_size
                if flags & 8:
                    if raw[cursor:cursor+4] == b"PK\x07\x08": cursor += 4
                    if cursor + 12 > central_offset or struct.unpack("<3L", raw[cursor:cursor+12]) != (member.CRC, member.compress_size, member.file_size):
                        fail("ARCHIVE_SIZE_MISMATCH")
                    cursor += 12
                if cursor > central_offset:
                    fail("ARCHIVE_LAYOUT_INVALID")
            if cursor != central_offset:
                fail("ARCHIVE_LAYOUT_INVALID")
            for member in members:
                if member.orig_filename != member.filename or member.flag_bits & 1:
                    fail("ARCHIVE_NODE_INVALID")
                if member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                    fail("ARCHIVE_COMPRESSION_DENIED")
                mode = stat.S_IFMT(member.external_attr >> 16)
                directory = member.is_dir()
                if mode not in ({0, stat.S_IFDIR} if directory else {0, stat.S_IFREG}):
                    fail("ARCHIVE_NODE_INVALID")
                if member.file_size > max(1, member.compress_size) * limits["ratio"]:
                    fail("ARCHIVE_EXPANSION_LIMIT")
                if len(member.extra) > 4096 or len(member.comment) > 1024:
                    fail("ARCHIVE_METADATA_LIMIT")
                if directory:
                    add(member.filename, True, member.file_size, None)
                else:
                    with archive.open(member) as stream:
                        add(member.filename, False, member.file_size, stream.read)
    else:
        data = raw
        if kind == "tar.gz":
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
            data = decoder.decompress(raw, limits["tar_bytes"] + 1)
            if len(data) > limits["tar_bytes"] or decoder.unconsumed_tail:
                fail("ARCHIVE_EXPANSION_LIMIT")
            if not decoder.eof or decoder.unused_data:
                fail("ARCHIVE_COMPRESSION_INVALID")
            if len(data) > max(1, len(raw)) * limits["ratio"]:
                fail("ARCHIVE_EXPANSION_LIMIT")
        if len(data) > limits["tar_bytes"] or len(data) % 512:
            fail("ARCHIVE_SIZE_MISMATCH")
        last_end = 0
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
            for member in archive:
                if member.sparse is not None or any(k.startswith("GNU.sparse") for k in member.pax_headers):
                    fail("ARCHIVE_NODE_INVALID")
                if not (member.isdir() or member.isreg()):
                    fail("ARCHIVE_NODE_INVALID")
                if len(json.dumps(member.pax_headers).encode("utf-8")) > 4096:
                    fail("ARCHIVE_METADATA_LIMIT")
                last_end = max(last_end, member.offset_data + ((member.size + 511) // 512) * 512)
                if member.isdir():
                    add(member.name, True, member.size, None)
                else:
                    with archive.extractfile(member) as stream:
                        add(member.name, False, member.size, stream.read)
        if len(data) - last_end < 1024 or any(data[last_end:]):
            fail("ARCHIVE_TRAILING_DATA")
    # A file cannot also be an ancestor directory, including case aliases.
    files = {name.casefold() for name, directory, _ in records if not directory}
    for name, _, _ in records:
        parts = name.split("/")
        if any("/".join(parts[:index]).casefold() in files for index in range(1, len(parts))):
            fail("ARCHIVE_MEMBER_CONFLICT")
    return records

def materialize(records, native, limits):
    marker = "skill.json" if native is None else "SKILL.md"
    files = {name: data for name, directory, data in records if not directory}
    if marker in files:
        prefix = ""
    else:
        roots = [name.rsplit("/", 1)[0] + "/" for name in files
                 if name.count("/") == 1 and name.rsplit("/", 1)[-1] == marker]
        if len(roots) != 1:
            fail("ARCHIVE_ROOT_INVALID")
        prefix = roots[0]
    for name, directory, _ in records:
        if prefix and directory and name == prefix[:-1]:
            continue
        if not name.startswith(prefix):
            fail("ARCHIVE_ROOT_INVALID")
    content = {}
    for name, data in files.items():
        relative = name[len(prefix):]
        if native is None and relative == "skill.json":
            continue
        if native is not None and relative == "skill.json":
            fail("ARCHIVE_METADATA_CONFLICT")
        path = PurePosixPath(relative)
        if path.suffix.lower() not in {".md", ".txt", ".py", ".json", ".csv"} and path.name not in {"LICENSE", "NOTICE", "COPYING", "README"}:
            fail("ARCHIVE_FILE_TYPE_DENIED")
        value = data.decode("utf-8")
        if "\0" in value:
            fail("ARCHIVE_TEXT_INVALID")
        content[relative] = value
    if not 1 <= len(content) <= 48:
        fail("ARCHIVE_FILE_LIMIT")
    if native is None:
        package = json_data(files[prefix + marker], 131072)
        if "files" in package:
            fail("ARCHIVE_METADATA_CONFLICT")
        package.setdefault("schema_version", 1)
        package.setdefault("instruction_path", "SKILL.md")
        package.setdefault("reference_paths", [])
        package.setdefault("entrypoints", [])
    else:
        references = sorted(name for name in content if name != "SKILL.md")
        if len(references) > 24 or any(len(content[name].encode("utf-8")) > 32768 for name in references):
            fail("ARCHIVE_REFERENCE_LIMIT")
        package = {**native, "schema_version": 1, "instruction_path": "SKILL.md",
                   "reference_paths": references, "entrypoints": []}
    if type(package.get("schema_version")) is not int or package["schema_version"] not in {1, 2}:
        fail("ARCHIVE_PACKAGE_VERSION_INVALID")
    package["files"] = [{"path": name, "content": content[name]} for name in sorted(content)]
    encoded = json.dumps(package, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > limits["package_bytes"]:
        fail("ARCHIVE_PACKAGE_LIMIT")
    return encoded, package

def scan_archive(config, limits, structural_scan, credential_pattern, marker):
    try:
        raw = Path("archive.bin").read_bytes()
        if len(raw) > limits["archive_bytes"] or len(raw) != config["bytes"] or hashlib.sha256(raw).hexdigest() != config["sha256"]:
            fail("ARCHIVE_SOURCE_MISMATCH")
        records = read_members(raw, config["archive_format"], limits)
        encoded, package = materialize(records, config.get("native"), limits)
        if re.search(credential_pattern, encoded.decode("utf-8")):
            fail("CREDENTIAL_SHAPED_CONTENT")
        Path("package.json").write_bytes(encoded)
        # This is only the fixed scanner's AST/pattern logic, never a package
        # import, setup hook or an entrypoint from the uploaded archive.
        exec(compile(structural_scan, "<fixed-skill-structural-scan>", "exec"), {})
        Path("archive.bin").unlink()
        receipt = {"state": "scanned", "schema_version": 1,
                   "archive_sha256": config["sha256"],
                   "package_sha256": hashlib.sha256(encoded).hexdigest(),
                   "package_bytes": len(encoded), "files": len(package["files"]),
                   "manual_source_license_review_required": True}
        print(marker + json.dumps(receipt, separators=(",", ":")))
    except Exception as error:
        code = "ARCHIVE_INVALID"
        if isinstance(error, ArchiveRejected):
            code = error.args[0]
        elif isinstance(error, ValueError) and error.args and error.args[0] in {"CREDENTIAL_SHAPED_CONTENT", "ENTRYPOINT_REQUIRES_RUN_PAYLOAD"}:
            code = error.args[0]
        elif isinstance(error, SyntaxError):
            code = "SKILL_SYNTAX_INVALID"
        print(marker + json.dumps({"state": "rejected", "error_code": code}, separators=(",", ":")))
        raise SystemExit(2)
""".strip()


ARCHIVE_ERROR_CODES = frozenset(re.findall(r'fail\("([A-Z_]+)"\)', ARCHIVE_CODE)) | {
    "ARCHIVE_INVALID",
    "CREDENTIAL_SHAPED_CONTENT",
    "ENTRYPOINT_REQUIRES_RUN_PAYLOAD",
    "SKILL_SYNTAX_INVALID",
}


def archive_receipt(response, archive_sha):
    stdout = response.get("stdout", "")
    if (
        not isinstance(stdout, str)
        or len(stdout.encode("utf-8")) > 32768
        or response.get("truncated")
        or response.get("error_code")
    ):
        raise PlatformError("SKILL_IMPORT_PROGRAM_FAILED", "The bounded archive scanner did not complete", 422)
    markers = [
        line[len(ARCHIVE_RESULT_PREFIX) :] for line in stdout.splitlines() if line.startswith(ARCHIVE_RESULT_PREFIX)
    ]
    if len(markers) != 1:
        raise PlatformError("SKILL_IMPORT_PROGRAM_FAILED", "The scanner result was not uniquely confirmed", 422)
    value = strict_json(markers[0].encode("utf-8"), max_bytes=8192)
    if (
        isinstance(value, dict)
        and value.get("state") == "rejected"
        and isinstance(value.get("error_code"), str)
        and value["error_code"] in ARCHIVE_ERROR_CODES
    ):
        raise PlatformError(value["error_code"], "The isolated archive scanner rejected this package", 422)
    if (
        response.get("exit_code") != 0
        or not isinstance(value, dict)
        or set(value)
        != {
            "state",
            "schema_version",
            "archive_sha256",
            "package_sha256",
            "package_bytes",
            "files",
            "manual_source_license_review_required",
        }
        or value["state"] != "scanned"
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["archive_sha256"] != archive_sha
        or value["manual_source_license_review_required"] is not True
        or not isinstance(value["package_sha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", value["package_sha256"])
        or type(value["package_bytes"]) is not int
        or not 1 <= value["package_bytes"] <= MAX_PACKAGE_BYTES
        or type(value["files"]) is not int
        or not 1 <= value["files"] <= 48
    ):
        raise PlatformError(
            "SKILL_IMPORT_RESULT_INVALID", "The archive scan receipt does not match its fixed input", 422
        )
    return value


def archive_code(request: dict) -> str:
    """Serialize bounded configuration as data; the output is for remote execution only."""
    from .archive_contracts import SkillArchivePrepare

    body = SkillArchivePrepare.model_validate(request)
    config = body.model_dump(mode="json", exclude={"request_id", "sandbox_profile"})
    limits = {
        "archive_bytes": MAX_ARCHIVE_BYTES,
        "members": MAX_ARCHIVE_MEMBERS,
        "tar_bytes": MAX_TAR_BYTES,
        "ratio": MAX_EXPANSION_RATIO,
        "package_bytes": MAX_PACKAGE_BYTES,
    }
    return (
        ARCHIVE_CODE
        + f"\nscan_archive(json.loads({json.dumps(config, ensure_ascii=False)!r}), "
        + f"{limits!r}, {SCAN_CODE!r}, {CREDENTIAL_PATTERN!r}, {ARCHIVE_RESULT_PREFIX!r})\n"
    )
