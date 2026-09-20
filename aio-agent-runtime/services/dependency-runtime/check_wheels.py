"""Runs ONLY inside the non-root offline build stage, before pip sees wheel archives."""

from email.parser import BytesParser
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import sys
import unicodedata
import zipfile

root = Path("/opt/aio-wheels")
manifest = json.loads(Path("/opt/aio-builder/manifest.json").read_text(encoding="utf-8"))
total_bytes, total_files = 0, 0
reserved = set(sys.stdlib_module_names) | {"pip", "setuptools", "sitecustomize", "usercustomize"}

for package in manifest["packages"]:
    file = root / package["filename"]
    if file.is_symlink() or file.stat().st_size != package["bytes"]:
        raise ValueError("WHEEL_SIZE_MISMATCH")
    with file.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != package["sha256"]:
            raise ValueError("WHEEL_HASH_MISMATCH")
        source.seek(max(0, file.stat().st_size - 65557))
        tail = source.read(65557)
    end = tail.rfind(b"PK\x05\x06")
    if end < 0 or len(tail) - end < 22:
        raise ValueError("WHEEL_CENTRAL_DIRECTORY_INVALID")
    record = struct.unpack_from("<4s4H2LH", tail, end)
    if record[1] or record[2] or record[3] != record[4] or record[4] > 12000 or record[5] > 16 * 1024 * 1024:
        raise ValueError("WHEEL_DIRECTORY_LIMIT_OR_MULTIDISK")
    with zipfile.ZipFile(file) as archive:
        entries = archive.infolist()
        if len(entries) != record[4]:
            raise ValueError("WHEEL_ENTRY_COUNT_MISMATCH")
        seen, metadata = set(), []
        for entry in entries:
            name = entry.filename.rstrip("/")
            parts = name.split("/")
            key = name.casefold()
            mode = entry.external_attr >> 16
            if (
                not name
                or entry.orig_filename != entry.filename
                or key in seen
                or len(name) > 512
                or unicodedata.normalize("NFC", name) != name
                or "\\" in name
                or ":" in name
                or any(ord(ch) < 32 for ch in name)
                or PurePosixPath(name).is_absolute()
                or any(part in {"", ".", ".."} for part in parts)
                or len(parts) > 20
                or stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}
                or mode & 0o7000
                or entry.flag_bits & 1
                or entry.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                or entry.file_size > 64 * 1024 * 1024
                or entry.file_size > max(1, entry.compress_size) * 200
                or name.lower().endswith(".pth")
                or parts[0].split(".")[0] in reserved
            ):
                raise ValueError("WHEEL_PATH_TYPE_OR_EXPANSION_DENIED")
            seen.add(key)
            total_bytes += entry.file_size
            total_files += 1
            if total_bytes > 512 * 1024 * 1024 or total_files > 20000:
                raise ValueError("WHEEL_EXPANSION_QUOTA")
            if len(parts) == 2 and parts[0].endswith(".dist-info") and parts[1] == "METADATA":
                if entry.file_size > 256 * 1024:
                    raise ValueError("WHEEL_METADATA_LIMIT")
                metadata.append(BytesParser().parsebytes(archive.read(entry)))
        if len(metadata) != 1:
            raise ValueError("WHEEL_METADATA_REQUIRED")
        value = metadata[0]
        if (
            re.sub(r"[-_.]+", "-", value.get("Name", "")).lower() != package["name"]
            or value.get("Version") != package["version"]
        ):
            raise ValueError("WHEEL_IDENTITY_MISMATCH")
print(json.dumps({"checked_wheels": len(manifest["packages"]), "entries": total_files, "expanded_bytes": total_bytes}))
