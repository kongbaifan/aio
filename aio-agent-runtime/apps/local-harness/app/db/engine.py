"""Short scoped PostgreSQL transactions. No implicit schema creation or SQLite fallback."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import NullPool

from ..auth.principal import Principal
from ..platform_errors import PlatformConfigurationError
from .schema import TENANT_TABLES

SCHEMA_REVISION = "0014_audit_records"


class Database:
    def __init__(self, url: str, *, null_pool: bool = False):
        if not url.startswith("postgresql+psycopg://"):
            raise PlatformConfigurationError("Platform persistence requires PostgreSQL")
        kwargs = {"poolclass": NullPool} if null_pool else {"pool_size": 10, "max_overflow": 5, "pool_pre_ping": True}
        self.engine: Engine = create_engine(url, hide_parameters=True, connect_args={"connect_timeout": 5}, **kwargs)

    def dispose(self) -> None:
        self.engine.dispose()

    @contextmanager
    def transaction(self, principal: Principal) -> Iterator[Connection]:
        with self.scoped(principal.org_id, principal.user_id) as connection:
            yield connection

    @contextmanager
    def scoped(self, org_id: UUID, user_id: UUID) -> Iterator[Connection]:
        if not isinstance(org_id, UUID) or not isinstance(user_id, UUID):
            raise ValueError("Database scope requires verified UUIDs")
        with self.engine.begin() as connection:
            connection.execute(
                text("SELECT set_config('aio.org_id', :org, true), set_config('aio.user_id', :usr, true)"),
                {"org": str(org_id), "usr": str(user_id)},
            )
            connection.execute(text("SET LOCAL statement_timeout = '10s'"))
            connection.execute(text("SET LOCAL lock_timeout = '3s'"))
            yield connection

    @contextmanager
    def bootstrap(self) -> Iterator[Connection]:
        """Only verified identity/session bootstrap queries; tenant rows remain RLS-denied."""
        with self.engine.begin() as connection:
            connection.execute(text("SELECT set_config('aio.org_id', '', true), set_config('aio.user_id', '', true)"))
            connection.execute(text("SET LOCAL statement_timeout = '5s'"))
            yield connection

    def verify_runtime_role(self) -> None:
        with self.engine.connect() as connection:
            role = (
                connection.execute(
                    text(
                        "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb FROM pg_roles WHERE rolname=current_user"
                    )
                )
                .mappings()
                .one()
            )
            if any(role.values()):
                raise PlatformConfigurationError("Platform database role has forbidden administrative privileges")
            inherited_admin = connection.execute(
                text(
                    "SELECT EXISTS(SELECT 1 FROM pg_roles r WHERE (r.rolsuper OR r.rolbypassrls OR r.rolcreaterole) "
                    "AND pg_has_role(current_user, r.oid, 'MEMBER'))"
                )
            ).scalar_one()
            if inherited_admin:
                raise PlatformConfigurationError("Platform role can assume privileged database roles")
            versions = connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
            if versions != [SCHEMA_REVISION]:
                raise PlatformConfigurationError("Platform database migration revision is not supported")
            if not connection.execute(
                text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname='vector')")
            ).scalar_one():
                raise PlatformConfigurationError(
                    "Knowledge retrieval requires the operator-installed pgvector extension"
                )
            rows = (
                connection.execute(
                    text(
                        "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, pg_get_userbyid(c.relowner)=current_user AS owned, "
                        "has_table_privilege(current_user, c.oid, 'SELECT') AS readable "
                        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE n.nspname='public' AND c.relkind='r' AND c.relname = ANY(:names)"
                    ),
                    {"names": [table.name for table in TENANT_TABLES]},
                )
                .mappings()
                .all()
            )
            if len(rows) != len(TENANT_TABLES) or any(
                not r["relrowsecurity"] or not r["relforcerowsecurity"] or r["owned"] or not r["readable"] for r in rows
            ):
                raise PlatformConfigurationError("Platform tenant tables must have FORCE RLS and a separate owner")
            unsafe_audit_grants = connection.execute(text(
                "SELECT has_any_column_privilege(current_user, 'aio_audit_events', 'UPDATE') "
                "OR has_table_privilege(current_user, 'aio_audit_events', 'DELETE') "
                "OR has_table_privilege(current_user, 'aio_outbox', 'DELETE') "
                "OR EXISTS(SELECT 1 FROM unnest(ARRAY['id', 'org_id', 'aggregate_id', 'kind', 'payload', 'created_at']) "
                "AS field(name) WHERE has_column_privilege(current_user, 'aio_outbox', field.name, 'UPDATE'))"
            )).scalar_one()
            if unsafe_audit_grants:
                raise PlatformConfigurationError("Platform audit facts and outbox payloads must be immutable")
