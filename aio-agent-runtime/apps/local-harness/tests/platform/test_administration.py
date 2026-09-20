"""Real PostgreSQL organization management, department grants and privacy boundaries."""

from dataclasses import replace
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.admin.contracts import AgentCreate, GrantCreate, MemberCreate, MemberUpdate, ModelCreate, ToolCreate
from app.admin.service import AdminService
from app.api.v2.application import create_platform_app
from app.auth.principal import Principal
from app.auth.service import AuthService, csrf_token
from app.db import schema as s
from app.db.provisioning import provision_identity
from app.platform_errors import PlatformError
from app.policy.repository import current_facts, require_resource


@pytest.fixture
def administration(tenant):
    t = dict(tenant)
    uid = uuid4()
    with t["admin"].begin() as c:
        provision_identity(
            c,
            org_id=t["org"],
            user_id=uid,
            issuer=t["settings"].oidc_issuer,
            subject=str(uid),
            display_name="Organization admin",
            role="org_admin",
        )
    p = Principal(t["org"], uid, 0)
    settings = replace(
        t["settings"],
        model_allowed_origins=frozenset({"https://models.example.test"}),
        model_secret_names=frozenset({"APPROVED_MODEL_KEY"}),
        sandbox_profiles=({"id": "standard", "image_digest": "sha256:" + "1" * 64, "max_timeout_seconds": 120},),
    )
    t.update(org_admin=p, administration=AdminService(t["db"], settings), settings=settings)
    return t


def fresh(t, p):
    with t["admin"].connect() as c:
        rev = c.execute(
            select(s.memberships.c.revision).where(
                s.memberships.c.org_id == p.org_id, s.memberships.c.user_id == p.user_id
            )
        ).scalar_one()
    return replace(p, membership_revision=rev)


def published_bundle(t):
    a = t["administration"]
    p = t["org_admin"]
    model = a.create_model(
        p,
        ModelCreate(
            name="Approved model",
            provider="internal",
            model="model-1",
            endpoint="https://models.example.test/v1/chat/completions",
            secret_env="APPROVED_MODEL_KEY",
            max_output_tokens=2048,
            max_call_charge=Decimal("0.01"),
            input_price_per_million=Decimal("1"),
            output_price_per_million=Decimal("2"),
        ),
    )
    tool = a.create_tool(
        p,
        ToolCreate(
            name="python_compute", description="Isolated computation", sandbox_profile="standard", timeout_seconds=30
        ),
    )
    agent = a.create_agent(
        p,
        AgentCreate(
            name="Analysis assistant",
            version="1",
            instruction="Use only approved tools.",
            model_id=UUID(model["id"]),
            tool_ids=(UUID(tool["id"]),),
            run_budget=Decimal("0.1"),
            max_rounds=4,
        ),
    )
    return model, tool, agent


def test_team_publish_checks_global_rounds_budget_and_frozen_policy(administration):
    from pydantic import ValidationError
    from app.runtime.team_contracts import TeamPolicy

    t = administration
    model, tool, _ = published_bundle(t)
    body = dict(
        name="Team agent",
        version="1",
        instruction="Approved sequential team",
        model_id=UUID(model["id"]),
        tool_ids=(UUID(tool["id"]),),
        run_budget=Decimal("0.03"),
        max_rounds=8,
        team=TeamPolicy(max_steps=2, max_step_rounds=3),
    )
    with pytest.raises(ValidationError):
        AgentCreate(**{**body, "max_rounds": 3})
    with pytest.raises(PlatformError) as error:
        t["administration"].create_agent(t["org_admin"], AgentCreate(**body))
    assert error.value.code == "AGENT_BUDGET_INVALID"
    agent = t["administration"].create_agent(t["org_admin"], AgentCreate(**{**body, "run_budget": Decimal("0.10")}))
    assert agent["manifest"]["team"] == {"max_steps": 2, "max_step_rounds": 3}
    assert len(agent["manifest"]["tools"]) == 1


def test_admin_role_does_not_grant_private_conversation_access(administration):
    t = administration
    a = t["administration"]
    p = t["org_admin"]
    assert len(a.members(p)) == 3
    assert a.me(p)["permissions"]["organization_admin"] is True
    with pytest.raises(PlatformError):
        t["service"].session_detail(p, t["session"])
    assert t["service"].list_sessions(p) == []
    with pytest.raises(PlatformError) as exc:
        a.members(t["alice"])
    assert exc.value.status == 403
    with pytest.raises(PlatformError):
        a.grants(p, t["project"])


