"""Pre-flight guards for migrations that read existing tenant rows.

Every tenant table has been FORCE ROW LEVEL SECURITY protected since 0001_platform, and
FORCE RLS applies to the table owner too. Migrations run through migrations/env.py, which
deliberately never sets the aio.org_id GUC that every tenant_scope policy compares against.

A schema-only migration is unaffected: DDL is not filtered by RLS. A migration that BACKFILLS
is affected, and the failure is silent rather than loud - a tenant-scoped identity reads zero
rows, writes an empty projection, and commits successfully. Any migration that reads existing
rows must call require_unblinded_tenant_read first.
"""

from sqlalchemy import text

# Stable migration constants, not user input: aio_users is a BOOTSTRAP table and has been
# exempt from row level security since 0001_platform, so it stays readable even when a
# tenant-scoped identity is blinded to every tenant table.
WITNESS = "aio_users"
ROOT = "aio_organizations"


def require_unblinded_tenant_read(connection, consequence: str) -> None:
    """Refuse unless this identity can actually see existing tenant rows.

    ``consequence`` states what the caller would silently lose, so the operator gets an
    actionable refusal instead of a success report over missing data.
    """
    exempt = connection.execute(
        text("SELECT bool_or(rolsuper OR rolbypassrls) FROM pg_roles WHERE rolname = CURRENT_USER")
    ).scalar()
    if not exempt:
        raise RuntimeError(
            "This migration reads existing rows and requires a migration identity exempt from row level "
            f"security (rolsuper or rolbypassrls); a tenant-scoped identity reads no rows and {consequence}. "
            "Re-run with the operator migration role, not the runtime role."
        )
    # Defence in depth behind the role check: an identity that sees a bootstrap row but no
    # organization at all is reading through a tenant policy, whatever its role attributes say.
    # A genuinely empty database (migrate before bootstrap) has neither, and is allowed through.
    blinded = connection.execute(
        text(f"SELECT (SELECT count(*) FROM {WITNESS}) > 0 AND (SELECT count(*) FROM {ROOT}) = 0")
    ).scalar()
    if blinded:
        raise RuntimeError(
            f"This migration reads existing rows but sees {WITNESS} rows with zero {ROOT}, so row level "
            f"security is filtering its reads and {consequence}. Re-run with the operator migration role, "
            "not the runtime role."
        )
