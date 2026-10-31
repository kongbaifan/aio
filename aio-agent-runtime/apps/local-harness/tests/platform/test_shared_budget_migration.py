"""Real v12 -> v13 migration, not a metadata-only test or a fake migration."""

from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
import secrets
from unittest.mock import patch
from uuid import uuid4

from alembic import command, op
from alembic.config import Config
from psycopg import sql
import pytest
from sqlalchemy import Insert, Select, Update, create_engine, func, insert, select, text, update

from app.auth.principal import Principal
from app.billing import budgets as shared_budgets
from app.db import schema as s
from app.db import schema_v12
from app.db import schema_v13 as v13  # 0013 binds to these exact Table objects
from app.db.engine import Database
from app.db.provisioning import provision_agent, provision_budget, provision_identity
from app.runtime.service import PlatformService
from app.observability import audit
from app.policy import kill_switches
from knowledge_fixtures import base, upload, knowledge_platform


@pytest.fixture
def legacy_budget_database(postgres, platform_settings, tmp_path, monkeypatch):
    # This fixture creates pre-v14 facts with the OLD writer, not the current audit schema.
    # The real v12 -> v13 migration and its original rows remain completely unmocked.
    def legacy_audit(c, p, action, resource_id, outcome, metadata=None, *, run_id=None, **context):
        c.execute(insert(schema_v12.audit).values(
            id=uuid4(), org_id=p.org_id, actor_id=p.user_id, service_actor_id=p.service_actor_id,
            action=action, resource_id=resource_id, outcome=outcome, run_id=run_id,
            metadata=metadata.model_dump(mode="json") if metadata is not None else {},
        ))

    monkeypatch.setattr(audit, "record", legacy_audit)
    # v12 has no kill switch table; the old authorization path had no switches to read.
    monkeypatch.setattr(kill_switches, "active", lambda connection, org_id: ())
    _, parent, _ = postgres
    name = "aio_budget_upgrade_" + secrets.token_hex(6)
    engine = database = None
    try:
        with parent.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            with c.connection.driver_connection.cursor() as cursor:
                cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        url = parent.url.set(database=name).render_as_string(hide_password=False)
        config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        config.attributes["database_url"] = url
        command.upgrade(config, "0012_skill_imports")
        engine, database = create_engine(url, hide_parameters=True), Database(url)
        org, alice, bob, dept = (uuid4() for _ in range(4))
        with engine.begin() as c:
            c.execute(
                insert(s.organizations).values(
                    id=org, name="Synthetic legacy accounting", allowed_classifications=["public", "internal"]
                )
            )
            for uid in (alice, bob):
                provision_identity(
                    c,
                    org_id=org,
                    user_id=uid,
                    issuer=platform_settings.oidc_issuer,
                    subject=str(uid),
                    display_name="Legacy fixture",
                    role="org_admin",
                )
                provision_budget(c, org_id=org, user_id=uid, hard_limit=Decimal("10"))
            c.execute(
                update(s.budgets)
                .where(s.budgets.c.org_id == org, s.budgets.c.owner_id == alice)
                .values(consumed=Decimal("0.04"))
            )
            c.execute(insert(s.departments).values(org_id=org, id=dept, name="Migration-time department"))
            c.execute(insert(s.department_memberships).values(org_id=org, department_id=dept, user_id=alice))
            agent = provision_agent(
                c,
                org_id=org,
                owner_id=alice,
                name="Legacy admission",
                version="1",
                instruction="Synthetic only",
                engine="test-fixture-only",
                manifest={"run_budget": "0.100000", "tools": []},
            )
        p, other = Principal(org, alice, 0), Principal(org, bob, 0)
        service = PlatformService(database, platform_settings)
        project = service.create_project(p, "Legacy project")["id"]
        session = service.create_session(p, project, agent, "Legacy task")["id"]
        # Only fixture admission acts as the OLD writer (v12 had no pool tables).
        # No migration behavior, underlying PG data, or migration assertions are mocked.
        with (
            patch.object(shared_budgets, "for_actor", return_value=[]),
            patch.object(shared_budgets, "check"),
            patch.object(shared_budgets, "reserve"),
        ):
            run = service.create_run(
                p,
                session,
                {
                    "message": "Synthetic pre-upgrade intent",
                    "agent_version_id": str(agent),
                    "expected_session_revision": 0,
                    "input_artifact_ids": [],
                    "mode": "single",
                },
                "legacy-budget-upgrade-key",
            )
        t = {
            "db": database,
            "admin": engine,
            "settings": platform_settings,
            "alice": p,
            "bob": other,
            "org": org,
            "agent": agent,
            "project": project,
            "session": session,
            "service": service,
            "dept": dept,
            "config": config,
            "run_id": run["run_id"],
        }
        t = knowledge_platform.__wrapped__(t, tmp_path)
        yield t
    finally:
        if database:
            database.dispose()
        if engine:
            engine.dispose()
        assert name.startswith("aio_budget_upgrade_") and parent.url.database == "aio_platform_test"
        with parent.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            with c.connection.driver_connection.cursor() as cursor:
                cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


