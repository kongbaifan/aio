"""Operator-only offline approval. Private keys are never accepted by platform/Worker APIs."""

import argparse
import base64
import json
from pathlib import Path

from aio_runtime_policy import RuntimeManifest, approve
from runtime_artifacts import ROOT, docker, file_hash


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument(
        "--key-file", type=Path, required=True, help="Private operator file containing base64 of 32 Ed25519 bytes"
    )
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--purpose", choices=["production", "test"], required=True)
    parser.add_argument("--review-note", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.candidate.stat().st_size > 65536 or args.key_file.stat().st_size > 1024:
        raise ValueError("Operator input exceeds its bound")
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "var") or output.exists():
        raise ValueError("Approval output must be a new file under private project var")
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    if candidate.get("state") != "review_required":
        raise ValueError("Only a built, unapproved candidate can be reviewed")
    for name, key in [
        ("inventory.json", "inventory_sha256"),
        ("smoke.json", "smoke_sha256"),
        ("sbom.cdx.json", "sbom_sha256"),
    ]:
        path = args.candidate.parent / name
        if path.is_symlink() or path.stat().st_size > 65536 or file_hash(path) != candidate[key]:
            raise ValueError("Runtime evidence changed after building")
    manifest = RuntimeManifest.model_validate(candidate["manifest"])
    inventory = json.loads((args.candidate.parent / "inventory.json").read_text(encoding="utf-8"))
    smoke = json.loads((args.candidate.parent / "smoke.json").read_text(encoding="utf-8"))
    expected = {item.name: item.version for item in manifest.packages}
    if (
        any(
            value.get("state") != "passed"
            or value.get("image_digest") != candidate["image_digest"]
            or value.get("container_limits_verified") is not True
            for value in (inventory, smoke)
        )
        or inventory.get("packages") != expected
        or inventory.get("dependency_closure_verified") is not True
        or inventory.get("package_code_imported") is not False
        or smoke.get("imports") != [name for item in manifest.packages for name in item.imports]
        or smoke.get("uid") != 10001
        or smoke.get("network") != "none"
        or smoke.get("readonly_runtime") is not True
    ):
        raise ValueError("Runtime inventory and isolated smoke must be confirmed before approval")
    image = json.loads(docker("image", "inspect", candidate["image_digest"]))[0]
    if image["Config"].get("Labels", {}).get("aio.runtime.manifest_digest") != manifest.digest:
        raise ValueError("Candidate image and runtime manifest do not agree")
    key = base64.b64decode(args.key_file.read_text(encoding="utf-8").strip(), validate=True)
    approval = approve(
        manifest,
        candidate["image_digest"],
        candidate,
        key_id=args.key_id,
        private_key=key,
        purpose=args.purpose,
        review_note=args.review_note,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as destination:
        destination.write(approval.model_dump_json(indent=2) + "\n")
    print("Wrote signed runtime approval (no private key in artifact):", output)


if __name__ == "__main__":
    main()
