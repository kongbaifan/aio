"""Bounded content-addressed local object store, never mounted into user cells.

Filesystem permissions on this root are a trusted storage-service boundary.
Object hashes are scoped by org, checked on write/read, and never used as grants.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from ..platform_errors import PlatformError

MAX_BLOB_BYTES = 8 * 1024 * 1024


def safe_path(value: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 512:
        raise PlatformError("INVALID_PATH", "File path is invalid", 422)
    if any(ord(ch) < 32 for ch in value) or "\\" in value or ":" in value:
        raise PlatformError("INVALID_PATH", "Unsupported file path", 422)
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"..", ".", ""} for part in value.split("/")) or len(path.parts) > 12:
        raise PlatformError("INVALID_PATH", "A bounded relative file path is required", 422)
    return value


class BlobStore:
    def __init__(self, root: Path):
        root = Path(root)
        if not root.is_absolute():
            raise ValueError("Artifact root must be an explicit absolute path")
        if root.exists() and root.is_symlink():
            raise ValueError("Artifact root cannot be a symlink")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = root.resolve()

    def _path(self, org_id: UUID, sha256: str) -> Path:
        if not isinstance(org_id, UUID) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise PlatformError("INVALID_BLOB_REFERENCE", "Object reference is invalid", 422)
        parent = self.root
        for part in ("objects", org_id.hex, sha256[:2]):
            candidate = parent / part
            if candidate.is_symlink() or (candidate.exists() and not candidate.is_dir()):
                raise PlatformError("STORAGE_BOUNDARY_INVALID", "Object store ancestry is not trusted", 503)
            if not candidate.resolve().is_relative_to(self.root):
                raise PlatformError("STORAGE_BOUNDARY_INVALID", "Object store path leaves its approved root", 503)
            candidate.mkdir(exist_ok=True, mode=0o700)
            parent = candidate
        return parent / sha256

    def put(self, org_id: UUID, data: bytes) -> str:
        if not isinstance(data, bytes) or len(data) > MAX_BLOB_BYTES:
            raise PlatformError("PAYLOAD_TOO_LARGE", "File exceeds the bounded object limit", 413)
        sha = hashlib.sha256(data).hexdigest()
        target = self._path(org_id, sha)
        if target.exists():
            self.get(org_id, sha, len(data))
            return sha
        if shutil.disk_usage(self.root).free < len(data) + 256 * 1024 * 1024:
            raise PlatformError(
                "STORAGE_CAPACITY_LOW", "Persistent storage has reached its safe free-space reserve", 503
            )
        temp = target.with_name(".upload-" + uuid4().hex)
        fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, getattr(stat, "S_IRUSR") | getattr(stat, "S_IWUSR"))
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            try:
                os.link(temp, target)
            except FileExistsError:
                self.get(org_id, sha, len(data))
        finally:
            temp.unlink(missing_ok=True)
        return sha

    def get(self, org_id: UUID, sha256: str, expected_size: int) -> bytes:
        if type(expected_size) is not int or not 0 <= expected_size <= MAX_BLOB_BYTES:
            raise PlatformError("INVALID_BLOB_REFERENCE", "Object size is invalid", 422)
        path = self._path(org_id, sha256)
        try:
            if path.is_symlink():
                raise OSError
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
            with os.fdopen(fd, "rb") as f:
                info = os.fstat(f.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size != expected_size:
                    raise OSError
                data = f.read(MAX_BLOB_BYTES + 1)
        except OSError:
            raise PlatformError("BLOB_UNAVAILABLE", "Stored file cannot be read safely", 503) from None
        if len(data) != expected_size or hashlib.sha256(data).hexdigest() != sha256:
            raise PlatformError("BLOB_INTEGRITY_ERROR", "Stored file failed integrity validation", 503)
        return data

    def remove(self, org_id: UUID, sha256: str) -> bool:
        """Trusted GC only: caller must hold the org storage lock and verify all durable references first."""
        path = self._path(org_id, sha256)
        if not path.resolve().is_relative_to(self.root):
            raise PlatformError("STORAGE_BOUNDARY_INVALID", "Object deletion leaves the approved root", 503)
        try:
            info = path.lstat()
        except FileNotFoundError:
            return False
        if not stat.S_ISREG(info.st_mode) or path.is_symlink():
            raise PlatformError("STORAGE_BOUNDARY_INVALID", "Only an owned regular blob can be deleted", 503)
        path.unlink()
        return True
