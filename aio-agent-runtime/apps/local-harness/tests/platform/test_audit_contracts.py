"""Closed audit schemas must reject content even when a caller forgets to redact it."""

import asyncio
from datetime import datetime, timezone
from typing import get_args
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import CheckConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.auth.principal import Principal
from app.db import schema_v13, schema_v14
from app.observability import audit
from app.observability import redaction as m
from app.platform_errors import PlatformError
from app.policy.service import KNOWN_ACTIONS

ID = uuid4()
DIGEST = "a" * 64
EXAMPLES = [
    (m.EmptyMetadata, {}),
    (m.MemberCreated, {"role": "member"}),
    (m.MemberUpdated, {"role": "auditor", "active": True}),
    (m.DepartmentMembership, {"user_id": ID}),
    (m.ResourceGrant, {"subject_type": "user", "subject_id": ID, "actions": ("project.read",)}),
    (m.GrantRevoked, {"grant_id": ID}),
    (m.BudgetLimit, {"owner_id": ID, "hard_limit": "10.000001", "currency": "USD"}),
    (m.SharedBudgetLimit, {"department_id": None, "hard_limit": None, "currency": "USD", "revision": 1}),
    (m.CredentialPrepared, {"binding_id": ID}),
    (m.CredentialActivated, {"credential_revision": 1}),
    (m.OAuthAuthorized, {"flow_id": ID}),
    (m.KnowledgeUpload, {"version_id": ID}),
    (m.KnowledgePublished, {"version_id": ID, "chunks": 3}),
    (m.ArchiveFinished, {"skill_id": ID}),
    (m.SkillValidation, {"job_id": ID, "reviewer_id": ID, "package_digest": DIGEST}),
    (m.SkillReviewed, {"validation_job_id": ID, "package_digest": DIGEST}),
    (m.ArtifactUploaded, {"bytes": 4}),
    (m.ToolPlanned, {"tool_version_id": ID, "action_digest": DIGEST}),
    (m.ToolDispatch, {"tool_version_id": ID, "action_digest": DIGEST, "dispatch_id": ID, "generation": 1}),
    (m.ToolResult, {"tool_version_id": ID, "action_digest": DIGEST, "dispatch_id": ID, "generation": 1,
                    "outcome_digest": DIGEST, "dispatch_outcome": "succeeded"}),
    (m.ApprovalDecided, {"invocation_id": ID, "requested_by": ID, "requires_different_actor": True,
                         "action_digest": DIGEST}),
    (m.RunReconciled, {"conclusion": "confirmed_success", "resolved_invocations": 1, "evidence_digest": DIGEST}),
    (m.AuditRead, {"scope": "organization", "row_count": 1, "limit": 10, "since": None, "until": None,
                   "before_created_at": None, "before_id": None}),
]


@pytest.mark.parametrize("model,values", EXAMPLES, ids=[model.__name__ for model, _ in EXAMPLES])
def test_audit_metadata_has_only_its_named_fields_and_rejects_content(model, values):
    assert set(model.model_fields) == set(values)
    assert model.model_json_schema()["additionalProperties"] is False
    assert model.model_validate(values)
    for name in ("prompt", "arguments", "result", "headers", "env", "exception", "file_content"):
        with pytest.raises(ValidationError):
            model.model_validate({**values, name: {"nested": "synthetic-secret-marker"}})


class CaptureConnection:
    def __init__(self, org):
        self.org, self.writes = org, []

    def execute(self, statement):
        if getattr(statement, "is_insert", False):
            self.writes.append(statement.compile().params)
        return self

    def scalar_one(self):
        return str(self.org)


