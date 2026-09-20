from datetime import datetime, timedelta, timezone
from uuid import uuid4
import base64
import hashlib
import json
import time

import pytest
from fastapi.testclient import TestClient

from aio_sandbox_manager.contracts import CellSpec, ExecuteRequest, InputFile, ManagerError
from aio_sandbox_manager.api import create_app


def cell(profile, **changes):
    data = dict(
        binding_id=uuid4(),
        org_id=uuid4(),
        run_id=uuid4(),
        generation=1,
        profile_id=profile.id,
        image_digest=profile.image_digest,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=60),
    )
    data.update(changes)
    return CellSpec(**data)


def execute(manager, spec, code, timeout=10, dispatch_id=None):
    return manager.execute(
        ExecuteRequest(spec=spec, dispatch_id=dispatch_id or uuid4(), code=code, timeout_seconds=timeout)
    )


def test_checkpoint_export_is_private_purpose_bound_stopped_and_idempotent(managed):
    manager, guard, profile = managed
    spec = cell(profile)
    manager.ensure(spec)
    execute(manager, spec, "from pathlib import Path; Path('handoff.txt').write_text('known files only')")
    app = create_app(manager, "checkpoint-test-" + "x" * 40, manage_lifecycle=False)
    with TestClient(app) as client:
        payload = {"spec": spec.model_dump(mode="json")}
        assert client.post("/v1/cells/checkpoint", json=payload).status_code == 401
        result = client.post(
            "/v1/cells/checkpoint", json=payload, headers={"Authorization": "Bearer checkpoint-test-" + "x" * 40}
        )
        assert result.status_code == 200 and result.json()["state"] == "destroyed"
    assert manager.checkpoint(spec) == result.json()
    assert any(item[0] == "checkpoint" for item in guard.calls)
    with pytest.raises(ManagerError) as conflict:
        manager.finalize(spec)
    assert conflict.value.code == "EXPORT_PURPOSE_CONFLICT"
    manager.acknowledge(spec)
    with manager.journal.connect() as c:
        row = c.execute(
            "SELECT export_json,spec_json FROM cells WHERE binding_id=?", (str(spec.binding_id),)
        ).fetchone()
        assert row["export_json"] is None and row["spec_json"] == ""
    assert not manager.backend.client.containers.list(
        all=True, filters={"label": "aio.manager=" + manager.journal.installation_id}
    )


def test_real_nonroot_readonly_root_and_no_network_host_mounts(managed):
    manager, guard, profile = managed
    spec = cell(profile)
    ready = manager.ensure(spec)
    code = """import os,json,pathlib,socket
facts={'uid':os.getuid(),'home':os.environ.get('HOME'),'docker_socket':pathlib.Path('/var/run/docker.sock').exists()}
try:pathlib.Path('/etc/aio_should_not_write').write_text('x');facts['root_writable']=True
except OSError:facts['root_writable']=False
facts['nnp']=[line for line in pathlib.Path('/proc/self/status').read_text().splitlines() if line.startswith(('NoNewPrivs:','CapEff:'))]
facts['interfaces']=sorted(p.name for p in pathlib.Path('/sys/class/net').iterdir())
print(json.dumps(facts))
"""
    facts = json.loads(execute(manager, spec, code)["stdout"])
    assert facts["uid"] == 10001 and not facts["root_writable"] and not facts["docker_socket"]
    assert facts["interfaces"] == ["lo"] and any("NoNewPrivs:\t1" == v for v in facts["nnp"])
    container = manager.backend.checked(spec, ready["container_id"])
    assert all(m["Type"] != "bind" for m in container.attrs["Mounts"])
    assert container.attrs["HostConfig"]["PidsLimit"] == profile.pids
    assert container.attrs["HostConfig"]["Memory"] == profile.memory_bytes
    assert container.attrs["HostConfig"]["NanoCpus"] == profile.nano_cpus


def test_two_cells_do_not_share_home_workspace_or_secrets(managed):
    manager, guard, profile = managed
    a, b = cell(profile), cell(profile)
    manager.ensure(a)
    manager.ensure(b)
    execute(
        manager,
        a,
        "from pathlib import Path; Path('private.txt').write_text('alice'); Path('/home/runner/private').write_text('alice')",
    )
    out = execute(
        manager,
        b,
        "from pathlib import Path; import os; print(Path('private.txt').exists(),Path('/home/runner/private').exists(),os.environ.get('PLATFORM_DATABASE_URL'))",
    )
    assert out["stdout"].strip() == "False False None"
    assert (
        execute(manager, a, "from pathlib import Path; print(Path('private.txt').read_text())")["stdout"].strip()
        == "alice"
    )


