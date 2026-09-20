"""Trusted CI/operator helpers. These are not imported by a browser, Worker, or user tool driver."""

import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from aio_runtime_policy import RuntimeManifest, canonical_digest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "services/dependency-runtime"
FILES = ("Dockerfile", ".dockerignore", "check_wheels.py", "inventory.py", "smoke.py")


def recipe_digest():
    return canonical_digest(
        "aio-runtime-recipe-v1", {name: hashlib.sha256((TEMPLATE / name).read_bytes()).hexdigest() for name in FILES}
    )


def docker(*args):
    return subprocess.run(["docker", *args], check=True, capture_output=True, text=True).stdout.strip()


def read_manifest(path):
    path = Path(path)
    if path.stat().st_size > 65536:
        raise ValueError("Runtime lock exceeds its bound")
    return RuntimeManifest.model_validate_json(path.read_bytes())


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download_wheels(manifest, directory):
    """Fetch opaque pinned wheel bytes only. All archive/metadata interpretation happens inside the build cell."""
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as client:
        for package in manifest.packages:
            target = directory / package.filename
            if target.exists():
                if target.is_symlink() or target.stat().st_size != package.bytes or file_hash(target) != package.sha256:
                    raise ValueError("Existing wheel cache does not match its approved immutable content")
                continue
            with client.stream("GET", f"https://pypi.org/pypi/{package.name}/{package.version}/json") as response:
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_bytes(65536):
                    data.extend(chunk)
                    if len(data) > 2 * 1024 * 1024:
                        raise ValueError("Index metadata exceeds its bound")
            candidates = [item for item in json.loads(data)["urls"] if item["filename"] == package.filename]
            if (
                len(candidates) != 1
                or candidates[0]["digests"]["sha256"] != package.sha256
                or candidates[0]["size"] != package.bytes
            ):
                raise ValueError("Index no longer provides the exact reviewed wheel")
            url = candidates[0]["url"]
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or parsed.hostname != "files.pythonhosted.org"
                or parsed.port not in {None, 443}
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("Unexpected wheel download authority")
            staged = directory / ("download-" + uuid4().hex)
            total, digest = 0, hashlib.sha256()
            with client.stream("GET", url) as response, staged.open("xb") as stream:
                response.raise_for_status()
                for chunk in response.iter_bytes(65536):
                    total += len(chunk)
                    if total > package.bytes:
                        raise ValueError("Wheel download exceeded its approved size")
                    digest.update(chunk)
                    stream.write(chunk)
            if total != package.bytes or digest.hexdigest() != package.sha256:
                raise ValueError("Wheel download failed integrity validation; quarantined bytes are not installed")
            staged.rename(target)
            print("Fetched fixed wheel", package.name, package.version, package.sha256)


def probe(image, kind, verification):
    if kind not in {"inventory", "smoke"}:
        raise ValueError("Only fixed runtime probes are supported")
    scope = "runtime-probe-" + uuid4().hex
    id = docker(
        "create",
        "--label",
        "aio.runtime-probe=" + scope,
        "--label",
        "aio.verification-run=" + verification,
        "--network",
        "none",
        "--read-only",
        "--user",
        "10001:10001",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--memory",
        "512m",
        "--memory-swap",
        "512m",
        "--cpus",
        "1",
        "--pids-limit",
        "64",
        "--log-driver",
        "none",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=67108864,mode=0700,uid=10001,gid=10001",
        "--tmpfs",
        "/home/runner:rw,nosuid,nodev,size=8388608,mode=0700,uid=10001,gid=10001",
        image,
        "/usr/local/bin/python",
        "-I",
        "-S",
        "/opt/aio-runtime/" + kind + ".py",
    )
    process = None
    stop = threading.Event()
    events = queue.Queue(maxsize=8)
    threads = []

    def reader(stream, channel):
        try:
            while not stop.is_set():
                data = stream.read(4096)
                while not stop.is_set():
                    try:
                        events.put((channel, data), timeout=0.1)
                        break
                    except queue.Full:
                        pass
                if not data:
                    break
        finally:
            stream.close()

    try:
        process = subprocess.Popen(
            ["docker", "start", "--attach", id],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        for channel, stream in [("out", process.stdout), ("err", process.stderr)]:
            thread = threading.Thread(target=reader, args=(stream, channel), daemon=True)
            thread.start()
            threads.append(thread)
        output = {"out": bytearray(), "err": bytearray()}
        done = set()
        deadline = time.monotonic() + 60
        while len(done) != 2:
            if time.monotonic() > deadline:
                raise RuntimeError("Runtime probe exceeded its external deadline")
            try:
                channel, chunk = events.get(timeout=0.1)
            except queue.Empty:
                continue
            if not chunk:
                done.add(channel)
            else:
                output[channel].extend(chunk)
                if len(output[channel]) > (65536 if channel == "out" else 16384):
                    raise RuntimeError("Runtime probe output exceeded its bound")
        process.wait(timeout=5)
        actual = json.loads(docker("inspect", id))[0]
        if actual["Config"]["Labels"].get("aio.runtime-probe") != scope:
            raise RuntimeError("Runtime probe ownership changed")
        if actual["State"]["ExitCode"] != 0 or actual["State"].get("OOMKilled") or process.returncode:
            # Only a bounded tail from this synthetic/operator probe; never user Run output or credentials.
            raise RuntimeError("Runtime probe failed: " + output["err"].decode("utf-8", "replace")[-2000:])
        host = actual["HostConfig"]
        if (
            not host["ReadonlyRootfs"]
            or host["NetworkMode"] != "none"
            or actual["Config"]["User"] != "10001:10001"
            or any(m["Type"] != "tmpfs" for m in actual.get("Mounts", []))
        ):
            raise RuntimeError("Runtime probe isolation was not enforced")
        result = json.loads(output["out"])
        if result.get("schema_version") != 1 or result.get("state") != "passed":
            raise RuntimeError("Runtime probe did not produce its expected receipt")
        return {**result, "container_limits_verified": True, "image_digest": image}
    finally:
        stop.set()
        actual = json.loads(docker("inspect", id))[0]
        if actual["Config"]["Labels"].get("aio.runtime-probe") != scope:
            raise RuntimeError("Refusing to clean an unrelated container")
        docker("rm", "--force", "--volumes", actual["Id"])
        if process and process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=2)


