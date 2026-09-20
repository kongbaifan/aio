"""Current tenant/author authority, real isolated archive import and immutable draft creation."""

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
from uuid import uuid4
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select, update

from app.api.v2.application import create_platform_app
from app.auth.service import AuthService, csrf_token
from app.db import schema as s
from app.execution.sandbox_client import ManagerClient
from app.platform_errors import PlatformError
from app.skills.contracts import SkillReview, SkillValidate
from app.skills.worker import SkillValidationWorker
from app.workspaces.service import ArtifactService
from archive_fixtures import archive_platform as archive_platform, archive, request, execute_import


@pytest.mark.parametrize("native", [False, True])
def test_archive_import_creates_only_a_private_draft_after_confirmed_cleanup(archive_platform, native):
    t = archive_platform
    raw, metadata = archive(native=native)
    body = request(t, raw, metadata)
    created = t["archives"].prepare(t["alice"], body)
    id = created["id"]
    assert t["archives"].prepare(t["alice"], body)["id"] == id
    assert t["archives"].list(t["bob"]) == []
    with pytest.raises(PlatformError):
        t["archives"].detail(t["bob"], id)
    with pytest.raises(PlatformError):
        t["archives"].upload(t["bob"], id, raw)
    with pytest.raises(PlatformError) as invalid:
        t["archives"].upload(t["alice"], id, raw + b"changed")
    assert invalid.value.code == "ARCHIVE_UPLOAD_MISMATCH"
    uploaded = t["archives"].upload(t["alice"], id, raw)
    assert uploaded["state"] == "queued" and not uploaded["automatically_published"]
    assert t["archives"].upload(t["alice"], id, raw)["state"] == "queued"
    result = execute_import(t)
    assert result["state"] == "imported", result
    assert result["cleanup_state"] == "confirmed" and result["manager_acknowledged"]
    with t["db"].transaction(t["alice"]) as c:
        row = c.execute(select(s.skill_imports).where(s.skill_imports.c.id == id)).mappings().one()
        assert row["spec"] is None and row["command"] is None and row["candidate"] is None
        skill = c.execute(select(s.skill_versions).where(s.skill_versions.c.id == result["skill_id"])).mappings().one()
        assert skill["state"] == "draft" and skill["published_tools"] == []
        assert bool(skill["package"]["entrypoints"]) is not native
        grants = c.execute(select(s.grants).where(s.grants.c.resource_id == result["skill_id"])).all()
        assert grants == []
    assert t["archives"].download(t["alice"], id)[1] == raw
    with pytest.raises(PlatformError):
        t["archives"].download(t["bob"], id)
    assert t["archives"].skills.list_authorized(t["bob"]) == []
    assert not t["manager"].backend.client.containers.list(
        all=True, filters={"label": "aio.manager=" + t["manager"].journal.installation_id}
    )


def test_imported_entrypoint_uses_existing_distinct_person_validation_and_release(archive_platform):
    t = archive_platform
    raw, metadata = archive()
    item = t["archives"].prepare(t["alice"], request(t, raw, metadata))
    t["archives"].upload(t["alice"], item["id"], raw)
    imported = execute_import(t)
    assert imported["state"] == "imported", imported
    skills = t["archives"].skills
    detail = skills.detail(t["alice"], imported["skill_id"])
    job = skills.submit(
        t["alice"],
        imported["skill_id"],
        SkillValidate(expected_revision=detail["revision"], reviewer_id=t["bob"].user_id),
    )

    async def validate():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=t["manager_app"]), base_url="http://manager.test"
        ) as http:
            client = ManagerClient("http://127.0.0.1:9999", t["manager_token"], client=http)
            return await SkillValidationWorker(t["validation"], client, t["org"], "archive-validator").run_once()

    result = asyncio.run(validate())
    assert result["state"] == "passed", (job, result)
    current = skills.detail(t["bob"], imported["skill_id"])
    with pytest.raises(PlatformError):
        skills.review(
            t["alice"],
            imported["skill_id"],
            SkillReview(expected_revision=current["revision"], decision="approve", note="self review denied"),
        )
    published = skills.review(
        t["bob"],
        imported["skill_id"],
        SkillReview(
            expected_revision=current["revision"],
            decision="approve",
            note="Synthetic source, license and behavior reviewed",
        ),
    )
    assert published["state"] == "published"