def test_initial_inputs_and_real_files_are_collected_by_external_daemon(managed):
    manager, guard, profile = managed
    data = "输入中文".encode()
    spec = cell(
        profile,
        inputs=(
            InputFile(
                path="input.txt", sha256=hashlib.sha256(data).hexdigest(), content_b64=base64.b64encode(data).decode()
            ),
        ),
    )
    manager.ensure(spec)
    out = execute(
        manager,
        spec,
        "from pathlib import Path; Path('result.txt').write_text(Path('input.txt').read_text()+' result',encoding='utf8')",
    )
    assert out["exit_code"] == 0
    result = manager.finalize(spec)
    assert result["state"] == "destroyed"
    files = {f["path"]: base64.b64decode(f["content_b64"]) for f in result["files"]}
    assert files["input.txt"] == data and files["result.txt"] == data + b" result"
    assert manager.backend.checked(spec, None) is None
    assert manager.finalize(spec) == result


def test_duplicate_dispatch_never_executes_code_twice(managed):
    manager, guard, profile = managed
    spec = cell(profile)
    manager.ensure(spec)
    id = uuid4()
    code = "from pathlib import Path; p=Path('count'); p.write_text(str(int(p.read_text())+1 if p.exists() else 1));print(p.read_text())"
    first = execute(manager, spec, code, dispatch_id=id)
    second = execute(manager, spec, code, dispatch_id=id)
    assert first == second and first["stdout"].strip() == "1"
    with pytest.raises(ManagerError):
        execute(manager, spec, "print('changed')", dispatch_id=id)


def test_workspace_has_actual_byte_and_inode_limits(managed):
    manager, guard, profile = managed
    spec = cell(profile)
    manager.ensure(spec)
    code = """import os,json
s=os.statvfs('/workspace')
print(json.dumps({'bytes':s.f_blocks*s.f_frsize,'inodes':s.f_files}))
try:
 with open('too-big','wb') as f:f.write(b'x'*(4*1024*1024))
 print('UNBOUNDED')
except OSError as e:print('QUOTA',e.errno)
"""
    out = execute(manager, spec, code)
    lines = out["stdout"].splitlines()
    stats = json.loads(lines[0])
    assert stats["bytes"] == profile.workspace_bytes and stats["inodes"] == profile.workspace_inodes
    assert "QUOTA 28" in out["stdout"] and "UNBOUNDED" not in out["stdout"]


def test_inode_exhaustion_is_local_and_bounded(managed):
    manager, guard, profile = managed
    spec = cell(profile)
    manager.ensure(spec)
    out = execute(
        manager,
        spec,
        """from pathlib import Path
try:
 for i in range(200):Path(str(i)).touch()
 print('UNBOUNDED')
except OSError as e:print('INODE_LIMIT',e.errno)""",
    )
    assert "INODE_LIMIT 28" in out["stdout"]


def test_timeout_kills_cell_and_its_background_processes(managed):
    manager, guard, profile = managed
    spec = cell(profile)
    manager.ensure(spec)
    started = time.monotonic()
    out = execute(
        manager,
        spec,
        "import subprocess,time; subprocess.Popen(['python','-c','import time;time.sleep(120)']);time.sleep(120)",
        timeout=1,
    )
    assert out["error_code"] == "EXECUTION_TIMEOUT" and time.monotonic() - started < 12
    assert manager.backend.checked(spec, None) is None
    assert manager.journal.cell(spec.binding_id)["state"] == "destroyed"


def test_output_flood_is_bounded_and_cell_reclaimed(managed):
    manager, guard, profile = managed
    spec = cell(profile)
    manager.ensure(spec)
    out = execute(
        manager,
        spec,
        """import sys
while True:sys.stdout.write('x'*4096);sys.stdout.flush()""",
    )
    assert out["error_code"] == "OUTPUT_LIMIT_EXCEEDED" and out["truncated"]
    assert len(out["stdout"].encode()) <= profile.output_bytes
    assert manager.backend.checked(spec, None) is None


def test_symlink_artifacts_are_rejected_not_followed(managed):
    manager, guard, profile = managed
    spec = cell(profile)
    manager.ensure(spec)
    execute(manager, spec, "import os;os.symlink('/etc/passwd','stolen.txt')")
    with pytest.raises(ManagerError) as exc:
        manager.finalize(spec)
    assert exc.value.code == "UNSAFE_ARTIFACT"
    assert manager.backend.checked(spec, None) is None


def test_current_authority_revocation_stops_new_work_and_reaper_cleans(managed):
    manager, guard, profile = managed
    spec = cell(profile)
    manager.ensure(spec)
    guard.denied.add("execute")
    with pytest.raises(RuntimeError):
        execute(manager, spec, "print('must not run')")
    guard.denied.add("alive")
    manager.reap()
    assert manager.backend.checked(spec, None) is None
    assert manager.journal.cell(spec.binding_id)["state"] == "destroyed"


def test_manager_capacity_is_not_one_cell_per_registered_user(managed):
    manager, guard, profile = managed
    a, b, c = cell(profile), cell(profile), cell(profile)
    manager.ensure(a)
    manager.ensure(b)
    with pytest.raises(ManagerError) as exc:
        manager.ensure(c)
    assert exc.value.code == "CELL_CAPACITY_EXCEEDED"
    manager.stop(a)
    assert manager.ensure(c)["state"] == "ready"