def _written(statement):
    """Values a projection write is about to send, keyed by column name."""
    return statement.compile().params


def _reads_organization_ids(statement):
    """The backfill loop's own source read: ``select(s.organizations.c.id)``.

    Distinguished from ``_reconcile``'s independent ``COUNT(*)`` over the same table by its
    selected columns, so perturbing one leaves the other reading the real database.
    """
    if not isinstance(statement, Select):
        return False
    froms = statement.get_final_froms()
    return len(froms) == 1 and froms[0] is v13.organizations and [c.name for c in statement.selected_columns] == ["id"]


def _credits_pool(statement):
    """The id of the pool a ``reserved`` increment targets, or None."""
    if isinstance(statement, Update) and statement.table is v13.budget_pools:
        return _written(statement).get("id_1")
    return None


@contextmanager
def _perturbed_projection(rewrite):
    """Patch the migration's own bind so the projection it WRITES is partial or wrong.

    Alembic loads version files through ``spec_from_file_location``, so ``0013_shared_budgets``
    never enters ``sys.modules`` and cannot be reached by module name. ``alembic.op.get_bind`` is
    the single seam the migration uses to obtain its connection, so wrapping the returned
    connection perturbs the backfill's writes while ``_reconcile`` still runs unmodified and still
    reads the real PostgreSQL database over the real transaction. No assertion, no source table,
    and no part of ``_reconcile`` is mocked; only the rows the backfill emits are altered.

    ``rewrite(statement, pools)`` returns a replacement statement, or ``None`` to drop the write.
    ``pools`` accumulates the ids the backfill assigned, so a rewrite can target exactly the
    organization pool or a department pool. Writes are only ever dropped where the migration
    discards the result anyway.
    """
    real, pools = op.get_bind, {"organization": None, "departments": []}

    class _Bind:
        def __init__(self, connection):
            self._connection = connection

        def __getattr__(self, name):
            # DDL (``table.create``) and result handling stay on the real connection.
            return getattr(self._connection, name)

        def execute(self, statement, *args, **kwargs):
            if isinstance(statement, Insert) and statement.table is v13.budget_pools:
                written = _written(statement)
                if written.get("department_id") is None:
                    pools["organization"] = written["id"]
                else:
                    pools["departments"].append(written["id"])
            replacement = rewrite(statement, pools)
            if replacement is None:
                return None
            return self._connection.execute(replacement, *args, **kwargs)

    with patch.object(op, "get_bind", lambda: _Bind(real())):
        yield pools


def _second_organization(t):
    """A real second organization with no budgets, holds, or departments of its own.

    On its own this organization is projected cleanly: it contributes an organization pool with
    zero opening consumption and no allocations. The org-pool bijection and independent-COUNT
    tests each perturb one write around it and assert a DIFFERENT refusal, which is what proves
    the extra organization is not itself the cause of either refusal.
    """
    other = uuid4()
    with t["admin"].begin() as c:
        c.execute(
            insert(s.organizations).values(
                id=other, name="Synthetic unprojected tenant", allowed_classifications=["public"]
            )
        )
    return other


