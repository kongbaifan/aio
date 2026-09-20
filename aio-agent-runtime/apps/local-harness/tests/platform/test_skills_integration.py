"""Real PostgreSQL publication/ACL/lease tests with explicitly synthetic execution receipts."""

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update, text
from sqlalchemy.exc import DBAPIError

from app.admin.contracts import AgentCreate, GrantCreate
from app.api.v2.application import create_platform_app
from app.auth.service import AuthService, csrf_token
from app.db import schema as s
from app.db.provisioning import provision_model
from app.platform_errors import PlatformError
from app.runtime.catalog import current_tool
from app.skills.contracts import SkillCreate, SkillValidate, SkillReview
from app.skills.service import SkillService
from app.skills.worker import SkillValidationWorker
from skill_fixtures import sample_package, SyntheticValidationManager, publish_sample


def create(t):
    return t["skills"].create(t["alice"], SkillCreate(package=sample_package(), sandbox_profile="test"))


def submit(t, row):
    return t["skills"].submit(
        t["alice"], row["id"], SkillValidate(expected_revision=row["revision"], reviewer_id=t["bob"].user_id)
    )


def test_drafts_private_even_from_unassigned_org_admin_and_other_org(skill_registry):
    t = skill_registry
    row = create(t)
    for p in (t["bob"], t["outsider"]):
        assert t["skills"].management_list(p) == []
        with pytest.raises(PlatformError) as denied:
            t["skills"].detail(p, row["id"])
        assert denied.value.status == 404
    assert t["skills"].list_authorized(t["alice"]) == []
    with pytest.raises(PlatformError):
        t["skills"].read_file(t["alice"], row["id"], "SKILL.md")
    submit(t, row)
    assert t["skills"].detail(t["bob"], row["id"])["state"] == "validating"


def test_immutable_package_columns_and_name_version_uniqueness(skill_registry):
    t = skill_registry
    row = create(t)
    with pytest.raises(PlatformError) as duplicate:
        create(t)
    assert duplicate.value.code == "SKILL_VERSION_EXISTS"
    with pytest.raises(DBAPIError):
        with t["db"].transaction(t["alice"]) as c:
            c.execute(update(s.skill_versions).where(s.skill_versions.c.id == row["id"]).values(package={}))
    with t["admin"].connect() as c:
        assert c.execute(
            text("SELECT relforcerowsecurity FROM pg_class WHERE relname='aio_skill_versions'")
        ).scalar_one()
        assert c.execute(
            text("SELECT relforcerowsecurity FROM pg_class WHERE relname='aio_skill_validation_jobs'")
        ).scalar_one()


def test_validation_and_distinct_reviewer_are_mandatory(skill_registry):
    t = skill_registry
    row = create(t)
    with pytest.raises(PlatformError):
        t["skills"].submit(t["alice"], row["id"], SkillValidate(expected_revision=0, reviewer_id=t["alice"].user_id))
    with pytest.raises(PlatformError):
        t["skills"].review(
            t["alice"], row["id"], SkillReview(expected_revision=0, decision="approve", note="not allowed")
        )
    disabled = SkillService(t["db"], replace(t["settings"], manager_url=None))
    with pytest.raises(PlatformError) as no_executor:
        disabled.submit(t["alice"], row["id"], SkillValidate(expected_revision=0, reviewer_id=t["bob"].user_id))
    assert no_executor.value.code == "EXECUTION_UNAVAILABLE"


