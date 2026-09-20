"""Explicit operator CLI for migrations and first organization administration.

Never called by API startup. Database passwords are read from the environment,
not command arguments or checked-in JSON. No destructive downgrade is provided.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate")
    boot = sub.add_parser("bootstrap")
    boot.add_argument("--organization-name", required=True)
    boot.add_argument("--organization-id", type=UUID)
    boot.add_argument("--admin-subject", required=True)
    boot.add_argument("--admin-name", required=True)
    boot.add_argument("--runtime-role", required=True)
    refresh = sub.add_parser("refresh-runtime-grants")
    refresh.add_argument("--runtime-role", required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "apps/local-harness"))
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, insert, select
    from app.db import schema as s
    from app.db.provisioning import grant_runtime_access, provision_identity, provision_runtime_role
    from app.platform_settings import validate_endpoint

    url = os.environ.get("PLATFORM_MIGRATION_DATABASE_URL", "")
    if not url.startswith("postgresql+psycopg://"):
        raise RuntimeError("Set an explicit operator PLATFORM_MIGRATION_DATABASE_URL; legacy .env is not loaded")
    config = Config(str(ROOT / "apps/local-harness/alembic.ini"))
    config.attributes["database_url"] = url
    if args.command == "migrate":
        command.upgrade(config, "head")
        print("Platform schema migration completed. Refresh runtime grants after schema changes.")
        return
    engine = create_engine(url, hide_parameters=True)
    try:
        with engine.begin() as c:
            if args.command == "refresh-runtime-grants":
                grant_runtime_access(c, args.runtime_role)
                print("Runtime privileges refreshed for the explicitly named role.")
                return
            issuer = os.environ.get("PLATFORM_OIDC_ISSUER", "")
            issuer = validate_endpoint(
                issuer, "OIDC issuer", production=os.environ.get("HARNESS_MODE") != "platform-test"
            )
            password = os.environ.get("PLATFORM_RUNTIME_DATABASE_PASSWORD", "")
            if len(password) < 32:
                raise RuntimeError(
                    "Provide a strong PLATFORM_RUNTIME_DATABASE_PASSWORD through the operator environment"
                )
            if (
                not 1 <= len(args.organization_name.strip()) <= 200
                or not 1 <= len(args.admin_name.strip()) <= 100
                or not 1 <= len(args.admin_subject) <= 255
            ):
                raise ValueError("Organization and identity fields are outside their supported bounds")
            org_id = args.organization_id or uuid4()
            if c.execute(select(s.organizations.c.id).where(s.organizations.c.id == org_id)).first():
                raise RuntimeError("Organization already exists; bootstrap never overwrites an existing tenant")
            provision_runtime_role(c, args.runtime_role, password)
            c.execute(
                insert(s.organizations).values(
                    id=org_id,
                    name=args.organization_name.strip(),
                    allowed_classifications=["public", "internal"],
                    denied_actions=[],
                )
            )
            existing = c.execute(
                select(s.users.c.id).where(s.users.c.issuer == issuer, s.users.c.subject == args.admin_subject)
            ).scalar_one_or_none()
            user_id = existing or uuid4()
            if existing:
                c.execute(
                    insert(s.memberships).values(
                        org_id=org_id, user_id=user_id, role="org_admin", display_name=args.admin_name
                    )
                )
            else:
                provision_identity(
                    c,
                    org_id=org_id,
                    user_id=user_id,
                    issuer=issuer,
                    subject=args.admin_subject,
                    display_name=args.admin_name,
                    role="org_admin",
                )
        print("Organization created:", org_id)
        print(
            "Configure PLATFORM_LOGIN_ORG_ID with this ID, deploy API/Worker, then grant models/tools and task budgets from the management UI."
        )
        print("Passwords and client secrets were not printed or written to the repository.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