def _assert_refused_without_losing_facts(t, message):
    """A refusal must abort the whole upgrade and leave every original charge fact intact."""
    with pytest.raises(RuntimeError, match=message) as error:
        command.upgrade(t["config"], "0013_shared_budgets")
    assert "refusing" in str(error.value)
    with t["admin"].connect() as c:
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0012_skill_imports"
        for name in ("aio_budget_pools", "aio_budget_allocations"):
            assert c.execute(text("SELECT to_regclass(:name)"), {"name": name}).scalar_one() is None
        budgets = {row["owner_id"]: row for row in c.execute(select(s.budgets)).mappings()}
        assert budgets[t["alice"].user_id]["consumed"] == Decimal("0.04")
        assert budgets[t["alice"].user_id]["reserved"] == Decimal("0.1")
        assert budgets[t["bob"].user_id]["consumed"] == 0 and budgets[t["bob"].user_id]["reserved"] == 0
        reservation = c.execute(select(s.reservations)).mappings().one()
        assert reservation["amount"] == Decimal("0.1") and reservation["state"] == "reserved"
        assert reservation["run_id"] == t["run_id"]
        assert c.execute(select(s.runs.c.id)).scalar_one() == t["run_id"]
        assert c.execute(select(func.count()).select_from(s.departments)).scalar_one() == 1


def test_migration_refuses_a_projection_missing_one_organizations_pool(legacy_budget_database):
    """Invariant (a): one organization pool per organization, by identity not by count."""
    t = legacy_budget_database
    other = _second_organization(t)

    def rewrite(statement, pools):
        # Drop only the second organization's pool. It has no holds, so no allocation
        # references it and the omission cannot surface as a foreign key error instead.
        if isinstance(statement, Insert) and statement.table is v13.budget_pools:
            written = _written(statement)
            if written["org_id"] == other and written.get("department_id") is None:
                return None
        return statement

    with _perturbed_projection(rewrite):
        _assert_refused_without_losing_facts(t, "exactly one organization pool per organization")
    with t["admin"].connect() as c:
        assert c.execute(select(func.count()).select_from(s.organizations)).scalar_one() == 2


def test_migration_refuses_a_pool_count_that_disagrees_with_the_organization_count(legacy_budget_database):
    """Invariant (b): the independent COUNT, which is the only check a filtered source read cannot satisfy.

    Every other reconciliation compares the projection against totals the loop accumulated from
    its own reads, so a filtered read matches one empty set against another. Here the loop reads
    one organization out of two: the bijection check passes, and only the independent count bites.
    """
    t = legacy_budget_database
    other = _second_organization(t)

    def rewrite(statement, pools):
        # Filter the backfill's source read exactly the way row level security would, while
        # _reconcile's own COUNT(*) still sees the real table.
        if _reads_organization_ids(statement):
            return statement.where(v13.organizations.c.id != other)
        return statement

    with _perturbed_projection(rewrite):
        _assert_refused_without_losing_facts(t, "organization pools for 2 organizations")


@pytest.mark.parametrize("opening", ["understated", "overstated"])
def test_migration_refuses_an_opening_total_that_disagrees_with_recorded_personal_consumption(
    legacy_budget_database, opening
):
    """Invariant (c): opening_consumed must equal SUM(budgets.consumed), forgiving and duplicating alike."""
    t = legacy_budget_database

    def rewrite(statement, pools):
        if isinstance(statement, Insert) and statement.table is v13.budget_pools:
            written = _written(statement)
            if written.get("department_id") is None and written["opening_consumed"] > 0:
                # Both directions stay inside the pool's own amounts CHECK constraint, so the
                # refusal comes from _reconcile and not from PostgreSQL.
                if opening == "understated":
                    return statement.values(opening_consumed=Decimal(0))
                doubled = written["opening_consumed"] * 2
                return statement.values(consumed=doubled, opening_consumed=doubled)
        return statement

    with _perturbed_projection(rewrite):
        _assert_refused_without_losing_facts(t, "silently forgive or duplicate spend already charged")