def test_current_action_authority_binds_command_stage_and_all_spec_bytes(skill_registry):
    t = skill_registry
    row = create(t)
    submit(t, row)
    h = t["validation"].claim(t["org"], "worker-a")
    assert t["validation"].claim(t["org"], "worker-b") is None
    command = h["commands"][0]
    payload = {
        "spec": h["spec"],
        "dispatch_id": command["dispatch_id"],
        "language": "python",
        "code": command["code"],
        "timeout_seconds": command["timeout_seconds"],
    }
    t["validation"].authorize("execute", payload)
    for changed in (
        {**payload, "code": "print('bypass')"},
        {**payload, "timeout_seconds": True},
        {**payload, "spec": {**h["spec"], "target_slot": "compute/main"}},
        {**payload, "dispatch_id": h["commands"][1]["dispatch_id"]},
    ):
        with pytest.raises(PlatformError):
            t["validation"].authorize("execute", changed)
    with pytest.raises(PlatformError):
        t["validation"].authorize("finalize", {"spec": h["spec"]})
    with t["admin"].begin() as c:
        c.execute(update(s.memberships).where(s.memberships.c.user_id == t["alice"].user_id).values(active=False))
    with pytest.raises(PlatformError):
        t["validation"].authorize("execute", payload)
    t["validation"].authorize("stop", {"spec": h["spec"]})