def test_member_provisioning_is_exact_issuer_scoped_and_duplicate_safe(administration):
    t = administration
    a = t["administration"]
    p = t["org_admin"]
    body = MemberCreate(subject="sales/new-member", display_name="New employee")
    member = a.create_member(p, body)
    assert member["role"] == "member" and member["active"]
    with pytest.raises(PlatformError) as exc:
        a.create_member(p, body)
    assert exc.value.code == "MEMBER_EXISTS"
    with t["admin"].connect() as c:
        assert (
            c.execute(select(s.users.c.issuer).where(s.users.c.id == member["user_id"])).scalar_one()
            == t["settings"].oidc_issuer
        )
        assert c.execute(select(s.budgets.c.id).where(s.budgets.c.owner_id == member["user_id"])).first() is None
    assert all(r["user_id"] != t["outsider"].user_id for r in a.members(p))


def test_last_admin_cannot_be_disabled_or_demoted(administration):
    t = administration
    a = t["administration"]
    p = t["org_admin"]
    for active, role in [(False, "org_admin"), (True, "member")]:
        with pytest.raises(PlatformError) as exc:
            a.update_member(
                p, p.user_id, MemberUpdate(expected_revision=0, display_name="Admin", active=active, role=role)
            )
        assert exc.value.code == "LAST_ADMIN_REQUIRED"


def test_member_disable_revokes_cookie_and_stale_requests(administration):
    t = administration
    a = t["administration"]
    auth = AuthService(t["db"], t["settings"])
    token, _ = auth.create_session(t["org"], t["settings"].oidc_issuer, str(t["bob"].user_id))
    a.update_member(
        t["org_admin"],
        t["bob"].user_id,
        MemberUpdate(expected_revision=0, display_name="Bob", active=False, role="member"),
    )
    with pytest.raises(PlatformError):
        auth.authenticate(token)
    with pytest.raises(PlatformError):
        a.update_member(
            t["org_admin"],
            t["bob"].user_id,
            MemberUpdate(expected_revision=0, display_name="Bob", active=True, role="member"),
        )


def test_department_grants_filter_lists_and_revocation_blocks_direct_access(administration):
    t = administration
    a = t["administration"]
    p = t["org_admin"]
    model, tool, agent = published_bundle(t)
    dept = a.create_department(p, "Sales")
    a.set_department_member(p, dept["id"], t["alice"].user_id, "member")
    a.set_grants(
        p,
        agent["id"],
        GrantCreate(
            subject_type="department",
            subject_id=dept["id"],
            actions=("agent.use", "agent.read"),
            include_dependencies=True,
        ),
    )
    alice = fresh(t, t["alice"])
    assert agent["id"] in {row["id"] for row in t["service"].list_agents(alice)}
    assert agent["id"] not in {row["id"] for row in t["service"].list_agents(t["bob"])}
    with t["db"].transaction(alice) as c:
        assert dept["id"] in current_facts(c, alice).department_ids
        require_resource(c, alice, UUID(model["id"]), "model.use")
        require_resource(c, alice, UUID(tool["id"]), "tool.use")
    a.set_department_member(p, dept["id"], alice.user_id, None)
    with pytest.raises(PlatformError):
        t["service"].list_agents(alice)
    alice = fresh(t, alice)
    assert agent["id"] not in {row["id"] for row in t["service"].list_agents(alice)}
    with t["db"].transaction(alice) as c:
        with pytest.raises(PlatformError):
            require_resource(c, alice, UUID(tool["id"]), "tool.use")


def test_department_disable_takes_effect_without_deleting_membership(administration):
    t = administration
    a = t["administration"]
    p = t["org_admin"]
    dept = a.create_department(p, "Finance")
    a.set_department_member(p, dept["id"], t["bob"].user_id, "member")
    a.set_grants(
        t["alice"],
        t["project"],
        GrantCreate(subject_type="department", subject_id=dept["id"], actions=("project.read",)),
    )
    assert t["service"].list_projects(fresh(t, t["bob"]))
    a.set_department_active(p, dept["id"], False)
    assert t["service"].list_projects(fresh(t, t["bob"])) == []
    with t["admin"].connect() as c:
        assert c.execute(
            select(s.department_memberships.c.user_id).where(s.department_memberships.c.department_id == dept["id"])
        ).first()