def test_migration_refuses_an_outstanding_hold_left_without_an_organization_scope(legacy_budget_database):
    """Invariant (d): per-subject hold-to-allocation equality on the organization pool."""
    t = legacy_budget_database

    def rewrite(statement, pools):
        # Drop the organization-pool allocation only. The pool's reserved total is still
        # incremented, so the hold looks funded while no allocation scopes it: the failure has
        # to be caught by the per-subject equality, not by the reserved-sum comparison.
        if isinstance(statement, Insert) and statement.table is v13.budget_allocations:
            if _written(statement)["pool_id"] == pools["organization"]:
                return None
        return statement

    with _perturbed_projection(rewrite):
        _assert_refused_without_losing_facts(t, "leave an outstanding hold with no shared charge scope")


def test_migration_refuses_a_department_pool_that_no_allocation_supports(legacy_budget_database):
    """Invariant (e): a department pool with no allocation is an invented scope that would cap real spend."""
    t = legacy_budget_database

    def rewrite(statement, pools):
        if isinstance(statement, Insert) and statement.table is v13.budget_allocations:
            if _written(statement)["pool_id"] in pools["departments"]:
                return None
        # Drop the matching reserved increment as well, leaving reserved == 0 == the sum of the
        # (absent) scoped allocations. The department pool is then internally consistent and only
        # the no-allocation check can object, so this bites that check alone: a bare department
        # scope, capping real spend, that no existing charge fact supports.
        if _credits_pool(statement) in pools["departments"]:
            return None
        return statement

    with _perturbed_projection(rewrite):
        _assert_refused_without_losing_facts(t, "with no allocation")


def test_migration_refuses_fabricated_historical_departmental_consumption(legacy_budget_database):
    """Invariant (f): v12 recorded no departmental history, so a department pool must open at zero."""
    t = legacy_budget_database

    def rewrite(statement, pools):
        if isinstance(statement, Insert) and statement.table is v13.budget_pools:
            written = _written(statement)
            if written.get("department_id") is not None:
                # Attribute Alice's real personal spend to her department. Organization pools are
                # the only rows the opening-total check reads, so invariant (c) cannot cover this.
                return statement.values(consumed=Decimal("0.04"), opening_consumed=Decimal("0.04"))
        return statement

    with _perturbed_projection(rewrite):
        _assert_refused_without_losing_facts(t, "refusing to invent historical departmental attribution")


@pytest.mark.parametrize("state", ["prepared", "not_sent", "unknown"])
def test_migration_preserves_original_holds_and_does_not_fabricate_past_department_spend(legacy_budget_database, state):
    t = legacy_budget_database
    kb = base(t, hybrid=True)
    upload(t, kb, "Synthetic migration document")
    handle = t["jobs"].claim(t["org"], "migration-writer")
    with (
        patch.object(shared_budgets, "for_actor", return_value=[]),
        patch.object(shared_budgets, "check"),
        patch.object(shared_budgets, "reserve"),
        patch.object(shared_budgets, "lock_subject", return_value=[]),
        patch.object(shared_budgets, "change"),
    ):
        call = t["billing"].prepare_job(handle, 0, ["Synthetic text"])
        if state == "unknown":
            t["billing"].start(t["alice"], call, handle=handle)
        if state != "prepared":
            t["billing"].uncertain(t["alice"], call)
    command.upgrade(t["config"], "0013_shared_budgets")
    with t["admin"].connect() as c:
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0013_shared_budgets"
        pools = {row["department_id"]: row for row in c.execute(select(s.budget_pools)).mappings()}
        expected = Decimal("0.1") + (Decimal(0) if state == "not_sent" else Decimal("0.02"))
        assert pools[None]["reserved"] == pools[t["dept"]]["reserved"] == expected
        assert pools[None]["opening_consumed"] == pools[None]["consumed"] == Decimal("0.04")
        assert pools[t["dept"]]["opening_consumed"] == pools[t["dept"]]["consumed"] == 0
        allocations = c.execute(select(s.budget_allocations)).mappings().all()
        assert len(allocations) == 4 and all(row["origin"] == "migration_hold" for row in allocations)
        assert c.execute(select(s.runs.c.id)).scalar_one() == t["run_id"]
        assert c.execute(select(s.embedding_calls.c.id)).scalar_one() == call["id"]
        for name in ("aio_budget_pools", "aio_budget_allocations"):
            assert c.execute(
                text("SELECT relforcerowsecurity FROM pg_class WHERE relname=:name"), {"name": name}
            ).scalar_one()
    # Actual new writer releases the OLD Run, and a never-sent legacy embedding
    # can rearm its zero allocation rather than bypassing caps or losing its identity.
    t["service"].cancel_run(t["alice"], t["run_id"])
    if state == "not_sent":
        assert t["billing"].prepare_job(handle, 0, ["Synthetic text"])["id"] == call["id"]
    if state == "unknown":
        t["billing"].reconcile(t["bob"], call["id"], Decimal("0.003"), "legacy-synthetic-invoice")
    with t["admin"].connect() as c:
        pools = {row["department_id"]: row for row in c.execute(select(s.budget_pools)).mappings()}
        assert pools[None]["reserved"] == pools[t["dept"]]["reserved"] == (0 if state == "unknown" else Decimal("0.02"))
        assert pools[None]["consumed"] == Decimal("0.043" if state == "unknown" else "0.04")
        assert pools[t["dept"]]["consumed"] == (Decimal("0.003") if state == "unknown" else 0)