def test_archive_request_identity_and_owner_cannot_be_changed_or_shared_by_extra_grants(archive_platform):
    t = archive_platform
    raw, _ = archive()
    body = request(t, raw)
    item = t["archives"].prepare(t["alice"], body)
    changed = body.model_copy(update={"sandbox_profile": "other"})
    with pytest.raises(PlatformError):
        t["archives"].prepare(t["alice"], changed)
    with t["admin"].begin() as c:
        c.execute(
            insert(s.grants).values(
                org_id=t["org"],
                id=uuid4(),
                resource_id=item["id"],
                subject_id=t["bob"].user_id,
                action="skill_import.read",
            )
        )
    with pytest.raises(PlatformError):
        t["archives"].download(t["bob"], item["id"])
    with pytest.raises(PlatformError):
        t["archives"].detail(t["bob"], item["id"])


def test_archive_storage_hold_is_shared_with_other_uploads_and_release_is_verified(archive_platform):
    t = archive_platform
    raw, _ = archive()
    with t["admin"].begin() as c:
        c.execute(
            update(s.organizations).where(s.organizations.c.id == t["org"]).values(storage_limit_bytes=len(raw) + 10)
        )
    item = t["archives"].prepare(t["alice"], request(t, raw))
    files = ArtifactService(t["db"], t["archives"].blobs)
    with pytest.raises(PlatformError) as quota:
        files.create_upload(t["alice"], t["project"], "other.txt", 11)
    assert quota.value.code == "STORAGE_QUOTA_EXCEEDED"
    current = t["archives"].delete(t["alice"], item["id"], item["revision"])
    assert current["state"] == "cancelled"
    assert t["archives"].gc(t["org"]) == [item["id"]]
    assert files.create_upload(t["alice"], t["project"], "other.txt", 11)["upload_id"]
    with pytest.raises(PlatformError):
        t["archives"].upload(t["alice"], item["id"], raw)


def test_archive_gc_keeps_another_authors_shared_content_hash(archive_platform):
    t = archive_platform
    raw, _ = archive()
    a = t["archives"].prepare(t["alice"], request(t, raw))
    b = t["archives"].prepare(t["bob"], request(t, raw))
    a = t["archives"].upload(t["alice"], a["id"], raw)
    b = t["archives"].upload(t["bob"], b["id"], raw)
    t["archives"].delete(t["alice"], a["id"], a["revision"])
    assert t["archives"].gc(t["org"]) == [a["id"]]
    assert t["archives"].download(t["bob"], b["id"])[1] == raw
    t["archives"].delete(t["bob"], b["id"], b["revision"])
    assert t["archives"].gc(t["org"]) == [b["id"]]
    with pytest.raises(PlatformError):
        t["archives"].blobs.get(t["org"], b["archive_sha256"], len(raw))


def test_partial_archive_write_keeps_a_durable_hold_and_cannot_resurrect_after_purge(archive_platform, monkeypatch):
    t = archive_platform
    raw, _ = archive()
    item = t["archives"].prepare(t["alice"], request(t, raw))
    original = t["archives"].blobs.put

    def lost_receipt(org, data):
        original(org, data)
        raise PlatformError("SYNTHETIC_WRITE_INTERRUPTED", "Synthetic storage acknowledgement loss", 503)

    with monkeypatch.context() as patch:
        patch.setattr(t["archives"].blobs, "put", lost_receipt)
        with pytest.raises(PlatformError):
            t["archives"].upload(t["alice"], item["id"], raw)
    with t["db"].transaction(t["alice"]) as c:
        row = c.execute(select(s.skill_imports).where(s.skill_imports.c.id == item["id"])).mappings().one()
        assert row["state"] == "uploading" and row["upload_bound"] and row["reserved_bytes"] == len(raw)
    t["archives"].delete(t["alice"], item["id"], row["revision"])
    assert t["archives"].gc(t["org"]) == [item["id"]]
    with pytest.raises(PlatformError):
        t["archives"].upload(t["alice"], item["id"], raw)
    with pytest.raises(PlatformError):
        t["archives"].blobs.get(t["org"], item["archive_sha256"], len(raw))


