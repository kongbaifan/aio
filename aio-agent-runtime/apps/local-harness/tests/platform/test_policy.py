from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.auth.principal import Principal
from app.policy.service import authorize
from app.policy.types import AuthorizationFacts, DecisionKind, Grant, Resource


def scenario():
    org, alice, bob, rid = (uuid4() for _ in range(4))
    return (
        Principal(org, alice, 1),
        Resource(org, rid, "session", bob),
        AuthorizationFacts(org, alice, 1, 2),
        datetime.now(timezone.utc),
    )


def test_owner_is_not_admin_and_other_user_denied():
    principal, resource, facts, now = scenario()
    assert authorize(principal, "session.read", resource, facts, now=now).outcome == DecisionKind.DENY
    owned = replace(resource, owner_id=principal.user_id)
    assert authorize(principal, "session.read", owned, facts, now=now).outcome == DecisionKind.ALLOW
    assert authorize(principal, "support.read", owned, facts, now=now).outcome == DecisionKind.DENY
    assert authorize(principal, "secrets.read", owned, facts, now=now).outcome == DecisionKind.DENY


def test_grant_is_exact_current_resource_action_and_subject():
    p, r, f, now = scenario()
    grant = Grant(p.org_id, r.id, "user", p.user_id, "session.read", now + timedelta(seconds=5))
    assert authorize(p, "session.read", r, f, (grant,), now=now).outcome == DecisionKind.ALLOW
    for wrong in [
        replace(grant, org_id=uuid4()),
        replace(grant, resource_id=uuid4()),
        replace(grant, subject_id=uuid4()),
        replace(grant, expires_at=now),
        replace(grant, action="session.delete"),
    ]:
        assert authorize(p, "session.read", r, f, (wrong,), now=now).outcome == DecisionKind.DENY


def test_revocation_and_org_ceiling_override_owner_and_grants():
    p, r, f, now = scenario()
    r = replace(r, owner_id=p.user_id)
    for changed in [
        replace(f, org_active=False),
        replace(f, user_active=False),
        replace(f, membership_active=False),
        replace(f, membership_revision=2),
        replace(f, org_id=uuid4()),
        replace(f, denied_actions=frozenset({"session.read"})),
        replace(f, allowed_classifications=frozenset()),
    ]:
        assert authorize(p, "session.read", r, changed, now=now).outcome == DecisionKind.DENY
    assert authorize(p, "session.read", replace(r, status="disabled"), f, now=now).outcome == DecisionKind.DENY


def test_delegation_is_a_ceiling_not_permanent_permission():
    p, r, f, now = scenario()
    r = replace(r, owner_id=p.user_id)
    assert authorize(p, "session.read", r, f, now=now, delegated_actions=frozenset()).outcome == DecisionKind.DENY
    assert (
        authorize(
            p, "session.read", r, f, now=now, delegated_actions=frozenset({"session.read"}), requires_approval=True
        ).outcome
        == DecisionKind.APPROVAL_REQUIRED
    )
