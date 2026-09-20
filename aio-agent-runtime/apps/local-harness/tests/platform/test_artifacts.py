from dataclasses import replace
from uuid import uuid4
import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select, update

from app.api.v2.application import create_platform_app
from app.auth.service import AuthService, csrf_token
from app.db import schema as s
from app.platform_errors import PlatformError
from app.workspaces.service import ArtifactService
from app.workspaces.storage import BlobStore, safe_path


@pytest.mark.parametrize("value", ["../private", "/etc/passwd", "C:/Users/private", "a//b", "a/./b", "a\\b"])
def test_artifact_paths_are_not_host_paths(value):
    with pytest.raises(PlatformError):
        safe_path(value)


def test_immutable_scoped_blob_hash_verification(tmp_path):
    blobs = BlobStore(tmp_path.resolve())
    a, b = uuid4(), uuid4()
    data = b"private payload"
    sha = blobs.put(a, data)
    assert sha == hashlib.sha256(data).hexdigest() and blobs.put(a, data) == sha
    assert blobs.get(a, sha, len(data)) == data
    with pytest.raises(PlatformError):
        blobs.get(b, sha, len(data))
    with pytest.raises(PlatformError):
        blobs.get(a, "../secret", len(data))
    path = blobs._path(a, sha)
    path.write_bytes(b"wrong payload!!")
    with pytest.raises(PlatformError):
        blobs.get(a, sha, len(data))


def test_blob_root_must_be_explicit_absolute():
    with pytest.raises(ValueError):
        BlobStore(__import__("pathlib").Path("relative-root"))


@pytest.fixture
def artifacts(tenant, tmp_path):
    return tenant, ArtifactService(tenant["db"], BlobStore(tmp_path.resolve() / "objects"))


def test_upload_is_private_immutable_and_does_not_share_session(artifacts):
    t, store = artifacts
    slot = store.create_upload(t["alice"], t["project"], "report.csv", 1024)
    first = store.upload(t["alice"], slot["upload_id"], b"a,b\n1,2\n")
    assert store.upload(t["alice"], slot["upload_id"], b"a,b\n1,2\n") == first
    with pytest.raises(PlatformError):
        store.upload(t["alice"], slot["upload_id"], b"changed")
    with pytest.raises(PlatformError):
        store.upload(t["bob"], slot["upload_id"], b"changed")
    with pytest.raises(PlatformError):
        store.download(t["bob"], first["id"])
    with pytest.raises(PlatformError):
        store.download(t["outsider"], first["id"])
    assert store.download(t["alice"], first["id"])[1] == b"a,b\n1,2\n"
    assert first["scan_state"] == "opaque_attachment"  # Do not claim malware or parser safety scanning.


def test_input_artifacts_are_validated_in_atomic_run_creation(artifacts):
    t, store = artifacts
    slot = store.create_upload(t["alice"], t["project"], "input.csv", 100)
    file = store.upload(t["alice"], slot["upload_id"], b"value\n3\n")
    body = {
        "message": "analyze",
        "agent_version_id": str(t["agent"]),
        "expected_session_revision": 0,
        "input_artifact_ids": [str(file["id"])],
        "mode": "single",
    }
    run = t["service"].create_run(t["alice"], t["session"], body, "input-test-" + uuid4().hex)
    assert run["state"] == "queued"
    with t["db"].transaction(t["alice"]) as c:
        assert c.execute(select(s.runs.c.input).where(s.runs.c.id == run["run_id"])).scalar_one()[
            "input_artifact_ids"
        ] == [str(file["id"])]


def test_revoked_source_blocks_derived_artifact_reads(artifacts):
    t, store = artifacts
    slot = store.create_upload(t["alice"], t["project"], "source.txt", 100)
    source = store.upload(t["alice"], slot["upload_id"], b"private source")
    derived = uuid4()
    sha = store.blobs.put(t["org"], b"derived summary")
    with t["admin"].begin() as c:
        c.execute(
            insert(s.resources).values(
                org_id=t["org"], id=derived, owner_id=t["alice"].user_id, kind="artifact", classification="internal"
            )
        )
        c.execute(
            insert(s.artifacts).values(
                org_id=t["org"],
                id=derived,
                project_id=t["project"],
                path="summary.txt",
                sha256=sha,
                bytes=15,
                media_type="text/plain",
                state="ready",
                kind="generated",
                source_refs=[str(source["id"])],
                scan_state="structural_attachment",
            )
        )
    assert store.download(t["alice"], derived)[1] == b"derived summary"
    with t["admin"].begin() as c:
        c.execute(update(s.resources).where(s.resources.c.id == source["id"]).values(status="disabled"))
    with pytest.raises(PlatformError):
        store.download(t["alice"], derived)
    assert not store.list_project(t["alice"], t["project"])


