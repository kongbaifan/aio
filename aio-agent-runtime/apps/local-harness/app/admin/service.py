"""Organization administration is explicit, audited and separate from business-data access."""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..auth.principal import Principal
from ..connections.catalog import MCP_DRIVERS
from ..db import schema as s
from ..db.engine import Database
from ..db.provisioning import provision_agent, provision_budget, provision_model, provision_tool
from ..platform_errors import PlatformError
from ..platform_settings import PlatformSettings, DeploymentMode, validate_endpoint
from ..policy.repository import current_facts, db_now, require_resource
from ..policy.service import actions_for_kind, KNOWN_ACTIONS
from ..runtime.catalog import current_model, current_tool
from .contracts import AgentCreate, GrantCreate, MemberCreate, MemberUpdate, ModelCreate, ToolCreate


class AdminService:
    def __init__(self, database: Database, settings: PlatformSettings):
        self.db, self.settings = database, settings

    @staticmethod
    def role(c, p: Principal) -> str:
        current_facts(c, p)
        return c.execute(
            select(s.memberships.c.role).where(s.memberships.c.org_id == p.org_id, s.memberships.c.user_id == p.user_id)
        ).scalar_one()

    @contextmanager
    def transaction(self, p: Principal, *, write=False, roles=frozenset({"org_admin"})):
        with self.db.transaction(p) as c:
            # Serialize organization mutations before resource/membership locks, never upgrade a shared org lock later.
            if write:
                c.execute(select(s.organizations.c.id).where(s.organizations.c.id == p.org_id).with_for_update()).one()
            role = self.role(c, p)
            if role not in roles:
                raise PlatformError("ADMIN_FORBIDDEN", "This management action is not permitted", 403)
            yield c

    @staticmethod
    def audit(c, p: Principal, action: str, resource_id: UUID, outcome: str, metadata: dict | None = None):
        c.execute(
            insert(s.audit).values(
                id=uuid4(),
                org_id=p.org_id,
                actor_id=p.user_id,
                action=action,
                resource_id=resource_id,
                outcome=outcome,
                metadata=metadata or {},
            )
        )

    @staticmethod
    def bump_policy(c, org_id: UUID):
        c.execute(
            update(s.organizations)
            .where(s.organizations.c.id == org_id)
            .values(policy_revision=s.organizations.c.policy_revision + 1)
        )

    def me(self, p: Principal) -> dict:
        with self.db.transaction(p) as c:
            facts = current_facts(c, p)
            row = (
                c.execute(
                    select(
                        s.memberships.c.role,
                        s.memberships.c.display_name,
                        s.users.c.display_name.label("identity_name"),
                        s.organizations.c.name.label("org_name"),
                    )
                    .select_from(s.memberships)
                    .join(s.users, s.users.c.id == s.memberships.c.user_id)
                    .join(s.organizations, s.organizations.c.id == s.memberships.c.org_id)
                    .where(s.memberships.c.org_id == p.org_id, s.memberships.c.user_id == p.user_id)
                )
                .mappings()
                .one()
            )
            departments = (
                c.execute(
                    select(s.departments.c.id, s.departments.c.name, s.department_memberships.c.role)
                    .join(
                        s.department_memberships,
                        (s.department_memberships.c.org_id == s.departments.c.org_id)
                        & (s.department_memberships.c.department_id == s.departments.c.id),
                    )
                    .where(
                        s.departments.c.org_id == p.org_id,
                        s.department_memberships.c.user_id == p.user_id,
                        s.departments.c.active.is_(True),
                    )
                    .order_by(s.departments.c.name)
                )
                .mappings()
                .all()
            )
            return {
                "user_id": p.user_id,
                "org_id": p.org_id,
                "display_name": row["display_name"] or row["identity_name"],
                "organization_name": row["org_name"],
                "role": row["role"],
                "membership_revision": facts.membership_revision,
                "departments": [dict(d) for d in departments],
                "permissions": {
                    "organization_admin": row["role"] == "org_admin",
                    "operations": row["role"] in {"org_admin", "operator"},
                    "audit": row["role"] in {"org_admin", "auditor"},
                },
            }

    def directory(self, p: Principal) -> dict:
        with self.db.transaction(p) as c:
            current_facts(c, p)
            rows = (
                c.execute(
                    select(
                        s.memberships.c.user_id,
                        s.memberships.c.display_name,
                        s.users.c.display_name.label("identity_name"),
                    )
                    .join(s.users, s.users.c.id == s.memberships.c.user_id)
                    .where(
                        s.memberships.c.org_id == p.org_id, s.memberships.c.active.is_(True), s.users.c.active.is_(True)
                    )
                    .order_by(s.memberships.c.user_id)
                    .limit(500)
                )
                .mappings()
                .all()
            )
            departments = (
                c.execute(
                    select(s.departments.c.id, s.departments.c.name)
                    .where(s.departments.c.org_id == p.org_id, s.departments.c.active.is_(True))
                    .order_by(s.departments.c.name)
                    .limit(200)
                )
                .mappings()
                .all()
            )
            return {
                "members": [
                    {"user_id": r["user_id"], "display_name": r["display_name"] or r["identity_name"]} for r in rows
                ],
                "departments": [dict(d) for d in departments],
            }

    def members(self, p: Principal) -> list[dict]:
        with self.transaction(p) as c:
            rows = (
                c.execute(
                    select(
                        s.memberships.c.user_id,
                        s.memberships.c.role,
                        s.memberships.c.active,
                        s.memberships.c.revision,
                        s.memberships.c.display_name,
                        s.users.c.display_name.label("identity_name"),
                        s.users.c.subject,
                    )
                    .join(s.users, s.users.c.id == s.memberships.c.user_id)
                    .where(s.memberships.c.org_id == p.org_id)
                    .order_by(s.memberships.c.user_id)
                    .limit(500)
                )
                .mappings()
                .all()
            )
            return [{**dict(row), "display_name": row["display_name"] or row["identity_name"]} for row in rows]

    def create_member(self, p: Principal, body: MemberCreate) -> dict:
        with self.transaction(p, write=True) as c:
            user = (
                c.execute(
                    select(s.users).where(
                        s.users.c.issuer == self.settings.oidc_issuer, s.users.c.subject == body.subject
                    )
                )
                .mappings()
                .first()
            )
            if user is None:
                uid = uuid4()
                c.execute(
                    pg_insert(s.users)
                    .values(
                        id=uid, issuer=self.settings.oidc_issuer, subject=body.subject, display_name=body.display_name
                    )
                    .on_conflict_do_nothing(index_elements=["issuer", "subject"])
                )
                user = (
                    c.execute(
                        select(s.users).where(
                            s.users.c.issuer == self.settings.oidc_issuer, s.users.c.subject == body.subject
                        )
                    )
                    .mappings()
                    .one()
                )
            if not user["active"]:
                raise PlatformError(
                    "IDENTITY_DISABLED", "This identity is disabled by the trusted identity administrator", 403
                )
            existing = (
                c.execute(
                    select(s.memberships).where(
                        s.memberships.c.org_id == p.org_id, s.memberships.c.user_id == user["id"]
                    )
                )
                .mappings()
                .first()
            )
            if existing:
                raise PlatformError("MEMBER_EXISTS", "This identity is already registered in the organization", 409)
            c.execute(
                insert(s.memberships).values(
                    org_id=p.org_id, user_id=user["id"], role=body.role, display_name=body.display_name, active=True
                )
            )
            # Newly provisioned identities have no budget and no agent/tool access until explicitly granted.
            self.audit(c, p, "member.create", user["id"], "created", {"role": body.role})
            return {
                "user_id": user["id"],
                "display_name": body.display_name,
                "role": body.role,
                "active": True,
                "revision": 0,
            }

    def update_member(self, p: Principal, user_id: UUID, body: MemberUpdate) -> dict:
        with self.transaction(p, write=True) as c:
            row = (
                c.execute(
                    select(s.memberships)
                    .where(s.memberships.c.org_id == p.org_id, s.memberships.c.user_id == user_id)
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if row is None:
                raise PlatformError("RESOURCE_NOT_FOUND", "Member is not in this organization", 404)
            if row["revision"] != body.expected_revision:
                raise PlatformError("REVISION_CONFLICT", "Membership changed; refresh before saving", 409)
            if row["role"] == "org_admin" and row["active"] and (body.role != "org_admin" or not body.active):
                others = c.execute(
                    select(func.count())
                    .select_from(s.memberships)
                    .where(
                        s.memberships.c.org_id == p.org_id,
                        s.memberships.c.active.is_(True),
                        s.memberships.c.role == "org_admin",
                        s.memberships.c.user_id != user_id,
                    )
                ).scalar_one()
                if others == 0:
                    raise PlatformError(
                        "LAST_ADMIN_REQUIRED", "The final active organization administrator cannot be removed", 409
                    )
            revision = row["revision"] + 1
            c.execute(
                update(s.memberships)
                .where(s.memberships.c.org_id == p.org_id, s.memberships.c.user_id == user_id)
                .values(display_name=body.display_name, role=body.role, active=body.active, revision=revision)
            )
            if not body.active:
                c.execute(
                    update(s.auth_sessions)
                    .where(
                        s.auth_sessions.c.org_id == p.org_id,
                        s.auth_sessions.c.user_id == user_id,
                        s.auth_sessions.c.revoked_at.is_(None),
                    )
                    .values(revoked_at=db_now(c))
                )
            self.audit(c, p, "member.update", user_id, "updated", {"active": body.active, "role": body.role})
            return {
                "user_id": user_id,
                "display_name": body.display_name,
                "role": body.role,
                "active": body.active,
                "revision": revision,
            }

    def departments(self, p: Principal) -> list[dict]:
        with self.transaction(p) as c:
            rows = (
                c.execute(
                    select(s.departments)
                    .where(s.departments.c.org_id == p.org_id)
                    .order_by(s.departments.c.name)
                    .limit(200)
                )
                .mappings()
                .all()
            )
            result = []
            for row in rows:
                members = (
                    c.execute(
                        select(
                            s.department_memberships.c.user_id,
                            s.department_memberships.c.role,
                            s.memberships.c.display_name,
                            s.users.c.display_name.label("identity_name"),
                        )
                        .join(
                            s.memberships,
                            (s.memberships.c.org_id == s.department_memberships.c.org_id)
                            & (s.memberships.c.user_id == s.department_memberships.c.user_id),
                        )
                        .join(s.users, s.users.c.id == s.memberships.c.user_id)
                        .where(
                            s.department_memberships.c.org_id == p.org_id,
                            s.department_memberships.c.department_id == row["id"],
                        )
                    )
                    .mappings()
                    .all()
                )
                result.append(
                    {
                        **dict(row),
                        "members": [
                            {**dict(m), "display_name": m["display_name"] or m["identity_name"]} for m in members
                        ],
                    }
                )
            return result

    def create_department(self, p: Principal, name: str) -> dict:
        name = name.strip()
        if not name:
            raise PlatformError("INVALID_REQUEST", "Department name is required", 422)
        with self.transaction(p, write=True) as c:
            if c.execute(
                select(s.departments.c.id).where(s.departments.c.org_id == p.org_id, s.departments.c.name == name)
            ).first():
                raise PlatformError("DEPARTMENT_EXISTS", "Department name is already used", 409)
            id = uuid4()
            c.execute(insert(s.departments).values(org_id=p.org_id, id=id, name=name))
            self.audit(c, p, "department.create", id, "created")
            return {"id": id, "name": name, "active": True, "members": []}

    def set_department_member(self, p: Principal, department_id: UUID, user_id: UUID, role: str | None) -> dict:
        with self.transaction(p, write=True) as c:
            dept = (
                c.execute(
                    select(s.departments)
                    .where(
                        s.departments.c.org_id == p.org_id,
                        s.departments.c.id == department_id,
                        s.departments.c.active.is_(True),
                    )
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            member = (
                c.execute(
                    select(s.memberships)
                    .where(s.memberships.c.org_id == p.org_id, s.memberships.c.user_id == user_id)
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if dept is None or member is None:
                raise PlatformError("RESOURCE_NOT_FOUND", "Department or member is not accessible", 404)
            if role is None:
                c.execute(
                    delete(s.department_memberships).where(
                        s.department_memberships.c.org_id == p.org_id,
                        s.department_memberships.c.department_id == department_id,
                        s.department_memberships.c.user_id == user_id,
                    )
                )
            else:
                if role not in {"member", "manager"}:
                    raise PlatformError("INVALID_REQUEST", "Department role is invalid", 422)
                c.execute(
                    pg_insert(s.department_memberships)
                    .values(org_id=p.org_id, department_id=department_id, user_id=user_id, role=role)
                    .on_conflict_do_update(index_elements=["org_id", "department_id", "user_id"], set_={"role": role})
                )
            c.execute(
                update(s.memberships)
                .where(s.memberships.c.org_id == p.org_id, s.memberships.c.user_id == user_id)
                .values(revision=s.memberships.c.revision + 1)
            )
            self.audit(
                c,
                p,
                "department.membership",
                department_id,
                "removed" if role is None else "granted",
                {"user_id": str(user_id)},
            )
            return {"department_id": department_id, "user_id": user_id, "role": role}

    def set_department_active(self, p: Principal, department_id: UUID, active: bool) -> dict:
        with self.transaction(p, write=True) as c:
            row = (
                c.execute(
                    select(s.departments)
                    .where(s.departments.c.org_id == p.org_id, s.departments.c.id == department_id)
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if row is None:
                raise PlatformError("RESOURCE_NOT_FOUND", "Department does not exist in this organization", 404)
            c.execute(update(s.departments).where(s.departments.c.id == department_id).values(active=active))
            affected = select(s.department_memberships.c.user_id).where(
                s.department_memberships.c.org_id == p.org_id, s.department_memberships.c.department_id == department_id
            )
            c.execute(
                update(s.memberships)
                .where(s.memberships.c.org_id == p.org_id, s.memberships.c.user_id.in_(affected))
                .values(revision=s.memberships.c.revision + 1)
            )
            self.audit(c, p, "department.status", department_id, "active" if active else "disabled")
            return {"id": department_id, "active": active}

    def _manageable(self, c, p: Principal, resource_id: UUID):
        facts = current_facts(c, p)
        row = (
            c.execute(
                select(s.resources)
                .where(s.resources.c.org_id == p.org_id, s.resources.c.id == resource_id)
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if row is None:
            raise PlatformError("RESOURCE_NOT_FOUND", "Resource is not accessible", 404)
        role = self.role(c, p)
        if row["kind"] == "knowledge" and row["owner_id"] == p.user_id:
            require_resource(c, p, resource_id, "knowledge.update", facts=facts)
        elif row["kind"] == "document":
            from ..knowledge.catalog import current_document

            current_document(c, p, resource_id, write=True)
        elif row["kind"] in {
            "agent",
            "tool",
            "model",
            "skill",
            "knowledge",
            "connection",
            "mcp_server",
            "embedding_model",
        }:
            if role != "org_admin":
                raise PlatformError("ADMIN_FORBIDDEN", "Capability grants require organization administration", 403)
        elif row["kind"] == "project":
            require_resource(c, p, resource_id, "project.members.manage", facts=facts)
        elif row["kind"] == "artifact":
            if row["owner_id"] != p.user_id:
                raise PlatformError("RESOURCE_NOT_FOUND", "Private artifact is not manageable", 404)
            from ..workspaces.service import ArtifactService

            ArtifactService.require_artifact(c, p, resource_id)
        elif row["kind"] in {"run", "approval"}:
            raise PlatformError(
                "RESTRICTED_GRANT", "Run reconciliation and approval roles must use their dedicated policy", 403
            )
        else:
            raise PlatformError(
                "RESTRICTED_GRANT", "This private resource cannot be shared through generic grants", 403
            )
        return row

    def grants(self, p: Principal, resource_id: UUID) -> dict:
        with self.db.transaction(p) as c:
            row = self._manageable(c, p, resource_id)
            users = (
                c.execute(select(s.grants).where(s.grants.c.org_id == p.org_id, s.grants.c.resource_id == resource_id))
                .mappings()
                .all()
            )
            groups = (
                c.execute(
                    select(s.department_grants).where(
                        s.department_grants.c.org_id == p.org_id, s.department_grants.c.resource_id == resource_id
                    )
                )
                .mappings()
                .all()
            )
            return {
                "resource_id": resource_id,
                "kind": row["kind"],
                "revision": row["revision"],
                "available_actions": sorted(actions_for_kind(row["kind"])),
                "items": [
                    {
                        "id": g["id"],
                        "subject_type": "user",
                        "subject_id": g["subject_id"],
                        "action": g["action"],
                        "expires_at": g["expires_at"],
                    }
                    for g in users
                ]
                + [
                    {
                        "id": g["id"],
                        "subject_type": "department",
                        "subject_id": g["department_id"],
                        "action": g["action"],
                        "expires_at": g["expires_at"],
                    }
                    for g in groups
                ],
            }

    def set_grants(self, p: Principal, resource_id: UUID, body: GrantCreate) -> dict:
        with self.db.transaction(p) as c:
            c.execute(select(s.organizations.c.id).where(s.organizations.c.id == p.org_id).with_for_update()).one()
            row = self._manageable(c, p, resource_id)
            actions = set(body.actions)
            if row["kind"] == "connection":
                connection = (
                    c.execute(
                        select(s.mcp_connections).where(
                            s.mcp_connections.c.org_id == p.org_id, s.mcp_connections.c.id == resource_id
                        )
                    )
                    .mappings()
                    .first()
                )
                if (
                    connection
                    and connection["scope"] == "personal"
                    and (body.subject_type != "user" or body.subject_id != row["owner_id"])
                ):
                    raise PlatformError(
                        "PERSONAL_CREDENTIAL_SHARING_DENIED",
                        "Create an explicit department service identity instead of sharing a personal credential",
                        403,
                    )
            if not actions or not actions <= actions_for_kind(row["kind"]) or "artifact.share" in actions:
                raise PlatformError("GRANT_ACTION_DENIED", "Requested grant exceeds the resource action boundary", 403)
            org = c.execute(select(s.organizations).where(s.organizations.c.id == p.org_id)).mappings().one()
            if actions & set(org["denied_actions"]):
                raise PlatformError("ORGANIZATION_POLICY_DENIED", "Organization policy forbids this action", 403)
            if body.expires_at and body.expires_at <= db_now(c):
                raise PlatformError("GRANT_EXPIRED", "Grant expiry must be in the future", 422)
            if body.subject_type == "user":
                target = c.execute(
                    select(s.memberships.c.user_id).where(
                        s.memberships.c.org_id == p.org_id,
                        s.memberships.c.user_id == body.subject_id,
                        s.memberships.c.active.is_(True),
                    )
                ).first()
                table = s.grants
                values = {"subject_id": body.subject_id, "subject_type": "user"}
                keys = ["org_id", "resource_id", "subject_type", "subject_id", "action"]
            else:
                target = c.execute(
                    select(s.departments.c.id).where(
                        s.departments.c.org_id == p.org_id,
                        s.departments.c.id == body.subject_id,
                        s.departments.c.active.is_(True),
                    )
                ).first()
                table = s.department_grants
                values = {"department_id": body.subject_id}
                keys = ["org_id", "resource_id", "department_id", "action"]
            if target is None:
                raise PlatformError(
                    "RESOURCE_NOT_FOUND", "Grant recipient must be an active organization member or department", 404
                )
            resources = [(row, actions)]
            if body.include_dependencies:
                if row["kind"] != "agent" or "agent.use" not in actions:
                    raise PlatformError("INVALID_GRANT_BUNDLE", "Dependency grants only apply to Agent use", 422)
                agent = (
                    c.execute(
                        select(s.agent_versions).where(
                            s.agent_versions.c.org_id == p.org_id, s.agent_versions.c.id == resource_id
                        )
                    )
                    .mappings()
                    .one()
                )
                refs = [(UUID(agent["manifest"]["model"]["id"]), {"model.use", "model.read"})]
                refs.extend((UUID(t["id"]), {"tool.use", "tool.read"}) for t in agent["manifest"].get("tools", []))
                refs.extend((UUID(v["id"]), {"skill.use", "skill.read"}) for v in agent["manifest"].get("skills", []))
                refs.extend(
                    (UUID(v["id"]), {"mcp_server.use", "mcp_server.read"})
                    for v in agent["manifest"].get("mcp_servers", [])
                )
                refs.extend(
                    (UUID(v["id"]), {"knowledge.read", "knowledge.search"})
                    for v in agent["manifest"].get("knowledge", [])
                )
                refs.extend(
                    (UUID(v["id"]), {"embedding_model.read", "embedding_model.use"})
                    for v in agent["manifest"].get("embedding_models", [])
                )
                for rid, allowed in sorted(refs, key=lambda item: str(item[0])):
                    resources.append((self._manageable(c, p, rid), allowed))
            for resource, granted in resources:
                if granted & set(org["denied_actions"]):
                    raise PlatformError("ORGANIZATION_POLICY_DENIED", "Dependency grant exceeds policy", 403)
                for action in sorted(granted):
                    c.execute(
                        pg_insert(table)
                        .values(
                            id=uuid4(),
                            org_id=p.org_id,
                            resource_id=resource["id"],
                            action=action,
                            expires_at=body.expires_at,
                            **values,
                        )
                        .on_conflict_do_update(index_elements=keys, set_={"expires_at": body.expires_at})
                    )
                c.execute(
                    update(s.resources)
                    .where(s.resources.c.id == resource["id"])
                    .values(revision=s.resources.c.revision + 1)
                )
                self.audit(
                    c,
                    p,
                    "resource.grant",
                    resource["id"],
                    "granted",
                    {"subject_type": body.subject_type, "subject_id": str(body.subject_id), "actions": sorted(granted)},
                )
            return {"resource_id": resource_id, "granted_resources": len(resources), "revision": row["revision"] + 1}

    def remove_grant(self, p: Principal, resource_id: UUID, grant_id: UUID, subject_type: str) -> dict:
        with self.db.transaction(p) as c:
            c.execute(select(s.organizations.c.id).where(s.organizations.c.id == p.org_id).with_for_update()).one()
            row = self._manageable(c, p, resource_id)
            if subject_type not in {"user", "department"}:
                raise PlatformError("INVALID_REQUEST", "Unknown grant type", 422)
            table = s.grants if subject_type == "user" else s.department_grants
            c.execute(
                delete(table).where(
                    table.c.org_id == p.org_id, table.c.resource_id == resource_id, table.c.id == grant_id
                )
            )
            c.execute(
                update(s.resources).where(s.resources.c.id == resource_id).values(revision=s.resources.c.revision + 1)
            )
            self.audit(c, p, "resource.grant.revoke", resource_id, "revoked", {"grant_id": str(grant_id)})
            return {"resource_id": resource_id, "revision": row["revision"] + 1}

    def options(self, p: Principal) -> dict:
        with self.transaction(p):
            return {
                "model_allowed_origins": sorted(self.settings.model_allowed_origins),
                "model_secret_names": sorted(self.settings.model_secret_names),
                "sandbox_profiles": list(self.settings.sandbox_profiles),
                "supported_drivers": ["sandbox.python"],
                "connector_endpoints": list(self.settings.connector_profiles),
                "document_profiles": list(self.settings.document_profiles),
                "supported_engines": ["local-harness-v2"],
            }

    def models(self, p: Principal) -> list[dict]:
        with self.transaction(p) as c:
            rows = (
                c.execute(
                    select(s.model_configs, s.resources.c.status, s.resources.c.revision)
                    .join(
                        s.resources,
                        (s.resources.c.id == s.model_configs.c.id) & (s.resources.c.org_id == s.model_configs.c.org_id),
                    )
                    .where(s.model_configs.c.org_id == p.org_id)
                    .order_by(s.model_configs.c.created_at.desc())
                    .limit(200)
                )
                .mappings()
                .all()
            )
            safe_keys = {
                "name",
                "endpoint",
                "secret_env",
                "max_output_tokens",
                "max_call_charge",
                "input_price_per_million",
                "output_price_per_million",
                "max_tokens_field",
                "currency",
            }
            return [
                {
                    **{k: row[k] for k in ("id", "provider", "model", "digest", "published", "status", "revision")},
                    "config": {k: v for k, v in row["config"].items() if k in safe_keys},
                }
                for row in rows
            ]

    def create_model(self, p: Principal, body: ModelCreate) -> dict:
        from urllib.parse import urlsplit

        endpoint = validate_endpoint(
            body.endpoint, "model endpoint", production=self.settings.mode is DeploymentMode.PRODUCTION
        )
        parsed = urlsplit(endpoint)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self.settings.model_allowed_origins or body.secret_env not in self.settings.model_secret_names:
            raise PlatformError(
                "MODEL_CONFIGURATION_DENIED",
                "Endpoint and credential reference must be allowed by the deployment operator",
                403,
            )
        if not parsed.path.rstrip("/").endswith("/chat/completions"):
            raise PlatformError(
                "MODEL_CONFIGURATION_INVALID", "A complete approved chat-completions endpoint is required", 422
            )
        config = {
            "name": body.name,
            "endpoint": endpoint,
            "secret_env": body.secret_env,
            "max_output_tokens": body.max_output_tokens,
            "max_call_charge": format(body.max_call_charge, "f"),
            "input_price_per_million": format(body.input_price_per_million, "f"),
            "output_price_per_million": format(body.output_price_per_million, "f"),
            "max_tokens_field": body.max_tokens_field,
            "currency": "USD",
        }
        with self.transaction(p, write=True) as c:
            model = provision_model(
                c, org_id=p.org_id, owner_id=p.user_id, provider=body.provider, model=body.model, config=config
            )
            self.audit(c, p, "model.version.create", UUID(model["id"]), "published")
            return model

    def tools(self, p: Principal) -> list[dict]:
        with self.transaction(p) as c:
            rows = (
                c.execute(
                    select(s.tool_versions, s.resources.c.status, s.resources.c.revision)
                    .join(
                        s.resources,
                        (s.resources.c.id == s.tool_versions.c.id) & (s.resources.c.org_id == s.tool_versions.c.org_id),
                    )
                    .where(s.tool_versions.c.org_id == p.org_id)
                    .order_by(s.tool_versions.c.created_at.desc())
                    .limit(200)
                )
                .mappings()
                .all()
            )
            safe_keys = {
                "description",
                "sandbox_profile",
                "image_digest",
                "network_profile_id",
                "timeout_seconds",
                "resource_scope",
            }
            return [
                {
                    **{
                        k: row[k]
                        for k in (
                            "id",
                            "name",
                            "driver",
                            "risk",
                            "digest",
                            "published",
                            "status",
                            "revision",
                            "input_schema",
                        )
                    },
                    "config": {k: v for k, v in row["config"].items() if k in safe_keys},
                }
                for row in rows
            ]

    def create_tool(self, p: Principal, body: ToolCreate) -> dict:
        profiles = {item["id"]: item for item in self.settings.sandbox_profiles}
        profile = profiles.get(body.sandbox_profile)
        if profile is None or body.timeout_seconds > profile["max_timeout_seconds"]:
            raise PlatformError(
                "SANDBOX_PROFILE_DENIED",
                "The deployment operator has not approved this execution profile or timeout",
                403,
            )
        schema = {
            "type": "object",
            "properties": {"code": {"type": "string", "minLength": 1, "maxLength": 65536}},
            "required": ["code"],
            "additionalProperties": False,
        }
        config = {
            "description": body.description,
            "sandbox_profile": body.sandbox_profile,
            "image_digest": profile["image_digest"],
            "network_profile_id": "none",
            "timeout_seconds": body.timeout_seconds,
        }
        if profile.get("runtime"):
            config["runtime_manifest_digest"] = profile["runtime"]["manifest_digest"]
        with self.transaction(p, write=True) as c:
            tool = provision_tool(
                c,
                org_id=p.org_id,
                owner_id=p.user_id,
                name=body.name,
                driver="sandbox.python",
                risk="R1",
                input_schema=schema,
                config=config,
            )
            self.audit(c, p, "tool.version.create", UUID(tool["id"]), "published")
            return tool

    def agents(self, p: Principal) -> list[dict]:
        with self.transaction(p) as c:
            rows = (
                c.execute(
                    select(s.agent_versions, s.resources.c.status, s.resources.c.revision)
                    .join(
                        s.resources,
                        (s.resources.c.id == s.agent_versions.c.id)
                        & (s.resources.c.org_id == s.agent_versions.c.org_id),
                    )
                    .where(s.agent_versions.c.org_id == p.org_id)
                    .order_by(s.agent_versions.c.created_at.desc())
                    .limit(200)
                )
                .mappings()
                .all()
            )
            return [dict(row) for row in rows]

    def create_agent(self, p: Principal, body: AgentCreate) -> dict:
        if len(set(body.tool_ids)) != len(body.tool_ids) or len(set(body.skill_ids)) != len(body.skill_ids):
            raise PlatformError("INVALID_REQUEST", "Tool references must be unique", 422)
        if len(body.instruction.encode("utf-8")) > 65536:
            raise PlatformError("PAYLOAD_TOO_LARGE", "Agent instructions exceed the byte limit", 413)
        with self.transaction(p, write=True) as c:
            model = (
                c.execute(
                    select(s.model_configs).where(
                        s.model_configs.c.org_id == p.org_id, s.model_configs.c.id == body.model_id
                    )
                )
                .mappings()
                .first()
            )
            if model is None:
                raise PlatformError("RESOURCE_NOT_FOUND", "Model is not available in this organization", 404)
            current_model(c, p, body.model_id, model["digest"])
            model_bound = Decimal(str(model["config"].get("max_call_charge", "0")))
            if not model_bound.is_finite() or model_bound <= 0 or body.run_budget < model_bound:
                raise PlatformError(
                    "AGENT_BUDGET_INVALID", "Run budget must cover at least one approved model call", 422
                )
            tools = []
            names = set()
            compute_profiles = set()
            from ..skills.catalog import current_skill

            skills = {id: current_skill(c, p, id) for id in body.skill_ids}
            from ..connections.catalog import current_server

            mcp_servers = {id: current_server(c, p, id) for id in body.mcp_server_ids}
            from ..knowledge.catalog import current_knowledge, current_embedding

            knowledge = {id: current_knowledge(c, p, id) for id in body.knowledge_ids}
            tool_ids = list(
                dict.fromkeys(
                    [
                        *body.tool_ids,
                        *(UUID(t["id"]) for skill in skills.values() for t in skill["published_tools"]),
                        *(UUID(t["id"]) for server in mcp_servers.values() for t in server["published_tools"]),
                        *(kb["tool_id"] for kb in knowledge.values()),
                    ]
                )
            )
            if len(tool_ids) > 64:
                raise PlatformError("TOOL_LIMIT_EXCEEDED", "Selected capabilities exceed the tool bound", 422)
            for id in tool_ids:
                t = (
                    c.execute(
                        select(s.tool_versions).where(s.tool_versions.c.org_id == p.org_id, s.tool_versions.c.id == id)
                    )
                    .mappings()
                    .first()
                )
                if t is None:
                    raise PlatformError("RESOURCE_NOT_FOUND", "Tool is not available in this organization", 404)
                entry = {key: t[key] for key in ("name", "driver", "risk", "digest")}
                entry["id"] = str(id)
                current_tool(c, p, id, entry)
                if t["driver"] in {"sandbox.python", "skill.python"}:
                    compute_profiles.add((t["config"].get("sandbox_profile"), t["config"].get("image_digest")))
                if t["driver"] in {"skill.python", "skill.read"}:
                    sid = UUID(t["config"]["skill_id"])
                    skills[sid] = current_skill(c, p, sid, t["config"]["skill_digest"])
                if t["driver"] in MCP_DRIVERS:
                    sid = UUID(t["config"]["server_id"])
                    mcp_servers[sid] = current_server(c, p, sid, t["config"]["server_digest"])
                if t["driver"] == "knowledge.search":
                    kid = UUID(t["config"]["knowledge_id"])
                    knowledge[kid] = current_knowledge(c, p, kid)
                if t["name"] in names:
                    raise PlatformError("TOOL_ALIAS_CONFLICT", "Two selected tool versions have the same alias", 422)
                names.add(t["name"])
                tools.append(entry)
            if len(compute_profiles) > 1:
                raise PlatformError(
                    "AGENT_RUNTIME_CONFLICT",
                    "This Run has one compute workspace; selected tools must use the same fixed runtime profile",
                    422,
                )
            manifest = {
                "model": {"id": str(body.model_id), "digest": model["digest"]},
                "tools": tools,
                "skills": [{"id": str(id), "digest": skill["digest"]} for id, skill in skills.items()],
                "mcp_servers": [{"id": str(id), "digest": server["digest"]} for id, server in mcp_servers.items()],
                "knowledge": [{"id": str(id)} for id in knowledge],
                "embedding_models": [
                    {"id": str(id), "digest": current_embedding(c, p, id)["digest"]}
                    for id in sorted(
                        {kb["embedding_model_id"] for kb in knowledge.values() if kb["embedding_model_id"]}, key=str
                    )
                ],
                "run_budget": format(body.run_budget, "f"),
                "max_rounds": body.max_rounds,
            }
            if body.team:
                if body.run_budget < model_bound * (body.team.max_steps + 2):
                    raise PlatformError(
                        "AGENT_BUDGET_INVALID", "Team budget must cover planning, each step and synthesis", 422
                    )
                manifest["team"] = body.team.model_dump(mode="json")
            id = provision_agent(
                c,
                org_id=p.org_id,
                owner_id=p.user_id,
                name=body.name,
                version=body.version,
                engine="local-harness-v2",
                instruction=body.instruction,
                manifest=manifest,
            )
            self.audit(c, p, "agent.version.create", id, "published")
            return {
                "id": id,
                "name": body.name,
                "version": body.version,
                "manifest": manifest,
                "revision": 0,
                "status": "active",
            }

    def set_status(self, p: Principal, id: UUID, status: str, expected_revision: int) -> dict:
        with self.db.transaction(p) as c:
            c.execute(select(s.organizations.c.id).where(s.organizations.c.id == p.org_id).with_for_update()).one()
            resource = self._manageable(c, p, id)
            if resource["revision"] != expected_revision:
                raise PlatformError("REVISION_CONFLICT", "Resource changed; refresh before saving", 409)
            if status not in {"active", "disabled"}:
                raise PlatformError("INVALID_REQUEST", "Unknown resource state", 422)
            c.execute(
                update(s.resources)
                .where(s.resources.c.id == id, s.resources.c.org_id == p.org_id)
                .values(status=status, revision=resource["revision"] + 1)
            )
            self.audit(c, p, "resource.status", id, status)
            return {"id": id, "status": status, "revision": resource["revision"] + 1}

    @staticmethod
    def _pool_view(row, name, department_id):
        reserved, consumed = (row["reserved"], row["consumed"]) if row else (Decimal(0), Decimal(0))
        limit = row["hard_limit"] if row else None
        return {
            "id": row["id"] if row else None,
            "scope": "department" if department_id else "organization",
            "department_id": department_id,
            "display_name": name,
            "currency": "USD",
            "hard_limit": str(limit) if limit is not None else None,
            "reserved": str(reserved),
            "consumed": str(consumed),
            "remaining": str(max(Decimal(0), limit - reserved - consumed)) if limit is not None else None,
            "warning": limit is not None and reserved + consumed >= limit * Decimal("0.8"),
            "exhausted": limit is not None and reserved + consumed >= limit,
            "revision": row["revision"] if row else 0,
            "created_at": row["created_at"] if row else None,
            "opening_consumed": str(row["opening_consumed"]) if row else "0",
        }

    def shared_budgets(self, p: Principal) -> list[dict]:
        with self.transaction(p) as c:
            pools = {
                row["department_id"]: row
                for row in c.execute(select(s.budget_pools).where(s.budget_pools.c.org_id == p.org_id)).mappings()
            }
            departments = c.execute(
                select(s.departments.c.id, s.departments.c.name)
                .where(s.departments.c.org_id == p.org_id)
                .order_by(s.departments.c.name, s.departments.c.id)
            ).mappings()
            return [
                self._pool_view(pools.get(None), "组织总额", None),
                *[self._pool_view(pools.get(row["id"]), row["name"], row["id"]) for row in departments],
            ]

    def set_shared_budget(
        self, p: Principal, department_id: UUID | None, limit: Decimal | None, expected_revision: int
    ) -> dict:
        from ..billing import budgets as shared_budgets

        if limit is not None and (
            not limit.is_finite() or limit < 0 or limit > 1000000 or limit.as_tuple().exponent < -6
        ):
            raise PlatformError("INVALID_REQUEST", "Budget requires a finite amount with at most six decimals", 422)
        with self.transaction(p, write=True) as c:
            name = "组织总额"
            if department_id:
                name = c.execute(
                    select(s.departments.c.name).where(
                        s.departments.c.org_id == p.org_id, s.departments.c.id == department_id
                    )
                ).scalar_one_or_none()
                if name is None:
                    raise PlatformError("RESOURCE_NOT_FOUND", "Department is not in this organization", 404)
            pools = shared_budgets.ensure(c, p.org_id, [department_id] if department_id else [])
            row = next(pool for pool in pools if pool["department_id"] == department_id)
            if row["revision"] != expected_revision:
                raise PlatformError("REVISION_CONFLICT", "Budget configuration changed; refresh before editing", 409)
            if limit is not None and limit < row["reserved"] + row["consumed"]:
                raise PlatformError(
                    "BUDGET_BELOW_COMMITTED", "Budget cannot be reduced below consumed and reserved amounts", 409
                )
            c.execute(
                update(s.budget_pools)
                .where(s.budget_pools.c.org_id == p.org_id, s.budget_pools.c.id == row["id"])
                .values(hard_limit=limit, revision=expected_revision + 1)
            )
            self.audit(
                c,
                p,
                "budget.shared_limit",
                row["id"],
                "updated",
                {
                    "department_id": str(department_id) if department_id else None,
                    "hard_limit": str(limit) if limit is not None else None,
                    "currency": "USD",
                    "revision": expected_revision + 1,
                },
            )
            return self._pool_view(
                {**dict(row), "hard_limit": limit, "revision": expected_revision + 1}, name, department_id
            )

    def budgets(self, p: Principal) -> list[dict]:
        with self.transaction(p) as c:
            rows = (
                c.execute(
                    select(s.budgets, s.memberships.c.display_name, s.users.c.display_name.label("identity_name"))
                    .join(
                        s.memberships,
                        (s.memberships.c.org_id == s.budgets.c.org_id)
                        & (s.memberships.c.user_id == s.budgets.c.owner_id),
                    )
                    .join(s.users, s.users.c.id == s.memberships.c.user_id)
                    .where(s.budgets.c.org_id == p.org_id)
                    .order_by(s.budgets.c.owner_id)
                    .limit(500)
                )
                .mappings()
                .all()
            )
            return [{**dict(row), "display_name": row["display_name"] or row["identity_name"]} for row in rows]

    def set_budget(self, p: Principal, user_id: UUID, limit: Decimal) -> dict:
        with self.transaction(p, write=True) as c:
            member = (
                c.execute(
                    select(s.memberships).where(s.memberships.c.org_id == p.org_id, s.memberships.c.user_id == user_id)
                )
                .mappings()
                .first()
            )
            if member is None:
                raise PlatformError("RESOURCE_NOT_FOUND", "Budget owner is not an organization member", 404)
            row = (
                c.execute(
                    select(s.budgets)
                    .where(
                        s.budgets.c.org_id == p.org_id, s.budgets.c.owner_id == user_id, s.budgets.c.currency == "USD"
                    )
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if not limit.is_finite() or limit <= 0:
                raise PlatformError("INVALID_REQUEST", "Budget limit must be a positive finite amount", 422)
            if row:
                if limit < row["reserved"] + row["consumed"]:
                    raise PlatformError(
                        "BUDGET_BELOW_COMMITTED", "Budget cannot be reduced below consumed and reserved amounts", 409
                    )
                c.execute(update(s.budgets).where(s.budgets.c.id == row["id"]).values(hard_limit=limit))
                id = row["id"]
            else:
                id = provision_budget(c, org_id=p.org_id, user_id=user_id, hard_limit=limit)
            self.audit(
                c,
                p,
                "budget.limit",
                id,
                "updated",
                {"owner_id": str(user_id), "hard_limit": str(limit), "currency": "USD"},
            )
            return {"id": id, "owner_id": user_id, "hard_limit": str(limit), "currency": "USD"}

    def own_budget(self, p: Principal) -> dict:
        with self.db.transaction(p) as c:
            current_facts(c, p)
            row = (
                c.execute(
                    select(s.budgets).where(
                        s.budgets.c.org_id == p.org_id, s.budgets.c.owner_id == p.user_id, s.budgets.c.currency == "USD"
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                return {"configured": False, "currency": "USD", "hard_limit": "0", "reserved": "0", "consumed": "0"}
            unknown = c.execute(
                select(func.count())
                .select_from(s.model_calls)
                .join(s.runs, (s.runs.c.org_id == s.model_calls.c.org_id) & (s.runs.c.id == s.model_calls.c.run_id))
                .where(
                    s.runs.c.org_id == p.org_id,
                    s.runs.c.actor_id == p.user_id,
                    s.model_calls.c.actual_charge.is_(None),
                    s.model_calls.c.state.in_(["started", "succeeded", "unknown"]),
                )
            ).scalar_one()
            return {
                "configured": True,
                **{key: str(row[key]) for key in ("hard_limit", "reserved", "consumed", "currency")},
                "unknown_calls": unknown
                + c.execute(
                    select(func.count())
                    .select_from(s.embedding_calls)
                    .where(
                        s.embedding_calls.c.org_id == p.org_id,
                        s.embedding_calls.c.requested_by == p.user_id,
                        s.embedding_calls.c.actual_charge.is_(None),
                        s.embedding_calls.c.state.in_(["started", "unknown", "succeeded"]),
                    )
                ).scalar_one(),
            }

    def audit_events(self, p: Principal, limit: int = 100) -> list[dict]:
        with self.transaction(p, roles=frozenset({"org_admin", "auditor"})) as c:
            rows = (
                c.execute(
                    select(
                        s.audit.c.id,
                        s.audit.c.actor_id,
                        s.audit.c.action,
                        s.audit.c.resource_id,
                        s.audit.c.run_id,
                        s.audit.c.outcome,
                        s.audit.c.created_at,
                    )
                    .where(s.audit.c.org_id == p.org_id)
                    .order_by(s.audit.c.created_at.desc(), s.audit.c.id)
                    .limit(min(limit, 200))
                )
                .mappings()
                .all()
            )
            # Deliberately no raw tool arguments, prompt, screenshots, error bodies or arbitrary audit metadata.
            return [dict(row) for row in rows]

    def operations(self, p: Principal, limit: int = 100) -> list[dict]:
        with self.transaction(p, roles=frozenset({"org_admin", "operator"})) as c:
            rows = (
                c.execute(
                    select(
                        s.runs.c.id,
                        s.runs.c.actor_id,
                        s.runs.c.project_id,
                        s.runs.c.state,
                        s.runs.c.generation,
                        s.runs.c.error_code,
                        s.runs.c.cleanup_state,
                        s.runs.c.created_at,
                        s.runs.c.started_at,
                        s.runs.c.finished_at,
                        s.jobs.c.state.label("job_state"),
                        s.jobs.c.lease_expires_at,
                    )
                    .join(s.jobs, (s.jobs.c.org_id == s.runs.c.org_id) & (s.jobs.c.run_id == s.runs.c.id))
                    .where(s.runs.c.org_id == p.org_id)
                    .order_by(s.runs.c.created_at.desc())
                    .limit(min(limit, 200))
                )
                .mappings()
                .all()
            )
            return [dict(row) for row in rows]

    def stop_run(self, p: Principal, run_id: UUID) -> dict:
        # This is an explicit operation privilege, not permission to read the private Run result.
        with self.transaction(p, roles=frozenset({"org_admin", "operator"})) as c:
            row = c.execute(select(s.runs.c.id).where(s.runs.c.org_id == p.org_id, s.runs.c.id == run_id)).first()
            if row is None:
                raise PlatformError("RESOURCE_NOT_FOUND", "Run is not in this organization", 404)
        from ..runtime.execution import ExecutionStore

        store = ExecutionStore(self.db, self.settings)
        with store._system_locked(p.org_id, run_id) as (c, run, job, now):
            if self.role(c, p) not in {"org_admin", "operator"}:
                raise PlatformError("ADMIN_FORBIDDEN", "Operation privilege changed", 403)
            if run["state"] in {"succeeded", "failed", "cancelled", "timed_out", "recovery_required"}:
                return {"run_id": run_id, "state": run["state"]}
            c.execute(
                update(s.runs)
                .where(s.runs.c.id == run_id)
                .values(state="cancel_requested", revision=s.runs.c.revision + 1)
            )
            c.execute(update(s.jobs).where(s.jobs.c.id == job["id"]).values(state="stopping"))
            self.audit(c, p, "operation.stop", run_id, "cancel_requested")
            store.platform._event(
                c, p.org_id, run_id, "run.cancel_requested", {"state": "cancel_requested", "reason": "OPERATOR_REQUEST"}
            )
            return {"run_id": run_id, "state": "cancel_requested"}

    def policy(self, p: Principal) -> dict:
        with self.transaction(p) as c:
            row = c.execute(select(s.organizations).where(s.organizations.c.id == p.org_id)).mappings().one()
            return {
                key: row[key]
                for key in (
                    "name",
                    "policy_revision",
                    "allowed_classifications",
                    "denied_actions",
                    "storage_limit_bytes",
                )
            }

    def update_policy(self, p: Principal, body) -> dict:
        with self.transaction(p, write=True) as c:
            row = c.execute(select(s.organizations).where(s.organizations.c.id == p.org_id)).mappings().one()
            if row["policy_revision"] != body.expected_revision:
                raise PlatformError("REVISION_CONFLICT", "Policy changed; refresh before saving", 409)
            if set(body.denied_actions) - KNOWN_ACTIONS - {"project.create"}:
                raise PlatformError("INVALID_POLICY", "Unknown action in policy deny list", 422)
            c.execute(
                update(s.organizations)
                .where(s.organizations.c.id == p.org_id)
                .values(
                    allowed_classifications=sorted(set(body.allowed_classifications)),
                    denied_actions=sorted(set(body.denied_actions)),
                    storage_limit_bytes=body.storage_limit_bytes,
                    policy_revision=row["policy_revision"] + 1,
                )
            )
            self.audit(c, p, "organization.policy", p.org_id, "updated")
            return {"policy_revision": row["policy_revision"] + 1}