@pytest.mark.parametrize("revoke", [False, True])
def test_archive_recovery_only_stops_old_cell_and_fences_old_worker(archive_platform, revoke):
    t = archive_platform
    raw, _ = archive()
    item = t["archives"].prepare(t["alice"], request(t, raw))
    t["archives"].upload(t["alice"], item["id"], raw)
    original = t["import_jobs"].prepare(t["import_jobs"].claim(t["org"], "lost-import-worker"))
    from aio_sandbox_manager.contracts import CellSpec

    spec = CellSpec.model_validate(original["spec"])
    t["manager"].ensure(spec)
    with t["admin"].begin() as c:
        c.execute(
            update(s.skill_imports)
            .where(s.skill_imports.c.id == item["id"])
            .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
        if revoke:
            c.execute(update(s.organizations).where(s.organizations.c.id == t["org"]).values(active=False))
    recovered = t["import_jobs"].recover(t["org"], "cleanup-import-worker")
    assert recovered["generation"] > original["generation"] and recovered["spec"] == original["spec"]
    assert t["import_jobs"].recover(t["org"], "cannot-steal-cleanup") is None
    with pytest.raises(PlatformError):
        t["import_jobs"].stopping(original, None)
    response = t["manager"].stop(spec)
    t["import_jobs"].stopped(recovered, response)
    t["import_jobs"].acknowledged(recovered, t["manager"].acknowledge(spec))
    finished = t["import_jobs"].finish(recovered)
    assert finished["state"] == "rejected" and finished["error_code"] == "SKILL_IMPORT_INTERRUPTED"
    assert "execute" not in t["guard"].operations
    assert not t["manager"].backend.client.containers.list(
        all=True, filters={"label": "aio.manager=" + t["manager"].journal.installation_id}
    )


def test_archive_authority_rejects_changed_code_or_binding_and_cancelled_execution(archive_platform):
    t = archive_platform
    raw, _ = archive()
    item = t["archives"].prepare(t["alice"], request(t, raw))
    t["archives"].upload(t["alice"], item["id"], raw)
    handle = t["import_jobs"].prepare(t["import_jobs"].claim(t["org"], "scanner"))
    payload = {"spec": handle["spec"], "language": "python", **handle["command"]}
    t["import_jobs"].authorize("execute", payload)
    with pytest.raises(PlatformError):
        t["import_jobs"].authorize("execute", {**payload, "code": "print('not-authorized')"})
    with pytest.raises(PlatformError):
        t["import_jobs"].authorize("ensure", {"spec": {**handle["spec"], "generation": 123}})
    current = t["archives"].detail(t["alice"], item["id"])
    t["archives"].delete(t["alice"], item["id"], current["revision"])
    with pytest.raises(PlatformError):
        t["import_jobs"].authorize("execute", payload)
    t["import_jobs"].authorize("stop", {"spec": handle["spec"]})


def test_duplicate_archive_version_never_overwrites_the_existing_skill(archive_platform):
    t = archive_platform
    raw, _ = archive()
    first = t["archives"].prepare(t["alice"], request(t, raw))
    t["archives"].upload(t["alice"], first["id"], raw)
    imported = execute_import(t)
    second = t["archives"].prepare(t["alice"], request(t, raw))
    t["archives"].upload(t["alice"], second["id"], raw)
    rejected = execute_import(t)
    assert rejected["state"] == "rejected" and rejected["error_code"] == "SKILL_VERSION_EXISTS"
    with t["db"].transaction(t["alice"]) as c:
        skills = c.execute(select(s.skill_versions.c.id).where(s.skill_versions.c.org_id == t["org"])).scalars().all()
        assert skills == [imported["skill_id"]]


def test_current_execution_environment_withdrawal_prevents_import_finalization(archive_platform, monkeypatch):
    t = archive_platform
    raw, _ = archive()
    item = t["archives"].prepare(t["alice"], request(t, raw))
    t["archives"].upload(t["alice"], item["id"], raw)
    original = t["import_jobs"].finish

    def withdrawn(handle):
        t["archives"].settings = replace(t["settings"], sandbox_profiles=())
        t["archives"].skills.settings = t["archives"].settings
        return original(handle)

    monkeypatch.setattr(t["import_jobs"], "finish", withdrawn)
    result = execute_import(t)
    assert result["state"] == "rejected" and result["skill_id"] is None
    assert result["cleanup_state"] == "confirmed" and result["manager_acknowledged"]


def test_archive_v2_metadata_and_exact_dependency_environment_survive_import(archive_platform):
    t = archive_platform
    if not os.environ.get("AIO_TEST_DEPENDENCY_PROFILE"):
        pytest.skip("Signed dependency image is required for the v2 archive contract")
    source = Path(__file__).resolve().parents[4] / "config/skill-packages/example-analytics.json"
    package = json.loads(source.read_text(encoding="utf-8"))
    files = package.pop("files")
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("skill.json", json.dumps(package))
        for file in files:
            z.writestr(file["path"], file["content"])
    raw = target.getvalue()
    profile = next(p for p in t["settings"].sandbox_profiles if p.get("runtime"))
    body = request(t, raw).model_copy(update={"sandbox_profile": profile["id"]})
    created = t["archives"].prepare(t["alice"], body)
    t["archives"].upload(t["alice"], created["id"], raw)
    result = execute_import(t)
    assert result["state"] == "imported", result
    detail = t["archives"].skills.detail(t["alice"], result["skill_id"])
    assert (
        detail["package"]["schema_version"] == 2
        and detail["runtime_manifest_digest"] == package["runtime_manifest_digest"]
    )
    assert detail["dependencies"] == sorted(package["dependencies"], key=lambda p: p["name"])


def test_archive_http_enforces_csrf_binary_limits_and_owner_only_access(archive_platform):
    t = archive_platform
    auth = AuthService(t["db"], t["settings"])
    token, _ = auth.create_session(t["org"], t["settings"].oidc_issuer, str(t["alice"].user_id))
    app = create_platform_app(t["settings"], database=t["db"])
    raw, native = archive(native=True)
    body = request(t, raw, native).model_dump(mode="json")
    with TestClient(app, base_url=t["settings"].public_origin) as client:
        assert client.get("/api/v2/admin/skill-imports").status_code == 401
        client.cookies.set(t["settings"].session_cookie, token)
        assert client.post("/api/v2/admin/skill-imports", json=body).status_code == 403
        headers = {"Origin": t["settings"].public_origin, "X-CSRF-Token": csrf_token(token)}
        assert (
            client.post(
                "/api/v2/admin/skill-imports", json={**body, "install": "no-host-install"}, headers=headers
            ).status_code
            == 422
        )
        created = client.post("/api/v2/admin/skill-imports", json=body, headers=headers)
        assert created.status_code == 201
        id = created.json()["id"]
        path = f"/api/v2/admin/skill-imports/{id}/content"
        assert client.put(path, content=raw, headers={"Content-Type": "application/octet-stream"}).status_code == 403
        assert (
            client.put(
                path,
                content=b"x",
                headers={**headers, "Content-Type": "application/octet-stream", "Content-Length": "2097153"},
            ).status_code
            == 413
        )
        assert (
            client.put(path, content=raw, headers={**headers, "Content-Type": "application/octet-stream"}).status_code
            == 200
        )
        download = client.get(f"/api/v2/admin/skill-imports/{id}/download")
        assert download.content == raw and download.headers["content-disposition"].startswith("attachment;")
        metadata = client.get(f"/api/v2/admin/skill-imports/{id}").json()
        assert not {"request", "spec", "command", "candidate"}.intersection(metadata)