def build(manifest, wheelhouse, output, *, verification):
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT / "var") or output.exists():
        raise ValueError("Build output must be a new private directory under project var")
    if manifest.recipe_sha256 != recipe_digest():
        raise ValueError("Runtime recipe changed; review and regenerate the lock before building")
    output.mkdir(parents=True)
    context = output / "context"
    context.mkdir()
    wheels = context / "wheels"
    wheels.mkdir()
    for name in FILES:
        shutil.copyfile(TEMPLATE / name, context / name)
    for package in manifest.packages:
        source = Path(wheelhouse).resolve() / package.filename
        if source.is_symlink() or source.stat().st_size != package.bytes or file_hash(source) != package.sha256:
            raise ValueError("A wheel does not match its approved immutable lock")
        shutil.copyfile(source, wheels / package.filename)
        if file_hash(wheels / package.filename) != package.sha256:
            raise ValueError("Wheel changed while transferring the build context")
    data = manifest.model_dump(mode="json")
    (context / "manifest.json").write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (context / "requirements.lock").write_text(
        "\n".join(f"{p.name}=={p.version} --hash=sha256:{p.sha256}" for p in manifest.packages) + "\n", encoding="utf-8"
    )
    tag = "aio-dependency-runtime:" + verification
    subprocess.run(
        [
            "docker",
            "build",
            "--network=none",
            "--tag",
            tag,
            "--build-arg",
            "BASE_IMAGE=" + manifest.base_image,
            "--build-arg",
            "MANIFEST_DIGEST=" + manifest.digest,
            str(context),
        ],
        check=True,
    )
    image = docker("image", "inspect", tag, "--format", "{{.Id}}")
    inventory, smoke = probe(image, "inventory", verification), probe(image, "smoke", verification)
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {"component": {"type": "container", "name": manifest.name, "version": image}},
        "components": [
            {
                "type": "library",
                "name": p.name,
                "version": p.version,
                "purl": f"pkg:pypi/{p.name}@{p.version}",
                "hashes": [{"alg": "SHA-256", "content": p.sha256}],
            }
            for p in manifest.packages
        ],
    }
    for name, value in [
        ("manifest.json", data),
        ("inventory.json", inventory),
        ("smoke.json", smoke),
        ("sbom.cdx.json", sbom),
    ]:
        (output / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    candidate = {
        "schema_version": 1,
        "state": "review_required",
        "image_digest": image,
        "manifest": data,
        "inventory_sha256": file_hash(output / "inventory.json"),
        "smoke_sha256": file_hash(output / "smoke.json"),
        "sbom_sha256": file_hash(output / "sbom.cdx.json"),
        "vulnerability_review": "not_claimed_by_inventory_or_functional_smoke",
    }
    (output / "candidate.json").write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
    return candidate