def test_grant_cannot_cross_org_or_use_wrong_resource_action(administration):
    t = administration
    a = t["administration"]
    for recipient, action in [(t["outsider"].user_id, "project.read"), (t["bob"].user_id, "approval.decide")]:
        with pytest.raises(PlatformError):
            a.set_grants(
                t["alice"], t["project"], GrantCreate(subject_type="user", subject_id=recipient, actions=(action,))
            )
    a.set_grants(
        t["alice"],
        t["project"],
        GrantCreate(subject_type="user", subject_id=t["bob"].user_id, actions=("project.read",)),
    )
    assert t["service"].list_projects(t["bob"])
    assert t["service"].list_sessions(t["bob"]) == []
    grant = a.grants(t["alice"], t["project"])["items"][0]
    a.remove_grant(t["alice"], t["project"], grant["id"], "user")
    assert t["service"].list_projects(t["bob"]) == []


def test_admin_model_creation_never_accepts_unapproved_endpoint_or_secret(administration):
    t = administration
    a = t["administration"]
    p = t["org_admin"]
    body = ModelCreate(
        name="Model",
        provider="approved",
        model="id",
        endpoint="https://models.example.test/v1/chat/completions",
        secret_env="APPROVED_MODEL_KEY",
        max_output_tokens=2048,
        max_call_charge=Decimal("0.01"),
        input_price_per_million=Decimal("1"),
        output_price_per_million=Decimal("2"),
    )
    for change in [
        {"endpoint": "https://evil.example.test/v1/chat/completions"},
        {"secret_env": "PLATFORM_DATABASE_URL"},
    ]:
        with pytest.raises(PlatformError):
            a.create_model(p, body.model_copy(update=change))
    created = a.create_model(p, body)
    rows = a.models(p)
    assert rows[0]["id"] == UUID(created["id"])
    assert all("api_key" not in row["config"] and "password" not in row["config"] for row in rows)


def test_tool_profiles_and_agent_dependencies_are_checked(administration):
    t = administration
    a = t["administration"]
    p = t["org_admin"]
    with pytest.raises(PlatformError):
        a.create_tool(p, ToolCreate(name="run", description="x", sandbox_profile="root-network", timeout_seconds=1))
    with pytest.raises(PlatformError):
        a.create_tool(p, ToolCreate(name="run", description="x", sandbox_profile="standard", timeout_seconds=300))
    model, tool, agent = published_bundle(t)
    a.set_status(p, UUID(tool["id"]), "disabled", 0)
    with pytest.raises(PlatformError):
        a.create_agent(
            p,
            AgentCreate(
                name="Rejected",
                version="1",
                instruction="x",
                model_id=UUID(model["id"]),
                tool_ids=(UUID(tool["id"]),),
                run_budget=Decimal("0.1"),
                max_rounds=4,
            ),
        )
    with t["admin"].connect() as c:
        original = c.execute(
            select(s.agent_versions.c.manifest).where(s.agent_versions.c.id == agent["id"])
        ).scalar_one()
        assert original["tools"][0]["digest"] == tool["digest"]


def test_budget_management_cannot_erase_committed_spend(administration):
    t = administration
    a = t["administration"]
    p = t["org_admin"]
    with t["admin"].begin() as c:
        c.execute(
            update(s.budgets)
            .where(s.budgets.c.org_id == t["org"], s.budgets.c.owner_id == t["bob"].user_id)
            .values(consumed=Decimal("2"), reserved=Decimal("1"))
        )
    with pytest.raises(PlatformError) as exc:
        a.set_budget(p, t["bob"].user_id, Decimal("2"))
    assert exc.value.code == "BUDGET_BELOW_COMMITTED"
    a.set_budget(p, t["bob"].user_id, Decimal("5"))
    usage = a.own_budget(t["bob"])
    assert usage["consumed"] == "2.000000" and usage["reserved"] == "1.000000"
    with pytest.raises(PlatformError):
        a.set_budget(p, t["outsider"].user_id, Decimal("5"))