def test_upload_and_download_http_are_csrf_scoped_and_attachment_only(artifacts):
    t, store = artifacts
    settings = replace(t["settings"], artifact_root=store.blobs.root)
    auth = AuthService(t["db"], settings)
    token, _ = auth.create_session(t["org"], settings.oidc_issuer, str(t["alice"].user_id))
    app = create_platform_app(settings, database=t["db"])
    with TestClient(app, base_url=settings.public_origin) as client:
        client.cookies.set(settings.session_cookie, token)
        headers = {"Origin": settings.public_origin, "X-CSRF-Token": csrf_token(token)}
        slot = client.post(
            f"/api/v2/projects/{t['project']}/uploads", json={"path": "attack.html", "max_bytes": 100}, headers=headers
        ).json()
        content = b"<script>not-inline-executed</script>"
        assert (
            client.put(
                slot["content_url"], content=content, headers={"Content-Type": "application/octet-stream"}
            ).status_code
            == 403
        )
        up = client.put(
            slot["content_url"], content=content, headers={**headers, "Content-Type": "application/octet-stream"}
        )
        assert up.status_code == 200
        id = up.json()["id"]
        response = client.get(f"/api/v2/artifacts/{id}/download")
        assert response.status_code == 200 and response.content == content
        assert response.headers["content-type"] == "application/octet-stream"
        assert response.headers["content-disposition"].startswith("attachment;")
        assert client.get(f"/api/v2/projects/{t['project']}/files").json()["items"][0]["id"] == id
        assert (
            client.post("/internal/v1/sandbox/authorize", json={"operation": "ensure", "spec": {}}).status_code == 401
        )


def test_storage_rejects_symlink_ancestor_before_creating_outside_directory(tmp_path):
    import os

    root = (tmp_path / "safe").resolve()
    outside = (tmp_path / "outside").resolve()
    root.mkdir()
    outside.mkdir()
    store = BlobStore(root)
    try:
        os.symlink(outside, root / "objects", target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation is unavailable in this test environment")
    with pytest.raises(PlatformError):
        store.put(uuid4(), b"content")
    assert list(outside.iterdir()) == []


def test_metadata_grant_does_not_implicitly_grant_download(artifacts):
    t, store = artifacts
    slot = store.create_upload(t["alice"], t["project"], "read-scope.txt", 100)
    file = store.upload(t["alice"], slot["upload_id"], b"private bytes")
    with t["admin"].begin() as c:
        for resource, action in [(t["project"], "project.read"), (file["id"], "artifact.read")]:
            c.execute(
                insert(s.grants).values(
                    id=uuid4(), org_id=t["org"], resource_id=resource, subject_id=t["bob"].user_id, action=action
                )
            )
    assert store.info(t["bob"], file["id"])["id"] == file["id"]
    with pytest.raises(PlatformError):
        store.download(t["bob"], file["id"])


def test_conflicting_upload_retry_does_not_write_untracked_blobs(artifacts):
    t, store = artifacts
    slot = store.create_upload(t["alice"], t["project"], "fixed.txt", 100)
    store.upload(t["alice"], slot["upload_id"], b"first")
    before = set(p.relative_to(store.blobs.root) for p in store.blobs.root.rglob("*") if p.is_file())
    with pytest.raises(PlatformError):
        store.upload(t["alice"], slot["upload_id"], b"different-content")
    after = set(p.relative_to(store.blobs.root) for p in store.blobs.root.rglob("*") if p.is_file())
    assert before == after


def test_concurrent_upload_reservations_cannot_overfill_project_storage(artifacts):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    t, store = artifacts
    with t["admin"].begin() as c:
        c.execute(update(s.projects).where(s.projects.c.id == t["project"]).values(storage_limit_bytes=100))
    barrier = Barrier(2)

    def reserve(name):
        barrier.wait(timeout=5)
        try:
            return store.create_upload(t["alice"], t["project"], name, 70)
        except PlatformError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        calls = [pool.submit(reserve, "a.txt"), pool.submit(reserve, "b.txt")]
        result = [call.result(timeout=10) for call in calls]
    assert sum(isinstance(row, dict) for row in result) == 1
    assert "STORAGE_QUOTA_EXCEEDED" in result


def test_failed_upload_keeps_hash_and_reserved_capacity_without_accepting_different_content(artifacts, monkeypatch):
    t, store = artifacts
    slot = store.create_upload(t["alice"], t["project"], "retry.txt", 100)
    original = store.blobs.put

    def fail(*args):
        raise PlatformError("STORAGE_CAPACITY_LOW", "synthetic storage outage", 503)

    monkeypatch.setattr(store.blobs, "put", fail)
    with pytest.raises(PlatformError):
        store.upload(t["alice"], slot["upload_id"], b"original")
    with t["db"].transaction(t["alice"]) as c:
        row = c.execute(select(s.upload_slots).where(s.upload_slots.c.id == slot["upload_id"])).mappings().one()
        assert row["state"] == "uploading" and row["content_sha256"] == hashlib.sha256(b"original").hexdigest()
    with pytest.raises(PlatformError) as exc:
        store.upload(t["alice"], slot["upload_id"], b"different")
    assert exc.value.code == "UPLOAD_CONFLICT"
    monkeypatch.setattr(store.blobs, "put", original)
    result = store.upload(t["alice"], slot["upload_id"], b"original")
    assert store.download(t["alice"], result["id"])[1] == b"original"
