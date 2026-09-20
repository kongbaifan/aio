"""Build and smoke-test the separate non-root credential gateway image, using only owned local resources.

This verifies container startup and deployment restrictions, not production networking/HA.
Protocol/TLS integration is tested separately against real loopback servers.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
import secrets
import subprocess
import tempfile
import time

import docker

ROOT = Path(__file__).resolve().parents[2]


def main():
    directory = (ROOT / "var/verification").resolve()
    directory.mkdir(parents=True, exist_ok=True)
    verification = "connector-" + secrets.token_hex(10)
    tag = "aio-connector-gateway:" + verification
    subprocess.run(["docker", "build", "--tag", tag, "services/connector-gateway"], cwd=ROOT, check=True)
    client = docker.from_env(timeout=20)
    container = volume = None
    labels = {"aio.connector-verification": verification, "aio.workspace": str(ROOT)}
    try:
        image = client.images.get(tag)
        with tempfile.TemporaryDirectory(prefix=verification + "-", dir=directory) as raw:
            temp = Path(raw).resolve()
            if not temp.is_relative_to(directory):
                raise ValueError("Verification files must stay in the project verification directory")
            config = temp / "endpoints.json"
            config.write_text('{"endpoints": []}\n', encoding="utf-8")
            volume = client.volumes.create(name=verification + "-vault", labels=labels)
            environment = {
                "CONNECTOR_ENDPOINTS_FILE": "/run/aio/endpoints.json",
                "CONNECTOR_VAULT_ROOT": "/var/lib/aio-connector",
                "CONNECTOR_VAULT_KEY": base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
                "CONNECTOR_SERVICE_TOKEN": secrets.token_urlsafe(40),
                "CONNECTOR_CONTROL_TOKEN": secrets.token_urlsafe(40),
                "CONNECTOR_CONTROL_ORIGIN": "https://control.example.test",
            }
            container = client.containers.run(
                image.id,
                detach=True,
                name=verification,
                labels=labels,
                read_only=True,
                network_mode="none",
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
                mem_limit=256 * 1024 * 1024,
                pids_limit=64,
                nano_cpus=1000000000,
                tmpfs={"/tmp": "size=8m,nosuid,nodev,noexec"},
                environment=environment,
                volumes={
                    volume.name: {"bind": "/var/lib/aio-connector", "mode": "rw"},
                    str(config): {"bind": "/run/aio/endpoints.json", "mode": "ro"},
                },
            )
            probe = "import json,os,pathlib,urllib.request; assert os.getuid()==10002; assert not pathlib.Path('/var/run/docker.sock').exists(); assert 'PLATFORM_DATABASE_URL' not in os.environ; assert 'PLATFORM_OIDC_CLIENT_SECRET' not in os.environ; response=json.load(urllib.request.urlopen('http://127.0.0.1:8082/healthz',timeout=1)); assert response['status']=='ok'; print(json.dumps({'uid':os.getuid(),'health':'ok','vault_exists':pathlib.Path('/var/lib/aio-connector/connector.sqlite3').is_file()}))"
            deadline = time.monotonic() + 30
            while True:
                container.reload()
                if container.status != "running":
                    raise RuntimeError("Owned connector image stopped before healthy; no secret logs are copied")
                result = container.exec_run(["python", "-I", "-c", probe], user="10002:10002")
                if result.exit_code == 0:
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("Owned connector image readiness timed out")
                time.sleep(0.2)
            checked = json.loads(result.output)
            host = container.attrs["HostConfig"]
            assert host["ReadonlyRootfs"] and host["NetworkMode"] == "none" and host["CapDrop"] == ["ALL"]
            assert checked == {"uid": 10002, "health": "ok", "vault_exists": True}
            report = {
                "image": image.id,
                "verification_id": verification,
                "state": "passed",
                "uid": 10002,
                "readonly_root": True,
                "docker_socket_mounted": False,
                "platform_database_or_oidc_secrets": False,
                "private_vault_volume": True,
                "smoke_network": "none",
                "business_network_verified_by_this_test": False,
            }
            (directory / "connector-image.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(
                "Separate credential gateway image startup/isolation smoke passed; production egress/HA gates remain separate."
            )
    finally:
        if container:
            container.reload()
            if container.attrs["Config"].get("Labels", {}).get("aio.connector-verification") != verification:
                raise RuntimeError("Refusing cleanup of an unrelated container")
            container.remove(force=True)
        if volume:
            volume.reload()
            if volume.attrs.get("Labels", {}).get("aio.connector-verification") != verification:
                raise RuntimeError("Refusing cleanup of an unrelated credential volume")
            volume.remove()
        client.close()


if __name__ == "__main__":
    main()