def test_auditor_and_operator_see_only_explicit_metadata(administration):
    t = administration
    a = t["administration"]
    p = t["org_admin"]
    a.update_member(
        p, t["bob"].user_id, MemberUpdate(expected_revision=0, display_name="Operator", active=True, role="operator")
    )
    bob = fresh(t, t["bob"])
    assert a.operations(bob) == []
    with pytest.raises(PlatformError):
        a.audit_events(bob)
    a.update_member(
        p,
        bob.user_id,
        MemberUpdate(expected_revision=bob.membership_revision, display_name="Auditor", active=True, role="auditor"),
    )
    bob = fresh(t, bob)
    logs = a.audit_events(bob)
    assert logs and all("metadata" not in row and "messages" not in row for row in logs)
    with pytest.raises(PlatformError):
        a.operations(bob)
    with pytest.raises(PlatformError):
        t["service"].session_detail(bob, t["session"])


def test_admin_http_requires_real_role_csrf_and_rejects_shell_fields(administration):
    t = administration
    auth = AuthService(t["db"], t["settings"])
    token, _ = auth.create_session(t["org"], t["settings"].oidc_issuer, str(t["alice"].user_id))
    app = create_platform_app(t["settings"], database=t["db"])
    with TestClient(app, base_url=t["settings"].public_origin) as client:
        client.cookies.set(t["settings"].session_cookie, token)
        assert client.get("/api/v2/admin/members").status_code == 403
        me = client.get("/api/v2/me").json()
        assert not me["permissions"]["organization_admin"]
        admin_token, _ = auth.create_session(t["org"], t["settings"].oidc_issuer, str(t["org_admin"].user_id))
        client.cookies.set(t["settings"].session_cookie, admin_token)
        assert client.get("/api/v2/admin/members").status_code == 200
        assert client.post("/api/v2/admin/departments", json={"name": "Sales"}).status_code == 403
        headers = {"Origin": t["settings"].public_origin, "X-CSRF-Token": csrf_token(admin_token)}
        assert client.post("/api/v2/admin/departments", json={"name": "Sales"}, headers=headers).status_code == 201
        assert (
            client.post(
                "/api/v2/admin/tools",
                json={
                    "name": "x",
                    "description": "x",
                    "sandbox_profile": "standard",
                    "timeout_seconds": 30,
                    "command": "sudo anything",
                    "privileged": True,
                },
                headers=headers,
            ).status_code
            == 422
        )
        assert client.get(f"/api/v2/sessions/{t['session']}").status_code == 404


def test_session_archive_refuses_unresolved_run_and_preserves_history(administration):
    t = administration
    body = {
        "message": "private message",
        "agent_version_id": str(t["agent"]),
        "expected_session_revision": 0,
        "mode": "single",
        "input_artifact_ids": [],
    }
    run = t["service"].create_run(t["alice"], t["session"], body, "session-archive-test-key")
    with pytest.raises(PlatformError):
        t["service"].archive_session(t["alice"], t["session"], 1)
    t["service"].cancel_run(t["alice"], run["run_id"])
    assert t["service"].archive_session(t["alice"], t["session"], 1)["archived"]
    assert t["service"].list_sessions(t["alice"]) == []
    with t["admin"].connect() as c:
        assert c.execute(select(s.messages.c.id).where(s.messages.c.run_id == run["run_id"])).first()


def test_directory_never_exposes_other_org_subjects(administration):
    t = administration
    a = t["administration"]
    directory = a.directory(t["alice"])
    assert all(set(member) == {"user_id", "display_name"} for member in directory["members"])
    assert t["outsider"].user_id not in {m["user_id"] for m in directory["members"]}


def test_private_project_grant_change_does_not_invalidate_unrelated_org_policy(administration):
    t = administration
    a = t["administration"]
    with t["admin"].connect() as c:
        before = c.execute(
            select(s.organizations.c.policy_revision).where(s.organizations.c.id == t["org"])
        ).scalar_one()
    a.set_grants(
        t["alice"],
        t["project"],
        GrantCreate(subject_type="user", subject_id=t["bob"].user_id, actions=("project.read",)),
    )
    with t["admin"].connect() as c:
        after = c.execute(
            select(s.organizations.c.policy_revision).where(s.organizations.c.id == t["org"])
        ).scalar_one()
        assert after == before
        assert c.execute(select(s.resources.c.revision).where(s.resources.c.id == t["project"])).scalar_one() > 0
    assert t["service"].list_projects(t["bob"])
