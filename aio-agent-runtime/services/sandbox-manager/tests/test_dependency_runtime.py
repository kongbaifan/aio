import base64
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
from uuid import uuid4
import zipfile

import pytest

from aio_runtime_policy import load_trust_keys
from aio_sandbox_manager.contracts import CellSpec, ExecuteRequest, InputFile, ManagerError, Profile
from aio_sandbox_manager.docker_backend import DockerBackend
from aio_sandbox_manager.journal import Journal
from aio_sandbox_manager.service import SandboxManager


@pytest.fixture
def dependency_manager(tmp_path):
    path = os.environ.get("AIO_TEST_DEPENDENCY_PROFILE")
    if not path:
        pytest.skip("Requires the real approved dependency image; run test_dependency_runtime.py")
    profile = Profile(**json.loads(Path(path).read_text(encoding="utf-8"))["profiles"][0])
    keys = load_trust_keys(os.environ["AIO_TEST_RUNTIME_TRUST_KEYS"])
    journal = Journal((tmp_path / "manager").resolve())

    class Guard:
        def validate(self, operation, payload):
            pass

    manager = SandboxManager(
        journal,
        DockerBackend(journal.installation_id),
        {profile.id: profile},
        Guard(),
        runtime_keys=keys,
        allow_test_runtimes=True,
    )
    try:
        yield manager, profile
    finally:
        manager.close()


def spec(profile):
    return CellSpec(
        binding_id=uuid4(),
        org_id=uuid4(),
        run_id=uuid4(),
        generation=1,
        profile_id=profile.id,
        image_digest=profile.image_digest,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=90),
    )


def execute(manager, current, code):
    manager.ensure(current)
    return manager.execute(ExecuteRequest(spec=current, dispatch_id=uuid4(), code=code, timeout_seconds=20))


def test_real_signed_numpy_pandas_runtime_is_private_readonly_and_networkless(dependency_manager):
    manager, profile = dependency_manager
    a, b = spec(profile), spec(profile)
    result = execute(
        manager,
        a,
        "import numpy as np,pandas as pd,os,sys,json\nfrom pathlib import Path\nf=pd.DataFrame({'x':[2,4,6]})\nPath('private.txt').write_text('only-this-run')\nprint(json.dumps({'mean':float(np.mean(f.x)), 'uid':os.getuid(), 'numpy':np.__version__, 'pandas':pd.__version__, 'numpy_file':np.__file__, 'network':sorted(p.name for p in Path('/sys/class/net').iterdir()), 'no_site':sys.flags.no_site}))",
    )
    assert result["exit_code"] == 0 and not result.get("error_code"), result
    actual = json.loads(result["stdout"])
    assert actual["mean"] == 4 and actual["uid"] == 10001 and actual["no_site"] == 1
    assert actual["numpy_file"].startswith("/opt/aio-deps/") and actual["network"] == ["lo"]
    assert actual["numpy"] == "2.5.3" and actual["pandas"] == "3.0.5"
    other = execute(manager, b, "from pathlib import Path\nprint(Path('private.txt').exists())")
    assert other["stdout"].strip() == "False"
    denied = execute(manager, b, "from pathlib import Path\nPath('/opt/aio-deps/injected.py').write_text('x')")
    assert denied["exit_code"] != 0
    container = manager.backend.checked(a, None)
    assert "-S" in container.attrs["Config"]["Cmd"] and container.attrs["Config"]["User"] == "10000:10000"
    manager.stop(a)
    manager.stop(b)
    assert manager.backend.checked(a, None) is None and manager.backend.checked(b, None) is None


@pytest.mark.parametrize("fault", ["unknown-key", "tamper", "production", "missing-approval"])
def test_runtime_approval_failure_never_starts_user_code(dependency_manager, fault):
    manager, profile = dependency_manager
    if fault == "unknown-key":
        manager.runtime_keys.clear()
    elif fault == "production":
        manager.allow_test_runtimes = False
    elif fault == "tamper":
        profile.runtime_approval["review_note"] = "Tampered after the operator signature"
    else:
        from dataclasses import replace

        manager.profiles[profile.id] = replace(profile, runtime_approval=None)
    current = spec(profile)
    with pytest.raises(ManagerError):
        execute(manager, current, "raise AssertionError('must never execute')")
    assert manager.backend.checked(current, None) is None


def test_runtime_trust_withdrawal_still_allows_owned_cleanup(dependency_manager):
    manager, profile = dependency_manager
    current = spec(profile)
    assert execute(manager, current, "print('ready')")["exit_code"] == 0
    manager.runtime_keys.clear()
    with pytest.raises(ManagerError):
        execute(manager, current, "print('must not run after withdrawal')")
    assert manager.stop(current)["state"] == "destroyed"


@pytest.mark.parametrize("fault", [None, "traversal", "symlink", "startup-hook", "expansion", "identity"])
def test_wheel_preflight_parses_untrusted_archives_only_in_an_isolated_cell(dependency_manager, fault):
    manager, profile = dependency_manager
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("example/__init__.py", "raise AssertionError('PACKAGE_CODE_MUST_NOT_RUN_DURING_SCAN')")
        archive.writestr(
            "example-1.0.0.dist-info/METADATA",
            "Name: " + ("other" if fault == "identity" else "example") + "\nVersion: 1.0.0\n",
        )
        if fault == "traversal":
            archive.writestr("../outside.py", "x")
        elif fault == "symlink":
            item = zipfile.ZipInfo("example/link")
            item.create_system = 3
            item.external_attr = 0o120777 << 16
            archive.writestr(item, "/etc/passwd")
        elif fault == "startup-hook":
            archive.writestr("startup.pth", "import os")
        elif fault == "expansion":
            archive.writestr("example/bomb.bin", b"x" * 100000)
    wheel = buffer.getvalue()
    filename = "example-1.0.0-py3-none-any.whl"
    package = {
        "name": "example",
        "version": "1.0.0",
        "filename": filename,
        "bytes": len(wheel),
        "sha256": hashlib.sha256(wheel).hexdigest(),
    }
    manifest = json.dumps({"packages": [package]}).encode()
    inputs = [
        InputFile(path="wheels/" + filename, sha256=package["sha256"], content_b64=base64.b64encode(wheel).decode()),
        InputFile(
            path="manifest.json",
            sha256=hashlib.sha256(manifest).hexdigest(),
            content_b64=base64.b64encode(manifest).decode(),
        ),
    ]
    current = CellSpec.model_validate({**spec(profile).model_dump(), "inputs": inputs})
    source = (Path(__file__).resolve().parents[3] / "services/dependency-runtime/check_wheels.py").read_text(
        encoding="utf-8"
    )
    source = source.replace("/opt/aio-wheels", "/workspace/wheels").replace(
        "/opt/aio-builder/manifest.json", "/workspace/manifest.json"
    )
    result = execute(manager, current, source)
    if fault:
        assert result["exit_code"] != 0 and "WHEEL_" in result["stderr"]
    else:
        assert result["exit_code"] == 0 and json.loads(result["stdout"])["checked_wheels"] == 1
    assert "PACKAGE_CODE_MUST_NOT_RUN_DURING_SCAN" not in result["stdout"]