def test_manager_api_rejects_unauthorized_and_docker_flags_before_execution(managed):
    manager, guard, profile = managed
    token = "test-service-token-" + ("z" * 40)
    app = create_app(manager, token, manage_lifecycle=False)
    spec = cell(profile)
    with TestClient(app) as client:
        assert client.post("/v1/cells/ensure", json={"spec": spec.model_dump(mode="json")}).status_code == 401
        headers = {"Authorization": "Bearer " + token}
        assert (
            client.post(
                "/v1/cells/ensure", json={"spec": {**spec.model_dump(mode="json"), "privileged": True}}, headers=headers
            ).status_code
            == 422
        )
        assert (
            client.post("/v1/cells/ensure", json={"spec": spec.model_dump(mode="json")}, headers=headers).status_code
            == 200
        )
        assert client.get("/docs", headers=headers).status_code == 404


def test_real_pid_limit_blocks_bounded_process_fanout(managed):
    manager, guard, profile = managed
    spec = cell(profile)
    manager.ensure(spec)
    code = """import subprocess
children=[]
try:
 for i in range(90):children.append(subprocess.Popen(['python','-c','import time;time.sleep(30)']))
 print('UNBOUNDED_PIDS')
except OSError as e:print('PID_LIMIT',len(children),e.errno)
finally:
 for p in children:p.kill()
 for p in children:p.wait()
"""
    result = execute(manager, spec, code)
    assert "PID_LIMIT" in result["stdout"] and "UNBOUNDED_PIDS" not in result["stdout"]
    assert manager.stop(spec)["state"] == "destroyed"


def test_single_manager_owns_its_journal_directory(managed):
    from aio_sandbox_manager.journal import Journal

    manager, guard, profile = managed
    with pytest.raises(RuntimeError):
        Journal(manager.journal.root)


def test_lost_cell_is_not_silently_recreated_with_empty_state(managed):
    manager, guard, profile = managed
    spec = cell(profile)
    ready = manager.ensure(spec)
    execute(manager, spec, "from pathlib import Path;Path('state.txt').write_text('must not vanish silently')")
    manager.backend.destroy(spec, ready["container_id"])
    with pytest.raises(ManagerError) as exc:
        manager.ensure(spec)
    assert exc.value.code == "CELL_LOST"


def test_concurrent_ensure_does_not_destroy_another_request_allocation(managed, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    manager, guard, profile = managed
    spec = cell(profile)
    entered = Event()
    release = Event()
    original = manager.backend.create

    def delayed(*args):
        entered.set()
        assert release.wait(timeout=5)
        return original(*args)

    monkeypatch.setattr(manager.backend, "create", delayed)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(manager.ensure, spec)
        assert entered.wait(timeout=3)
        with pytest.raises(ManagerError) as exc:
            manager.ensure(spec)
        assert exc.value.code == "CELL_BUSY"
        release.set()
        ready = first.result(timeout=10)
    assert manager.backend.checked(spec, ready["container_id"]) is not None


def test_untrusted_code_cannot_stop_watchdog_and_idle_cell_expires_without_reaper(managed):
    manager, guard, profile = managed
    spec = cell(profile, deadline=datetime.now(timezone.utc) + timedelta(seconds=4))
    ready = manager.ensure(spec)
    result = execute(
        manager,
        spec,
        "import os,signal\ntry:os.kill(1,signal.SIGSTOP);print('ALLOWED')\nexcept PermissionError:print('WATCHDOG_PROTECTED')",
        timeout=2,
    )
    assert result["stdout"].strip() == "WATCHDOG_PROTECTED"
    # No manager reaper is running. The separate non-root PID1 timer must stop the cell by itself.
    deadline = time.monotonic() + 7
    while True:
        container = manager.backend.checked(spec, ready["container_id"])
        if not container.attrs["State"]["Running"]:
            break
        assert time.monotonic() < deadline, "Cell exceeded its hard lifetime without a live manager reaper"
        time.sleep(0.1)
    assert manager.stop(spec)["state"] == "destroyed"


def test_sparse_file_cannot_exceed_collector_memory_budget(managed):
    manager, guard, profile = managed
    spec = cell(profile)
    manager.ensure(spec)
    execute(manager, spec, "with open('sparse','wb') as f:f.truncate(64*1024*1024)")
    with pytest.raises(ManagerError) as exc:
        manager.finalize(spec)
    assert exc.value.code in {"EXPORT_QUOTA_EXCEEDED", "ARTIFACT_QUOTA_EXCEEDED"}
    assert manager.backend.checked(spec, None) is None


def test_retained_manager_payload_budget_blocks_new_allocations(managed, monkeypatch):
    manager, guard, profile = managed
    spec = cell(profile)
    monkeypatch.setattr(manager, "_retained_bytes", lambda c: 128 * 1024 * 1024)
    with pytest.raises(ManagerError) as exc:
        manager.ensure(spec)
    assert exc.value.code == "MANAGER_STORAGE_QUOTA"
    assert manager.backend.checked(spec, None) is None
    assert manager.journal.cells() == []
