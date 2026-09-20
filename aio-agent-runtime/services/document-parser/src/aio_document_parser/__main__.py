"""Fixed parser command run by sandbox-manager, never imported as an API fallback."""

import hashlib
import json
from pathlib import Path

from .parser import MAX_SOURCE_BYTES, ParseFailure, parse


def main():
    try:
        manifest_raw = Path("parse-request.json").read_bytes()
        if len(manifest_raw) > 4096:
            raise ParseFailure("DOCUMENT_MANIFEST_INVALID")
        manifest = json.loads(manifest_raw)
        if set(manifest) != {"schema_version", "format", "source_sha256"} or manifest["schema_version"] != 1:
            raise ParseFailure("DOCUMENT_MANIFEST_INVALID")
        with Path("document.bin").open("rb") as source:
            raw = source.read(MAX_SOURCE_BYTES + 1)
        if hashlib.sha256(raw).hexdigest() != manifest["source_sha256"]:
            raise ParseFailure("DOCUMENT_SOURCE_CHANGED")
        result = parse(raw, manifest["format"])
        encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        Path("parsed-document.json").write_bytes(encoded)
        print(
            json.dumps(
                {
                    "status": "parsed",
                    "sha256": hashlib.sha256(encoded).hexdigest(),
                    "bytes": len(encoded),
                    "chunks": len(result["chunks"]),
                }
            )
        )
    except ParseFailure as exc:
        print(json.dumps({"status": "rejected", "code": str(exc)}))
        raise SystemExit(2) from None
    except Exception:
        print('{"status":"rejected","code":"DOCUMENT_PARSE_FAILED"}')
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
