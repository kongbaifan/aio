"""Validate the bounded manager-produced file bundle, without extracting archives on the host."""

import base64
import hashlib
from sqlalchemy import or_
from sqlalchemy.dialects.postgresql import JSONB
from ..platform_errors import PlatformError
from .storage import MAX_BLOB_BYTES, safe_path


def unbound_manifest(column):
    # Legacy SQLAlchemy JSONB(None) wrote JSON null, not SQL NULL. Both mean
    # no export intent; [] is a real bound empty export and is not equivalent.
    return or_(column.is_(None), column == JSONB.NULL)


def prepare_export(files):
    if not isinstance(files, list) or len(files) > 64:
        raise PlatformError("ARTIFACT_QUOTA_EXCEEDED", "Too many generated files", 413)
    prepared, paths, total = [], set(), 0
    for file in files:
        try:
            if not isinstance(file, dict) or set(file) != {"path", "content_b64", "bytes", "sha256"}:
                raise ValueError
            path = safe_path(file["path"])
            raw = file["content_b64"]
            if not isinstance(raw, str) or len(raw) > (MAX_BLOB_BYTES + 2) // 3 * 4:
                raise ValueError
            data = base64.b64decode(raw, validate=True)
            total += len(data)
            sha = hashlib.sha256(data).hexdigest()
            if (
                path in paths
                or total > MAX_BLOB_BYTES
                or type(file["bytes"]) is not int
                or len(data) != file["bytes"]
                or sha != file["sha256"]
            ):
                raise ValueError
        except (ValueError, TypeError, KeyError):
            raise PlatformError(
                "ARTIFACT_INVALID", "Generated file manifest is invalid or exceeds quota", 409
            ) from None
        paths.add(path)
        prepared.append({"path": path, "sha256": sha, "bytes": len(data), "data": data})
    prepared.sort(key=lambda item: item["path"])
    return prepared, [{key: value for key, value in item.items() if key != "data"} for item in prepared]
