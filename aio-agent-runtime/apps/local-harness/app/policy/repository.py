"""授权 facts 只从本次事务和当前数据库状态读取，不信任请求体缓存。"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, exists, select
from sqlalchemy.engine import Connection
from sqlalchemy.exc import OperationalError

from ..auth.principal import Principal
from ..db import schema as s
from ..platform_errors import PlatformError
from .service import OWNER_ACTIONS, authorize
from .types import AuthorizationFacts, DecisionKind, Grant, Resource


def db_now(connection: Connection) -> datetime:
    from sqlalchemy import func

    return connection.execute(select(func.clock_timestamp())).scalar_one()


def _resource_lock_query(org_id: UUID, ids: list[UUID]):
    return (
        select(s.resources.c.id)
        .where(s.resources.c.org_id == org_id, s.resources.c.id.in_(ids))
        .order_by(s.resources.c.id)
    )


def _run_resource_query(org_id: UUID, run_id: UUID):
    return select(s.runs.c.id, s.runs.c.project_id, s.runs.c.session_id, s.runs.c.agent_version_id).where(
        s.runs.c.org_id == org_id, s.runs.c.id == run_id
    )


def lock_resource_rows(connection: Connection, org_id: UUID, ids: list[UUID]) -> None:
    """Canonical resource-row lock order, not an authorization decision.

    Service lifecycle receipts may need these locks after business access is revoked.
    Callers must establish their own verified scope and authorize mutations separately.
    """
    connection.execute(_resource_lock_query(org_id, ids).with_for_update()).all()


def lock_run_resources(connection: Connection, org_id: UUID, run_id: UUID) -> None:
    """Structural lifecycle prefix: organization -> immutable Run resource references.

    This neither grants business access nor takes the Run row lock. Callers must
    still verify their exact binding and acquire Run/lifecycle rows afterward.
    It deliberately remains usable after organization or membership revocation.
    """
    connection.execute(
        select(s.organizations.c.id).where(s.organizations.c.id == org_id).with_for_update(read=True)
    ).one()
    refs = connection.execute(_run_resource_query(org_id, run_id)).one()
    lock_resource_rows(connection, org_id, list(refs))


def try_lock_run_resources(connection: Connection, org_id: UUID, run_id: UUID) -> bool:
    """Atomic non-waiting prefix, not authority and not a claimed Run.

    NOWAIT prevents concurrent claimers splitting a multi-resource lock set.
    On busy/missing input the inner savepoint releases all prefix locks. After
    success, the queue must still roll back its OUTER candidate savepoint if
    Run/Job is skipped. Only PostgreSQL lock-not-available is a busy candidate;
    deadlocks, broken connections and all other errors propagate unchanged.
    """
    with connection.begin_nested() as prefix:
        try:
            organization = connection.execute(
                select(s.organizations.c.id)
                .where(s.organizations.c.id == org_id)
                .with_for_update(read=True, nowait=True)
            ).first()
            refs = connection.execute(_run_resource_query(org_id, run_id)).first() if organization else None
            if refs is None:
                prefix.rollback()
                return False
            locked = connection.execute(_resource_lock_query(org_id, list(refs)).with_for_update(nowait=True)).scalars()
            if set(locked) != set(refs):
                prefix.rollback()
                return False
        except OperationalError as error:
            if getattr(error.orig, "sqlstate", None) != "55P03":
                raise
            prefix.rollback()
            return False
        return True


def current_facts(connection: Connection, principal: Principal, *, lock: bool = False) -> AuthorizationFacts:
    org_q = select(s.organizations).where(s.organizations.c.id == principal.org_id)
    member_q = select(s.memberships).where(
        s.memberships.c.org_id == principal.org_id, s.memberships.c.user_id == principal.user_id
    )
    if lock:
        # Shared locks serialize revocation with this short authorization transaction.
        org_q, member_q = org_q.with_for_update(read=True), member_q.with_for_update(read=True)
    org = connection.execute(org_q).mappings().first()
    member = connection.execute(member_q).mappings().first()
    active = connection.execute(select(s.users.c.active).where(s.users.c.id == principal.user_id)).scalar_one_or_none()
    if org is None or member is None or not (org["active"] and member["active"] and active):
        raise PlatformError("AUTH_REQUIRED", "Identity is not active in this organization", 401)
    if member["revision"] != principal.membership_revision:
        raise PlatformError("IDENTITY_REVISION_CHANGED", "Identity permissions changed; authenticate again", 401)
    department_ids = (
        connection.execute(
            select(s.department_memberships.c.department_id)
            .join(
                s.departments,
                (s.departments.c.org_id == s.department_memberships.c.org_id)
                & (s.departments.c.id == s.department_memberships.c.department_id),
            )
            .where(
                s.department_memberships.c.org_id == principal.org_id,
                s.department_memberships.c.user_id == principal.user_id,
                s.departments.c.active.is_(True),
            )
        )
        .scalars()
        .all()
    )
    return AuthorizationFacts(
        org_id=principal.org_id,
        user_id=principal.user_id,
        membership_revision=member["revision"],
        policy_revision=org["policy_revision"],
        department_ids=frozenset(department_ids),
        allowed_classifications=frozenset(org["allowed_classifications"]),
        denied_actions=frozenset(org["denied_actions"]),
    )


def resource_from_row(row) -> Resource:
    return Resource(
        org_id=row["org_id"],
        id=row["id"],
        kind=row["kind"],
        owner_id=row["owner_id"],
        status=row["status"],
        revision=row["revision"],
        classification=row["classification"],
    )


def require_resource(
    connection: Connection,
    principal: Principal,
    resource_id: UUID,
    action: str,
    *,
    facts: AuthorizationFacts | None = None,
    lock: bool = False,
) -> Resource:
    facts = facts or current_facts(connection, principal)
    query = select(s.resources).where(s.resources.c.id == resource_id, s.resources.c.org_id == principal.org_id)
    if lock:
        query = query.with_for_update()
    row = connection.execute(query).mappings().first()
    if row is None:
        raise PlatformError("RESOURCE_NOT_FOUND", "Resource does not exist or is not accessible", 404)
    grants = tuple(
        Grant(
            org_id=g["org_id"],
            resource_id=g["resource_id"],
            subject_type=g["subject_type"],
            subject_id=g["subject_id"],
            action=g["action"],
            expires_at=g["expires_at"],
        )
        for g in connection.execute(
            select(s.grants).where(
                s.grants.c.org_id == principal.org_id,
                s.grants.c.resource_id == resource_id,
                s.grants.c.subject_id == principal.user_id,
                s.grants.c.action == action,
            )
        ).mappings()
    )
    group_grants = tuple(
        Grant(
            org_id=g["org_id"],
            resource_id=g["resource_id"],
            subject_type="department",
            subject_id=g["department_id"],
            action=g["action"],
            expires_at=g["expires_at"],
        )
        for g in connection.execute(
            select(s.department_grants).where(
                s.department_grants.c.org_id == principal.org_id,
                s.department_grants.c.resource_id == resource_id,
                s.department_grants.c.department_id.in_(facts.department_ids),
                s.department_grants.c.action == action,
            )
        ).mappings()
    )
    grants = grants + group_grants
    resource = resource_from_row(row)
    decision = authorize(principal, action, resource, facts, grants, now=db_now(connection))
    if decision.outcome != DecisionKind.ALLOW:
        raise PlatformError(decision.reason_code, "Resource does not exist or is not accessible", 404)
    return resource


def visible_resources(connection: Connection, principal: Principal, kind: str, action: str):
    facts = current_facts(connection, principal)
    if action in facts.denied_actions:
        raise PlatformError("POLICY_DENIED", "This action is disabled by organization policy", 403)
    grant = exists(
        select(s.grants.c.id).where(
            s.grants.c.org_id == principal.org_id,
            s.grants.c.resource_id == s.resources.c.id,
            s.grants.c.subject_type == "user",
            s.grants.c.subject_id == principal.user_id,
            s.grants.c.action == action,
            (s.grants.c.expires_at.is_(None) | (s.grants.c.expires_at > db_now(connection))),
        )
    )
    group_grant = exists(
        select(s.department_grants.c.id).where(
            s.department_grants.c.org_id == principal.org_id,
            s.department_grants.c.resource_id == s.resources.c.id,
            s.department_grants.c.department_id.in_(facts.department_ids),
            s.department_grants.c.action == action,
            (s.department_grants.c.expires_at.is_(None) | (s.department_grants.c.expires_at > db_now(connection))),
        )
    )
    owner = s.resources.c.owner_id == principal.user_id if action in OWNER_ACTIONS.get(kind, ()) else False
    return and_(
        s.resources.c.org_id == principal.org_id,
        s.resources.c.kind == kind,
        s.resources.c.status == "active",
        s.resources.c.classification.in_(facts.allowed_classifications),
        grant | group_grant | owner,
    )
