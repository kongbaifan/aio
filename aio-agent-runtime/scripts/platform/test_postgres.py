"""Run platform tests against a disposable, loopback-only PostgreSQL container.

No host database is installed, no user data is mounted, and cleanup is limited to
the exact container ID and workspace label this process created. Pull the selected
test image explicitly before invoking this command; it does not retry/restart pulls.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from urllib.parse import quote

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

ROOT = Path(__file__).resolve().parents[2]


def docker(*args: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], check=True, text=True, capture_output=True, **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image", default="pgvector/pgvector@sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f"
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    docker("image", "inspect", args.image)
    label = "aio.platform-verification"
    name = "aio-platform-test-" + secrets.token_hex(5)
    password = secrets.token_urlsafe(40)
    env = {**os.environ, "POSTGRES_PASSWORD": password}
    container_id = None
    try:
        created = docker(
            "run",
            "--rm",
            "--detach",
            "--name",
            name,
            "--label",
            label + "=true",
            "--label",
            "aio.workspace=" + str(ROOT),
            "--memory",
            "384m",
            "--cpus",
            "1",
            "--pids-limit",
            "128",
            "--publish",
            "127.0.0.1::5432",
            "--env",
            "POSTGRES_PASSWORD",
            "--env",
            "POSTGRES_USER=platform_migrator",
            "--env",
            "POSTGRES_DB=aio_platform_test",
            args.image,
            env=env,
        )
        container_id = created.stdout.strip()
        port_mapping = docker("port", container_id, "5432/tcp").stdout.strip()
        if not port_mapping.startswith("127.0.0.1:") or "\n" in port_mapping:
            raise RuntimeError("Verification PostgreSQL must bind only one loopback address")
        port = int(port_mapping.rsplit(":", 1)[1])
        url = f"postgresql+psycopg://platform_migrator:{quote(password, safe='')}@127.0.0.1:{port}/aio_platform_test"
        engine = create_engine(url, hide_parameters=True, connect_args={"connect_timeout": 2})
        deadline = time.monotonic() + 60
        while True:
            try:
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
                break
            except SQLAlchemyError:
                running = json.loads(docker("inspect", container_id).stdout)[0]["State"]["Running"]
                if not running or time.monotonic() >= deadline:
                    raise RuntimeError("Disposable verification database did not become ready") from None
                time.sleep(0.5)
        engine.dispose()
        test_env = {**os.environ, "AIO_TEST_POSTGRES_URL": url}
        # Prevent ambient user service settings from turning the isolated tests into a production run.
        test_env["HARNESS_MODE"] = "legacy-local"
        command = [sys.executable, "-m", "pytest", "apps/local-harness/tests/platform", "-q", "-ra", "--tb=short"]
        if args.report:
            report = args.report.resolve()
            if not report.is_relative_to(ROOT):
                raise ValueError("Verification reports must remain in this project workspace")
            report.parent.mkdir(parents=True, exist_ok=True)
            command.append("--junitxml=" + str(report))
        result = subprocess.run(command, cwd=ROOT, env=test_env, check=False)
        image = json.loads(docker("image", "inspect", args.image).stdout)[0]
        print("Verification image:", image.get("RepoDigests") or image["Id"])
        return result.returncode
    finally:
        if container_id:
            inspection = subprocess.run(["docker", "inspect", container_id], text=True, capture_output=True)
            if inspection.returncode == 0:
                item = json.loads(inspection.stdout)[0]
                labels = item["Config"].get("Labels", {})
                if (
                    item["Id"] != container_id
                    or labels.get(label) != "true"
                    or labels.get("aio.workspace") != str(ROOT)
                ):
                    raise RuntimeError("Refusing to remove a container not owned by this verification run")
                docker("rm", "--force", container_id)


if __name__ == "__main__":
    raise SystemExit(main())
