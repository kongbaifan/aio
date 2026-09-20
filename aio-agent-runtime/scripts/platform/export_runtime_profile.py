"""Validate a signed operator approval and emit a fixed profile; never pull/build/install or run packages."""

import argparse
import json
from pathlib import Path

from aio_runtime_policy import load_trust_keys, verify_approval
from aio_sandbox_manager.contracts import Profile
from runtime_artifacts import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--trust-keys", type=Path, required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--allow-test",
        action="store_true",
        help="Synthetic local verification only; production consumers still reject test approvals",
    )
    args = parser.parse_args()
    if args.approval.stat().st_size > 65536:
        raise ValueError("Approval exceeds its bound")
    raw = json.loads(args.approval.read_text(encoding="utf-8"))
    approval = verify_approval(raw, raw["image_digest"], load_trust_keys(args.trust_keys), allow_test=args.allow_test)
    profile = {
        "id": args.profile_id,
        "image_digest": approval.image_digest,
        "runtime_approval": approval.model_dump(mode="json"),
        "memory_bytes": 512 * 1024 * 1024,
        "temp_bytes": 32 * 1024 * 1024,
        "max_timeout_seconds": 60,
    }
    Profile(**profile)
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "var") or output.exists():
        raise ValueError("Profile output must be a new private project var file")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as file:
        file.write(json.dumps({"profiles": [profile]}, indent=2) + "\n")
    print("Wrote verified runtime profile without executing packages:", output)


if __name__ == "__main__":
    main()
