"""Explicit operator-only provisioning, never called by API startup or user input."""

import re
from decimal import Decimal
from uuid import UUID, uuid4

from psycopg import sql
from sqlalchemy import insert

from ..runtime.actions import canonical_digest
from . import schema as s


def provision_runtime_role(connection, role: str, password: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,40}", role) or len(password) < 32:
        raise ValueError("A distinct bounded role name and strong password are required")
    # psycopg identifiers/literals safely quote administrative SQL; passwords are never printed.
    cursor = connection.connection.driver_connection.cursor()
    cursor.execute(
        sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS").format(
            sql.Identifier(role), sql.Literal(password)
        )
    )
    cursor.close()
    grant_runtime_access(connection, role)


def grant_runtime_access(connection, role: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,40}", role):
        raise ValueError("A bounded dedicated runtime role name is required")
    cursor = connection.connection.driver_connection.cursor()
    cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
    cursor.execute(sql.SQL("GRANT SELECT ON TABLE alembic_version TO {}").format(sql.Identifier(role)))
    append_only = {
        s.events.name,
        s.audit.name,
        s.ledger.name,
        s.checkpoints.name,
        s.manifest_snapshots.name,
        s.workspace_versions.name,
        s.embedding_ledger.name,
    }
    readonly = {
        s.users.name,
        s.organizations.name,
        s.memberships.name,
        s.agent_versions.name,
        s.tool_versions.name,
        s.model_configs.name,
        s.skill_versions.name,
        s.mcp_servers.name,
        s.embedding_models.name,
    }
    for table in s.metadata.tables.values():
        privileges = (
            "SELECT"
            if table.name in readonly
            else "SELECT, INSERT"
            if table.name in append_only
            else "SELECT, INSERT, UPDATE, DELETE"
        )
        cursor.execute(
            sql.SQL("GRANT {} ON TABLE {} TO {}").format(
                sql.SQL(privileges), sql.Identifier(table.name), sql.Identifier(role)
            )
        )
    # Refresh removes stale mutation privileges as well as granting the current minimum.
    for name in append_only:
        cursor.execute(
            sql.SQL("REVOKE UPDATE, DELETE ON {} FROM {}").format(sql.Identifier(name), sql.Identifier(role))
        )
        cursor.execute(
            sql.SQL("REVOKE UPDATE ({}) ON {} FROM {}").format(
                sql.SQL(", ").join(sql.Identifier(column.name) for column in s.metadata.tables[name].columns),
                sql.Identifier(name), sql.Identifier(role),
            )
        )
    # Financial bindings and outbox payloads are immutable even to platform administrators.
    for table, columns in (
        (s.budget_pools, "hard_limit, reserved, consumed, revision"),
        (s.budget_allocations, "reserved, consumed"),
        (s.outbox, "delivered_at, attempts, next_attempt_at, last_error_code, lease_owner, leased_until"),
    ):
        cursor.execute(
            sql.SQL("REVOKE UPDATE, DELETE ON {} FROM {}").format(sql.Identifier(table.name), sql.Identifier(role))
        )
        cursor.execute(
            sql.SQL("REVOKE UPDATE ({}) ON {} FROM {}").format(
                sql.SQL(", ").join(sql.Identifier(column.name) for column in table.columns),
                sql.Identifier(table.name), sql.Identifier(role),
            )
        )
        cursor.execute(
            sql.SQL("GRANT UPDATE ({}) ON {} TO {}").format(
                sql.SQL(columns), sql.Identifier(table.name), sql.Identifier(role)
            )
        )
    # PostgreSQL row-locking SELECT (FOR SHARE) requires UPDATE privilege on at least one column.
    # Grant only revision columns, not identity activation/roles or tenant policy contents.
    cursor.execute(sql.SQL("GRANT UPDATE (policy_revision) ON aio_organizations TO {}").format(sql.Identifier(role)))
    cursor.execute(sql.SQL("GRANT UPDATE (revision) ON aio_memberships TO {}").format(sql.Identifier(role)))
    # Browser administration is protected by the server's current-role checks. These grants do not grant users DB access.
    cursor.execute(
        sql.SQL(
            "GRANT INSERT ON aio_users, aio_memberships, aio_agent_versions, aio_tool_versions, aio_model_configs TO {}"
        ).format(sql.Identifier(role))
    )
    cursor.execute(
        sql.SQL("GRANT UPDATE (active, role, revision, display_name) ON aio_memberships TO {}").format(
            sql.Identifier(role)
        )
    )
    cursor.execute(
        sql.SQL(
            "GRANT UPDATE (policy_revision, allowed_classifications, denied_actions, storage_limit_bytes) ON aio_organizations TO {}"
        ).format(sql.Identifier(role))
    )
    for table in (s.agent_versions, s.tool_versions, s.model_configs):
        cursor.execute(
            sql.SQL("GRANT UPDATE (published) ON {} TO {}").format(sql.Identifier(table.name), sql.Identifier(role))
        )
    cursor.execute(sql.SQL("GRANT INSERT ON aio_skill_versions TO {}").format(sql.Identifier(role)))
    cursor.execute(
        sql.SQL(
            "GRANT UPDATE (state, revision, reviewer_id, review_note, validation_job_id, published_tools, published_at) ON aio_skill_versions TO {}"
        ).format(sql.Identifier(role))
    )
    cursor.execute(sql.SQL("GRANT INSERT ON aio_mcp_servers TO {}").format(sql.Identifier(role)))
    cursor.execute(sql.SQL("GRANT INSERT ON aio_embedding_models TO {}").format(sql.Identifier(role)))
    cursor.execute(
        sql.SQL(
            "GRANT UPDATE (state, revision, definition, digest, published_tools, discovery_id) ON aio_mcp_servers TO {}"
        ).format(sql.Identifier(role))
    )
    cursor.close()