@pytest.mark.parametrize("corruption", ["unmatched_hold", "unsupported_currency"])
def test_migration_refuses_unreconciled_balances_without_dropping_original_facts(legacy_budget_database, corruption):
    t = legacy_budget_database
    with t["admin"].begin() as c:
        values = {"reserved": Decimal("0.11")} if corruption == "unmatched_hold" else {"currency": "EUR"}
        c.execute(
            update(s.budgets)
            .where(s.budgets.c.org_id == t["org"], s.budgets.c.owner_id == t["alice"].user_id)
            .values(**values)
        )
    with pytest.raises(RuntimeError, match="migration"):
        command.upgrade(t["config"], "0013_shared_budgets")
    with t["admin"].connect() as c:
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0012_skill_imports"
        assert c.execute(text("SELECT to_regclass('aio_budget_pools')")).scalar_one() is None
        assert c.execute(select(s.runs.c.id)).scalar_one() == t["run_id"]
        assert c.execute(select(s.reservations.c.amount)).scalar_one() == Decimal("0.1")


def test_migration_refuses_a_row_level_security_scoped_identity_instead_of_an_empty_projection(legacy_budget_database):
    """This is the only migration that reads existing rows, and it FORCE-RLS-protects its own tables first.

    A tenant-scoped migration identity therefore sees zero organizations and would commit an empty
    projection while reporting success. Prove the refusal, not the silent success.
    """
    t = legacy_budget_database
    role, password = "aio_rls_" + secrets.token_hex(5), secrets.token_urlsafe(40)
    url = t["admin"].url.set(username=role, password=password).render_as_string(hide_password=False)
    try:
        with t["admin"].connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            with c.connection.driver_connection.cursor() as cursor:
                # Same attributes provision_runtime_role uses; that helper cannot be reused here because
                # it grants on the v13 pool tables, which do not exist yet at 0012_skill_imports.
                cursor.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS").format(
                        sql.Identifier(role), sql.Literal(password)
                    )
                )
                # Deliberately generous DDL/DML privileges: the refusal under test must come from the
                # RLS exemption check, never from an unrelated missing grant.
                for statement in (
                    "GRANT ALL ON SCHEMA public TO {}",
                    "GRANT ALL ON ALL TABLES IN SCHEMA public TO {}",
                    "GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {}",
                ):
                    cursor.execute(sql.SQL(statement).format(sql.Identifier(role)))
        scoped = create_engine(url, hide_parameters=True)
        try:
            with scoped.connect() as c:
                attributes = (
                    c.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=CURRENT_USER"))
                    .mappings()
                    .one()
                )
                assert attributes["rolsuper"] is False and attributes["rolbypassrls"] is False
                assert not c.execute(
                    text("SELECT bool_or(rolsuper OR rolbypassrls) FROM pg_roles WHERE rolname=CURRENT_USER")
                ).scalar_one()
                # The defect's premise: FORCE RLS plus an unset aio.org_id hides every source fact,
                # so an unguarded backfill loop iterates nothing at all.
                assert c.execute(text("SELECT current_setting('aio.org_id', true)")).scalar_one() is None
                for table in (s.organizations, s.budgets, s.reservations, s.department_memberships):
                    assert c.execute(select(func.count()).select_from(table)).scalar_one() == 0
                assert c.execute(text("SELECT has_table_privilege(CURRENT_USER, 'aio_budgets', 'SELECT')")).scalar_one()
                assert c.execute(text("SELECT has_schema_privilege(CURRENT_USER, 'public', 'CREATE')")).scalar_one()
        finally:
            scoped.dispose()
        with t["admin"].connect() as c:
            assert c.execute(select(func.count()).select_from(s.organizations)).scalar_one() == 1
            assert c.execute(select(func.count()).select_from(s.reservations)).scalar_one() == 1
        config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        config.attributes["database_url"] = url
        try:
            command.upgrade(config, "0013_shared_budgets")
        except RuntimeError as error:
            assert "row level security" in str(error)
        else:
            with t["admin"].connect() as c:
                version = c.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                pools = c.execute(select(s.budget_pools)).mappings().all()
                allocations = c.execute(select(s.budget_allocations)).mappings().all()
            pytest.fail(
                f"Scoped migration identity reported success at {version} with {len(pools)} pools and "
                f"{len(allocations)} allocations: opening consumption 0.04 was recorded as zero and the "
                "outstanding 0.1 hold was left without any shared charge scope"
            )
        # A refusal must leave no partial state that would lose facts.
        with t["admin"].connect() as c:
            assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0012_skill_imports"
            for name in ("aio_budget_pools", "aio_budget_allocations"):
                assert c.execute(text("SELECT to_regclass(:name)"), {"name": name}).scalar_one() is None
            budgets = {row["owner_id"]: row for row in c.execute(select(s.budgets)).mappings()}
            assert budgets[t["alice"].user_id]["consumed"] == Decimal("0.04")
            assert budgets[t["alice"].user_id]["reserved"] == Decimal("0.1")
            assert budgets[t["bob"].user_id]["consumed"] == 0 and budgets[t["bob"].user_id]["reserved"] == 0
            reservation = c.execute(select(s.reservations)).mappings().one()
            assert reservation["amount"] == Decimal("0.1") and reservation["state"] == "reserved"
            assert reservation["run_id"] == t["run_id"]
            assert c.execute(select(s.runs.c.id)).scalar_one() == t["run_id"]
    finally:
        with t["admin"].connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            with c.connection.driver_connection.cursor() as cursor:
                assert role.startswith("aio_rls_")
                cursor.execute(sql.SQL("DROP OWNED BY {} CASCADE").format(sql.Identifier(role)))
                cursor.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))


