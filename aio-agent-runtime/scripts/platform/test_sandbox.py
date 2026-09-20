"""Build a pinned compute image and run real Docker plus PostgreSQL integration tests.

Every test resource is labeled with a fresh verification ID. Cleanup inspects exact
container/volume labels and never touches an unrelated user service or workspace.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def docker(*args):
    return subprocess.run(["docker", *args], check=True, capture_output=True, text=True).stdout.strip()


def cleanup(verification):
    for container in docker("ps", "-aq", "--filter", "label=aio.verification-run=" + verification).splitlines():
        actual = json.loads(docker("inspect", container))[0]
        if actual["Config"].get("Labels", {}).get("aio.verification-run") != verification:
            raise RuntimeError("Refusing to remove an unrelated container")
        docker("rm", "--force", actual["Id"])
    for name in docker("volume", "ls", "-q", "--filter", "label=aio.verification-run=" + verification).splitlines():
        actual = json.loads(docker("volume", "inspect", name))[0]
        if actual.get("Labels", {}).get("aio.verification-run") != verification:
            raise RuntimeError("Refusing to remove an unrelated volume")
        docker("volume", "rm", actual["Name"])


def main():
    verification = "verify-" + secrets.token_hex(10)
    tag = "aio-platform-compute:" + verification
    subprocess.run(["docker", "build", "--tag", tag, "services/run-executor"], cwd=ROOT, check=True)
    image = docker("image", "inspect", tag, "--format", "{{.Id}}")
    parser_tag = "aio-document-parser:" + verification
    subprocess.run(["docker", "build", "--tag", parser_tag, "services/document-parser"], cwd=ROOT, check=True)
    parser_image = docker("image", "inspect", parser_tag, "--format", "{{.Id}}")
    from test_stdio import build as build_stdio

    stdio_image = build_stdio(verification)
    from test_dependency_runtime import prepare as prepare_dependencies

    dependency_environment = prepare_dependencies(verification + "-dependencies")
    env = {
        **os.environ,
        "AIO_TEST_COMPUTE_IMAGE": image,
        "AIO_TEST_DOCUMENT_IMAGE": parser_image,
        "AIO_TEST_STDIO_IMAGE": stdio_image,
        "AIO_VERIFICATION_RUN_ID": verification,
        **dependency_environment,
    }
    env["PYTHONPATH"] = str(ROOT / "services/sandbox-manager/src") + os.pathsep + env.get("PYTHONPATH", "")
    reports = ROOT / "var/verification"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "sandbox-profile.json").write_text(
        json.dumps({"profiles": [{"id": "standard", "image_digest": image}]}, indent=2) + "\n", encoding="utf-8"
    )
    (reports / "document-profile.json").write_text(
        json.dumps(
            {"profiles": [{"id": "documents", "image_digest": parser_image, "max_timeout_seconds": 60}]}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    try:
        commands = [
            [
                sys.executable,
                "-m",
                "pytest",
                "packages/runtime-policy/tests",
                "-q",
                "--tb=short",
                "--junitxml=" + str(reports / "runtime-policy.xml"),
            ],
            [
                sys.executable,
                "-m",
                "pytest",
                "services/sandbox-manager/tests",
                "-q",
                "--tb=short",
                "--junitxml=" + str(reports / "sandbox-manager.xml"),
            ],
            [sys.executable, "scripts/platform/test_postgres.py", "--report", str(reports / "platform-postgres.xml")],
            [
                sys.executable,
                "-m",
                "pytest",
                "services/connector-gateway/tests",
                "-q",
                "--tb=short",
                "--junitxml=" + str(reports / "connector-gateway.xml"),
            ],
            [
                sys.executable,
                "-m",
                "pytest",
                "services/document-parser/tests",
                "-q",
                "--tb=short",
                "--junitxml=" + str(reports / "document-parser.xml"),
            ],
        ]
        code = 0
        for command in commands:
            result = subprocess.run(command, cwd=ROOT, env=env, check=False)
            code = code or result.returncode
        print("Verified compute image:", image)
        return code
    finally:
        cleanup(verification)
        # The local built image is intentionally retained as a reproducible test/development artifact.


if __name__ == "__main__":
    raise SystemExit(main())