def provision_identity(
    connection, *, org_id: UUID, user_id: UUID, issuer: str, subject: str, display_name: str, role: str = "member"
) -> None:
    connection.execute(insert(s.users).values(id=user_id, issuer=issuer, subject=subject, display_name=display_name))
    connection.execute(insert(s.memberships).values(org_id=org_id, user_id=user_id, role=role))


def provision_agent(
    connection, *, org_id: UUID, owner_id: UUID, name: str, version: str, engine: str, instruction: str, manifest: dict
) -> UUID:
    id = uuid4()
    connection.execute(
        insert(s.resources).values(org_id=org_id, id=id, kind="agent", owner_id=owner_id, classification="internal")
    )
    connection.execute(
        insert(s.agent_versions).values(
            org_id=org_id,
            id=id,
            name=name,
            version=version,
            engine=engine,
            instruction=instruction,
            manifest=manifest,
            digest=canonical_digest(
                "aio-agent-v1", {"instruction": instruction, "manifest": manifest, "engine": engine}
            ),
            published=True,
        )
    )
    return id


def provision_budget(connection, *, org_id: UUID, user_id: UUID, hard_limit: Decimal) -> UUID:
    if not hard_limit.is_finite() or hard_limit <= 0:
        raise ValueError("A positive finite budget is required")
    id = uuid4()
    connection.execute(
        insert(s.budgets).values(org_id=org_id, id=id, owner_id=user_id, currency="USD", hard_limit=hard_limit)
    )
    return id


def provision_tool(
    connection, *, org_id: UUID, owner_id: UUID, name: str, driver: str, risk: str, input_schema: dict, config: dict
) -> dict:
    from ..runtime.catalog import definition_digest, validate_schema
    from ..runtime.contracts import bounded_json

    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", name) or risk not in {"R0", "R1", "R2"}:
        raise ValueError("Tool name/risk is invalid")
    validate_schema(input_schema)
    bounded_json(config, 65536)
    id = uuid4()
    digest = definition_digest(name, driver, risk, input_schema, config)
    connection.execute(
        insert(s.resources).values(org_id=org_id, id=id, kind="tool", owner_id=owner_id, classification="internal")
    )
    connection.execute(
        insert(s.tool_versions).values(
            org_id=org_id,
            id=id,
            name=name,
            driver=driver,
            risk=risk,
            input_schema=input_schema,
            config=config,
            digest=digest,
            published=True,
        )
    )
    return {"id": str(id), "name": name, "driver": driver, "risk": risk, "digest": digest}


def provision_model(connection, *, org_id: UUID, owner_id: UUID, provider: str, model: str, config: dict) -> dict:
    from ..runtime.contracts import bounded_json

    bounded_json(config, 65536)
    id = uuid4()
    digest = canonical_digest("aio-model-definition-v1", {"provider": provider, "model": model, "config": config})
    connection.execute(
        insert(s.resources).values(org_id=org_id, id=id, kind="model", owner_id=owner_id, classification="internal")
    )
    connection.execute(
        insert(s.model_configs).values(
            org_id=org_id, id=id, provider=provider, model=model, config=config, digest=digest, published=True
        )
    )
    return {"id": str(id), "digest": digest}