def test_migration_projects_nonzero_opening_consumption_with_an_exempt_identity(legacy_budget_database):
    """Negative control for the guard: the same fixture data must produce a real, non-empty projection."""
    t = legacy_budget_database
    with t["admin"].connect() as c:
        assert c.execute(
            text("SELECT bool_or(rolsuper OR rolbypassrls) FROM pg_roles WHERE rolname=CURRENT_USER")
        ).scalar_one()
    command.upgrade(t["config"], "0013_shared_budgets")
    with t["admin"].connect() as c:
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0013_shared_budgets"
        pools = {row["department_id"]: row for row in c.execute(select(s.budget_pools)).mappings()}
        assert set(pools) == {None, t["dept"]}
        # An empty or zeroed projection can never satisfy a nonzero opening balance.
        assert pools[None]["opening_consumed"] == pools[None]["consumed"] == Decimal("0.04")
        assert pools[None]["opening_consumed"] > 0
        assert pools[None]["reserved"] == pools[t["dept"]]["reserved"] == Decimal("0.1")
        assert pools[t["dept"]]["opening_consumed"] == pools[t["dept"]]["consumed"] == 0
        allocations = c.execute(select(s.budget_allocations)).mappings().all()
        assert {row["pool_id"] for row in allocations} == {row["id"] for row in pools.values()}
        assert len(allocations) == 2
        assert all(row["origin"] == "migration_hold" and row["run_id"] == t["run_id"] for row in allocations)
        assert all(row["reserved"] == Decimal("0.1") and row["consumed"] == 0 for row in allocations)
