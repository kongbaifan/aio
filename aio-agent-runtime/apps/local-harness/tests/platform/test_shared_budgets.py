"""Real PostgreSQL scope admission, financial projections and authorization boundaries."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select, update
from sqlalchemy.exc import DBAPIError

from app.admin.service import AdminService
from app.api.v2.application import create_platform_app
from app.auth.service import AuthService, csrf_token
from app.db import schema as s
from app.db.provisioning import provision_agent
from app.platform_errors import PlatformError
from knowledge_fixtures import base, ingest, upload
from test_administration import administration as administration, fresh
from test_execution_integration import scenario as scenario, SyntheticModelFactory, worker, claim
from app.runtime.actions import canonical_digest


# The exact projection the management contract permits (AdminService._pool_view). Financial
# detail belonging to a person or a call — prompts, requester identity, per-user consumption,
# call parameters — is not part of a shared pool summary, so an added key must fail loudly
# instead of relying on a substring smoke test that the response shape can never trip.
POOL_VIEW_KEYS = frozenset(
    {
        "id",
        "scope",
        "department_id",
        "display_name",
        "currency",
        "hard_limit",
        "reserved",
        "consumed",
        "remaining",
        "warning",
        "exhausted",
        "revision",
        "created_at",
        "opening_consumed",
    }
)


def department(t, *principals, name=None):
    id = uuid4()
    with t["admin"].begin() as c:
        c.execute(insert(s.departments).values(org_id=t["org"], id=id, name=name or str(id)))
        for p in principals:
            c.execute(insert(s.department_memberships).values(org_id=t["org"], department_id=id, user_id=p.user_id))
    return id


def rows(t, table):
    with t["db"].transaction(t["alice"]) as c:
        return [dict(row) for row in c.execute(select(table).where(table.c.org_id == t["org"])).mappings()]


def caps(t):
    """Persisted shared configuration, read directly instead of through the endpoint under test."""
    return {row["department_id"]: (row["hard_limit"], row["revision"]) for row in rows(t, s.budget_pools)}


def assert_projection(t):
    pools, allocations, personal = rows(t, s.budget_pools), rows(t, s.budget_allocations), rows(t, s.budgets)
    assert pools
    for pool in pools:
        bound = [row for row in allocations if row["pool_id"] == pool["id"]]
        assert pool["reserved"] == sum((row["reserved"] for row in bound), Decimal(0))
        assert pool["consumed"] == pool["opening_consumed"] + sum((row["consumed"] for row in bound), Decimal(0))
    organization = next(pool for pool in pools if pool["department_id"] is None)
    # Opening consumption is the migrated projection of personal charges already
    # settled before v13, so the organization total still equals the personal
    # total: opening covers the pre-migration part and allocations the rest.
    assert organization["reserved"] == sum((row["reserved"] for row in personal), Decimal(0))
    assert organization["consumed"] == sum((row["consumed"] for row in personal), Decimal(0))
    return {pool["department_id"]: pool for pool in pools}


def private_session(t, p):
    # Distinct Agent and Project resources ensure shared-cap concurrency is not
    # accidentally serialized by both actors using the same Agent resource lock.
    with t["admin"].begin() as c:
        agent = provision_agent(
            c,
            org_id=t["org"],
            owner_id=p.user_id,
            name="Independent budget fixture",
            version=uuid4().hex,
            engine="test-fixture-only",
            instruction="Synthetic only",
            manifest={"run_budget": "0.100000", "tools": []},
        )
    project = t["service"].create_project(p, "Budget concurrency")
    session = t["service"].create_session(p, project["id"], agent, "Independent admission")
    return session["id"], {
        "message": "Synthetic private prompt",
        "agent_version_id": str(agent),
        "expected_session_revision": 0,
        "input_artifact_ids": [],
        "mode": "single",
    }


def create(t, p, item, key=None):
    return t["service"].create_run(p, item[0], item[1], key or "budget-test-" + uuid4().hex)


def reconciler(t):
    """Give the second identity organization administration and Run reconciliation.

    Shared caps are configured by an administrator, and late invoices are checked by a
    different person than the run owner; both facts are required by the same tests.
    """
    with t["admin"].begin() as c:
        c.execute(
            update(s.memberships)
            .where(s.memberships.c.org_id == t["org"], s.memberships.c.user_id == t["bob"].user_id)
            .values(role="org_admin")
        )
        c.execute(
            insert(s.grants).values(
                org_id=t["org"],
                id=uuid4(),
                resource_id=t["run_id"],
                subject_id=t["bob"].user_id,
                action="run.reconcile",
            )
        )
    return AdminService(t["db"], t["settings"])


@pytest.mark.parametrize("scope", ["organization", "department"])
def test_two_users_cannot_reserve_the_same_last_shared_amount(administration, scope):
    t = administration
    dept = department(t, t["alice"], t["bob"])
    target = dept if scope == "department" else None
    t["administration"].set_shared_budget(t["org_admin"], target, Decimal("0.1"), 0)
    sessions = [private_session(t, p) for p in (t["alice"], t["bob"])]
    barrier = Barrier(2)

    def enter(index):
        barrier.wait(timeout=5)
        try:
            return create(t, (t["alice"], t["bob"])[index], sessions[index])
        except PlatformError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        result = list(executor.map(enter, (0, 1)))
    assert sum(isinstance(item, dict) for item in result) == 1
    assert "SHARED_BUDGET_EXCEEDED" in result
    pools = assert_projection(t)
    assert pools[target]["reserved"] == Decimal("0.1")
    assert len(rows(t, s.runs)) == len(rows(t, s.jobs)) == len(rows(t, s.idempotency_keys)) == 1


def test_distinct_departments_have_distinct_caps_and_overlap_is_not_summed(administration):
    t = administration
    deps = [department(t, p) for p in (t["alice"], t["bob"])]
    for dept in deps:
        t["administration"].set_shared_budget(t["org_admin"], dept, Decimal("0.1"), 0)
    for p in (t["alice"], t["bob"]):
        create(t, p, private_session(t, p))
    pools = assert_projection(t)
    assert pools[None]["reserved"] == Decimal("0.2")
    assert all(pools[dept]["reserved"] == Decimal("0.1") for dept in deps)


def test_all_active_departments_apply_and_failed_admission_is_atomic(administration):
    t = administration
    one, two = department(t, t["alice"]), department(t, t["alice"])
    t["administration"].set_shared_budget(t["org_admin"], one, Decimal("1"), 0)
    t["administration"].set_shared_budget(t["org_admin"], two, Decimal("0.09"), 0)
    item = private_session(t, t["alice"])
    with pytest.raises(PlatformError, match="Department") as error:
        create(t, t["alice"], item)
    assert error.value.code == "SHARED_BUDGET_EXCEEDED"
    assert rows(t, s.runs) == rows(t, s.budget_allocations) == rows(t, s.idempotency_keys) == []
    assert all(pool["reserved"] == 0 for pool in assert_projection(t).values())


def test_idempotent_retry_then_cancel_releases_each_scope_once(administration):
    t = administration
    department(t, t["alice"])
    item = private_session(t, t["alice"])
    first = create(t, t["alice"], item, "same-shared-budget-key")
    second = create(t, t["alice"], item, "same-shared-budget-key")
    assert first["run_id"] == second["run_id"]
    assert len(rows(t, s.budget_allocations)) == 2
    assert all(pool["reserved"] == Decimal("0.1") for pool in assert_projection(t).values())
    for _ in range(2):
        t["service"].cancel_run(t["alice"], first["run_id"])
    assert all(pool["reserved"] == pool["consumed"] == 0 for pool in assert_projection(t).values())


def test_enabling_caps_accounts_for_existing_holds_and_never_resets_them(administration):
    t = administration
    dept = department(t, t["alice"])
    create(t, t["alice"], private_session(t, t["alice"]))
    for scope in (None, dept):
        with pytest.raises(PlatformError) as error:
            t["administration"].set_shared_budget(t["org_admin"], scope, Decimal("0.09"), 0)
        assert error.value.code == "BUDGET_BELOW_COMMITTED"
        t["administration"].set_shared_budget(t["org_admin"], scope, Decimal("0.1"), 0)
        t["administration"].set_shared_budget(t["org_admin"], scope, None, 1)
    assert all(pool["reserved"] == Decimal("0.1") for pool in assert_projection(t).values())
    with pytest.raises(PlatformError) as error:
        t["administration"].set_shared_budget(t["org_admin"], dept, Decimal("1"), 0)
    assert error.value.code == "REVISION_CONFLICT"
    # Each accepted cap change leaves one durable audit row; a refused one leaves none,
    # so a rejected edit can never be mistaken for an applied policy decision.
    events = [row for row in rows(t, s.audit) if row["action"] == "budget.shared_limit"]
    assert len(events) == 4
    assert {row["outcome"] for row in events} == {"updated"}
    assert {row["actor_id"] for row in events} == {t["org_admin"].user_id}
    # Read order is not guaranteed, so compare the set of recorded decisions: for each
    # scope both the enable at revision 1 and the explicit removal at revision 2.
    recorded = {
        (row["metadata"]["department_id"], row["metadata"]["hard_limit"], row["metadata"]["revision"]) for row in events
    }
    assert recorded == {(None, "0.1", 1), (None, None, 2), (str(dept), "0.1", 1), (str(dept), None, 2)}
    assert all(row["metadata"]["currency"] == "USD" for row in events)


def test_department_transfer_preserves_old_binding_and_uses_new_scope_for_new_work(administration):
    t = administration
    old, new = department(t, t["alice"]), department(t)
    old_run = create(t, t["alice"], private_session(t, t["alice"]))
    a, p = t["administration"], t["org_admin"]
    a.set_department_member(p, old, t["alice"].user_id, None)
    a.set_department_member(p, new, t["alice"].user_id, "member")
    t["alice"] = fresh(t, t["alice"])
    new_run = create(t, t["alice"], private_session(t, t["alice"]))
    pools = assert_projection(t)
    assert pools[old]["reserved"] == pools[new]["reserved"] == Decimal("0.1")
    t["service"].cancel_run(t["alice"], old_run["run_id"])
    pools = assert_projection(t)
    assert pools[old]["reserved"] == 0 and pools[new]["reserved"] == Decimal("0.1")
    assert next(row for row in rows(t, s.runs) if row["id"] == new_run["run_id"])["state"] == "queued"


def test_unknown_late_charge_is_projected_once_even_above_cap(tenant, scenario):
    dept = department(tenant, tenant["alice"])
    t = scenario()
    admin = reconciler(t)
    for scope in (None, dept):
        admin.set_shared_budget(t["bob"], scope, Decimal("0.1"), 0)
    assert (
        asyncio.run(worker(t, SyntheticModelFactory(no_tool=True, unknown_usage=True)).run_once())["state"]
        == "succeeded"
    )
    assert all(pool["reserved"] == Decimal("0.02") and pool["consumed"] == 0 for pool in assert_projection(t).values())
    call = rows(t, s.model_calls)[0]
    for amount in (Decimal("0.15"), Decimal("0.150000")):
        t["store"].record_late_model_usage(t["bob"], call["id"], amount, "synthetic-invoice/one")
    assert all(pool["reserved"] == 0 and pool["consumed"] == Decimal("0.15") for pool in assert_projection(t).values())
    assert len(rows(t, s.ledger)) == 2
    with pytest.raises(PlatformError) as error:
        create(t, t["alice"], private_session(t, t["alice"]))
    assert error.value.code == "SHARED_BUDGET_EXCEEDED"


def test_normal_worker_settlement_is_not_double_charged(tenant, scenario):
    dept = department(tenant, tenant["alice"])
    t = scenario()
    reconciler(t).set_shared_budget(t["bob"], dept, Decimal("0.1"), 0)
    assert asyncio.run(worker(t).run_once())["state"] == "succeeded"
    assert all(pool["consumed"] == Decimal("0.002") and pool["reserved"] == 0 for pool in assert_projection(t).values())
    assert asyncio.run(worker(t).run_once()) is None
    assert all(pool["consumed"] == Decimal("0.002") and pool["reserved"] == 0 for pool in assert_projection(t).values())


def test_queue_expiry_recovery_releases_every_scope_exactly_once(tenant, scenario):
    dept = department(tenant, tenant["alice"])
    t = scenario()
    reconciler(t).set_shared_budget(t["bob"], dept, Decimal("0.1"), 0)
    # Admission holds the whole published Run budget, not one model call's bound.
    assert all(pool["reserved"] == Decimal("0.1") for pool in assert_projection(t).values())
    with t["admin"].begin() as c:
        c.execute(
            update(s.runs)
            .where(s.runs.c.id == t["run_id"])
            .values(queue_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
    assert t["store"].recover_due(t["org"])[0]["state"] == "timed_out"
    assert all(pool["reserved"] == pool["consumed"] == 0 for pool in assert_projection(t).values())
    # A second sweep must not release the same hold twice.
    assert t["store"].recover_due(t["org"]) == []
    assert all(pool["reserved"] == pool["consumed"] == 0 for pool in assert_projection(t).values())


def test_revoked_department_still_settles_the_original_charge_fact(tenant, scenario):
    dept = department(tenant, tenant["alice"])
    t = scenario()
    admin = reconciler(t)
    admin.set_shared_budget(t["bob"], dept, Decimal("0.1"), 0)
    assert (
        asyncio.run(worker(t, SyntheticModelFactory(no_tool=True, unknown_usage=True)).run_once())["state"]
        == "succeeded"
    )
    assert all(pool["reserved"] == Decimal("0.02") for pool in assert_projection(t).values())
    with t["admin"].begin() as c:
        c.execute(
            update(s.departments)
            .where(s.departments.c.org_id == t["org"], s.departments.c.id == dept)
            .values(active=False)
        )
    # Revoking the scope must not erase the outstanding hold or block the real invoice.
    call = rows(t, s.model_calls)[0]
    t["store"].record_late_model_usage(t["bob"], call["id"], Decimal("0.03"), "revoked-scope-invoice")
    pools = assert_projection(t)
    assert pools[dept]["reserved"] == 0 and pools[dept]["consumed"] == Decimal("0.03")
    # A deactivated department is no longer a scope for new work.
    create(t, t["alice"], private_session(t, t["alice"]))
    assert assert_projection(t)[dept]["reserved"] == 0


def test_exhausted_department_does_not_block_a_sibling_department(administration):
    t = administration
    full, spare = department(t, t["alice"]), department(t, t["bob"])
    a, p = t["administration"], t["org_admin"]
    a.set_shared_budget(p, full, Decimal("0.1"), 0)
    a.set_shared_budget(p, spare, Decimal("0.1"), 0)
    create(t, t["alice"], private_session(t, t["alice"]))
    with pytest.raises(PlatformError) as error:
        create(t, t["alice"], private_session(t, t["alice"]))
    assert error.value.code == "SHARED_BUDGET_EXCEEDED"
    # The sibling department is untouched by the exhausted one.
    create(t, t["bob"], private_session(t, t["bob"]))
    pools = assert_projection(t)
    assert pools[full]["reserved"] == pools[spare]["reserved"] == Decimal("0.1")
    assert pools[None]["reserved"] == Decimal("0.2")


def test_member_without_any_department_is_still_capped_by_the_organization(administration):
    t = administration
    t["administration"].set_shared_budget(t["org_admin"], None, Decimal("0.1"), 0)
    create(t, t["alice"], private_session(t, t["alice"]))
    with pytest.raises(PlatformError) as error:
        create(t, t["bob"], private_session(t, t["bob"]))
    assert error.value.code == "SHARED_BUDGET_EXCEEDED"
    pools = assert_projection(t)
    assert list(pools) == [None] and pools[None]["reserved"] == Decimal("0.1")


@pytest.mark.parametrize("stage", ["prepare", "dispatch"])
def test_delayed_overage_blocks_already_admitted_runs_before_next_paid_dispatch(scenario, stage):
    first = scenario()
    reconciler(first).set_shared_budget(first["bob"], None, Decimal("0.2"), 0)
    assert (
        asyncio.run(worker(first, SyntheticModelFactory(no_tool=True, unknown_usage=True)).run_once())["state"]
        == "succeeded"
    )
    second = scenario()
    handle = claim(second)
    seq = second["store"].load(handle)["run"]["checkpoint_seq"]
    digest = canonical_digest("shared-budget-dispatch", {"synthetic": True})
    prepared = second["store"].prepare_model_call(handle, seq, digest, Decimal("0.02")) if stage == "dispatch" else None
    first_call = next(row for row in rows(first, s.model_calls) if row["run_id"] == first["run_id"])
    first["store"].record_late_model_usage(first["bob"], first_call["id"], Decimal("0.21"), "late-synthetic-overage")
    with pytest.raises(PlatformError) as error:
        if prepared:
            second["store"].start_model_call(handle, prepared["id"])
        else:
            second["store"].prepare_model_call(handle, seq, digest, Decimal("0.02"))
    assert error.value.code == "SHARED_BUDGET_EXCEEDED"
    assert not any(
        row["state"] == "started" for row in rows(second, s.model_calls) if row["run_id"] == second["run_id"]
    )
    assert_projection(first)


def test_ingestion_and_standalone_embedding_are_capped_while_preview_stays_lexical(knowledge_platform):
    t = knowledge_platform
    dept = department(t, t["alice"])
    admin = t["knowledge"].admin
    admin.set_shared_budget(t["alice"], dept, Decimal("0.02"), 0)
    kb = base(t, hybrid=True)
    upload(t, kb, "年假与休假规则")
    assert asyncio.run(ingest(t))["state"] == "ready"
    assert assert_projection(t)[dept]["consumed"] == Decimal("0.001")
    before = len(t["embedding_factory"].requests)
    preview = asyncio.run(t["retrieval"].search(t["alice"], kb["id"], "年假", "preview:" + uuid4().hex))
    assert preview["retrieval_mode"] == "lexical" and len(t["embedding_factory"].requests) == before
    upload(t, kb, "额外的休假说明")
    assert asyncio.run(ingest(t))["error_code"] == "SHARED_BUDGET_EXCEEDED"
    # The browser intentionally remains lexical. Exercise the existing internal
    # standalone embedding-intent path explicitly, not a fictitious paid preview.
    query = t["retrieval"].prepare(t["alice"], kb["id"], "年假", "standalone:" + uuid4().hex, 5)
    with pytest.raises(PlatformError) as error:
        t["billing"].prepare_query(t["alice"], query["id"], ["年假"])
    assert error.value.code == "SHARED_BUDGET_EXCEEDED" and len(t["embedding_factory"].requests) == before
    admin.set_shared_budget(t["alice"], dept, Decimal("0.021"), 1)
    call = t["billing"].prepare_query(t["alice"], query["id"], ["年假"])
    t["billing"].start(t["alice"], call)
    t["billing"].complete(
        t["alice"], call, {"vectors": [[1.0, 0.0, 0.0]], "charge": Decimal("0.001"), "input_tokens": 1}
    )
    assert assert_projection(t)[dept]["consumed"] == Decimal("0.002")


def test_unknown_embedding_keeps_every_scope_hold_until_distinct_reconciliation(knowledge_platform):
    t = knowledge_platform
    department(t, t["alice"])
    kb = base(t, hybrid=True)
    upload(t, kb, "年假规则")
    t["embedding_factory"].fail = True
    assert asyncio.run(ingest(t))["state"] == "failed"
    assert rows(t, s.knowledge_jobs)[0]["state"] == "recovery_required"
    call = rows(t, s.embedding_calls)[0]
    assert all(pool["reserved"] == Decimal("0.02") for pool in assert_projection(t).values())
    for _ in range(2):
        t["billing"].reconcile(t["bob"], call["id"], Decimal("0.003"), "synthetic-shared-embedding-receipt")
    assert all(pool["reserved"] == 0 and pool["consumed"] == Decimal("0.003") for pool in assert_projection(t).values())
    assert len(rows(t, s.embedding_ledger)) == 2


def test_embedding_not_sent_refund_and_rearm_are_projected(knowledge_platform):
    t = knowledge_platform
    dept = department(t, t["alice"])
    kb = base(t, hybrid=True)
    upload(t, kb, "年假")
    handle = t["jobs"].claim(t["org"], "budget-retry")
    call = t["billing"].prepare_job(handle, 0, ["年假"])
    assert assert_projection(t)[dept]["reserved"] == Decimal("0.02")
    t["billing"].uncertain(t["alice"], call)
    assert assert_projection(t)[dept]["reserved"] == 0
    t["knowledge"].admin.set_shared_budget(t["alice"], dept, Decimal("0.01"), 0)
    with pytest.raises(PlatformError) as error:
        t["billing"].prepare_job(handle, 0, ["年假"])
    assert error.value.code == "SHARED_BUDGET_EXCEEDED"
    t["knowledge"].admin.set_shared_budget(t["alice"], dept, Decimal("0.02"), 1)
    again = t["billing"].prepare_job(handle, 0, ["年假"])
    assert again["id"] == call["id"] and len(rows(t, s.budget_allocations)) == 2
    assert assert_projection(t)[dept]["reserved"] == Decimal("0.02")
    t["billing"].uncertain(t["alice"], again)
    assert assert_projection(t)[dept]["reserved"] == 0


def test_embedding_receipt_and_uncertainty_race_preserves_one_charge(knowledge_platform):
    t = knowledge_platform
    department(t, t["alice"])
    kb = base(t, hybrid=True)
    upload(t, kb, "Concurrent synthetic embedding")
    handle = t["jobs"].claim(t["org"], "budget-receipt-race")
    call = t["billing"].prepare_job(handle, 0, ["Synthetic text"])
    t["billing"].start(t["alice"], call, handle=handle)
    barrier = Barrier(2)

    def act(receipt):
        barrier.wait(timeout=5)
        if receipt:
            t["billing"].complete(
                t["alice"],
                call,
                {"vectors": [[1.0, 0.0, 0.0]], "charge": Decimal("0.001"), "input_tokens": 1},
                handle=handle,
            )
        else:
            t["billing"].uncertain(t["alice"], call)

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(act, (True, False)))
    assert all(pool["reserved"] == 0 and pool["consumed"] == Decimal("0.001") for pool in assert_projection(t).values())
    assert len([row for row in rows(t, s.embedding_ledger) if row["status"] == "actual"]) == 1


def test_shared_budget_http_authority_csrf_precision_and_scope(administration):
    t = administration
    auth = AuthService(t["db"], t["settings"])
    app = create_platform_app(t["settings"], database=t["db"])
    endpoint = "/api/v2/admin/shared-budgets"
    with TestClient(app, base_url=t["settings"].public_origin) as client:
        member_token, _ = auth.create_session(t["org"], t["settings"].oidc_issuer, str(t["alice"].user_id))
        client.cookies.set(t["settings"].session_cookie, member_token)
        assert client.get(endpoint).status_code == 403
        # A non-administrator must be refused the WRITE too, with a valid CSRF token present, so the
        # refusal is attributable to the role and not to the CSRF gate. Checking only GET would let a
        # role regression on the PUT routes pass unnoticed.
        member_headers = {"Origin": t["settings"].public_origin, "X-CSRF-Token": csrf_token(member_token)}
        for scope in ("/organization", "/departments/" + str(department(t, t["alice"]))):
            refused = client.put(
                endpoint + scope, json={"expected_revision": 0, "hard_limit": "1"}, headers=member_headers
            )
            assert refused.status_code == 403 and refused.json()["error"]["code"] == "ADMIN_FORBIDDEN"
        assert not rows(t, s.budget_pools), "a refused write must not create a pool"
        token, _ = auth.create_session(t["org"], t["settings"].oidc_issuer, str(t["org_admin"].user_id))
        client.cookies.set(t["settings"].session_cookie, token)
        assert client.get(endpoint).status_code == 200
        body = {"expected_revision": 0, "hard_limit": "0.100001"}
        assert client.put(endpoint + "/organization", json=body).status_code == 403
        headers = {"Origin": t["settings"].public_origin, "X-CSRF-Token": csrf_token(token)}
        result = client.put(endpoint + "/organization", json=body, headers=headers)
        assert result.status_code == 200 and result.json()["hard_limit"] == "0.100001"
        assert client.put(endpoint + "/organization", json=body, headers=headers).status_code == 409
        assert (
            client.put(
                endpoint + "/organization", json={**body, "hard_limit": "0.0000001"}, headers=headers
            ).status_code
            == 422
        )
        assert (
            client.put(
                endpoint + "/organization", json={**body, "owner_id": str(t["alice"].user_id)}, headers=headers
            ).status_code
            == 422
        )
        assert client.put(endpoint + "/departments/" + str(uuid4()), json=body, headers=headers).status_code == 404
        items = client.get(endpoint).json()["items"]
        # Positive projection check: any added key is a leak, and the permitted keys are all present.
        assert items and all(set(item) == POOL_VIEW_KEYS for item in items)
        assert result.json().keys() <= POOL_VIEW_KEYS


def test_pool_rls_and_immutable_binding_permissions(administration):
    t = administration
    run = create(t, t["alice"], private_session(t, t["alice"]))
    allocation = rows(t, s.budget_allocations)[0]
    with t["db"].transaction(t["outsider"]) as c:
        assert (
            c.execute(select(s.budget_allocations).where(s.budget_allocations.c.run_id == run["run_id"])).first()
            is None
        )
    with pytest.raises(DBAPIError):
        with t["db"].transaction(t["alice"]) as c:
            c.execute(
                update(s.budget_allocations).where(s.budget_allocations.c.id == allocation["id"]).values(run_id=uuid4())
            )
    with pytest.raises(DBAPIError):
        with t["db"].transaction(t["alice"]) as c:
            c.execute(s.budget_allocations.delete().where(s.budget_allocations.c.id == allocation["id"]))
    with pytest.raises(DBAPIError):
        with t["db"].transaction(t["alice"]) as c:
            c.execute(insert(s.budget_pools).values(org_id=t["outsider"].org_id, id=uuid4()))
    assert_projection(t)