def test_lost_cleanup_is_durable_and_recovery_never_automatically_publishes(skill_registry):
    t = skill_registry
    row = create(t)
    submit(t, row)
    worker = SkillValidationWorker(
        t["validation"], SyntheticValidationManager(t, stop_fails=True), t["org"], "worker-a"
    )
    with pytest.raises(RuntimeError):
        asyncio.run(worker.run_once())
    detail = t["skills"].detail(t["alice"], row["id"])
    assert detail["state"] == "validating" and detail["validations"][0]["cleanup_state"] == "pending"
    with pytest.raises(PlatformError):
        t["skills"].review(
            t["bob"],
            row["id"],
            SkillReview(expected_revision=detail["revision"], decision="approve", note="not yet safe"),
        )
    with t["admin"].begin() as c:
        c.execute(
            update(s.skill_validation_jobs)
            .where(s.skill_validation_jobs.c.skill_id == row["id"])
            .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
    manager = SyntheticValidationManager(t)
    result = asyncio.run(SkillValidationWorker(t["validation"], manager, t["org"], "recovery-b").run_once())
    assert result["state"] == "failed" and manager.calls == ["stop"]
    detail = t["skills"].detail(t["alice"], row["id"])
    assert detail["state"] == "rejected" and detail["validations"][0]["cleanup_state"] == "confirmed"


def test_failed_execution_receipt_does_not_store_raw_error_or_pass(skill_registry):
    t = skill_registry
    row = create(t)
    submit(t, row)
    result = asyncio.run(
        SkillValidationWorker(
            t["validation"], SyntheticValidationManager(t, fail_execution=True), t["org"], "worker-a"
        ).run_once()
    )
    assert result["state"] == "failed"
    detail = t["skills"].detail(t["alice"], row["id"])
    assert "synthetic-private-error" not in str(detail)
    assert detail["validations"][0]["results"] == []


def test_publication_pins_tools_and_use_does_not_grant_package_read(skill_registry):
    t = skill_registry
    row = asyncio.run(publish_sample(t))
    assert row["state"] == "published" and {v["driver"] for v in row["published_tools"]} == {
        "skill.read",
        "skill.python",
    }
    with t["admin"].begin() as c:
        c.execute(
            delete(s.grants).where(s.grants.c.resource_id == row["id"], s.grants.c.subject_id == t["bob"].user_id)
        )
    t["administration"].set_grants(
        t["alice"], row["id"], GrantCreate(subject_type="user", subject_id=t["bob"].user_id, actions=("skill.use",))
    )
    assert len(t["skills"].list_authorized(t["bob"])) == 1
    with pytest.raises(PlatformError):
        t["skills"].read_file(t["bob"], row["id"], "SKILL.md")
    old_digest = row["digest"]
    newer = asyncio.run(publish_sample(t, package=sample_package(version="1.0.1")))
    assert newer["id"] != row["id"] and newer["digest"] != old_digest
    assert t["skills"].detail(t["alice"], row["id"])["digest"] == old_digest


def test_agent_skill_dependency_grants_and_current_disable_are_enforced(skill_registry):
    t = skill_registry
    row = asyncio.run(publish_sample(t))
    with t["admin"].begin() as c:
        model = provision_model(
            c,
            org_id=t["org"],
            owner_id=t["alice"].user_id,
            provider="synthetic",
            model="synthetic",
            config={"max_call_charge": "0.020000"},
        )
    agent = t["administration"].create_agent(
        t["alice"],
        AgentCreate(
            name="Skill agent",
            version="1",
            instruction="Use the bounded Skill",
            model_id=UUID(model["id"]),
            skill_ids=(row["id"],),
            run_budget=Decimal("0.1"),
            max_rounds=3,
        ),
    )
    result = t["administration"].set_grants(
        t["alice"],
        agent["id"],
        GrantCreate(
            subject_type="user", subject_id=t["bob"].user_id, actions=("agent.use",), include_dependencies=True
        ),
    )
    assert result["granted_resources"] == 5  # Agent + model + two tools + Skill
    with t["db"].transaction(t["bob"]) as c:
        for entry in row["published_tools"]:
            current_tool(c, t["bob"], UUID(entry["id"]), entry)
    t["administration"].set_status(t["alice"], row["id"], "disabled", 1)
    with t["db"].transaction(t["bob"]) as c:
        with pytest.raises(PlatformError):
            current_tool(c, t["bob"], UUID(row["published_tools"][0]["id"]), row["published_tools"][0])


def test_http_skill_admission_uses_auth_csrf_and_rejects_unknown_runtime_fields(skill_registry):
    t = skill_registry
    auth = AuthService(t["db"], t["settings"])
    token, _ = auth.create_session(t["org"], t["settings"].oidc_issuer, str(t["alice"].user_id))
    app = create_platform_app(t["settings"], database=t["db"])
    body = SkillCreate(package=sample_package(), sandbox_profile="test").model_dump(mode="json")
    with TestClient(app, base_url=t["settings"].public_origin) as client:
        assert client.get("/api/v2/admin/skills").status_code == 401
        client.cookies.set(t["settings"].session_cookie, token)
        assert client.post("/api/v2/admin/skills", json=body).status_code == 403
        headers = {"Origin": t["settings"].public_origin, "X-CSRF-Token": csrf_token(token)}
        assert (
            client.post(
                "/api/v2/admin/skills", json={**body, "host_command": "must-not-run"}, headers=headers
            ).status_code
            == 422
        )
        response = client.post("/api/v2/admin/skills", json=body, headers=headers)
        assert response.status_code == 201 and response.json()["state"] == "draft"
        assert client.get("/api/v2/skills").json()["items"] == []


def test_expired_validation_recovery_fences_old_worker_without_cleanup_lease_theft(skill_registry):
    t = skill_registry
    row = create(t)
    submit(t, row)
    original = t["validation"].claim(t["org"], "old-worker")
    with t["admin"].begin() as c:
        c.execute(
            update(s.skill_validation_jobs)
            .where(s.skill_validation_jobs.c.skill_id == row["id"])
            .values(deadline_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
    recovered = t["validation"].recover_one(t["org"], "cleanup-worker")
    assert recovered["generation"] == original["generation"] + 1
    assert t["validation"].recover_one(t["org"], "competing-cleanup-worker") is None
    with pytest.raises(PlatformError):
        t["validation"].stopping(original, None)
    t["validation"].authorize("stop", {"spec": recovered["spec"]})
    result = t["validation"].finish(recovered, {"state": "destroyed", "binding_id": recovered["spec"]["binding_id"]})
    assert result["state"] == "failed"


@pytest.mark.parametrize("withdraw", ["author", "profile"])
def test_publication_rechecks_current_author_and_operator_profile(skill_registry, withdraw):
    t = skill_registry
    row = create(t)
    submit(t, row)
    result = asyncio.run(
        SkillValidationWorker(t["validation"], SyntheticValidationManager(t), t["org"], "worker-a").run_once()
    )
    assert result["state"] == "passed"
    detail = t["skills"].detail(t["bob"], row["id"])
    service = t["skills"]
    if withdraw == "author":
        with t["admin"].begin() as c:
            c.execute(update(s.memberships).where(s.memberships.c.user_id == t["alice"].user_id).values(active=False))
    else:
        service = SkillService(t["db"], replace(t["settings"], sandbox_profiles=()))
    with pytest.raises(PlatformError):
        service.review(
            t["bob"],
            row["id"],
            SkillReview(
                expected_revision=detail["revision"], decision="approve", note="cannot bypass withdrawn authority"
            ),
        )
    with t["admin"].connect() as c:
        assert (
            c.execute(select(s.skill_versions.c.state).where(s.skill_versions.c.id == row["id"])).scalar_one()
            == "validated"
        )


def test_assigned_reviewer_read_grant_is_current_not_a_permanent_role_bypass(skill_registry):
    t = skill_registry
    row = create(t)
    submit(t, row)
    assert t["skills"].detail(t["bob"], row["id"])["reviewer_id"] == t["bob"].user_id
    grant = next(g for g in t["administration"].grants(t["alice"], row["id"])["items"] if g["action"] == "skill.read")
    t["administration"].remove_grant(t["alice"], row["id"], grant["id"], "user")
    with pytest.raises(PlatformError):
        t["skills"].detail(t["bob"], row["id"])


def test_department_skill_use_and_revocation_do_not_mutate_organization_policy(skill_registry):
    t = skill_registry
    row = asyncio.run(publish_sample(t))
    department = t["administration"].create_department(t["alice"], "Shared Skill department")
    t["administration"].set_department_member(t["alice"], department["id"], t["bob"].user_id, "member")
    with t["admin"].connect() as c:
        revision = c.execute(
            select(s.memberships.c.revision).where(
                s.memberships.c.org_id == t["org"], s.memberships.c.user_id == t["bob"].user_id
            )
        ).scalar_one()
    bob = replace(t["bob"], membership_revision=revision)
    t["administration"].set_grants(
        t["alice"],
        row["id"],
        GrantCreate(subject_type="department", subject_id=department["id"], actions=("skill.use",)),
    )
    assert len(t["skills"].list_authorized(bob)) == 1
    t["administration"].set_department_member(t["alice"], department["id"], bob.user_id, None)
    with t["admin"].connect() as c:
        revision = c.execute(
            select(s.memberships.c.revision).where(
                s.memberships.c.org_id == t["org"], s.memberships.c.user_id == bob.user_id
            )
        ).scalar_one()
        assert (
            c.execute(select(s.organizations.c.policy_revision).where(s.organizations.c.id == t["org"])).scalar_one()
            == 0
        )
    assert t["skills"].list_authorized(replace(bob, membership_revision=revision)) == []


def test_private_manager_http_authority_dispatches_skill_slot_without_artifact_host_execution(skill_registry):
    t = skill_registry
    row = create(t)
    submit(t, row)
    handle = t["validation"].claim(t["org"], "worker-a")
    token = "synthetic-control-" + "c" * 40
    settings = replace(t["settings"], manager_control_token=token)
    app = create_platform_app(settings, database=t["db"])
    command = handle["commands"][0]
    payload = {
        "operation": "execute",
        "spec": handle["spec"],
        "dispatch_id": command["dispatch_id"],
        "language": "python",
        "code": command["code"],
        "timeout_seconds": command["timeout_seconds"],
    }
    with TestClient(app) as client:
        assert client.post("/internal/v1/sandbox/authorize", json=payload).status_code == 401
        assert client.post(
            "/internal/v1/sandbox/authorize", json=payload, headers={"X-Manager-Token": token}
        ).json() == {"allowed": True}
        assert (
            client.post(
                "/internal/v1/sandbox/authorize",
                json={**payload, "code": "print('not approved')"},
                headers={"X-Manager-Token": token},
            ).status_code
            == 403
        )
