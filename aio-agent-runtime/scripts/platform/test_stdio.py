"""Build the immutable SDK reference image and exercise real isolated stdio pipes."""

import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

from test_sandbox import cleanup, docker

ROOT = Path(__file__).resolve().parents[2]


def build(verification):
    lock = ROOT / "services/mcp-stdio-runtime/requirements.lock"
    digest = hashlib.sha256(lock.read_bytes()).hexdigest()
    tag = "aio-mcp-stdio:" + verification
    subprocess.run(
        ["docker", "build", "--build-arg", "DEPENDENCY_DIGEST=" + digest, "--tag", tag, "services/mcp-stdio-runtime"],
        cwd=ROOT,
        check=True,
    )
    image = docker("image", "inspect", tag, "--format", "{{.Id}}")
    profile = {
        "id": "stdio-reference",
        "image_digest": image,
        "executable": "/usr/local/bin/python",
        "arguments": ["-I", "-u", "/opt/mcp/example_server.py"],
        "dependency_digest": digest,
        "credential_env": "MCP_ACCESS_TOKEN",
        "input_policy": "run_attachments",
    }
    directory = ROOT / "var/verification"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "stdio-profile.json").write_text(
        json.dumps({"profiles": [profile]}, indent=2) + "\n", encoding="utf-8"
    )
    return image


def main():
    verification = "stdio-" + secrets.token_hex(10)
    image = build(verification)
    try:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "services/sandbox-manager/tests/test_stdio.py",
                "-q",
                "--tb=short",
                "--junitxml=var/verification/stdio-manager.xml",
            ],
            cwd=ROOT,
            env={**os.environ, "AIO_TEST_STDIO_IMAGE": image, "AIO_VERIFICATION_RUN_ID": verification},
            check=False,
        ).returncode
    finally:
        cleanup(verification)


if __name__ == "__main__":
    raise SystemExit(main())