@pytest.mark.parametrize("case", ["dict", "wrong_model", "unknown_action", "unknown_outcome", "mutated_instance"])
def test_writer_refuses_bypass_without_emitting_a_record(case):
    p = Principal(uuid4(), uuid4(), 0)
    c = CaptureConnection(p.org_id)
    metadata = m.MemberUpdated(active=True, role="member")
    action, outcome = "member.update", "updated"
    if case == "dict":
        metadata = {"active": True, "role": "member"}
    elif case == "wrong_model":
        metadata = m.EmptyMetadata()
    elif case == "unknown_action":
        action = "raw-provider-response-synthetic-secret-marker"
    elif case == "unknown_outcome":
        outcome = "synthetic-secret-marker"
    else:
        metadata = metadata.model_copy(update={"active": "synthetic-secret-marker"})
    with pytest.raises(PlatformError) as error:
        audit.record(c, p, action, p.user_id, outcome, metadata)
    assert error.value.code == "AUDIT_METADATA_INVALID"
    assert "synthetic-secret-marker" not in str(error.value)
    assert c.writes == []


@pytest.mark.parametrize("values", [
    {"owner_id": ID, "hard_limit": "1e3"}, {"owner_id": ID, "hard_limit": "NaN"},
    {"owner_id": ID, "hard_limit": "0.0000001"}, {"owner_id": ID, "hard_limit": "secret=10"},
])
def test_amount_fields_cannot_carry_free_text_or_inexact_amounts(values):
    with pytest.raises(ValidationError):
        m.BudgetLimit(**values)


def test_permission_fields_are_enumerated_in_the_schema():
    assert set(get_args(m.PermissionAction)) == KNOWN_ACTIONS
    assert set(m.ResourceGrant.model_json_schema()["properties"]["actions"]["items"]["enum"]) == KNOWN_ACTIONS
    with pytest.raises(ValidationError):
        m.ResourceGrant(subject_type="user", subject_id=ID, actions=("Authorization=synthetic-secret-marker",))


def test_trace_is_scoped_across_concurrent_tasks_and_cleared_on_failure():
    p = Principal(uuid4(), uuid4(), 0)

    async def write(trace):
        c = CaptureConnection(p.org_id)
        with audit.trace_scope(trace):
            await asyncio.sleep(0)
            audit.record(c, p, "project.create", uuid4(), "created")
        return c.writes[0]["trace_id"]

    async def both():
        return await asyncio.gather(write("a" * 32), write("b" * 32))

    assert asyncio.run(both()) == ["a" * 32, "b" * 32]
    with pytest.raises(RuntimeError), audit.trace_scope("c" * 32):
        raise RuntimeError("synthetic failure")
    c = CaptureConnection(p.org_id)
    audit.record(c, p, "project.create", uuid4(), "created")
    assert c.writes[0]["trace_id"] is None


@pytest.mark.parametrize("values", [
    {"before_id": ID}, {"before_created_at": datetime.now(timezone.utc)},
    {"since": datetime(2026, 1, 1)},
    {"since": datetime(2026, 1, 2, tzinfo=timezone.utc), "until": datetime(2026, 1, 1, tzinfo=timezone.utc)},
])
def test_audit_pagination_rejects_partial_cursors_and_ambiguous_time(values):
    with pytest.raises(ValidationError):
        m.AuditRead(row_count=0, limit=10, **values)


def test_v14_check_constraints_render_their_literals_instead_of_bind_parameters():
    # Regression: an unescaped ":v1" compiled to "'NULL'", rejecting every structured audit insert.
    ddl = str(CreateTable(schema_v14.audit).compile(dialect=postgresql.dialect()))
    assert "action || ':v1'" in ddl
    assert "NULL'" not in ddl
    for table in (schema_v14.audit, schema_v14.outbox):
        for constraint in table.constraints:
            if isinstance(constraint, CheckConstraint):
                assert not constraint.sqltext.compile(dialect=postgresql.dialect()).params


def test_v14_does_not_mutate_historical_metadata_in_memory():
    assert len(schema_v13.metadata.tables) == len(schema_v14.metadata.tables) == 61
    assert not set(schema_v14.AUDIT_COLUMNS) & set(schema_v13.audit.c.keys())
    assert not set(schema_v14.OUTBOX_COLUMNS) & set(schema_v13.outbox.c.keys())
    assert {fk.target_fullname for fk in schema_v14.audit.foreign_keys} == {"aio_organizations.id"}
