"""Run the built workbench's real HTTP verification in an owned finite-lived local stack.

This does not claim browser visual inspection. Synthetic identity/model providers
exercise actual API, PostgreSQL, Worker, Docker and artifact paths.
"""

from __future__ import annotations
import json
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]


def choose_ports():
    for _ in range(100):
        port = 20000 + secrets.randbelow(20000)
        sockets = []
        try:
            for offset in range(4):
                sock = socket.socket()
                sock.bind(("127.0.0.1", port + offset))
                sockets.append(sock)
            return port
        except OSError:
            pass
        finally:
            for sock in sockets:
                sock.close()
    raise RuntimeError("No verification port range available")


def main():
    directory = ROOT / "var/verification"
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="workbench-http-", dir=directory) as temp:
        temp = Path(temp).resolve()
        if not temp.is_relative_to(directory.resolve()):
            raise ValueError("Invalid test workspace")
        info = temp / "info.json"
        stop = temp / "stop"
        log_path = directory / "workbench-http-server.log"
        process = None
        verification = None
        try:
            with log_path.open("w", encoding="utf-8") as output:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "scripts/platform/preview_workbench.py",
                        "--port",
                        str(choose_ports()),
                        "--lifetime",
                        "300",
                        "--info-path",
                        str(info),
                        "--stop-file",
                        str(stop),
                    ],
                    cwd=ROOT,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                )
                deadline = time.monotonic() + 90
                while True:
                    if process.poll() is not None:
                        raise RuntimeError("Verification stack stopped before ready; inspect its scoped test log")
                    if info.exists():
                        try:
                            data = json.loads(info.read_text(encoding="utf-8"))
                        except (OSError, ValueError):
                            data = {}
                        if data.get("state") == "running":
                            verification = data["verification_id"]
                            break
                    if time.monotonic() > deadline:
                        raise RuntimeError("Verification stack readiness timed out")
                    time.sleep(0.1)
                result = subprocess.run(
                    [sys.executable, "scripts/platform/verify_workbench_http.py", "--info", str(info)],
                    cwd=ROOT,
                    check=False,
                )
                if result.returncode:
                    raise RuntimeError("Live workbench HTTP assertions failed")
                stop.touch()
                process.wait(timeout=30)
                if process.returncode:
                    raise RuntimeError("Verification stack did not shut down cleanly; inspect test log")
            print("Workbench HTTP assertions and owned-service cleanup passed. Browser visual QA remains separate.")
        finally:
            stop.touch(exist_ok=True)
            if process and process.poll() is None:
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=10)
            if verification:
                from test_sandbox import cleanup

                cleanup(verification)
                from test_postgres import docker

                rows = docker("ps", "-aq", "--filter", "label=aio.preview=" + verification).stdout.splitlines()
                for id in rows:
                    owned = json.loads(docker("inspect", id).stdout)[0]
                    if owned["Config"].get("Labels", {}).get("aio.preview") != verification:
                        raise RuntimeError("Unexpected cleanup ownership")
                    docker("rm", "--force", owned["Id"])


if __name__ == "__main__":
    main()
