"""Build and approve an explicitly synthetic dependency profile, then verify actual isolated execution."""

import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from runtime_artifacts import ROOT, build, download_wheels, read_manifest
from test_sandbox import cleanup


def prepare(verification):
    manifest = read_manifest(ROOT / "config/runtime-locks/analytics-python.json")
    wheelhouse = ROOT / "var/runtime-wheels/analytics"
    download_wheels(manifest, wheelhouse)
    output = ROOT / "var/runtime-candidates" / verification
    candidate = build(manifest, wheelhouse, output, verification=verification)
    key = Ed25519PrivateKey.generate()
    key_id = "synthetic-runtime-verification"
    directory = ROOT / "var/verification"
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="runtime-signing-", dir=directory) as temporary:
        temporary = Path(temporary).resolve()
        if not temporary.is_relative_to(directory.resolve()):
            raise ValueError("Invalid test signing workspace")
        private = temporary / "synthetic-private-key"
        private.write_bytes(base64.b64encode(key.private_bytes_raw()))
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/platform/approve_runtime.py"),
                "--candidate",
                str(output / "candidate.json"),
                "--key-file",
                str(private),
                "--key-id",
                key_id,
                "--purpose",
                "test",
                "--review-note",
                "Synthetic verification only; this does not approve company production use or vulnerability gates.",
                "--output",
                str(output / "approval.json"),
            ],
            check=True,
            cwd=ROOT,
        )
    approval = json.loads((output / "approval.json").read_text(encoding="utf-8"))
    trust = {
        "keys": [{"id": key_id, "public_key": base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")}]
    }
    profile = {
        "id": "analytics",
        "image_digest": candidate["image_digest"],
        "runtime_approval": approval,
        "memory_bytes": 512 * 1024 * 1024,
        "temp_bytes": 32 * 1024 * 1024,
        "max_timeout_seconds": 60,
    }
    (directory / "dependency-profile.json").write_text(
        json.dumps({"profiles": [profile]}, indent=2) + "\n", encoding="utf-8"
    )
    (directory / "runtime-trust.json").write_text(json.dumps(trust, indent=2) + "\n", encoding="utf-8")
    (directory / "dependency-build.json").write_text(
        json.dumps(
            {
                "state": "passed",
                "verification_id": verification,
                "candidate": str(output.relative_to(ROOT)).replace("\\", "/"),
                "image": candidate["image_digest"],
                "manifest_digest": manifest.digest,
                "purpose": "test",
                "sbom": str((output / "sbom.cdx.json").relative_to(ROOT)).replace("\\", "/"),
                "vulnerability_review": "not_claimed",
                "license_review": "operator_required",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "AIO_TEST_DEPENDENCY_PROFILE": str(directory / "dependency-profile.json"),
        "AIO_TEST_RUNTIME_TRUST_KEYS": str(directory / "runtime-trust.json"),
    }


def main():
    verification = "dependencies-" + secrets.token_hex(10)
    try:
        env = {**os.environ, **prepare(verification), "AIO_VERIFICATION_RUN_ID": verification}
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "services/sandbox-manager/tests/test_dependency_runtime.py",
                "-q",
                "--tb=short",
                "--junitxml=var/verification/dependency-manager.xml",
            ],
            cwd=ROOT,
            env=env,
            check=False,
        ).returncode
    finally:
        cleanup(verification)


if __name__ == "__main__":
    raise SystemExit(main())
